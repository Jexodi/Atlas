$ErrorActionPreference = "Stop"

$Project = Join-Path $PSScriptRoot "Atlas.UI.csproj"

Write-Host "Restauration Atlas.UI..." -ForegroundColor Cyan
dotnet restore $Project

Write-Host "Compilation Atlas.UI..." -ForegroundColor Cyan
dotnet build $Project -c Debug -p:Platform=x64

Write-Host ""
Write-Host "Compilation terminee." -ForegroundColor Green
