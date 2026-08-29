param(
    [string]$StorageRoot = "C:\Atlas",

    [switch]$DisableStartup,

    [switch]$DisableDesktopShortcut,

    [switch]$Update,

    [switch]$Silent,

    [switch]$RestartAtlas,

    [string]$ProgressFile = ""
)

$ErrorActionPreference = "Stop"

$ServiceName = "AtlasV2Service"
$ServiceDisplayName = "Atlas V2 Privileged Service"
$ServiceDescription = "Service privilégié local d'Atlas V2."

$AtlasRoot = Resolve-Path (Join-Path $PSScriptRoot "..")

$PackagedReleaseRoot = Join-Path $PSScriptRoot "Atlas"
$DevelopmentReleaseRoot = Join-Path $AtlasRoot "dist\Atlas"

if (Test-Path (Join-Path $PackagedReleaseRoot "Atlas.exe"))
{
    $ReleaseRoot = $PackagedReleaseRoot
}
elseif (Test-Path (Join-Path $DevelopmentReleaseRoot "Atlas.exe"))
{
    $ReleaseRoot = $DevelopmentReleaseRoot
}
else
{
    throw (
        "Impossible de trouver la distribution Atlas. " +
        "Chemins testés : $PackagedReleaseRoot ; $DevelopmentReleaseRoot"
    )
}

$InstallRoot = Join-Path $env:ProgramFiles "Atlas"

$AtlasExeSource = Join-Path $ReleaseRoot "Atlas.exe"
$CoreExeSource = Join-Path $ReleaseRoot "core\Atlas.Core.exe"
$ServiceExeSource = Join-Path $ReleaseRoot "service\Atlas.Service.exe"
$IntegrityManifestSource = Join-Path $ReleaseRoot "integrity.sha256.json"

$AtlasExeInstalled = Join-Path $InstallRoot "Atlas.exe"
$ServiceExeInstalled = Join-Path $InstallRoot "service\Atlas.Service.exe"

$ProgramDataRoot = Join-Path $env:ProgramData "Atlas"
$ServiceConfigPath = Join-Path $ProgramDataRoot "service_config.json"

$RunKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
$RunValueName = "Atlas"

$InstallerMutexName = "Global\Atlas.Setup.Installation"
$InstallerMutex = $null
$InstallerMutexOwned = $false

$AtlasVersion = "3.3.5-rc.4"
$AtlasPublisher = "Atlas"
$UninstallKey = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Atlas"
$UninstallExeInstalled = Join-Path $InstallRoot "Atlas.Uninstall.exe"

$InstalledConfigPath = Join-Path $InstallRoot "config\atlas.json"
$LocalAppDataRoot = [Environment]::GetFolderPath(
    [Environment+SpecialFolder]::LocalApplicationData
)
$RuntimeConfigPath = Join-Path $LocalAppDataRoot "Atlas\config\atlas.json"
$InstallBackupRoot = Join-Path $env:TEMP "AtlasInstallBackup"
$PreservedConfigPath = Join-Path $InstallBackupRoot "atlas.previous.json"

$RollbackInstallRoot = Join-Path `
    (Split-Path $InstallRoot -Parent) `
    "Atlas.__rollback"

function Test-Administrator
{
    $Identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $Principal = New-Object Security.Principal.WindowsPrincipal($Identity)

    return $Principal.IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator
    )
}

function Wait-ServiceState
{
    param(
        [string]$Name,
        [string]$State,
        [int]$TimeoutSeconds = 60
    )

    $Deadline = (Get-Date).AddSeconds($TimeoutSeconds)

    do
    {
        $Service = Get-Service -Name $Name -ErrorAction SilentlyContinue

        if ($null -ne $Service -and $Service.Status.ToString() -eq $State)
        {
            return $true
        }

        Start-Sleep -Milliseconds 300
    }
    while ((Get-Date) -lt $Deadline)

    return $false
}

function Write-Utf8NoBomFile
{
    param(
        [string]$Path,
        [string]$Content
    )

    $Utf8NoBom = New-Object System.Text.UTF8Encoding($false)

    [System.IO.File]::WriteAllText(
        $Path,
        $Content,
        $Utf8NoBom
    )
}

function Write-UpdateProgress
{
    param(
        [int]$Percent,
        [string]$Message,
        [string]$State = "running"
    )

    if ([string]::IsNullOrWhiteSpace($ProgressFile))
    {
        return
    }

    try
    {
        $ProgressDirectory = Split-Path `
            -Path $ProgressFile `
            -Parent

        if (-not [string]::IsNullOrWhiteSpace($ProgressDirectory))
        {
            New-Item `
                -ItemType Directory `
                -Path $ProgressDirectory `
                -Force `
                | Out-Null
        }

        $Payload = [ordered]@{
            version = 1
            target_version = $AtlasVersion
            percent = [Math]::Max(0, [Math]::Min(100, $Percent))
            state = $State
            message = $Message
            updated_utc = [DateTime]::UtcNow.ToString("o")
        }

        $Json = $Payload | ConvertTo-Json -Depth 5

        Write-Utf8NoBomFile `
            -Path $ProgressFile `
            -Content $Json
    }
    catch
    {
        # Le reporting de progression ne doit jamais casser une mise à jour.
    }
}

function Import-ExistingUpdatePreferences
{
    if (-not $Update)
    {
        return
    }

    $ExistingConfig = $null

    foreach ($Candidate in @(
        $RuntimeConfigPath,
        $InstalledConfigPath
    ))
    {
        if (-not (Test-Path $Candidate))
        {
            continue
        }

        try
        {
            $ExistingConfig = Get-Content `
                -Path $Candidate `
                -Raw `
                -Encoding UTF8 `
                | ConvertFrom-Json

            break
        }
        catch
        {
        }
    }

    if ($null -ne $ExistingConfig)
    {
        $ExistingStorageRoot = [string]$ExistingConfig.storage.root

        # Une mise à jour conserve uniquement un véritable volume dédié ATLAS.
        # Les anciens dossiers locaux ne doivent jamais remplacer le choix
        # actuel de l'installateur, dont la valeur locale est C:\Atlas.
        if ($ExistingStorageRoot -match "^[A-Za-z]:\\$")
        {
            $ExistingDriveLetter = $ExistingStorageRoot.Substring(0, 1)
            $ExistingVolume = Get-Volume `
                -DriveLetter $ExistingDriveLetter `
                -ErrorAction SilentlyContinue

            if ($null -ne $ExistingVolume -and $ExistingVolume.FileSystemLabel -eq "ATLAS")
            {
                $script:StorageRoot = $ExistingStorageRoot
            }
        }
    }

    $PreviousState = Get-PreviousIntegrationState

    $script:DisableStartup =
        [string]::IsNullOrWhiteSpace(
            [string]$PreviousState.StartupCommand
        )

    $script:DisableDesktopShortcut =
        -not [bool]$PreviousState.DesktopShortcutExists
}

function Start-AtlasAfterUpdate
{
    if (-not $RestartAtlas)
    {
        return
    }

    if (-not (Test-Path $AtlasExeInstalled))
    {
        throw "Impossible de redémarrer Atlas : Atlas.exe est introuvable."
    }

    Write-UpdateProgress `
        -Percent 99 `
        -Message "Redémarrage d'Atlas..." `
        -State "restarting"

    $AtlasProcess = Start-Process `
        -FilePath $AtlasExeInstalled `
        -WorkingDirectory $InstallRoot `
        -PassThru

    Start-Sleep `
        -Seconds 2

    if ($AtlasProcess.HasExited)
    {
        throw (
            "Atlas s'est arrêté immédiatement après la mise à jour " +
            "(code $($AtlasProcess.ExitCode))."
        )
    }

    Write-UpdateProgress `
        -Percent 100 `
        -Message "Mise à jour terminée." `
        -State "completed"
}

