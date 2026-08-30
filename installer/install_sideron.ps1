param(
    [string]$StorageRoot = "C:\SIDERON",

    [switch]$DisableStartup,

    [switch]$DisableDesktopShortcut,

    [switch]$Update,

    [switch]$Silent,

    [switch]$RestartSideron,

    [string]$ProgressFile = ""
)

$ErrorActionPreference = "Stop"

$ServiceName = "SIDERONService"
$ServiceDisplayName = "Sideron V2 Privileged Service"
$ServiceDescription = "Service privilégié local d'Sideron V2."

$SideronRoot = Resolve-Path (Join-Path $PSScriptRoot "..")

$PackagedReleaseRoot = Join-Path $PSScriptRoot "SIDERON"
$DevelopmentReleaseRoot = Join-Path $SideronRoot "dist\SIDERON"

if (Test-Path (Join-Path $PackagedReleaseRoot "SIDERON.exe"))
{
    $ReleaseRoot = $PackagedReleaseRoot
}
elseif (Test-Path (Join-Path $DevelopmentReleaseRoot "SIDERON.exe"))
{
    $ReleaseRoot = $DevelopmentReleaseRoot
}
else
{
    throw (
        "Impossible de trouver la distribution Sideron. " +
        "Chemins testés : $PackagedReleaseRoot ; $DevelopmentReleaseRoot"
    )
}

$InstallRoot = Join-Path $env:ProgramFiles "SIDERON"
$LegacyInstallRoot = Join-Path $env:ProgramFiles "Atlas"
$LegacyServiceName = "AtlasV2Service"
$LegacyUninstallKey = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Atlas"
$LegacyInstalledConfigPath = Join-Path $LegacyInstallRoot "config\atlas.json"

$SideronExeSource = Join-Path $ReleaseRoot "SIDERON.exe"
$CoreExeSource = Join-Path $ReleaseRoot "core\SIDERON.Core.exe"
$ServiceExeSource = Join-Path $ReleaseRoot "service\SIDERON.Service.exe"
$IntegrityManifestSource = Join-Path $ReleaseRoot "integrity.sha256.json"

$SideronExeInstalled = Join-Path $InstallRoot "SIDERON.exe"
$ServiceExeInstalled = Join-Path $InstallRoot "service\SIDERON.Service.exe"

$ProgramDataRoot = Join-Path $env:ProgramData "SIDERON"
$ServiceConfigPath = Join-Path $ProgramDataRoot "service_config.json"

$RunKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
$RunValueName = "SIDERON"

$InstallerMutexName = "Global\SIDERON.Setup.Installation"
$InstallerMutex = $null
$InstallerMutexOwned = $false

$SideronVersion = "3.3.6-rc.1"
$SideronPublisher = "SIDERON"
$UninstallKey = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\SIDERON"
$UninstallExeInstalled = Join-Path $InstallRoot "SIDERON.Uninstall.exe"

$InstalledConfigPath = Join-Path $InstallRoot "config\sideron.json"
$SideronApiBaseUrl = "https://atlasbot.freeboxos.fr/sideron-api/"
$SideronAccessPath = Join-Path $env:LOCALAPPDATA "SIDERON\auth\access.bin"
$LocalAppDataRoot = [Environment]::GetFolderPath(
    [Environment+SpecialFolder]::LocalApplicationData
)
$RuntimeConfigPath = Join-Path $LocalAppDataRoot "SIDERON\config\sideron.json"
$LegacyRuntimeConfigPath = Join-Path $LocalAppDataRoot "Atlas\config\atlas.json"
$InstallBackupRoot = Join-Path $env:TEMP "SIDERONInstallBackup"
$PreservedConfigPath = Join-Path $InstallBackupRoot "sideron.previous.json"

$RollbackInstallRoot = Join-Path `
    (Split-Path $InstallRoot -Parent) `
    "SIDERON.__rollback"


