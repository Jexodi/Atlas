param(
    [ValidateSet("Folder", "Shrink", "WholeDisk")]
    [string]$Mode = "Folder",

    [ValidateRange(10, 2048)]
    [int]$PartitionSizeGB = 50,

    [int]$DiskNumber = -1,

    [int]$PartitionNumber = -1,

    [switch]$Apply,

    [string]$Confirmation = ""
)

$ErrorActionPreference = "Stop"

$SideronVolumeLabel = "SIDERON"
$DefaultFolderRoot = "C:\SIDERON"

$SideronFolders = @(
    "Backups",
    "Cache",
    "Documents",
    "Exports",
    "Imports",
    "Memory",
    "Projects",
    "System",
    "Temp"
)

function Test-Administrator
{
    $Identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $Principal = New-Object Security.Principal.WindowsPrincipal($Identity)

    return $Principal.IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator
    )
}

function Format-Bytes
{
    param(
        [UInt64]$Bytes
    )

    if ($Bytes -ge 1TB)
    {
        return "{0:N2} To" -f ($Bytes / 1TB)
    }

    if ($Bytes -ge 1GB)
    {
        return "{0:N2} Go" -f ($Bytes / 1GB)
    }

    if ($Bytes -ge 1MB)
    {
        return "{0:N2} Mo" -f ($Bytes / 1MB)
    }

    return "$Bytes octets"
}

