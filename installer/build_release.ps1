$ErrorActionPreference = "Stop"

$SideronRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$Python = Join-Path $SideronRoot ".venv\Scripts\python.exe"

$UiProject = Join-Path $SideronRoot "ui-native\Sideron.UI"
$UiPublish = Join-Path $UiProject "bin\publish\win-x64"

$CoreDist = Join-Path $SideronRoot "build\core-dist\SIDERON.Core"

# IMPORTANT :
# SIDERONService peut être en cours d'exécution depuis build\service-dist.
# La release utilise donc des dossiers dédiés afin de ne jamais toucher
# aux fichiers chargés par le service Windows actif.
$ServiceReleaseBuildRoot = Join-Path $SideronRoot "build\release-service-package"
$ServiceReleaseDistRoot = Join-Path $SideronRoot "build\release-service-dist"
$ServiceDist = Join-Path $ServiceReleaseDistRoot "SIDERON.Service"

$ReleaseRoot = Join-Path $SideronRoot "dist\SIDERON"
$ReleaseCore = Join-Path $ReleaseRoot "core"
$ReleaseService = Join-Path $ReleaseRoot "service"

Write-Host "=== Sideron Release Builder ===" -ForegroundColor Cyan
Write-Host ""

Write-Host "1/4 - Packaging Core Python..." -ForegroundColor Cyan
& (Join-Path $PSScriptRoot "build_core.ps1")

if ($LASTEXITCODE -ne 0)
{
    throw "Le packaging du Core a echoue."
}

Write-Host ""
Write-Host "2/4 - Packaging SideronService autonome..." -ForegroundColor Cyan
& (Join-Path $PSScriptRoot "build_service.ps1") `
    -BuildRoot $ServiceReleaseBuildRoot `
    -DistRoot $ServiceReleaseDistRoot

if ($LASTEXITCODE -ne 0)
{
    throw "Le packaging de SideronService a echoue."
}

Write-Host ""
Write-Host "3/4 - Publication Sideron UI..." -ForegroundColor Cyan
& (Join-Path $UiProject "publish.ps1")

if ($LASTEXITCODE -ne 0)
{
    throw "La publication de l'interface a echoue."
}

if (Test-Path $ReleaseRoot)
{
    Remove-Item $ReleaseRoot -Recurse -Force
}

New-Item `
    -ItemType Directory `
    -Path $ReleaseRoot `
    -Force `
    | Out-Null

New-Item `
    -ItemType Directory `
    -Path $ReleaseCore `
    -Force `
    | Out-Null

New-Item `
    -ItemType Directory `
    -Path $ReleaseService `
    -Force `
    | Out-Null

Write-Host ""
Write-Host "4/4 - Assemblage dist\SIDERON..." -ForegroundColor Cyan

Copy-Item `
    (Join-Path $UiPublish "*") `
    $ReleaseRoot `
    -Recurse `
    -Force

Copy-Item `
    (Join-Path $CoreDist "*") `
    $ReleaseCore `
    -Recurse `
    -Force

Copy-Item `
    (Join-Path $ServiceDist "*") `
    $ReleaseService `
    -Recurse `
    -Force

foreach ($Folder in @(
    "config",
    "assets"
))
{
    $Source = Join-Path $SideronRoot $Folder

    if (Test-Path $Source)
    {
        Copy-Item `
            $Source `
            (Join-Path $ReleaseRoot $Folder) `
            -Recurse `
            -Force
    }
}

$SideronExe = Join-Path $ReleaseRoot "SIDERON.exe"
$CoreExe = Join-Path $ReleaseCore "SIDERON.Core.exe"
$ServiceExe = Join-Path $ReleaseService "SIDERON.Service.exe"
$CoreBaseLibrary = Join-Path $ReleaseCore "_internal\base_library.zip"
$CorePythonDll = Get-ChildItem `
    -Path (Join-Path $ReleaseCore "_internal") `
    -Filter "python3*.dll" `
    -File `
    -ErrorAction SilentlyContinue `
    | Where-Object {
        $_.Name -ne "python3.dll"
    } `
    | Select-Object -First 1

if (-not (Test-Path $SideronExe))
{
    throw "SIDERON.exe est absent du dossier de distribution."
}

if (-not (Test-Path $CoreExe))
{
    throw "SIDERON.Core.exe est absent du dossier de distribution."
}

if (-not (Test-Path $CoreBaseLibrary))
{
    throw "Runtime Python Core incomplet dans la release : core\_internal\base_library.zip est absent."
}

if ($null -eq $CorePythonDll)
{
    throw "Runtime Python Core incomplet dans la release : DLL Python versionnee absente."
}

& $Python -c "import sys,zipfile; z=zipfile.ZipFile(sys.argv[1]); names=set(z.namelist()); req=('encodings/__init__.pyc','encodings/utf_8.pyc'); missing=[x for x in req if x not in names]; sys.exit(0 if not missing else 7)" $CoreBaseLibrary

if ($LASTEXITCODE -ne 0)
{
    throw "Runtime Python Core invalide dans la release : encodings est absent ou incomplet."
}

Write-Host ""
Write-Host "Validation runtime SIDERON.Core de la release : OK" -ForegroundColor Green
Write-Host "Base library : $CoreBaseLibrary"
Write-Host "Python DLL   : $($CorePythonDll.FullName)"

if (-not (Test-Path $ServiceExe))
{
    throw "SIDERON.Service.exe est absent du dossier de distribution."
}

Write-Host ""
Write-Host "Validation SIDERON.Service.exe de la release..." -ForegroundColor Cyan

$ServiceSelfTest = Start-Process `
    -FilePath $ServiceExe `
    -ArgumentList "--self-test" `
    -Wait `
    -PassThru

if ($ServiceSelfTest.ExitCode -ne 0)
{
    throw "L'auto-test du SIDERON.Service.exe de la release a echoue avec le code $($ServiceSelfTest.ExitCode)."
}

Write-Host ""
Write-Host "Distribution portable Sideron complete :" -ForegroundColor Green
Write-Host $ReleaseRoot
Write-Host ""
Write-Host "Executables principaux :" -ForegroundColor Green
Write-Host "UI      : $SideronExe"
Write-Host "Core    : $CoreExe"
Write-Host "Service : $ServiceExe"
Write-Host ""
Write-Host "SideronService n'est pas installe automatiquement par ce build." -ForegroundColor DarkGray
Write-Host "L'installation Windows complete sera ajoutee a l'etape installateur." -ForegroundColor DarkGray