function Enter-AtlasInstallerLock
{
    try
    {
        $script:InstallerMutex = New-Object System.Threading.Mutex(
            $false,
            $InstallerMutexName
        )

        $script:InstallerMutexOwned = $script:InstallerMutex.WaitOne(
            [TimeSpan]::Zero,
            $false
        )
    }
    catch [System.Threading.AbandonedMutexException]
    {
        $script:InstallerMutexOwned = $true
    }

    if (-not $script:InstallerMutexOwned)
    {
        $LockMessage = "Une autre installation ou mise à jour d'Atlas est déjà en cours. Fermez l'autre installateur puis réessayez."
        throw $LockMessage
    }
}

function Exit-AtlasInstallerLock
{
    if ($null -eq $script:InstallerMutex)
    {
        return
    }

    if ($script:InstallerMutexOwned)
    {
        try
        {
            $script:InstallerMutex.ReleaseMutex()
        }
        catch
        {
        }
    }

    try
    {
        $script:InstallerMutex.Dispose()
    }
    catch
    {
    }

    $script:InstallerMutex = $null
    $script:InstallerMutexOwned = $false
}

function Suspend-AtlasWindowsStartup
{
    Remove-ItemProperty `
        -Path $RunKey `
        -Name $RunValueName `
        -ErrorAction SilentlyContinue
}

function Stop-ExistingAtlasService
{
    param(
        [switch]$KeepRegistration
    )

    # Ne pas dépendre uniquement du nom historique du service. Une ancienne
    # version peut avoir laissé Atlas.Service.exe enregistré sous un autre nom.
    $InstalledServicePath = $ServiceExeInstalled.ToLowerInvariant()
    $ServiceRegistrations = @(
        Get-CimInstance Win32_Service -ErrorAction SilentlyContinue |
            Where-Object {
                $RegisteredPath = [string]$_.PathName

                $_.Name -eq $ServiceName -or
                (
                    -not [string]::IsNullOrWhiteSpace($RegisteredPath) -and
                    $RegisteredPath.ToLowerInvariant().Contains(
                        $InstalledServicePath
                    )
                )
            }
    )

    $Existing = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue

    if ($null -eq $Existing -and $ServiceRegistrations.Count -eq 0)
    {
        return
    }

    foreach ($Registration in $ServiceRegistrations)
    {
        $RegisteredName = [string]$Registration.Name

        Write-Host "Service $RegisteredName existant détecté." -ForegroundColor Yellow

        # Empêche une stratégie de récupération héritée de relancer le binaire
        # pendant la courte fenêtre où le dossier doit être renommé.
        & sc.exe failure $RegisteredName "reset=" 0 "actions=" "" | Out-Null
        & sc.exe stop $RegisteredName | Out-Null

        $StopDeadline = (Get-Date).AddSeconds(20)

        do
        {
            $CurrentRegistration = Get-CimInstance `
                Win32_Service `
                -Filter "Name='$($RegisteredName.Replace("'", "''"))'" `
                -ErrorAction SilentlyContinue

            if (
                $null -eq $CurrentRegistration -or
                $CurrentRegistration.State -eq "Stopped"
            )
            {
                break
            }

            Start-Sleep -Milliseconds 250
        }
        while ((Get-Date) -lt $StopDeadline)

        # Certains services PyInstaller peuvent annoncer STOPPED quelques
        # instants avant la disparition effective de leur processus.
        if (
            $null -ne $CurrentRegistration -and
            [UInt32]$CurrentRegistration.ProcessId -gt 0
        )
        {
            Stop-Process `
                -Id ([int]$CurrentRegistration.ProcessId) `
                -Force `
                -ErrorAction SilentlyContinue
        }
    }

    $Existing = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue

    if ($null -ne $Existing -and $Existing.Status -ne "Stopped")
    {
        Write-Host "Arrêt du service existant..." -ForegroundColor Cyan
        & sc.exe stop $ServiceName | Out-Host

        if (-not (Wait-ServiceState -Name $ServiceName -State "Stopped"))
        {
            throw "Impossible d'arrêter $ServiceName."
        }
    }

    if ($KeepRegistration)
    {
        return
    }

    Write-Host "Suppression de l'enregistrement du service existant..." -ForegroundColor Cyan
    & sc.exe delete $ServiceName | Out-Host

    $Deadline = (Get-Date).AddSeconds(10)

    do
    {
        $Existing = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue

        if ($null -eq $Existing)
        {
            break
        }

        Start-Sleep -Milliseconds 300
    }
    while ((Get-Date) -lt $Deadline)

    if ($null -ne (Get-Service -Name $ServiceName -ErrorAction SilentlyContinue))
    {
        throw "Windows n'a pas encore supprimé $ServiceName."
    }
}

function Stop-AtlasProcesses
{
    function Get-RunningAtlasProcesses
    {
        $KnownNames = @(
            "Atlas",
            "Atlas.Core",
            "Atlas.Service"
        )

        $ProcessIds = @(
            Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
                Where-Object {
                    if ([int]$_.ProcessId -eq $PID)
                    {
                        return $false
                    }

                    $ExecutablePath = [string]$_.ExecutablePath

                    return (
                        $KnownNames -contains (
                            [IO.Path]::GetFileNameWithoutExtension(
                                [string]$_.Name
                            )
                        ) -or
                        (
                            -not [string]::IsNullOrWhiteSpace($ExecutablePath) -and
                            $ExecutablePath.StartsWith(
                                $InstallRoot,
                                [StringComparison]::OrdinalIgnoreCase
                            )
                        )
                    )
                } |
                ForEach-Object { [int]$_.ProcessId }
        )

        return @(
            foreach ($ProcessId in ($ProcessIds | Select-Object -Unique))
            {
                Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
            }
        )
    }

    $Processes = @(Get-RunningAtlasProcesses)

    if ($Processes.Count -eq 0)
    {
        return
    }

    Write-Host "Fermeture de l'instance Atlas existante..." -ForegroundColor Cyan

    foreach ($Process in $Processes)
    {
        try
        {
            if ($Process.MainWindowHandle -ne 0)
            {
                [void]$Process.CloseMainWindow()
            }
        }
        catch
        {
        }
    }

    $GracefulDeadline = (Get-Date).AddSeconds(5)

    do
    {
        Start-Sleep -Milliseconds 250
        $Remaining = @(Get-RunningAtlasProcesses)
    }
    while ($Remaining.Count -gt 0 -and (Get-Date) -lt $GracefulDeadline)

    if ($Remaining.Count -gt 0)
    {
        Write-Host "Arrêt forcé des composants Atlas restants..." -ForegroundColor Yellow
    }

    foreach ($Process in $Remaining)
    {
        # /T ferme aussi les éventuels processus enfants qui conserveraient
        # un runtime ou un fichier du dossier d'installation ouvert.
        & taskkill.exe /PID $Process.Id /T /F 2>$null | Out-Null

        Stop-Process `
            -Id $Process.Id `
            -Force `
            -ErrorAction SilentlyContinue
    }

    $ForcedDeadline = (Get-Date).AddSeconds(10)

    do
    {
        Start-Sleep -Milliseconds 250
        $Remaining = @(Get-RunningAtlasProcesses)
    }
    while ($Remaining.Count -gt 0 -and (Get-Date) -lt $ForcedDeadline)

    if ($Remaining.Count -gt 0)
    {
        $RemainingNames = (
            $Remaining |
                ForEach-Object { "$($_.ProcessName) (PID $($_.Id))" }
        ) -join ", "

        throw (
            "Impossible de fermer complètement les composants Atlas avant " +
            "l'installation : $RemainingNames."
        )
    }

    Write-Host "Tous les processus Atlas sont arrêtés." -ForegroundColor Green
}