function Get-FirstAvailableSideronDriveLetter
{
    # A: reste prioritaire. C: est volontairement exclu.
    $Candidates = @(
        "A", "B",
        "D", "E", "F", "G", "H", "I", "J", "K", "L", "M",
        "N", "O", "P", "Q", "R", "S", "T", "U", "V", "W",
        "X", "Y", "Z"
    )

    $UsedLetters = @(
        Get-Volume `
            -ErrorAction SilentlyContinue `
        | Where-Object {
            $null -ne $_.DriveLetter
        } `
        | ForEach-Object {
            $_.DriveLetter.ToString().ToUpperInvariant()
        }
    )

    foreach ($Candidate in $Candidates)
    {
        if ($UsedLetters -notcontains $Candidate)
        {
            return $Candidate
        }
    }

    throw "Aucune lettre de lecteur n'est disponible pour le volume SIDERON."
}

function Initialize-SideronStorageLayout
{
    param(
        [string]$Root
    )

    if (-not (Test-Path $Root))
    {
        New-Item `
            -ItemType Directory `
            -Path $Root `
            -Force `
            | Out-Null
    }

    foreach ($Folder in $SideronFolders)
    {
        $FolderPath = Join-Path $Root $Folder

        New-Item `
            -ItemType Directory `
            -Path $FolderPath `
            -Force `
            | Out-Null
    }
}

function Get-ShrinkPlan
{
    param(
        [int]$RequestedDiskNumber,
        [int]$RequestedPartitionNumber,
        [int]$RequestedSizeGB
    )

    if ($RequestedDiskNumber -lt 0)
    {
        throw "Indique -DiskNumber pour choisir le disque à partitionner."
    }

    if ($RequestedPartitionNumber -lt 0)
    {
        throw "Indique -PartitionNumber pour choisir la partition à réduire."
    }

    $Partition = Get-Partition `
        -DiskNumber $RequestedDiskNumber `
        -PartitionNumber $RequestedPartitionNumber `
        -ErrorAction Stop

    $PartitionType = [string]$Partition.Type
    $PartitionSize = [UInt64]$Partition.Size
    $RequestedBytes = [UInt64]$RequestedSizeGB * 1GB

    $ProtectedTypes = @(
        "System",
        "Reserved",
        "Recovery",
        "Unknown"
    )

    if ($ProtectedTypes -contains $PartitionType)
    {
        throw (
            "La partition sélectionnée est de type '$PartitionType'. " +
            "Sideron refuse de réduire les partitions système, réservées ou de récupération."
        )
    }

    if ($RequestedBytes -ge $PartitionSize)
    {
        throw (
            "La taille demandée pour SIDERON ($RequestedSizeGB Go) " +
            "est supérieure ou égale à la taille de la partition sélectionnée " +
            "($(Format-Bytes $PartitionSize))."
        )
    }

    $Volume = $Partition `
        | Get-Volume `
            -ErrorAction Stop

    if ($null -eq $Volume)
    {
        throw "La partition sélectionnée n'est pas associée à un volume exploitable."
    }

    if ($Volume.FileSystem -ne "NTFS")
    {
        throw (
            "Sideron réduit uniquement une partition NTFS. " +
            "Format détecté : $($Volume.FileSystem)."
        )
    }

    if ($null -eq $Volume.DriveLetter)
    {
        throw "La partition sélectionnée ne possède pas de lettre de lecteur."
    }

    $Supported = Get-PartitionSupportedSize `
        -DiskNumber $RequestedDiskNumber `
        -PartitionNumber $RequestedPartitionNumber `
        -ErrorAction Stop

    $CurrentSize = [UInt64]$Partition.Size
    $MinimumSize = [UInt64]$Supported.SizeMin
    $FreeBytes = [UInt64]$Volume.SizeRemaining
    $SafetyMarginBytes = [UInt64](10GB)

    if ($CurrentSize -le $MinimumSize)
    {
        $MaximumShrinkBytes = [UInt64]0
    }
    else
    {
        $MaximumShrinkBytes = [UInt64]($CurrentSize - $MinimumSize)
    }

    if ($FreeBytes -le $SafetyMarginBytes)
    {
        $MaximumByFreeSpace = [UInt64]0
    }
    else
    {
        $MaximumByFreeSpace = [UInt64]($FreeBytes - $SafetyMarginBytes)
    }

    $SafeMaximumShrinkBytes = [UInt64](
        [Math]::Min(
            [double]$MaximumShrinkBytes,
            [double]$MaximumByFreeSpace
        )
    )

    $CanCreate = ($RequestedBytes -le $SafeMaximumShrinkBytes) -and ($RequestedBytes -ge 10GB)

    $NewSourceSizeBytes = [UInt64]0

    if ($RequestedBytes -lt $CurrentSize)
    {
        $NewSourceSizeBytes = [UInt64]($CurrentSize - $RequestedBytes)
    }

    [PSCustomObject]@{
        Mode = "Shrink"
        DiskNumber = $RequestedDiskNumber
        PartitionNumber = $RequestedPartitionNumber
        PartitionType = $PartitionType
        SourceDriveLetter = $Volume.DriveLetter
        SourceFileSystem = $Volume.FileSystem
        SourceCurrentSizeBytes = $CurrentSize
        SourceFreeBytes = $FreeBytes
        WindowsMinimumSizeBytes = $MinimumSize
        SafeMaximumShrinkBytes = $SafeMaximumShrinkBytes
        RequestedSizeBytes = $RequestedBytes
        RequestedSizeGB = $RequestedSizeGB
        NewSourceSizeBytes = $NewSourceSizeBytes
        TargetDriveLetter = Get-FirstAvailableSideronDriveLetter
        VolumeLabel = $SideronVolumeLabel
        CanCreate = $CanCreate
    }
}


function Get-WholeDiskPlan
{
    param(
        [int]$RequestedDiskNumber
    )

    if ($RequestedDiskNumber -lt 0)
    {
        throw "Indique -DiskNumber pour choisir le disque entier à dédier à Sideron."
    }

    $Disk = Get-Disk `
        -Number $RequestedDiskNumber `
        -ErrorAction Stop

    if ($Disk.IsBoot -or $Disk.IsSystem)
    {
        throw "Sideron refuse d'effacer le disque système ou le disque de démarrage."
    }

    if ($Disk.Size -lt 10GB)
    {
        throw "Le disque choisi est trop petit pour être dédié à Sideron."
    }

    [PSCustomObject]@{
        Mode = "WholeDisk"
        DiskNumber = $RequestedDiskNumber
        FriendlyName = $Disk.FriendlyName
        BusType = $Disk.BusType
        SizeBytes = [UInt64]$Disk.Size
        TargetDriveLetter = Get-FirstAvailableSideronDriveLetter
        VolumeLabel = $SideronVolumeLabel
        CanCreate = $true
    }
}

function Show-ShrinkPlan
{
    param(
        $Plan
    )

    Write-Host "Mode                     : réduction d'une partition"
    Write-Host "Disque                   : $($Plan.DiskNumber)"
    Write-Host "Partition                : $($Plan.PartitionNumber)"
    Write-Host "Type                     : $($Plan.PartitionType)"
    Write-Host "Volume source            : $($Plan.SourceDriveLetter):"
    Write-Host "Taille actuelle          : $(Format-Bytes $Plan.SourceCurrentSizeBytes)"
    Write-Host "Espace libre             : $(Format-Bytes $Plan.SourceFreeBytes)"
    Write-Host "Réduction max Sideron sûre : $(Format-Bytes $Plan.SafeMaximumShrinkBytes)"
    Write-Host "Taille volume SIDERON      : $($Plan.RequestedSizeGB) Go"
    Write-Host "Lettre attribuée         : $($Plan.TargetDriveLetter):"
    Write-Host "Nom du volume            : $($Plan.VolumeLabel)"
}

function Show-WholeDiskPlan
{
    param(
        $Plan
    )

    Write-Host "Mode             : disque entier dédié"
    Write-Host "Disque           : $($Plan.DiskNumber)"
    Write-Host "Nom              : $($Plan.FriendlyName)"
    Write-Host "Type             : $($Plan.BusType)"
    Write-Host "Taille           : $(Format-Bytes $Plan.SizeBytes)"
    Write-Host "Lettre attribuée : $($Plan.TargetDriveLetter):"
    Write-Host "Nom du volume    : $($Plan.VolumeLabel)"
    Write-Host ""
    Write-Host "ATTENTION : TOUT LE CONTENU DE CE DISQUE SERA EFFACÉ." -ForegroundColor Red
}

function Close-SideronAutoOpenedExplorer
{
    param(
        [string]$DriveLetter
    )

    $ExpectedRoot = $DriveLetter.TrimEnd(":") + ":\"
    $Deadline = (Get-Date).AddSeconds(3)

    do
    {
        try
        {
            $Shell = New-Object -ComObject Shell.Application
            $Windows = @($Shell.Windows())

            foreach ($Window in $Windows)
            {
                try
                {
                    $FullName = [string]$Window.FullName

                    if ([string]::IsNullOrWhiteSpace($FullName))
                    {
                        continue
                    }

                    if (-not $FullName.EndsWith("explorer.exe", [System.StringComparison]::OrdinalIgnoreCase))
                    {
                        continue
                    }

                    $LocationUrl = [string]$Window.LocationURL

                    if ([string]::IsNullOrWhiteSpace($LocationUrl))
                    {
                        continue
                    }

                    $LocationUri = New-Object System.Uri($LocationUrl)
                    $LocalPath = [System.Uri]::UnescapeDataString($LocationUri.LocalPath)
                    $NormalizedPath = $LocalPath.TrimEnd("\") + "\"

                    if ([string]::Equals($NormalizedPath, $ExpectedRoot, [System.StringComparison]::OrdinalIgnoreCase))
                    {
                        $Window.Quit()
                    }
                }
                catch
                {
                    # Une fenêtre Explorer peut disparaître pendant
                    # l'énumération. Ce cas est sans conséquence.
                }
            }
        }
        catch
        {
            # L'installation ne doit jamais échouer uniquement
            # parce que l'automatisation Explorer est indisponible.
        }

        Start-Sleep -Milliseconds 200
    }
    while ((Get-Date) -lt $Deadline)
}


function New-SideronVolumeFromShrink
{
    param(
        $Plan
    )

    $CreatedPartition = $null
    $ShrinkCompleted = $false

    try
    {
        Write-Host "1/5 - Réduction de la partition source..." -ForegroundColor Cyan

        Resize-Partition `
            -DiskNumber $Plan.DiskNumber `
            -PartitionNumber $Plan.PartitionNumber `
            -Size $Plan.NewSourceSizeBytes `
            -ErrorAction Stop

        $ShrinkCompleted = $true

        Write-Host "2/5 - Création du volume SIDERON..." -ForegroundColor Cyan

        $CreatedPartition = New-Partition `
            -DiskNumber $Plan.DiskNumber `
            -Size $Plan.RequestedSizeBytes `
            -ErrorAction Stop

        Write-Host "3/5 - Formatage NTFS..." -ForegroundColor Cyan

        Format-Volume `
            -Partition $CreatedPartition `
            -FileSystem "NTFS" `
            -NewFileSystemLabel $Plan.VolumeLabel `
            -Confirm:$false `
            -Force `
            -ErrorAction Stop `
            | Out-Null

        Write-Host "4/5 - Attribution de la lettre $($Plan.TargetDriveLetter):..." -ForegroundColor Cyan

        Set-Partition `
            -DiskNumber $CreatedPartition.DiskNumber `
            -PartitionNumber $CreatedPartition.PartitionNumber `
            -NewDriveLetter $Plan.TargetDriveLetter `
            -ErrorAction Stop

        Write-Host "5/5 - Création de l'arborescence Sideron..." -ForegroundColor Cyan

        $Root = "$($Plan.TargetDriveLetter):\"
        Initialize-SideronStorageLayout -Root $Root

        Close-SideronAutoOpenedExplorer `
            -DriveLetter $Plan.TargetDriveLetter

        Write-Host ""
        Write-Host "VOLUME SIDERON CRÉÉ AVEC SUCCÈS" -ForegroundColor Green
        Write-Host "SIDERON_STORAGE_ROOT=$Root"
    }
    catch
    {
        $OriginalError = $_

        if ($null -ne $CreatedPartition)
        {
            try
            {
                Remove-Partition `
                    -DiskNumber $CreatedPartition.DiskNumber `
                    -PartitionNumber $CreatedPartition.PartitionNumber `
                    -Confirm:$false `
                    -ErrorAction Stop

                $CreatedPartition = $null
            }
            catch
            {
                Write-Host "Impossible de supprimer automatiquement le volume SIDERON partiellement créé." -ForegroundColor Red
                throw $OriginalError
            }
        }

        if ($ShrinkCompleted)
        {
            try
            {
                Resize-Partition `
                    -DiskNumber $Plan.DiskNumber `
                    -PartitionNumber $Plan.PartitionNumber `
                    -Size $Plan.SourceCurrentSizeBytes `
                    -ErrorAction Stop
            }
            catch
            {
                Write-Host "La restauration automatique de la partition source a échoué." -ForegroundColor Red
            }
        }

        throw $OriginalError
    }
}

