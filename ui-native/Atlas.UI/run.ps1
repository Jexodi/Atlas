$ErrorActionPreference = "Stop"

$Project = Join-Path $PSScriptRoot "Atlas.UI.csproj"

dotnet run `
    --project $Project `
    -c Debug `
    -p:Platform=x64