function ConvertTo-AtlasVersion
{
    param(
        [string]$Value
    )

    if ([string]::IsNullOrWhiteSpace($Value))
    {
        return $null
    }

    $Match = [regex]::Match(
        $Value,
        '^(?<major>\d+)\.(?<minor>\d+)\.(?<patch>\d+)'
    )

    if (-not $Match.Success)
    {
        return $null
    }

    return New-Object System.Version(
        [int]$Match.Groups['major'].Value,
        [int]$Match.Groups['minor'].Value,
        [int]$Match.Groups['patch'].Value
    )
}

function Get-InstalledAtlasVersion
{
    try
    {
        $Item = Get-ItemProperty `
            -Path $UninstallKey `
            -Name "DisplayVersion" `
            -ErrorAction Stop

        return [string]$Item.DisplayVersion
    }
    catch
    {
        if (Test-Path $InstalledConfigPath)
        {
            try
            {
                $Config = Get-Content `
                    -Path $InstalledConfigPath `
                    -Raw `
                    -Encoding UTF8 `
                    | ConvertFrom-Json

                return [string]$Config.atlas.version
            }
            catch
            {
            }
        }
    }

    return $null
}

function Get-InstallationMode
{
    $InstalledVersionText = Get-InstalledAtlasVersion

    if ([string]::IsNullOrWhiteSpace($InstalledVersionText))
    {
        if (Test-Path $InstallRoot)
        {
            return [PSCustomObject]@{
                Mode = "Repair"
                InstalledVersion = "inconnue"
            }
        }

        return [PSCustomObject]@{
            Mode = "Fresh"
            InstalledVersion = $null
        }
    }

    $InstalledVersion = ConvertTo-AtlasVersion -Value $InstalledVersionText
    $TargetVersion = ConvertTo-AtlasVersion -Value $AtlasVersion

    if ($null -ne $InstalledVersion -and $null -ne $TargetVersion)
    {
        if ($InstalledVersion -gt $TargetVersion)
        {
            throw (
                "Une version plus récente d'Atlas est déjà installée : " +
                "$InstalledVersionText. Installation de $AtlasVersion refusée."
            )
        }

        if ($InstalledVersion -lt $TargetVersion)
        {
            return [PSCustomObject]@{
                Mode = "Update"
                InstalledVersion = $InstalledVersionText
            }
        }
    }

    return [PSCustomObject]@{
        Mode = "Repair"
        InstalledVersion = $InstalledVersionText
    }
}

function Preserve-ExistingConfiguration
{
    if (-not (Test-Path $InstalledConfigPath))
    {
        return
    }

    if (Test-Path $InstallBackupRoot)
    {
        Remove-Item `
            -Path $InstallBackupRoot `
            -Recurse `
            -Force `
            -ErrorAction SilentlyContinue
    }

    New-Item `
        -ItemType Directory `
        -Path $InstallBackupRoot `
        -Force `
        | Out-Null

    Copy-Item `
        -Path $InstalledConfigPath `
        -Destination $PreservedConfigPath `
        -Force
}

function Merge-AtlasConfiguration
{
    param(
        $Target,
        $Source
    )

    foreach ($Property in $Source.PSObject.Properties)
    {
        $TargetProperty = $Target.PSObject.Properties[$Property.Name]

        if ($null -eq $TargetProperty)
        {
            $Target | Add-Member `
                -NotePropertyName $Property.Name `
                -NotePropertyValue $Property.Value

            continue
        }

        $SourceValue = $Property.Value
        $TargetValue = $TargetProperty.Value

        $SourceIsObject = $null -ne $SourceValue -and $SourceValue -is [PSCustomObject]
        $TargetIsObject = $null -ne $TargetValue -and $TargetValue -is [PSCustomObject]

        if ($SourceIsObject -and $TargetIsObject)
        {
            Merge-AtlasConfiguration `
                -Target $TargetValue `
                -Source $SourceValue
        }
        else
        {
            $TargetProperty.Value = $SourceValue
        }
    }
}

function Restore-PreservedConfiguration
{
    $NewConfigPath = Join-Path $InstallRoot "config\atlas.json"

    if (-not (Test-Path $NewConfigPath))
    {
        throw "Configuration Atlas de la nouvelle version introuvable : $NewConfigPath"
    }

    if (Test-Path $PreservedConfigPath)
    {
        try
        {
            $NewConfig = Get-Content `
                -Path $NewConfigPath `
                -Raw `
                -Encoding UTF8 `
                | ConvertFrom-Json

            $OldConfig = Get-Content `
                -Path $PreservedConfigPath `
                -Raw `
                -Encoding UTF8 `
                | ConvertFrom-Json

            Merge-AtlasConfiguration `
                -Target $NewConfig `
                -Source $OldConfig

            $NewConfig.atlas.version = $AtlasVersion
            $NewConfig.storage.root = $StorageRoot
            $NewConfig.ui.start_with_windows = (-not $DisableStartup)

            $ConfigJson = $NewConfig | ConvertTo-Json -Depth 30

            Write-Utf8NoBomFile `
                -Path $NewConfigPath `
                -Content $ConfigJson
        }
        catch
        {
            throw "Impossible de restaurer la configuration Atlas existante : $($_.Exception.Message)"
        }
    }

    if (Test-Path $InstallBackupRoot)
    {
        Remove-Item `
            -Path $InstallBackupRoot `
            -Recurse `
            -Force `
            -ErrorAction SilentlyContinue
    }
}

function Get-PreviousIntegrationState
{
    $StartupCommand = $null

    try
    {
        $StartupCommand = Get-ItemPropertyValue `
            -Path $RunKey `
            -Name $RunValueName `
            -ErrorAction Stop
    }
    catch
    {
    }

    $DesktopPath = [Environment]::GetFolderPath(
        [Environment+SpecialFolder]::DesktopDirectory
    )

    $ProgramsPath = [Environment]::GetFolderPath(
        [Environment+SpecialFolder]::CommonPrograms
    )

    return [PSCustomObject]@{
        StartupCommand = $StartupCommand
        DesktopShortcutExists = Test-Path (
            Join-Path $DesktopPath "Atlas.lnk"
        )
        StartMenuShortcutExists = Test-Path (
            Join-Path $ProgramsPath "Atlas.lnk"
        )
        InstalledVersion = Get-InstalledAtlasVersion
    }
}

function Prepare-InstallationRollback
{
    param(
        [string]$Mode
    )

    if (Test-Path $RollbackInstallRoot)
    {
        Remove-Item `
            -Path $RollbackInstallRoot `
            -Recurse `
            -Force `
            -ErrorAction Stop
    }

    if ($Mode -eq "Fresh")
    {
        return
    }

    if (-not (Test-Path $InstallRoot))
    {
        return
    }

    Write-Host "Sauvegarde temporaire de l'installation actuelle..." -ForegroundColor Cyan

    $RollbackDirectoryName = Split-Path `
        -Path $RollbackInstallRoot `
        -Leaf

    $MoveDeadline = (Get-Date).AddSeconds(30)
    $LastMoveError = $null

    do
    {
        try
        {
            # InstallRoot et RollbackInstallRoot sont sur le même volume.
            # Rename-Item effectue donc un basculement atomique : l'ancien
            # dossier reste entier si Windows refuse encore le renommage.
            Rename-Item `
                -Path $InstallRoot `
                -NewName $RollbackDirectoryName `
                -ErrorAction Stop

            return
        }
        catch [System.IO.IOException]
        {
            $LastMoveError = $_.Exception.Message

            if ((Get-Date) -ge $MoveDeadline)
            {
                throw
            }

            Start-Sleep -Milliseconds 500
        }
        catch [System.UnauthorizedAccessException]
        {
            $LastMoveError = $_.Exception.Message

            if ((Get-Date) -ge $MoveDeadline)
            {
                throw
            }

            Start-Sleep -Milliseconds 500
        }
    }
    while ((Get-Date) -lt $MoveDeadline)

    $BlockingProcesses = @(
        Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
            Where-Object {
                -not [string]::IsNullOrWhiteSpace([string]$_.ExecutablePath) -and
                ([string]$_.ExecutablePath).StartsWith(
                    $InstallRoot,
                    [StringComparison]::OrdinalIgnoreCase
                )
            } |
            ForEach-Object {
                "$($_.Name) (PID $($_.ProcessId))"
            }
    )

    $BlockingSummary = if ($BlockingProcesses.Count -gt 0) {
        " Processus Atlas encore actifs : $($BlockingProcesses -join ', ')."
    }
    else {
        " Aucun processus exécuté depuis le dossier Atlas n'a été détecté."
    }

    throw (
        "Impossible de libérer l'installation Atlas actuelle. " +
        "Erreur Windows : $LastMoveError" +
        $BlockingSummary
    )
}

