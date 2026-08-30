$ErrorActionPreference = "Stop"

$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = $Utf8NoBom
[Console]::InputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom

Add-Type -AssemblyName PresentationFramework
Add-Type -AssemblyName PresentationCore
Add-Type -AssemblyName WindowsBase


Add-Type @"
using System;
using System.Runtime.InteropServices;

public static class SideronInstallerNative
{
    public const uint WM_SETICON = 0x0080;
    public const int ICON_SMALL = 0;
    public const int ICON_BIG = 1;
    public const uint IMAGE_ICON = 1;
    public const uint LR_LOADFROMFILE = 0x0010;
    public const uint LR_DEFAULTSIZE = 0x0040;
    public const int SW_RESTORE = 9;

    [DllImport("user32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    public static extern IntPtr LoadImage(
        IntPtr hInst,
        string name,
        uint type,
        int cx,
        int cy,
        uint fuLoad);

    [DllImport("user32.dll")]
    public static extern IntPtr SendMessage(
        IntPtr hWnd,
        uint msg,
        IntPtr wParam,
        IntPtr lParam);

    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static extern bool SetForegroundWindow(
        IntPtr hWnd);

    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static extern bool ShowWindow(
        IntPtr hWnd,
        int nCmdShow);

    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static extern bool DestroyIcon(
        IntPtr hIcon);

    [DllImport("shell32.dll", CharSet = CharSet.Unicode)]
    public static extern int SetCurrentProcessExplicitAppUserModelID(
        string appID);
}
"@

$SideronRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$StorageScript = Join-Path $PSScriptRoot "storage_partition.ps1"

if (-not (Test-Path $StorageScript))
{
    throw "storage_partition.ps1 est introuvable : $StorageScript"
}

$SideronAppUserModelId = "SIDERON.Setup"
$InstallerDiagnosticLogPath = Join-Path `
    $env:TEMP `
    "Sideron-installation-error.log"

function Write-SideronInstallerDiagnostic
{
    param(
        [string]$Stage,
        [System.Exception]$Exception,
        $StorageResult = $null,
        $InstallResult = $null,
        [string]$ProgressFile = ""
    )

    try
    {
        $Lines = New-Object System.Collections.Generic.List[string]

        $Lines.Add("Sideron - diagnostic d'installation")
        $Lines.Add("Date : $([DateTime]::Now.ToString('yyyy-MM-dd HH:mm:ss'))")
        $Lines.Add("Étape : $Stage")
        $Lines.Add("PowerShell : $($PSVersionTable.PSVersion)")
        $Lines.Add("Système : $([Environment]::OSVersion.VersionString)")
        $Lines.Add("")
        $Lines.Add("Erreur :")

        if ($null -ne $Exception)
        {
            $Lines.Add($Exception.ToString())
        }
        else
        {
            $Lines.Add("Aucune exception détaillée n'a été fournie.")
        }

        if ($null -ne $StorageResult)
        {
            $Lines.Add("")
            $Lines.Add("Préparation du stockage :")
            $Lines.Add("Code de sortie : $($StorageResult.ExitCode)")
            $Lines.Add("Sortie standard :")
            $Lines.Add([string]$StorageResult.Output)
            $Lines.Add("Sortie d'erreur :")
            $Lines.Add([string]$StorageResult.ErrorOutput)
        }

        if ($null -ne $InstallResult)
        {
            $Lines.Add("")
            $Lines.Add("Installation Sideron :")
            $Lines.Add("Code de sortie : $($InstallResult.ExitCode)")
            $Lines.Add("Sortie standard :")
            $Lines.Add([string]$InstallResult.Output)
            $Lines.Add("Sortie d'erreur :")
            $Lines.Add([string]$InstallResult.ErrorOutput)
        }

        if (
            -not [string]::IsNullOrWhiteSpace($ProgressFile) -and
            (Test-Path $ProgressFile)
        )
        {
            $Lines.Add("")
            $Lines.Add("Dernier état de progression :")
            $Lines.Add(
                [string](Get-Content -Path $ProgressFile -Raw -ErrorAction SilentlyContinue)
            )
        }

        [System.IO.File]::WriteAllLines(
            $InstallerDiagnosticLogPath,
            $Lines,
            $Utf8NoBom
        )
    }
    catch
    {
        try
        {
            [System.IO.File]::WriteAllText(
                $InstallerDiagnosticLogPath,
                "Impossible de produire le diagnostic complet : $($_.Exception.Message)",
                $Utf8NoBom
            )
        }
        catch
        {
        }
    }
}

try
{
    [void][SideronInstallerNative]::SetCurrentProcessExplicitAppUserModelID(
        $SideronAppUserModelId
    )
}
catch
{
}

function Set-SideronAdaptiveWindow
{
    param(
        [System.Windows.Window]$TargetWindow,
        [double]$PreferredWidth,
        [double]$PreferredHeight,
        [double]$ScreenMargin = 24
    )

    $WorkArea = [System.Windows.SystemParameters]::WorkArea
    $AvailableWidth = [Math]::Max(320, $WorkArea.Width - $ScreenMargin)
    $AvailableHeight = [Math]::Max(220, $WorkArea.Height - $ScreenMargin)

    $Scale = [Math]::Min(
        1.0,
        [Math]::Min(
            $AvailableWidth / $PreferredWidth,
            $AvailableHeight / $PreferredHeight
        )
    )

    if ($Scale -lt 1.0 -and $null -ne $TargetWindow.Content)
    {
        # Réduit le contenu et la fenêtre ensemble. Une simple MaxHeight
        # réduit uniquement le cadre et coupe les dernières lignes.
        $TargetWindow.Content.LayoutTransform =
            [System.Windows.Media.ScaleTransform]::new($Scale, $Scale)
    }

    $TargetWindow.MaxWidth = $AvailableWidth
    $TargetWindow.MaxHeight = $AvailableHeight
    $TargetWindow.Width = [Math]::Min($PreferredWidth * $Scale, $AvailableWidth)
    $TargetWindow.Height = [Math]::Min($PreferredHeight * $Scale, $AvailableHeight)
}

[xml]$Xaml = @"
<Window
    xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
    xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
    Title="Installation Sideron"
    Width="1060"
    Height="720"
    WindowStartupLocation="CenterScreen"
    ResizeMode="NoResize"
    WindowStyle="None"
    Background="#090F16"
    Foreground="#EEF7FC">

    <Window.Resources>
        <Style TargetType="TextBlock">
            <Setter Property="Foreground" Value="#DCEAF2"/>
            <Setter Property="FontFamily" Value="Segoe UI"/>
        </Style>

        <Style TargetType="Button">
            <Setter Property="Foreground" Value="#F4FBFF"/>
            <Setter Property="Background" Value="#183247"/>
            <Setter Property="BorderBrush" Value="#31566E"/>
            <Setter Property="BorderThickness" Value="1"/>
            <Setter Property="Padding" Value="14,8"/>
            <Setter Property="Margin" Value="0,0,8,0"/>
            <Setter Property="Cursor" Value="Hand"/>
            <Setter Property="Template">
                <Setter.Value>
                    <ControlTemplate TargetType="Button">
                        <Border
                            x:Name="ButtonBorder"
                            Background="{TemplateBinding Background}"
                            BorderBrush="{TemplateBinding BorderBrush}"
                            BorderThickness="{TemplateBinding BorderThickness}"
                            CornerRadius="5">

                            <ContentPresenter
                                HorizontalAlignment="Center"
                                VerticalAlignment="Center"
                                Margin="{TemplateBinding Padding}"
                                TextElement.Foreground="{TemplateBinding Foreground}"/>
                        </Border>

                        <ControlTemplate.Triggers>
                            <Trigger Property="IsMouseOver" Value="True">
                                <Setter
                                    TargetName="ButtonBorder"
                                    Property="Background"
                                    Value="#21435A"/>
                                <Setter
                                    TargetName="ButtonBorder"
                                    Property="BorderBrush"
                                    Value="#4C8CAB"/>
                            </Trigger>

                            <Trigger Property="IsPressed" Value="True">
                                <Setter
                                    TargetName="ButtonBorder"
                                    Property="Background"
                                    Value="#112E40"/>
                                <Setter
                                    TargetName="ButtonBorder"
                                    Property="BorderBrush"
                                    Value="#67D4FF"/>
                            </Trigger>

                            <Trigger Property="IsEnabled" Value="False">
                                <Setter
                                    TargetName="ButtonBorder"
                                    Property="Opacity"
                                    Value="0.45"/>
                            </Trigger>
                        </ControlTemplate.Triggers>
                    </ControlTemplate>
                </Setter.Value>
            </Setter>
        </Style>

        <Style TargetType="ComboBox">
            <Setter Property="Foreground" Value="#EEF7FC"/>
            <Setter Property="Background" Value="#101A25"/>
            <Setter Property="BorderBrush" Value="#31566E"/>
            <Setter Property="BorderThickness" Value="1"/>
            <Setter Property="MinHeight" Value="36"/>
            <Setter Property="Padding" Value="10,4"/>
            <Setter Property="Template">
                <Setter.Value>
                    <ControlTemplate TargetType="ComboBox">
                        <Grid>
                            <Border
                                x:Name="ComboBorder"
                                Background="{TemplateBinding Background}"
                                BorderBrush="{TemplateBinding BorderBrush}"
                                BorderThickness="{TemplateBinding BorderThickness}"
                                CornerRadius="6">

                                <Grid>
                                    <Grid.ColumnDefinitions>
                                        <ColumnDefinition Width="*"/>
                                        <ColumnDefinition Width="34"/>
                                    </Grid.ColumnDefinitions>

                                    <ContentPresenter
                                        Grid.Column="0"
                                        Margin="{TemplateBinding Padding}"
                                        VerticalAlignment="Center"
                                        HorizontalAlignment="Left"
                                        Content="{TemplateBinding SelectionBoxItem}"
                                        ContentTemplate="{TemplateBinding SelectionBoxItemTemplate}"
                                        TextElement.Foreground="#EEF7FC"/>

                                    <Border
                                        Grid.Column="1"
                                        Background="#132331"
                                        BorderBrush="#263B4A"
                                        BorderThickness="1,0,0,0"
                                        CornerRadius="0,6,6,0">

