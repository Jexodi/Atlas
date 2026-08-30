$ErrorActionPreference = "Stop"

$Project = Join-Path $PSScriptRoot "Sideron.UI.csproj"

Write-Host "Restauration Sideron.UI..." -ForegroundColor Cyan
dotnet restore $Project

Write-Host "Compilation Sideron.UI..." -ForegroundColor Cyan
dotnet build $Project -c Debug -p:Platform=x64

Write-Host ""
Write-Host "Compilation terminee." -ForegroundColor Green