function Restore-OrphanedRollbackBeforeInstallation
{
    if (-not (Test-Path $RollbackInstallRoot))
    {
        return
    }

    Write-Host "Une mise à jour Atlas interrompue a été détectée." -ForegroundColor Yellow
    Write-UpdateProgress `
        -Percent 3 `
        -Message "Récupération de l’installation Atlas précédente..." `
        -State "rolling_back"

    Stop-ExistingAtlasService -KeepRegistration
    Stop-AtlasProcesses

    if (Test-Path $InstallRoot)
    {
        Remove-Item `
            -Path $InstallRoot `
            -Recurse `
            -Force `
            -ErrorAction Stop
    }

    Rename-Item `
        -Path $RollbackInstallRoot `
        -NewName (Split-Path -Path $InstallRoot -Leaf) `
        -ErrorAction Stop

    if (-not (Test-Path $AtlasExeInstalled))
    {
        throw (
            "La sauvegarde Atlas récupérée est incomplète : " +
            "$AtlasExeInstalled est introuvable."
        )
    }

    Write-Host "Installation Atlas précédente récupérée." -ForegroundColor Green
}

function Restore-PreviousShortcutState
{
    param(
        $State
    )

    if ($null -ne $State.StartupCommand)
    {
        New-Item `
            -Path $RunKey `
            -Force `
            | Out-Null

        New-ItemProperty `
            -Path $RunKey `
            -Name $RunValueName `
            -PropertyType String `
            -Value ([string]$State.StartupCommand) `
            -Force `
            | Out-Null
    }
    else
    {
        Remove-ItemProperty `
            -Path $RunKey `
            -Name $RunValueName `
            -ErrorAction SilentlyContinue
    }

    $DesktopPath = [Environment]::GetFolderPath(
        [Environment+SpecialFolder]::DesktopDirectory
    )
    $DesktopShortcut = Join-Path $DesktopPath "Atlas.lnk"

    if ($State.DesktopShortcutExists)
    {
        $Shell = New-Object -ComObject WScript.Shell
        $Shortcut = $Shell.CreateShortcut($DesktopShortcut)
        $Shortcut.TargetPath = $AtlasExeInstalled
        $Shortcut.WorkingDirectory = $InstallRoot
        $Shortcut.IconLocation = "$AtlasExeInstalled,0"
        $Shortcut.Description = "Atlas"
        $Shortcut.Save()
    }
    else
    {
        Remove-Item `
            -Path $DesktopShortcut `
            -Force `
            -ErrorAction SilentlyContinue
    }

    $ProgramsPath = [Environment]::GetFolderPath(
        [Environment+SpecialFolder]::CommonPrograms
    )
    $StartMenuShortcut = Join-Path $ProgramsPath "Atlas.lnk"

    if ($State.StartMenuShortcutExists)
    {
        $Shell = New-Object -ComObject WScript.Shell
        $Shortcut = $Shell.CreateShortcut($StartMenuShortcut)
        $Shortcut.TargetPath = $AtlasExeInstalled
        $Shortcut.WorkingDirectory = $InstallRoot
        $Shortcut.IconLocation = "$AtlasExeInstalled,0"
        $Shortcut.Description = "Atlas - Assistant personnel"
        $Shortcut.Save()
    }
    else
    {
        Remove-Item `
            -Path $StartMenuShortcut `
            -Force `
            -ErrorAction SilentlyContinue
    }
}

function Restore-PreviousInstalledApplication
{
    param(
        [string]$Version
    )

    if ([string]::IsNullOrWhiteSpace($Version))
    {
        return
    }

    Register-AtlasInstalledApplication `
        -Version $Version
}

function Remove-AtlasIntegrationArtifacts
{
    Stop-ExistingAtlasService

    Remove-ItemProperty `
        -Path $RunKey `
        -Name $RunValueName `
        -ErrorAction SilentlyContinue

    $DesktopPath = [Environment]::GetFolderPath(
        [Environment+SpecialFolder]::DesktopDirectory
    )

    if (-not [string]::IsNullOrWhiteSpace($DesktopPath))
    {
        Remove-Item `
            -Path (Join-Path $DesktopPath "Atlas.lnk") `
            -Force `
            -ErrorAction SilentlyContinue
    }

    $ProgramsPath = [Environment]::GetFolderPath(
        [Environment+SpecialFolder]::CommonPrograms
    )

    if (-not [string]::IsNullOrWhiteSpace($ProgramsPath))
    {
        Remove-Item `
            -Path (Join-Path $ProgramsPath "Atlas.lnk") `
            -Force `
            -ErrorAction SilentlyContinue
    }

    Remove-Item `
        -Path $UninstallKey `
        -Recurse `
        -Force `
        -ErrorAction SilentlyContinue
}

function Cleanup-FailedFreshInstallation
{
    Write-Host ""
    Write-Host "Nettoyage de l'installation Atlas incomplète..." -ForegroundColor Yellow

    Remove-AtlasIntegrationArtifacts

    if (Test-Path $InstallRoot)
    {
        Remove-Item `
            -Path $InstallRoot `
            -Recurse `
            -Force `
            -ErrorAction SilentlyContinue
    }

    if (Test-Path $RollbackInstallRoot)
    {
        Remove-Item `
            -Path $RollbackInstallRoot `
            -Recurse `
            -Force `
            -ErrorAction SilentlyContinue
    }

    if (Test-Path $InstallBackupRoot)
    {
        Remove-Item `
            -Path $InstallBackupRoot `
            -Recurse `
            -Force `
            -ErrorAction SilentlyContinue
    }

    Write-Host "Nettoyage terminé." -ForegroundColor DarkGray
}