                                        <Viewbox
                                            Width="12"
                                            Height="8"
                                            HorizontalAlignment="Center"
                                            VerticalAlignment="Center">

                                        <Path
                                            Stroke="#8FDFFF"
                                            StrokeThickness="1.8"
                                            StrokeStartLineCap="Round"
                                            StrokeEndLineCap="Round"
                                            StrokeLineJoin="Round"
                                            Data="M 1,1 L 6,6 L 11,1"/>
                                    </Viewbox>
                                    </Border>
                                </Grid>
                            </Border>

                            <ToggleButton
                                x:Name="DropDownToggle"
                                Background="Transparent"
                                BorderBrush="Transparent"
                                BorderThickness="0"
                                Focusable="False"
                                ClickMode="Press"
                                IsChecked="{Binding IsDropDownOpen, RelativeSource={RelativeSource TemplatedParent}, Mode=TwoWay}">

                                <ToggleButton.Template>
                                    <ControlTemplate TargetType="ToggleButton">
                                        <Border
                                            Background="Transparent"
                                            BorderBrush="Transparent"
                                            BorderThickness="0"/>
                                    </ControlTemplate>
                                </ToggleButton.Template>
                            </ToggleButton>

                            <Popup
                                x:Name="PART_Popup"
                                Placement="Bottom"
                                IsOpen="{TemplateBinding IsDropDownOpen}"
                                AllowsTransparency="True"
                                Focusable="False"
                                PopupAnimation="Fade">

                                <Border
                                    MinWidth="{Binding ActualWidth, RelativeSource={RelativeSource TemplatedParent}}"
                                    MaxHeight="320"
                                    Margin="0,4,0,0"
                                    Background="#0F1822"
                                    BorderBrush="#31566E"
                                    BorderThickness="1"
                                    CornerRadius="6">

                                    <ScrollViewer
                                        Margin="2"
                                        VerticalScrollBarVisibility="Auto"
                                        HorizontalScrollBarVisibility="Disabled">

                                        <StackPanel IsItemsHost="True"/>
                                    </ScrollViewer>
                                </Border>
                            </Popup>
                        </Grid>

                        <ControlTemplate.Triggers>
                            <Trigger Property="IsMouseOver" Value="True">
                                <Setter
                                    TargetName="ComboBorder"
                                    Property="BorderBrush"
                                    Value="#4C8CAB"/>
                                <Setter
                                    TargetName="ComboBorder"
                                    Property="Background"
                                    Value="#122331"/>
                            </Trigger>

                            <Trigger Property="IsKeyboardFocusWithin" Value="True">
                                <Setter
                                    TargetName="ComboBorder"
                                    Property="BorderBrush"
                                    Value="#67D4FF"/>
                            </Trigger>

                            <Trigger Property="IsEnabled" Value="False">
                                <Setter
                                    TargetName="ComboBorder"
                                    Property="Opacity"
                                    Value="0.55"/>
                            </Trigger>
                        </ControlTemplate.Triggers>
                    </ControlTemplate>
                </Setter.Value>
            </Setter>
        </Style>

        <Style TargetType="ComboBoxItem">
            <Setter Property="Foreground" Value="#DCEAF2"/>
            <Setter Property="Background" Value="Transparent"/>
            <Setter Property="Padding" Value="11,8"/>
            <Setter Property="HorizontalContentAlignment" Value="Stretch"/>
            <Setter Property="Template">
                <Setter.Value>
                    <ControlTemplate TargetType="ComboBoxItem">
                        <Border
                            x:Name="ItemBorder"
                            Background="{TemplateBinding Background}"
                            CornerRadius="4"
                            Margin="2">

                            <ContentPresenter
                                Margin="{TemplateBinding Padding}"
                                VerticalAlignment="Center"
                                TextElement.Foreground="{TemplateBinding Foreground}"/>
                        </Border>

                        <ControlTemplate.Triggers>
                            <Trigger Property="IsHighlighted" Value="True">
                                <Setter
                                    TargetName="ItemBorder"
                                    Property="Background"
                                    Value="#173347"/>
                                <Setter
                                    Property="Foreground"
                                    Value="#FFFFFF"/>
                            </Trigger>

                            <Trigger Property="IsSelected" Value="True">
                                <Setter
                                    TargetName="ItemBorder"
                                    Property="Background"
                                    Value="#1B4961"/>
                                <Setter
                                    Property="Foreground"
                                    Value="#FFFFFF"/>
                            </Trigger>

                            <Trigger Property="IsEnabled" Value="False">
                                <Setter Property="Opacity" Value="0.45"/>
                            </Trigger>
                        </ControlTemplate.Triggers>
                    </ControlTemplate>
                </Setter.Value>
            </Setter>
        </Style>

        <Style TargetType="CheckBox">
            <Setter Property="Foreground" Value="#DCEAF2"/>
            <Setter Property="FontSize" Value="12"/>
            <Setter Property="VerticalContentAlignment" Value="Center"/>
        </Style>

        <Style TargetType="TextBox">
            <Setter Property="Foreground" Value="#EAF4F9"/>
            <Setter Property="Background" Value="#101A25"/>
            <Setter Property="BorderBrush" Value="#31566E"/>
            <Setter Property="BorderThickness" Value="1"/>
        </Style>

        <Style TargetType="RadioButton">
            <Setter Property="Foreground" Value="#EAF4F9"/>
            <Setter Property="Margin" Value="0,0,0,8"/>
        </Style>
    </Window.Resources>

    <Border
        Background="#090F16"
        BorderBrush="#356D86"
        BorderThickness="1">

    <Grid Margin="32,24,32,28">
        <Grid.RowDefinitions>
            <RowDefinition Height="Auto"/>
            <RowDefinition Height="*"/>
            <RowDefinition Height="Auto"/>
            <RowDefinition Height="Auto"/>
        </Grid.RowDefinitions>

        <Grid x:Name="InstallerHeader" Grid.Row="0" Margin="0,0,0,20">
            <Grid.ColumnDefinitions>
                <ColumnDefinition Width="*"/>
                <ColumnDefinition Width="44"/>
            </Grid.ColumnDefinitions>

        <StackPanel Grid.Column="0">
            <TextBlock
                Text="INSTALLATION SIDERON"
                FontSize="13"
                FontWeight="Bold"
                Foreground="#F0FAFF"
                />

            <TextBlock
                Text="Configuration du stockage"
                FontSize="28"
                FontWeight="SemiBold"
                Margin="0,6,0,0"
                Foreground="#F4FBFF"/>

            <TextBlock
                Text="Choisissez où Sideron pourra stocker ses données et configurez son démarrage avec Windows."
                FontSize="13"
                Margin="0,8,0,0"
                Foreground="#95A8B5"
                TextWrapping="Wrap"/>
        </StackPanel>

            <Button
                x:Name="WindowCloseButton"
                Grid.Column="1"
                Content="&#x00D7;"
                Width="36"
                Height="36"
                Margin="8,0,0,0"
                Padding="0"
                FontSize="20"
                VerticalAlignment="Top"
                Background="Transparent"
                BorderBrush="#31566E"
                ToolTip="Fermer"/>
        </Grid>

        <Border
            Grid.Row="1"
            Padding="20"
            CornerRadius="10"
            Background="#101821"
            BorderBrush="#263B4A"
            BorderThickness="1">

            <ScrollViewer
                VerticalScrollBarVisibility="Auto"
                HorizontalScrollBarVisibility="Disabled"
                Padding="0,0,14,0">

                <ScrollViewer.Resources>

                    <Style TargetType="{x:Type ScrollBar}">
                        <Setter Property="Width" Value="4"/>
                        <Setter Property="MinWidth" Value="4"/>
                        <Setter Property="MaxWidth" Value="4"/>
                        <Setter Property="Margin" Value="10,0,0,0"/>
                    </Style>

                </ScrollViewer.Resources>

                <StackPanel>

                    <TextBlock
                        Text="Mode de stockage"
                        FontSize="16"
                        FontWeight="SemiBold"
                        Margin="0,0,0,14"/>

                    <RadioButton
                        x:Name="ModeFolder"
                        IsChecked="True"
                        Content="Dossier local — C:\SIDERON"/>

                    <TextBlock
                        Text="Aucune modification de partition. Sideron utilise simplement C:\SIDERON."
                        Margin="24,0,0,14"
                        FontSize="11"
                        Foreground="#8297A6"
                        TextWrapping="Wrap"/>

                    <RadioButton
                        x:Name="ModeShrink"
                        Content="Créer un volume SIDERON en réduisant une partition"/>

                    <TextBlock
                        Text="Vous choisissez le disque, la partition et la taille du nouveau volume."
                        Margin="24,0,0,14"
                        FontSize="11"
                        Foreground="#8297A6"
                        TextWrapping="Wrap"/>

                    <RadioButton
                        x:Name="ModeWholeDisk"
                        Content="Dédier un disque entier à Sideron"/>

                    <TextBlock
                        Text="Le disque sélectionné sera entièrement réservé à Sideron."
                        Margin="24,0,0,22"
                        FontSize="11"
                        Foreground="#8297A6"
                        TextWrapping="Wrap"/>

                    <StackPanel
                        x:Name="DiskSelectionPanel"
                        Visibility="Collapsed">

                        <Separator
                            Margin="0,0,0,18"
                            Background="#263B4A"/>

                        <TextBlock
                            Text="Disque"
                            FontWeight="SemiBold"
                            Margin="0,0,0,6"/>

                        <ComboBox
                            x:Name="DiskComboBox"
                            Margin="0,0,0,14"/>
                    </StackPanel>

                    <StackPanel
                        x:Name="PartitionSelectionPanel"
                        Visibility="Collapsed">

                        <TextBlock
                            Text="Partition à réduire"
                            FontWeight="SemiBold"
                            Margin="0,0,0,6"/>

                        <ComboBox
                            x:Name="PartitionComboBox"
                            Margin="0,0,0,14"/>
                    </StackPanel>

                    <StackPanel
                        x:Name="PartitionSizePanel"
                        Visibility="Collapsed">

                        <TextBlock
                            Text="Taille du volume SIDERON"
                            FontWeight="SemiBold"
                            Margin="0,0,0,6"/>