function Ensure-SideronApiAccess
{
    [CmdletBinding()]
    param()

    if (Test-Path $SideronAccessPath)
    {
        Write-Host "Accès OpenAI SIDERON déjà configuré pour cet utilisateur." -ForegroundColor DarkGray
        return
    }

    Write-Host "Configuration de l'accès OpenAI SIDERON..." -ForegroundColor Cyan
    Add-Type -AssemblyName System.Security

    $RegisterUri = $SideronApiBaseUrl.TrimEnd('/') + "/v1/install/register"
    $Payload = @{
        install_id = [Guid]::NewGuid().ToString("D")
        version = $SideronVersion
    } | ConvertTo-Json -Compress

    $Response = $null
    $LastError = $null
    for ($Attempt = 1; $Attempt -le 3; $Attempt++)
    {
        try
        {
            $Response = Invoke-RestMethod -Uri $RegisterUri -Method Post -ContentType "application/json; charset=utf-8" -Body $Payload -TimeoutSec 20 -ErrorAction Stop
            if ($null -eq $Response -or [string]::IsNullOrWhiteSpace([string]$Response.access_token) -or -not ([string]$Response.access_token).StartsWith("sideron_"))
            {
                throw "Le relais SIDERON a renvoyé une réponse d'inscription invalide."
            }
            break
        }
        catch
        {
            $LastError = $_.Exception.Message
            $Response = $null
            if ($Attempt -lt 3) { Start-Sleep -Seconds 2 }
        }
    }

    if ($null -eq $Response)
    {
        throw "Impossible de configurer l'accès OpenAI SIDERON pendant l'installation : $LastError"
    }

    $AccessBytes = [Text.Encoding]::ASCII.GetBytes([string]$Response.access_token)
    try
    {
        $Protected = [Security.Cryptography.ProtectedData]::Protect($AccessBytes, $null, [Security.Cryptography.DataProtectionScope]::CurrentUser)
        $AccessDirectory = Split-Path -Path $SideronAccessPath -Parent
        [IO.Directory]::CreateDirectory($AccessDirectory) | Out-Null
        [IO.File]::WriteAllBytes($SideronAccessPath, $Protected)
    }
    finally
    {
        if ($null -ne $AccessBytes) { [Array]::Clear($AccessBytes, 0, $AccessBytes.Length) }
    }

    Write-Host "Accès OpenAI SIDERON configuré automatiquement." -ForegroundColor Green
}

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
            target_version = $SideronVersion
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
    if (-not $Update -and
        -not (Test-Path $LegacyInstalledConfigPath) -and
        -not (Test-Path $LegacyRuntimeConfigPath))
    {
        return
    }

    $ExistingConfig = $null

    foreach ($Candidate in @(
        $RuntimeConfigPath,
        $InstalledConfigPath,
        $LegacyRuntimeConfigPath,
        $LegacyInstalledConfigPath
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

        # Conserve le stockage historique C:\Atlas sans le déplacer ni le
        # reformater. Les volumes dédiés Atlas et SIDERON restent acceptés.
        if ($ExistingStorageRoot -eq "C:\Atlas" -and (Test-Path $ExistingStorageRoot))
        {
            $script:StorageRoot = $ExistingStorageRoot
        }
        elseif ($ExistingStorageRoot -match "^[A-Za-z]:\\$")
        {
            $ExistingDriveLetter = $ExistingStorageRoot.Substring(0, 1)
            $ExistingVolume = Get-CimInstance `
                -ClassName Win32_LogicalDisk `
                -Filter "DeviceID = '$($ExistingDriveLetter):'" `
                -OperationTimeoutSec 3 `
                -ErrorAction SilentlyContinue

            if (
                $null -ne $ExistingVolume -and
                $ExistingVolume.VolumeName -in @("SIDERON", "ATLAS")
            )
            {
                $script:StorageRoot = $ExistingStorageRoot
            }
        }
    }

    # La lecture des dossiers spéciaux Windows peut attendre indéfiniment
    # lorsqu'un Bureau est redirigé vers un emplacement réseau indisponible.
    # Les préférences de mise à jour sont donc lues dans la configuration et
    # dans des chemins locaux déterministes, sans résoudre de Known Folder.
    if ($null -ne $ExistingConfig -and $null -ne $ExistingConfig.ui)
    {
        $script:DisableStartup = -not [bool]$ExistingConfig.ui.start_with_windows
    }

    $LocalDesktopShortcut = Join-Path $env:USERPROFILE "Desktop\SIDERON.lnk"
    $LegacyDesktopShortcut = Join-Path $env:USERPROFILE "Desktop\Atlas.lnk"
    $script:DisableDesktopShortcut = -not (
        (Test-Path -LiteralPath $LocalDesktopShortcut) -or
        (Test-Path -LiteralPath $LegacyDesktopShortcut)
    )
}

function Start-SideronAfterUpdate
{
    if (-not $RestartSideron)
    {
        return
    }

    if (-not (Test-Path $SideronExeInstalled))
    {
        throw "Impossible de redémarrer Sideron : SIDERON.exe est introuvable."
    }

    Write-UpdateProgress `
        -Percent 99 `
        -Message "Redémarrage d'Sideron..." `
        -State "restarting"

    $SideronProcess = Start-Process `
        -FilePath $SideronExeInstalled `
        -WorkingDirectory $InstallRoot `
        -PassThru

    Start-Sleep `
        -Seconds 2

    if ($SideronProcess.HasExited)
    {
        throw (
            "Sideron s'est arrêté immédiatement après la mise à jour " +
            "(code $($SideronProcess.ExitCode))."
        )
    }

    Write-UpdateProgress `
        -Percent 100 `
        -Message "Mise à jour terminée." `
        -State "completed"
}

function Enter-SideronInstallerLock
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
        $LockMessage = "Une autre installation ou mise à jour d'Sideron est déjà en cours. Fermez l'autre installateur puis réessayez."
        throw $LockMessage
    }
}

function Exit-SideronInstallerLock
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

