param(
    [string]$InstalledRoot = "",

    [switch]$RemoveData,

    [switch]$Quiet
)

$ErrorActionPreference = "Stop"

$ServiceName = "AtlasV2Service"

if ([string]::IsNullOrWhiteSpace($InstalledRoot))
{
    $InstallRoot = Join-Path $env:ProgramFiles "Atlas"
}
else
{
    $InstallRoot = $InstalledRoot.TrimEnd("\")
}

$ProgramDataRoot = Join-Path $env:ProgramData "Atlas"
$LocalAppDataRoot = Join-Path $env:LOCALAPPDATA "Atlas"

$RunKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
$RunValueName = "Atlas"

$DesktopPath = [Environment]::GetFolderPath(
    [Environment+SpecialFolder]::DesktopDirectory
)
$DesktopShortcutPath = Join-Path $DesktopPath "Atlas.lnk"

$ProgramsPath = [Environment]::GetFolderPath(
    [Environment+SpecialFolder]::CommonPrograms
)
$StartMenuShortcutPath = Join-Path $ProgramsPath "Atlas.lnk"

$UninstallKey = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Atlas"

function Test-Administrator
{
    $Identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $Principal = New-Object Security.Principal.WindowsPrincipal($Identity)

    return $Principal.IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator
    )
}

function Wait-ServiceStopped
{
    param(
        [string]$Name,
        [int]$TimeoutSeconds = 30
    )

    $Deadline = (Get-Date).AddSeconds($TimeoutSeconds)

    do
    {
        $Service = Get-Service `
            -Name $Name `
            -ErrorAction SilentlyContinue

        if ($null -eq $Service -or $Service.Status -eq "Stopped")
        {
            return $true
        }

        Start-Sleep -Milliseconds 300
    }
    while ((Get-Date) -lt $Deadline)

    return $false
}

function Get-InstalledStorageRoot
{
    $ConfigPath = Join-Path $InstallRoot "config\atlas.json"

    if (-not (Test-Path $ConfigPath))
    {
        return $null
    }

    try
    {
        $Config = Get-Content `
            -Path $ConfigPath `
            -Raw `
            -Encoding UTF8 `
            | ConvertFrom-Json

        if ($null -ne $Config.storage)
        {
            return [string]$Config.storage.root
        }
    }
    catch
    {
    }

    return $null
}