                        <Grid>
                            <Grid.ColumnDefinitions>
                                <ColumnDefinition Width="*"/>
                                <ColumnDefinition Width="90"/>
                            </Grid.ColumnDefinitions>

                            <Slider
                                x:Name="SizeSlider"
                                Grid.Column="0"
                                Minimum="10"
                                Maximum="50"
                                Value="50"
                                TickFrequency="10"
                                IsSnapToTickEnabled="False"
                                Margin="0,0,12,0"/>

                            <TextBox
                                x:Name="SizeTextBox"
                                Grid.Column="1"
                                Text="50"
                                Height="32"
                                Padding="8,4"
                                VerticalContentAlignment="Center"/>
                        </Grid>

                        <TextBlock
                            Text="Go"
                            HorizontalAlignment="Right"
                            Margin="0,4,0,0"
                            Foreground="#8297A6"/>
                    </StackPanel>

                    <Separator Margin="0,20,0,18" Background="#263B4A"/>

                    <Grid>
                        <Grid.RowDefinitions>
                            <RowDefinition Height="Auto"/>
                            <RowDefinition Height="Auto"/>
                        </Grid.RowDefinitions>

                        <Grid Grid.Row="0">
                            <Grid.ColumnDefinitions>
                                <ColumnDefinition Width="*"/>
                                <ColumnDefinition Width="Auto"/>
                            </Grid.ColumnDefinitions>

                            <StackPanel>
                                <TextBlock
                                    Text="Démarrage"
                                    FontSize="14"
                                    FontWeight="SemiBold"/>

                                <TextBlock
                                    Text="Lancer automatiquement Sideron à l’ouverture de votre session Windows."
                                    Margin="0,4,20,0"
                                    FontSize="11"
                                    Foreground="#8297A6"
                                    TextWrapping="Wrap"/>
                            </StackPanel>

                            <CheckBox
                                x:Name="StartupCheckBox"
                                Grid.Column="1"
                                IsChecked="True"
                                Margin="18,0,0,0"
                                VerticalAlignment="Center"
                                Foreground="#EEF7FC"
                                Content="Démarrer avec Windows"/>
                        </Grid>

                        <Grid Grid.Row="1" Margin="0,16,0,0">
                            <Grid.ColumnDefinitions>
                                <ColumnDefinition Width="*"/>
                                <ColumnDefinition Width="Auto"/>
                            </Grid.ColumnDefinitions>

                            <StackPanel>
                                <TextBlock
                                    Text="Raccourci Bureau"
                                    FontSize="14"
                                    FontWeight="SemiBold"/>

                                <TextBlock
                                    Text="Créer un raccourci Sideron sur le Bureau de l’utilisateur."
                                    Margin="0,4,20,0"
                                    FontSize="11"
                                    Foreground="#8297A6"
                                    TextWrapping="Wrap"/>
                            </StackPanel>

                            <CheckBox
                                x:Name="DesktopShortcutCheckBox"
                                Grid.Column="1"
                                IsChecked="True"
                                Margin="18,0,0,0"
                                VerticalAlignment="Center"
                                Foreground="#EEF7FC"
                                Content="Créer l’icône sur le Bureau"/>
                        </Grid>
                    </Grid>

                </StackPanel>
            </ScrollViewer>
        </Border>

        <Border
            x:Name="InstallProgressPanel"
            Grid.Row="2"
            Visibility="Collapsed"
            Margin="0,18,0,0"
            Padding="14,11"
            CornerRadius="8"
            Background="#101821"
            BorderBrush="#263B4A"
            BorderThickness="1">

            <StackPanel>
                <Grid Margin="0,0,0,8">
                    <Grid.ColumnDefinitions>
                        <ColumnDefinition Width="*"/>
                        <ColumnDefinition Width="Auto"/>
                    </Grid.ColumnDefinitions>

                    <TextBlock
                        x:Name="InstallProgressText"
                        Text="Préparation..."
                        FontSize="12"
                        FontWeight="SemiBold"
                        Foreground="#DCEAF2"/>

                    <TextBlock
                        x:Name="InstallProgressPercentText"
                        Grid.Column="1"
                        Text="0 %"
                        FontSize="11"
                        Foreground="#67D4FF"/>
                </Grid>

                <ProgressBar
                    x:Name="InstallProgressBar"
                    Height="6"
                    Minimum="0"
                    Maximum="100"
                    Value="0"/>
            </StackPanel>
        </Border>

        <Grid Grid.Row="3" Margin="0,14,0,0">
            <Grid.ColumnDefinitions>
                <ColumnDefinition Width="*"/>
                <ColumnDefinition Width="Auto"/>
            </Grid.ColumnDefinitions>

            <TextBlock
                x:Name="StatusText"
                VerticalAlignment="Center"
                Text="Aucune modification de disque ne sera effectuée."
                Foreground="#93A9B7"/>

            <StackPanel Grid.Column="1" Orientation="Horizontal">
                <Button
                    x:Name="CloseButton"
                    Content="Fermer"
                    Background="Transparent"/>