function Suspend-SideronWindowsStartup
{
    Remove-ItemProperty `
        -Path $RunKey `
        -Name $RunValueName `
        -ErrorAction SilentlyContinue
}

function Stop-ExistingSideronService
{
    param(
        [switch]$KeepRegistration
    )

    # Ne pas dépendre uniquement du nom historique du service. Une ancienne
    # version peut avoir laissé SIDERON.Service.exe enregistré sous un autre nom.
    $InstalledServicePath = $ServiceExeInstalled.ToLowerInvariant()
    $ServiceRegistrations = @(
        Get-CimInstance Win32_Service -ErrorAction SilentlyContinue |
            Where-Object {
                $RegisteredPath = [string]$_.PathName

                $_.Name -in @($ServiceName, $LegacyServiceName) -or
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

function Stop-SideronProcesses
{
    function Get-RunningSideronProcesses
    {
        $KnownNames = @(
            "SIDERON",
            "SIDERON.Core",
            "SIDERON.Service",
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
                            (
                                $ExecutablePath.StartsWith(
                                    $InstallRoot,
                                    [StringComparison]::OrdinalIgnoreCase
                                ) -or
                                $ExecutablePath.StartsWith(
                                    $LegacyInstallRoot,
                                    [StringComparison]::OrdinalIgnoreCase
                                )
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

    $Processes = @(Get-RunningSideronProcesses)

    if ($Processes.Count -eq 0)
    {
        return
    }

    Write-Host "Fermeture de l'instance Sideron existante..." -ForegroundColor Cyan

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
        $Remaining = @(Get-RunningSideronProcesses)
    }
    while ($Remaining.Count -gt 0 -and (Get-Date) -lt $GracefulDeadline)

    if ($Remaining.Count -gt 0)
    {
        Write-Host "Arrêt forcé des composants Sideron restants..." -ForegroundColor Yellow
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
        $Remaining = @(Get-RunningSideronProcesses)
    }
    while ($Remaining.Count -gt 0 -and (Get-Date) -lt $ForcedDeadline)

    if ($Remaining.Count -gt 0)
    {
        $RemainingNames = (
            $Remaining |
                ForEach-Object { "$($_.ProcessName) (PID $($_.Id))" }
        ) -join ", "

        throw (
            "Impossible de fermer complètement les composants Sideron avant " +
            "l'installation : $RemainingNames."
        )
    }

    Write-Host "Tous les processus Sideron sont arrêtés." -ForegroundColor Green
}

function ConvertTo-SideronVersion
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

function Get-InstalledSideronVersion
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

                return [string]$Config.sideron.version
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
    $InstalledVersionText = Get-InstalledSideronVersion

    if ([string]::IsNullOrWhiteSpace($InstalledVersionText))
    {
        if ((Test-Path $LegacyInstallRoot) -or
            (Test-Path $LegacyInstalledConfigPath) -or
            (Test-Path $LegacyRuntimeConfigPath))
        {
            return [PSCustomObject]@{
                Mode = "Migration"
                InstalledVersion = "Atlas"
            }
        }

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

    $InstalledVersion = ConvertTo-SideronVersion -Value $InstalledVersionText
    $TargetVersion = ConvertTo-SideronVersion -Value $SideronVersion

    if ($null -ne $InstalledVersion -and $null -ne $TargetVersion)
    {
        if ($InstalledVersion -gt $TargetVersion)
        {
            throw (
                "Une version plus récente d'Sideron est déjà installée : " +
                "$InstalledVersionText. Installation de $SideronVersion refusée."
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
    $SourceConfigPath = @(
        $InstalledConfigPath,
        $RuntimeConfigPath,
        $LegacyRuntimeConfigPath,
        $LegacyInstalledConfigPath
    ) | Where-Object { Test-Path $_ } | Select-Object -First 1

    if ([string]::IsNullOrWhiteSpace([string]$SourceConfigPath))
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
        -Path $SourceConfigPath `
        -Destination $PreservedConfigPath `
        -Force
}

function Merge-SideronConfiguration
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
            Merge-SideronConfiguration `
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
    $NewConfigPath = Join-Path $InstallRoot "config\sideron.json"

    if (-not (Test-Path $NewConfigPath))
    {
        throw "Configuration Sideron de la nouvelle version introuvable : $NewConfigPath"
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

            Merge-SideronConfiguration `
                -Target $NewConfig `
                -Source $OldConfig

            $NewConfig.sideron.version = $SideronVersion
            $NewConfig.storage.root = $StorageRoot
            $NewConfig.ui.start_with_windows = (-not $DisableStartup)

            $ConfigJson = $NewConfig | ConvertTo-Json -Depth 30

            Write-Utf8NoBomFile `
                -Path $NewConfigPath `
                -Content $ConfigJson
        }
        catch
        {
            throw "Impossible de restaurer la configuration Sideron existante : $($_.Exception.Message)"
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

    # Ne pas résoudre les Known Folders ici : un Bureau redirigé et hors
    # ligne peut bloquer l'installation. Ces deux emplacements restent locaux.
    $DesktopPath = Join-Path $env:USERPROFILE "Desktop"
    $ProgramsPath = Join-Path $env:ProgramData "Microsoft\Windows\Start Menu\Programs"

    return [PSCustomObject]@{
        StartupCommand = $StartupCommand
        DesktopShortcutExists = Test-Path (
            Join-Path $DesktopPath "Sideron.lnk"
        )
        StartMenuShortcutExists = Test-Path (
            Join-Path $ProgramsPath "Sideron.lnk"
        )
        InstalledVersion = Get-InstalledSideronVersion
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

    if ($Mode -in @("Fresh", "Migration"))
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
        " Processus Sideron encore actifs : $($BlockingProcesses -join ', ')."
    }
    else {
        " Aucun processus exécuté depuis le dossier Sideron n'a été détecté."
    }

    throw (
        "Impossible de libérer l'installation Sideron actuelle. " +
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

    Write-Host "Une mise à jour Sideron interrompue a été détectée." -ForegroundColor Yellow
    Write-UpdateProgress `
        -Percent 3 `
        -Message "Récupération de l’installation Sideron précédente..." `
        -State "rolling_back"

    Stop-ExistingSideronService -KeepRegistration
    Stop-SideronProcesses

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

    if (-not (Test-Path $SideronExeInstalled))
    {
        throw (
            "La sauvegarde Sideron récupérée est incomplète : " +
            "$SideronExeInstalled est introuvable."
        )
    }

    Write-Host "Installation Sideron précédente récupérée." -ForegroundColor Green
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
    $DesktopShortcut = Join-Path $DesktopPath "Sideron.lnk"

    if ($State.DesktopShortcutExists)
    {
        $Shell = New-Object -ComObject WScript.Shell
        $Shortcut = $Shell.CreateShortcut($DesktopShortcut)
        $Shortcut.TargetPath = $SideronExeInstalled
        $Shortcut.WorkingDirectory = $InstallRoot
        $Shortcut.IconLocation = "$SideronExeInstalled,0"
        $Shortcut.Description = "SIDERON"
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
    $StartMenuShortcut = Join-Path $ProgramsPath "Sideron.lnk"

    if ($State.StartMenuShortcutExists)
    {
        $Shell = New-Object -ComObject WScript.Shell
        $Shortcut = $Shell.CreateShortcut($StartMenuShortcut)
        $Shortcut.TargetPath = $SideronExeInstalled
        $Shortcut.WorkingDirectory = $InstallRoot
        $Shortcut.IconLocation = "$SideronExeInstalled,0"
        $Shortcut.Description = "Sideron - Assistant personnel"
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

    Register-SideronInstalledApplication `
        -Version $Version
}

function Remove-SideronIntegrationArtifacts
{
    Stop-ExistingSideronService

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
            -Path (Join-Path $DesktopPath "Sideron.lnk") `
            -Force `
            -ErrorAction SilentlyContinue
    }

    $ProgramsPath = [Environment]::GetFolderPath(
        [Environment+SpecialFolder]::CommonPrograms
    )

    if (-not [string]::IsNullOrWhiteSpace($ProgramsPath))
    {
        Remove-Item `
            -Path (Join-Path $ProgramsPath "Sideron.lnk") `
            -Force `
            -ErrorAction SilentlyContinue
    }

    Remove-Item `
        -Path $UninstallKey `
        -Recurse `
        -Force `
        -ErrorAction SilentlyContinue
}

function Complete-LegacyAtlasMigration
{
    if (-not (Test-Path $LegacyInstallRoot) -and
        $null -eq (Get-Service -Name $LegacyServiceName -ErrorAction SilentlyContinue))
    {
        return
    }

    Write-Host "Finalisation de la migration Atlas vers SIDERON..." -ForegroundColor Cyan

    $LegacyService = Get-Service -Name $LegacyServiceName -ErrorAction SilentlyContinue
    if ($null -ne $LegacyService)
    {
        & sc.exe stop $LegacyServiceName | Out-Null
        & sc.exe delete $LegacyServiceName | Out-Null
    }

    Remove-ItemProperty -Path $RunKey -Name "Atlas" -ErrorAction SilentlyContinue

    foreach ($LegacyShortcut in @(
        (Join-Path $env:USERPROFILE "Desktop\Atlas.lnk"),
        (Join-Path $env:ProgramData "Microsoft\Windows\Start Menu\Programs\Atlas.lnk")
    ))
    {
        Remove-Item -Path $LegacyShortcut -Force -ErrorAction SilentlyContinue
    }

    Remove-Item -Path $LegacyUninstallKey -Recurse -Force -ErrorAction SilentlyContinue

    # Conserver l'ancien dossier de programmes pendant la migration : une
    # suppression récursive pourrait être partielle si un fichier est verrouillé
    # et empêcher tout retour arrière. Les données C:\Atlas ne sont jamais touchées.
    Write-Host "Migration Atlas vers SIDERON terminée. L'ancien dossier de programmes est conservé pour récupération." -ForegroundColor Green
}

function Restart-LegacyAtlasAfterFailure
{
    $LegacyService = Get-Service -Name $LegacyServiceName -ErrorAction SilentlyContinue
    if ($null -ne $LegacyService -and $LegacyService.Status -ne "Running")
    {
        & sc.exe start $LegacyServiceName | Out-Null
    }
}

function Cleanup-FailedFreshInstallation
{
    Write-Host ""
    Write-Host "Nettoyage de l'installation Sideron incomplète..." -ForegroundColor Yellow

    Remove-SideronIntegrationArtifacts

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

    Stop-ExistingSideronService

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
        throw "La sauvegarde de restauration Sideron est introuvable."
    }

    Rename-Item `
        -Path $RollbackInstallRoot `
        -NewName (Split-Path -Path $InstallRoot -Leaf) `
        -ErrorAction Stop

    Write-ServiceConfiguration
    Install-SideronService

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

    Write-Host "Ancienne installation Sideron restaurée." -ForegroundColor Green
}

function Repair-PreviousInstallationWithoutRollback
{
    param(
        $IntegrationState
    )

    Write-Host ""
    Write-Host "Restauration de l'installation Sideron existante..." -ForegroundColor Yellow

    if (-not (Test-Path $InstallRoot))
    {
        throw "L'installation Sideron existante est introuvable."
    }

    Stop-ExistingSideronService
    Write-ServiceConfiguration
    Install-SideronService

    Restore-PreviousShortcutState `
        -State $IntegrationState

    Restore-PreviousInstalledApplication `
        -Version $IntegrationState.InstalledVersion

    Write-Host "Installation Sideron existante réactivée." -ForegroundColor Green
}

function Test-InstalledSideronHealth
{
    Write-Host "Validation de l'installation Sideron..." -ForegroundColor Cyan

    $RequiredFiles = @(
        $SideronExeInstalled,
        (Join-Path $InstallRoot "core\SIDERON.Core.exe"),
        (Join-Path $InstallRoot "service\SIDERON.Service.exe"),
        (Join-Path $InstallRoot "config\sideron.json"),
        $UninstallExeInstalled
    )

    foreach ($RequiredFile in $RequiredFiles)
    {
        if (-not (Test-Path $RequiredFile))
        {
            throw "Validation Sideron échouée : fichier manquant $RequiredFile"
        }
    }

    try
    {
        $InstalledConfig = Get-Content `
            -Path (Join-Path $InstallRoot "config\sideron.json") `
            -Raw `
            -Encoding UTF8 `
            | ConvertFrom-Json
    }
    catch
    {
        throw "Validation Sideron échouée : configuration sideron.json illisible."
    }

    if ([string]$InstalledConfig.sideron.version -ne $SideronVersion)
    {
        throw (
            "Validation Sideron échouée : version installée inattendue. " +
            "Attendue : $SideronVersion ; détectée : $($InstalledConfig.sideron.version)"
        )
    }

    if ([string]$InstalledConfig.storage.root -ne $StorageRoot)
    {
        throw (
            "Validation Sideron échouée : racine de stockage inattendue. " +
            "Attendue : $StorageRoot ; détectée : $($InstalledConfig.storage.root)"
        )
    }

    $Service = Get-Service `
        -Name $ServiceName `
        -ErrorAction SilentlyContinue

    if ($null -eq $Service)
    {
        throw "Validation Sideron échouée : service $ServiceName introuvable."
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
            throw "Validation Sideron échouée : service $ServiceName non démarré."
        }
    }

    $Service = Get-Service `
        -Name $ServiceName `
        -ErrorAction Stop

    if ($Service.Status -ne "Running")
    {
        throw "Validation Sideron échouée : service $ServiceName non opérationnel."
    }

    if (-not (Test-Path $UninstallKey))
    {
        throw "Validation Sideron échouée : entrée Applications installées absente."
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
        throw "Validation Sideron échouée : version Applications installées illisible."
    }

    if ($RegisteredVersion -ne $SideronVersion)
    {
        throw (
            "Validation Sideron échouée : version Windows inattendue. " +
            "Attendue : $SideronVersion ; détectée : $RegisteredVersion"
        )
    }

    $ProgramsPath = [Environment]::GetFolderPath(
        [Environment+SpecialFolder]::CommonPrograms
    )

    $StartMenuShortcutPath = Join-Path $ProgramsPath "Sideron.lnk"

    if (-not (Test-Path $StartMenuShortcutPath))
    {
        throw "Validation Sideron échouée : raccourci du menu Démarrer absent."
    }

    if (-not $DisableDesktopShortcut)
    {
        $DesktopPath = [Environment]::GetFolderPath(
            [Environment+SpecialFolder]::DesktopDirectory
        )

        $DesktopShortcutPath = Join-Path $DesktopPath "Sideron.lnk"

        if (-not (Test-Path $DesktopShortcutPath))
        {
            throw "Validation Sideron échouée : raccourci Bureau demandé mais absent."
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
                throw "Validation Sideron échouée : démarrage Windows encore actif."
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
            throw "Validation Sideron échouée : démarrage Windows demandé mais absent."
        }

        if ([string]::IsNullOrWhiteSpace($StartupValue))
        {
            throw "Validation Sideron échouée : commande de démarrage Windows vide."
        }
    }

    Write-Host "Validation Sideron réussie." -ForegroundColor Green
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


function Read-SideronIntegrityManifest
{
    param(
        [string]$ManifestPath
    )

    if (-not (Test-Path $ManifestPath))
    {
        throw "Manifeste d'intégrité Sideron introuvable : $ManifestPath"
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
        throw "Manifeste d'intégrité Sideron illisible : $ManifestPath"
    }

    if ([string]$Manifest.algorithm -ne "SHA256")
    {
        throw "Algorithme du manifeste Sideron non pris en charge."
    }

    if ($null -eq $Manifest.files -or $Manifest.files.Count -eq 0)
    {
        throw "Le manifeste d'intégrité Sideron ne contient aucun fichier."
    }

    return $Manifest
}

function Test-SideronPayloadIntegrity
{
    param(
        [string]$RootPath,
        [string]$ManifestPath,
        [string]$Context
    )

    Write-Host "Vérification SHA-256 : $Context..." -ForegroundColor Cyan

    $Manifest = Read-SideronIntegrityManifest `
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
            throw "Entrée vide dans le manifeste d'intégrité Sideron."
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
            throw "Chemin interdit dans le manifeste Sideron : $RelativePath"
        }

        if (-not (Test-Path $ResolvedCandidate -PathType Leaf))
        {
            throw "Intégrité Sideron échouée : fichier absent $RelativePath"
        }

        $File = Get-Item `
            -Path $ResolvedCandidate `
            -ErrorAction Stop

        if ([UInt64]$File.Length -ne [UInt64]$Entry.size)
        {
            throw "Intégrité Sideron échouée : taille incorrecte pour $RelativePath"
        }

        $ActualHash = Get-FileHash `
            -Path $ResolvedCandidate `
            -Algorithm SHA256 `
            -ErrorAction Stop

        $ExpectedHash = ([string]$Entry.sha256).ToLowerInvariant()
        $ComputedHash = ([string]$ActualHash.Hash).ToLowerInvariant()

        if ($ComputedHash -ne $ExpectedHash)
        {
            throw "Intégrité Sideron échouée : SHA-256 incorrect pour $RelativePath"
        }
    }

    Write-Host "Intégrité SHA-256 validée : $Context." -ForegroundColor Green
}

function Test-ReleasePayloadIntegrity
{
    Test-SideronPayloadIntegrity `
        -RootPath $ReleaseRoot `
        -ManifestPath $IntegrityManifestSource `
        -Context "payload du Setup"
}

function Test-InstalledPayloadIntegrity
{
    $InstalledManifestPath = Join-Path `
        $InstallRoot `
        "integrity.sha256.json"

    Test-SideronPayloadIntegrity `
        -RootPath $InstallRoot `
        -ManifestPath $InstalledManifestPath `
        -Context "installation copiée"
}


function Test-ReleasePayload
{
    foreach ($Path in @(
        $SideronExeSource,
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

    Write-Host "Auto-test SIDERON.Service.exe..." -ForegroundColor Cyan

    $SelfTest = Start-Process `
        -FilePath $ServiceExeSource `
        -ArgumentList "--self-test" `
        -Wait `
        -PassThru

    if ($SelfTest.ExitCode -ne 0)
    {
        throw "SIDERON.Service.exe a échoué à l'auto-test (code $($SelfTest.ExitCode))."
    }
}

function Prepare-StorageRoot
{
    $ResolvedStorageRoot = $StorageRoot.Trim()

    if ([string]::IsNullOrWhiteSpace($ResolvedStorageRoot))
    {
        throw "La zone de stockage Sideron ne peut pas être vide."
    }

    if ($ResolvedStorageRoot -in @("C:\SIDERON", "C:\Atlas"))
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
            throw "Le volume Sideron sélectionné n'existe pas : $ResolvedStorageRoot"
        }

        $DriveLetter = $ResolvedStorageRoot.Substring(0, 1)
        $Volume = Get-Volume `
            -DriveLetter $DriveLetter `
            -ErrorAction Stop

        if ($Volume.FileSystemLabel -notin @("SIDERON", "ATLAS"))
        {
            throw "Le volume dédié sélectionné doit porter le label SIDERON (ou ATLAS pour un stockage existant)."
        }
    }
    else
    {
        throw "Zone de stockage invalide. Utilise C:\SIDERON, le stockage historique C:\Atlas ou la racine d'un volume dédié SIDERON."
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


function Update-InstalledSideronConfig
{
    $ConfigPath = Join-Path $InstallRoot "config\sideron.json"

    if (-not (Test-Path $ConfigPath))
    {
        throw "Configuration Sideron introuvable après copie : $ConfigPath"
    }

    $Config = Get-Content `
        -Path $ConfigPath `
        -Raw `
        -Encoding UTF8 `
        | ConvertFrom-Json

    $Config.sideron.version = $SideronVersion
    $Config.storage.root = $StorageRoot
    $Config.ui.start_with_windows = (-not $DisableStartup)

    $ConfigJson = $Config | ConvertTo-Json -Depth 30

    Write-Utf8NoBomFile `
        -Path $ConfigPath `
        -Content $ConfigJson
}

function Sync-RuntimeConfiguration
{
    $TemplateConfigPath = Join-Path $InstallRoot "config\sideron.json"

    if (-not (Test-Path $TemplateConfigPath))
    {
        throw "Modèle de configuration Sideron introuvable : $TemplateConfigPath"
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

            Merge-SideronConfiguration `
                -Target $TemplateConfig `
                -Source $ExistingRuntimeConfig
        }
        catch
        {
            throw "Configuration runtime Sideron existante illisible : $RuntimeConfigPath"
        }
    }

    $TemplateConfig.sideron.version = $SideronVersion
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
        throw "Impossible de déterminer le SID de l'utilisateur Sideron."
    }

    $Payload = [ordered]@{
        version = 1
        allowed_user_sid = $CurrentSid
    }

    $ServiceConfigJson = $Payload | ConvertTo-Json -Depth 5

    Write-Utf8NoBomFile `
        -Path $ServiceConfigPath `
        -Content $ServiceConfigJson

    Write-Host "SID utilisateur Sideron : $CurrentSid" -ForegroundColor DarkGray

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

function Install-SideronService
{
    if (-not (Test-Path $ServiceExeInstalled))
    {
        throw "SIDERON.Service.exe installé introuvable : $ServiceExeInstalled"
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

    $ShortcutPath = Join-Path $ProgramsPath "Sideron.lnk"

    $Shell = New-Object -ComObject WScript.Shell
    $Shortcut = $Shell.CreateShortcut($ShortcutPath)

    $Shortcut.TargetPath = $SideronExeInstalled
    $Shortcut.WorkingDirectory = $InstallRoot
    $Shortcut.IconLocation = "$SideronExeInstalled,0"
    $Shortcut.Description = "Sideron - Assistant personnel"
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

    $ShortcutPath = Join-Path $DesktopPath "Sideron.lnk"

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

    $Shortcut.TargetPath = $SideronExeInstalled
    $Shortcut.WorkingDirectory = $InstallRoot
    $Shortcut.IconLocation = "$SideronExeInstalled,0"
    $Shortcut.Description = "SIDERON"
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
        -Value "`"$SideronExeInstalled`"" `
        -Force `
        | Out-Null
}

function Register-SideronInstalledApplication
{
    param(
        [string]$Version = $SideronVersion
    )

    if (-not (Test-Path $UninstallExeInstalled))
    {
        throw "SIDERON.Uninstall.exe installé introuvable : $UninstallExeInstalled"
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
        DisplayName = "SIDERON"
        DisplayVersion = $Version
        Publisher = $SideronPublisher
        InstallLocation = $InstallRoot
        DisplayIcon = $SideronExeInstalled
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
    throw "Le mode silencieux Sideron est réservé aux mises à jour intégrées."
}

Write-UpdateProgress `
    -Percent 2 `
    -Message "Initialisation d’Sideron..."

Write-Host "========================================" -ForegroundColor Cyan
Write-Host " Installation Sideron 3.3.6-rc.1" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

if (-not (Test-Administrator))
{
    throw "L'installation doit être lancée depuis PowerShell en administrateur."
}

Enter-SideronInstallerLock

try
{
    Restore-OrphanedRollbackBeforeInstallation

    Write-UpdateProgress `
        -Percent 5 `
        -Message "Lecture de l’installation Sideron..."

    Import-ExistingUpdatePreferences

    Write-UpdateProgress `
        -Percent 7 `
        -Message "Détection de la version installée..."

    if ($Update)
    {
        # L'interface Sideron a déjà comparé les versions et validé le manifeste
        # avant de lancer ce programme. Ne pas relire ici le Registre ou une
        # configuration potentiellement inaccessible : cette seconde lecture
        # pouvait immobiliser indéfiniment une mise à jour à 7 %.
        if (-not (Test-Path -LiteralPath $SideronExeInstalled -PathType Leaf))
        {
            throw (
                "La mise à jour intégrée exige une installation Sideron " +
                "existante : $SideronExeInstalled est introuvable."
            )
        }

        $InstallState = [PSCustomObject]@{
            Mode = "Update"
            InstalledVersion = "version existante"
        }
    }
    else
    {
        $InstallState = Get-InstallationMode
    }

    if ($Update -and $InstallState.Mode -ne "Update")
    {
        throw (
            "La mise à jour intégrée exige une version Sideron existante plus ancienne. " +
            "Mode détecté : $($InstallState.Mode)."
        )
    }

    Write-UpdateProgress `
        -Percent 9 `
        -Message "Lecture des préférences Windows..."

    $PreviousIntegrationState = Get-PreviousIntegrationState

    Write-UpdateProgress `
        -Percent 10 `
        -Message "Vérification des fichiers Sideron..."

    Test-ReleasePayload
    Test-ReleasePayloadIntegrity

    Write-Host ""
    Write-Host "Destination application : $InstallRoot" -ForegroundColor Cyan
    Write-Host "Zone de données          : $StorageRoot" -ForegroundColor Cyan
    Write-Host "Version cible            : $SideronVersion" -ForegroundColor Cyan

    if ($InstallState.Mode -eq "Update")
    {
        Write-Host "Mise à jour              : $($InstallState.InstalledVersion) -> $SideronVersion" -ForegroundColor Yellow
    }
    elseif ($InstallState.Mode -eq "Repair")
    {
        Write-Host "Réinstallation           : $($InstallState.InstalledVersion)" -ForegroundColor Yellow
    }
    elseif ($InstallState.Mode -eq "Migration")
    {
        Write-Host "Migration                : Atlas -> SIDERON $SideronVersion" -ForegroundColor Yellow
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
            -Message "Arrêt des composants Sideron..."

        Suspend-SideronWindowsStartup
        Stop-ExistingSideronService -KeepRegistration
        Stop-SideronProcesses
        Prepare-StorageRoot
        Preserve-ExistingConfiguration

        Stop-ExistingSideronService

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
            -Message "Copie des fichiers Sideron..."

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
            Update-InstalledSideronConfig
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
            -Message "Configuration des composants Sideron..."

        Write-ServiceConfiguration
        Install-SideronService
        Configure-WindowsStartup
        Configure-DesktopShortcut
        Configure-StartMenuShortcut
        Register-SideronInstalledApplication

        Write-UpdateProgress `
            -Percent 92 `
            -Message "Validation finale d'Sideron..."

        Test-InstalledSideronHealth

        Sync-RuntimeConfiguration

        Write-UpdateProgress `
            -Percent 94 `
            -Message "Configuration de l'accès OpenAI SIDERON..."

        Ensure-SideronApiAccess

        # La suppression de l'ancienne application n'intervient qu'après la
        # validation complète de SIDERON. C:\Atlas reste intact lorsqu'il est
        # utilisé comme zone de données.
        Complete-LegacyAtlasMigration

        if ($Update -and $RestartSideron)
        {
            Start-SideronAfterUpdate
        }

        Complete-InstallationRollback

        Write-UpdateProgress `
            -Percent 98 `
            -Message "Installation Sideron terminée." `
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
                    "L'installation Sideron a échoué : $InstallationError " +
                    "La restauration automatique a également échoué : $RollbackError"
                )
            }

            Write-UpdateProgress `
                -Percent 0 `
                -Message "La mise à jour a échoué : $InstallationError La version précédente d'Sideron a été restaurée." `
                -State "failed"

            throw (
                "L'installation Sideron a échoué : $InstallationError " +
                "L'installation précédente a été restaurée automatiquement."
            )
        }

        if ($InstallState.Mode -in @("Update", "Repair"))
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
                    -Message "La mise à jour et la restauration d'Sideron ont échoué : $RecoveryError" `
                    -State "failed"

                throw (
                    "L'installation Sideron a échoué : $InstallationError " +
                    "La restauration de l'installation existante a également échoué : $RecoveryError"
                )
            }

            Write-UpdateProgress `
                -Percent 0 `
                -Message "La mise à jour a échoué : $InstallationError L'installation Sideron existante a été réactivée." `
                -State "failed"

            throw (
                "L'installation Sideron a échoué : $InstallationError " +
                "L'installation existante a été réactivée automatiquement."
            )
        }

        Cleanup-FailedFreshInstallation
        Restart-LegacyAtlasAfterFailure

        Write-UpdateProgress `
            -Percent 0 `
            -Message $InstallationError `
            -State "failed"

        throw (
            "L'installation Sideron a échoué : $InstallationError " +
            "Les éléments de l'installation incomplète ont été supprimés."
        )
    }

    Write-Host ""
    Write-Host "========================================" -ForegroundColor Green
    Write-Host " Sideron installé avec succès." -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "Application : $SideronExeInstalled"
    Write-Host "Stockage    : $StorageRoot"
    Write-Host "Service     : $ServiceName (RUNNING)"
    Write-Host "Démarrage   : $(if ($DisableStartup) { 'désactivé' } else { 'activé' })"
    Write-Host ""
    Write-Host "Pour lancer Sideron :" -ForegroundColor Green
    Write-Host "& `"$SideronExeInstalled`""

    if ($Update)
    {
        if (-not $RestartSideron)
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
    Exit-SideronInstallerLock
}
