$ErrorActionPreference = "Stop"

$AtlasRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$Python = Join-Path $AtlasRoot ".venv\Scripts\python.exe"
$Spec = Join-Path $PSScriptRoot "atlas_core.spec"
$BuildRoot = Join-Path $AtlasRoot "build\core-package"
$DistRoot = Join-Path $AtlasRoot "build\core-dist"

if (-not (Test-Path $Python))
{
    throw "Python virtuel introuvable : $Python"
}

& $Python -c "import PyInstaller" 2>$null

if ($LASTEXITCODE -ne 0)
{
    throw @"
PyInstaller n'est pas installe dans le .venv.

Installe la dependance avec :
    .\.venv\Scripts\python.exe -m pip install pyinstaller
"@
}

if (Test-Path $BuildRoot)
{
    Remove-Item $BuildRoot -Recurse -Force
}

if (Test-Path $DistRoot)
{
    Remove-Item $DistRoot -Recurse -Force
}

Push-Location $AtlasRoot

try
{
    Write-Host "Packaging Atlas Core..." -ForegroundColor Cyan

    $PyInstallerStdOut = [System.IO.Path]::GetTempFileName()
    $PyInstallerStdErr = [System.IO.Path]::GetTempFileName()

    try
    {
        $PyInstallerArguments = @(
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--workpath",
            $BuildRoot,
            "--distpath",
            $DistRoot,
            $Spec
        )

        $PyInstallerProcess = Start-Process `
            -FilePath $Python `
            -ArgumentList $PyInstallerArguments `
            -Wait `
            -PassThru `
            -NoNewWindow `
            -RedirectStandardOutput $PyInstallerStdOut `
            -RedirectStandardError $PyInstallerStdErr

        if (Test-Path $PyInstallerStdOut)
        {
            Get-Content `
                -Path $PyInstallerStdOut `
                -ErrorAction SilentlyContinue `
                | ForEach-Object {
                    if (-not [string]::IsNullOrWhiteSpace($_))
                    {
                        Write-Host $_
                    }
                }
        }

        if (Test-Path $PyInstallerStdErr)
        {
            Get-Content `
                -Path $PyInstallerStdErr `
                -ErrorAction SilentlyContinue `
                | ForEach-Object {
                    if (-not [string]::IsNullOrWhiteSpace($_))
                    {
                        Write-Host $_ -ForegroundColor DarkGray
                    }
                }
        }

        if ($PyInstallerProcess.ExitCode -ne 0)
        {
            throw "PyInstaller a echoue avec le code $($PyInstallerProcess.ExitCode)."
        }
    }
    finally
    {
        Remove-Item `
            -Path $PyInstallerStdOut `
            -Force `
            -ErrorAction SilentlyContinue

        Remove-Item `
            -Path $PyInstallerStdErr `
            -Force `
            -ErrorAction SilentlyContinue
    }
}
finally
{
    Pop-Location
}

$CoreRoot = Join-Path $DistRoot "Atlas.Core"
$CoreExe = Join-Path $CoreRoot "Atlas.Core.exe"
$CoreInternal = Join-Path $CoreRoot "_internal"
$CoreBaseLibrary = Join-Path $CoreInternal "base_library.zip"

if (-not (Test-Path $CoreExe))
{
    throw "Atlas.Core.exe n'a pas ete genere."
}

if (-not (Test-Path $CoreInternal))
{
    throw "Le dossier runtime Atlas.Core\\_internal n'a pas ete genere."
}

# PyInstaller doit normalement produire base_library.zip pour un build
# onedir avec noarchive=False. Sur certains builds Python 3.14 du Core,
# l'analyse peut toutefois se terminer sans l'ajouter au COLLECT.
#
# Dans ce cas, on genere un bundle Python minimal AVEC LE MEME interpreteur
# et la MEME version de PyInstaller, puis on recupere uniquement sa
# base_library.zip. Cette archive contient exclusivement les modules
# bootstrap de la bibliotheque standard Python (dont encodings).
if (-not (Test-Path $CoreBaseLibrary))
{
    Write-Host ""
    Write-Host "base_library.zip absent du Core ; reconstruction du runtime Python de base..." -ForegroundColor Yellow

    $BootstrapRoot = Join-Path $AtlasRoot "build\\core-bootstrap-library"
    $BootstrapWork = Join-Path $BootstrapRoot "work"
    $BootstrapDist = Join-Path $BootstrapRoot "dist"
    $BootstrapScript = Join-Path $BootstrapRoot "bootstrap.py"

    if (Test-Path $BootstrapRoot)
    {
        Remove-Item $BootstrapRoot -Recurse -Force
    }

    New-Item `
        -ItemType Directory `
        -Path $BootstrapRoot `
        -Force `
        | Out-Null

    $Utf8NoBom = New-Object System.Text.UTF8Encoding($false)

    [System.IO.File]::WriteAllText(
        $BootstrapScript,
        "pass`r`n",
        $Utf8NoBom
    )

    $BootstrapStdOut = [System.IO.Path]::GetTempFileName()
    $BootstrapStdErr = [System.IO.Path]::GetTempFileName()

    try
    {
        $BootstrapArguments = @(
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--onedir",
            "--name",
            "Atlas.Core.Bootstrap",
            "--workpath",
            $BootstrapWork,
            "--distpath",
            $BootstrapDist,
            $BootstrapScript
        )

        $BootstrapProcess = Start-Process `
            -FilePath $Python `
            -ArgumentList $BootstrapArguments `
            -Wait `
            -PassThru `
            -NoNewWindow `
            -RedirectStandardOutput $BootstrapStdOut `
            -RedirectStandardError $BootstrapStdErr

        if ($BootstrapProcess.ExitCode -ne 0)
        {
            if (Test-Path $BootstrapStdOut)
            {
                Get-Content $BootstrapStdOut -ErrorAction SilentlyContinue |
                    ForEach-Object {
                        if (-not [string]::IsNullOrWhiteSpace($_))
                        {
                            Write-Host $_
                        }
                    }
            }

            if (Test-Path $BootstrapStdErr)
            {
                Get-Content $BootstrapStdErr -ErrorAction SilentlyContinue |
                    ForEach-Object {
                        if (-not [string]::IsNullOrWhiteSpace($_))
                        {
                            Write-Host $_ -ForegroundColor DarkGray
                        }
                    }
            }

            throw "Impossible de reconstruire base_library.zip (PyInstaller code $($BootstrapProcess.ExitCode))."
        }

        $BootstrapBaseLibrary = Join-Path `
            $BootstrapDist `
            "Atlas.Core.Bootstrap\\_internal\\base_library.zip"

        if (-not (Test-Path $BootstrapBaseLibrary))
        {
            throw "Le bundle Python minimal n'a pas produit base_library.zip."
        }

        Copy-Item `
            -Path $BootstrapBaseLibrary `
            -Destination $CoreBaseLibrary `
            -Force

        Write-Host "base_library.zip restaure dans Atlas.Core\\_internal." -ForegroundColor Green
    }
    finally
    {
        Remove-Item `
            -Path $BootstrapStdOut `
            -Force `
            -ErrorAction SilentlyContinue

        Remove-Item `
            -Path $BootstrapStdErr `
            -Force `
            -ErrorAction SilentlyContinue

        Remove-Item `
            -Path $BootstrapRoot `
            -Recurse `
            -Force `
            -ErrorAction SilentlyContinue
    }
}

if (-not (Test-Path $CoreBaseLibrary))
{
    throw "Runtime Python Core incomplet : base_library.zip est absent."
}

$CorePythonDll = Get-ChildItem `
    -Path $CoreInternal `
    -Filter "python3*.dll" `
    -File `
    -ErrorAction SilentlyContinue `
    | Where-Object {
        $_.Name -ne "python3.dll"
    } `
    | Select-Object -First 1

if ($null -eq $CorePythonDll)
{
    throw "Runtime Python Core incomplet : DLL Python versionnee absente de _internal."
}

# On ne se contente pas de verifier le nom du fichier : l'archive doit
# reellement contenir les codecs de demarrage necessaires a Python.
& $Python -c "import sys,zipfile; p=sys.argv[1]; z=zipfile.ZipFile(p); names=set(z.namelist()); req=('encodings/__init__.pyc','encodings/utf_8.pyc'); missing=[x for x in req if x not in names]; print('base_library.zip:', p); print('encodings bootstrap: OK' if not missing else 'missing: '+', '.join(missing)); sys.exit(0 if not missing else 7)" $CoreBaseLibrary

if ($LASTEXITCODE -ne 0)
{
    throw "Runtime Python Core invalide : base_library.zip ne contient pas les modules encodings requis."
}

Write-Host ""
Write-Host "Atlas.Core genere et runtime Python valide :" -ForegroundColor Green
Write-Host "Executable   : $CoreExe"
Write-Host "Python DLL   : $($CorePythonDll.FullName)"
Write-Host "Base library : $CoreBaseLibrary"