                <Button
                    x:Name="InstallButton"
                    Content="Installer Sideron"
                    Background="#1D6C8E"
                    BorderBrush="#56A8C8"/>
            </StackPanel>
        </Grid>
    </Grid>
    </Border>
</Window>
"@

$Reader = New-Object System.Xml.XmlNodeReader $Xaml
$Window = [Windows.Markup.XamlReader]::Load($Reader)
Set-SideronAdaptiveWindow `
    -TargetWindow $Window `
    -PreferredWidth 1060 `
    -PreferredHeight 720

$SideronInstallerIconPath = Join-Path $PSScriptRoot "sideron.ico"
$SideronInstallerLargeIconHandle = [IntPtr]::Zero
$SideronInstallerSmallIconHandle = [IntPtr]::Zero
$SideronInstallerWindowHandle = [IntPtr]::Zero

if (Test-Path $SideronInstallerIconPath)
{
    try
    {
        $Window.Icon = [System.Windows.Media.Imaging.BitmapFrame]::Create(
            [System.Uri]::new(
                $SideronInstallerIconPath
            )
        )
    }
    catch
    {
    }
}

$Window.Add_SourceInitialized({
    try
    {
        [void][SideronInstallerNative]::SetCurrentProcessExplicitAppUserModelID(
            $SideronAppUserModelId
        )

        $InteropHelper = New-Object System.Windows.Interop.WindowInteropHelper($Window)
        $script:SideronInstallerWindowHandle = $InteropHelper.Handle

        if ((Test-Path $SideronInstallerIconPath) -and $script:SideronInstallerWindowHandle -ne [IntPtr]::Zero)
        {
            $script:SideronInstallerLargeIconHandle = [SideronInstallerNative]::LoadImage(
                [IntPtr]::Zero,
                $SideronInstallerIconPath,
                [SideronInstallerNative]::IMAGE_ICON,
                32,
                32,
                ([SideronInstallerNative]::LR_LOADFROMFILE -bor [SideronInstallerNative]::LR_DEFAULTSIZE)
            )

            $script:SideronInstallerSmallIconHandle = [SideronInstallerNative]::LoadImage(
                [IntPtr]::Zero,
                $SideronInstallerIconPath,
                [SideronInstallerNative]::IMAGE_ICON,
                16,
                16,
                ([SideronInstallerNative]::LR_LOADFROMFILE -bor [SideronInstallerNative]::LR_DEFAULTSIZE)
            )

            if ($script:SideronInstallerLargeIconHandle -ne [IntPtr]::Zero)
            {
                [void][SideronInstallerNative]::SendMessage(
                    $script:SideronInstallerWindowHandle,
                    [SideronInstallerNative]::WM_SETICON,
                    [IntPtr][SideronInstallerNative]::ICON_BIG,
                    $script:SideronInstallerLargeIconHandle
                )
            }

            if ($script:SideronInstallerSmallIconHandle -ne [IntPtr]::Zero)
            {
                [void][SideronInstallerNative]::SendMessage(
                    $script:SideronInstallerWindowHandle,
                    [SideronInstallerNative]::WM_SETICON,
                    [IntPtr][SideronInstallerNative]::ICON_SMALL,
                    $script:SideronInstallerSmallIconHandle
                )
            }
        }
    }
    catch
    {
    }
})

$Window.Add_Closed({
    if ($script:SideronInstallerLargeIconHandle -ne [IntPtr]::Zero)
    {
        [void][SideronInstallerNative]::DestroyIcon(
            $script:SideronInstallerLargeIconHandle
        )

        $script:SideronInstallerLargeIconHandle = [IntPtr]::Zero
    }

    if ($script:SideronInstallerSmallIconHandle -ne [IntPtr]::Zero)
    {
        [void][SideronInstallerNative]::DestroyIcon(
            $script:SideronInstallerSmallIconHandle
        )

        $script:SideronInstallerSmallIconHandle = [IntPtr]::Zero
    }
})

$SetupReadyEventName = $env:SIDERON_SETUP_READY_EVENT
$SetupReadyEvent = $null

if (-not [string]::IsNullOrWhiteSpace($SetupReadyEventName))
{
    try
    {
        $SetupReadyEvent = [System.Threading.EventWaitHandle]::OpenExisting(
            $SetupReadyEventName
        )
    }
    catch
    {
    }
}

$Window.Add_ContentRendered({
    try
    {
        $Window.ShowInTaskbar = $true
        $Window.WindowState = [System.Windows.WindowState]::Normal

        if ($script:SideronInstallerWindowHandle -eq [IntPtr]::Zero)
        {
            $InteropHelper = New-Object System.Windows.Interop.WindowInteropHelper($Window)
            $script:SideronInstallerWindowHandle = $InteropHelper.Handle
        }

        if ($script:SideronInstallerWindowHandle -ne [IntPtr]::Zero)
        {
            [void][SideronInstallerNative]::ShowWindow(
                $script:SideronInstallerWindowHandle,
                [SideronInstallerNative]::SW_RESTORE
            )

            [void][SideronInstallerNative]::SetForegroundWindow(
                $script:SideronInstallerWindowHandle
            )
        }

        $Window.Topmost = $true
        [void]$Window.Activate()
        [void]$Window.Focus()
        $Window.Topmost = $false
    }
    catch
    {
    }

    if ($null -ne $SetupReadyEvent)
    {
        try
        {
            [void]$SetupReadyEvent.Set()
        }
        catch
        {
        }

        try
        {
            $SetupReadyEvent.Dispose()
        }
        catch
        {
        }

        $script:SetupReadyEvent = $null
    }
})

$ModeFolder = $Window.FindName("ModeFolder")
$ModeShrink = $Window.FindName("ModeShrink")
$ModeWholeDisk = $Window.FindName("ModeWholeDisk")
$DiskSelectionPanel = $Window.FindName("DiskSelectionPanel")
$PartitionSelectionPanel = $Window.FindName("PartitionSelectionPanel")
$PartitionSizePanel = $Window.FindName("PartitionSizePanel")
$DiskComboBox = $Window.FindName("DiskComboBox")
$PartitionComboBox = $Window.FindName("PartitionComboBox")
$SizeSlider = $Window.FindName("SizeSlider")
$SizeTextBox = $Window.FindName("SizeTextBox")
$StartupCheckBox = $Window.FindName("StartupCheckBox")
$DesktopShortcutCheckBox = $Window.FindName("DesktopShortcutCheckBox")
$StatusText = $Window.FindName("StatusText")
$InstallButton = $Window.FindName("InstallButton")
$InstallProgressPanel = $Window.FindName("InstallProgressPanel")
$InstallProgressText = $Window.FindName("InstallProgressText")
$InstallProgressPercentText = $Window.FindName("InstallProgressPercentText")
$InstallProgressBar = $Window.FindName("InstallProgressBar")
$CloseButton = $Window.FindName("CloseButton")
$WindowCloseButton = $Window.FindName("WindowCloseButton")
$InstallerHeader = $Window.FindName("InstallerHeader")

$WindowCloseButton.Add_Click({
    $Window.Close()
})

$InstallerHeader.Add_MouseLeftButtonDown({
    param($Sender, $EventArgs)

    if ($EventArgs.ChangedButton -eq [System.Windows.Input.MouseButton]::Left)
    {
        try
        {
            $Window.DragMove()
        }
        catch
        {
        }
    }
})

function Format-InstallerSize
{
    param(
        [UInt64]$Bytes
    )

    if ($Bytes -ge 1TB)
    {
        return "{0:N2} To" -f ($Bytes / 1TB)
    }

    return "{0:N2} Go" -f ($Bytes / 1GB)
}

function Get-InstallerDisks
{
    return @(
        Get-Disk `
            -ErrorAction Stop `
        | Sort-Object Number
    )
}

function Refresh-DiskList
{
    $CurrentDisk = $null

    if ($null -ne $DiskComboBox.SelectedItem)
    {
        $CurrentDisk = $DiskComboBox.SelectedItem.Tag
    }

    $DiskComboBox.Items.Clear()

    foreach ($Disk in (Get-InstallerDisks))
    {
        $Item = New-Object System.Windows.Controls.ComboBoxItem
        $Item.Tag = $Disk.Number

        $Flags = @()

        if ($Disk.IsBoot)
        {
            $Flags += "Boot"
        }

        if ($Disk.IsSystem)
        {
            $Flags += "Système"
        }

        $FlagText = ""

        if ($Flags.Count -gt 0)
        {
            $FlagText = " · " + ($Flags -join ", ")
        }

        $Item.Content = (
            "Disque {0} · {1} · {2} · {3}{4}" -f
            $Disk.Number,
            $Disk.FriendlyName,
            $Disk.BusType,
            (Format-InstallerSize ([UInt64]$Disk.Size)),
            $FlagText
        )

        $DiskComboBox.Items.Add($Item) | Out-Null

        if ($null -ne $CurrentDisk -and $CurrentDisk -eq $Disk.Number)
        {
            $DiskComboBox.SelectedItem = $Item
        }
    }

    if ($DiskComboBox.SelectedIndex -lt 0 -and $DiskComboBox.Items.Count -gt 0)
    {
        $DiskComboBox.SelectedIndex = 0
    }
}

function Refresh-PartitionList
{
    $PartitionComboBox.Items.Clear()

    if ($null -eq $DiskComboBox.SelectedItem)
    {
        return
    }

    $DiskNumber = [int]$DiskComboBox.SelectedItem.Tag

    $Partitions = @(
        Get-Partition `
            -DiskNumber $DiskNumber `
            -ErrorAction SilentlyContinue `
        | Sort-Object PartitionNumber
    )

    $IgnoredPartitionTypes = @(
        "System",
        "Reserved",
        "Recovery",
        "Unknown"
    )

    foreach ($Partition in $Partitions)
    {
        $PartitionType = [string]$Partition.Type

        if ($IgnoredPartitionTypes -contains $PartitionType)
        {
            continue
        }

        $Item = New-Object System.Windows.Controls.ComboBoxItem
        $Item.Tag = $Partition.PartitionNumber

        $Letter = "-"

        if ($null -ne $Partition.DriveLetter)
        {
            $Letter = "$($Partition.DriveLetter):"
        }

        $Item.Content = (
            "Partition {0} · {1} · {2} · {3}" -f
            $Partition.PartitionNumber,
            $Letter,
            $PartitionType,
            (Format-InstallerSize ([UInt64]$Partition.Size))
        )

        $PartitionComboBox.Items.Add($Item) | Out-Null
    }

    if ($PartitionComboBox.Items.Count -gt 0)
    {
        $BestIndex = -1

        for ($Index = 0; $Index -lt $PartitionComboBox.Items.Count; $Index++)
        {
            $PartitionNumber = [int]$PartitionComboBox.Items[$Index].Tag

            $Partition = Get-Partition `
                -DiskNumber $DiskNumber `
                -PartitionNumber $PartitionNumber `
                -ErrorAction SilentlyContinue

            if ($null -ne $Partition -and $null -ne $Partition.DriveLetter)
            {
                try
                {
                    $Volume = $Partition | Get-Volume -ErrorAction Stop

                    if ($Volume.FileSystem -eq "NTFS")
                    {
                        $BestIndex = $Index
                        break
                    }
                }
                catch
                {
                }
            }
        }

        if ($BestIndex -ge 0)
        {
            $PartitionComboBox.SelectedIndex = $BestIndex
        }
        else
        {
            $PartitionComboBox.SelectedIndex = 0
        }
    }
}

function Update-PartitionSizeRange
{
    if (($ModeShrink.IsChecked -ne $true) -or ($null -eq $DiskComboBox.SelectedItem) -or ($null -eq $PartitionComboBox.SelectedItem))
    {
        return
    }

    try
    {
        $SelectedDiskNumber = [int]$DiskComboBox.SelectedItem.Tag
        $SelectedPartitionNumber = [int]$PartitionComboBox.SelectedItem.Tag

        $SelectedPartition = Get-Partition `
            -DiskNumber $SelectedDiskNumber `
            -PartitionNumber $SelectedPartitionNumber `
            -ErrorAction Stop

        $SelectedVolume = $SelectedPartition `
            | Get-Volume `
                -ErrorAction Stop

        if ($null -eq $SelectedVolume)
        {
            return
        }

        $FreeBytes = [UInt64]$SelectedVolume.SizeRemaining
        $MaximumGB = [Math]::Floor($FreeBytes / 1GB)

        if ($MaximumGB -lt 10)
        {
            $MaximumGB = 10
        }

        $SizeSlider.Maximum = [double]$MaximumGB

        $CurrentValue = 50

        if ([int]::TryParse($SizeTextBox.Text, [ref]$CurrentValue))
        {
            if ($CurrentValue -gt $MaximumGB)
            {
                $CurrentValue = [int]$MaximumGB
            }

            if ($CurrentValue -lt 10)
            {
                $CurrentValue = 10
            }
        }
        else
        {
            $CurrentValue = [Math]::Min(50, [int]$MaximumGB)
        }

        $SizeSlider.Value = [double]$CurrentValue
        $SizeTextBox.Text = [string]$CurrentValue

        $StatusText.Text = (
            "Espace libre détecté : {0:N2} Go · taille maximale proposée : {1} Go" -f
            ($FreeBytes / 1GB),
            $MaximumGB
        )
    }
    catch
    {
        $SizeSlider.Maximum = 50
    }
}

function Update-ModeUi
{
    if ($ModeFolder.IsChecked -eq $true)
    {
        $DiskSelectionPanel.Visibility = "Collapsed"
        $PartitionSelectionPanel.Visibility = "Collapsed"
        $PartitionSizePanel.Visibility = "Collapsed"

        $StatusText.Text = "Stockage prévu : C:\SIDERON"
        return
    }

    if ($ModeShrink.IsChecked -eq $true)
    {
        $DiskSelectionPanel.Visibility = "Visible"
        $PartitionSelectionPanel.Visibility = "Visible"
        $PartitionSizePanel.Visibility = "Visible"

        $StatusText.Text = "Choisissez le disque, la partition et la taille du volume SIDERON."
        Update-PartitionSizeRange
        return
    }

    $DiskSelectionPanel.Visibility = "Visible"
    $PartitionSelectionPanel.Visibility = "Collapsed"
    $PartitionSizePanel.Visibility = "Collapsed"

    $StatusText.Text = "Choisissez le disque entier qui sera dédié à Sideron."
}


