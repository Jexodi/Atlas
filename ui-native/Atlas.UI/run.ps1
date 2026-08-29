$ErrorActionPreference = "Stop"

$Project = Join-Path $PSScriptRoot "Atlas.UI.csproj"
$AtlasRoot = Resolve-Path (Join-Path $PSScriptRoot "..\\..")
$MainCore = [System.IO.Path]::GetFullPath((Join-Path $AtlasRoot "main_core.py"))

# Un test de développement ne doit pas réutiliser le Core de l'installation
# Windows, qui ne contient pas nécessairement les dernières modifications.
Stop-Service -Name "AtlasV2Service" -Force -ErrorAction SilentlyContinue

Get-Process -Name "Atlas.Core", "Atlas.Service" -ErrorAction SilentlyContinue |
    Stop-Process -Force -ErrorAction SilentlyContinue

# Arrête uniquement un ancien Core Python de ce projet.
Get-CimInstance Win32_Process `
    -Filter "Name = 'python.exe' OR Name = 'pythonw.exe'" `
    -ErrorAction SilentlyContinue |
    Where-Object {
        $CommandLine = [string]$_.CommandLine
        $CommandLine -and $CommandLine.IndexOf(
            $MainCore,
            [System.StringComparison]::OrdinalIgnoreCase
        ) -ge 0
    } |
    ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }

dotnet run `
    --project $Project `
    -c Debug `
    -p:Platform=x64