function Restore-PreviousInstallation
{
    param(
        $IntegrationState
    )

    Write-Host ""
    Write-Host "Restauration de l'installation précédente..." -ForegroundColor Yellow

    Stop-ExistingAtlasService

    if (Test-Path $InstallRoot)
    {
        Remove-Item `
            -Path $InstallRoot `
            -Recurse `
            -Force `
            -ErrorAction SilentlyContinue
    }

    if (-not (Test-Path $RollbackInstallRoot))
    {
        throw "La sauvegarde de restauration Atlas est introuvable."
    }

    Rename-Item `
        -Path $RollbackInstallRoot `
        -NewName (Split-Path -Path $InstallRoot -Leaf) `
        -ErrorAction Stop

    Write-ServiceConfiguration
    Install-AtlasService

    Restore-PreviousShortcutState `
        -State $IntegrationState

    Restore-PreviousInstalledApplication `
        -Version $IntegrationState.InstalledVersion

    if (Test-Path $InstallBackupRoot)
    {
        Remove-Item `
            -Path $InstallBackupRoot `
            -Recurse `
            -Force `
            -ErrorAction SilentlyContinue
    }

    Write-Host "Ancienne installation Atlas restaurée." -ForegroundColor Green
}

function Repair-PreviousInstallationWithoutRollback
{
    param(
        $IntegrationState
    )

    Write-Host ""
    Write-Host "Réactivation de l'installation Atlas existante..." -ForegroundColor Yellow

    if (-not (Test-Path $InstallRoot))
    {
        throw "L'installation Atlas existante est introuvable."
    }

    Stop-ExistingAtlasService
    Write-ServiceConfiguration
    Install-AtlasService

    Restore-PreviousShortcutState `
        -State $IntegrationState

    Restore-PreviousInstalledApplication `
        -Version $IntegrationState.InstalledVersion

    Write-Host "Installation Atlas existante réactivée." -ForegroundColor Green
}

function Test-InstalledAtlasHealth
{
    Write-Host "Validation de l'installation Atlas..." -ForegroundColor Cyan

    $RequiredFiles = @(
        $AtlasExeInstalled,
        (Join-Path $InstallRoot "core\Atlas.Core.exe"),
        (Join-Path $InstallRoot "service\Atlas.Service.exe"),
        (Join-Path $InstallRoot "config\atlas.json"),
        $UninstallExeInstalled
    )

    foreach ($RequiredFile in $RequiredFiles)
    {
        if (-not (Test-Path $RequiredFile))
        {
            throw "Validation Atlas échouée : fichier manquant $RequiredFile"
        }
    }

    try
    {
        $InstalledConfig = Get-Content `
            -Path (Join-Path $InstallRoot "config\atlas.json") `
            -Raw `
            -Encoding UTF8 `
            | ConvertFrom-Json
    }
    catch
    {
        throw "Validation Atlas échouée : configuration atlas.json illisible."
    }

    if ([string]$InstalledConfig.atlas.version -ne $AtlasVersion)
    {
        throw (
            "Validation Atlas échouée : version installée inattendue. " +
            "Attendue : $AtlasVersion ; détectée : $($InstalledConfig.atlas.version)"
        )
    }

    if ([string]$InstalledConfig.storage.root -ne $StorageRoot)
    {
        throw (
            "Validation Atlas échouée : racine de stockage inattendue. " +
            "Attendue : $StorageRoot ; détectée : $($InstalledConfig.storage.root)"
        )
    }

    $Service = Get-Service `
        -Name $ServiceName `
        -ErrorAction SilentlyContinue

    if ($null -eq $Service)
    {
        throw "Validation Atlas échouée : service $ServiceName introuvable."
    }

    if ($Service.Status -ne "Running")
    {
        try
        {
            Start-Service `
                -Name $ServiceName `
                -ErrorAction Stop

            $Service.WaitForStatus(
                [System.ServiceProcess.ServiceControllerStatus]::Running,
                [TimeSpan]::FromSeconds(15)
            )
        }
        catch
        {
            throw "Validation Atlas échouée : service $ServiceName non démarré."
        }
    }

    $Service = Get-Service `
        -Name $ServiceName `
        -ErrorAction Stop

    if ($Service.Status -ne "Running")
    {
        throw "Validation Atlas échouée : service $ServiceName non opérationnel."
    }

    if (-not (Test-Path $UninstallKey))
    {
        throw "Validation Atlas échouée : entrée Applications installées absente."
    }

    try
    {
        $RegisteredVersion = [string](
            Get-ItemPropertyValue `
                -Path $UninstallKey `
                -Name "DisplayVersion" `
                -ErrorAction Stop
        )
    }
    catch
    {
        throw "Validation Atlas échouée : version Applications installées illisible."
    }

    if ($RegisteredVersion -ne $AtlasVersion)
    {
        throw (
            "Validation Atlas échouée : version Windows inattendue. " +
            "Attendue : $AtlasVersion ; détectée : $RegisteredVersion"
        )
    }

    $ProgramsPath = [Environment]::GetFolderPath(
        [Environment+SpecialFolder]::CommonPrograms
    )

    $StartMenuShortcutPath = Join-Path $ProgramsPath "Atlas.lnk"

    if (-not (Test-Path $StartMenuShortcutPath))
    {
        throw "Validation Atlas échouée : raccourci du menu Démarrer absent."
    }

    if (-not $DisableDesktopShortcut)
    {
        $DesktopPath = [Environment]::GetFolderPath(
            [Environment+SpecialFolder]::DesktopDirectory
        )

        $DesktopShortcutPath = Join-Path $DesktopPath "Atlas.lnk"

        if (-not (Test-Path $DesktopShortcutPath))
        {
            throw "Validation Atlas échouée : raccourci Bureau demandé mais absent."
        }
    }

    if ($DisableStartup)
    {
        try
        {
            $StartupValue = Get-ItemPropertyValue `
                -Path $RunKey `
                -Name $RunValueName `
                -ErrorAction Stop

            if (-not [string]::IsNullOrWhiteSpace([string]$StartupValue))
            {
                throw "Validation Atlas échouée : démarrage Windows encore actif."
            }
        }
        catch [System.Management.Automation.ItemNotFoundException]
        {
        }
        catch [System.Management.Automation.PSArgumentException]
        {
        }
    }
    else
    {
        try
        {
            $StartupValue = [string](
                Get-ItemPropertyValue `
                    -Path $RunKey `
                    -Name $RunValueName `
                    -ErrorAction Stop
            )
        }
        catch
        {
            throw "Validation Atlas échouée : démarrage Windows demandé mais absent."
        }

        if ([string]::IsNullOrWhiteSpace($StartupValue))
        {
            throw "Validation Atlas échouée : commande de démarrage Windows vide."
        }
    }

    Write-Host "Validation Atlas réussie." -ForegroundColor Green
}

function Complete-InstallationRollback
{
    if (Test-Path $RollbackInstallRoot)
    {
        Remove-Item `
            -Path $RollbackInstallRoot `
            -Recurse `
            -Force `
            -ErrorAction SilentlyContinue
    }
}


