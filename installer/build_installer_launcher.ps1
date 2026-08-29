$ErrorActionPreference = "Stop"

$InstallerRoot = $PSScriptRoot
$ProjectRoot = Resolve-Path (Join-Path $InstallerRoot "..")

$LauncherRoot = Join-Path $InstallerRoot "Sideron.Setup.Launcher"
$LauncherProject = Join-Path $LauncherRoot "Sideron.Setup.Launcher.csproj"
$PayloadZip = Join-Path $LauncherRoot "payload.zip"

$ReleaseRoot = Join-Path $ProjectRoot "dist\SIDERON"
$PayloadStage = Join-Path $ProjectRoot "build\installer-payload"
$PayloadValidationRoot = Join-Path $ProjectRoot "build\installer-payload-validation"
$PublishRoot = Join-Path $ProjectRoot "build\installer-launcher"

$UpdateHostRoot = Join-Path $InstallerRoot "Sideron.UpdateHost"
$UpdateHostProject = Join-Path $UpdateHostRoot "Sideron.UpdateHost.csproj"
$UpdateHostPublishRoot = Join-Path $ProjectRoot "build\update-host"
$ProjectsOutputRoot = "D:\Jérémi\Documents\Projects"
$ArchiveRoot = Join-Path $ProjectsOutputRoot "Archive"
$VersionSourcePath = Join-Path $ProjectRoot "config\sideron.json"

if (-not (Test-Path $VersionSourcePath))
{
    throw "Impossible de déterminer la version Sideron : config\sideron.json est introuvable."
}

try
{
    $VersionConfig = Get-Content `
        -Path $VersionSourcePath `
        -Raw `
        -Encoding UTF8 `
        | ConvertFrom-Json

    $SideronBuildVersion = [string]$VersionConfig.sideron.version
}
catch
{
    throw "Impossible de lire la version Sideron depuis config\sideron.json."
}

if ([string]::IsNullOrWhiteSpace($SideronBuildVersion))
{
    throw "La version Sideron est vide dans config\sideron.json."
}

if ($SideronBuildVersion -match "(?i)-dev(?:\.|$)")
{
    $BuildChannel = "DEV"
}
elseif ($SideronBuildVersion -match "(?i)-rc(?:\.|$)")
{
    $BuildChannel = "RC"
}
else
{
    $BuildChannel = "RELEASE"
}

$OutputRoot = Join-Path $ProjectsOutputRoot $BuildChannel
$ArchiveChannelRoot = Join-Path $ArchiveRoot $BuildChannel
$FinalSetupName = "Sideron-$SideronBuildVersion.exe"
$FinalSetupExe = Join-Path $OutputRoot $FinalSetupName

$UninstallLauncherRoot = Join-Path $InstallerRoot "Sideron.Uninstall.Launcher"
$UninstallLauncherProject = Join-Path $UninstallLauncherRoot "Sideron.Uninstall.Launcher.csproj"
$UninstallPublishRoot = Join-Path $ProjectRoot "build\uninstall-launcher"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host " Build SIDERON.Setup.exe autonome" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

if (-not (Test-Path $LauncherProject))
{
    throw "Projet SIDERON.Setup.Launcher introuvable : $LauncherProject"
}

if (-not (Test-Path $UninstallLauncherProject))
{
    throw "Projet SIDERON.Uninstall.Launcher introuvable : $UninstallLauncherProject"
}

if (-not (Test-Path $UpdateHostProject))
{
    throw "Projet Sideron.UpdateHost introuvable : $UpdateHostProject"
}

foreach ($Required in @(
    (Join-Path $ReleaseRoot "SIDERON.exe"),
    (Join-Path $ReleaseRoot "core\SIDERON.Core.exe"),
    (Join-Path $ReleaseRoot "service\SIDERON.Service.exe"),
    (Join-Path $InstallerRoot "installer_gui.ps1"),
    (Join-Path $InstallerRoot "storage_partition.ps1"),
    (Join-Path $InstallerRoot "install_sideron.ps1"),
    (Join-Path $InstallerRoot "uninstall_sideron.ps1"),
    (Join-Path $LauncherRoot "sideron.ico")
))
{
    if (-not (Test-Path $Required))
    {
        throw "Fichier requis manquant : $Required"
    }
}

foreach ($Path in @(
    $PayloadStage,
    $PayloadValidationRoot,
    $PublishRoot,
    $UninstallPublishRoot,
    $UpdateHostPublishRoot
))
{
    if (Test-Path $Path)
    {
        Remove-Item $Path -Recurse -Force
    }

    New-Item -ItemType Directory -Path $Path -Force | Out-Null
}

if (-not (Test-Path $OutputRoot))
{
    New-Item -ItemType Directory -Path $OutputRoot -Force | Out-Null
}

if (-not (Test-Path $ArchiveChannelRoot))
{
    New-Item `
        -ItemType Directory `
        -Path $ArchiveChannelRoot `
        -Force `
        | Out-Null
}