function Get-SelectedStorageInstallPlan
{
    if ($ModeFolder.IsChecked -eq $true)
    {
        return [PSCustomObject]@{
            Mode = "Folder"
            StorageRoot = "C:\SIDERON"
            DiskNumber = -1
            PartitionNumber = -1
            PartitionSizeGB = 0
            Confirmation = ""
            Destructive = $false
            Summary = "Utiliser le dossier local C:\SIDERON"
        }
    }

    if ($null -eq $DiskComboBox.SelectedItem)
    {
        throw "Sélectionne un disque."
    }

    $SelectedDiskNumber = [int]$DiskComboBox.SelectedItem.Tag

    if ($ModeShrink.IsChecked -eq $true)
    {
        if ($null -eq $PartitionComboBox.SelectedItem)
        {
            throw "Sélectionne une partition."
        }

        $SelectedPartitionNumber = [int]$PartitionComboBox.SelectedItem.Tag
        $SizeGB = 0

        if (-not [int]::TryParse($SizeTextBox.Text, [ref]$SizeGB))
        {
            throw "La taille du volume SIDERON doit être un nombre entier en Go."
        }

        return [PSCustomObject]@{
            Mode = "Shrink"
            StorageRoot = ""
            DiskNumber = $SelectedDiskNumber
            PartitionNumber = $SelectedPartitionNumber
            PartitionSizeGB = $SizeGB
            Confirmation = "CREER VOLUME SIDERON"
            Destructive = $true
            Summary = "Réduire la partition sélectionnée et créer un volume SIDERON de $SizeGB Go"
        }
    }

    return [PSCustomObject]@{
        Mode = "WholeDisk"
        StorageRoot = ""
        DiskNumber = $SelectedDiskNumber
        PartitionNumber = -1
        PartitionSizeGB = 0
        Confirmation = "EFFACER DISQUE $SelectedDiskNumber"
        Destructive = $true
        Summary = "Effacer entièrement le disque $SelectedDiskNumber et le dédier à Sideron"
    }
}

function Set-SideronDialogButtonStyle
{
    param(
        [System.Windows.Controls.Button]$Button,
        [bool]$Primary = $false
    )

    $Button.Foreground = "#F4FBFF"
    $Button.BorderThickness = "1"
    $Button.Cursor = "Hand"

    if ($Primary)
    {
        $Button.Background = "#1D6C8E"
        $Button.BorderBrush = "#56A8C8"
    }
    else
    {
        $Button.Background = "#101821"
        $Button.BorderBrush = "#31566E"
    }

    $Template = New-Object System.Windows.Controls.ControlTemplate(
        [System.Windows.Controls.Button]
    )

    $Factory = New-Object System.Windows.FrameworkElementFactory(
        [System.Windows.Controls.Border]
    )

    $Factory.Name = "ButtonBorder"
    $Factory.SetBinding(
        [System.Windows.Controls.Border]::BackgroundProperty,
        (New-Object System.Windows.Data.Binding("Background") -Property @{
            RelativeSource = New-Object System.Windows.Data.RelativeSource(
                [System.Windows.Data.RelativeSourceMode]::TemplatedParent
            )
        })
    )
    $Factory.SetBinding(
        [System.Windows.Controls.Border]::BorderBrushProperty,
        (New-Object System.Windows.Data.Binding("BorderBrush") -Property @{
            RelativeSource = New-Object System.Windows.Data.RelativeSource(
                [System.Windows.Data.RelativeSourceMode]::TemplatedParent
            )
        })
    )
    $Factory.SetBinding(
        [System.Windows.Controls.Border]::BorderThicknessProperty,
        (New-Object System.Windows.Data.Binding("BorderThickness") -Property @{
            RelativeSource = New-Object System.Windows.Data.RelativeSource(
                [System.Windows.Data.RelativeSourceMode]::TemplatedParent
            )
        })
    )
    $Factory.SetValue(
        [System.Windows.Controls.Border]::CornerRadiusProperty,
        (New-Object System.Windows.CornerRadius(5))
    )

    $Content = New-Object System.Windows.FrameworkElementFactory(
        [System.Windows.Controls.ContentPresenter]
    )
    $Content.SetValue(
        [System.Windows.Controls.ContentPresenter]::HorizontalAlignmentProperty,
        [System.Windows.HorizontalAlignment]::Center
    )
    $Content.SetValue(
        [System.Windows.Controls.ContentPresenter]::VerticalAlignmentProperty,
        [System.Windows.VerticalAlignment]::Center
    )
    $Factory.AppendChild($Content)

    $Template.VisualTree = $Factory

    $HoverTrigger = New-Object System.Windows.Trigger
    $HoverTrigger.Property = [System.Windows.UIElement]::IsMouseOverProperty
    $HoverTrigger.Value = $true
    $HoverTrigger.Setters.Add(
        (New-Object System.Windows.Setter(
            [System.Windows.Controls.Border]::BackgroundProperty,
            (New-Object System.Windows.Media.SolidColorBrush(
                [System.Windows.Media.Color]::FromRgb(33, 67, 90)
            )),
            "ButtonBorder"
        ))
    )
    $HoverTrigger.Setters.Add(
        (New-Object System.Windows.Setter(
            [System.Windows.Controls.Border]::BorderBrushProperty,
            (New-Object System.Windows.Media.SolidColorBrush(
                [System.Windows.Media.Color]::FromRgb(76, 140, 171)
            )),
            "ButtonBorder"
        ))
    )
    $Template.Triggers.Add($HoverTrigger)

    $PressedTrigger = New-Object System.Windows.Trigger
    $PressedTrigger.Property = [System.Windows.Controls.Primitives.ButtonBase]::IsPressedProperty
    $PressedTrigger.Value = $true
    $PressedTrigger.Setters.Add(
        (New-Object System.Windows.Setter(
            [System.Windows.Controls.Border]::BackgroundProperty,
            (New-Object System.Windows.Media.SolidColorBrush(
                [System.Windows.Media.Color]::FromRgb(17, 46, 64)
            )),
            "ButtonBorder"
        ))
    )
    $PressedTrigger.Setters.Add(
        (New-Object System.Windows.Setter(
            [System.Windows.Controls.Border]::BorderBrushProperty,
            (New-Object System.Windows.Media.SolidColorBrush(
                [System.Windows.Media.Color]::FromRgb(103, 212, 255)
            )),
            "ButtonBorder"
        ))
    )
    $Template.Triggers.Add($PressedTrigger)

    $Button.Template = $Template
}

