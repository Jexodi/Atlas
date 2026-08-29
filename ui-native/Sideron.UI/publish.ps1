$ErrorActionPreference = "Stop"

$Project = Join-Path $PSScriptRoot "Sideron.UI.csproj"

Write-Host "Publication Sideron self-contained..." -ForegroundColor Cyan

dotnet publish `
    $Project `
    -c Release `
    -p:Platform=x64 `
    -p:PublishProfile=win-x64

Write-Host ""
Write-Host "Sortie UI :" -ForegroundColor Green
Write-Host (Join-Path $PSScriptRoot "bin\publish\win-x64")