function New-SideronVolumeFromWholeDisk
{
    param(
        $Plan
    )

    Write-Host "1/6 - Analyse des anciens volumes..." -ForegroundColor Cyan

    $ExistingPartitions = @(
        Get-Partition `
            -DiskNumber $Plan.DiskNumber `
            -ErrorAction SilentlyContinue
    )

    Write-Host "2/6 - Effacement du disque..." -ForegroundColor Cyan

    Clear-Disk `
        -Number $Plan.DiskNumber `
        -RemoveData `
        -RemoveOEM `
        -Confirm:$false `
        -ErrorAction Stop

    Write-Host "3/6 - Initialisation GPT et création du volume..." -ForegroundColor Cyan

    Initialize-Disk `
        -Number $Plan.DiskNumber `
        -PartitionStyle GPT `
        -ErrorAction Stop

    $CreatedPartition = New-Partition `
        -DiskNumber $Plan.DiskNumber `
        -UseMaximumSize `
        -ErrorAction Stop

    Write-Host "4/6 - Formatage NTFS..." -ForegroundColor Cyan

    Format-Volume `
        -Partition $CreatedPartition `
        -FileSystem "NTFS" `
        -NewFileSystemLabel $Plan.VolumeLabel `
        -Confirm:$false `
        -Force `
        -ErrorAction Stop `
        | Out-Null

    Write-Host "5/6 - Attribution de la lettre $($Plan.TargetDriveLetter):..." -ForegroundColor Cyan

    Set-Partition `
        -DiskNumber $CreatedPartition.DiskNumber `
        -PartitionNumber $CreatedPartition.PartitionNumber `
        -NewDriveLetter $Plan.TargetDriveLetter `
        -ErrorAction Stop

    Write-Host "6/6 - Création de l'arborescence Sideron..." -ForegroundColor Cyan

    $Root = "$($Plan.TargetDriveLetter):\"
    Initialize-SideronStorageLayout -Root $Root

    Close-SideronAutoOpenedExplorer `
        -DriveLetter $Plan.TargetDriveLetter

    Write-Host ""
    Write-Host "DISQUE SIDERON PRÉPARÉ AVEC SUCCÈS" -ForegroundColor Green
    Write-Host "SIDERON_STORAGE_ROOT=$Root"
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host " Gestion du stockage Sideron" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

if (-not (Test-Administrator))
{
    throw "Ce script doit être lancé depuis PowerShell en administrateur."
}

if ($Mode -eq "Folder")
{
    Write-Host "Mode                 : dossier local"
    Write-Host "Chemin               : $DefaultFolderRoot"
    Write-Host "Nom de volume dédié  : aucun"
    Write-Host ""

    if (-not $Apply)
    {
        Write-Host "PLAN VALIDE" -ForegroundColor Green
        Write-Host "AUCUNE MODIFICATION DE DISQUE N'A ÉTÉ EFFECTUÉE." -ForegroundColor Yellow
        exit 0
    }

    Initialize-SideronStorageLayout `
        -Root $DefaultFolderRoot

    Write-Host "STOCKAGE SIDERON CRÉÉ AVEC SUCCÈS" -ForegroundColor Green
    Write-Host "SIDERON_STORAGE_ROOT=$DefaultFolderRoot"

    exit 0
}