function Show-InstallConfirmation
{
    param(
        $Plan
    )

    $Dialog = New-Object System.Windows.Window
    $Dialog.Title = "SIDERON"
    $Dialog.Width = 560
    $Dialog.SizeToContent = "Height"
    $Dialog.MinHeight = 250
    $Dialog.MaxHeight = 520
    $Dialog.WindowStartupLocation = "CenterOwner"
    $Dialog.ResizeMode = "NoResize"
    $Dialog.WindowStyle = "None"
    $Dialog.AllowsTransparency = $true
    $Dialog.Background = "Transparent"
    $Dialog.Owner = $Window
    $Dialog.ShowInTaskbar = $false
    Set-SideronAdaptiveWindow `
        -TargetWindow $Dialog `
        -PreferredWidth 560 `
        -PreferredHeight 520 `
        -ScreenMargin 40

    $Shell = New-Object System.Windows.Controls.Border
    $Shell.Background = "#0B1018"
    $Shell.BorderBrush = "#31566E"
    $Shell.BorderThickness = "1"
    $Shell.CornerRadius = "10"

    $Root = New-Object System.Windows.Controls.Grid
    $Root.Margin = "0"

    $Root.RowDefinitions.Add((New-Object System.Windows.Controls.RowDefinition -Property @{ Height = "44" }))
    $Root.RowDefinitions.Add((New-Object System.Windows.Controls.RowDefinition -Property @{ Height = "Auto" }))
    $Root.RowDefinitions.Add((New-Object System.Windows.Controls.RowDefinition -Property @{ Height = "64" }))

    # Barre de titre Sideron.
    $TitleBar = New-Object System.Windows.Controls.Grid
    $TitleBar.Background = "#0E1721"
    [System.Windows.Controls.Grid]::SetRow($TitleBar, 0)

    $TitleBar.ColumnDefinitions.Add((New-Object System.Windows.Controls.ColumnDefinition -Property @{ Width = "*" }))
    $TitleBar.ColumnDefinitions.Add((New-Object System.Windows.Controls.ColumnDefinition -Property @{ Width = "44" }))

    $WindowTitle = New-Object System.Windows.Controls.TextBlock
    $WindowTitle.Text = "SIDERON"
    $WindowTitle.Margin = "16,0,0,0"
    $WindowTitle.VerticalAlignment = "Center"
    $WindowTitle.FontSize = 12
    $WindowTitle.FontWeight = "SemiBold"
    $WindowTitle.Foreground = "#DCEAF2"
    $TitleBar.Children.Add($WindowTitle) | Out-Null

    $CloseDialogButton = New-Object System.Windows.Controls.Button
    $CloseDialogButton.Content = "×"
        $CloseDialogButton.Width = 44
    $CloseDialogButton.Height = 44
    $CloseDialogButton.Padding = "0"
    $CloseDialogButton.Margin = "0"
    $CloseDialogButton.Background = "Transparent"
    $CloseDialogButton.Foreground = "#AFC1CC"
    $CloseDialogButton.BorderThickness = "0"
    $CloseDialogButton.FontSize = 20
    [System.Windows.Controls.Grid]::SetColumn($CloseDialogButton, 1)

    $CloseDialogButton.Add_Click({
        $Dialog.DialogResult = $false
        $Dialog.Close()
    })

    $TitleBar.Children.Add($CloseDialogButton) | Out-Null

    $TitleBar.Add_MouseLeftButtonDown({
        try
        {
            $Dialog.DragMove()
        }
        catch
        {
        }
    })

    $Root.Children.Add($TitleBar) | Out-Null

    # Contenu.
    $ContentRoot = New-Object System.Windows.Controls.StackPanel
    $ContentRoot.Margin = "26,20,26,10"
    [System.Windows.Controls.Grid]::SetRow($ContentRoot, 1)

    $Heading = New-Object System.Windows.Controls.TextBlock
    $Heading.Text = "Confirmer l'installation"
    $Heading.FontSize = 23
    $Heading.FontWeight = "SemiBold"
    $Heading.Margin = "0,0,0,16"
    $Heading.Foreground = "#F4FBFF"
    $ContentRoot.Children.Add($Heading) | Out-Null

    $SummaryCard = New-Object System.Windows.Controls.Border
    $SummaryCard.Background = "#101821"
    $SummaryCard.BorderBrush = "#263B4A"
    $SummaryCard.BorderThickness = "1"
    $SummaryCard.CornerRadius = "8"
    $SummaryCard.Padding = "16"

    $SummaryGrid = New-Object System.Windows.Controls.Grid

    $SummaryGrid.ColumnDefinitions.Add((New-Object System.Windows.Controls.ColumnDefinition -Property @{ Width = "112" }))
    $SummaryGrid.ColumnDefinitions.Add((New-Object System.Windows.Controls.ColumnDefinition -Property @{ Width = "*" }))

    for ($Index = 0; $Index -lt 5; $Index++)
    {
        $SummaryGrid.RowDefinitions.Add(
            (New-Object System.Windows.Controls.RowDefinition -Property @{ Height = "Auto" })
        )
    }

    function Add-SummaryRow
    {
        param(
            [int]$Row,
            [string]$Label,
            [string]$Value
        )

        $LabelText = New-Object System.Windows.Controls.TextBlock
        $LabelText.Text = $Label
        $LabelText.FontSize = 11
        $LabelText.Foreground = "#8297A6"
        $LabelText.Margin = "0,4,12,6"
        [System.Windows.Controls.Grid]::SetRow($LabelText, $Row)
        [System.Windows.Controls.Grid]::SetColumn($LabelText, 0)
        $SummaryGrid.Children.Add($LabelText) | Out-Null

        $ValueText = New-Object System.Windows.Controls.TextBlock
        $ValueText.Text = $Value
        $ValueText.FontSize = 12
        $ValueText.FontWeight = "SemiBold"
        $ValueText.Foreground = "#EEF7FC"
        $ValueText.Margin = "0,4,0,6"
        $ValueText.TextWrapping = "Wrap"
        $ValueText.MaxWidth = 340
        [System.Windows.Controls.Grid]::SetRow($ValueText, $Row)
        [System.Windows.Controls.Grid]::SetColumn($ValueText, 1)
        $SummaryGrid.Children.Add($ValueText) | Out-Null
    }

    Add-SummaryRow -Row 0 -Label "Stockage" -Value $Plan.Summary
    Add-SummaryRow -Row 1 -Label "Application" -Value "C:\Program Files\SIDERON"
    Add-SummaryRow -Row 2 -Label "Service" -Value "SIDERONService"
    $StartupSummary = "Désactivé"

    if ($StartupCheckBox.IsChecked -eq $true)
    {
        $StartupSummary = "Automatique avec Windows"
    }

    $DesktopShortcutSummary = "Non"

    if ($DesktopShortcutCheckBox.IsChecked -eq $true)
    {
        $DesktopShortcutSummary = "Oui"
    }

    Add-SummaryRow -Row 3 -Label "Démarrage" -Value $StartupSummary
    Add-SummaryRow -Row 4 -Label "Icône Bureau" -Value $DesktopShortcutSummary

    $SummaryCard.Child = $SummaryGrid
    $ContentRoot.Children.Add($SummaryCard) | Out-Null

    if ($Plan.Mode -eq "WholeDisk")
    {
        $WarningCard = New-Object System.Windows.Controls.Border
        $WarningCard.Background = "#261B12"
        $WarningCard.BorderBrush = "#76502C"
        $WarningCard.BorderThickness = "1"
        $WarningCard.CornerRadius = "7"
        $WarningCard.Padding = "12"
        $WarningCard.Margin = "0,12,0,0"

        $Warning = New-Object System.Windows.Controls.TextBlock
        $Warning.Text = "Attention : toutes les données du disque $($Plan.DiskNumber) seront définitivement supprimées."
        $Warning.FontSize = 11
        $Warning.FontWeight = "SemiBold"
        $Warning.Foreground = "#FFCF7C"
        $Warning.TextWrapping = "Wrap"

        $WarningCard.Child = $Warning
        $ContentRoot.Children.Add($WarningCard) | Out-Null
    }
    elseif ($Plan.Mode -eq "Shrink")
    {
        $WarningCard = New-Object System.Windows.Controls.Border
        $WarningCard.Background = "#211B12"
        $WarningCard.BorderBrush = "#66502F"
        $WarningCard.BorderThickness = "1"
        $WarningCard.CornerRadius = "7"
        $WarningCard.Padding = "12"
        $WarningCard.Margin = "0,12,0,0"

        $Warning = New-Object System.Windows.Controls.TextBlock
        $Warning.Text = "La partition sélectionnée sera redimensionnée pour créer le volume SIDERON."
        $Warning.FontSize = 11
        $Warning.Foreground = "#F3C97D"
        $Warning.TextWrapping = "Wrap"

        $WarningCard.Child = $Warning
        $ContentRoot.Children.Add($WarningCard) | Out-Null
    }

    $Root.Children.Add($ContentRoot) | Out-Null

    # Pied de fenêtre.
    $Footer = New-Object System.Windows.Controls.Border
    $Footer.Background = "#0E1721"
    $Footer.BorderBrush = "#1F303D"
    $Footer.BorderThickness = "0,1,0,0"
    [System.Windows.Controls.Grid]::SetRow($Footer, 2)

    $Buttons = New-Object System.Windows.Controls.StackPanel
    $Buttons.Orientation = "Horizontal"
    $Buttons.HorizontalAlignment = "Right"
    $Buttons.VerticalAlignment = "Center"
    $Buttons.Margin = "0,0,18,0"

    $Cancel = New-Object System.Windows.Controls.Button
    $Cancel.Content = "Annuler"
    $Cancel.MinWidth = 105
    $Cancel.Height = 34
    $Cancel.Padding = "14,6"
    $Cancel.Margin = "0,0,10,0"
    $Cancel.Background = "#101821"
    $Cancel.Foreground = "#EEF7FC"
    $Cancel.BorderBrush = "#31566E"
    Set-SideronDialogButtonStyle -Button $Cancel -Primary $false

    $Cancel.Add_Click({
        $Dialog.DialogResult = $false
        $Dialog.Close()
    })

    $Buttons.Children.Add($Cancel) | Out-Null

    $Confirm = New-Object System.Windows.Controls.Button
    $Confirm.Content = "Installer Sideron"
    $Confirm.MinWidth = 135
    $Confirm.Height = 34
    $Confirm.Padding = "14,6"
    $Confirm.Background = "#1D6C8E"
    $Confirm.Foreground = "#FFFFFF"
    $Confirm.BorderBrush = "#56A8C8"
    Set-SideronDialogButtonStyle -Button $Confirm -Primary $true

    $Confirm.Add_Click({
        $Dialog.DialogResult = $true
        $Dialog.Close()
    })

    $Buttons.Children.Add($Confirm) | Out-Null
    $Footer.Child = $Buttons
    $Root.Children.Add($Footer) | Out-Null

    $Shell.Child = $Root
    $Dialog.Content = $Shell
    Set-SideronAdaptiveWindow `
        -TargetWindow $Dialog `
        -PreferredWidth 560 `
        -PreferredHeight 520 `
        -ScreenMargin 40

    $Result = $Dialog.ShowDialog()

    return ($Result -eq $true)
}


function Invoke-HiddenPowerShell
{
    param(
        [string]$Command
    )

    $ChildCommand = "[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding(`$false); "
    $ChildCommand += "[Console]::InputEncoding = New-Object System.Text.UTF8Encoding(`$false); "
    $ChildCommand += "`$OutputEncoding = [Console]::OutputEncoding; "
    $ChildCommand += $Command

    $ProcessInfo = New-Object System.Diagnostics.ProcessStartInfo
    $ProcessInfo.FileName = "powershell.exe"
    $ProcessInfo.Arguments = "-NoProfile -ExecutionPolicy Bypass -Command " + '"' + $ChildCommand.Replace('"', '\"') + '"'
    $ProcessInfo.UseShellExecute = $false
    $ProcessInfo.RedirectStandardOutput = $true
    $ProcessInfo.RedirectStandardError = $true
    $ProcessInfo.StandardOutputEncoding = $Utf8NoBom
    $ProcessInfo.StandardErrorEncoding = $Utf8NoBom
    $ProcessInfo.CreateNoWindow = $true
    $ProcessInfo.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden

    $Process = New-Object System.Diagnostics.Process
    $Process.StartInfo = $ProcessInfo
    [void]$Process.Start()

    $Output = $Process.StandardOutput.ReadToEnd()
    $ErrorOutput = $Process.StandardError.ReadToEnd()
    $Process.WaitForExit()

    return [PSCustomObject]@{
        ExitCode = $Process.ExitCode
        Output = $Output
        ErrorOutput = $ErrorOutput
    }
}

function Get-StorageRootFromOutput
{
    param(
        [string]$Output
    )

    foreach ($Line in ($Output -split "[`r`n]+"))
    {
        if ($Line.StartsWith("SIDERON_STORAGE_ROOT="))
        {
            return $Line.Substring("SIDERON_STORAGE_ROOT=".Length).Trim()
        }
    }

    return $null
}


