param(
    [string]$BuildRoot = "",
    [string]$DistRoot = ""
)

$ErrorActionPreference = "Stop"

$AtlasRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$Python = Join-Path $AtlasRoot ".venv\Scripts\python.exe"
$Spec = Join-Path $PSScriptRoot "atlas_service.spec"

if ([string]::IsNullOrWhiteSpace($BuildRoot))
{
    $BuildRoot = Join-Path $AtlasRoot "build\service-package"
}

if ([string]::IsNullOrWhiteSpace($DistRoot))
{
    $DistRoot = Join-Path $AtlasRoot "build\service-dist"
}

$ServiceExe = Join-Path $DistRoot "Atlas.Service\Atlas.Service.exe"

Write-Host "=== AtlasService Standalone Builder ===" -ForegroundColor Cyan
Write-Host ""

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

if (-not (Test-Path $Spec))
{
    throw "Spec AtlasService introuvable : $Spec"
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
    Write-Host "1/2 - Packaging AtlasService..." -ForegroundColor Cyan

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

if (-not (Test-Path $ServiceExe))
{
    throw "Atlas.Service.exe n'a pas ete genere."
}

Write-Host ""
Write-Host "2/2 - Auto-test de l'executable autonome..." -ForegroundColor Cyan

$Process = Start-Process `
    -FilePath $ServiceExe `
    -ArgumentList "--self-test" `
    -Wait `
    -PassThru

if ($Process.ExitCode -ne 0)
{
    throw "L'auto-test Atlas.Service.exe a echoue avec le code $($Process.ExitCode)."
}

Write-Host ""
Write-Host "Atlas.Service.exe autonome genere et valide :" -ForegroundColor Green
Write-Host $ServiceExe
Write-Host ""
Write-Host "Aucune installation de service Windows n'a ete modifiee." -ForegroundColor DarkGray