function Remove-AtlasStorageData
{
    param(
        [string]$StorageRoot
    )

    if ([string]::IsNullOrWhiteSpace($StorageRoot))
    {
        return
    }

    if (-not (Test-Path $StorageRoot))
    {
        return
    }

    $FullRoot = [System.IO.Path]::GetFullPath($StorageRoot)

    if ($FullRoot -eq "C:\")
    {
        throw "Refus de supprimer la racine du disque système."
    }

    if ($FullRoot -match "^[A-Za-z]:\\$")
    {
        Get-ChildItem `
            -Path $FullRoot `
            -Force `
            -ErrorAction SilentlyContinue `
            | Remove-Item `
                -Recurse `
                -Force `
                -ErrorAction Stop

        return
    }

    Remove-Item `
        -Path $FullRoot `
        -Recurse `
        -Force `
        -ErrorAction Stop
}

if (-not (Test-Administrator))
{
    throw "La désinstallation doit être lancée en administrateur."
}

$StorageRoot = Get-InstalledStorageRoot

# Laisse le temps à Atlas.Uninstall.exe de quitter.
Start-Sleep -Milliseconds 1200

foreach ($ProcessName in @(
    "Atlas",
    "Atlas.Core"
))
{
    Get-Process `
        -Name $ProcessName `
        -ErrorAction SilentlyContinue `
        | Stop-Process `
            -Force `
            -ErrorAction SilentlyContinue
}

$Service = Get-Service `
    -Name $ServiceName `
    -ErrorAction SilentlyContinue

if ($null -ne $Service)
{
    if ($Service.Status -ne "Stopped")
    {
        & sc.exe stop $ServiceName | Out-Null

        if (-not (Wait-ServiceStopped -Name $ServiceName))
        {
            throw "Impossible d'arrêter $ServiceName."
        }
    }

    & sc.exe delete $ServiceName | Out-Null

    if ($LASTEXITCODE -ne 0)
    {
        throw "Impossible de supprimer $ServiceName."
    }

    Start-Sleep -Milliseconds 800
}

Remove-ItemProperty `
    -Path $RunKey `
    -Name $RunValueName `
    -ErrorAction SilentlyContinue

Remove-Item `
    -Path $DesktopShortcutPath `
    -Force `
    -ErrorAction SilentlyContinue

Remove-Item `
    -Path $StartMenuShortcutPath `
    -Force `
    -ErrorAction SilentlyContinue

Remove-Item `
    -Path $UninstallKey `
    -Recurse `
    -Force `
    -ErrorAction SilentlyContinue

if (Test-Path $ProgramDataRoot)
{
    Remove-Item `
        -Path $ProgramDataRoot `
        -Recurse `
        -Force `
        -ErrorAction SilentlyContinue
}

if (Test-Path $InstallRoot)
{
    Remove-Item `
        -Path $InstallRoot `
        -Recurse `
        -Force `
        -ErrorAction Stop
}

if ($RemoveData)
{
    Remove-AtlasStorageData `
        -StorageRoot $StorageRoot

    if (Test-Path $LocalAppDataRoot)
    {
        Remove-Item `
            -Path $LocalAppDataRoot `
            -Recurse `
            -Force `
            -ErrorAction Stop
    }
}

if (-not $Quiet)
{
    Add-Type -AssemblyName PresentationFramework
    Add-Type -AssemblyName PresentationCore
    Add-Type -AssemblyName WindowsBase

    $DataResultText = "Les données utilisateur ont été conservées."

    if ($RemoveData)
    {
        $DataResultText = "Les données utilisateur Atlas ont été supprimées."
    }

    [xml]$CompletionXaml = @"
<Window
    xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
    xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
    Title="Désinstallation Atlas"
    Width="620"
    Height="248"
    WindowStartupLocation="CenterScreen"
    ResizeMode="NoResize"
    WindowStyle="None"
    Background="#091016"
    Foreground="#E5F4FC"
    ShowInTaskbar="True"
    Topmost="True">

    <Border
        Background="#091016"
        BorderBrush="#356D86"
        BorderThickness="1">

        <Grid Margin="34,27,34,25">
            <Grid.RowDefinitions>
                <RowDefinition Height="40"/>
                <RowDefinition Height="30"/>
                <RowDefinition Height="46"/>
                <RowDefinition Height="*"/>
            </Grid.RowDefinitions>

            <TextBlock
                Grid.Row="0"
                Text="DÉSINSTALLATION ATLAS"
                FontFamily="Segoe UI"
                FontSize="20"
                FontWeight="Bold"
                Foreground="#F0FAFF"
                VerticalAlignment="Top"/>

            <TextBlock
                Grid.Row="1"
                Text="Atlas a été désinstallé avec succès."
                FontFamily="Segoe UI"
                FontSize="12"
                Foreground="#52BEEA"
                VerticalAlignment="Top"/>

            <TextBlock
                x:Name="DataResultText"
                Grid.Row="2"
                FontFamily="Segoe UI"
                FontSize="13"
                Foreground="#F1FAFF"
                VerticalAlignment="Center"/>

            <Button
                x:Name="CloseCompletionButton"
                Grid.Row="3"
                Content="Fermer"
                Width="110"
                Height="34"
                Margin="0,0,0,8"
                Padding="12,5"
                HorizontalAlignment="Right"
                VerticalAlignment="Bottom"
                Background="#101D27"
                BorderBrush="#356D86"
                Foreground="#E5F4FC"
                Cursor="Hand"/>
        </Grid>
    </Border>
</Window>
"@

    $CompletionReader = New-Object System.Xml.XmlNodeReader $CompletionXaml
    $CompletionWindow = [Windows.Markup.XamlReader]::Load($CompletionReader)
    $CompletionWindow.FindName("DataResultText").Text = $DataResultText
    $CompletionWindow.FindName("CloseCompletionButton").Add_Click({
        $CompletionWindow.Close()
    })

    [void]$CompletionWindow.ShowDialog()
}

$TempRoot = Split-Path $PSCommandPath -Parent

Start-Process `
    -FilePath "cmd.exe" `
    -ArgumentList @(
        "/c",
        "ping 127.0.0.1 -n 2 >nul & rmdir /s /q `"$TempRoot`""
    ) `
    -WindowStyle Hidden