if ($Mode -eq "Shrink")
{
    $Plan = Get-ShrinkPlan `
        -RequestedDiskNumber $DiskNumber `
        -RequestedPartitionNumber $PartitionNumber `
        -RequestedSizeGB $PartitionSizeGB

    Show-ShrinkPlan -Plan $Plan
    Write-Host ""

    if (-not $Plan.CanCreate)
    {
        Write-Host "PLAN REFUSÉ" -ForegroundColor Red
        Write-Host "La taille demandée dépasse la réduction considérée sûre."
        exit 2
    }

    Write-Host "PLAN VALIDE" -ForegroundColor Green

    if (-not $Apply)
    {
        Write-Host "AUCUNE MODIFICATION DE DISQUE N'A ÉTÉ EFFECTUÉE." -ForegroundColor Yellow
        exit 0
    }

    $Required = "CREER VOLUME SIDERON"

    if ($Confirmation -ne $Required)
    {
        Write-Host ""
        Write-Host "Pour appliquer ce plan, saisis exactement :" -ForegroundColor Yellow
        Write-Host $Required -ForegroundColor Green

        $Confirmation = Read-Host "Confirmation"
    }

    if ($Confirmation -ne $Required)
    {
        Write-Host "Création annulée." -ForegroundColor Yellow
        exit 3
    }

    New-SideronVolumeFromShrink -Plan $Plan
    exit 0
}

if ($Mode -eq "WholeDisk")
{
    $Plan = Get-WholeDiskPlan `
        -RequestedDiskNumber $DiskNumber

    Show-WholeDiskPlan -Plan $Plan
    Write-Host ""
    Write-Host "PLAN VALIDE" -ForegroundColor Green

    if (-not $Apply)
    {
        Write-Host "AUCUNE MODIFICATION DE DISQUE N'A ÉTÉ EFFECTUÉE." -ForegroundColor Yellow
        exit 0
    }

    $Required = "EFFACER DISQUE $DiskNumber"

    if ($Confirmation -ne $Required)
    {
        Write-Host ""
        Write-Host "Pour effacer entièrement ce disque, saisis exactement :" -ForegroundColor Red
        Write-Host $Required -ForegroundColor Green

        $Confirmation = Read-Host "Confirmation"
    }

    if ($Confirmation -ne $Required)
    {
        Write-Host "Opération annulée." -ForegroundColor Yellow
        exit 3
    }

    New-SideronVolumeFromWholeDisk -Plan $Plan
    exit 0
}

throw "Mode de stockage Sideron inconnu."
