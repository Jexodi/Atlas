$ErrorActionPreference = "Stop"

$AtlasRoot = "C:\Atlas"

$FilesToRemove = @(
    "ui-native\Atlas.UI\Services\ApplicationCatalogService.cs",
    "ui-native\Atlas.UI\Services\ExternalApplicationHostService.cs",
    "ui-native\Atlas.UI\Models\InstalledApplication.cs"
)

Write-Host ""
Write-Host "Suppression du module Applications externes..."
Write-Host ""

foreach ($RelativePath in $FilesToRemove) {
    $FullPath = Join-Path $AtlasRoot $RelativePath

    if (Test-Path $FullPath) {
        Remove-Item $FullPath -Force
        Write-Host "[SUPPRIME] $RelativePath"
    }
    else {
        Write-Host "[DEJA ABSENT] $RelativePath"
    }
}

Write-Host ""
Write-Host "Nettoyage termine."
Write-Host ""