$PreviousSideronBuilds = @(
    Get-ChildItem `
        -Path $OutputRoot `
        -Filter "Sideron-*.exe" `
        -File `
        -ErrorAction SilentlyContinue `
        | Where-Object {
            $_.Name -ne $FinalSetupName
        }
)

foreach ($PreviousSideronBuild in $PreviousSideronBuilds)
{
    $ArchiveDestination = Join-Path `
        $ArchiveChannelRoot `
        $PreviousSideronBuild.Name

    if (Test-Path $ArchiveDestination)
    {
        $ArchiveBaseName = [System.IO.Path]::GetFileNameWithoutExtension(
            $PreviousSideronBuild.Name
        )

        $ArchiveExtension = [System.IO.Path]::GetExtension(
            $PreviousSideronBuild.Name
        )

        $ArchiveTimestamp = Get-Date -Format "yyyyMMdd-HHmmss"

        $ArchiveDestination = Join-Path `
            $ArchiveChannelRoot `
            (
                $ArchiveBaseName +
                "-" +
                $ArchiveTimestamp +
                $ArchiveExtension
            )
    }

    Write-Host (
        "Archivage de l'ancien build : " +
        $PreviousSideronBuild.Name +
        " -> " +
        $ArchiveDestination
    ) -ForegroundColor DarkGray

    Move-Item `
        -Path $PreviousSideronBuild.FullName `
        -Destination $ArchiveDestination `
        -Force `
        -ErrorAction Stop
}

if (Test-Path $PayloadZip)
{
    Remove-Item $PayloadZip -Force
}

Write-Host "1/6 - Préparation du payload..." -ForegroundColor Cyan

foreach ($File in @(
    "installer_gui.ps1",
    "storage_partition.ps1",
    "install_sideron.ps1",
    "uninstall_sideron.ps1"
))
{
    Copy-Item `
        (Join-Path $InstallerRoot $File) `
        (Join-Path $PayloadStage $File) `
        -Force
}

Copy-Item `
    (Join-Path $LauncherRoot "sideron.ico") `
    (Join-Path $PayloadStage "sideron.ico") `
    -Force

Copy-Item `
    $ReleaseRoot `
    (Join-Path $PayloadStage "SIDERON") `
    -Recurse `
    -Force

Write-Host "2/6 - Construction du désinstalleur..." -ForegroundColor Cyan

dotnet publish `
    $UninstallLauncherProject `
    -c Release `
    -r win-x64 `
    --self-contained true `
    -p:PublishSingleFile=true `
    -p:IncludeNativeLibrariesForSelfExtract=true `
    -o $UninstallPublishRoot

if ($LASTEXITCODE -ne 0)
{
    throw "La publication de SIDERON.Uninstall.exe a échoué."
}

$PublishedUninstallExe = Join-Path $UninstallPublishRoot "SIDERON.Uninstall.exe"

if (-not (Test-Path $PublishedUninstallExe))
{
    throw "SIDERON.Uninstall.exe n'a pas été généré."
}

$PayloadSideronRoot = Join-Path $PayloadStage "SIDERON"
$PayloadInstallerRoot = Join-Path $PayloadSideronRoot "installer"

New-Item `
    -ItemType Directory `
    -Path $PayloadInstallerRoot `
    -Force `
    | Out-Null

Copy-Item `
    $PublishedUninstallExe `
    (Join-Path $PayloadSideronRoot "SIDERON.Uninstall.exe") `
    -Force

Copy-Item `
    (Join-Path $InstallerRoot "uninstall_sideron.ps1") `
    (Join-Path $PayloadInstallerRoot "uninstall_sideron.ps1") `
    -Force

Write-Host "3/6 - Construction de Sideron.UpdateHost..." -ForegroundColor Cyan

dotnet publish `
    $UpdateHostProject `
    -c Release `
    -r win-x64 `
    --self-contained true `
    -p:PublishSingleFile=true `
    -p:IncludeNativeLibrariesForSelfExtract=true `
    -o $UpdateHostPublishRoot

if ($LASTEXITCODE -ne 0)
{
    throw "La publication de Sideron.UpdateHost.exe a échoué."
}

$PublishedUpdateHostExe = Join-Path `
    $UpdateHostPublishRoot `
    "Sideron.UpdateHost.exe"

if (-not (Test-Path $PublishedUpdateHostExe))
{
    throw "Sideron.UpdateHost.exe n'a pas été généré."
}

Copy-Item `
    $PublishedUpdateHostExe `
    (Join-Path $PayloadStage "Sideron.UpdateHost.exe") `
    -Force