function Read-AtlasIntegrityManifest
{
    param(
        [string]$ManifestPath
    )

    if (-not (Test-Path $ManifestPath))
    {
        throw "Manifeste d'intégrité Atlas introuvable : $ManifestPath"
    }

    try
    {
        $Manifest = Get-Content `
            -Path $ManifestPath `
            -Raw `
            -Encoding UTF8 `
            -ErrorAction Stop `
            | ConvertFrom-Json
    }
    catch
    {
        throw "Manifeste d'intégrité Atlas illisible : $ManifestPath"
    }

    if ([string]$Manifest.algorithm -ne "SHA256")
    {
        throw "Algorithme du manifeste Atlas non pris en charge."
    }

    if ($null -eq $Manifest.files -or $Manifest.files.Count -eq 0)
    {
        throw "Le manifeste d'intégrité Atlas ne contient aucun fichier."
    }

    return $Manifest
}

function Test-AtlasPayloadIntegrity
{
    param(
        [string]$RootPath,
        [string]$ManifestPath,
        [string]$Context
    )

    Write-Host "Vérification SHA-256 : $Context..." -ForegroundColor Cyan

    $Manifest = Read-AtlasIntegrityManifest `
        -ManifestPath $ManifestPath

    $ResolvedRoot = [System.IO.Path]::GetFullPath(
        $RootPath
    ).TrimEnd(
        [System.IO.Path]::DirectorySeparatorChar
    )

    $RequiredPrefix = $ResolvedRoot + [System.IO.Path]::DirectorySeparatorChar

    foreach ($Entry in $Manifest.files)
    {
        $RelativePath = [string]$Entry.path

        if ([string]::IsNullOrWhiteSpace($RelativePath))
        {
            throw "Entrée vide dans le manifeste d'intégrité Atlas."
        }

        $NormalizedRelativePath = $RelativePath.Replace(
            "/",
            [System.IO.Path]::DirectorySeparatorChar
        )

        $CandidatePath = Join-Path `
            $RootPath `
            $NormalizedRelativePath

        $ResolvedCandidate = [System.IO.Path]::GetFullPath(
            $CandidatePath
        )

        if (-not $ResolvedCandidate.StartsWith(
            $RequiredPrefix,
            [System.StringComparison]::OrdinalIgnoreCase
        ))
        {
            throw "Chemin interdit dans le manifeste Atlas : $RelativePath"
        }

        if (-not (Test-Path $ResolvedCandidate -PathType Leaf))
        {
            throw "Intégrité Atlas échouée : fichier absent $RelativePath"
        }

        $File = Get-Item `
            -Path $ResolvedCandidate `
            -ErrorAction Stop

        if ([UInt64]$File.Length -ne [UInt64]$Entry.size)
        {
            throw "Intégrité Atlas échouée : taille incorrecte pour $RelativePath"
        }

        $ActualHash = Get-FileHash `
            -Path $ResolvedCandidate `
            -Algorithm SHA256 `
            -ErrorAction Stop

        $ExpectedHash = ([string]$Entry.sha256).ToLowerInvariant()
        $ComputedHash = ([string]$ActualHash.Hash).ToLowerInvariant()

        if ($ComputedHash -ne $ExpectedHash)
        {
            throw "Intégrité Atlas échouée : SHA-256 incorrect pour $RelativePath"
        }
    }

    Write-Host "Intégrité SHA-256 validée : $Context." -ForegroundColor Green
}

function Test-ReleasePayloadIntegrity
{
    Test-AtlasPayloadIntegrity `
        -RootPath $ReleaseRoot `
        -ManifestPath $IntegrityManifestSource `
        -Context "payload du Setup"
}

function Test-InstalledPayloadIntegrity
{
    $InstalledManifestPath = Join-Path `
        $InstallRoot `
        "integrity.sha256.json"

    Test-AtlasPayloadIntegrity `
        -RootPath $InstallRoot `
        -ManifestPath $InstalledManifestPath `
        -Context "installation copiée"
}


function Test-ReleasePayload
{
    foreach ($Path in @(
        $AtlasExeSource,
        $CoreExeSource,
        $ServiceExeSource,
        $IntegrityManifestSource
    ))
    {
        if (-not (Test-Path $Path))
        {
            throw "Fichier de release manquant : $Path"
        }
    }

    Write-Host "Auto-test Atlas.Service.exe..." -ForegroundColor Cyan

    $SelfTest = Start-Process `
        -FilePath $ServiceExeSource `
        -ArgumentList "--self-test" `
        -Wait `
        -PassThru

    if ($SelfTest.ExitCode -ne 0)
    {
        throw "Atlas.Service.exe a échoué à l'auto-test (code $($SelfTest.ExitCode))."
    }
}

function Prepare-StorageRoot
{
    $ResolvedStorageRoot = $StorageRoot.Trim()

    if ([string]::IsNullOrWhiteSpace($ResolvedStorageRoot))
    {
        throw "La zone de stockage Atlas ne peut pas être vide."
    }

    if ($ResolvedStorageRoot -eq "C:\Atlas")
    {
        New-Item `
            -ItemType Directory `
            -Path $ResolvedStorageRoot `
            -Force `
            | Out-Null
    }
    elseif ($ResolvedStorageRoot -match "^[A-Za-z]:\\$")
    {
        if (-not (Test-Path $ResolvedStorageRoot))
        {
            throw "Le volume Atlas sélectionné n'existe pas : $ResolvedStorageRoot"
        }

        $DriveLetter = $ResolvedStorageRoot.Substring(0, 1)
        $Volume = Get-Volume `
            -DriveLetter $DriveLetter `
            -ErrorAction Stop

        if ($Volume.FileSystemLabel -ne "ATLAS")
        {
            throw "Le volume dédié sélectionné doit porter le label ATLAS."
        }
    }
    else
    {
        throw "Zone de stockage invalide. Utilise C:\Atlas ou la racine d'un volume dédié ATLAS."
    }

    foreach ($Folder in @(
        "Backups",
        "Cache",
        "Documents",
        "Exports",
        "Imports",
        "Memory",
        "Projects",
        "System",
        "Temp"
    ))
    {
        New-Item `
            -ItemType Directory `
            -Path (Join-Path $ResolvedStorageRoot $Folder) `
            -Force `
            | Out-Null
    }

    $script:StorageRoot = $ResolvedStorageRoot
}


function Update-InstalledAtlasConfig
{
    $ConfigPath = Join-Path $InstallRoot "config\atlas.json"

    if (-not (Test-Path $ConfigPath))
    {
        throw "Configuration Atlas introuvable après copie : $ConfigPath"
    }

    $Config = Get-Content `
        -Path $ConfigPath `
        -Raw `
        -Encoding UTF8 `
        | ConvertFrom-Json

    $Config.atlas.version = $AtlasVersion
    $Config.storage.root = $StorageRoot
    $Config.ui.start_with_windows = (-not $DisableStartup)

    $ConfigJson = $Config | ConvertTo-Json -Depth 30

    Write-Utf8NoBomFile `
        -Path $ConfigPath `
        -Content $ConfigJson
}

function Sync-RuntimeConfiguration
{
    $TemplateConfigPath = Join-Path $InstallRoot "config\atlas.json"

    if (-not (Test-Path $TemplateConfigPath))
    {
        throw "Modèle de configuration Atlas introuvable : $TemplateConfigPath"
    }

    $TemplateConfig = Get-Content `
        -Path $TemplateConfigPath `
        -Raw `
        -Encoding UTF8 `
        | ConvertFrom-Json

    if (Test-Path $RuntimeConfigPath)
    {
        try
        {
            $ExistingRuntimeConfig = Get-Content `
                -Path $RuntimeConfigPath `
                -Raw `
                -Encoding UTF8 `
                | ConvertFrom-Json

            Merge-AtlasConfiguration `
                -Target $TemplateConfig `
                -Source $ExistingRuntimeConfig
        }
        catch
        {
            throw "Configuration runtime Atlas existante illisible : $RuntimeConfigPath"
        }
    }

    $TemplateConfig.atlas.version = $AtlasVersion
    $TemplateConfig.storage.root = $StorageRoot
    $TemplateConfig.ui.start_with_windows = (-not $DisableStartup)

    $RuntimeConfigDirectory = Split-Path `
        $RuntimeConfigPath `
        -Parent

    New-Item `
        -ItemType Directory `
        -Path $RuntimeConfigDirectory `
        -Force `
        | Out-Null

    $RuntimeTemporaryPath = "$RuntimeConfigPath.tmp"
    $RuntimeJson = $TemplateConfig | ConvertTo-Json -Depth 30

    Write-Utf8NoBomFile `
        -Path $RuntimeTemporaryPath `
        -Content $RuntimeJson

    Move-Item `
        -Path $RuntimeTemporaryPath `
        -Destination $RuntimeConfigPath `
        -Force

    Write-Host "Configuration runtime : $RuntimeConfigPath" -ForegroundColor DarkGray
}


function Write-ServiceConfiguration
{
    New-Item `
        -ItemType Directory `
        -Path $ProgramDataRoot `
        -Force `
        | Out-Null

    $CurrentSid = (
        [Security.Principal.WindowsIdentity]::GetCurrent()
    ).User.Value

    if ([string]::IsNullOrWhiteSpace($CurrentSid))
    {
        throw "Impossible de déterminer le SID de l'utilisateur Atlas."
    }

    $Payload = [ordered]@{
        version = 1
        allowed_user_sid = $CurrentSid
    }

    $ServiceConfigJson = $Payload | ConvertTo-Json -Depth 5

    Write-Utf8NoBomFile `
        -Path $ServiceConfigPath `
        -Content $ServiceConfigJson

    Write-Host "SID utilisateur Atlas : $CurrentSid" -ForegroundColor DarkGray

    & icacls.exe `
        $ProgramDataRoot `
        "/inheritance:r" `
        "/grant:r" `
        "*S-1-5-18:(OI)(CI)F" `
        "*S-1-5-32-544:(OI)(CI)F" `
        "*${CurrentSid}:(OI)(CI)RX" `
        | Out-Host

    if ($LASTEXITCODE -ne 0)
    {
        throw "Impossible de sécuriser $ProgramDataRoot."
    }

    & icacls.exe `
        $ServiceConfigPath `
        "/inheritance:r" `
        "/grant:r" `
        "*S-1-5-18:F" `
        "*S-1-5-32-544:F" `
        "*${CurrentSid}:R" `
        | Out-Host

    if ($LASTEXITCODE -ne 0)
    {
        throw "Impossible de sécuriser service_config.json."
    }
}

function Install-AtlasService
{
    if (-not (Test-Path $ServiceExeInstalled))
    {
        throw "Atlas.Service.exe installé introuvable : $ServiceExeInstalled"
    }

    Write-Host "Création de $ServiceName..." -ForegroundColor Cyan

    $BinaryPath = "`"$ServiceExeInstalled`""

    & sc.exe create `
        $ServiceName `
        "binPath=" `
        $BinaryPath `
        "start=" `
        "auto" `
        "obj=" `
        "LocalSystem" `
        "DisplayName=" `
        $ServiceDisplayName `
        | Out-Host

    if ($LASTEXITCODE -ne 0)
    {
        throw "Impossible de créer $ServiceName."
    }

    & sc.exe description `
        $ServiceName `
        $ServiceDescription `
        | Out-Host

    if ($LASTEXITCODE -ne 0)
    {
        throw "Impossible de définir la description du service."
    }

    & sc.exe failure `
        $ServiceName `
        "reset=" `
        "86400" `
        "actions=" `
        "restart/5000" `
        | Out-Host

    if ($LASTEXITCODE -ne 0)
    {
        throw "Impossible de configurer la récupération du service."
    }

    & sc.exe start $ServiceName | Out-Host

    Write-Host "Attente du passage de $ServiceName en RUNNING..." -ForegroundColor Cyan

    if (
        -not (
            Wait-ServiceState `
                -Name $ServiceName `
                -State "Running" `
                -TimeoutSeconds 60
        )
    )
    {
        Write-Host "Source de la distribution : $ReleaseRoot" -ForegroundColor DarkGray
Write-Host ""
        Write-Host "État final retourné par Windows :" -ForegroundColor Yellow
        & sc.exe query $ServiceName | Out-Host

        throw "$ServiceName n'a pas atteint l'état RUNNING dans les 60 secondes."
    }

    Write-Host "$ServiceName est RUNNING." -ForegroundColor Green
}

function Configure-StartMenuShortcut
{
    $ProgramsPath = [Environment]::GetFolderPath(
        [Environment+SpecialFolder]::CommonPrograms
    )

    if ([string]::IsNullOrWhiteSpace($ProgramsPath))
    {
        throw "Impossible de déterminer le dossier Programmes du menu Démarrer."
    }

    $ShortcutPath = Join-Path $ProgramsPath "Atlas.lnk"

    $Shell = New-Object -ComObject WScript.Shell
    $Shortcut = $Shell.CreateShortcut($ShortcutPath)

    $Shortcut.TargetPath = $AtlasExeInstalled
    $Shortcut.WorkingDirectory = $InstallRoot
    $Shortcut.IconLocation = "$AtlasExeInstalled,0"
    $Shortcut.Description = "Atlas - Assistant personnel"
    $Shortcut.Save()
}

function Configure-DesktopShortcut
{
    $DesktopPath = [Environment]::GetFolderPath(
        [Environment+SpecialFolder]::DesktopDirectory
    )

    if ([string]::IsNullOrWhiteSpace($DesktopPath))
    {
        throw "Impossible de déterminer le dossier Bureau de l'utilisateur."
    }

    $ShortcutPath = Join-Path $DesktopPath "Atlas.lnk"

    if ($DisableDesktopShortcut)
    {
        Remove-Item `
            -Path $ShortcutPath `
            -Force `
            -ErrorAction SilentlyContinue

        return
    }

    $Shell = New-Object -ComObject WScript.Shell
    $Shortcut = $Shell.CreateShortcut($ShortcutPath)

    $Shortcut.TargetPath = $AtlasExeInstalled
    $Shortcut.WorkingDirectory = $InstallRoot
    $Shortcut.IconLocation = "$AtlasExeInstalled,0"
    $Shortcut.Description = "Atlas"
    $Shortcut.Save()
}

function Configure-WindowsStartup
{
    New-Item `
        -Path $RunKey `
        -Force `
        | Out-Null

    if ($DisableStartup)
    {
        Remove-ItemProperty `
            -Path $RunKey `
            -Name $RunValueName `
            -ErrorAction SilentlyContinue

        return
    }

    New-ItemProperty `
        -Path $RunKey `
        -Name $RunValueName `
        -PropertyType String `
        -Value "`"$AtlasExeInstalled`"" `
        -Force `
        | Out-Null
}

function Register-AtlasInstalledApplication
{
    param(
        [string]$Version = $AtlasVersion
    )

    if (-not (Test-Path $UninstallExeInstalled))
    {
        throw "Atlas.Uninstall.exe installé introuvable : $UninstallExeInstalled"
    }

    New-Item `
        -Path $UninstallKey `
        -Force `
        | Out-Null

    $MeasuredSize = (
        Get-ChildItem `
            -Path $InstallRoot `
            -File `
            -Recurse `
            -ErrorAction SilentlyContinue `
        | Measure-Object `
            -Property Length `
            -Sum
    ).Sum

    if ($null -eq $MeasuredSize)
    {
        $MeasuredSize = 0
    }

    $EstimatedSizeKb = [int]($MeasuredSize / 1KB)

    $Values = @{
        DisplayName = "Atlas"
        DisplayVersion = $Version
        Publisher = $AtlasPublisher
        InstallLocation = $InstallRoot
        DisplayIcon = $AtlasExeInstalled
        UninstallString = "`"$UninstallExeInstalled`""
        QuietUninstallString = "`"$UninstallExeInstalled`" --quiet"
    }

    foreach ($Name in $Values.Keys)
    {
        New-ItemProperty `
            -Path $UninstallKey `
            -Name $Name `
            -PropertyType String `
            -Value $Values[$Name] `
            -Force `
            | Out-Null
    }

    foreach ($DwordValue in @{
        NoModify = 1
        NoRepair = 1
        EstimatedSize = $EstimatedSizeKb
    }.GetEnumerator())
    {
        New-ItemProperty `
            -Path $UninstallKey `
            -Name $DwordValue.Key `
            -PropertyType DWord `
            -Value $DwordValue.Value `
            -Force `
            | Out-Null
    }
}

if ($Silent -and -not $Update)
{
    throw "Le mode silencieux Atlas est réservé aux mises à jour intégrées."
}

Write-UpdateProgress `
    -Percent 2 `
    -Message "Initialisation d’Atlas..."

Write-Host "========================================" -ForegroundColor Cyan
Write-Host " Installation Atlas 3.3.5-rc.4" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

if (-not (Test-Administrator))
{
    throw "L'installation doit être lancée depuis PowerShell en administrateur."
}

Enter-AtlasInstallerLock

try
{
    Restore-OrphanedRollbackBeforeInstallation

    Write-UpdateProgress `
        -Percent 5 `
        -Message "Lecture de l’installation Atlas..."

    Import-ExistingUpdatePreferences

    $InstallState = Get-InstallationMode

    if ($Update -and $InstallState.Mode -ne "Update")
    {
        throw (
            "La mise à jour intégrée exige une version Atlas existante plus ancienne. " +
            "Mode détecté : $($InstallState.Mode)."
        )
    }

    Write-UpdateProgress `
        -Percent 10 `
        -Message "Vérification des fichiers Atlas..."

    Test-ReleasePayload
    Test-ReleasePayloadIntegrity

    $PreviousIntegrationState = Get-PreviousIntegrationState

    Write-Host ""
    Write-Host "Destination application : $InstallRoot" -ForegroundColor Cyan
    Write-Host "Zone de données          : $StorageRoot" -ForegroundColor Cyan
    Write-Host "Version cible            : $AtlasVersion" -ForegroundColor Cyan

    if ($InstallState.Mode -eq "Update")
    {
        Write-Host "Mise à jour              : $($InstallState.InstalledVersion) -> $AtlasVersion" -ForegroundColor Yellow
    }
    elseif ($InstallState.Mode -eq "Repair")
    {
        Write-Host "Réinstallation           : $($InstallState.InstalledVersion)" -ForegroundColor Yellow
    }
    else
    {
        Write-Host "Type d'installation      : nouvelle installation" -ForegroundColor DarkGray
    }
    Write-Host ""

    $RollbackAvailable = $false

    try
    {
        Write-UpdateProgress `
            -Percent 20 `
            -Message "Arrêt des composants Atlas..."

        Suspend-AtlasWindowsStartup
        Stop-ExistingAtlasService -KeepRegistration
        Stop-AtlasProcesses
        Prepare-StorageRoot
        Preserve-ExistingConfiguration

        Stop-ExistingAtlasService

        Write-UpdateProgress `
            -Percent 35 `
            -Message "Préparation de l’installation..."

        Prepare-InstallationRollback `
            -Mode $InstallState.Mode

        if (Test-Path $RollbackInstallRoot)
        {
            $RollbackAvailable = $true
        }

        Write-Host "Copie de la distribution..." -ForegroundColor Cyan

        Write-UpdateProgress `
            -Percent 55 `
            -Message "Copie des fichiers Atlas..."

        New-Item `
            -ItemType Directory `
            -Path $InstallRoot `
            -Force `
            | Out-Null

        Copy-Item `
            (Join-Path $ReleaseRoot "*") `
            $InstallRoot `
            -Recurse `
            -Force `
            -ErrorAction Stop

        if ($InstallState.Mode -eq "Fresh")
        {
            Update-InstalledAtlasConfig
        }
        else
        {
            Restore-PreservedConfiguration
        }

        Write-UpdateProgress `
            -Percent 70 `
            -Message "Validation de l'intégrité installée..."

        Test-InstalledPayloadIntegrity

        Write-UpdateProgress `
            -Percent 82 `
            -Message "Configuration des composants Atlas..."

        Write-ServiceConfiguration
        Install-AtlasService
        Configure-WindowsStartup
        Configure-DesktopShortcut
        Configure-StartMenuShortcut
        Register-AtlasInstalledApplication

        Write-UpdateProgress `
            -Percent 92 `
            -Message "Validation finale d'Atlas..."

        Test-InstalledAtlasHealth

        Sync-RuntimeConfiguration

        if ($Update -and $RestartAtlas)
        {
            Start-AtlasAfterUpdate
        }

        Complete-InstallationRollback

        Write-UpdateProgress `
            -Percent 98 `
            -Message "Installation Atlas terminée." `
            -State "installed"

        if (Test-Path $InstallBackupRoot)
        {
            Remove-Item `
                -Path $InstallBackupRoot `
                -Recurse `
                -Force `
                -ErrorAction SilentlyContinue
        }
    }
    catch
    {
        $InstallationError = $_.Exception.Message

        # Ne jamais dépendre uniquement du drapeau : une ancienne version du
        # moteur a pu déplacer des fichiers avant de lever une erreur.
        if (Test-Path $RollbackInstallRoot)
        {
            $RollbackAvailable = $true
        }

        Write-UpdateProgress `
            -Percent 0 `
            -Message "Échec détecté. Restauration de la version précédente..." `
            -State "rolling_back"

        if ($RollbackAvailable)
        {
            try
            {
                Restore-PreviousInstallation `
                    -IntegrationState $PreviousIntegrationState
            }
            catch
            {
                $RollbackError = $_.Exception.Message

                Write-UpdateProgress `
                    -Percent 0 `
                    -Message "La mise à jour et la restauration automatique ont échoué : $RollbackError" `
                    -State "failed"

                throw (
                    "L'installation Atlas a échoué : $InstallationError " +
                    "La restauration automatique a également échoué : $RollbackError"
                )
            }

            Write-UpdateProgress `
                -Percent 0 `
                -Message "La mise à jour a échoué : $InstallationError La version précédente d'Atlas a été restaurée." `
                -State "failed"

            throw (
                "L'installation Atlas a échoué : $InstallationError " +
                "L'installation précédente a été restaurée automatiquement."
            )
        }

        if ($InstallState.Mode -ne "Fresh")
        {
            try
            {
                Repair-PreviousInstallationWithoutRollback `
                    -IntegrationState $PreviousIntegrationState
            }
            catch
            {
                $RecoveryError = $_.Exception.Message

                Write-UpdateProgress `
                    -Percent 0 `
                    -Message "La mise à jour et la réactivation d'Atlas ont échoué : $RecoveryError" `
                    -State "failed"

                throw (
                    "L'installation Atlas a échoué : $InstallationError " +
                    "La réactivation de l'installation existante a également échoué : $RecoveryError"
                )
            }

            Write-UpdateProgress `
                -Percent 0 `
                -Message "La mise à jour a échoué : $InstallationError L'installation Atlas existante a été réactivée." `
                -State "failed"

            throw (
                "L'installation Atlas a échoué : $InstallationError " +
                "L'installation existante a été réactivée automatiquement."
            )
        }

        Cleanup-FailedFreshInstallation

        Write-UpdateProgress `
            -Percent 0 `
            -Message $InstallationError `
            -State "failed"

        throw (
            "L'installation Atlas a échoué : $InstallationError " +
            "Les éléments de l'installation incomplète ont été supprimés."
        )
    }

    Write-Host ""
    Write-Host "========================================" -ForegroundColor Green
    Write-Host " Atlas installé avec succès." -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "Application : $AtlasExeInstalled"
    Write-Host "Stockage    : $StorageRoot"
    Write-Host "Service     : $ServiceName (RUNNING)"
    Write-Host "Démarrage   : $(if ($DisableStartup) { 'désactivé' } else { 'activé' })"
    Write-Host ""
    Write-Host "Pour lancer Atlas :" -ForegroundColor Green
    Write-Host "& `"$AtlasExeInstalled`""

    if ($Update)
    {
        if (-not $RestartAtlas)
        {
            Write-UpdateProgress `
                -Percent 100 `
                -Message "Mise à jour terminée." `
                -State "completed"
        }
    }
    else
    {
        Write-UpdateProgress `
            -Percent 100 `
            -Message "Installation terminée." `
            -State "completed"
    }

}
finally
{
    Exit-AtlasInstallerLock
}