function New-SideronInstallProgressWindow
{
    [xml]$ProgressXaml = @"
<Window
    xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
    xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
    Title="Installation Sideron"
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
                <RowDefinition Height="27"/>
                <RowDefinition Height="36"/>
                <RowDefinition Height="18"/>
                <RowDefinition Height="14"/>
                <RowDefinition Height="28"/>
                <RowDefinition Height="*"/>
            </Grid.RowDefinitions>

            <TextBlock
                Grid.Row="0"
                Text="INSTALLATION SIDERON"
                FontFamily="Segoe UI"
                FontSize="20"
                FontWeight="Bold"
                Foreground="#F0FAFF"
                VerticalAlignment="Top"/>

            <TextBlock
                x:Name="CompactVersionText"
                Grid.Row="1"
                Text="Préparation de l’installation..."
                FontFamily="Segoe UI"
                FontSize="12"
                Foreground="#52BEEA"
                VerticalAlignment="Top"/>

            <TextBlock
                x:Name="CompactStatusText"
                Grid.Row="2"
                Text="Initialisation..."
                FontFamily="Segoe UI"
                FontSize="13"
                Foreground="#F1FAFF"
                VerticalAlignment="Center"/>

            <Grid
                x:Name="CompactProgressTrack"
                Grid.Row="3"
                Height="6"
                VerticalAlignment="Center">

                <Border
                    Background="#172B36"
                    CornerRadius="3"/>

                <Border
                    x:Name="CompactProgressFill"
                    Width="0"
                    HorizontalAlignment="Left"
                    Background="#38C9F4"
                    CornerRadius="3"/>
            </Grid>

            <TextBlock
                x:Name="CompactPercentText"
                Grid.Row="5"
                Text="0 %"
                FontFamily="Segoe UI"
                FontSize="12"
                FontWeight="SemiBold"
                Foreground="#55D5FF"
                HorizontalAlignment="Right"
                VerticalAlignment="Center"/>

            <StackPanel
                x:Name="CompactCompletionButtons"
                Grid.Row="5"
                Grid.RowSpan="2"
                Orientation="Horizontal"
                HorizontalAlignment="Right"
                VerticalAlignment="Center"
                Visibility="Collapsed">

                <Button
                    x:Name="CompactCloseButton"
                    Content="Fermer"
                    Width="110"
                    Height="34"
                    Margin="0,0,10,0"
                    Padding="12,5"
                    Background="#101D27"
                    BorderBrush="#356D86"
                    Foreground="#E5F4FC"
                    Cursor="Hand"/>

                <Button
                    x:Name="CompactLaunchButton"
                    Content="Lancer Sideron"
                    Width="130"
                    Height="34"
                    Padding="12,5"
                    Background="#1D6C8E"
                    BorderBrush="#55D5FF"
                    Foreground="#FFFFFF"
                    Cursor="Hand"/>
            </StackPanel>
        </Grid>
    </Border>
</Window>
"@

    $ProgressReader = New-Object System.Xml.XmlNodeReader $ProgressXaml
    $ProgressWindow = [Windows.Markup.XamlReader]::Load($ProgressReader)
    Set-SideronAdaptiveWindow `
        -TargetWindow $ProgressWindow `
        -PreferredWidth 620 `
        -PreferredHeight 248

    $ProgressWindow.Tag = [PSCustomObject]@{
        VersionText = $ProgressWindow.FindName("CompactVersionText")
        StatusText = $ProgressWindow.FindName("CompactStatusText")
        ProgressTrack = $ProgressWindow.FindName("CompactProgressTrack")
        ProgressFill = $ProgressWindow.FindName("CompactProgressFill")
        PercentText = $ProgressWindow.FindName("CompactPercentText")
        CompletionButtons = $ProgressWindow.FindName("CompactCompletionButtons")
        CloseButton = $ProgressWindow.FindName("CompactCloseButton")
        LaunchButton = $ProgressWindow.FindName("CompactLaunchButton")
        CompletionFrame = $null
        LaunchRequested = $false
    }

    $ProgressWindow.Tag.CloseButton.Add_Click({
        $ProgressWindow.Tag.LaunchRequested = $false

        if ($null -ne $ProgressWindow.Tag.CompletionFrame)
        {
            $ProgressWindow.Tag.CompletionFrame.Continue = $false
        }
    })

    $ProgressWindow.Tag.LaunchButton.Add_Click({
        $ProgressWindow.Tag.LaunchRequested = $true

        if ($null -ne $ProgressWindow.Tag.CompletionFrame)
        {
            $ProgressWindow.Tag.CompletionFrame.Continue = $false
        }
    })

    $ProgressWindow.Add_Closed({
        if ($null -ne $ProgressWindow.Tag.CompletionFrame)
        {
            $ProgressWindow.Tag.CompletionFrame.Continue = $false
        }
    })

    if (Test-Path $SideronInstallerIconPath)
    {
        try
        {
            $ProgressWindow.Icon = [System.Windows.Media.Imaging.BitmapFrame]::Create(
                [System.Uri]::new(
                    $SideronInstallerIconPath
                )
            )
        }
        catch
        {
        }
    }

    return $ProgressWindow
}

function Update-CompactInstallProgress
{
    param(
        [System.Windows.Window]$ProgressWindow,
        [int]$Value,
        [string]$Text
    )

    if ($null -eq $ProgressWindow)
    {
        return
    }

    if ($Value -lt 0)
    {
        $Value = 0
    }

    if ($Value -gt 100)
    {
        $Value = 100
    }

    $Controls = $ProgressWindow.Tag

    $Controls.StatusText.Text = $Text
    $Controls.PercentText.Text = "$Value %"

    $TrackWidth = [double]$Controls.ProgressTrack.ActualWidth

    if ($TrackWidth -le 0)
    {
        $TrackWidth = 552
    }

    $Controls.ProgressFill.Width = (
        $TrackWidth * ([double]$Value / 100.0)
    )

    $ProgressWindow.Dispatcher.Invoke(
        [System.Action]{},
        [System.Windows.Threading.DispatcherPriority]::Render
    )
}

function Show-SideronInstallCompletion
{
    param(
        [System.Windows.Window]$ProgressWindow
    )

    $Controls = $ProgressWindow.Tag

    $Controls.VersionText.Text = "Sideron a été installé avec succès."
    $Controls.StatusText.Text = "Installation terminée"
    $Controls.StatusText.FontSize = 16
    $Controls.StatusText.FontWeight = "SemiBold"
    $Controls.ProgressTrack.Visibility = "Collapsed"
    $Controls.PercentText.Visibility = "Collapsed"
    $Controls.CompletionButtons.Visibility = "Visible"
    $Controls.LaunchRequested = $false

    $CompletionFrame = New-Object System.Windows.Threading.DispatcherFrame
    $Controls.CompletionFrame = $CompletionFrame

    $ProgressWindow.Topmost = $true
    [void]$ProgressWindow.Activate()
    [void]$ProgressWindow.Focus()

    $ProgressWindow.Dispatcher.Invoke(
        [System.Action]{},
        [System.Windows.Threading.DispatcherPriority]::Render
    )

    [System.Windows.Threading.Dispatcher]::PushFrame($CompletionFrame)

    $Controls.CompletionFrame = $null

    return [bool]$Controls.LaunchRequested
}

function Read-SideronInstallProgress
{
    param(
        [string]$ProgressFile
    )

    if (-not (Test-Path $ProgressFile))
    {
        return $null
    }

    try
    {
        return (
            Get-Content `
                -Path $ProgressFile `
                -Raw `
                -Encoding UTF8 `
                | ConvertFrom-Json
        )
    }
    catch
    {
        return $null
    }
}

function Invoke-HiddenPowerShellWithInstallProgress
{
    param(
        [string]$Command,
        [string]$ProgressFile,
        [System.Windows.Window]$ProgressWindow
    )

    $ProcessInfo = New-Object System.Diagnostics.ProcessStartInfo
    $ProcessInfo.FileName = "powershell.exe"
    $ProcessInfo.Arguments = (
        "-NoProfile -ExecutionPolicy Bypass -Command " +
        '"' +
        $Command.Replace('"', '\"') +
        '"'
    )
    $ProcessInfo.UseShellExecute = $false
    $ProcessInfo.RedirectStandardOutput = $true
    $ProcessInfo.RedirectStandardError = $true
    $ProcessInfo.StandardOutputEncoding = $Utf8NoBom
    $ProcessInfo.StandardErrorEncoding = $Utf8NoBom
    $ProcessInfo.CreateNoWindow = $true
    $ProcessInfo.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden

    $Process = New-Object System.Diagnostics.Process
    $Process.StartInfo = $ProcessInfo

    [void]$Process.Start()

    # ReadToEndAsync draine les deux flux dans du code .NET natif. Il ne faut
    # pas utiliser add_OutputDataReceived/add_ErrorDataReceived ici : sous
    # Windows PowerShell 5.1, leurs scriptblocks peuvent être appelés depuis
    # un thread dépourvu de runspace et arrêter brutalement l'installateur.
    $OutputTask = $Process.StandardOutput.ReadToEndAsync()
    $ErrorTask = $Process.StandardError.ReadToEndAsync()

    $LastPercent = -1
    $LastMessage = ""

    while (-not $Process.HasExited)
    {
        $Progress = Read-SideronInstallProgress `
            -ProgressFile $ProgressFile

        if ($null -ne $Progress)
        {
            $EnginePercent = [int]$Progress.percent
            $MappedPercent = 45 + [int][Math]::Round(
                [Math]::Max(
                    0,
                    [Math]::Min(
                        100,
                        $EnginePercent
                    )
                ) * 0.55
            )

            $Message = [string]$Progress.message

            if (
                ($MappedPercent -ne $LastPercent) -or
                ($Message -ne $LastMessage)
            )
            {
                Update-CompactInstallProgress `
                    -ProgressWindow $ProgressWindow `
                    -Value $MappedPercent `
                    -Text $Message

                $LastPercent = $MappedPercent
                $LastMessage = $Message
            }
        }

        $ProgressWindow.Dispatcher.Invoke(
            [System.Action]{},
            [System.Windows.Threading.DispatcherPriority]::Background
        )

        Start-Sleep -Milliseconds 120
    }

    $Process.WaitForExit()

    $CapturedOutput = $OutputTask.GetAwaiter().GetResult()
    $CapturedError = $ErrorTask.GetAwaiter().GetResult()

    $FinalProgress = Read-SideronInstallProgress `
        -ProgressFile $ProgressFile

    if ($null -ne $FinalProgress)
    {
        $FinalPercent = [int]$FinalProgress.percent

        if ($FinalPercent -ge 100)
        {
            Update-CompactInstallProgress `
                -ProgressWindow $ProgressWindow `
                -Value 100 `
                -Text ([string]$FinalProgress.message)
        }
    }

    return [PSCustomObject]@{
        ExitCode = $Process.ExitCode
        Output = [string]$CapturedOutput
        ErrorOutput = [string]$CapturedError
    }
}

function Update-InstallProgress
{
    param(
        [int]$Value,
        [string]$Text
    )

    if ($Value -lt 0)
    {
        $Value = 0
    }

    if ($Value -gt 100)
    {
        $Value = 100
    }

    $InstallProgressPanel.Visibility = "Visible"
    $InstallProgressBar.Value = $Value
    $InstallProgressText.Text = $Text
    $InstallProgressPercentText.Text = "$Value %"
    $StatusText.Text = $Text

    $Window.Dispatcher.Invoke(
        [System.Action]{},
        [System.Windows.Threading.DispatcherPriority]::Render
    )
}

function Set-InstallerBusy
{
    param(
        [bool]$Busy
    )

    $InstallButton.IsEnabled = (-not $Busy)
    $CloseButton.IsEnabled = (-not $Busy)

    if (-not $Busy)
    {
        $Window.Dispatcher.Invoke(
            [System.Action]{},
            [System.Windows.Threading.DispatcherPriority]::Render
        )
    }
}


function Invoke-SideronInstallation
{
    Remove-Item `
        -Path $InstallerDiagnosticLogPath `
        -Force `
        -ErrorAction SilentlyContinue

    $Plan = Get-SelectedStorageInstallPlan

    if (-not (Show-InstallConfirmation -Plan $Plan))
    {
        $StatusText.Text = "Installation annulée."
        return
    }

    Set-InstallerBusy -Busy $true

    $ProgressWindow = New-SideronInstallProgressWindow
    $ProgressControls = $ProgressWindow.Tag

    $ProgressControls.VersionText.Text = "Installation d’Sideron..."

    $Window.Hide()
    $ProgressWindow.Show()

    Update-CompactInstallProgress `
        -ProgressWindow $ProgressWindow `
        -Value 0 `
        -Text "Préparation..."

    try
    {
        Update-CompactInstallProgress `
            -ProgressWindow $ProgressWindow `
            -Value 5 `
            -Text "Validation du stockage..."

        $EscapedStorageScript = $StorageScript.Replace("'", "''")

        if ($Plan.Mode -eq "Folder")
        {
            $StorageCommand = "& '$EscapedStorageScript' -Mode Folder -Apply"
        }
        elseif ($Plan.Mode -eq "Shrink")
        {
            $StorageCommand = "& '$EscapedStorageScript' -Mode Shrink "
            $StorageCommand += "-DiskNumber $($Plan.DiskNumber) "
            $StorageCommand += "-PartitionNumber $($Plan.PartitionNumber) "
            $StorageCommand += "-PartitionSizeGB $($Plan.PartitionSizeGB) "
            $StorageCommand += "-Apply -Confirmation '$($Plan.Confirmation)'"
        }
        else
        {
            $StorageCommand = "& '$EscapedStorageScript' -Mode WholeDisk "
            $StorageCommand += "-DiskNumber $($Plan.DiskNumber) "
            $StorageCommand += "-Apply -Confirmation '$($Plan.Confirmation)'"
        }

        Update-CompactInstallProgress `
            -ProgressWindow $ProgressWindow `
            -Value 15 `
            -Text "Préparation du stockage..."
        $StorageResult = Invoke-HiddenPowerShell -Command $StorageCommand
        $StorageCombined = ($StorageResult.Output + [Environment]::NewLine + $StorageResult.ErrorOutput).Trim()
if ($StorageResult.ExitCode -ne 0)
        {
            $DetailedStorageError = $StorageCombined

            if ([string]::IsNullOrWhiteSpace($DetailedStorageError))
            {
                $DetailedStorageError = (
                    "Le processus de préparation du stockage s'est terminé " +
                    "avec le code $($StorageResult.ExitCode)."
                )
            }

            throw (
                "La préparation du stockage a échoué.`n`n" +
                $DetailedStorageError.Trim()
            )
        }

        $StorageRoot = Get-StorageRootFromOutput -Output $StorageResult.Output

        if ([string]::IsNullOrWhiteSpace($StorageRoot))
        {
            if ($Plan.Mode -eq "Folder")
            {
                $StorageRoot = "C:\SIDERON"
            }
            else
            {
                throw "Impossible de déterminer la racine du volume SIDERON créé."
            }
        }

        Update-CompactInstallProgress `
            -ProgressWindow $ProgressWindow `
            -Value 45 `
            -Text "Stockage prêt · préparation d’Sideron..."

        $InstallScript = Join-Path $PSScriptRoot "install_sideron.ps1"

        if (-not (Test-Path $InstallScript))
        {
            throw "install_sideron.ps1 est introuvable."
        }

        $EscapedInstallScript = $InstallScript.Replace("'", "''")
        $EscapedStorageRoot = $StorageRoot.Replace("'", "''")
        $InstallCommand = "& '$EscapedInstallScript' -StorageRoot '$EscapedStorageRoot'"

        if ($StartupCheckBox.IsChecked -ne $true)
        {
            $InstallCommand += " -DisableStartup"
        }

        if ($DesktopShortcutCheckBox.IsChecked -ne $true)
        {
            $InstallCommand += " -DisableDesktopShortcut"
        }

        $ProgressFile = Join-Path `
            $env:TEMP `
            ("SideronInstallProgress-" + [Guid]::NewGuid().ToString("N") + ".json")

        Remove-Item `
            -Path $ProgressFile `
            -Force `
            -ErrorAction SilentlyContinue

        $EscapedProgressFile = $ProgressFile.Replace("'", "''")
        $InstallCommand += " -ProgressFile '$EscapedProgressFile'"

        Update-CompactInstallProgress `
            -ProgressWindow $ProgressWindow `
            -Value 46 `
            -Text "Installation des composants Sideron..."

        $InstallResult = Invoke-HiddenPowerShellWithInstallProgress `
            -Command $InstallCommand `
            -ProgressFile $ProgressFile `
            -ProgressWindow $ProgressWindow

        $InstallCombined = (
            $InstallResult.Output +
            [Environment]::NewLine +
            $InstallResult.ErrorOutput
        ).Trim()
        if ($InstallResult.ExitCode -ne 0)
        {
            $DetailedInstallError = $InstallCombined

            if ([string]::IsNullOrWhiteSpace($DetailedInstallError))
            {
                $DetailedInstallError = (
                    "Le processus d'installation Sideron s'est terminé " +
                    "avec le code $($InstallResult.ExitCode)."
                )
            }

            $DetailedInstallError = $DetailedInstallError.Trim()

            throw (
                "L'installation d'Sideron a échoué.`n`n" +
                $DetailedInstallError
            )
        }

        Update-CompactInstallProgress `
            -ProgressWindow $ProgressWindow `
            -Value 100 `
            -Text "Installation terminée."

        Start-Sleep -Milliseconds 500

        $InstalledSideronExe = "C:\Program Files\SIDERON\SIDERON.exe"
        $LaunchSideron = Show-SideronInstallCompletion `
            -ProgressWindow $ProgressWindow

        if ($LaunchSideron -and (Test-Path $InstalledSideronExe))
        {
            Start-Process `
                -FilePath $InstalledSideronExe `
                -WorkingDirectory (Split-Path $InstalledSideronExe -Parent)
        }

        if ($null -ne $ProgressWindow)
        {
            $ProgressWindow.Close()
        }

        $Window.Close()
    }
    catch
    {
        $InstallationException = $_.Exception
        $DiagnosticStorageResult = $null
        $DiagnosticInstallResult = $null
        $DiagnosticProgressFile = ""

        if (Get-Variable -Name StorageResult -ErrorAction SilentlyContinue)
        {
            $DiagnosticStorageResult = $StorageResult
        }

        if (Get-Variable -Name InstallResult -ErrorAction SilentlyContinue)
        {
            $DiagnosticInstallResult = $InstallResult
        }

        if (Get-Variable -Name ProgressFile -ErrorAction SilentlyContinue)
        {
            $DiagnosticProgressFile = [string]$ProgressFile
        }

        Write-SideronInstallerDiagnostic `
            -Stage "Invoke-SideronInstallation" `
            -Exception $InstallationException `
            -StorageResult $DiagnosticStorageResult `
            -InstallResult $DiagnosticInstallResult `
            -ProgressFile $DiagnosticProgressFile

        if ($null -ne $ProgressWindow)
        {
            try
            {
                $ProgressWindow.Hide()
            }
            catch
            {
            }
        }

        $Window.Show()
        $Window.WindowState = [System.Windows.WindowState]::Normal
        $Window.Topmost = $true
        $Window.Activate()
        $Window.Focus()
        $StatusText.Text = "Échec de l'installation."

        $ErrorMessage = (
            $InstallationException.Message +
            "`n`nUn diagnostic a été enregistré dans :`n" +
            $InstallerDiagnosticLogPath
        )

        try
        {
            [System.Windows.MessageBox]::Show(
                $Window,
                $ErrorMessage,
                "Échec de l'installation Sideron",
                [System.Windows.MessageBoxButton]::OK,
                [System.Windows.MessageBoxImage]::Error
            ) | Out-Null
        }
        finally
        {
            $Window.Topmost = $false

            if ($null -ne $ProgressWindow)
            {
                try
                {
                    $ProgressWindow.Close()
                }
                catch
                {
                }
            }
        }
    }
    finally
    {
        if (
            (Get-Variable -Name ProgressFile -ErrorAction SilentlyContinue) -and
            (-not [string]::IsNullOrWhiteSpace($ProgressFile))
        )
        {
            Remove-Item `
                -Path $ProgressFile `
                -Force `
                -ErrorAction SilentlyContinue
        }

        Set-InstallerBusy -Busy $false
    }
}


$ModeFolder.Add_Checked({
    Update-ModeUi
})

$ModeShrink.Add_Checked({
    Update-ModeUi
})

$ModeWholeDisk.Add_Checked({
    Update-ModeUi
})

$DiskComboBox.Add_SelectionChanged({
    if ($ModeShrink.IsChecked -eq $true)
    {
        Refresh-PartitionList
        Update-PartitionSizeRange
    }
})

$PartitionComboBox.Add_SelectionChanged({
    if ($ModeShrink.IsChecked -eq $true)
    {
        Update-PartitionSizeRange
    }
})

$SizeSlider.Add_ValueChanged({
    if ($null -ne $SizeTextBox)
    {
        $SizeTextBox.Text = [string][int]$SizeSlider.Value
    }
})

$SizeTextBox.Add_LostFocus({
    $Value = 50

    if ([int]::TryParse($SizeTextBox.Text, [ref]$Value))
    {
        if ($Value -lt 10)
        {
            $Value = 10
        }

        $MaximumAllowed = [int][Math]::Floor($SizeSlider.Maximum)

        if ($Value -gt $MaximumAllowed)
        {
            $Value = $MaximumAllowed
        }

        $SizeTextBox.Text = [string]$Value
        $SizeSlider.Value = [double]$Value
    }
})



$InstallButton.Add_Click({
    Invoke-SideronInstallation
})

$CloseButton.Add_Click({
    $Window.Close()
})

Refresh-DiskList
Refresh-PartitionList
Update-ModeUi
Update-PartitionSizeRange
Update-PartitionSizeRange
[void]$Window.ShowDialog()