Copy-Item `
    (Join-Path $LauncherRoot "sideron.ico") `
    (Join-Path $PayloadStage "sideron.ico") `
    -Force

Write-Host "Génération du manifeste d'intégrité SHA-256..." -ForegroundColor Cyan

$IntegrityManifestPath = Join-Path `
    $PayloadSideronRoot `
    "integrity.sha256.json"

$IntegrityEntries = @()

$IntegrityFiles = Get-ChildItem `
    -Path $PayloadSideronRoot `
    -File `
    -Recurse `
    -ErrorAction Stop `
    | Where-Object {
        $_.FullName -ne $IntegrityManifestPath `
        -and $_.FullName -ne (Join-Path $PayloadSideronRoot "config\sideron.json")
    } `
    | Sort-Object FullName

foreach ($IntegrityFile in $IntegrityFiles)
{
    $RelativePath = $IntegrityFile.FullName.Substring(
        $PayloadSideronRoot.Length
    ).TrimStart(
        [System.IO.Path]::DirectorySeparatorChar,
        [System.IO.Path]::AltDirectorySeparatorChar
    )

    $RelativePath = $RelativePath.Replace(
        [System.IO.Path]::DirectorySeparatorChar,
        "/"
    )

    $Hash = Get-FileHash `
        -Path $IntegrityFile.FullName `
        -Algorithm SHA256 `
        -ErrorAction Stop

    $IntegrityEntries += [PSCustomObject]@{
        path = $RelativePath
        sha256 = $Hash.Hash.ToLowerInvariant()
        size = [UInt64]$IntegrityFile.Length
    }
}

$IntegrityManifest = [PSCustomObject]@{
    algorithm = "SHA256"
    generated_utc = [DateTime]::UtcNow.ToString("o")
    excluded = @(
        "integrity.sha256.json",
        "config/sideron.json"
    )
    files = $IntegrityEntries
}

$IntegrityJson = $IntegrityManifest `
    | ConvertTo-Json -Depth 6

[System.IO.File]::WriteAllText(
    $IntegrityManifestPath,
    $IntegrityJson,
    (New-Object System.Text.UTF8Encoding($false))
)

if (-not (Test-Path $IntegrityManifestPath))
{
    throw "Le manifeste d'intégrité Sideron n'a pas été généré."
}

$IntegrityCountMessage = "Manifeste SHA-256 : $($IntegrityEntries.Count) fichiers protégés."
Write-Host $IntegrityCountMessage -ForegroundColor DarkGray

Write-Host "4/6 - Compression du payload interne..." -ForegroundColor Cyan

Compress-Archive `
    -Path (Join-Path $PayloadStage "*") `
    -DestinationPath $PayloadZip `
    -CompressionLevel Optimal `
    -Force

if (-not (Test-Path $PayloadZip))
{
    throw "Le payload.zip n'a pas été généré."
}

Expand-Archive `
    -Path $PayloadZip `
    -DestinationPath $PayloadValidationRoot `
    -Force

# Expand-Archive doit avoir pu lire toute la table centrale du ZIP. Cette
# vérification explicite évite d'embarquer un payload tronqué après une copie
# ou un archivage interrompu.
Add-Type -AssemblyName System.IO.Compression.FileSystem
$PayloadArchive = [System.IO.Compression.ZipFile]::OpenRead($PayloadZip)

try
{
    if ($PayloadArchive.Entries.Count -eq 0)
    {
        throw "Le payload.zip généré est vide."
    }
}
finally
{
    $PayloadArchive.Dispose()
}

$SourceInstallerHash = Get-FileHash `
    -Path (Join-Path $InstallerRoot "install_sideron.ps1") `
    -Algorithm SHA256 `
    -ErrorAction Stop

$EmbeddedInstallerHash = Get-FileHash `
    -Path (Join-Path $PayloadValidationRoot "install_sideron.ps1") `
    -Algorithm SHA256 `
    -ErrorAction Stop

if ($SourceInstallerHash.Hash -ne $EmbeddedInstallerHash.Hash)
{
    throw (
        "Le payload de l'installateur contient une ancienne version " +
        "de install_sideron.ps1. Build interrompu."
    )
}

Remove-Item `
    -Path $PayloadValidationRoot `
    -Recurse `
    -Force

Write-Host "Validation du moteur de mise à jour embarqué : OK" -ForegroundColor Green

Write-Host "5/6 - Publication de SIDERON.Setup.exe..." -ForegroundColor Cyan

dotnet publish `
    $LauncherProject `
    -c Release `
    -r win-x64 `
    --self-contained true `
    -p:PublishSingleFile=true `
    -p:IncludeNativeLibrariesForSelfExtract=true `
    -o $PublishRoot

if ($LASTEXITCODE -ne 0)
{
    throw "La publication de SIDERON.Setup.exe a échoué."
}

$PublishedSetupExe = Join-Path $PublishRoot "SIDERON.Setup.exe"

if (-not (Test-Path $PublishedSetupExe))
{
    throw "SIDERON.Setup.exe n'a pas été généré."
}

Write-Host "6/6 - Assemblage final..." -ForegroundColor Cyan

Copy-Item $PublishedSetupExe $FinalSetupExe -Force

if (-not (Test-Path $FinalSetupExe))
{
    throw "Le fichier final $FinalSetupName n'a pas été généré."
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host " $FinalSetupName autonome généré." -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Canal de build : $BuildChannel" -ForegroundColor Cyan
Write-Host "Fichier final :" -ForegroundColor Green
Write-Host $FinalSetupExe
Write-Host ""
Write-Host "Taille : $([Math]::Round((Get-Item $FinalSetupExe).Length / 1MB, 1)) Mo"
Write-Host ""
Write-Host "Aucun autre fichier n'est nécessaire pour lancer l'installation."
