using Atlas.UI.Models;
using Atlas.UI.Services;
using Microsoft.UI.Input;
using Microsoft.UI.Windowing;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Shapes;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Input;
using System.Runtime.InteropServices;
using System.Text.Json;
using System.Globalization;
using System.Text;
using Windows.System;
using Windows.UI.Core;
using WinRT.Interop;
using IOPath = System.IO.Path;

namespace Atlas.UI.Desktop;

public sealed partial class DesktopWindow : Window
{
    private enum ExplorerSortColumn
    {
        Name,
        Type,
        Modified,
        Size,
    }

    private enum ExplorerViewMode
    {
        Details,
        Compact,
        Icons,
    }

    [Flags]
    private enum WindowSnapTarget
    {
        None,
        Left,
        Right,
        Maximize,
    }

    private enum WindowResizeEdge
    {
        None = 0,
        Left = 1,
        Top = 2,
        Right = 4,
        Bottom = 8,
    }

    private sealed record ResizeHandleContext(
        FrameworkElement Panel,
        WindowResizeEdge Edge);


    private sealed record FloatingWindowRestoreState(
        double Width,
        double Height,
        Thickness Margin,
        HorizontalAlignment HorizontalAlignment,
        VerticalAlignment VerticalAlignment);


    private sealed class PrimaryExplorerTabState
    {
        public Guid Id { get; } = Guid.NewGuid();
        public string Directory { get; set; } = string.Empty;
        public Stack<string> BackHistory { get; } = new();
        public Stack<string> ForwardHistory { get; } = new();
        public Button? TabButton { get; set; }
        public Border? TabContainer { get; set; }
    }

    private readonly AtlasConfigService _config;
    private readonly DisplayService _displayService;
    private readonly DispatcherTimer _clockTimer;
    private readonly DispatcherTimer _taskbarGuardTimer;
    private readonly DispatcherTimer _storageWidgetTimer;
    private readonly DispatcherTimer _updateCheckTimer;
    private readonly TaskbarVisibilityService _taskbarVisibility;
    private readonly AtlasIpcServerService _ipc;
    private readonly CoreProcessService _coreProcess;
    private readonly StartupRegistrationService _startupRegistration;
    private readonly AtlasUpdateService _updateService;
    private AtlasUpdateConfiguration _updateConfiguration =
        AtlasUpdateConfiguration.Default;

    private AtlasUpdateManifest? _availableUpdateManifest;
    private AtlasUpdateDownloadResult? _verifiedDownloadedUpdate;
    private bool _updateCheckInProgress;
    private bool _syncingUpdateChannel;
    private DisplayDescriptor? _atlasDisplay;
    private string _currentListeningMode = "continuous";
    private bool _syncingMicrophone;
    private bool _syncingSpeaker;
    private bool _changingUpdateChannel;
    private bool _updateOperationInProgress;
    private bool _updateCheckAgain;
    private bool _updateNoticeOpen;
    private readonly HashSet<string> _notifiedUpdates = new();
    private bool _voiceSessionActive;
    private bool _applyingWidgetPreferences;
    private FrameworkElement? _draggedDesktopWidget;
    private Windows.Foundation.Point _desktopWidgetDragStartPointer;
    private double _desktopWidgetDragStartLeft;
    private double _desktopWidgetDragStartTop;
    private string _widgetsLayoutMode = "right";
    private bool _widgetPresetNeedsInitialLayout;
    private bool _widgetsLocked = true;
    private const double DockHeightDip = 62.0;
    private const double DockBottomMarginDip = 18.0;
    private const double DockWorkspaceGapDip = 10.0;

    private const string AtlasVersion =
        "3.3.5-rc.4";

    private const string AtlasReleaseChannel =
        "Experimental";

    private bool _coreConnected;

    private readonly List<PrimaryExplorerTabState> _primaryExplorerTabs =
        new();

    private PrimaryExplorerTabState? _activePrimaryExplorerTab;
    private bool _applyingPrimaryExplorerTabs;

    private readonly HashSet<string> _selectedPaths =
        new(
            StringComparer.OrdinalIgnoreCase);

    private readonly Dictionary<string, Button> _entryButtons =
        new(
            StringComparer.OrdinalIgnoreCase);

    private readonly List<string> _visiblePaths =
        new();

    private WorkspaceFileService? _workspaceFiles;

    private string? _selectionAnchorPath;

    private ExplorerSortColumn _sortColumn =
        ExplorerSortColumn.Name;

    private bool _sortAscending =
        true;

    private ExplorerViewMode _viewMode =
        ExplorerViewMode.Details;

    private IReadOnlyList<string> _clipboardPaths =
        Array.Empty<string>();

    private bool _clipboardMove;

    private bool _syncingSettingsControls;

    private bool _settingsEditingReady;
    private bool _settingsHasUnsavedChanges;

    private int _floatingWindowZIndex =
        20;

    private FrameworkElement? _movingPanel;
    private FrameworkElement? _moveCaptureElement;
    private Windows.Foundation.Point _moveStartPoint;
    private double _moveStartLeft;
    private double _moveStartTop;

    private bool _pendingDragRestoreFromMaximized;
    private double _dragRestorePointerRatioX;

    private FrameworkElement? _resizingPanel;
    private FrameworkElement? _activeResizeHandle;
    private WindowResizeEdge _activeResizeEdge =
        WindowResizeEdge.None;
    private Windows.Foundation.Point _resizeStartPoint;
    private double _resizeStartLeft;
    private double _resizeStartTop;
    private double _resizeStartWidth;
    private double _resizeStartHeight;

    private readonly Dictionary<Guid, SecondaryExplorerWindow>
        _secondaryExplorerWindows =
            new();

    private readonly Dictionary<FrameworkElement, FloatingWindowRestoreState>
        _floatingWindowRestoreStates =
            new();

    private readonly Dictionary<FrameworkElement, Button>
        _floatingWindowMaximizeButtons =
            new();

    private readonly Dictionary<Guid, Button>
        _minimizedSecondaryExplorerButtons =
            new();

    private readonly HashSet<FrameworkElement>
        _minimizedPrimaryPanels =
            new();

    private bool _primaryWindowLayoutsApplied;
    private bool _applyingPrimaryWindowLayouts;

    private WindowSnapTarget _activeWindowSnapTarget =
        WindowSnapTarget.None;

    private string _currentPermissionMode =
        "normal";

    private string _workspaceRoot =
        string.Empty;

    private string _currentDirectory =
        string.Empty;

    private bool _initialized;

    public DesktopWindow()
    {
        InitializeComponent();

        ApplyAtlasWindowIcon();

        _config =
            new AtlasConfigService();

        _displayService =
            new DisplayService();

        _taskbarVisibility =
            new TaskbarVisibilityService();

        _ipc =
            new AtlasIpcServerService();

        _coreProcess =
            new CoreProcessService();

        _startupRegistration =
            new StartupRegistrationService();

        _updateService =
            new AtlasUpdateService();

        _ipc.ConnectionChanged +=
            OnIpcConnectionChanged;

        _ipc.MessageReceived +=
            OnIpcMessageReceived;

        _taskbarGuardTimer =
            new DispatcherTimer
            {
                Interval =
                    TimeSpan.FromSeconds(
                        2),
            };

        _taskbarGuardTimer.Tick +=
            (_, _) =>
            {
                _taskbarVisibility.Refresh();
            };

        _storageWidgetTimer =
            new DispatcherTimer
            {
                Interval =
                    TimeSpan.FromSeconds(
                        10),
            };

        _storageWidgetTimer.Tick +=
            (_, _) =>
            {
                UpdateStorageWidget();
            };

        _updateCheckTimer =
            new DispatcherTimer
            {
                Interval = TimeSpan.FromMinutes(30),
            };

        _updateCheckTimer.Tick +=
            (_, _) => _ = CheckForUpdatesAsync();

        Title =
            "Atlas Desktop";

        _clockTimer =
            new DispatcherTimer
            {
                Interval =
                    TimeSpan.FromSeconds(1),
            };

        _clockTimer.Tick +=
            (_, _) =>
            {
                UpdateClock();
            };

        UpdateClock();
        UpdateStorageWidget();

        _clockTimer.Start();
        _taskbarGuardTimer.Start();
        _storageWidgetTimer.Start();
        _updateCheckTimer.Start();

        Closed +=
            (_, _) =>
            {
                _clockTimer.Stop();
                _taskbarGuardTimer.Stop();
                _storageWidgetTimer.Stop();
                _updateCheckTimer.Stop();

                _taskbarVisibility.Restore();

                _ipc.Dispose();

                _coreProcess.Dispose();

                UiLog.Info(
                    "DesktopWindow closed; Windows taskbar restored.");
            };
    }

    public void InitializeDesktop()
    {
        if (_initialized)
        {
            return;
        }

        _initialized = true;

        ConfigureWindowBounds();

        UpdateAboutSettingsPresentation();
        UpdateSecurityOverviewPresentation();

        DesktopIntegrationService
            .AttachInteractiveDesktop(
                this);

        InitializeFloatingWindowManager();

        UpdateDockWindowStates();

        LoadWidgetPreferences();

        SyncWidgetManagerUi();

        Root.PointerPressed +=
            DesktopRoot_PointerPressed;

        Root.SizeChanged +=
            (_, _) =>
            {
                if (_atlasDisplay is not null)
                {
                    UpdateDockHeightFromDisplay(
                        _atlasDisplay);
                }

                if (
                    _widgetPresetNeedsInitialLayout
                    && Root.ActualWidth > 0
                    && Root.ActualHeight > 0
                )
                {
                    _widgetPresetNeedsInitialLayout =
                        false;

                    ApplyDesktopWidgetPreset(
                        string.Equals(
                            _widgetsLayoutMode,
                            "left",
                            StringComparison.OrdinalIgnoreCase)
                            ? HorizontalAlignment.Left
                            : HorizontalAlignment.Right,
                        save: false);
                }

                if (
                    !_primaryWindowLayoutsApplied
                    && Root.ActualWidth > 0
                    && Root.ActualHeight > 0
                )
                {
                    ApplyPrimaryWindowLayouts();
                }

                ClampAllFloatingWindowsToWorkspace();
                ClampAllDesktopWidgetsToWorkspace();
            };

        var atlasConfig =
            _config.Load();

        _workspaceRoot =
            atlasConfig.StorageRoot;

        _startupRegistration.Apply(
            atlasConfig.StartWithWindows);

        _workspaceFiles =
            new WorkspaceFileService(
                _workspaceRoot);

        _ipc.Start();

        UpdateCoreDockControlUi(
            "Recherche du Core…");

        _ = EnsureCoreStartedAsync();

        UpdateSortIndicators();
        UpdateViewPresentation();

        RestorePrimaryExplorerTabs(
            atlasConfig.PrimaryExplorerTabs,
            atlasConfig.PrimaryExplorerActiveTabIndex);

        LoadSettingsUi();
        _ = CheckForUpdatesAsync();
    }

    private async Task EnsureCoreStartedAsync()
    {
        CoreStatusText.Text =
            "Recherche du Core…";

        var started =
            await _coreProcess
                .EnsureStartedAsync(
                    () =>
                        _ipc.IsConnected,
                    TimeSpan.FromSeconds(
                        1.5));

        if (
            started
            && !_ipc.IsConnected
        )
        {
            CoreStatusText.Text =
                "Démarrage du Core…";
        }
    }

    private void ApplyAtlasWindowIcon()
    {
        try
        {
            var candidates =
                new[]
                {
                    IOPath.Combine(
                        AppContext.BaseDirectory,
                        "Assets",
                        "atlas.ico"),
                    IOPath.Combine(
                        AppContext.BaseDirectory,
                        "assets",
                        "atlas.ico"),
                };

            var iconPath =
                candidates.FirstOrDefault(
                    File.Exists);

            if (
                !string.IsNullOrWhiteSpace(
                    iconPath)
            )
            {
                AppWindow.SetIcon(
                    iconPath);

                UiLog.Info(
                    $"Atlas window icon loaded: {iconPath}");
            }
        }
        catch (Exception exception)
        {
            UiLog.Error(
                "Unable to apply Atlas window icon.",
                exception);
        }
    }

    private void ConfigureWindowBounds()
    {
        // Restore Windows first so rcWork contains the real taskbar
        // reservation before Atlas hides the taskbar on this monitor.
        _taskbarVisibility.Restore();

        var atlasConfig =
            _config.Load();

        var display =
            _displayService.ResolveDisplay(
                atlasConfig.ScreenId,
                atlasConfig.ScreenIndex);

        if (display is null)
        {
            return;
        }

        _atlasDisplay =
            display;

        ExtendsContentIntoTitleBar =
            true;

        if (
            AppWindow.Presenter
            is OverlappedPresenter presenter
        )
        {
            presenter.SetBorderAndTitleBar(
                false,
                false);

            presenter.IsResizable =
                false;

            presenter.IsMaximizable =
                false;

            presenter.IsMinimizable =
                false;
        }

        // Affiche Atlas dans la barre des tâches et dans les sélecteurs de
        // fenêtres Windows, tout en conservant son rendu plein écran.
        AppWindow.IsShownInSwitchers =
            true;

        AppWindow.MoveAndResize(
            display.Bounds);

        UpdateDockHeightFromDisplay(
            display);

        _taskbarVisibility.HideOnMonitor(
            display.Bounds);

        UiLog.Info(
            $"Windows taskbar hidden on Atlas monitor {display.DeviceName}. Atlas dock uses its independent floating layout.");
    }

    private void UpdateDockHeightFromDisplay(
        DisplayDescriptor display)
    {
        // The Atlas dock is intentionally independent from the Windows
        // taskbar. Its visual proportions stay identical on every monitor.
        Dock.Height =
            DockHeightDip;
    }

    private double GetFloatingWorkspaceBottom()
    {
        var dockHeight =
            Dock.ActualHeight > 0
                ? Dock.ActualHeight
                : DockHeightDip;

        return Math.Max(
            0,
            Root.ActualHeight
                - dockHeight
                - DockBottomMarginDip
                - DockWorkspaceGapDip);
    }

    private void ClampFloatingPanelToWorkspace(
        FrameworkElement panel)
    {
        if (
            panel.Visibility
                != Visibility.Visible
            || Root.ActualWidth <= 0
            || Root.ActualHeight <= 0
        )
        {
            return;
        }

        EnsureFloatingPanelUsesAbsolutePosition(
            panel);

        var workspaceBottom =
            GetFloatingWorkspaceBottom();

        var width =
            panel.ActualWidth > 0
                ? panel.ActualWidth
                : panel.Width;

        var height =
            panel.ActualHeight > 0
                ? panel.ActualHeight
                : panel.Height;

        width =
            Math.Min(
                Math.Max(
                    panel.MinWidth,
                    width),
                Math.Max(
                    panel.MinWidth,
                    Root.ActualWidth));

        height =
            Math.Min(
                Math.Max(
                    panel.MinHeight,
                    height),
                Math.Max(
                    panel.MinHeight,
                    workspaceBottom));

        var maxLeft =
            Math.Max(
                0,
                Root.ActualWidth
                    - width);

        var maxTop =
            Math.Max(
                0,
                workspaceBottom
                    - height);

        panel.Width =
            width;

        panel.Height =
            height;

        panel.Margin =
            new Thickness(
                Math.Clamp(
                    panel.Margin.Left,
                    0,
                    maxLeft),
                Math.Clamp(
                    panel.Margin.Top,
                    0,
                    maxTop),
                0,
                0);
    }

    private void ClampAllFloatingWindowsToWorkspace()
    {
        foreach (
            var panel
            in new FrameworkElement[]
            {
                FilesPanel,
                SettingsPanel,
                SystemPanel,
                WidgetManagerPanel,
            })
        {
            ClampFloatingPanelToWorkspace(
                panel);
        }

        foreach (
            var window
            in _secondaryExplorerWindows
                .Values)
        {
            ClampFloatingPanelToWorkspace(
                window.Panel);
        }

    }

    private void LoadSettingsUi()
    {
        _settingsEditingReady =
            false;

        var config =
            _config.Load();

        PopulateDisplaySettings(
            config);

        UpdateStorageSettingsPresentation();

        SettingsStartupToggle.IsOn =
            config.StartWithWindows;

        UpdateStartupRegistrationPresentation();
        UpdateUpdateSettingsPresentation();

        var storageRoot =
            IOPath.GetFullPath(
                config.StorageRoot);

        foreach (
            var item
            in SettingsStorageComboBox
                .Items
                .OfType<ComboBoxItem>())
        {
            if (
                item.Tag is string path
                && string.Equals(
                    IOPath.GetFullPath(
                        path),
                    storageRoot,
                    StringComparison.OrdinalIgnoreCase)
            )
            {
                SettingsStorageComboBox
                    .SelectedItem =
                    item;

                break;
            }
        }

        if (
            SettingsStorageComboBox
                .SelectedItem
            is null
        )
        {
            SettingsStorageComboBox
                .SelectedIndex = 0;
        }

        SyncSecondarySettingsControls();

        UpdateDisplaySettingsPresentation();

        SettingsStatusText.Text =
            string.Empty;

        _settingsEditingReady =
            true;

        ClearSettingsDirtyState();
    }

    private void PopulateDisplaySettings(
        AtlasConfig config)
    {
        SettingsDisplayComboBox
            .Items
            .Clear();

        var displays =
            _displayService
                .EnumerateDisplays();

        var selectedIndex =
            -1;

        for (
            var index = 0;
            index < displays.Count;
            index++
        )
        {
            var display =
                displays[
                    index
                ];

            var item =
                new ComboBoxItem
                {
                    Content =
                        BuildDisplayLabel(
                            display),

                    Tag =
                        display.DeviceName,
                };

            SettingsDisplayComboBox
                .Items
                .Add(
                    item);

            if (
                string.Equals(
                    display.DeviceName,
                    config.ScreenId,
                    StringComparison.OrdinalIgnoreCase)
                || (
                    string.IsNullOrWhiteSpace(
                        config.ScreenId)
                    && index
                        == config.ScreenIndex
                )
            )
            {
                selectedIndex =
                    index;
            }
        }

        if (
            selectedIndex < 0
            && displays.Count > 0
        )
        {
            selectedIndex = 0;
        }

        SettingsDisplayComboBox
            .SelectedIndex =
            selectedIndex;
    }

    private static string BuildDisplayLabel(
        DisplayDescriptor display)
    {
        var displayNumber =
            ExtractWindowsDisplayNumber(
                display.DeviceName);

        var width =
            display.Bounds.Width;

        var height =
            display.Bounds.Height;

        var numberText =
            displayNumber is null
                ? "Écran"
                : $"Écran {displayNumber.Value}";

        var friendlyNameText =
            string.IsNullOrWhiteSpace(
                display.FriendlyName)
                ? string.Empty
                : $" · {display.FriendlyName}";

        var resolutionText =
            width > 0
            && height > 0
                ? $" · {width} × {height}"
                : string.Empty;

        var primaryText =
            display.IsPrimary
                ? " · Principal"
                : string.Empty;

        return
            numberText
            + friendlyNameText
            + resolutionText
            + primaryText;
    }

    private static int? ExtractWindowsDisplayNumber(
        string? deviceName)
    {
        if (string.IsNullOrWhiteSpace(
                deviceName))
        {
            return null;
        }

        const string prefix =
            @"\\.\DISPLAY";

        if (
            !deviceName.StartsWith(
                prefix,
                StringComparison.OrdinalIgnoreCase)
        )
        {
            return null;
        }

        var suffix =
            deviceName[
                prefix.Length..
            ];

        return int.TryParse(
            suffix,
            out var number)
            ? number
            : null;
    }

    private void InitializeFloatingWindowManager()
    {
        AttachFloatingWindowBehavior(
            FilesPanel);

        AttachFloatingWindowBehavior(
            SettingsPanel);

        AttachFloatingWindowBehavior(
            SystemPanel);

        AttachFloatingWindowBehavior(
            WidgetManagerPanel);
    }

    private void AttachFloatingWindowBehavior(
        FrameworkElement panel)
    {
        panel.PointerMoved +=
            FloatingPanel_PointerMoved;

        panel.PointerReleased +=
            FloatingPanel_PointerReleased;

        panel.PointerCaptureLost +=
            FloatingPanel_PointerCaptureLost;

        if (panel is Border border)
        {
            AttachResizeHandles(
                border);
        }
    }

    private void AttachResizeHandles(
        Border panel)
    {
        if (
            panel.Child
            is not Grid host
        )
        {
            return;
        }

        var overlay =
            new Grid
            {
                HorizontalAlignment =
                    HorizontalAlignment.Stretch,
                VerticalAlignment =
                    VerticalAlignment.Stretch,
                IsHitTestVisible =
                    true,
            };

        Grid.SetRowSpan(
            overlay,
            100);

        Grid.SetColumnSpan(
            overlay,
            100);

        Canvas.SetZIndex(
            overlay,
            10000);

        AddResizeHandle(
            overlay,
            panel,
            WindowResizeEdge.Left,
            width: 7,
            height: double.NaN,
            HorizontalAlignment.Left,
            VerticalAlignment.Stretch);

        AddResizeHandle(
            overlay,
            panel,
            WindowResizeEdge.Right,
            width: 7,
            height: double.NaN,
            HorizontalAlignment.Right,
            VerticalAlignment.Stretch);

        AddResizeHandle(
            overlay,
            panel,
            WindowResizeEdge.Top,
            width: double.NaN,
            height: 7,
            HorizontalAlignment.Stretch,
            VerticalAlignment.Top);

        AddResizeHandle(
            overlay,
            panel,
            WindowResizeEdge.Bottom,
            width: double.NaN,
            height: 7,
            HorizontalAlignment.Stretch,
            VerticalAlignment.Bottom);

        AddResizeHandle(
            overlay,
            panel,
            WindowResizeEdge.Left
            | WindowResizeEdge.Top,
            width: 14,
            height: 14,
            HorizontalAlignment.Left,
            VerticalAlignment.Top);

        AddResizeHandle(
            overlay,
            panel,
            WindowResizeEdge.Right
            | WindowResizeEdge.Top,
            width: 14,
            height: 14,
            HorizontalAlignment.Right,
            VerticalAlignment.Top);

        AddResizeHandle(
            overlay,
            panel,
            WindowResizeEdge.Left
            | WindowResizeEdge.Bottom,
            width: 14,
            height: 14,
            HorizontalAlignment.Left,
            VerticalAlignment.Bottom);

        AddResizeHandle(
            overlay,
            panel,
            WindowResizeEdge.Right
            | WindowResizeEdge.Bottom,
            width: 14,
            height: 14,
            HorizontalAlignment.Right,
            VerticalAlignment.Bottom);

        host.Children.Add(
            overlay);
    }

    private static InputCursor CreateResizeCursor(
        WindowResizeEdge edge)
    {
        var shape =
            edge switch
            {
                WindowResizeEdge.Left => InputSystemCursorShape.SizeWestEast,
                WindowResizeEdge.Right => InputSystemCursorShape.SizeWestEast,
                WindowResizeEdge.Top => InputSystemCursorShape.SizeNorthSouth,
                WindowResizeEdge.Bottom => InputSystemCursorShape.SizeNorthSouth,
                WindowResizeEdge.Left
                | WindowResizeEdge.Top => InputSystemCursorShape.SizeNorthwestSoutheast,
                WindowResizeEdge.Right
                | WindowResizeEdge.Bottom => InputSystemCursorShape.SizeNorthwestSoutheast,
                WindowResizeEdge.Right
                | WindowResizeEdge.Top => InputSystemCursorShape.SizeNortheastSouthwest,
                WindowResizeEdge.Left
                | WindowResizeEdge.Bottom => InputSystemCursorShape.SizeNortheastSouthwest,
                _ => InputSystemCursorShape.Arrow,
            };

        return
            InputSystemCursor.Create(
                shape);
    }

    private static void SetElementCursor(
        UIElement element,
        InputCursor cursor)
    {
        var property =
            typeof(UIElement)
                .GetProperty(
                    "ProtectedCursor",
                    System.Reflection.BindingFlags.Instance
                    | System.Reflection.BindingFlags.NonPublic);

        property?.SetValue(
            element,
            cursor);
    }

    private void AddResizeHandle(
        Grid overlay,
        FrameworkElement panel,
        WindowResizeEdge edge,
        double width,
        double height,
        HorizontalAlignment horizontalAlignment,
        VerticalAlignment verticalAlignment)
    {
        var handle =
            new Border
            {
                Width = width,
                Height = height,
                HorizontalAlignment =
                    horizontalAlignment,
                VerticalAlignment =
                    verticalAlignment,
                Background =
                    new SolidColorBrush(
                        Windows.UI.Color.FromArgb(0, 0, 0, 0)),
                Tag =
                    new ResizeHandleContext(
                        panel,
                        edge),
            };

        SetElementCursor(
            handle,
            CreateResizeCursor(
                edge));

        handle.PointerPressed +=
            ResizeHandle_PointerPressed;

        handle.PointerMoved +=
            ResizeHandle_PointerMoved;

        handle.PointerReleased +=
            ResizeHandle_PointerReleased;

        handle.PointerCaptureLost +=
            ResizeHandle_PointerCaptureLost;

        overlay.Children.Add(
            handle);
    }

    private void FloatingPanel_DoubleTapped(
        object sender,
        DoubleTappedRoutedEventArgs e)
    {
        if (
            sender is not FrameworkElement panel
            || IsInteractiveWindowSource(
                e.OriginalSource
                    as DependencyObject,
                panel)
        )
        {
            return;
        }

        var position =
            e.GetPosition(
                panel);

        if (position.Y > 64)
        {
            return;
        }

        var maximizeButton =
            ResolveFloatingWindowMaximizeButton(
                panel);

        if (maximizeButton is null)
        {
            return;
        }

        ToggleFloatingWindowMaximize(
            panel,
            maximizeButton);

        e.Handled =
            true;
    }

    private void FloatingPanel_PointerPressed(
        object sender,
        PointerRoutedEventArgs e)
    {
        if (
            sender
            is not FrameworkElement panel
        )
        {
            return;
        }

        BringFloatingWindowToFront(
            panel);

        if (
            IsPointerOverResizeHandle(
                e.OriginalSource
                as DependencyObject)
            || IsInteractiveWindowSource(
                e.OriginalSource
                as DependencyObject,
                panel)
        )
        {
            return;
        }

        var panelPoint =
            e.GetCurrentPoint(
                panel);

        if (
            !panelPoint.Properties
                .IsLeftButtonPressed
            || panelPoint.Position.Y
                > 64
        )
        {
            return;
        }

        EnsureFloatingPanelUsesAbsolutePosition(
            panel);

        _movingPanel =
            panel;

        _moveCaptureElement =
            panel;

        _moveStartPoint =
            e.GetCurrentPoint(
                Root)
                .Position;

        _moveStartLeft =
            panel.Margin.Left;

        _moveStartTop =
            panel.Margin.Top;

        _pendingDragRestoreFromMaximized =
            _floatingWindowRestoreStates.ContainsKey(
                panel);

        if (_pendingDragRestoreFromMaximized)
        {
            var panelWidth =
                Math.Max(
                    1,
                    panel.ActualWidth);

            _dragRestorePointerRatioX =
                Math.Clamp(
                    panelPoint.Position.X
                    / panelWidth,
                    0.08,
                    0.92);
        }

        panel.CapturePointer(
            e.Pointer);

        e.Handled =
            true;
    }

    private void FloatingPanel_PointerMoved(
        object sender,
        PointerRoutedEventArgs e)
    {
        if (
            _movingPanel is null
            || !ReferenceEquals(
                sender,
                _movingPanel)
        )
        {
            return;
        }

        var point =
            e.GetCurrentPoint(
                Root);

        if (
            !point.Properties
                .IsLeftButtonPressed
        )
        {
            EndPanelMove(
                e);

            return;
        }

        var deltaX =
            point.Position.X
            - _moveStartPoint.X;

        var deltaY =
            point.Position.Y
            - _moveStartPoint.Y;

        if (
            _pendingDragRestoreFromMaximized
            && (
                Math.Abs(
                    deltaX)
                    >= 5
                || Math.Abs(
                    deltaY)
                    >= 5
            )
        )
        {
            RestoreMaximizedPanelForDrag(
                _movingPanel,
                point.Position);

            _pendingDragRestoreFromMaximized =
                false;

            _moveStartPoint =
                point.Position;

            _moveStartLeft =
                _movingPanel.Margin.Left;

            _moveStartTop =
                _movingPanel.Margin.Top;

            deltaX =
                0;

            deltaY =
                0;
        }

        var width =
            Math.Max(
                1,
                _movingPanel.ActualWidth);

        var height =
            Math.Max(
                1,
                _movingPanel.ActualHeight);

        var maxLeft =
            Math.Max(
                0,
                Root.ActualWidth
                - width);

        var maxTop =
            Math.Max(
                0,
                GetFloatingWorkspaceBottom()
                - height);

        var left =
            Math.Clamp(
                _moveStartLeft
                + deltaX,
                0,
                maxLeft);

        var top =
            Math.Clamp(
                _moveStartTop
                + deltaY,
                0,
                maxTop);

        _movingPanel.Margin =
            new Thickness(
                left,
                top,
                0,
                0);

        UpdateWindowSnapPreview(
            _movingPanel);

        e.Handled =
            true;
    }

    private void FloatingPanel_PointerReleased(
        object sender,
        PointerRoutedEventArgs e)
    {
        if (
            _movingPanel is null
            || !ReferenceEquals(
                sender,
                _movingPanel)
        )
        {
            return;
        }

        EndPanelMove(
            e);

        e.Handled =
            true;
    }

    private void FloatingPanel_PointerCaptureLost(
        object sender,
        PointerRoutedEventArgs e)
    {
        if (
            _movingPanel is not null
            && ReferenceEquals(
                sender,
                _movingPanel)
        )
        {
            _movingPanel =
                null;

            _moveCaptureElement =
                null;

            _pendingDragRestoreFromMaximized =
                false;

            HideWindowSnapPreview();
        }
    }

    private void EndPanelMove(
        PointerRoutedEventArgs e)
    {
        var movedPanel =
            _movingPanel;

        var capture =
            _moveCaptureElement
            as UIElement;

        var snapTarget =
            _activeWindowSnapTarget;

        _movingPanel =
            null;

        _moveCaptureElement =
            null;

        _pendingDragRestoreFromMaximized =
            false;

        HideWindowSnapPreview();

        if (capture is not null)
        {
            capture.ReleasePointerCapture(
                e.Pointer);
        }

        if (movedPanel is not null)
        {
            ApplyFloatingWindowSnap(
                movedPanel,
                snapTarget);

            SavePrimaryWindowLayouts();
            SaveSecondaryExplorerLayouts();
        }
    }

    private void RestoreMaximizedPanelForDrag(
        FrameworkElement panel,
        Windows.Foundation.Point pointerPosition)
    {
        if (
            !_floatingWindowRestoreStates.TryGetValue(
                panel,
                out var restoreState)
        )
        {
            return;
        }

        _floatingWindowRestoreStates.Remove(
            panel);

        if (
            _floatingWindowMaximizeButtons.TryGetValue(
                panel,
                out var maximizeButton)
        )
        {
            UpdateMaximizeButtonVisual(
                maximizeButton,
                false);

            _floatingWindowMaximizeButtons.Remove(
                panel);
        }

        EnsureFloatingPanelUsesAbsolutePosition(
            panel);

        panel.Width =
            restoreState.Width;

        panel.Height =
            restoreState.Height;

        var workspaceWidth =
            Math.Max(
                1,
                Root.ActualWidth);

        var workspaceBottom =
            Math.Max(
                1,
                GetFloatingWorkspaceBottom());

        var targetLeft =
            pointerPosition.X
            - panel.Width
            * _dragRestorePointerRatioX;

        var targetTop =
            pointerPosition.Y
            - 24;

        targetLeft =
            Math.Clamp(
                targetLeft,
                8,
                Math.Max(
                    8,
                    workspaceWidth
                    - panel.Width
                    - 8));

        targetTop =
            Math.Clamp(
                targetTop,
                8,
                Math.Max(
                    8,
                    workspaceBottom
                    - panel.Height
                    - 8));

        panel.Margin =
            new Thickness(
                targetLeft,
                targetTop,
                0,
                0);

        BringFloatingWindowToFront(
            panel);
    }

    private void ApplyFloatingWindowSnap(
        FrameworkElement panel,
        WindowSnapTarget? forcedTarget = null)
    {
        if (
            Root.ActualWidth <= 0
            || Root.ActualHeight <= 0
            || panel.Visibility
                != Visibility.Visible
            || _floatingWindowRestoreStates.ContainsKey(
                panel)
        )
        {
            return;
        }

        var target =
            forcedTarget
            ?? GetWindowSnapTarget(
                panel);

        switch (target)
        {
            case WindowSnapTarget.Maximize:
                var maximizeButton =
                    ResolveFloatingWindowMaximizeButton(
                        panel);

                if (maximizeButton is not null)
                {
                    ToggleFloatingWindowMaximize(
                        panel,
                        maximizeButton);
                }

                break;

            case WindowSnapTarget.Left:
                SnapFloatingWindowToHalf(
                    panel,
                    leftSide: true);
                break;

            case WindowSnapTarget.Right:
                SnapFloatingWindowToHalf(
                    panel,
                    leftSide: false);
                break;
        }
    }

    private WindowSnapTarget GetWindowSnapTarget(
        FrameworkElement panel)
    {
        const double snapThreshold =
            12.0;

        var left =
            panel.Margin.Left;

        var top =
            panel.Margin.Top;

        var width =
            Math.Max(
                1,
                panel.ActualWidth);

        var right =
            left
            + width;

        if (top <= snapThreshold)
        {
            return WindowSnapTarget.Maximize;
        }

        if (left <= snapThreshold)
        {
            return WindowSnapTarget.Left;
        }

        if (
            Root.ActualWidth
            - right
            <= snapThreshold
        )
        {
            return WindowSnapTarget.Right;
        }

        return WindowSnapTarget.None;
    }

    private void UpdateWindowSnapPreview(
        FrameworkElement? panel)
    {
        if (
            panel is null
            || Root.ActualWidth <= 0
            || Root.ActualHeight <= 0
            || _floatingWindowRestoreStates.ContainsKey(
                panel)
        )
        {
            HideWindowSnapPreview();
            return;
        }

        var target =
            GetWindowSnapTarget(
                panel);

        if (target == WindowSnapTarget.None)
        {
            HideWindowSnapPreview();
            return;
        }

        _activeWindowSnapTarget =
            target;

        const double outerMargin =
            14.0;

        const double centerGap =
            7.0;

        var workspaceWidth =
            Math.Max(
                1,
                Root.ActualWidth);

        var workspaceBottom =
            Math.Max(
                1,
                GetFloatingWorkspaceBottom());

        double left;
        double top;
        double width;
        double height;

        if (target == WindowSnapTarget.Maximize)
        {
            left = outerMargin;
            top = outerMargin;

            width =
                Math.Max(
                    1,
                    workspaceWidth
                    - outerMargin * 2);

            height =
                Math.Max(
                    1,
                    workspaceBottom
                    - outerMargin * 2);
        }
        else
        {
            var availableWidth =
                Math.Max(
                    1,
                    workspaceWidth
                    - outerMargin * 2
                    - centerGap);

            width =
                availableWidth
                / 2.0;

            height =
                Math.Max(
                    1,
                    workspaceBottom
                    - outerMargin * 2);

            top =
                outerMargin;

            left =
                target == WindowSnapTarget.Left
                    ? outerMargin
                    : Math.Max(
                        outerMargin,
                        workspaceWidth
                        - outerMargin
                        - width);
        }

        WindowSnapPreview.Width =
            width;

        WindowSnapPreview.Height =
            height;

        WindowSnapPreview.Margin =
            new Thickness(
                left,
                top,
                0,
                0);

        WindowSnapPreview.Visibility =
            Visibility.Visible;
    }

    private void HideWindowSnapPreview()
    {
        _activeWindowSnapTarget =
            WindowSnapTarget.None;

        WindowSnapPreview.Visibility =
            Visibility.Collapsed;
    }

    private void SnapFloatingWindowToHalf(
        FrameworkElement panel,
        bool leftSide)
    {
        EnsureFloatingPanelUsesAbsolutePosition(
            panel);

        const double outerMargin =
            14.0;

        const double centerGap =
            7.0;

        var workspaceWidth =
            Math.Max(
                1,
                Root.ActualWidth);

        var workspaceBottom =
            Math.Max(
                1,
                GetFloatingWorkspaceBottom());

        var availableWidth =
            Math.Max(
                panel.MinWidth,
                workspaceWidth
                - (
                    outerMargin
                    * 2)
                - centerGap);

        var halfWidth =
            Math.Max(
                panel.MinWidth,
                availableWidth
                / 2.0);

        var targetHeight =
            Math.Max(
                panel.MinHeight,
                workspaceBottom
                - (
                    outerMargin
                    * 2));

        var targetLeft =
            leftSide
                ? outerMargin
                : Math.Max(
                    outerMargin,
                    workspaceWidth
                    - outerMargin
                    - halfWidth);

        panel.HorizontalAlignment =
            HorizontalAlignment.Left;

        panel.VerticalAlignment =
            VerticalAlignment.Top;

        panel.Width =
            halfWidth;

        panel.Height =
            targetHeight;

        panel.Margin =
            new Thickness(
                targetLeft,
                outerMargin,
                0,
                0);

        BringFloatingWindowToFront(
            panel);
    }

    private Button? ResolveFloatingWindowMaximizeButton(
        FrameworkElement panel)
    {
        if (ReferenceEquals(
                panel,
                FilesPanel))
        {
            return FilesMaximizeButton;
        }

        if (ReferenceEquals(
                panel,
                SettingsPanel))
        {
            return SettingsMaximizeButton;
        }

        if (ReferenceEquals(
                panel,
                WidgetManagerPanel))
        {
            return WidgetsMaximizeButton;
        }

        foreach (
            var window
            in _secondaryExplorerWindows.Values)
        {
            if (ReferenceEquals(
                    window.Panel,
                    panel))
            {
                return window.MaximizeButton;
            }
        }

        return null;
    }

    private static bool IsPointerOverResizeHandle(
        DependencyObject? source)
    {
        var current =
            source;

        while (current is not null)
        {
            if (
                current
                is FrameworkElement element
                && element.Tag
                    is ResizeHandleContext
            )
            {
                return true;
            }

            current =
                VisualTreeHelper.GetParent(
                    current);
        }

        return false;
    }

    private static bool IsInteractiveWindowSource(
        DependencyObject? source,
        FrameworkElement panel)
    {
        var current =
            source;

        while (
            current is not null
            && current != panel
        )
        {
            if (
                current is Button
                || current is TextBox
                || current is ComboBox
                || current is ToggleSwitch
                || current is Slider
                || current is Microsoft.UI.Xaml.Controls.Primitives.ScrollBar
            )
            {
                return true;
            }

            current =
                VisualTreeHelper.GetParent(
                    current);
        }

        return false;
    }

    private void BringFloatingWindowToFront(
        FrameworkElement panel)
    {
        _floatingWindowZIndex++;

        Canvas.SetZIndex(
            panel,
            _floatingWindowZIndex);

        if (
            ReferenceEquals(
                panel,
                FilesPanel)
            || ReferenceEquals(
                panel,
                SettingsPanel)
            || ReferenceEquals(
                panel,
                WidgetManagerPanel)
        )
        {
            UpdateDockWindowStates();
        }
    }

    private void DesktopRoot_PointerPressed(
        object sender,
        PointerRoutedEventArgs e)
    {
        var source =
            e.OriginalSource
            as DependencyObject;

        if (
            IsPointerInsideAtlasForegroundUi(
                source)
        )
        {
            return;
        }

    }

    private bool IsPointerInsideAtlasForegroundUi(
        DependencyObject? source)
    {
        var current =
            source;

        while (current is not null)
        {
            if (
                ReferenceEquals(
                    current,
                    Dock)
                || ReferenceEquals(
                    current,
                    FilesPanel)
                || ReferenceEquals(
                    current,
                    SettingsPanel)
                || ReferenceEquals(
                    current,
                    SystemPanel)
                || ReferenceEquals(
                    current,
                    WidgetManagerPanel)
            )
            {
                return true;
            }

            foreach (
                var secondaryWindow
                in _secondaryExplorerWindows
                    .Values
            )
            {
                if (
                    ReferenceEquals(
                        current,
                        secondaryWindow.Panel)
                )
                {
                    return true;
                }
            }

            current =
                VisualTreeHelper.GetParent(
                    current);
        }

        return false;
    }

    private FrameworkElement? ResolveFloatingPanel(
        string? panelName)
    {
        return panelName switch
        {
            "FilesPanel" => FilesPanel,
            "SettingsPanel" => SettingsPanel,
            "SystemPanel" => SystemPanel,
            "WidgetManagerPanel" => WidgetManagerPanel,
            _ => null,
        };
    }

    private void EnsureFloatingPanelUsesAbsolutePosition(
        FrameworkElement panel)
    {
        if (
            panel.HorizontalAlignment
                == HorizontalAlignment.Left
            && panel.VerticalAlignment
                == VerticalAlignment.Top
        )
        {
            return;
        }

        var transform =
            panel.TransformToVisual(
                Root);

        var origin =
            transform.TransformPoint(
                new Windows.Foundation.Point(
                    0,
                    0));

        panel.HorizontalAlignment =
            HorizontalAlignment.Left;

        panel.VerticalAlignment =
            VerticalAlignment.Top;

        panel.Margin =
            new Thickness(
                origin.X,
                origin.Y,
                0,
                0);
    }

    private void ResizeHandle_PointerPressed(
        object sender,
        PointerRoutedEventArgs e)
    {
        if (
            sender
            is not FrameworkElement handle
            || handle.Tag
                is not ResizeHandleContext context
        )
        {
            return;
        }

        var point =
            e.GetCurrentPoint(
                Root);

        if (
            !point.Properties
                .IsLeftButtonPressed
        )
        {
            return;
        }

        var panel =
            context.Panel;

        BringFloatingWindowToFront(
            panel);

        EnsureFloatingPanelUsesAbsolutePosition(
            panel);

        _resizingPanel =
            panel;

        _activeResizeHandle =
            handle;

        _activeResizeEdge =
            context.Edge;

        _resizeStartPoint =
            point.Position;

        _resizeStartLeft =
            panel.Margin.Left;

        _resizeStartTop =
            panel.Margin.Top;

        _resizeStartWidth =
            panel.ActualWidth;

        _resizeStartHeight =
            panel.ActualHeight;

        handle.CapturePointer(
            e.Pointer);

        e.Handled =
            true;
    }

    private void ResizeHandle_PointerMoved(
        object sender,
        PointerRoutedEventArgs e)
    {
        if (
            _resizingPanel is null
            || _activeResizeHandle is null
            || !ReferenceEquals(
                sender,
                _activeResizeHandle)
        )
        {
            return;
        }

        var point =
            e.GetCurrentPoint(
                Root);

        if (
            !point.Properties
                .IsLeftButtonPressed
        )
        {
            EndResize(
                e);

            return;
        }

        var deltaX =
            point.Position.X
            - _resizeStartPoint.X;

        var deltaY =
            point.Position.Y
            - _resizeStartPoint.Y;

        var left =
            _resizeStartLeft;

        var top =
            _resizeStartTop;

        var width =
            _resizeStartWidth;

        var height =
            _resizeStartHeight;

        var minWidth =
            Math.Max(
                320,
                _resizingPanel.MinWidth);

        var minHeight =
            Math.Max(
                220,
                _resizingPanel.MinHeight);

        var startRight =
            _resizeStartLeft
            + _resizeStartWidth;

        var startBottom =
            _resizeStartTop
            + _resizeStartHeight;

        if (
            _activeResizeEdge
                .HasFlag(
                    WindowResizeEdge.Left)
        )
        {
            left =
                Math.Clamp(
                    _resizeStartLeft
                    + deltaX,
                    0,
                    startRight
                    - minWidth);

            width =
                startRight
                - left;
        }

        if (
            _activeResizeEdge
                .HasFlag(
                    WindowResizeEdge.Right)
        )
        {
            width =
                Math.Clamp(
                    _resizeStartWidth
                    + deltaX,
                    minWidth,
                    Math.Max(
                        minWidth,
                        Root.ActualWidth
                        - _resizeStartLeft));
        }

        if (
            _activeResizeEdge
                .HasFlag(
                    WindowResizeEdge.Top)
        )
        {
            top =
                Math.Clamp(
                    _resizeStartTop
                    + deltaY,
                    0,
                    startBottom
                    - minHeight);

            height =
                startBottom
                - top;
        }

        if (
            _activeResizeEdge
                .HasFlag(
                    WindowResizeEdge.Bottom)
        )
        {
            height =
                Math.Clamp(
                    _resizeStartHeight
                    + deltaY,
                    minHeight,
                    Math.Max(
                        minHeight,
                        GetFloatingWorkspaceBottom()
                        - _resizeStartTop));
        }

        _resizingPanel.Margin =
            new Thickness(
                left,
                top,
                0,
                0);

        _resizingPanel.Width =
            width;

        _resizingPanel.Height =
            height;

        e.Handled =
            true;
    }

    private void ResizeHandle_PointerReleased(
        object sender,
        PointerRoutedEventArgs e)
    {
        if (
            _activeResizeHandle is null
            || !ReferenceEquals(
                sender,
                _activeResizeHandle)
        )
        {
            return;
        }

        EndResize(
            e);

        e.Handled =
            true;
    }

    private void ResizeHandle_PointerCaptureLost(
        object sender,
        PointerRoutedEventArgs e)
    {
        if (
            _activeResizeHandle is not null
            && ReferenceEquals(
                sender,
                _activeResizeHandle)
        )
        {
            _resizingPanel =
                null;

            _activeResizeHandle =
                null;

            _activeResizeEdge =
                WindowResizeEdge.None;
        }
    }

    private void EndResize(
        PointerRoutedEventArgs e)
    {
        if (
            _activeResizeHandle
            is UIElement capture
        )
        {
            capture.ReleasePointerCapture(
                e.Pointer);
        }

        var resizedPanel =
            _resizingPanel;

        _resizingPanel =
            null;

        _activeResizeHandle =
            null;

        _activeResizeEdge =
            WindowResizeEdge.None;

        if (resizedPanel is not null)
        {
            SavePrimaryWindowLayouts();
            SaveSecondaryExplorerLayouts();
        }
    }

    private void ApplyPrimaryWindowLayouts()
    {
        if (_primaryWindowLayoutsApplied)
        {
            return;
        }

        _primaryWindowLayoutsApplied = true;
        _applyingPrimaryWindowLayouts = true;

        try
        {
            var config = _config.Load();

            ApplyPrimaryWindowLayout(
                FilesPanel,
                config.FilesWindowX,
                config.FilesWindowY,
                config.FilesWindowWidth,
                config.FilesWindowHeight);

            ApplyPrimaryWindowLayout(
                SettingsPanel,
                config.SettingsWindowX,
                config.SettingsWindowY,
                config.SettingsWindowWidth,
                config.SettingsWindowHeight);

            ApplyPrimaryWindowLayout(
                WidgetManagerPanel,
                config.WidgetsWindowX,
                config.WidgetsWindowY,
                config.WidgetsWindowWidth,
                config.WidgetsWindowHeight);

            if (config.FilesWindowMaximized)
            {
                ToggleFloatingWindowMaximize(
                    FilesPanel,
                    FilesMaximizeButton);
            }

            if (config.SettingsWindowMaximized)
            {
                ToggleFloatingWindowMaximize(
                    SettingsPanel,
                    SettingsMaximizeButton);
            }

            if (config.WidgetsWindowMaximized)
            {
                ToggleFloatingWindowMaximize(
                    WidgetManagerPanel,
                    WidgetsMaximizeButton);
            }

            RestorePrimaryWindowSessionState(
                FilesPanel,
                config.FilesWindowState);

            RestorePrimaryWindowSessionState(
                SettingsPanel,
                config.SettingsWindowState);

            RestorePrimaryWindowSessionState(
                WidgetManagerPanel,
                config.WidgetsWindowState);

            RestoreSecondaryExplorerWindows(
                config.SecondaryExplorerWindows);
        }
        finally
        {
            _applyingPrimaryWindowLayouts = false;
        }
    }

    private void RestorePrimaryWindowSessionState(
        FrameworkElement panel,
        string state)
    {
        switch (
            state.Trim()
                .ToLowerInvariant())
        {
            case "open":
                _minimizedPrimaryPanels.Remove(
                    panel);

                panel.Visibility =
                    Visibility.Visible;

                BringFloatingWindowToFront(
                    panel);

                break;

            case "minimized":
                panel.Visibility =
                    Visibility.Collapsed;

                _minimizedPrimaryPanels.Add(
                    panel);

                break;

            default:
                panel.Visibility =
                    Visibility.Collapsed;

                _minimizedPrimaryPanels.Remove(
                    panel);

                break;
        }

        UpdateDockWindowStates();
    }

    private void ApplyPrimaryWindowLayout(
        FrameworkElement panel,
        int x,
        int y,
        int width,
        int height)
    {
        if (
            x < 0
            || y < 0
            || width <= 0
            || height <= 0
        )
        {
            return;
        }

        EnsureFloatingPanelUsesAbsolutePosition(
            panel);

        panel.Width = width;
        panel.Height = height;

        panel.Margin =
            new Thickness(
                x,
                y,
                0,
                0);

        ClampFloatingPanelToWorkspace(
            panel);
    }

    private void SavePrimaryWindowLayouts()
    {
        if (
            _applyingPrimaryWindowLayouts
            || !_primaryWindowLayoutsApplied
        )
        {
            return;
        }

        try
        {
            var config = _config.Load();

            var updated =
                config with
                {
                    FilesWindowX = GetPrimaryWindowCoordinate(FilesPanel, true),
                    FilesWindowY = GetPrimaryWindowCoordinate(FilesPanel, false),
                    FilesWindowWidth = GetPrimaryWindowSize(FilesPanel, true),
                    FilesWindowHeight = GetPrimaryWindowSize(FilesPanel, false),
                    FilesWindowMaximized =
                        _floatingWindowRestoreStates.ContainsKey(FilesPanel),
                    FilesWindowState =
                        GetPrimaryWindowSessionState(FilesPanel),

                    SettingsWindowX = GetPrimaryWindowCoordinate(SettingsPanel, true),
                    SettingsWindowY = GetPrimaryWindowCoordinate(SettingsPanel, false),
                    SettingsWindowWidth = GetPrimaryWindowSize(SettingsPanel, true),
                    SettingsWindowHeight = GetPrimaryWindowSize(SettingsPanel, false),
                    SettingsWindowMaximized =
                        _floatingWindowRestoreStates.ContainsKey(SettingsPanel),
                    SettingsWindowState =
                        GetPrimaryWindowSessionState(SettingsPanel),

                    WidgetsWindowX = GetPrimaryWindowCoordinate(WidgetManagerPanel, true),
                    WidgetsWindowY = GetPrimaryWindowCoordinate(WidgetManagerPanel, false),
                    WidgetsWindowWidth = GetPrimaryWindowSize(WidgetManagerPanel, true),
                    WidgetsWindowHeight = GetPrimaryWindowSize(WidgetManagerPanel, false),
                    WidgetsWindowMaximized =
                        _floatingWindowRestoreStates.ContainsKey(WidgetManagerPanel),
                    WidgetsWindowState =
                        GetPrimaryWindowSessionState(WidgetManagerPanel),
                };

            _config.Save(updated);
        }
        catch (Exception exception)
        {
            UiLog.Error(
                "Unable to save primary Atlas window layouts.",
                exception);
        }
    }

    private string GetPrimaryWindowSessionState(
        FrameworkElement panel)
    {
        if (_minimizedPrimaryPanels.Contains(
                panel))
        {
            return "minimized";
        }

        return panel.Visibility
            == Visibility.Visible
                ? "open"
                : "closed";
    }

    private int GetPrimaryWindowCoordinate(
        FrameworkElement panel,
        bool horizontal)
    {
        if (
            _floatingWindowRestoreStates.TryGetValue(
                panel,
                out var restoreState)
        )
        {
            return Math.Max(
                0,
                (int)Math.Round(
                    horizontal
                        ? restoreState.Margin.Left
                        : restoreState.Margin.Top));
        }

        return Math.Max(
            0,
            (int)Math.Round(
                horizontal
                    ? panel.Margin.Left
                    : panel.Margin.Top));
    }

    private int GetPrimaryWindowSize(
        FrameworkElement panel,
        bool horizontal)
    {
        if (
            _floatingWindowRestoreStates.TryGetValue(
                panel,
                out var restoreState)
        )
        {
            return Math.Max(
                1,
                (int)Math.Round(
                    horizontal
                        ? restoreState.Width
                        : restoreState.Height));
        }

        var value =
            horizontal
                ? panel.Width
                : panel.Height;

        if (
            double.IsNaN(value)
            || value <= 0
        )
        {
            value =
                horizontal
                    ? panel.ActualWidth
                    : panel.ActualHeight;
        }

        return Math.Max(
            1,
            (int)Math.Round(value));
    }

    private void MinimizeFloatingPanel_Click(
        object sender,
        RoutedEventArgs e)
    {
        if (
            sender is not Button button
            || button.Tag is not string panelName
        )
        {
            return;
        }

        var panel =
            ResolveFloatingPanel(
                panelName);

        if (panel is null)
        {
            return;
        }

        panel.Visibility =
            Visibility.Collapsed;


        if (
            ReferenceEquals(
                panel,
                FilesPanel)
            || ReferenceEquals(
                panel,
                SettingsPanel)
            || ReferenceEquals(
                panel,
                WidgetManagerPanel)
        )
        {
            _minimizedPrimaryPanels.Add(
                panel);

            UpdateDockWindowStates();
            SavePrimaryWindowLayouts();
        }
    }

    private void ToggleMaximizeFloatingPanel_Click(
        object sender,
        RoutedEventArgs e)
    {
        if (
            sender is not Button button
            || button.Tag is not string panelName
        )
        {
            return;
        }

        var panel =
            ResolveFloatingPanel(
                panelName);

        if (panel is null)
        {
            return;
        }

        ToggleFloatingWindowMaximize(
            panel,
            button);
    }

    private void ToggleFloatingWindowMaximize(
        FrameworkElement panel,
        Button? maximizeButton = null)
    {
        if (
            _floatingWindowRestoreStates.TryGetValue(
                panel,
                out var restoreState)
        )
        {
            panel.Width = restoreState.Width;
            panel.Height = restoreState.Height;
            panel.Margin = restoreState.Margin;
            panel.HorizontalAlignment = restoreState.HorizontalAlignment;
            panel.VerticalAlignment = restoreState.VerticalAlignment;

            _floatingWindowRestoreStates.Remove(panel);

            UpdateMaximizeButtonVisual(
                maximizeButton,
                false);

            if (
                _floatingWindowMaximizeButtons.TryGetValue(
                    panel,
                    out var rememberedButton)
            )
            {
                UpdateMaximizeButtonVisual(
                    rememberedButton,
                    false);

                _floatingWindowMaximizeButtons.Remove(
                    panel);
            }

            SavePrimaryWindowLayouts();
            SaveSecondaryExplorerLayouts();

            return;
        }

        EnsureFloatingPanelUsesAbsolutePosition(
            panel);

        _floatingWindowRestoreStates[panel] =
            new FloatingWindowRestoreState(
                panel.ActualWidth,
                panel.ActualHeight,
                panel.Margin,
                panel.HorizontalAlignment,
                panel.VerticalAlignment);

        if (maximizeButton is not null)
        {
            _floatingWindowMaximizeButtons[panel] =
                maximizeButton;
        }

        var outerMargin = 14.0;

        var workspaceBottom =
            GetFloatingWorkspaceBottom();

        panel.HorizontalAlignment =
            HorizontalAlignment.Left;

        panel.VerticalAlignment =
            VerticalAlignment.Top;

        panel.Margin =
            new Thickness(
                outerMargin,
                outerMargin,
                0,
                0);

        panel.Width =
            Math.Max(
                panel.MinWidth,
                Root.ActualWidth
                - (
                    outerMargin
                    * 2));

        panel.Height =
            Math.Max(
                panel.MinHeight,
                workspaceBottom
                - (
                    outerMargin
                    * 2));

        BringFloatingWindowToFront(
            panel);

        UpdateMaximizeButtonVisual(
            maximizeButton,
            true);

        SavePrimaryWindowLayouts();
        SaveSecondaryExplorerLayouts();
    }

    private static void UpdateMaximizeButtonVisual(
        Button? button,
        bool maximized)
    {
        if (button is null)
        {
            return;
        }

        if (
            button.Content
            is FontIcon icon
        )
        {
            icon.Glyph =
                maximized
                    ? "\uE923"
                    : "\uE922";
        }

        ToolTipService.SetToolTip(
            button,
            maximized
                ? "Restaurer"
                : "Agrandir");
    }

    private void MinimizeSecondaryExplorerWindow(
        SecondaryExplorerWindow window)
    {
        if (
            _minimizedSecondaryExplorerButtons.ContainsKey(
                window.Id)
        )
        {
            return;
        }

        window.Panel.Visibility =
            Visibility.Collapsed;


        var button =
            new Button
            {
                Width = 46,
                Height = 46,
                Padding = new Thickness(0),
                Background = CreateBrush("#2B182331"),
                BorderBrush = CreateBrush("#34719EC2"),
                BorderThickness = new Thickness(1),
                CornerRadius = new CornerRadius(15),
                Content =
                    new FontIcon
                    {
                        Glyph = "\uE8B7",
                        FontSize = 17,
                        Foreground =
                            CreateBrush("#EAF7FF"),
                    },
            };

        ToolTipService.SetToolTip(
            button,
            window.DisplayTitle);

        button.Click +=
            (_, _) =>
            {
                RestoreSecondaryExplorerWindow(
                    window);
            };

        _minimizedSecondaryExplorerButtons[window.Id] =
            button;

        MinimizedWindowsHost.Children.Add(
            button);

        SaveSecondaryExplorerLayouts();
    }

    private void RestoreSecondaryExplorerWindow(
        SecondaryExplorerWindow window)
    {
        if (
            _minimizedSecondaryExplorerButtons.Remove(
                window.Id,
                out var button)
        )
        {
            MinimizedWindowsHost.Children.Remove(
                button);
        }

        window.Panel.Visibility =
            Visibility.Visible;

        BringFloatingWindowToFront(
            window.Panel);

        SaveSecondaryExplorerLayouts();
    }

    private bool RestorePrimaryPanelIfMinimized(
        FrameworkElement panel)
    {
        if (
            !_minimizedPrimaryPanels.Remove(
                panel)
        )
        {
            return false;
        }

        panel.Visibility =
            Visibility.Visible;

        BringFloatingWindowToFront(
            panel);

        UpdateDockWindowStates();
        SavePrimaryWindowLayouts();

        return true;
    }

    private void UpdateDockWindowStates()
    {
        ApplyDockWindowState(
            DockFilesButton,
            DockFilesStateDot,
            FilesPanel);

        ApplyDockWindowState(
            DockWidgetsButton,
            DockWidgetsStateDot,
            WidgetManagerPanel);

        ApplyDockWindowState(
            DockSettingsButton,
            DockSettingsStateDot,
            SettingsPanel);
    }

    private void ApplyDockWindowState(
        Button button,
        Ellipse dot,
        FrameworkElement panel)
    {
        var minimized =
            _minimizedPrimaryPanels.Contains(
                panel);

        var visible =
            panel.Visibility
                == Visibility.Visible;

        if (minimized)
        {
            button.Background =
                CreateBrush(
                    "#392B2A23");

            button.BorderBrush =
                CreateBrush(
                    "#6A9A7A42");

            dot.Fill =
                CreateBrush(
                    "#F1C76E");

            dot.Visibility =
                Visibility.Visible;

            return;
        }

        if (visible)
        {
            button.Background =
                CreateBrush(
                    "#43152E43");

            button.BorderBrush =
                CreateBrush(
                    "#596CDFFF");

            dot.Fill =
                CreateBrush(
                    "#67D9FF");

            dot.Visibility =
                Visibility.Visible;

            return;
        }

        button.Background =
            CreateBrush(
                "#2B182331");

        button.BorderBrush =
            CreateBrush(
                "#34719EC2");

        dot.Visibility =
            Visibility.Collapsed;
    }

    private void ShowFloatingPanel(
        FrameworkElement panel)
    {
        _minimizedPrimaryPanels.Remove(
            panel);

        panel.Visibility =
            Visibility.Visible;

        BringFloatingWindowToFront(
            panel);

        UpdateDockWindowStates();
    }

    private void ToggleFloatingPanel(
        FrameworkElement panel)
    {
        if (
            panel.Visibility
            == Visibility.Visible
        )
        {
            panel.Visibility =
                Visibility.Collapsed;

            _minimizedPrimaryPanels.Remove(
                panel);

            UpdateDockWindowStates();
            SavePrimaryWindowLayouts();

            return;
        }

        ShowFloatingPanel(
            panel);

        SavePrimaryWindowLayouts();
    }

    private void ForgetFloatingWindowState(
        FrameworkElement panel)
    {
        _floatingWindowRestoreStates.Remove(
            panel);

        _floatingWindowMaximizeButtons.Remove(
            panel);

        _minimizedPrimaryPanels.Remove(
            panel);

        UpdateDockWindowStates();
    }

    private void Settings_Click(
        object sender,
        RoutedEventArgs e)
    {
        if (
            RestorePrimaryPanelIfMinimized(
                SettingsPanel)
        )
        {
            return;
        }

        if (
            SettingsPanel.Visibility
            == Visibility.Visible
        )
        {
            BringFloatingWindowToFront(
                SettingsPanel);

            return;
        }

        LoadSettingsUi();

        SelectSettingsSection(
            "home");

        UpdateSettingsHomeDashboard();

        ShowFloatingPanel(
            SettingsPanel);

        UiLog.Info(
            "Settings panel opened.");
    }

    private async void CloseSettingsPanel_Click(
        object sender,
        RoutedEventArgs e)
    {
        if (
            _settingsHasUnsavedChanges
            && !await ConfirmDiscardSettingsChangesAsync()
        )
        {
            return;
        }

        CloseSettingsPanelInternal();
    }

    private async Task<bool> ConfirmDiscardSettingsChangesAsync()
    {
        var dialog =
            new ContentDialog
            {
                Title =
                    "Abandonner les modifications ?",

                Content =
                    "Les changements effectués dans les Paramètres Atlas n’ont pas été enregistrés.",

                PrimaryButtonText =
                    "Abandonner",

                CloseButtonText =
                    "Continuer la modification",

                DefaultButton =
                    ContentDialogButton.Close,

                XamlRoot =
                    Root.XamlRoot,
            };

        ApplyAtlasDialogStyle(
            dialog);

        var result =
            await dialog.ShowAsync();

        return result
            == ContentDialogResult.Primary;
    }

    private void CloseSettingsPanelInternal()
    {
        SettingsPanel.Visibility =
            Visibility.Collapsed;

        _settingsEditingReady =
            false;

        ClearSettingsDirtyState();

        ForgetFloatingWindowState(
            SettingsPanel);

        SavePrimaryWindowLayouts();
    }


    private void SettingsSearchBox_TextChanged(
        object sender,
        TextChangedEventArgs e)
    {
        var query =
            SettingsSearchBox.Text
                .Trim();

        if (query.Length < 3)
        {
            return;
        }

        var section =
            ResolveSettingsSearchSection(
                query);

        if (section is null)
        {
            SettingsStatusText.Text =
                "Aucun paramètre correspondant.";

            return;
        }

        OpenSettingsSearchSection(
            section);

        SettingsStatusText.Text =
            $"Résultat : {GetSettingsSectionDisplayName(section)}";
    }

    private void SettingsSearchBox_KeyDown(
        object sender,
        KeyRoutedEventArgs e)
    {
        if (e.Key == VirtualKey.Escape)
        {
            SettingsSearchBox.Text =
                string.Empty;

            SelectSettingsSection(
                "home");

            UpdateSettingsHomeDashboard();

            e.Handled =
                true;

            return;
        }

        if (e.Key != VirtualKey.Enter)
        {
            return;
        }

        var section =
            ResolveSettingsSearchSection(
                SettingsSearchBox.Text);

        if (section is null)
        {
            SettingsStatusText.Text =
                "Aucun paramètre correspondant.";
        }
        else
        {
            OpenSettingsSearchSection(
                section);

            SettingsStatusText.Text =
                $"Résultat : {GetSettingsSectionDisplayName(section)}";
        }

        e.Handled =
            true;
    }

    private string? ResolveSettingsSearchSection(
        string query)
    {
        var normalized =
            NormalizeSettingsSearchText(
                query);

        if (string.IsNullOrWhiteSpace(
                normalized))
        {
            return null;
        }

        var entries =
            new (
                string Section,
                string[] Keywords
            )[]
            {
                (
                    "display",
                    new[]
                    {
                        "affichage",
                        "ecran",
                        "moniteur",
                        "resolution",
                        "display",
                    }
                ),
                (
                    "desktop",
                    new[]
                    {
                        "bureau",
                        "fenetre",
                        "fenetres",
                        "widget",
                        "widgets",
                        "disposition",
                        "snap",
                    }
                ),
                (
                    "network",
                    new[]
                    {
                        "reseau",
                        "network",
                        "ethernet",
                        "wifi",
                        "ip",
                        "ipv4",
                        "dns",
                        "passerelle",
                        "debit",
                    }
                ),
                (
                    "voice",
                    new[]
                    {
                        "voix",
                        "ecoute",
                        "micro",
                        "microphone",
                        "wake",
                        "reveil",
                        "atlas",
                    }
                ),
                (
                    "storage",
                    new[]
                    {
                        "stockage",
                        "storage",
                        "disque",
                        "volume",
                        "dossier atlas",
                        "racine",
                        "espace",
                    }
                ),
                (
                    "startup",
                    new[]
                    {
                        "demarrage",
                        "startup",
                        "windows",
                        "session",
                        "automatique",
                    }
                ),
                (
                    "permissions",
                    new[]
                    {
                        "securite",
                        "permission",
                        "permissions",
                        "autorisation",
                        "administrateur",
                        "atlaservice",
                        "service",
                        "risque",
                    }
                ),
                (
                    "updates",
                    new[]
                    {
                        "miseajour",
                        "misesajour",
                        "update",
                        "updates",
                        "version",
                        "canal",
                        "dev",
                        "rc",
                        "release",
                    }
                ),
                (
                    "about",
                    new[]
                    {
                        "apropos",
                        "version",
                        "build",
                        "winui",
                        "core",
                        "architecture",
                    }
                ),
            };

        foreach (
            var entry
            in entries)
        {
            if (
                entry.Keywords.Any(
                    keyword =>
                        keyword.Contains(
                            normalized,
                            StringComparison.OrdinalIgnoreCase)
                        || normalized.Contains(
                            keyword,
                            StringComparison.OrdinalIgnoreCase))
            )
            {
                return entry.Section;
            }
        }

        return null;
    }

    private static string NormalizeSettingsSearchText(
        string value)
    {
        if (string.IsNullOrWhiteSpace(
                value))
        {
            return string.Empty;
        }

        var normalized =
            value
                .Trim()
                .ToLowerInvariant()
                .Normalize(
                    NormalizationForm.FormD);

        var builder =
            new System.Text.StringBuilder();

        foreach (
            var character
            in normalized)
        {
            if (
                CharUnicodeInfo.GetUnicodeCategory(
                    character)
                != UnicodeCategory.NonSpacingMark
            )
            {
                builder.Append(
                    character);
            }
        }

        return builder
            .ToString()
            .Normalize(
                NormalizationForm.FormC)
            .Replace(
                " ",
                string.Empty);
    }

    private void OpenSettingsSearchSection(
        string section)
    {
        SelectSettingsSection(
            section);

        switch (section)
        {
            case "home":
                UpdateSettingsHomeDashboard();
                break;

            case "display":
                UpdateDisplaySettingsPresentation();
                break;

            case "voice":
                RequestListeningModeState();
                break;

            case "storage":
                UpdateStorageSettingsPresentation();
                break;

            case "startup":
                UpdateStartupRegistrationPresentation();
                break;

            case "permissions":
                UpdateSecurityOverviewPresentation();

                _ = _ipc.SendCommandAsync(
                    "security.get_permission_state");
                break;

            case "updates":
                UpdateUpdateSettingsPresentation();
                break;

            case "about":
                UpdateAboutSettingsPresentation();
                break;
        }
    }

    private static string GetSettingsSectionDisplayName(
        string section)
    {
        return section switch
        {
            "display" =>
                "Affichage",

            "desktop" =>
                "Bureau",

            "network" =>
                "Réseau",

            "voice" =>
                "Voix & écoute",

            "storage" =>
                "Stockage",

            "startup" =>
                "Démarrage",

            "permissions" =>
                "Sécurité",

            "updates" =>
                "Mises à jour",

            "about" =>
                "À propos",

            _ =>
                "Accueil",
        };
    }

    private void SettingsHomeNav_Click(
        object sender,
        RoutedEventArgs e)
    {
        SelectSettingsSection(
            "home");

        UpdateSettingsHomeDashboard();
    }

    private void UpdateSettingsHomeDashboard()
    {
        HomeVersionText.Text =
            $"Atlas {AtlasVersion}";

        HomeCoreStatusText.Text =
            _coreConnected
                ? "Connecté"
                : "Déconnecté";

        HomeListeningModeText.Text =
            _currentListeningMode == "wake_word"
                ? "Mot de réveil"
                : "Écoute continue";

        HomeListeningDetailText.Text =
            !_coreConnected
                ? "Core non connecté."
                : _currentListeningMode == "wake_word"
                    ? "Atlas attend le mot de réveil local avant d’ouvrir une session vocale."
                    : "Atlas maintient l’écoute vocale continue.";

        var storageRoot =
            string.IsNullOrWhiteSpace(
                _workspaceRoot)
                ? GetSelectedStorageRoot()
                : _workspaceRoot;

        HomeStoragePathText.Text =
            string.IsNullOrWhiteSpace(
                storageRoot)
                ? "Non configuré"
                : storageRoot;

        HomeStorageStateText.Text =
            !string.IsNullOrWhiteSpace(
                storageRoot)
            && Directory.Exists(
                storageRoot)
                ? "Disponible"
                : "À vérifier";

        var startupStatus =
            _startupRegistration
                .GetStatus();

        HomeStartupStateText.Text =
            startupStatus.Enabled
                ? "Actif"
                : "Inactif";

        HomePermissionModeText.Text =
            $"Mode : {GetPermissionModeDisplayName(_currentPermissionMode)}";
    }

    private void HomeOpenAbout_Click(
        object sender,
        RoutedEventArgs e)
    {
        SelectSettingsSection(
            "about");

        UpdateAboutSettingsPresentation();
    }

    private void HomeOpenVoice_Click(
        object sender,
        RoutedEventArgs e)
    {
        SelectSettingsSection(
            "voice");

        RequestListeningModeState();
    }

    private void HomeOpenStorage_Click(
        object sender,
        RoutedEventArgs e)
    {
        SelectSettingsSection(
            "storage");

        UpdateStorageSettingsPresentation();
    }

    private void HomeOpenStartup_Click(
        object sender,
        RoutedEventArgs e)
    {
        SelectSettingsSection(
            "startup");

        UpdateStartupRegistrationPresentation();
    }

    private void HomeOpenSecurity_Click(
        object sender,
        RoutedEventArgs e)
    {
        SelectSettingsSection(
            "permissions");

        UpdateSecurityOverviewPresentation();

        _ = _ipc.SendCommandAsync(
            "security.get_permission_state");
    }

    private void SettingsDisplayNav_Click(
        object sender,
        RoutedEventArgs e)
    {
        SelectSettingsSection(
            "display");

        UpdateDisplaySettingsPresentation();
    }

    private void UpdateDisplaySettingsPresentation()
    {
        var selectedDeviceName =
            SettingsDisplayComboBoxSecondary
                .SelectedItem
            is ComboBoxItem selectedItem
            && selectedItem.Tag
                is string selectedTag
                ? selectedTag
                : string.Empty;

        var displays =
            _displayService
                .EnumerateDisplays();

        var selectedDisplay =
            displays.FirstOrDefault(
                display =>
                    string.Equals(
                        display.DeviceName,
                        selectedDeviceName,
                        StringComparison.OrdinalIgnoreCase));

        if (selectedDisplay is null)
        {
            DisplaySettingsNameText.Text =
                "Aucun écran sélectionné";

            DisplaySettingsDeviceText.Text =
                "—";

            DisplaySettingsResolutionText.Text =
                "—";

            DisplaySettingsWorkAreaText.Text =
                "—";

            DisplaySettingsPrimaryText.Text =
                "État indisponible";

            DisplaySettingsAppliedText.Text =
                "Sélectionnez un écran Atlas.";

            DisplaySettingsPendingText.Text =
                "Aucun changement en attente.";

            return;
        }

        DisplaySettingsNameText.Text =
            string.IsNullOrWhiteSpace(
                selectedDisplay.FriendlyName)
                ? BuildDisplayLabel(
                    selectedDisplay)
                : selectedDisplay.FriendlyName;

        DisplaySettingsDeviceText.Text =
            selectedDisplay.DeviceName;

        DisplaySettingsResolutionText.Text =
            $"{selectedDisplay.Bounds.Width} × {selectedDisplay.Bounds.Height}";

        DisplaySettingsWorkAreaText.Text =
            $"Zone Windows : {selectedDisplay.WorkArea.Width} × {selectedDisplay.WorkArea.Height}";

        DisplaySettingsPrimaryText.Text =
            selectedDisplay.IsPrimary
                ? "Écran principal Windows"
                : "Écran secondaire Windows";

        var appliedDeviceName =
            _atlasDisplay?.DeviceName
            ?? string.Empty;

        var isApplied =
            !string.IsNullOrWhiteSpace(
                appliedDeviceName)
            && string.Equals(
                selectedDisplay.DeviceName,
                appliedDeviceName,
                StringComparison.OrdinalIgnoreCase);

        DisplaySettingsAppliedText.Text =
            isApplied
                ? "Cet écran héberge actuellement le bureau Atlas."
                : $"Atlas est actuellement sur {(_atlasDisplay is null ? "un autre écran" : BuildDisplayLabel(_atlasDisplay))}.";

        DisplaySettingsPendingText.Text =
            isApplied
                ? "Aucun changement en attente."
                : "Changement en attente · cliquez sur Enregistrer pour l’appliquer.";
    }

    private void RefreshDisplaySettings_Click(
        object sender,
        RoutedEventArgs e)
    {
        PopulateDisplaySettings(
            _config.Load());

        SyncSecondarySettingsControls();

        UpdateDisplaySettingsPresentation();
    }

    private void ResetDesktopWindows_Click(
        object sender,
        RoutedEventArgs e)
    {
        ResetPrimaryDesktopWindows();

        SavePrimaryWindowLayouts();

        SettingsStatusText.Text =
            "Disposition des fenêtres réinitialisée.";

        UiLog.Info(
            "Atlas primary window layout reset to defaults.");
    }

    private void ResetDesktopWidgets_Click(
        object sender,
        RoutedEventArgs e)
    {
        ResetDesktopWidgets();

        SettingsStatusText.Text =
            "Disposition des widgets réinitialisée.";

        UiLog.Info(
            "Atlas widget layout reset to right preset.");
    }

    private void ResetDesktopLayout_Click(
        object sender,
        RoutedEventArgs e)
    {
        ResetPrimaryDesktopWindows();
        ResetDesktopWidgets();

        SavePrimaryWindowLayouts();

        SettingsStatusText.Text =
            "Disposition complète du bureau réinitialisée.";

        UiLog.Info(
            "Atlas desktop layout reset to defaults.");
    }

    private void ResetPrimaryDesktopWindows()
    {
        ResetPrimaryWindowLayout(
            FilesPanel,
            FilesMaximizeButton,
            1280,
            760);

        ResetPrimaryWindowLayout(
            SettingsPanel,
            SettingsMaximizeButton,
            1140,
            700);

        ResetPrimaryWindowLayout(
            WidgetManagerPanel,
            WidgetsMaximizeButton,
            760,
            500);
    }

    private void ResetDesktopWidgets()
    {
        ApplyDesktopWidgetPreset(
            HorizontalAlignment.Right,
            save: true);
    }

    private void ResetPrimaryWindowLayout(
        FrameworkElement panel,
        Button maximizeButton,
        double width,
        double height)
    {
        _floatingWindowRestoreStates.Remove(
            panel);

        _floatingWindowMaximizeButtons.Remove(
            panel);

        UpdateMaximizeButtonVisual(
            maximizeButton,
            false);

        EnsureFloatingPanelUsesAbsolutePosition(
            panel);

        var workspaceWidth =
            Math.Max(
                1,
                Root.ActualWidth);

        var workspaceBottom =
            Math.Max(
                1,
                GetFloatingWorkspaceBottom());

        var targetWidth =
            Math.Min(
                width,
                Math.Max(
                    panel.MinWidth,
                    workspaceWidth - 40));

        var targetHeight =
            Math.Min(
                height,
                Math.Max(
                    panel.MinHeight,
                    workspaceBottom - 40));

        panel.Width =
            targetWidth;

        panel.Height =
            targetHeight;

        panel.Margin =
            new Thickness(
                Math.Max(
                    20,
                    (
                        workspaceWidth
                        - targetWidth
                    )
                    / 2),
                Math.Max(
                    20,
                    (
                        workspaceBottom
                        - targetHeight
                    )
                    / 2),
                0,
                0);

        ClampFloatingPanelToWorkspace(
            panel);
    }

    private void SettingsDesktopNav_Click(
        object sender,
        RoutedEventArgs e)
    {
        SelectSettingsSection(
            "desktop");
    }

    private void SettingsNetworkNav_Click(
        object sender,
        RoutedEventArgs e)
    {
        SelectSettingsSection(
            "network");
    }

    private void SettingsVoiceNav_Click(
        object sender,
        RoutedEventArgs e)
    {
        SelectSettingsSection(
            "voice");

        RequestListeningModeState();
    }

    private async void ListeningContinuous_Click(
        object sender,
        RoutedEventArgs e)
    {
        await SetListeningModeAsync(
            "continuous");
    }

    private async void ListeningWakeWord_Click(
        object sender,
        RoutedEventArgs e)
    {
        await SetListeningModeAsync(
            "wake_word");
    }

    private void RefreshListeningMode_Click(
        object sender,
        RoutedEventArgs e)
    {
        RequestListeningModeState();
    }

    private void RequestListeningModeState()
    {
        if (!_ipc.IsConnected)
        {
            UpdateListeningModePresentation(
                null,
                false,
                "Atlas");

            return;
        }

        _ = _ipc.SendCommandAsync(
            "audio.get_listening_mode");
        // Keep the two established commands for compatibility with a Core
        // that has not yet been rebuilt with the combined inventory command.
        _ = _ipc.SendCommandAsync("audio.get_input_devices");
        _ = _ipc.SendCommandAsync("audio.get_output_devices");
    }

    private async void SpeakerComboBox_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (_syncingSpeaker || SpeakerComboBox.SelectedItem is not ComboBoxItem item) return;
        var selection = item.Tag as string;
        try
        {
            // Leave the native selection callback before sending a command that can refresh items.
            await Task.Yield();
            if (!_ipc.IsConnected)
            {
                SpeakerStatusText.Text = "Core non connecté : sortie inchangée.";
                return;
            }
            SpeakerComboBox.IsEnabled = false;
            SpeakerStatusText.Text = "Changement de la sortie audio…";
            if (!await _ipc.SendCommandAsync("audio.set_output_device", new { device = selection }))
                SpeakerStatusText.Text = "Impossible de joindre le Core.";
        }
        catch (Exception exception) { SpeakerStatusText.Text = exception.Message; }
        finally { SpeakerComboBox.IsEnabled = true; }
    }

    private void HandleSpeakerState(JsonElement message)
    {
        if (!message.TryGetProperty("payload", out var payload)) return;
        _syncingSpeaker = true;
        try
        {
            SpeakerComboBox.Items.Clear();
            var defaultItem = new ComboBoxItem { Content = "Par défaut Windows", Tag = "" };
            SpeakerComboBox.Items.Add(defaultItem);
            var selected = payload.TryGetProperty("selected", out var value)
                && value.ValueKind == JsonValueKind.String ? value.GetString() : "";
            var active = payload.GetProperty("active_index");
            var label = "Aucune sortie active";
            SpeakerComboBox.SelectedItem = defaultItem;
            foreach (var device in payload.GetProperty("devices").EnumerateArray())
            {
                var id = device.GetProperty("id").GetString();
                var name = device.GetProperty("label").GetString();
                var item = new ComboBoxItem { Content = name, Tag = id };
                SpeakerComboBox.Items.Add(item);
                if (id == selected) SpeakerComboBox.SelectedItem = item;
                if (active.ValueKind == JsonValueKind.Number && active.GetInt32() == device.GetProperty("index").GetInt32())
                    label = name ?? label;
            }
            if (!string.IsNullOrEmpty(selected)
                && ReferenceEquals(SpeakerComboBox.SelectedItem, defaultItem))
            {
                var missing = new ComboBoxItem { Content = "Sortie mémorisée indisponible", Tag = selected };
                SpeakerComboBox.Items.Add(missing);
                SpeakerComboBox.SelectedItem = missing;
            }
            SpeakerStatusText.Text = "Sortie active : " + label;
            if (payload.TryGetProperty("warning", out var warning) && !string.IsNullOrEmpty(warning.GetString()))
                SpeakerStatusText.Text += " · " + warning.GetString();
        }
        finally { _syncingSpeaker = false; }
    }

    private async void MicrophoneComboBox_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (_syncingMicrophone || MicrophoneComboBox.SelectedItem is not ComboBoxItem item)
            return;
        if (!_ipc.IsConnected)
        {
            MicrophoneStatusText.Text = "Core non connecté : microphone inchangé.";
            return;
        }
        MicrophoneComboBox.IsEnabled = false;
        try
        {
            if (!await _ipc.SendCommandAsync("audio.set_input_device", new { device = item.Tag as string }))
                MicrophoneStatusText.Text = "Impossible de joindre le Core.";
            else MicrophoneStatusText.Text = "Changement du microphone…";
        }
        catch (Exception exception) { MicrophoneStatusText.Text = exception.Message; }
        finally { MicrophoneComboBox.IsEnabled = true; }
    }

    private void HandleMicrophoneState(JsonElement message)
    {
        if (!message.TryGetProperty("payload", out var payload)) return;
        _syncingMicrophone = true;
        try
        {
            MicrophoneComboBox.Items.Clear();
            var defaultItem = new ComboBoxItem { Content = "Par défaut Windows", Tag = "" };
            MicrophoneComboBox.Items.Add(defaultItem);
            var selected = payload.TryGetProperty("selected", out var selectedValue)
                && selectedValue.ValueKind == JsonValueKind.String ? selectedValue.GetString() : "";
            MicrophoneComboBox.SelectedItem = defaultItem;
            var active = payload.GetProperty("active_index");
            var activeLabel = "Aucun microphone actif";
            if (payload.TryGetProperty("devices", out var devices))
                foreach (var device in devices.EnumerateArray())
                {
                    var id = device.GetProperty("id").GetString();
                    var label = device.GetProperty("label").GetString();
                    var item = new ComboBoxItem { Content = label, Tag = id };
                    MicrophoneComboBox.Items.Add(item);
                    if (id == selected) MicrophoneComboBox.SelectedItem = item;
                    if (active.ValueKind == JsonValueKind.Number && active.GetInt32() == device.GetProperty("index").GetInt32())
                        activeLabel = label ?? activeLabel;
                }
            if (!string.IsNullOrEmpty(selected)
                && ReferenceEquals(MicrophoneComboBox.SelectedItem, defaultItem))
            {
                var missing = new ComboBoxItem { Content = "Microphone mémorisé indisponible", Tag = selected };
                MicrophoneComboBox.Items.Add(missing);
                MicrophoneComboBox.SelectedItem = missing;
            }
            MicrophoneStatusText.Text = "Micro actif : " + activeLabel;
            if (payload.TryGetProperty("warning", out var warning) && !string.IsNullOrEmpty(warning.GetString()))
                MicrophoneStatusText.Text += " · " + warning.GetString();
        }
        finally { _syncingMicrophone = false; }
    }

    private async Task SetListeningModeAsync(
        string mode)
    {
        if (!_ipc.IsConnected)
        {
            SettingsStatusText.Text =
                "Core non connecté · mode d’écoute inchangé.";

            UpdateListeningModePresentation(
                null,
                false,
                "Atlas");

            return;
        }

        ListeningContinuousButton.IsEnabled =
            false;

        ListeningWakeWordButton.IsEnabled =
            false;

        SettingsStatusText.Text =
            "Modification du mode d’écoute…";

        try
        {
            var sent =
                await _ipc.SendCommandAsync(
                    "audio.set_listening_mode",
                    new
                    {
                        mode,
                    });

            if (!sent)
            {
                SettingsStatusText.Text =
                    "Impossible d’envoyer le mode d’écoute au Core.";
            }
        }
        catch (Exception exception)
        {
            UiLog.Error(
                "Unable to change listening mode.",
                exception);

            SettingsStatusText.Text =
                "Erreur lors de la modification du mode d’écoute.";
        }
        finally
        {
            ListeningContinuousButton.IsEnabled =
                true;

            ListeningWakeWordButton.IsEnabled =
                true;
        }
    }

    private void HandleListeningModeState(
        JsonElement message)
    {
        if (
            !message.TryGetProperty(
                "payload",
                out var payload)
            || payload.ValueKind
                != JsonValueKind.Object
        )
        {
            return;
        }

        var mode =
            ReadJsonString(
                payload,
                "mode");

        var wakeWord =
            ReadJsonString(
                payload,
                "wake_word")
            ?? "Atlas";

        var voiceSessionActive =
            false;

        if (
            payload.TryGetProperty(
                "voice_session_active",
                out var voiceSessionNode)
            && (
                voiceSessionNode.ValueKind
                    == JsonValueKind.True
                || voiceSessionNode.ValueKind
                    == JsonValueKind.False
            )
        )
        {
            voiceSessionActive =
                voiceSessionNode.GetBoolean();
        }

        UpdateListeningModePresentation(
            mode,
            voiceSessionActive,
            wakeWord);

        UpdateSettingsHomeDashboard();

        SettingsStatusText.Text =
            mode switch
            {
                "wake_word" =>
                    $"Mode vocal actif · réveil « {wakeWord} »",

                "continuous" =>
                    "Écoute continue active",

                _ =>
                    "État d’écoute reçu du Core",
            };
    }

    private void HandleListeningModeError(
        JsonElement message)
    {
        var reason =
            "Le Core a refusé la modification du mode d’écoute.";

        if (
            message.TryGetProperty(
                "payload",
                out var payload)
            && payload.ValueKind
                == JsonValueKind.Object
        )
        {
            reason =
                ReadJsonString(
                    payload,
                    "reason")
                ?? reason;
        }

        SettingsStatusText.Text =
            reason;

        RequestListeningModeState();
    }

    private void UpdateListeningModePresentation(
        string? mode,
        bool voiceSessionActive,
        string wakeWord)
    {
        _voiceSessionActive =
            voiceSessionActive;

        ListeningWakeWordText.Text =
            wakeWord;

        if (
            mode
                is "continuous"
                or "wake_word"
        )
        {
            _currentListeningMode =
                mode;
        }

        var connected =
            _ipc.IsConnected
            && mode is not null;

        var continuous =
            connected
            && _currentListeningMode
                == "continuous";

        var wakeMode =
            connected
            && _currentListeningMode
                == "wake_word";

        ListeningContinuousIndicator.Fill =
            CreateBrush(
                continuous
                    ? "#67DFA0"
                    : "#48586776");

        ListeningWakeWordIndicator.Fill =
            CreateBrush(
                wakeMode
                    ? "#67DFA0"
                    : "#48586776");

        ListeningContinuousButton.BorderBrush =
            CreateBrush(
                continuous
                    ? "#5B67DFA0"
                    : "#31587590");

        ListeningWakeWordButton.BorderBrush =
            CreateBrush(
                wakeMode
                    ? "#5B67DFA0"
                    : "#31587590");

        if (!connected)
        {
            ListeningStateIndicator.Fill =
                CreateBrush(
                    "#7A8593A0");

            ListeningStateText.Text =
                "Core non connecté";

            ListeningStateDescriptionText.Text =
                "Démarre Atlas Core pour utiliser les réglages de voix.";

            VoiceWidgetStateIndicator.Fill =
                CreateBrush(
                    "#7A8593A0");

            VoiceWidgetStateText.Text =
                "Core non connecté";

            VoiceWidgetModeText.Text =
                "Mode d’écoute indisponible";

            VoiceWidgetWakeWordText.Text =
                wakeWord;

            return;
        }

        ListeningStateIndicator.Fill =
            CreateBrush(
                voiceSessionActive
                    ? "#F1C76E"
                    : "#67DFA0");

        if (continuous)
        {
            ListeningStateText.Text =
                voiceSessionActive
                    ? "Conversation active"
                    : "Écoute continue";

            ListeningStateDescriptionText.Text =
                "Atlas écoute en permanence et peut répondre sans mot de réveil.";

            VoiceWidgetStateIndicator.Fill =
                CreateBrush(
                    voiceSessionActive
                        ? "#F1C76E"
                        : "#67DFA0");

            VoiceWidgetStateText.Text =
                voiceSessionActive
                    ? "Conversation active"
                    : "Écoute continue";

            VoiceWidgetModeText.Text =
                "Atlas écoute sans mot de réveil.";

            VoiceWidgetWakeWordText.Text =
                wakeWord;
        }
        else
        {
            ListeningStateText.Text =
                voiceSessionActive
                    ? "Session vocale active"
                    : $"En attente de « {wakeWord} »";

            ListeningStateDescriptionText.Text =
                voiceSessionActive
                    ? "Le mot de réveil a été détecté. La session vocale est active."
                    : $"La détection de « {wakeWord} » reste locale jusqu’au réveil.";

            VoiceWidgetStateIndicator.Fill =
                CreateBrush(
                    voiceSessionActive
                        ? "#F1C76E"
                        : "#67DFA0");

            VoiceWidgetStateText.Text =
                voiceSessionActive
                    ? "Session vocale active"
                    : $"En attente de « {wakeWord} »";

            VoiceWidgetModeText.Text =
                voiceSessionActive
                    ? "Réveil détecté · session ouverte"
                    : "Réveil vocal local actif";

            VoiceWidgetWakeWordText.Text =
                wakeWord;
        }
    }

    private void SettingsStorageNav_Click(
        object sender,
        RoutedEventArgs e)
    {
        SelectSettingsSection(
            "storage");

        UpdateStorageSettingsPresentation();
    }

    private void UpdateStorageSettingsPresentation()
    {
        var rootPath =
            string.IsNullOrWhiteSpace(
                _workspaceRoot)
                ? GetSelectedStorageRoot()
                : _workspaceRoot;

        StorageSettingsRootPathText.Text =
            string.IsNullOrWhiteSpace(
                rootPath)
                ? "Aucune racine configurée"
                : rootPath;

        if (string.IsNullOrWhiteSpace(
                rootPath))
        {
            StorageSettingsRootStateText.Text =
                "Non configurée";

            StorageSettingsVolumeText.Text =
                "—";

            StorageSettingsUsageText.Text =
                "—";

            StorageSettingsPercentText.Text =
                "—";

            StorageSettingsUsageBar.Value =
                0;

            return;
        }

        try
        {
            var fullPath =
                IOPath.GetFullPath(
                    rootPath);

            var root =
                IOPath.GetPathRoot(
                    fullPath);

            var rootAvailable =
                Directory.Exists(
                    fullPath);

            StorageSettingsRootStateText.Text =
                rootAvailable
                    ? "Disponible"
                    : "Non créée";

            if (string.IsNullOrWhiteSpace(
                    root))
            {
                StorageSettingsVolumeText.Text =
                    "Volume introuvable";

                StorageSettingsUsageText.Text =
                    "—";

                StorageSettingsPercentText.Text =
                    "—";

                StorageSettingsUsageBar.Value =
                    0;

                return;
            }

            var drive =
                new DriveInfo(
                    root);

            if (!drive.IsReady)
            {
                StorageSettingsVolumeText.Text =
                    $"{drive.Name} · indisponible";

                StorageSettingsUsageText.Text =
                    "Volume non prêt";

                StorageSettingsPercentText.Text =
                    "—";

                StorageSettingsUsageBar.Value =
                    0;

                return;
            }

            var total =
                drive.TotalSize;

            var free =
                drive.AvailableFreeSpace;

            var used =
                Math.Max(
                    0,
                    total - free);

            var percent =
                total > 0
                    ? used * 100.0 / total
                    : 0;

            StorageSettingsVolumeText.Text =
                string.IsNullOrWhiteSpace(
                    drive.VolumeLabel)
                    ? drive.Name
                    : $"{drive.VolumeLabel} · {drive.Name}";

            StorageSettingsUsageText.Text =
                $"{FormatBytes(used)} utilisés · {FormatBytes(free)} libres sur {FormatBytes(total)}";

            StorageSettingsPercentText.Text =
                $"{percent:0.#} %";

            StorageSettingsUsageBar.Value =
                Math.Clamp(
                    percent,
                    0,
                    100);
        }
        catch (Exception exception)
        {
            StorageSettingsRootStateText.Text =
                "Indisponible";

            StorageSettingsVolumeText.Text =
                "Erreur";

            StorageSettingsUsageText.Text =
                exception.Message;

            StorageSettingsPercentText.Text =
                "—";

            StorageSettingsUsageBar.Value =
                0;

            UiLog.Error(
                "Unable to refresh storage settings presentation.",
                exception);
        }
    }

    private string GetSelectedStorageRoot()
    {
        if (
            SettingsStorageComboBoxSecondary
                .SelectedItem
            is ComboBoxItem item
            && item.Tag
                is string selectedRoot
        )
        {
            return selectedRoot;
        }

        return string.Empty;
    }

    private void RefreshStorageSettings_Click(
        object sender,
        RoutedEventArgs e)
    {
        UpdateStorageSettingsPresentation();
    }

    private void SettingsStartupNav_Click(
        object sender,
        RoutedEventArgs e)
    {
        SelectSettingsSection(
            "startup");

        UpdateStartupRegistrationPresentation();
    }

    private void SettingsPermissionsNav_Click(
        object sender,
        RoutedEventArgs e)
    {
        SelectSettingsSection(
            "permissions");

        UpdateSecurityOverviewPresentation();

        _ = _ipc.SendCommandAsync(
            "security.get_permission_state");
    }

    private void SettingsUpdatesNav_Click(
        object sender,
        RoutedEventArgs e)
    {
        SelectSettingsSection(
            "updates");

        UpdateUpdateSettingsPresentation();
        _ = CheckForUpdatesAsync();
    }

    private void UpdateUpdateSettingsPresentation()
    {
        if (_updateOperationInProgress) return;
        _updateConfiguration =
            _config.LoadUpdateConfiguration();

        UpdateCurrentVersionText.Text =
            _updateConfiguration.Version;

        _syncingUpdateChannel = true;
        try
        {
            // Build once: clearing native ComboBox items inside SelectionChanged can crash WinUI.
            if (UpdateChannelComboBox.Items.Count == 0)
            {
                if (_updateConfiguration.Channel == "dev")
                    UpdateChannelComboBox.Items.Add(new ComboBoxItem { Content = "DEV", Tag = "dev" });
                else
                {
                    UpdateChannelComboBox.Items.Add(new ComboBoxItem { Content = "Experimental", Tag = "rc" });
                    UpdateChannelComboBox.Items.Add(new ComboBoxItem { Content = "Release", Tag = "release" });
                }
            }
            UpdateChannelComboBox.SelectedIndex = _updateConfiguration.Channel == "release" ? 1 : 0;
            UpdateChannelComboBox.IsEnabled = !_changingUpdateChannel && _updateConfiguration.Channel != "dev";
        }
        finally { _syncingUpdateChannel = false; }

        UpdateSourceText.Text =
            string.IsNullOrWhiteSpace(
                _updateConfiguration.ManifestUrl)
                ? "Non configurée"
                : _updateConfiguration.ManifestUrl;

        UpdateStatusText.Text =
            _updateConfiguration.Enabled
                ? "Non vérifié"
                : "Mises à jour désactivées";

        UpdateAvailableVersionText.Text =
            "—";

        _availableUpdateManifest =
            null;

        DownloadUpdateButton.Visibility =
            Visibility.Collapsed;

        DownloadUpdateButton.IsEnabled =
            false;

        _verifiedDownloadedUpdate =
            null;

        InstallUpdateButton.Visibility =
            Visibility.Collapsed;

        InstallUpdateButton.IsEnabled =
            false;

        UpdateDownloadProgress.Value =
            0;

        UpdateDownloadProgress.Visibility =
            Visibility.Collapsed;

        UpdateDownloadPathText.Text =
            string.Empty;

        UpdateDownloadPathText.Visibility =
            Visibility.Collapsed;

        UpdateNotesText.Text =
            string.Empty;

        UpdateNotesText.Visibility =
            Visibility.Collapsed;
    }

    private async void UpdateChannelComboBox_SelectionChanged(
        object sender,
        SelectionChangedEventArgs e)
    {
        if (_syncingUpdateChannel || _changingUpdateChannel || _updateOperationInProgress
            || UpdateChannelComboBox.SelectedItem is not ComboBoxItem item
            || item.Tag is not string channel)
        {
            return;
        }

        if (channel == _updateConfiguration.Channel) return;
        _changingUpdateChannel = true;
        try
        {
            await Task.Yield();
            UpdateChannelComboBox.IsEnabled = false;
            _updateConfiguration = _config.SaveUpdateChannel(channel);
            UpdateUpdateSettingsPresentation();
            UpdateSourceText.Text = _updateConfiguration.ManifestUrl;
            await CheckForUpdatesAsync();
        }
        catch (Exception exception)
        {
            UiLog.Error("Update channel change failed.", exception);
            _syncingUpdateChannel = true;
            try { UpdateChannelComboBox.SelectedIndex = _updateConfiguration.Channel == "release" ? 1 : 0; }
            finally { _syncingUpdateChannel = false; }
            UpdateStatusText.Text = "Impossible de changer de canal : " + exception.Message;
        }
        finally
        {
            _changingUpdateChannel = false;
            UpdateChannelComboBox.IsEnabled = !_updateOperationInProgress && _updateConfiguration.Channel != "dev";
        }
    }

    private async Task CheckForUpdatesAsync()
    {
        if (_updateOperationInProgress || _verifiedDownloadedUpdate is not null) return;
        if (_updateCheckInProgress)
        {
            _updateCheckAgain = true;
            return;
        }

        _updateCheckInProgress = true;

        UpdateCheckProgress.IsActive =
            true;

        UpdateCheckProgress.Visibility =
            Visibility.Visible;

        UpdateStatusText.Text =
            "Vérification en cours…";

        UpdateAvailableVersionText.Text =
            "—";

        _availableUpdateManifest =
            null;

        DownloadUpdateButton.Visibility =
            Visibility.Collapsed;

        DownloadUpdateButton.IsEnabled =
            false;

        _verifiedDownloadedUpdate =
            null;

        InstallUpdateButton.Visibility =
            Visibility.Collapsed;

        InstallUpdateButton.IsEnabled =
            false;

        UpdateDownloadProgress.Value =
            0;

        UpdateDownloadProgress.Visibility =
            Visibility.Collapsed;

        UpdateDownloadPathText.Text =
            string.Empty;

        UpdateDownloadPathText.Visibility =
            Visibility.Collapsed;

        UpdateNotesText.Visibility =
            Visibility.Collapsed;

        try
        {
            _updateConfiguration =
                _config.LoadUpdateConfiguration();

            var options =
                new AtlasUpdateOptions(
                    _updateConfiguration.Enabled,
                    _updateConfiguration.Channel,
                    _updateConfiguration.CheckOnStartup,
                    _updateConfiguration.ManifestUrl);

            var result =
                await _updateService.CheckAsync(
                    _updateConfiguration.Version,
                    options);

            if (_config.LoadUpdateConfiguration().Channel != options.Channel)
            {
                _updateCheckAgain = true;
                return;
            }

            UpdateStatusText.Text =
                result.Message;

            UpdateAvailableVersionText.Text =
                result.Manifest?.Version
                ?? "—";

            UpdateSourceText.Text =
                string.IsNullOrWhiteSpace(
                    _updateConfiguration.ManifestUrl)
                    ? "Non configurée"
                    : _updateConfiguration.ManifestUrl;

            var notes =
                result.Manifest?.Notes;

            if (!string.IsNullOrWhiteSpace(
                    notes))
            {
                UpdateNotesText.Text =
                    notes;

                UpdateNotesText.Visibility =
                    Visibility.Visible;
            }

            if (
                (result.Status == AtlasUpdateStatus.UpdateAvailable
                    || result.Status == AtlasUpdateStatus.ReinstallAvailable)
                && result.Manifest is not null
            )
            {
                _availableUpdateManifest =
                    result.Manifest;

                var downloadConfigured =
                    Uri.TryCreate(
                        result.Manifest.DownloadUrl,
                        UriKind.Absolute,
                        out var downloadUri)
                    && downloadUri.Scheme
                        == Uri.UriSchemeHttps
                    && !string.IsNullOrWhiteSpace(
                        result.Manifest.Sha256);

                DownloadUpdateButton.Visibility =
                    Visibility.Visible;

                DownloadUpdateButton.IsEnabled =
                    downloadConfigured;
                DownloadUpdateButton.Content = result.Status == AtlasUpdateStatus.ReinstallAvailable
                    ? "Télécharger pour réinstaller la Release" : "Télécharger la mise à jour";
                if (downloadConfigured && result.Status == AtlasUpdateStatus.UpdateAvailable)
                    _ = NotifyUpdateAvailableAsync(result.Manifest, options.Channel);

                if (!downloadConfigured)
                {
                    UpdateStatusText.Text =
                        $"{result.Message} Le téléchargement n'est pas encore configuré dans le manifeste.";
                }
            }
        }
        catch (HttpRequestException exception)
        {
            UpdateStatusText.Text =
                $"Impossible de contacter le serveur de mise à jour : {exception.Message}";

            UiLog.Error(
                "Atlas update HTTP check failed.",
                exception);
        }
        catch (TaskCanceledException exception)
        {
            UpdateStatusText.Text =
                "La vérification des mises à jour a expiré.";

            UiLog.Error(
                "Atlas update check timed out.",
                exception);
        }
        catch (Exception exception)
        {
            UpdateStatusText.Text =
                $"Échec de la vérification : {exception.Message}";

            UiLog.Error(
                "Atlas update check failed.",
                exception);
        }
        finally
        {
            UpdateCheckProgress.IsActive =
                false;

            UpdateCheckProgress.Visibility =
                Visibility.Collapsed;

            _updateCheckInProgress = false;
            if (_updateCheckAgain)
            {
                _updateCheckAgain = false;
                _ = CheckForUpdatesAsync();
            }
        }
    }

    private async Task NotifyUpdateAvailableAsync(AtlasUpdateManifest manifest, string channel)
    {
        var key = channel + ":" + manifest.Version;
        if (_updateNoticeOpen || _notifiedUpdates.Contains(key) || Root.XamlRoot is null
            || (SettingsPanel.Visibility == Visibility.Visible && SettingsUpdatesSection.Visibility == Visibility.Visible))
            return;
        _updateNoticeOpen = true;
        try
        {
            var dialog = new ContentDialog
            {
                Title = "Mise à jour Atlas disponible",
                Content = $"Atlas {manifest.Version} est disponible sur le canal {channel}. Voulez-vous ouvrir les mises à jour ?",
                PrimaryButtonText = "Voir la mise à jour", CloseButtonText = "Plus tard",
                DefaultButton = ContentDialogButton.Close, XamlRoot = Root.XamlRoot,
            };
            ApplyAtlasDialogStyle(dialog);
            var result = await dialog.ShowAsync();
            _notifiedUpdates.Add(key);
            if (result == ContentDialogResult.Primary)
            {
                Settings_Click(this, new RoutedEventArgs());
                SelectSettingsSection("updates");
                BringFloatingWindowToFront(SettingsPanel);
            }
        }
        catch (Exception exception) { UiLog.Error("Update notification deferred.", exception); }
        finally { _updateNoticeOpen = false; }
    }

    private async void DownloadUpdate_Click(
        object sender,
        RoutedEventArgs e)
    {
        if (_updateOperationInProgress) return;
        var manifest =
            _availableUpdateManifest;

        if (manifest is null)
        {
            UpdateStatusText.Text =
                "Vérifiez d'abord les mises à jour Atlas.";

            return;
        }

        _updateOperationInProgress = true;
        UpdateChannelComboBox.IsEnabled = false;
        DownloadUpdateButton.IsEnabled = false;

        UpdateDownloadProgress.Value =
            0;

        UpdateDownloadProgress.Visibility =
            Visibility.Visible;

        UpdateDownloadPathText.Text =
            string.Empty;

        UpdateDownloadPathText.Visibility =
            Visibility.Collapsed;

        UpdateStatusText.Text =
            $"Téléchargement d'Atlas {manifest.Version}…";

        try
        {
            var progress =
                new Progress<double>(
                    value =>
                    {
                        UpdateDownloadProgress.Value =
                            Math.Clamp(
                                value,
                                0,
                                100);
                    });

            var result =
                await _updateService.DownloadAsync(
                    manifest,
                    progress);

            UpdateDownloadProgress.Value =
                100;

            UpdateStatusText.Text =
                $"Atlas {manifest.Version} téléchargé et SHA-256 validé.";

            UpdateDownloadPathText.Text =
                $"Fichier vérifié : {result.FilePath}";

            UpdateDownloadPathText.Visibility =
                Visibility.Visible;

            _verifiedDownloadedUpdate =
                result;

            InstallUpdateButton.Visibility =
                Visibility.Visible;

            InstallUpdateButton.IsEnabled =
                true;

            UiLog.Info(
                $"Atlas update downloaded and verified: version={manifest.Version}, path={result.FilePath}, sha256={result.Sha256}, size={result.SizeBytes}");
        }
        catch (InvalidDataException exception)
        {
            UpdateStatusText.Text =
                exception.Message;

            UiLog.Error(
                "Atlas update integrity validation failed.",
                exception);
        }
        catch (HttpRequestException exception)
        {
            UpdateStatusText.Text =
                $"Téléchargement impossible : {exception.Message}";

            UiLog.Error(
                "Atlas update download HTTP request failed.",
                exception);
        }
        catch (TaskCanceledException exception)
        {
            UpdateStatusText.Text =
                "Le téléchargement de la mise à jour a expiré.";

            UiLog.Error(
                "Atlas update download timed out.",
                exception);
        }
        catch (Exception exception)
        {
            UpdateStatusText.Text =
                $"Échec du téléchargement : {exception.Message}";

            UiLog.Error(
                "Atlas update download failed.",
                exception);
        }
        finally
        {
            _updateOperationInProgress = false;
            UpdateChannelComboBox.IsEnabled = _updateConfiguration.Channel != "dev";
            DownloadUpdateButton.IsEnabled =
                _availableUpdateManifest is not null
                && !string.IsNullOrWhiteSpace(
                    _availableUpdateManifest.DownloadUrl)
                && !string.IsNullOrWhiteSpace(
                    _availableUpdateManifest.Sha256);
        }
    }

    private async void InstallUpdate_Click(
        object sender,
        RoutedEventArgs e)
    {
        if (_updateOperationInProgress) return;
        var manifest = _availableUpdateManifest;
        var downloaded = _verifiedDownloadedUpdate;

        if (manifest is null || downloaded is null)
        {
            UpdateStatusText.Text =
                "Téléchargez d'abord une mise à jour Atlas vérifiée.";
            return;
        }

        _updateOperationInProgress = true;
        UpdateChannelComboBox.IsEnabled = false;
        InstallUpdateButton.IsEnabled = false;
        DownloadUpdateButton.IsEnabled = false;

        try
        {
            UpdateStatusText.Text =
                "Vérification finale de l'intégrité…";

            var verified =
                await _updateService.VerifyDownloadedFileAsync(
                    manifest,
                    downloaded.FilePath);

            var dialog =
                new ContentDialog
                {
                    Title = $"Installer Atlas {manifest.Version} ?",
                    Content =
                        "Atlas va demander une autorisation administrateur, installer la mise à jour en arrière-plan "
                        + "puis redémarrer automatiquement. Vos paramètres seront conservés.",
                    PrimaryButtonText = "Installer",
                    CloseButtonText = "Annuler",
                    DefaultButton = ContentDialogButton.Close,
                    XamlRoot = Root.XamlRoot,
                };

            ApplyAtlasDialogStyle(dialog);

            if (await dialog.ShowAsync() != ContentDialogResult.Primary)
            {
                UpdateStatusText.Text = "Installation annulée.";
                return;
            }

            UpdateStatusText.Text =
                $"Préparation de la mise à jour Atlas {manifest.Version}…";

            var progressFile =
                IOPath.Combine(
                    Environment.GetFolderPath(
                        Environment.SpecialFolder.LocalApplicationData),
                    "Atlas",
                    "updates",
                    "update-progress.json");

            var progressDirectory =
                IOPath.GetDirectoryName(
                    progressFile);

            if (!string.IsNullOrWhiteSpace(
                    progressDirectory))
            {
                Directory.CreateDirectory(
                    progressDirectory);
            }

            var startInfo =
                new System.Diagnostics.ProcessStartInfo
                {
                    FileName = verified.FilePath,
                    UseShellExecute = true,
                    Verb = "runas",
                    // Ne jamais transmettre C:\Program Files\Atlas comme
                    // répertoire courant à l'installateur élevé : un simple
                    // répertoire courant suffit à bloquer son renommage.
                    WorkingDirectory =
                        IOPath.GetDirectoryName(verified.FilePath)
                        ?? IOPath.GetTempPath(),
                };

            startInfo.ArgumentList.Add(
                "--update");

            startInfo.ArgumentList.Add(
                "--silent");

            // L'installateur élevé est lancé avant la fermeture de l'UI afin
            // que l'UAC reste attaché à l'action de l'utilisateur. Il doit
            // toutefois attendre la fin réelle d'Atlas.exe avant de toucher
            // C:\Program Files\Atlas.
            startInfo.ArgumentList.Add(
                "--wait-for-process");

            startInfo.ArgumentList.Add(
                Environment.ProcessId.ToString());

            startInfo.ArgumentList.Add(
                "--restart-atlas");

            startInfo.ArgumentList.Add(
                "--progress-file");

            startInfo.ArgumentList.Add(
                progressFile);

            var process =
                System.Diagnostics.Process.Start(
                    startInfo);

            if (process is null)
            {
                throw new InvalidOperationException(
                    "Windows n'a pas pu lancer l'installateur Atlas.");
            }

            UiLog.Info(
                $"Verified Atlas installer launched: version={manifest.Version}, path={verified.FilePath}, sha256={verified.Sha256}");

            await ShutdownAtlasForUpdateAsync();
            Close();
        }
        catch (System.ComponentModel.Win32Exception exception)
        {
            if (exception.NativeErrorCode == 1223)
            {
                UpdateStatusText.Text =
                    "Élévation administrateur annulée.";
                UiLog.Info(
                    "Atlas silent update elevation canceled by user.");
            }
            else
            {
                UpdateStatusText.Text =
                    $"Impossible de lancer l’installateur : {exception.Message}";
                UiLog.Error(
                    "Unable to launch Atlas silent update.",
                    exception);
            }
        }
        catch (InvalidDataException exception)
        {
            _verifiedDownloadedUpdate = null;
            InstallUpdateButton.Visibility = Visibility.Collapsed;
            UpdateStatusText.Text = exception.Message;
            UiLog.Error(
                "Atlas update final integrity validation failed.",
                exception);
        }
        catch (Exception exception)
        {
            UpdateStatusText.Text =
                $"Échec du lancement de la mise à jour : {exception.Message}";
            UiLog.Error(
                "Atlas silent update launch failed.",
                exception);
        }
        finally
        {
            _updateOperationInProgress = false;
            UpdateChannelComboBox.IsEnabled = _updateConfiguration.Channel != "dev";
            DownloadUpdateButton.IsEnabled =
                _availableUpdateManifest is not null
                && !string.IsNullOrWhiteSpace(_availableUpdateManifest.DownloadUrl)
                && !string.IsNullOrWhiteSpace(_availableUpdateManifest.Sha256);

            InstallUpdateButton.IsEnabled =
                _verifiedDownloadedUpdate is not null;
        }
    }

    private async Task ShutdownAtlasForUpdateAsync()
    {
        _taskbarGuardTimer.Stop();
        _taskbarVisibility.Restore();

        try
        {
            if (_ipc.IsConnected)
            {
                var shutdownTask =
                    _ipc.SendCommandAsync("atlas.shutdown_core");

                await Task.WhenAny(
                    shutdownTask,
                    Task.Delay(750));
            }

            if (_coreProcess.OwnsCoreProcess)
            {
                await _coreProcess.WaitForOwnedCoreExitAsync(
                    TimeSpan.FromMilliseconds(2500));

                _coreProcess.StopOwnedCoreIfStillRunning();
            }
        }
        catch (Exception exception)
        {
            UiLog.Error(
                "Atlas Core shutdown before update installer failed.",
                exception);

            try
            {
                _coreProcess.StopOwnedCoreIfStillRunning();
            }
            catch
            {
            }
        }
    }

    private void SettingsAboutNav_Click(
        object sender,
        RoutedEventArgs e)
    {
        SelectSettingsSection(
            "about");

        UpdateAboutSettingsPresentation();
    }

    private void UpdateSecurityOverviewPresentation()
    {
        SecurityPermissionModeText.Text =
            $"Mode : {GetPermissionModeDisplayName(_currentPermissionMode)}";

        SecurityRiskLevelText.Text =
            _currentPermissionMode switch
            {
                "restricted" =>
                    "Niveau de risque : faible",

                "normal" =>
                    "Niveau de risque : modéré",

                "advanced" =>
                    "Niveau de risque : élevé · confirmations selon l’action",

                "administrator" =>
                    "Niveau de risque : administrateur · confirmation requise",

                "jarvis" =>
                    "Niveau de risque : maximal · contrôles Core toujours actifs",

                _ =>
                    "Niveau de risque : non déterminé",
            };

        SecurityCoreStateText.Text =
            _coreConnected
                ? "Core : connecté"
                : "Core : déconnecté";

        SecurityWorkspacePathText.Text =
            string.IsNullOrWhiteSpace(
                _workspaceRoot)
                ? "Non configurée"
                : _workspaceRoot;
    }

    private void UpdateAboutSettingsPresentation()
    {
        AboutVersionText.Text =
            $"Atlas {AtlasVersion}";

        AboutChannelText.Text =
            $"Canal {AtlasReleaseChannel}";

        AboutCoreStatusText.Text =
            _coreConnected
                ? "Connecté"
                : "Déconnecté";

        AboutStoragePathText.Text =
            string.IsNullOrWhiteSpace(
                _workspaceRoot)
                ? "Non configuré"
                : _workspaceRoot;

        AboutMachineNameText.Text =
            Environment.MachineName;

        AboutOperatingSystemText.Text =
            Environment.OSVersion
                .VersionString;

        AboutArchitectureText.Text =
            Environment.Is64BitOperatingSystem
                ? "Windows x64"
                : "Windows x86";
    }

    private void SelectSettingsSection(
        string section)
    {
        SyncSecondarySettingsControls();

        SettingsHomeSection.Visibility =
            section == "home"
                ? Visibility.Visible
                : Visibility.Collapsed;

        SettingsDisplaySection.Visibility =
            section == "display"
                ? Visibility.Visible
                : Visibility.Collapsed;

        SettingsDesktopSection.Visibility =
            section == "desktop"
                ? Visibility.Visible
                : Visibility.Collapsed;

        SettingsNetworkSection.Visibility =
            section == "network"
                ? Visibility.Visible
                : Visibility.Collapsed;

        SettingsVoiceSection.Visibility =
            section == "voice"
                ? Visibility.Visible
                : Visibility.Collapsed;

        SettingsStorageSection.Visibility =
            section == "storage"
                ? Visibility.Visible
                : Visibility.Collapsed;

        SettingsStartupSection.Visibility =
            section == "startup"
                ? Visibility.Visible
                : Visibility.Collapsed;

        SettingsPermissionsSection.Visibility =
            section == "permissions"
                ? Visibility.Visible
                : Visibility.Collapsed;

        SettingsUpdatesSection.Visibility =
            section == "updates"
                ? Visibility.Visible
                : Visibility.Collapsed;

        SettingsAboutSection.Visibility =
            section == "about"
                ? Visibility.Visible
                : Visibility.Collapsed;

        switch (section)
        {
            case "display":
                SettingsPageTitleText.Text =
                    "Affichage";
                SettingsPageSubtitleText.Text =
                    "Configuration de l’écran utilisé par Atlas";
                break;

            case "desktop":
                SettingsPageTitleText.Text =
                    "Bureau";
                SettingsPageSubtitleText.Text =
                    "Disposition des fenêtres et widgets Atlas";
                break;

            case "network":
                SettingsPageTitleText.Text =
                    "Réseau";
                SettingsPageSubtitleText.Text =
                    "Connexion active et configuration réseau locale";
                break;

            case "voice":
                SettingsPageTitleText.Text =
                    "Voix & écoute";
                SettingsPageSubtitleText.Text =
                    "Mode d’écoute et réveil vocal local";
                break;

            case "storage":
                SettingsPageTitleText.Text =
                    "Stockage";
                SettingsPageSubtitleText.Text =
                    "Zone de travail dédiée à Atlas";
                break;

            case "startup":
                SettingsPageTitleText.Text =
                    "Démarrage";
                SettingsPageSubtitleText.Text =
                    "Comportement d’ouverture de session";
                break;

            case "permissions":
                SettingsPageTitleText.Text =
                    "Permissions";
                SettingsPageSubtitleText.Text =
                    "Contrôle des actions autorisées au Core Atlas";
                break;

            case "updates":
                SettingsPageTitleText.Text =
                    "Mises à jour";
                SettingsPageSubtitleText.Text =
                    "Version, canal et disponibilité des nouvelles versions Atlas";
                break;

            case "about":
                SettingsPageTitleText.Text =
                    "À propos";
                SettingsPageSubtitleText.Text =
                    "Informations sur l’interface Atlas";
                break;

            default:
                SettingsPageTitleText.Text =
                    "Accueil";
                SettingsPageSubtitleText.Text =
                    "Vue d’ensemble des paramètres Atlas";
                break;
        }

        ApplySettingsNavState(
            SettingsNavHomeButton,
            section == "home");
        ApplySettingsNavState(
            SettingsNavDisplayButton,
            section == "display");
        ApplySettingsNavState(
            SettingsNavDesktopButton,
            section == "desktop");
        ApplySettingsNavState(
            SettingsNavNetworkButton,
            section == "network");
        ApplySettingsNavState(
            SettingsNavVoiceButton,
            section == "voice");
        ApplySettingsNavState(
            SettingsNavStorageButton,
            section == "storage");
        ApplySettingsNavState(
            SettingsNavStartupButton,
            section == "startup");
        ApplySettingsNavState(
            SettingsNavPermissionsButton,
            section == "permissions");

        ApplySettingsNavState(
            SettingsNavUpdatesButton,
            section == "updates");

        ApplySettingsNavState(
            SettingsNavAboutButton,
            section == "about");
    }

    private void SyncSecondarySettingsControls()
    {
        if (_syncingSettingsControls)
        {
            return;
        }

        _syncingSettingsControls =
            true;

        try
        {
            // Capture impérativement les valeurs AVANT Items.Clear().
            // Le Clear déclenche SelectionChanged sur WinUI.
            var displaySelectedIndex =
                SettingsDisplayComboBox
                    .SelectedIndex;

            var storageSelectedIndex =
                SettingsStorageComboBox
                    .SelectedIndex;

            var startupEnabled =
                SettingsStartupToggle
                    .IsOn;

            SettingsDisplayComboBoxSecondary
                .Items
                .Clear();

            foreach (
                var item
                in SettingsDisplayComboBox
                    .Items
                    .OfType<ComboBoxItem>())
            {
                SettingsDisplayComboBoxSecondary
                    .Items
                    .Add(
                        new ComboBoxItem
                        {
                            Content =
                                item.Content,

                            Tag =
                                item.Tag,
                        });
            }

            SettingsDisplayComboBoxSecondary
                .SelectedIndex =
                displaySelectedIndex;

            SettingsStorageComboBoxSecondary
                .SelectedIndex =
                storageSelectedIndex;

            SettingsStartupToggleSecondary
                .IsOn =
                startupEnabled;
        }
        finally
        {
            _syncingSettingsControls =
                false;
        }
    }

    private void ApplySettingsNavState(
        Button button,
        bool active)
    {
        button.Background =
            CreateBrush(
                active
                    ? "#65343749"
                    : "#3C2B2D3A");

        button.BorderBrush =
            CreateBrush(
                active
                    ? "#5A666A7D"
                    : "#32575B6C");

        if (button.Content is FontIcon icon)
        {
            icon.Foreground =
                CreateBrush(
                    active
                        ? "#67D4FF"
                        : "#DDEEFF");
        }
    }

    private static SolidColorBrush CreateBrush(
        string color)
    {
        return new SolidColorBrush(
            ColorFromHex(color));
    }


    private void MarkSettingsDirty()
    {
        if (
            !_settingsEditingReady
            || _syncingSettingsControls
        )
        {
            return;
        }

        _settingsHasUnsavedChanges =
            true;

        SettingsSaveButton.IsEnabled =
            true;

        SettingsStatusText.Text =
            "Modifications non enregistrées.";
    }

    private void ClearSettingsDirtyState()
    {
        _settingsHasUnsavedChanges =
            false;

        SettingsSaveButton.IsEnabled =
            false;
    }

    private void SettingsDisplayComboBox_SelectionChanged(
        object sender,
        SelectionChangedEventArgs e)
    {
        if (_syncingSettingsControls)
        {
            return;
        }

        if (SettingsDisplayComboBoxSecondary.SelectedIndex
            != SettingsDisplayComboBox.SelectedIndex)
        {
            SettingsDisplayComboBoxSecondary.SelectedIndex =
                SettingsDisplayComboBox.SelectedIndex;
        }

        MarkSettingsDirty();
    }

    private void SettingsDisplayComboBoxSecondary_SelectionChanged(
        object sender,
        SelectionChangedEventArgs e)
    {
        if (_syncingSettingsControls)
        {
            return;
        }

        if (SettingsDisplayComboBox.SelectedIndex
            != SettingsDisplayComboBoxSecondary.SelectedIndex)
        {
            SettingsDisplayComboBox.SelectedIndex =
                SettingsDisplayComboBoxSecondary.SelectedIndex;
        }

        UpdateDisplaySettingsPresentation();
        MarkSettingsDirty();
    }

    private void SettingsStorageComboBox_SelectionChanged(
        object sender,
        SelectionChangedEventArgs e)
    {
        if (_syncingSettingsControls)
        {
            return;
        }

        if (SettingsStorageComboBoxSecondary.SelectedIndex
            != SettingsStorageComboBox.SelectedIndex)
        {
            SettingsStorageComboBoxSecondary.SelectedIndex =
                SettingsStorageComboBox.SelectedIndex;
        }

        MarkSettingsDirty();
    }

    private void SettingsStorageComboBoxSecondary_SelectionChanged(
        object sender,
        SelectionChangedEventArgs e)
    {
        if (_syncingSettingsControls)
        {
            return;
        }

        if (SettingsStorageComboBox.SelectedIndex
            != SettingsStorageComboBoxSecondary.SelectedIndex)
        {
            SettingsStorageComboBox.SelectedIndex =
                SettingsStorageComboBoxSecondary.SelectedIndex;
        }

        UpdateStorageSettingsPresentation();
        MarkSettingsDirty();
    }

    private void UpdateStartupRegistrationPresentation()
    {
        var status =
            _startupRegistration
                .GetStatus();

        StartupRegistrationStatusText.Text =
            status.Enabled
                ? "Actif"
                : "Inactif";

        StartupRegistrationCommandText.Text =
            status.Enabled
            && !string.IsNullOrWhiteSpace(
                status.Command)
                ? status.Command
                : "Aucun lancement automatique Atlas enregistré dans Windows.";
    }

    private void RefreshStartupRegistration_Click(
        object sender,
        RoutedEventArgs e)
    {
        UpdateStartupRegistrationPresentation();
    }

    private void SettingsStartupToggle_Toggled(
        object sender,
        RoutedEventArgs e)
    {
        if (_syncingSettingsControls)
        {
            return;
        }

        if (SettingsStartupToggleSecondary.IsOn
            != SettingsStartupToggle.IsOn)
        {
            SettingsStartupToggleSecondary.IsOn =
                SettingsStartupToggle.IsOn;
        }

        MarkSettingsDirty();
    }

    private void SettingsStartupToggleSecondary_Toggled(
        object sender,
        RoutedEventArgs e)
    {
        if (_syncingSettingsControls)
        {
            return;
        }

        if (SettingsStartupToggle.IsOn
            != SettingsStartupToggleSecondary.IsOn)
        {
            SettingsStartupToggle.IsOn =
                SettingsStartupToggleSecondary.IsOn;
        }

        MarkSettingsDirty();
    }

    private static Windows.UI.Color ColorFromHex(
        string color)
    {
        color = color.TrimStart('#');

        if (color.Length == 6)
        {
            color = "FF" + color;
        }

        var value =
            Convert.ToUInt32(
                color,
                16);

        var a = (byte)((value >> 24) & 0xFF);
        var r = (byte)((value >> 16) & 0xFF);
        var g = (byte)((value >> 8) & 0xFF);
        var b = (byte)(value & 0xFF);

        return Windows.UI.Color.FromArgb(
            a,
            r,
            g,
            b);
    }

    private void SettingsPermissionModeComboBox_SelectionChanged(
        object sender,
        SelectionChangedEventArgs e)
    {
        var mode =
            GetSelectedPermissionMode();

        UpdatePermissionModePresentation(
            mode);

        if (
            !string.Equals(
                mode,
                _currentPermissionMode,
                StringComparison.OrdinalIgnoreCase)
        )
        {
            MarkSettingsDirty();
        }
    }

    private string GetSelectedPermissionMode()
    {
        if (
            SettingsPermissionModeComboBox
                .SelectedItem
            is ComboBoxItem item
            && item.Tag is string mode
        )
        {
            return mode;
        }

        return _currentPermissionMode;
    }

    private void SelectPermissionMode(
        string mode)
    {
        foreach (
            var item
            in SettingsPermissionModeComboBox
                .Items
                .OfType<ComboBoxItem>())
        {
            if (
                item.Tag is string itemMode
                && string.Equals(
                    itemMode,
                    mode,
                    StringComparison.OrdinalIgnoreCase)
            )
            {
                SettingsPermissionModeComboBox
                    .SelectedItem =
                    item;

                return;
            }
        }
    }

    private void UpdatePermissionModePresentation(
        string mode)
    {
        string description;
        string policy;

        switch (mode)
        {
            case "restricted":
                description =
                    "Mode le plus prudent : Atlas peut consulter et exécuter uniquement les actions considérées comme sûres.";

                policy =
                    "Lecture seule : autorisée · Actions sûres : autorisées · Modification locale : refusée · Administrateur : refusé · Critique : refusé";
                break;

            case "normal":
                description =
                    "Usage quotidien avec confirmation avant toute modification locale.";

                policy =
                    "Lecture seule : autorisée · Actions sûres : autorisées · Modification locale : confirmation · Administrateur : refusé · Critique : refusé";
                break;

            case "advanced":
                description =
                    "Atlas peut effectuer les modifications locales directement et demande confirmation pour les actions administrateur.";

                policy =
                    "Lecture seule : autorisée · Actions sûres : autorisées · Modification locale : autorisée · Administrateur : confirmation · Critique : refusé";
                break;

            case "administrator":
                description =
                    "Les actions administrateur sont autorisées sans confirmation systématique. Les actions critiques restent protégées.";

                policy =
                    "Lecture seule : autorisée · Modification locale : autorisée · Administrateur : autorisé · Critique : confirmation";
                break;

            case "jarvis":
                description =
                    "Mode le plus autonome : toutes les actions non critiques autorisées par les Skills peuvent s’exécuter sans confirmation.";

                policy =
                    "Lecture seule : autorisée · Modification locale : autorisée · Administrateur : autorisé · Critique : confirmation obligatoire";
                break;

            default:
                description =
                    "Mode de permissions non reconnu.";

                policy =
                    "Le Core doit fournir un mode valide.";
                break;
        }

        SettingsPermissionModeDescriptionText.Text =
            description;

        SettingsPermissionPolicyText.Text =
            policy;

        SettingsPermissionWarningCard.Visibility =
            mode is "administrator" or "jarvis"
                ? Visibility.Visible
                : Visibility.Collapsed;
    }

    private void ApplyAtlasDialogStyle(
        ContentDialog dialog)
    {
        dialog.RequestedTheme =
            ElementTheme.Dark;

        dialog.Background =
            Root.Resources[
                "AtlasWindowAcrylicBrush"]
            as Brush
            ?? CreateBrush(
                "#CC151620");

        dialog.Foreground =
            CreateBrush(
                "#F1F1F5");

        dialog.BorderBrush =
            Root.Resources[
                "AtlasWindowBorderBrush"]
            as Brush
            ?? CreateBrush(
                "#3C5B5E70");

        dialog.BorderThickness =
            new Thickness(
                1);

        dialog.CornerRadius =
            new CornerRadius(
                10);

        dialog.MinWidth =
            360;

        // Lightweight styling resources used by the default WinUI
        // ContentDialog template and its buttons.
        dialog.Resources[
            "ContentDialogBackground"] =
            dialog.Background;

        dialog.Resources[
            "ContentDialogForeground"] =
            CreateBrush(
                "#F1F1F5");

        dialog.Resources[
            "ContentDialogBorderBrush"] =
            CreateBrush(
                "#3C5B5E70");

        dialog.Resources[
            "ContentDialogSeparatorBorderBrush"] =
            CreateBrush(
                "#26575B6C");

        dialog.Resources[
            "ContentDialogTopOverlay"] =
            CreateBrush(
                "#101A1B26");

        // Keep the Atlas desktop visible instead of heavily dimming it.
        dialog.Resources[
            "ContentDialogSmokeFill"] =
            CreateBrush(
                "#18000000");

        // Secondary / normal buttons.
        dialog.Resources[
            "ButtonBackground"] =
            CreateBrush(
                "#45323543");

        dialog.Resources[
            "ButtonBackgroundPointerOver"] =
            CreateBrush(
                "#663B3E50");

        dialog.Resources[
            "ButtonBackgroundPressed"] =
            CreateBrush(
                "#7A292B39");

        dialog.Resources[
            "ButtonForeground"] =
            CreateBrush(
                "#ECECF2");

        dialog.Resources[
            "ButtonForegroundPointerOver"] =
            CreateBrush(
                "#FFFFFF");

        dialog.Resources[
            "ButtonBorderBrush"] =
            CreateBrush(
                "#355B5F70");

        dialog.Resources[
            "ButtonBorderBrushPointerOver"] =
            CreateBrush(
                "#526A6E80");

        // The ContentDialog default button uses AccentButtonStyle.
        dialog.Resources[
            "AccentButtonBackground"] =
            CreateBrush(
                "#C748BDEA");

        dialog.Resources[
            "AccentButtonBackgroundPointerOver"] =
            CreateBrush(
                "#E05BC9F2");

        dialog.Resources[
            "AccentButtonBackgroundPressed"] =
            CreateBrush(
                "#A83CA3CC");

        dialog.Resources[
            "AccentButtonForeground"] =
            CreateBrush(
                "#07131A");

        dialog.Resources[
            "AccentButtonForegroundPointerOver"] =
            CreateBrush(
                "#061219");
    }

    private async Task<bool> ConfirmElevatedPermissionModeAsync(
        string mode)
    {
        if (
            mode is not "administrator"
            and not "jarvis"
        )
        {
            return true;
        }

        var title =
            mode == "jarvis"
                ? "Activer le mode JARVIS ?"
                : "Activer le mode Administrateur ?";

        var content =
            mode == "jarvis"
                ? "Le mode JARVIS autorise les actions non critiques permises par les Skills sans confirmation préalable. Les actions critiques restent soumises à confirmation."
                : "Le mode Administrateur autorise les actions administrateur permises par les Skills sans confirmation systématique. Les actions critiques restent soumises à confirmation.";

        var dialog =
            new ContentDialog
            {
                Title = title,
                Content = content,
                PrimaryButtonText = "Activer",
                CloseButtonText = "Annuler",
                DefaultButton =
                    ContentDialogButton.Close,
                XamlRoot =
                    Root.XamlRoot,
            };

        ApplyAtlasDialogStyle(
            dialog);

        return (
            await dialog.ShowAsync()
        ) == ContentDialogResult.Primary;
    }

    private async void SaveSettings_Click(
        object sender,
        RoutedEventArgs e)
    {
        if (
            SettingsDisplayComboBoxSecondary
                .SelectedItem
            is ComboBoxItem secondaryDisplayItem)
        {
            SettingsDisplayComboBox.SelectedIndex =
                SettingsDisplayComboBoxSecondary.SelectedIndex;
        }

        SettingsStartupToggle.IsOn =
            SettingsStartupSection.Visibility
            == Visibility.Visible
                ? SettingsStartupToggleSecondary.IsOn
                : SettingsStartupToggle.IsOn;

        if (
            SettingsDisplayComboBox
                .SelectedItem
            is not ComboBoxItem
                displayItem
            || displayItem.Tag
                is not string
                displayId
        )
        {
            await ShowMessageAsync(
                "Paramètres",
                "Sélectionnez un écran Atlas.");

            return;
        }

        var displays =
            _displayService
                .EnumerateDisplays();

        var screenIndex =
            displays
                .ToList()
                .FindIndex(
                    display =>
                        string.Equals(
                            display.DeviceName,
                            displayId,
                            StringComparison.OrdinalIgnoreCase));

        if (screenIndex < 0)
        {
            screenIndex = 0;
        }

        var oldConfig =
            _config.Load();

        var newConfig =
            new AtlasConfig(
                oldConfig.StorageRoot,
                displayId,
                screenIndex,
                SettingsStartupToggle.IsOn);

        try
        {
            _config.Save(
                newConfig);

            _startupRegistration.Apply(
                newConfig.StartWithWindows);

            UpdateStartupRegistrationPresentation();

            var screenChanged =
                !string.Equals(
                    oldConfig.ScreenId,
                    newConfig.ScreenId,
                    StringComparison.OrdinalIgnoreCase)
                || oldConfig.ScreenIndex
                    != newConfig.ScreenIndex;

            if (screenChanged)
            {
                ConfigureWindowBounds();
            }

            var selectedPermissionMode =
                GetSelectedPermissionMode();

            var permissionModeChanged =
                !string.Equals(
                    selectedPermissionMode,
                    _currentPermissionMode,
                    StringComparison.OrdinalIgnoreCase);

            if (permissionModeChanged)
            {
                if (
                    !await ConfirmElevatedPermissionModeAsync(
                        selectedPermissionMode)
                )
                {
                    SelectPermissionMode(
                        _currentPermissionMode);

                    UpdatePermissionModePresentation(
                        _currentPermissionMode);

                    SettingsStatusText.Text =
                        "Paramètres enregistrés · changement de permissions annulé.";

                    return;
                }

                if (!_ipc.IsConnected)
                {
                    await ShowMessageAsync(
                        "Core non connecté",
                        "Le mode de permissions n’a pas été modifié car Atlas Core n’est pas connecté.");

                    SelectPermissionMode(
                        _currentPermissionMode);

                    return;
                }

                var permissionCommandSent =
                    await _ipc.SendCommandAsync(
                        "security.set_permission_mode",
                        new
                        {
                            mode =
                                selectedPermissionMode,

                            confirmed =
                                selectedPermissionMode
                                is "administrator"
                                or "jarvis",
                        });

                if (!permissionCommandSent)
                {
                    await ShowMessageAsync(
                        "Permissions",
                        "Impossible d’envoyer la modification de permissions au Core.");

                    SelectPermissionMode(
                        _currentPermissionMode);

                    return;
                }
            }

            SettingsStatusText.Text =
                permissionModeChanged
                        ? "Paramètres enregistrés · application du mode de permissions…"
                        : "Paramètres enregistrés.";

            ClearSettingsDirtyState();

            UiLog.Info(
                "Atlas settings saved from native UI.");
        }
        catch (Exception exception)
        {
            UiLog.Error(
                "Unable to save Atlas settings.",
                exception);

            await ShowMessageAsync(
                "Enregistrement impossible",
                exception.Message);
        }
    }

    private void NavigateToDirectory(
        string directory,
        bool addHistory = true)
    {
        try
        {
            var resolved =
                IOPath.GetFullPath(
                    directory);

            var rootResolved =
                IOPath.GetFullPath(
                    _workspaceRoot);

            if (
                !resolved.StartsWith(
                    rootResolved,
                    StringComparison.OrdinalIgnoreCase)
            )
            {
                return;
            }

            if (!Directory.Exists(
                    resolved))
            {
                return;
            }

            if (
                addHistory
                && !string.IsNullOrWhiteSpace(
                    _currentDirectory)
                && !string.Equals(
                    _currentDirectory,
                    resolved,
                    StringComparison.OrdinalIgnoreCase)
            )
            {
                _activePrimaryExplorerTab?.BackHistory.Push(
                    _currentDirectory);

                _activePrimaryExplorerTab?.ForwardHistory.Clear();
            }

            _currentDirectory =
                resolved;

            ClearSelection();

            if (_activePrimaryExplorerTab is not null)
            {
                _activePrimaryExplorerTab.Directory = resolved;
            }

            WorkspacePathText.Text =
                rootResolved;

            BreadcrumbText.Text =
                BuildBreadcrumb(
                    resolved);

            var tabDisplayName =
                GetExplorerTabDisplayName(
                    resolved);

            SearchBox.PlaceholderText =
                "Rechercher dans "
                + tabDisplayName;

            UpdatePrimaryExplorerTabVisuals();

            RenderDirectory(
                SearchBox.Text);

            SavePrimaryExplorerTabs();
        }
        catch (Exception exception)
        {
            UiLog.Error(
                "Explorer navigation failed.",
                exception);
        }
    }

    private string BuildBreadcrumb(
        string directory)
    {
        var root =
            IOPath.GetFullPath(
                _workspaceRoot);

        var current =
            IOPath.GetFullPath(
                directory);

        if (string.Equals(
                root,
                current,
                StringComparison.OrdinalIgnoreCase))
        {
            return "Atlas";
        }

        var relative =
            IOPath.GetRelativePath(
                root,
                current);

        return "Atlas  ›  "
            + relative.Replace(
                IOPath.DirectorySeparatorChar,
                '›');
    }

    private void RenderDirectory(
        string? search)
    {
        FolderList.Children.Clear();
        IconGrid.Items.Clear();

        _entryButtons.Clear();
        _visiblePaths.Clear();

        IEnumerable<string> entries;

        try
        {
            entries =
                Directory
                    .EnumerateFileSystemEntries(
                        _currentDirectory);
        }
        catch
        {
            entries =
                Array.Empty<string>();
        }

        if (!string.IsNullOrWhiteSpace(
                search))
        {
            entries =
                entries.Where(
                    path =>
                        IOPath.GetFileName(
                            path)
                        .Contains(
                            search.Trim(),
                            StringComparison
                                .CurrentCultureIgnoreCase));
        }

        entries =
            SortEntries(
                entries);

        var list =
            entries.ToArray();

        _visiblePaths.AddRange(
            list);

        foreach (var entry in list)
        {
            if (
                _viewMode
                == ExplorerViewMode.Icons
            )
            {
                IconGrid.Items.Add(
                    CreateIconEntry(
                        entry));
            }
            else
            {
                FolderList.Children.Add(
                    CreateEntryRow(
                        entry));
            }
        }

        StatusText.Text =
            list.Length switch
            {
                0 => "Aucun élément",
                1 => "1 élément",
                _ => $"{list.Length} éléments",
            };

        UpdateSelectionUi();
    }

    private UIElement CreateIconEntry(
        string path)
    {
        var isDirectory =
            Directory.Exists(
                path);

        var name =
            IOPath.GetFileName(
                path);

        var content =
            new Grid
            {
                Width = 138,
                Height = 98,
            };

        content.RowDefinitions.Add(
            new RowDefinition
            {
                Height =
                    new GridLength(
                        1,
                        GridUnitType.Star),
            });

        content.RowDefinitions.Add(
            new RowDefinition
            {
                Height =
                    new GridLength(
                        34),
            });

        var iconHost =
            new Grid
            {
                HorizontalAlignment =
                    HorizontalAlignment.Center,
                VerticalAlignment =
                    VerticalAlignment.Center,
            };

        var glow =
            new Border
            {
                Width = 58,
                Height = 58,
                CornerRadius =
                    new CornerRadius(
                        18),
                Background =
                    new SolidColorBrush(
                        Windows.UI.Color.FromArgb(
                            22,
                            85,
                            200,
                            255)),
                HorizontalAlignment =
                    HorizontalAlignment.Center,
                VerticalAlignment =
                    VerticalAlignment.Center,
            };

        iconHost.Children.Add(
            glow);

        iconHost.Children.Add(
            new FontIcon
            {
                Glyph =
                    isDirectory
                        ? "\uE8B7"
                        : "\uE8A5",
                FontSize =
                    isDirectory
                        ? 34
                        : 30,
                Foreground =
                    new SolidColorBrush(
                        Windows.UI.Color.FromArgb(
                            255,
                            85,
                            200,
                            255)),
                HorizontalAlignment =
                    HorizontalAlignment.Center,
                VerticalAlignment =
                    VerticalAlignment.Center,
            });

        content.Children.Add(
            iconHost);

        var label =
            new TextBlock
            {
                Text = name,
                FontSize = 11,
                FontWeight =
                    Microsoft.UI.Text
                        .FontWeights.SemiBold,
                Foreground =
                    new SolidColorBrush(
                        Windows.UI.Color.FromArgb(
                            255,
                            231,
                            245,
                            255)),
                TextAlignment =
                    TextAlignment.Center,
                TextTrimming =
                    TextTrimming.CharacterEllipsis,
                MaxLines = 2,
                HorizontalAlignment =
                    HorizontalAlignment.Stretch,
                VerticalAlignment =
                    VerticalAlignment.Center,
                Margin =
                    new Thickness(
                        5,
                        0,
                        5,
                        0),
            };

        Grid.SetRow(
            label,
            1);

        content.Children.Add(
            label);

        var button =
            new Button
            {
                Style =
                    Root.Resources[
                        "AtlasExplorerEntryButtonStyle"]
                    as Style,
                Width = 146,
                Height = 108,
                Padding =
                    new Thickness(
                        4),
                CornerRadius =
                    new CornerRadius(
                        14),
                HorizontalContentAlignment =
                    HorizontalAlignment.Center,
                VerticalContentAlignment =
                    VerticalAlignment.Center,
                Content = content,
                Tag = path,
            };

        button.Click +=
            (_, _) =>
            {
                SelectEntry(
                    path);
            };

        button.DoubleTapped +=
            (_, _) =>
            {
                ActivateEntry(
                    path);
            };

        button.ContextFlyout =
            CreateEntryContextMenu(
                path);

        _entryButtons[
            path
        ] = button;

        return button;
    }

    private UIElement CreateEntryRow(
        string path)
    {
        var isDirectory =
            Directory.Exists(
                path);

        var info =
            isDirectory
                ? null
                : new FileInfo(
                    path);

        var grid =
            new Grid
            {
                Height =
                    _viewMode
                    == ExplorerViewMode.Compact
                        ? 32
                        : 42,
            };

        grid.ColumnDefinitions.Add(
            new ColumnDefinition
            {
                Width =
                    new GridLength(
                        368),
            });

        grid.ColumnDefinitions.Add(
            new ColumnDefinition
            {
                Width =
                    new GridLength(
                        150),
            });

        grid.ColumnDefinitions.Add(
            new ColumnDefinition
            {
                Width =
                    new GridLength(
                        190),
            });

        grid.ColumnDefinitions.Add(
            new ColumnDefinition
            {
                Width =
                    new GridLength(
                        120),
            });

        grid.ColumnDefinitions.Add(
            new ColumnDefinition
            {
                Width =
                    new GridLength(
                        1,
                        GridUnitType.Star),
            });

        var namePanel =
            new StackPanel
            {
                Orientation =
                    Orientation.Horizontal,
                Spacing = 9,
                VerticalAlignment =
                    VerticalAlignment.Center,
            };

        namePanel.Children.Add(
            new FontIcon
            {
                Glyph =
                    isDirectory
                        ? "\uE8B7"
                        : "\uE8A5",
                FontSize =
                    _viewMode
                    == ExplorerViewMode.Compact
                        ? 13
                        : 15,
                Foreground =
                    new SolidColorBrush(
                        Windows.UI.Color.FromArgb(
                            255,
                            85,
                            200,
                            255)),
            });

        namePanel.Children.Add(
            new TextBlock
            {
                Text =
                    IOPath.GetFileName(
                        path),
                FontSize =
                    _viewMode
                    == ExplorerViewMode.Compact
                        ? 11
                        : 12,
                FontWeight =
                    Microsoft.UI.Text
                        .FontWeights.SemiBold,
                Foreground =
                    new SolidColorBrush(
                        Windows.UI.Color.FromArgb(
                            255,
                            231,
                            245,
                            255)),
                VerticalAlignment =
                    VerticalAlignment.Center,
            });

        grid.Children.Add(
            namePanel);

        var typeText =
            new TextBlock
            {
                Text =
                    isDirectory
                        ? "Dossier"
                        : GetDisplayType(
                            path),
                FontSize = 11,
                Foreground =
                    new SolidColorBrush(
                        Windows.UI.Color.FromArgb(
                            190,
                            126,
                            165,
                            187)),
                VerticalAlignment =
                    VerticalAlignment.Center,
            };

        Grid.SetColumn(
            typeText,
            1);

        grid.Children.Add(
            typeText);

        DateTime modified;

        try
        {
            modified =
                File.GetLastWriteTime(
                    path);
        }
        catch
        {
            modified =
                DateTime.MinValue;
        }

        var modifiedText =
            new TextBlock
            {
                Text =
                    modified == DateTime.MinValue
                        ? ""
                        : modified.ToString(
                            "dd/MM/yyyy HH:mm"),
                FontSize = 11,
                Foreground =
                    new SolidColorBrush(
                        Windows.UI.Color.FromArgb(
                            180,
                            126,
                            165,
                            187)),
                VerticalAlignment =
                    VerticalAlignment.Center,
            };

        Grid.SetColumn(
            modifiedText,
            2);

        grid.Children.Add(
            modifiedText);

        var sizeText =
            new TextBlock
            {
                Text =
                    isDirectory
                        ? ""
                        : FormatSize(
                            info?.Length ?? 0),
                FontSize = 11,
                Foreground =
                    new SolidColorBrush(
                        Windows.UI.Color.FromArgb(
                            180,
                            126,
                            165,
                            187)),
                VerticalAlignment =
                    VerticalAlignment.Center,
            };

        Grid.SetColumn(
            sizeText,
            3);

        grid.Children.Add(
            sizeText);

        var button =
            new Button
            {
                Style =
                    Root.Resources[
                        "AtlasExplorerEntryButtonStyle"]
                    as Style,
                Content = grid,
                Tag = path,
            };

        button.Click +=
            (_, _) =>
            {
                SelectEntry(
                    path);
            };

        button.DoubleTapped +=
            (_, _) =>
            {
                ActivateEntry(
                    path);
            };

        button.ContextFlyout =
            CreateEntryContextMenu(
                path);

        _entryButtons[
            path
        ] = button;

        return button;
    }

    private MenuFlyout CreateEntryContextMenu(
        string path)
    {
        var menu =
            new MenuFlyout();

        var open =
            new MenuFlyoutItem
            {
                Text = "Ouvrir",
                Icon =
                    new FontIcon
                    {
                        Glyph = "\uE8B7",
                    },
            };

        open.Click +=
            (_, _) =>
            {
                ActivateEntry(
                    path);
            };

        menu.Items.Add(
            open);

        menu.Items.Add(
            new MenuFlyoutSeparator());

        var rename =
            new MenuFlyoutItem
            {
                Text = "Renommer",
            };

        rename.Click +=
            async (_, _) =>
            {
                SelectOnly(
                    path);

                await RenameSelectedAsync();
            };

        menu.Items.Add(
            rename);

        var copy =
            new MenuFlyoutItem
            {
                Text = "Copier",
            };

        copy.Click +=
            (_, _) =>
            {
                SelectOnly(
                    path);

                CopySelection(
                    false);
            };

        menu.Items.Add(
            copy);

        var cut =
            new MenuFlyoutItem
            {
                Text = "Couper",
            };

        cut.Click +=
            (_, _) =>
            {
                SelectOnly(
                    path);

                CopySelection(
                    true);
            };

        menu.Items.Add(
            cut);

        menu.Items.Add(
            new MenuFlyoutSeparator());

        var delete =
            new MenuFlyoutItem
            {
                Text = "Supprimer",
            };

        delete.Click +=
            async (_, _) =>
            {
                SelectOnly(
                    path);

                await DeleteSelectedAsync();
            };

        menu.Items.Add(
            delete);

        return menu;
    }

    private void ExplorerContentSurface_PointerPressed(
        object sender,
        PointerRoutedEventArgs e)
    {
        if (
            IsPointerOverExplorerEntry(
                e.OriginalSource
                as DependencyObject)
        )
        {
            return;
        }

        ClearSelection();
    }

    private bool IsPointerOverExplorerEntry(
        DependencyObject? source)
    {
        var current =
            source;

        while (
            current is not null
            && current != ExplorerContentSurface
        )
        {
            if (
                current is Button button
                && button.Tag is string path
                && _entryButtons.TryGetValue(
                    path,
                    out var registeredButton)
                && ReferenceEquals(
                    button,
                    registeredButton)
            )
            {
                return true;
            }

            current =
                VisualTreeHelper.GetParent(
                    current);
        }

        return false;
    }

    private void SelectEntry(
        string path)
    {
        var controlPressed =
            IsModifierDown(
                VirtualKey.Control);

        var shiftPressed =
            IsModifierDown(
                VirtualKey.Shift);

        if (
            shiftPressed
            && !string.IsNullOrWhiteSpace(
                _selectionAnchorPath)
        )
        {
            SelectRange(
                _selectionAnchorPath,
                path,
                preserveExisting:
                    controlPressed);

            return;
        }

        if (controlPressed)
        {
            if (
                !_selectedPaths.Add(
                    path)
            )
            {
                _selectedPaths.Remove(
                    path);
            }

            _selectionAnchorPath =
                path;

            UpdateSelectionUi();

            return;
        }

        SelectOnly(
            path);
    }

    private static bool IsModifierDown(
        VirtualKey key)
    {
        var state =
            InputKeyboardSource
                .GetKeyStateForCurrentThread(
                    key);

        return (
            state
            & CoreVirtualKeyStates.Down
        ) == CoreVirtualKeyStates.Down;
    }

    private void SelectRange(
        string anchorPath,
        string currentPath,
        bool preserveExisting)
    {
        var anchorIndex =
            _visiblePaths.FindIndex(
                path =>
                    string.Equals(
                        path,
                        anchorPath,
                        StringComparison.OrdinalIgnoreCase));

        var currentIndex =
            _visiblePaths.FindIndex(
                path =>
                    string.Equals(
                        path,
                        currentPath,
                        StringComparison.OrdinalIgnoreCase));

        if (
            anchorIndex < 0
            || currentIndex < 0
        )
        {
            SelectOnly(
                currentPath);

            return;
        }

        if (!preserveExisting)
        {
            _selectedPaths.Clear();
        }

        var first =
            Math.Min(
                anchorIndex,
                currentIndex);

        var last =
            Math.Max(
                anchorIndex,
                currentIndex);

        for (
            var index = first;
            index <= last;
            index++
        )
        {
            _selectedPaths.Add(
                _visiblePaths[
                    index
                ]);
        }

        UpdateSelectionUi();
    }

    private void SelectOnly(
        string path)
    {
        _selectedPaths.Clear();

        _selectedPaths.Add(
            path);

        _selectionAnchorPath =
            path;

        UpdateSelectionUi();
    }

    private void ClearSelection()
    {
        _selectedPaths.Clear();

        _selectionAnchorPath =
            null;

        UpdateSelectionUi();
    }

    private void UpdateSelectionUi()
    {
        foreach (
            var pair
            in _entryButtons)
        {
            var selected =
                _selectedPaths.Contains(
                    pair.Key);

            pair.Value.Background =
                new SolidColorBrush(
                    selected
                        ? Windows.UI.Color.FromArgb(
                            55,
                            46,
                            95,
                            126)
                        : Windows.UI.Color.FromArgb(
                            7,
                            27,
                            39,
                            52));

            pair.Value.BorderBrush =
                new SolidColorBrush(
                    selected
                        ? Windows.UI.Color.FromArgb(
                            120,
                            85,
                            200,
                            255)
                        : Windows.UI.Color.FromArgb(
                            20,
                            119,
                            158,
                            187));
        }

        SelectionStatusText.Text =
            _selectedPaths.Count switch
            {
                0 => "",
                1 => "1 sélectionné",
                _ => $"{_selectedPaths.Count} sélectionnés",
            };

        var hasSelection =
            _selectedPaths.Count > 0;

        CutButton.IsEnabled =
            hasSelection;

        CopyButton.IsEnabled =
            hasSelection;

        DeleteButton.IsEnabled =
            hasSelection;

        MoreButton.IsEnabled =
            _selectedPaths.Count == 1;

        PasteButton.IsEnabled =
            _clipboardPaths.Count > 0;
    }

    private IEnumerable<string> SortEntries(
        IEnumerable<string> entries)
    {
        var directories =
            entries.Where(
                path =>
                    Directory.Exists(
                        path));

        var files =
            entries.Where(
                path =>
                    !Directory.Exists(
                        path));

        return SortGroup(
                directories)
            .Concat(
                SortGroup(
                    files));
    }

    private IEnumerable<string> SortGroup(
        IEnumerable<string> entries)
    {
        return _sortColumn switch
        {
            ExplorerSortColumn.Type =>
                ApplyDirection(
                    entries,
                    path =>
                        GetSortType(
                            path),
                    StringComparer
                        .CurrentCultureIgnoreCase),

            ExplorerSortColumn.Modified =>
                ApplyDirection(
                    entries,
                    path =>
                        GetSafeModifiedTime(
                            path)),

            ExplorerSortColumn.Size =>
                ApplyDirection(
                    entries,
                    path =>
                        GetSafeSize(
                            path)),

            _ =>
                ApplyDirection(
                    entries,
                    path =>
                        IOPath.GetFileName(
                            path),
                    StringComparer
                        .CurrentCultureIgnoreCase),
        };
    }

    private IEnumerable<string> ApplyDirection<TKey>(
        IEnumerable<string> entries,
        Func<string, TKey> selector)
    {
        return _sortAscending
            ? entries.OrderBy(
                selector)
            : entries.OrderByDescending(
                selector);
    }

    private IEnumerable<string> ApplyDirection<TKey>(
        IEnumerable<string> entries,
        Func<string, TKey> selector,
        IComparer<TKey> comparer)
    {
        return _sortAscending
            ? entries.OrderBy(
                selector,
                comparer)
            : entries.OrderByDescending(
                selector,
                comparer);
    }

    private static string GetSortType(
        string path)
    {
        return Directory.Exists(
                path)
            ? "Dossier"
            : IOPath.GetExtension(
                path);
    }

    private static DateTime GetSafeModifiedTime(
        string path)
    {
        try
        {
            return File.GetLastWriteTime(
                path);
        }
        catch
        {
            return DateTime.MinValue;
        }
    }

    private static long GetSafeSize(
        string path)
    {
        try
        {
            return Directory.Exists(
                    path)
                ? -1
                : new FileInfo(
                    path).Length;
        }
        catch
        {
            return -1;
        }
    }

    private void ApplySort(
        ExplorerSortColumn column)
    {
        if (_sortColumn == column)
        {
            _sortAscending =
                !_sortAscending;
        }
        else
        {
            _sortColumn =
                column;

            _sortAscending =
                true;
        }

        UpdateSortIndicators();

        RenderDirectory(
            SearchBox.Text);
    }

    private void UpdateSortIndicators()
    {
        SortNameIndicator.Text = "";
        SortTypeIndicator.Text = "";
        SortModifiedIndicator.Text = "";
        SortSizeIndicator.Text = "";

        var indicator =
            _sortAscending
                ? "↑"
                : "↓";

        switch (_sortColumn)
        {
            case ExplorerSortColumn.Name:
                SortNameIndicator.Text =
                    indicator;
                break;

            case ExplorerSortColumn.Type:
                SortTypeIndicator.Text =
                    indicator;
                break;

            case ExplorerSortColumn.Modified:
                SortModifiedIndicator.Text =
                    indicator;
                break;

            case ExplorerSortColumn.Size:
                SortSizeIndicator.Text =
                    indicator;
                break;
        }
    }

    private void SortName_Click(
        object sender,
        RoutedEventArgs e)
    {
        ApplySort(
            ExplorerSortColumn.Name);
    }

    private void SortType_Click(
        object sender,
        RoutedEventArgs e)
    {
        ApplySort(
            ExplorerSortColumn.Type);
    }

    private void SortModified_Click(
        object sender,
        RoutedEventArgs e)
    {
        ApplySort(
            ExplorerSortColumn.Modified);
    }

    private void SortSize_Click(
        object sender,
        RoutedEventArgs e)
    {
        ApplySort(
            ExplorerSortColumn.Size);
    }

    private void DetailsView_Click(
        object sender,
        RoutedEventArgs e)
    {
        SetViewMode(
            ExplorerViewMode.Details);
    }

    private void CompactView_Click(
        object sender,
        RoutedEventArgs e)
    {
        SetViewMode(
            ExplorerViewMode.Compact);
    }

    private void IconView_Click(
        object sender,
        RoutedEventArgs e)
    {
        SetViewMode(
            ExplorerViewMode.Icons);
    }

    private void SetViewMode(
        ExplorerViewMode mode)
    {
        if (_viewMode == mode)
        {
            UpdateViewPresentation();

            return;
        }

        _viewMode =
            mode;

        UpdateViewPresentation();

        RenderDirectory(
            SearchBox.Text);
    }

    private void UpdateViewPresentation()
    {
        var icons =
            _viewMode
            == ExplorerViewMode.Icons;

        DetailsScroller.Visibility =
            icons
                ? Visibility.Collapsed
                : Visibility.Visible;

        IconGrid.Visibility =
            icons
                ? Visibility.Visible
                : Visibility.Collapsed;

        UpdateViewButtons();
    }

    private void UpdateViewButtons()
    {
        DetailsViewButton.Opacity =
            _viewMode
            == ExplorerViewMode.Details
                ? 1.0
                : 0.55;

        CompactViewButton.Opacity =
            _viewMode
            == ExplorerViewMode.Compact
                ? 1.0
                : 0.55;

        IconViewButton.Opacity =
            _viewMode
            == ExplorerViewMode.Icons
                ? 1.0
                : 0.55;
    }

    private void CopySelection(
        bool move)
    {
        if (_selectedPaths.Count == 0)
        {
            return;
        }

        _clipboardPaths =
            _selectedPaths
                .ToArray();

        _clipboardMove =
            move;

        PasteButton.IsEnabled =
            true;

        SelectionStatusText.Text =
            move
                ? $"{_clipboardPaths.Count} prêt(s) à déplacer"
                : $"{_clipboardPaths.Count} prêt(s) à copier";
    }

    private async Task NewFolderAsync()
    {
        if (_workspaceFiles is null)
        {
            return;
        }

        var name =
            await PromptTextAsync(
                "Nouveau dossier",
                "Nom du dossier",
                "Nouveau dossier");

        if (name is null)
        {
            return;
        }

        try
        {
            _workspaceFiles.CreateFolder(
                _currentDirectory,
                name);

            RenderDirectory(
                SearchBox.Text);
        }
        catch (Exception exception)
        {
            await ShowMessageAsync(
                "Création impossible",
                exception.Message);
        }
    }

    private async Task RenameSelectedAsync()
    {
        if (
            _workspaceFiles is null
            || _selectedPaths.Count != 1
        )
        {
            return;
        }

        var source =
            _selectedPaths.First();

        var currentName =
            IOPath.GetFileName(
                source);

        var name =
            await PromptTextAsync(
                "Renommer",
                "Nouveau nom",
                currentName);

        if (name is null)
        {
            return;
        }

        try
        {
            _workspaceFiles.Rename(
                source,
                name);

            ClearSelection();

            RenderDirectory(
                SearchBox.Text);
        }
        catch (Exception exception)
        {
            await ShowMessageAsync(
                "Renommage impossible",
                exception.Message);
        }
    }

    private async Task DeleteSelectedAsync()
    {
        if (
            _workspaceFiles is null
            || _selectedPaths.Count == 0
        )
        {
            return;
        }

        var dialog =
            new ContentDialog
            {
                Title = "Supprimer",
                Content =
                    _selectedPaths.Count == 1
                        ? "Supprimer définitivement cet élément ?"
                        : $"Supprimer définitivement les {_selectedPaths.Count} éléments sélectionnés ?",
                PrimaryButtonText = "Supprimer",
                CloseButtonText = "Annuler",
                DefaultButton =
                    ContentDialogButton.Close,
                XamlRoot =
                    Root.XamlRoot,
            };

        ApplyAtlasDialogStyle(
            dialog);

        var result =
            await dialog.ShowAsync();

        if (
            result
            != ContentDialogResult.Primary
        )
        {
            return;
        }

        try
        {
            _workspaceFiles.Delete(
                _selectedPaths);

            ClearSelection();

            RenderDirectory(
                SearchBox.Text);
        }
        catch (Exception exception)
        {
            await ShowMessageAsync(
                "Suppression impossible",
                exception.Message);
        }
    }

    private async Task PasteAsync()
    {
        if (
            _workspaceFiles is null
            || _clipboardPaths.Count == 0
        )
        {
            return;
        }

        try
        {
            _workspaceFiles.CopyIntoDirectory(
                _clipboardPaths,
                _currentDirectory,
                _clipboardMove);

            if (_clipboardMove)
            {
                _clipboardPaths =
                    Array.Empty<string>();

                _clipboardMove =
                    false;
            }

            ClearSelection();

            RenderDirectory(
                SearchBox.Text);
        }
        catch (Exception exception)
        {
            await ShowMessageAsync(
                "Collage impossible",
                exception.Message);
        }
    }

    private async Task<string?> PromptTextAsync(
        string title,
        string label,
        string initialValue)
    {
        var input =
            new TextBox
            {
                Text = initialValue,
                Header = label,
                SelectionStart = 0,
                SelectionLength =
                    initialValue.Length,
                MinWidth = 360,
            };

        var dialog =
            new ContentDialog
            {
                Title = title,
                Content = input,
                PrimaryButtonText = "Valider",
                CloseButtonText = "Annuler",
                DefaultButton =
                    ContentDialogButton.Primary,
                XamlRoot =
                    Root.XamlRoot,
            };

        ApplyAtlasDialogStyle(
            dialog);

        var result =
            await dialog.ShowAsync();

        if (
            result
            != ContentDialogResult.Primary
        )
        {
            return null;
        }

        return input.Text;
    }

    private async Task ShowMessageAsync(
        string title,
        string message)
    {
        var dialog =
            new ContentDialog
            {
                Title = title,
                Content = message,
                CloseButtonText = "Fermer",
                XamlRoot =
                    Root.XamlRoot,
            };

        ApplyAtlasDialogStyle(
            dialog);

        await dialog.ShowAsync();
    }

    private async void NewFolder_Click(
        object sender,
        RoutedEventArgs e)
    {
        await NewFolderAsync();
    }

    private void Cut_Click(
        object sender,
        RoutedEventArgs e)
    {
        CopySelection(
            true);
    }

    private void Copy_Click(
        object sender,
        RoutedEventArgs e)
    {
        CopySelection(
            false);
    }

    private async void Paste_Click(
        object sender,
        RoutedEventArgs e)
    {
        await PasteAsync();
    }

    private async void Delete_Click(
        object sender,
        RoutedEventArgs e)
    {
        await DeleteSelectedAsync();
    }

    private async void Rename_Click(
        object sender,
        RoutedEventArgs e)
    {
        await RenameSelectedAsync();
    }

    private void ActivateEntry(
        string path)
    {
        if (Directory.Exists(
                path))
        {
            NavigateToDirectory(
                path);

            return;
        }

        try
        {
            System.Diagnostics.Process.Start(
                new System.Diagnostics.ProcessStartInfo
                {
                    FileName = path,
                    UseShellExecute = true,
                });
        }
        catch (Exception exception)
        {
            UiLog.Error(
                "Opening file failed.",
                exception);
        }
    }

    private static string GetDisplayType(
        string path)
    {
        var extension =
            IOPath.GetExtension(
                path);

        if (string.IsNullOrWhiteSpace(
                extension))
        {
            return "Fichier";
        }

        return extension
            .TrimStart('.')
            .ToUpperInvariant()
            + " — Fichier";
    }

    private static string FormatSize(
        long bytes)
    {
        string[] units =
        {
            "o",
            "Ko",
            "Mo",
            "Go",
            "To",
        };

        double value =
            bytes;

        var unit =
            0;

        while (
            value >= 1024
            && unit < units.Length - 1
        )
        {
            value /= 1024;
            unit++;
        }

        return unit == 0
            ? $"{value:0} {units[unit]}"
            : $"{value:0.##} {units[unit]}";
    }

    private async void FilesPanel_KeyDown(
        object sender,
        KeyRoutedEventArgs e)
    {
        var ctrl = IsModifierDown(VirtualKey.Control);
        var alt = IsModifierDown(VirtualKey.Menu);
        var shift = IsModifierDown(VirtualKey.Shift);

        var textInputActive =
            e.OriginalSource
            is TextBox;

        if (
            textInputActive
            && (
                (
                    ctrl
                    && (
                        e.Key == VirtualKey.A
                        || e.Key == VirtualKey.C
                        || e.Key == VirtualKey.X
                        || e.Key == VirtualKey.V
                    )
                )
                || e.Key == VirtualKey.F2
                || e.Key == VirtualKey.Delete
            )
        )
        {
            return;
        }

        if (ctrl && e.Key == VirtualKey.A)
        {
            _selectedPaths.Clear();

            foreach (var path in _visiblePaths)
            {
                _selectedPaths.Add(path);
            }

            _selectionAnchorPath =
                _visiblePaths.LastOrDefault();

            UpdateSelectionUi();

            e.Handled = true;
            return;
        }

        if (ctrl && e.Key == VirtualKey.C)
        {
            CopySelection(false);
            e.Handled = true;
            return;
        }

        if (ctrl && e.Key == VirtualKey.X)
        {
            CopySelection(true);
            e.Handled = true;
            return;
        }

        if (ctrl && e.Key == VirtualKey.V)
        {
            await PasteAsync();
            e.Handled = true;
            return;
        }

        if (e.Key == VirtualKey.F2)
        {
            await RenameSelectedAsync();
            e.Handled = true;
            return;
        }

        if (e.Key == VirtualKey.Delete)
        {
            await DeleteSelectedAsync();
            e.Handled = true;
            return;
        }

        if (ctrl && e.Key == VirtualKey.T)
        {
            NewExplorerTab_Click(sender, new RoutedEventArgs());
            e.Handled = true;
            return;
        }

        if (ctrl && e.Key == VirtualKey.W)
        {
            if (_activePrimaryExplorerTab is not null)
            {
                ClosePrimaryExplorerTab(_activePrimaryExplorerTab);
            }
            e.Handled = true;
            return;
        }

        if (ctrl && e.Key == VirtualKey.L)
        {
            ExplorerAddressBox.Text = _currentDirectory;
            ExplorerAddressBox.Visibility = Visibility.Visible;
            ExplorerAddressBox.Focus(FocusState.Programmatic);
            ExplorerAddressBox.SelectAll();
            e.Handled = true;
            return;
        }

        if (ctrl && e.Key == VirtualKey.F)
        {
            SearchBox.Focus(
                FocusState.Programmatic);

            SearchBox.SelectAll();

            e.Handled = true;
            return;
        }

        if (
            ctrl
            && shift
            && e.Key == VirtualKey.N
        )
        {
            await NewFolderAsync();

            e.Handled = true;
            return;
        }

        if (ctrl && e.Key == VirtualKey.N)
        {
            var directory =
                string.IsNullOrWhiteSpace(
                    _currentDirectory)
                    ? _workspaceRoot
                    : _currentDirectory;

            OpenSecondaryExplorerWindow(
                directory);

            e.Handled = true;
            return;
        }

        if (
            !textInputActive
            && e.Key == VirtualKey.Enter
        )
        {
            if (_selectedPaths.Count == 1)
            {
                var selectedPath =
                    _selectedPaths.First();

                ActivateEntry(
                    selectedPath);
            }

            e.Handled = true;
            return;
        }

        if (
            !textInputActive
            && e.Key == VirtualKey.Back
        )
        {
            NavigatePrimaryExplorerBack();

            e.Handled = true;
            return;
        }

        if (e.Key == VirtualKey.F5)
        {
            RenderDirectory(
                SearchBox.Text);

            e.Handled = true;
            return;
        }

        if (alt && e.Key == VirtualKey.Up)
        {
            Up_Click(
                sender,
                new RoutedEventArgs());

            e.Handled = true;
            return;
        }

        if (alt && e.Key == VirtualKey.Left)
        {
            NavigatePrimaryExplorerBack();
            e.Handled = true;
            return;
        }

        if (alt && e.Key == VirtualKey.Right)
        {
            NavigatePrimaryExplorerForward();
            e.Handled = true;
        }
    }

    private void ExplorerAddressBox_KeyDown(
        object sender,
        KeyRoutedEventArgs e)
    {
        if (e.Key == VirtualKey.Escape)
        {
            ExplorerAddressBox.Visibility = Visibility.Collapsed;
            e.Handled = true;
            return;
        }

        if (e.Key == VirtualKey.Enter)
        {
            var requested = ExplorerAddressBox.Text.Trim();
            ExplorerAddressBox.Visibility = Visibility.Collapsed;
            if (!string.IsNullOrWhiteSpace(requested))
            {
                NavigateToDirectory(requested);
            }
            e.Handled = true;
        }
    }

    private void ExplorerAddressBox_LostFocus(
        object sender,
        RoutedEventArgs e)
    {
        ExplorerAddressBox.Visibility = Visibility.Collapsed;
    }

    private void NavigatePrimaryExplorerBack()
    {
        var tab = _activePrimaryExplorerTab;
        if (tab is null || tab.BackHistory.Count == 0) return;

        if (!string.IsNullOrWhiteSpace(_currentDirectory))
        {
            tab.ForwardHistory.Push(_currentDirectory);
        }

        NavigateToDirectory(tab.BackHistory.Pop(), false);
    }

    private void NavigatePrimaryExplorerForward()
    {
        var tab = _activePrimaryExplorerTab;
        if (tab is null || tab.ForwardHistory.Count == 0) return;

        if (!string.IsNullOrWhiteSpace(_currentDirectory))
        {
            tab.BackHistory.Push(_currentDirectory);
        }

        NavigateToDirectory(tab.ForwardHistory.Pop(), false);
    }

    private void Back_Click(
        object sender,
        RoutedEventArgs e)
    {
        NavigatePrimaryExplorerBack();
    }

    private void Forward_Click(
        object sender,
        RoutedEventArgs e)
    {
        NavigatePrimaryExplorerForward();
    }

    private void Up_Click(
        object sender,
        RoutedEventArgs e)
    {
        if (string.IsNullOrWhiteSpace(
                _currentDirectory))
        {
            return;
        }

        var root =
            IOPath.GetFullPath(
                _workspaceRoot);

        var current =
            IOPath.GetFullPath(
                _currentDirectory);

        if (string.Equals(
                root,
                current,
                StringComparison.OrdinalIgnoreCase))
        {
            return;
        }

        var parent =
            Directory.GetParent(
                current);

        if (parent is not null)
        {
            NavigateToDirectory(
                parent.FullName);
        }
    }

    private void Refresh_Click(
        object sender,
        RoutedEventArgs e)
    {
        RenderDirectory(
            SearchBox.Text);
    }

    private void SearchBox_TextChanged(
        object sender,
        TextChangedEventArgs e)
    {
        RenderDirectory(
            SearchBox.Text);
    }

    private void HomeFolder_Click(
        object sender,
        RoutedEventArgs e)
    {
        NavigateToDirectory(
            _workspaceRoot);
    }

    private void ProjectsFolder_Click(
        object sender,
        RoutedEventArgs e)
    {
        NavigateKnownFolder(
            "Projects");
    }

    private void DocumentsFolder_Click(
        object sender,
        RoutedEventArgs e)
    {
        NavigateKnownFolder(
            "Documents");
    }

    private void ImportsFolder_Click(
        object sender,
        RoutedEventArgs e)
    {
        NavigateKnownFolder(
            "Imports");
    }

    private void NavigateKnownFolder(
        string name)
    {
        var path =
            IOPath.Combine(
                _workspaceRoot,
                name);

        if (Directory.Exists(
                path))
        {
            NavigateToDirectory(
                path);
        }
    }

    private void OnIpcConnectionChanged(
        bool connected)
    {
        DispatcherQueue.TryEnqueue(
            () =>
            {
                _coreConnected =
                    connected;

                UpdateAboutSettingsPresentation();
                UpdateSecurityOverviewPresentation();
                UpdateSettingsHomeDashboard();

                CoreStatusText.Text =
                    connected
                        ? "Core connecté"
                        : "Core non connecté";

                UpdateCoreDockControlUi(
                    connected
                        ? "Connecté · prêt"
                        : "Core arrêté");

                if (connected)
                {
                    _ = _ipc.SendCommandAsync(
                        "security.get_permission_state");

                    _ = _ipc.SendCommandAsync(
                        "audio.get_listening_mode");
                }
                else
                {
                    UpdateListeningModePresentation(
                        null,
                        false,
                        "Atlas");
                }

                SystemPanelCoreText.Text =
                    connected
                        ? "Connecté"
                        : "Déconnecté";

                if (!connected)
                {
                    CpuTelemetryText.Text =
                        "-- %";

                    MemoryTelemetryText.Text =
                        "-- %";

                    DiskTelemetryText.Text =
                        "-- %";

                    UptimeTelemetryText.Text =
                        "--";

                    NetworkTelemetryText.Text =
                        "--";

                    CpuTelemetryBar.Value = 0;
                    MemoryTelemetryBar.Value = 0;
                    DiskTelemetryBar.Value = 0;

                    SystemPanelCpuText.Text =
                        "-- %";

                    SystemPanelMemoryText.Text =
                        "-- %";

                    SystemPanelDiskText.Text =
                        "-- %";

                    SystemPanelUptimeText.Text =
                        "--";

                    SystemPanelNetworkText.Text =
                        "--";

                    SystemPanelMemoryDetailText.Text =
                        "-- / --";

                    SystemPanelDiskDetailText.Text =
                        "-- / --";

                    SystemPanelCpuBar.Value = 0;
                    SystemPanelMemoryBar.Value = 0;
                    SystemPanelDiskBar.Value = 0;

                    NetworkPanelTypeText.Text =
                        "--";

                    NetworkPanelAdapterText.Text =
                        "--";

                    NetworkPanelIpv4Text.Text =
                        "--";

                    NetworkPanelGatewayText.Text =
                        "--";

                    NetworkPanelDnsText.Text =
                        "--";

                    NetworkPanelLinkSpeedText.Text =
                        "--";

                    NetworkPanelDownloadText.Text =
                        "--";

                    NetworkPanelUploadText.Text =
                        "--";

                    NetworkPanelStatusText.Text =
                        "--";

                    NetworkWidgetTypeText.Text =
                        "--";

                    NetworkWidgetAdapterText.Text =
                        "--";

                    NetworkWidgetIpv4Text.Text =
                        "--";

                    NetworkWidgetDownloadText.Text =
                        "--";

                    NetworkWidgetUploadText.Text =
                        "--";
                }
            });
    }

    private void OnIpcMessageReceived(
        JsonElement message)
    {
        DispatcherQueue.TryEnqueue(
            () =>
            {
                HandleIpcMessage(
                    message);
            });
    }

    private void HandleIpcMessage(
        JsonElement message)
    {
        if (
            !message.TryGetProperty(
                "type",
                out var typeNode)
            || typeNode.ValueKind
                != JsonValueKind.String
        )
        {
            return;
        }

        var type =
            typeNode.GetString();

        if (
            type == "hello"
        )
        {
            CoreStatusText.Text =
                "Core connecté";

            return;
        }

        if (
            type != "event"
            || !message.TryGetProperty(
                "name",
                out var nameNode)
            || nameNode.ValueKind
                != JsonValueKind.String
        )
        {
            return;
        }

        var name =
            nameNode.GetString();

        switch (name)
        {
            case "atlas.status":
            case "atlas.ready":

                CoreStatusText.Text =
                    "Core connecté · prêt";

                UpdateCoreDockControlUi(
                    "Connecté · prêt");

                break;

            case "atlas.stopping":

                CoreStatusText.Text =
                    "Core en arrêt…";

                CoreDockStatusText.Text =
                    "Arrêt en cours…";

                CoreDockIndicator.Fill =
                    CreateBrush(
                        "#F1C76E");

                CoreDockFlyoutIndicator.Fill =
                    CreateBrush(
                        "#F1C76E");

                break;

            case "atlas.pong":

                CoreStatusText.Text =
                    "Core connecté · prêt";

                UpdateCoreDockControlUi(
                    "Connecté · prêt");

                break;

            case "ui.workspace.open_directory":

                HandleWorkspaceOpenEvent(
                    message);

                break;

            case "system.telemetry":

                HandleSystemTelemetry(
                    message);

                break;

            case "audio.listening_mode_state":

                HandleListeningModeState(
                    message);

                break;

            case "audio.input_devices":
                HandleMicrophoneState(message);
                break;
            case "audio.output_devices":
                HandleSpeakerState(message);
                break;
            case "audio.output_device_error":
                if (message.TryGetProperty("payload", out var outputError))
                    SpeakerStatusText.Text = outputError.GetProperty("reason").GetString();
                break;
            case "audio.device_inventory_error":
                if (message.TryGetProperty("payload", out var inventoryError))
                {
                    var reason = inventoryError.TryGetProperty("reason", out var reasonValue)
                        ? reasonValue.GetString()
                        : "Inventaire audio indisponible.";
                    MicrophoneStatusText.Text = reason;
                    SpeakerStatusText.Text = reason;
                }
                break;
            case "audio.input_device_error":
                if (message.TryGetProperty("payload", out var microphoneError))
                    MicrophoneStatusText.Text = microphoneError.GetProperty("reason").GetString();
                break;

            case "audio.listening_mode_error":

                HandleListeningModeError(
                    message);

                break;

            case "security.permission_state":
            case "security.permission_mode_changed":

                HandlePermissionState(
                    message);

                break;

            case "security.permission_error":

                HandlePermissionError(
                    message);

                break;

            case "ai.speech_started":

                CoreStatusText.Text =
                    "Atlas parle";

                if (_currentListeningMode == "wake_word")
                {
                    UpdateListeningModePresentation(
                        "wake_word",
                        true,
                        ListeningWakeWordText.Text);
                }

                break;

            case "ai.speech_ended":

                CoreStatusText.Text =
                    "Core connecté · prêt";

                break;
        }
    }

    private void HandlePermissionState(
        JsonElement message)
    {
        if (
            !message.TryGetProperty(
                "payload",
                out var payload)
            || payload.ValueKind
                != JsonValueKind.Object
        )
        {
            return;
        }

        var mode =
            ReadJsonString(
                payload,
                "mode");

        if (string.IsNullOrWhiteSpace(
                mode))
        {
            return;
        }

        _currentPermissionMode =
            mode;

        SelectPermissionMode(
            mode);

        UpdatePermissionModePresentation(
            mode);

        UpdateSecurityOverviewPresentation();
        UpdateSettingsHomeDashboard();

        if (
            string.Equals(
                GetSelectedPermissionMode(),
                mode,
                StringComparison.OrdinalIgnoreCase)
        )
        {
            ClearSettingsDirtyState();
        }

        SettingsStatusText.Text =
            $"Mode de permissions actif : {GetPermissionModeDisplayName(mode)}";
    }

    private void HandlePermissionError(
        JsonElement message)
    {
        if (
            !message.TryGetProperty(
                "payload",
                out var payload)
            || payload.ValueKind
                != JsonValueKind.Object
        )
        {
            return;
        }

        var reason =
            ReadJsonString(
                payload,
                "reason")
            ?? "Modification de permissions refusée par le Core.";

        SelectPermissionMode(
            _currentPermissionMode);

        UpdatePermissionModePresentation(
            _currentPermissionMode);

        SettingsStatusText.Text =
            reason;
    }

    private static string GetPermissionModeDisplayName(
        string mode)
    {
        return mode switch
        {
            "restricted" => "Restreint",
            "normal" => "Normal",
            "advanced" => "Avancé",
            "administrator" => "Administrateur",
            "jarvis" => "JARVIS",
            _ => mode,
        };
    }

    private void HandleSystemTelemetry(
        JsonElement message)
    {
        if (
            !message.TryGetProperty(
                "payload",
                out var payload)
            || payload.ValueKind
                != JsonValueKind.Object
        )
        {
            return;
        }

        var cpu =
            ReadJsonDouble(
                payload,
                "cpu_percent");

        var memory =
            ReadJsonDouble(
                payload,
                "memory_percent");

        var disk =
            ReadJsonDouble(
                payload,
                "disk_percent");

        var uptime =
            ReadJsonInt64(
                payload,
                "uptime_seconds");

        var network =
            ReadJsonBool(
                payload,
                "network_up");

        var storageRoot =
            ReadJsonString(
                payload,
                "storage_root");

        var memoryUsed =
            ReadJsonInt64(
                payload,
                "memory_used_bytes");

        var memoryTotal =
            ReadJsonInt64(
                payload,
                "memory_total_bytes");

        var diskUsed =
            ReadJsonInt64(
                payload,
                "disk_used_bytes");

        var diskTotal =
            ReadJsonInt64(
                payload,
                "disk_total_bytes");

        CpuTelemetryText.Text =
            cpu is null
                ? "-- %"
                : $"{cpu:0.#} %";

        MemoryTelemetryText.Text =
            memory is null
                ? "-- %"
                : $"{memory:0.#} %";

        DiskTelemetryText.Text =
            disk is null
                ? "-- %"
                : $"{disk:0.#} %";

        CpuTelemetryBar.Value =
            cpu ?? 0;

        MemoryTelemetryBar.Value =
            memory ?? 0;

        DiskTelemetryBar.Value =
            disk ?? 0;

        DiskTelemetryLabel.Text =
            string.IsNullOrWhiteSpace(
                storageRoot)
                ? "DISQUE"
                : $"DISQUE {storageRoot}";

        UptimeTelemetryText.Text =
            uptime is null
                ? "--"
                : FormatUptime(
                    uptime.Value);

        NetworkTelemetryText.Text =
            network switch
            {
                true => "En ligne",
                false => "Hors ligne",
                _ => "--",
            };

        SystemPanelCpuText.Text =
            CpuTelemetryText.Text;

        SystemPanelCpuBar.Value =
            cpu ?? 0;

        SystemPanelMemoryText.Text =
            MemoryTelemetryText.Text;

        SystemPanelMemoryBar.Value =
            memory ?? 0;

        SystemPanelMemoryDetailText.Text =
            FormatBytePair(
                memoryUsed,
                memoryTotal);

        SystemPanelDiskText.Text =
            DiskTelemetryText.Text;

        SystemPanelDiskBar.Value =
            disk ?? 0;

        SystemPanelDiskTitleText.Text =
            string.IsNullOrWhiteSpace(
                storageRoot)
                ? "STOCKAGE"
                : $"STOCKAGE {storageRoot}";

        SystemPanelDiskDetailText.Text =
            FormatBytePair(
                diskUsed,
                diskTotal);

        SystemPanelUptimeText.Text =
            UptimeTelemetryText.Text;

        SystemPanelNetworkText.Text =
            NetworkTelemetryText.Text;

        HandleNetworkTelemetry(
            payload);
    }

    private void HandleNetworkTelemetry(
        JsonElement payload)
    {
        if (
            !payload.TryGetProperty(
                "network",
                out var network)
            || network.ValueKind
                != JsonValueKind.Object
        )
        {
            return;
        }

        NetworkPanelTypeText.Text =
            ReadJsonString(
                network,
                "connection_type")
            ?? "--";

        var adapter =
            ReadJsonString(
                network,
                "interface");

        var description =
            ReadJsonString(
                network,
                "description");

        NetworkPanelAdapterText.Text =
            string.IsNullOrWhiteSpace(
                description)
                ? adapter ?? "--"
                : string.IsNullOrWhiteSpace(
                    adapter)
                    ? description
                    : $"{adapter} · {description}";

        NetworkPanelIpv4Text.Text =
            ReadJsonString(
                network,
                "ipv4")
            ?? "--";

        NetworkPanelGatewayText.Text =
            ReadJsonString(
                network,
                "gateway")
            ?? "--";

        NetworkPanelDnsText.Text =
            ReadJsonStringArray(
                network,
                "dns");

        var linkSpeed =
            ReadJsonInt64(
                network,
                "link_speed_mbps");

        NetworkPanelLinkSpeedText.Text =
            linkSpeed is null
                ? "--"
                : $"{linkSpeed} Mbit/s";

        var download =
            ReadJsonDouble(
                network,
                "download_bps");

        var upload =
            ReadJsonDouble(
                network,
                "upload_bps");

        NetworkPanelDownloadText.Text =
            FormatRate(
                download);

        NetworkPanelUploadText.Text =
            FormatRate(
                upload);

        var up =
            ReadJsonBool(
                network,
                "up");

        NetworkPanelStatusText.Text =
            up switch
            {
                true => "Connecté",
                false => "Déconnecté",
                _ => "--",
            };

        NetworkWidgetTypeText.Text =
            NetworkPanelTypeText.Text;

        NetworkWidgetAdapterText.Text =
            adapter
            ?? description
            ?? "--";

        NetworkWidgetIpv4Text.Text =
            NetworkPanelIpv4Text.Text;

        NetworkWidgetDownloadText.Text =
            NetworkPanelDownloadText.Text;

        NetworkWidgetUploadText.Text =
            NetworkPanelUploadText.Text;
    }

    private static string ReadJsonStringArray(
        JsonElement payload,
        string propertyName)
    {
        if (
            !payload.TryGetProperty(
                propertyName,
                out var node)
            || node.ValueKind
                != JsonValueKind.Array
        )
        {
            return "--";
        }

        var values =
            node
                .EnumerateArray()
                .Where(
                    item =>
                        item.ValueKind
                        == JsonValueKind.String)
                .Select(
                    item =>
                        item.GetString())
                .Where(
                    value =>
                        !string.IsNullOrWhiteSpace(
                            value))
                .ToArray();

        return values.Length == 0
            ? "--"
            : string.Join(
                " · ",
                values);
    }

    private static string FormatRate(
        double? bytesPerSecond)
    {
        if (
            bytesPerSecond is null
            || bytesPerSecond < 0
        )
        {
            return "--";
        }

        var value =
            bytesPerSecond.Value;

        if (value >= 1024 * 1024)
        {
            return
                $"{value / (1024 * 1024):0.0} Mo/s";
        }

        if (value >= 1024)
        {
            return
                $"{value / 1024:0.0} Ko/s";
        }

        return
            $"{value:0} o/s";
    }

    private static string FormatBytePair(
        long? usedBytes,
        long? totalBytes)
    {
        if (
            usedBytes is null
            || totalBytes is null
            || totalBytes <= 0
        )
        {
            return "-- / --";
        }

        return
            $"{FormatBytes(usedBytes.Value)} / "
            + $"{FormatBytes(totalBytes.Value)}";
    }

    private static string FormatBytes(
        long bytes)
    {
        var value =
            Math.Max(
                0,
                bytes);

        string[] units =
        {
            "o",
            "Ko",
            "Mo",
            "Go",
            "To",
        };

        var size =
            (double)value;

        var unitIndex =
            0;

        while (
            size >= 1024
            && unitIndex
                < units.Length - 1
        )
        {
            size /= 1024;
            unitIndex++;
        }

        return
            $"{size:0.#} "
            + units[
                unitIndex
            ];
    }

    private static string FormatUptime(
        long totalSeconds)
    {
        var uptime =
            TimeSpan.FromSeconds(
                Math.Max(
                    0,
                    totalSeconds));

        if (uptime.TotalDays >= 1)
        {
            return
                $"{(int)uptime.TotalDays}j "
                + $"{uptime.Hours}h";
        }

        if (uptime.TotalHours >= 1)
        {
            return
                $"{uptime.Hours}h "
                + $"{uptime.Minutes}m";
        }

        return
            $"{uptime.Minutes}m";
    }

    private static double? ReadJsonDouble(
        JsonElement payload,
        string propertyName)
    {
        if (
            payload.TryGetProperty(
                propertyName,
                out var node)
            && node.ValueKind
                == JsonValueKind.Number
            && node.TryGetDouble(
                out var value)
        )
        {
            return value;
        }

        return null;
    }

    private static long? ReadJsonInt64(
        JsonElement payload,
        string propertyName)
    {
        if (
            payload.TryGetProperty(
                propertyName,
                out var node)
            && node.ValueKind
                == JsonValueKind.Number
            && node.TryGetInt64(
                out var value)
        )
        {
            return value;
        }

        return null;
    }

    private static bool? ReadJsonBool(
        JsonElement payload,
        string propertyName)
    {
        if (!payload.TryGetProperty(
                propertyName,
                out var node))
        {
            return null;
        }

        if (
            node.ValueKind
            == JsonValueKind.True
        )
        {
            return true;
        }

        if (
            node.ValueKind
            == JsonValueKind.False
        )
        {
            return false;
        }

        return null;
    }

    private static string? ReadJsonString(
        JsonElement payload,
        string propertyName)
    {
        if (
            payload.TryGetProperty(
                propertyName,
                out var node)
            && node.ValueKind
                == JsonValueKind.String
        )
        {
            return node.GetString();
        }

        return null;
    }

    private void HandleWorkspaceOpenEvent(
        JsonElement message)
    {
        if (
            !message.TryGetProperty(
                "payload",
                out var payload)
            || payload.ValueKind
                != JsonValueKind.Object
            || !payload.TryGetProperty(
                "path",
                out var pathNode)
            || pathNode.ValueKind
                != JsonValueKind.String
        )
        {
            return;
        }

        var path =
            pathNode.GetString();

        if (string.IsNullOrWhiteSpace(
                path))
        {
            return;
        }

        NavigateToDirectory(
            path,
            false);

        ShowFloatingPanel(
            FilesPanel);

        UiLog.Info(
            $"Workspace opened from Core IPC: {path}");
    }

    private void OpenSystemPanel_Click(
        object sender,
        RoutedEventArgs e)
    {
        ShowFloatingPanel(
            SystemPanel);
    }

    private void CloseSystemPanel_Click(
        object sender,
        RoutedEventArgs e)
    {
        ForgetFloatingWindowState(
            SystemPanel);

        SystemPanel.Visibility =
            Visibility.Collapsed;
    }

    private void Atlas_Click(
        object sender,
        RoutedEventArgs e)
    {
        UpdateCoreDockControlUi();

        AtlasCoreFlyout.ShowAt(
            AtlasCoreButton);
    }

    private async void AtlasTestCore_Click(
        object sender,
        RoutedEventArgs e)
    {
        if (!_ipc.IsConnected)
        {
            CoreStatusText.Text =
                "Core non connecté";

            UpdateCoreDockControlUi(
                "Core non connecté");

            return;
        }

        CoreStatusText.Text =
            "Core connecté · test…";

        UpdateCoreDockControlUi(
            "Test en cours…");

        try
        {
            await _ipc.SendCommandAsync(
                "atlas.ping");
        }
        catch (Exception exception)
        {
            UiLog.Error(
                "Atlas Core connection test failed.",
                exception);

            UpdateCoreDockControlUi(
                "Échec du test");
        }
    }

    private async void AtlasStartCore_Click(
        object sender,
        RoutedEventArgs e)
    {
        if (_ipc.IsConnected)
        {
            UpdateCoreDockControlUi(
                "Core déjà connecté");

            return;
        }

        CoreDockStartButton.IsEnabled =
            false;

        CoreDockStatusText.Text =
            "Démarrage…";

        CoreDockIndicator.Fill =
            CreateBrush(
                "#F1C76E");

        CoreDockFlyoutIndicator.Fill =
            CreateBrush(
                "#F1C76E");

        try
        {
            await _coreProcess
                .EnsureStartedAsync(
                    () =>
                        _ipc.IsConnected,
                    TimeSpan.Zero);

            // The IPC server reconnects independently. Wait briefly
            // so the flyout can immediately reflect a successful start.
            var deadline =
                DateTime.UtcNow
                + TimeSpan.FromSeconds(
                    6);

            while (
                !_ipc.IsConnected
                && DateTime.UtcNow
                    < deadline
            )
            {
                await Task.Delay(
                    150);
            }

            if (_ipc.IsConnected)
            {
                CoreStatusText.Text =
                    "Core connecté · prêt";

                UpdateCoreDockControlUi(
                    "Connecté · prêt");
            }
            else
            {
                CoreStatusText.Text =
                    "Core en démarrage…";

                UpdateCoreDockControlUi(
                    "Démarrage en cours…");
            }
        }
        catch (Exception exception)
        {
            UiLog.Error(
                "Unable to start Atlas Core from dock.",
                exception);

            CoreStatusText.Text =
                "Échec démarrage Core";

            UpdateCoreDockControlUi(
                "Échec du démarrage");
        }
        finally
        {
            CoreDockStartButton.IsEnabled =
                !_ipc.IsConnected;
        }
    }

    private async void AtlasStopCore_Click(
        object sender,
        RoutedEventArgs e)
    {
        CoreDockStopButton.IsEnabled =
            false;

        CoreDockStatusText.Text =
            "Arrêt en cours…";

        CoreDockIndicator.Fill =
            CreateBrush(
                "#F1C76E");

        CoreDockFlyoutIndicator.Fill =
            CreateBrush(
                "#F1C76E");

        CoreStatusText.Text =
            "Core en arrêt…";

        try
        {
            if (_ipc.IsConnected)
            {
                var shutdownTask =
                    _ipc.SendCommandAsync(
                        "atlas.shutdown_core");

                await Task.WhenAny(
                    shutdownTask,
                    Task.Delay(
                        500));
            }

            if (_coreProcess.OwnsCoreProcess)
            {
                await _coreProcess
                    .WaitForOwnedCoreExitAsync(
                        TimeSpan.FromMilliseconds(
                            1800));

                _coreProcess
                    .StopOwnedCoreIfStillRunning();
            }

            var deadline =
                DateTime.UtcNow
                + TimeSpan.FromSeconds(
                    3);

            while (
                _ipc.IsConnected
                && DateTime.UtcNow
                    < deadline
            )
            {
                await Task.Delay(
                    100);
            }

            UpdateCoreDockControlUi(
                _ipc.IsConnected
                    ? "Arrêt demandé…"
                    : "Core arrêté");
        }
        catch (Exception exception)
        {
            UiLog.Error(
                "Unable to stop Atlas Core from dock.",
                exception);

            UpdateCoreDockControlUi(
                "Échec de l’arrêt");
        }
        finally
        {
            CoreDockStopButton.IsEnabled =
                _ipc.IsConnected;
        }
    }

    private void UpdateCoreDockControlUi(
        string? statusOverride = null)
    {
        var connected =
            _ipc.IsConnected;

        var indicatorColor =
            connected
                ? "#67DFA0"
                : "#778493A0";

        CoreDockIndicator.Fill =
            CreateBrush(
                indicatorColor);

        CoreDockFlyoutIndicator.Fill =
            CreateBrush(
                indicatorColor);

        CoreDockStatusText.Text =
            statusOverride
            ?? (
                connected
                    ? "Connecté · prêt"
                    : "Core arrêté"
            );

        CoreDockTestButton.IsEnabled =
            connected;

        CoreDockStartButton.IsEnabled =
            !connected;

        CoreDockStopButton.IsEnabled =
            connected;
    }

    private void Files_Click(
        object sender,
        RoutedEventArgs e)
    {
        if (
            RestorePrimaryPanelIfMinimized(
                FilesPanel)
        )
        {
            return;
        }

        if (
            FilesPanel.Visibility
            == Visibility.Visible
        )
        {
            BringFloatingWindowToFront(
                FilesPanel);

            return;
        }

        if (_primaryExplorerTabs.Count == 0)
        {
            InitializePrimaryExplorerTabs();
        }

        NavigateToDirectory(
            string.IsNullOrWhiteSpace(
                _currentDirectory)
                ? _workspaceRoot
                : _currentDirectory,
            false);

        UpdateSelectionUi();

        ShowFloatingPanel(
            FilesPanel);

        _ = _ipc.SendCommandAsync(
            "ui.files_opened",
            new
            {
                path =
                    _currentDirectory,
            });
    }

    private void RestorePrimaryExplorerTabs(
        IReadOnlyList<string> directories,
        int activeIndex)
    {
        _applyingPrimaryExplorerTabs = true;

        try
        {
            _primaryExplorerTabs.Clear();
            PrimaryExplorerTabsHost.Children.Clear();

            var restoredDirectories =
                directories
                    .Where(
                        directory =>
                            !string.IsNullOrWhiteSpace(directory))
                    .Select(
                        ResolvePrimaryExplorerDirectory)
                    .ToArray();

            if (restoredDirectories.Length == 0)
            {
                restoredDirectories =
                    new[]
                    {
                        _workspaceRoot,
                    };
            }

            foreach (var directory in restoredDirectories)
            {
                var tab =
                    new PrimaryExplorerTabState
                    {
                        Directory = directory,
                    };

                _primaryExplorerTabs.Add(tab);
                AddPrimaryExplorerTabButton(tab);
            }

            activeIndex =
                Math.Clamp(
                    activeIndex,
                    0,
                    _primaryExplorerTabs.Count - 1);

            _activePrimaryExplorerTab =
                _primaryExplorerTabs[activeIndex];

            _currentDirectory =
                _activePrimaryExplorerTab.Directory;

            SearchBox.Text = string.Empty;

            NavigateToDirectory(
                _currentDirectory,
                false);

            UpdatePrimaryExplorerTabVisuals();
        }
        finally
        {
            _applyingPrimaryExplorerTabs = false;
        }
    }

    private string ResolvePrimaryExplorerDirectory(
        string directory)
    {
        try
        {
            var fullPath =
                IOPath.GetFullPath(directory);

            var root =
                IOPath.GetFullPath(_workspaceRoot);

            if (
                fullPath.StartsWith(
                    root,
                    StringComparison.OrdinalIgnoreCase)
                && Directory.Exists(fullPath)
            )
            {
                return fullPath;
            }
        }
        catch
        {
        }

        return _workspaceRoot;
    }

    private void SavePrimaryExplorerTabs()
    {
        if (_applyingPrimaryExplorerTabs)
        {
            return;
        }

        try
        {
            if (
                _activePrimaryExplorerTab is not null
                && !string.IsNullOrWhiteSpace(_currentDirectory)
            )
            {
                _activePrimaryExplorerTab.Directory =
                    _currentDirectory;
            }

            var directories =
                _primaryExplorerTabs
                    .Select(tab => tab.Directory)
                    .Where(
                        directory =>
                            !string.IsNullOrWhiteSpace(directory))
                    .ToArray();

            var activeIndex =
                _activePrimaryExplorerTab is null
                    ? 0
                    : Math.Max(
                        0,
                        _primaryExplorerTabs.IndexOf(
                            _activePrimaryExplorerTab));

            var config =
                _config.Load();

            _config.Save(
                config with
                {
                    PrimaryExplorerTabs = directories,
                    PrimaryExplorerActiveTabIndex = activeIndex,
                });
        }
        catch (Exception exception)
        {
            UiLog.Error(
                "Unable to save primary Explorer tabs.",
                exception);
        }
    }

    private void InitializePrimaryExplorerTabs()
    {
        _primaryExplorerTabs.Clear();
        PrimaryExplorerTabsHost.Children.Clear();

        var tab = new PrimaryExplorerTabState
        {
            Directory = _workspaceRoot,
        };

        _primaryExplorerTabs.Add(tab);
        _activePrimaryExplorerTab = tab;
        AddPrimaryExplorerTabButton(tab);
        UpdatePrimaryExplorerTabVisuals();

        SavePrimaryExplorerTabs();
    }

    private void NewExplorerTab_Click(
        object sender,
        RoutedEventArgs e)
    {
        var directory =
            string.IsNullOrWhiteSpace(_currentDirectory)
                ? _workspaceRoot
                : _currentDirectory;

        if (IsModifierDown(VirtualKey.Shift))
        {
            OpenSecondaryExplorerWindow(directory);
            return;
        }

        var tab = new PrimaryExplorerTabState
        {
            Directory = directory,
        };

        _primaryExplorerTabs.Add(tab);
        AddPrimaryExplorerTabButton(tab);
        ActivatePrimaryExplorerTab(tab);

        SavePrimaryExplorerTabs();
    }

    private void AddPrimaryExplorerTabButton(
        PrimaryExplorerTabState tab)
    {
        var container =
            new Border
            {
                Height = 34,
                MinWidth = 84,
                MaxWidth = 210,
                CornerRadius =
                    new CornerRadius(
                        7),
                BorderThickness =
                    new Thickness(
                        1),
            };

        var layout =
            new Grid();

        layout.ColumnDefinitions.Add(
            new ColumnDefinition
            {
                Width =
                    new GridLength(
                        1,
                        GridUnitType.Star),
            });

        layout.ColumnDefinitions.Add(
            new ColumnDefinition
            {
                Width =
                    GridLength.Auto,
            });

        var content =
            new StackPanel
            {
                Orientation =
                    Orientation.Horizontal,
                Spacing = 7,
            };

        content.Children.Add(
            new FontIcon
            {
                Glyph = "\uE8B7",
                FontSize = 14,
                Foreground =
                    CreateBrush(
                        "#5FD0FF"),
            });

        var label =
            new TextBlock
            {
                Text =
                    GetExplorerTabDisplayName(
                        tab.Directory),
                FontSize = 12,
                FontWeight =
                    Microsoft.UI.Text
                        .FontWeights.SemiBold,
                Foreground =
                    CreateBrush(
                        "#E8E8EF"),
                VerticalAlignment =
                    VerticalAlignment.Center,
                TextTrimming =
                    TextTrimming.CharacterEllipsis,
            };

        content.Children.Add(
            label);

        var mainButton =
            new Button
            {
                Height = 32,
                MinWidth = 54,
                MaxWidth = 174,
                Padding =
                    new Thickness(
                        11,
                        0,
                        7,
                        0),
                Background =
                    CreateBrush(
                        "#00000000"),
                BorderThickness =
                    new Thickness(
                        0),
                HorizontalContentAlignment =
                    HorizontalAlignment.Left,
                Content =
                    content,
                Tag =
                    tab.Id,
            };

        mainButton.Click +=
            (_, _) =>
                ActivatePrimaryExplorerTab(
                    tab);

        layout.Children.Add(
            mainButton);

        var closeButton =
            new Button
            {
                Width = 28,
                Height = 28,
                Padding =
                    new Thickness(
                        0),
                Margin =
                    new Thickness(
                        0,
                        0,
                        3,
                        0),
                Background =
                    CreateBrush(
                        "#00000000"),
                BorderThickness =
                    new Thickness(
                        0),
                CornerRadius =
                    new CornerRadius(
                        5),
                Content =
                    new FontIcon
                    {
                        Glyph = "\uE711",
                        FontSize = 10,
                        Foreground =
                            CreateBrush(
                                "#AEB2BF"),
                    },
            };

        ToolTipService.SetToolTip(
            closeButton,
            "Fermer l’onglet");

        closeButton.Click +=
            (_, _) =>
                ClosePrimaryExplorerTab(
                    tab);

        Grid.SetColumn(
            closeButton,
            1);

        layout.Children.Add(
            closeButton);

        container.Child =
            layout;

        tab.TabButton =
            mainButton;

        tab.TabContainer =
            container;

        PrimaryExplorerTabsHost
            .Children
            .Add(
                container);
    }

    private void ClosePrimaryExplorerTab(
        PrimaryExplorerTabState tab)
    {
        var index =
            _primaryExplorerTabs
                .IndexOf(
                    tab);

        if (index < 0)
        {
            return;
        }

        var wasActive =
            ReferenceEquals(
                tab,
                _activePrimaryExplorerTab);

        if (
            wasActive
            && !string.IsNullOrWhiteSpace(
                _currentDirectory)
        )
        {
            tab.Directory =
                _currentDirectory;
        }

        if (
            tab.TabContainer
            is not null
        )
        {
            PrimaryExplorerTabsHost
                .Children
                .Remove(
                    tab.TabContainer);
        }

        _primaryExplorerTabs
            .RemoveAt(
                index);

        if (_primaryExplorerTabs.Count == 0)
        {
            _activePrimaryExplorerTab =
                null;

            _selectedPaths.Clear();

            FilesPanel.Visibility =
                Visibility.Collapsed;

            SavePrimaryExplorerTabs();

            return;
        }

        if (!wasActive)
        {
            UpdatePrimaryExplorerTabVisuals();

            SavePrimaryExplorerTabs();

            return;
        }

        var nextIndex =
            Math.Min(
                index,
                _primaryExplorerTabs.Count - 1);

        ActivatePrimaryExplorerTab(
            _primaryExplorerTabs[
                nextIndex
            ]);

        SavePrimaryExplorerTabs();
    }

    private void ActivatePrimaryExplorerTab(
        PrimaryExplorerTabState tab)
    {
        if (_activePrimaryExplorerTab is not null
            && !string.IsNullOrWhiteSpace(_currentDirectory))
        {
            _activePrimaryExplorerTab.Directory = _currentDirectory;
        }

        _activePrimaryExplorerTab = tab;
        SearchBox.Text = string.Empty;

        NavigateToDirectory(
            string.IsNullOrWhiteSpace(tab.Directory)
                ? _workspaceRoot
                : tab.Directory,
            false);

        UpdatePrimaryExplorerTabVisuals();

        SavePrimaryExplorerTabs();
    }

    private void UpdatePrimaryExplorerTabVisuals()
    {
        foreach (var tab in _primaryExplorerTabs)
        {
            if (tab.TabButton is null)
            {
                continue;
            }

            var active = ReferenceEquals(tab, _activePrimaryExplorerTab);

            if (tab.TabContainer is not null)
            {
                tab.TabContainer.Background =
                    active
                        ? Root.Resources[
                            "AtlasWindowControlBrush"]
                            as Brush
                        : CreateBrush(
                            "#161A2330");

                tab.TabContainer.BorderBrush =
                    active
                        ? CreateBrush(
                            "#4A62677A")
                        : Root.Resources[
                            "AtlasWindowInnerBorderBrush"]
                            as Brush;
            }

            if (
                tab.TabButton.Content
                is StackPanel content
                && content.Children
                    .OfType<TextBlock>()
                    .FirstOrDefault()
                is TextBlock label
            )
            {
                label.Text =
                    GetExplorerTabDisplayName(
                        tab.Directory);
            }
        }
    }

    private string GetExplorerTabDisplayName(string directory)
    {
        try
        {
            var resolved = IOPath.GetFullPath(directory);
            var root = IOPath.GetFullPath(_workspaceRoot);

            if (string.Equals(
                resolved,
                root,
                StringComparison.OrdinalIgnoreCase))
            {
                return "Atlas";
            }

            var name = IOPath.GetFileName(resolved);
            return string.IsNullOrWhiteSpace(name) ? "Atlas" : name;
        }
        catch
        {
            return "Atlas";
        }
    }

    private void RestoreSecondaryExplorerWindows(
        IReadOnlyList<SecondaryExplorerLayout> layouts)
    {
        foreach (
            var layout
            in layouts)
        {
            OpenSecondaryExplorerWindow(
                layout.Directory,
                layout);
        }
    }

    private void SaveSecondaryExplorerLayouts()
    {
        if (
            _applyingPrimaryWindowLayouts
            || !_primaryWindowLayoutsApplied
        )
        {
            return;
        }

        try
        {
            var config =
                _config.Load();

            var layouts =
                _secondaryExplorerWindows
                    .Values
                    .Select(
                        window =>
                            new SecondaryExplorerLayout(
                                window.CurrentDirectory,
                                GetPrimaryWindowCoordinate(
                                    window.Panel,
                                    true),
                                GetPrimaryWindowCoordinate(
                                    window.Panel,
                                    false),
                                GetPrimaryWindowSize(
                                    window.Panel,
                                    true),
                                GetPrimaryWindowSize(
                                    window.Panel,
                                    false),
                                _floatingWindowRestoreStates.ContainsKey(
                                    window.Panel),
                                _minimizedSecondaryExplorerButtons.ContainsKey(
                                    window.Id),
                                window.TabDirectories,
                                window.ActiveTabIndex))
                    .ToArray();

            _config.Save(
                config with
                {
                    SecondaryExplorerWindows =
                        layouts,
                });
        }
        catch (Exception exception)
        {
            UiLog.Error(
                "Unable to save secondary Explorer layouts.",
                exception);
        }
    }

    private void OpenSecondaryExplorerWindow(
        string directory,
        SecondaryExplorerLayout? restoredLayout = null)
    {
        var window =
            new SecondaryExplorerWindow(
                this,
                directory);

        if (restoredLayout is not null)
        {
            window.RestoreTabs(
                restoredLayout.Tabs,
                restoredLayout.ActiveTabIndex);
        }

        _secondaryExplorerWindows[
            window.Id
        ] = window;

        Root.Children.Add(
            window.Panel);

        if (restoredLayout is not null)
        {
            window.Panel.Width =
                Math.Max(
                    window.Panel.MinWidth,
                    restoredLayout.Width);

            window.Panel.Height =
                Math.Max(
                    window.Panel.MinHeight,
                    restoredLayout.Height);

            window.Panel.Margin =
                new Thickness(
                    restoredLayout.X,
                    restoredLayout.Y,
                    0,
                    0);

            ClampFloatingPanelToWorkspace(
                window.Panel);
        }
        else
        {
            var offset =
                26
                * (
                    _secondaryExplorerWindows.Count
                    % 8
                );

            var targetLeft =
                Math.Max(
                    20,
                    (
                        Root.ActualWidth
                        - window.Panel.Width
                    )
                    / 2
                    + offset);

            var targetTop =
                Math.Max(
                    20,
                    (
                        GetFloatingWorkspaceBottom()
                        - window.Panel.Height
                    )
                    / 2
                    + offset);

            window.Panel.Margin =
                new Thickness(
                    Math.Min(
                        targetLeft,
                        Math.Max(
                            20,
                            Root.ActualWidth
                            - window.Panel.Width
                            - 20)),
                    Math.Min(
                        targetTop,
                        Math.Max(
                            20,
                            GetFloatingWorkspaceBottom()
                            - window.Panel.Height
                            - 20)),
                    0,
                    0);
        }

        AttachFloatingWindowBehavior(
            window.Panel);

        BringFloatingWindowToFront(
            window.Panel);

        if (
            restoredLayout?.Maximized
                == true
        )
        {
            ToggleFloatingWindowMaximize(
                window.Panel,
                window.MaximizeButton);
        }

        if (
            restoredLayout?.Minimized
                == true
        )
        {
            MinimizeSecondaryExplorerWindow(
                window);
        }

        window.Closed +=
            (_, _) =>
            {
                if (
                    _minimizedSecondaryExplorerButtons.Remove(
                        window.Id,
                        out var minimizedButton)
                )
                {
                    MinimizedWindowsHost.Children.Remove(
                        minimizedButton);
                }

                _floatingWindowRestoreStates.Remove(
                    window.Panel);

                _floatingWindowMaximizeButtons.Remove(
                    window.Panel);

                _secondaryExplorerWindows.Remove(
                    window.Id);

                Root.Children.Remove(
                    window.Panel);

                SaveSecondaryExplorerLayouts();
            };
    }

    private void CloseFiles_Click(
        object sender,
        RoutedEventArgs e)
    {
        FilesPanel.Visibility =
            Visibility.Collapsed;


        ForgetFloatingWindowState(
            FilesPanel);

        SavePrimaryWindowLayouts();
    }

    private void LoadWidgetPreferences()
    {
        var config =
            _config.Load();

        _applyingWidgetPreferences =
            true;

        try
        {
            CoreStatusCard.Visibility =
                config.WidgetCoreVisible
                    ? Visibility.Visible
                    : Visibility.Collapsed;

            SystemTelemetryCard.Visibility =
                config.WidgetSystemVisible
                    ? Visibility.Visible
                    : Visibility.Collapsed;

            VoiceListeningCard.Visibility =
                config.WidgetVoiceVisible
                    ? Visibility.Visible
                    : Visibility.Collapsed;

            StorageWidgetCard.Visibility =
                config.WidgetStorageVisible
                    ? Visibility.Visible
                    : Visibility.Collapsed;

            NetworkWidgetCard.Visibility =
                config.WidgetNetworkVisible
                    ? Visibility.Visible
                    : Visibility.Collapsed;

            _widgetsLayoutMode =
                config.WidgetsAlignment;

            _widgetsLocked =
                config.WidgetsLocked;

            if (
                config.WidgetCoreX >= 0
                && config.WidgetCoreY >= 0
                && config.WidgetSystemX >= 0
                && config.WidgetSystemY >= 0
                && config.WidgetVoiceX >= 0
                && config.WidgetVoiceY >= 0
                && config.WidgetStorageX >= 0
                && config.WidgetStorageY >= 0
                && config.WidgetNetworkX >= 0
                && config.WidgetNetworkY >= 0
            )
            {
                SetDesktopWidgetPosition(
                    CoreStatusCard,
                    config.WidgetCoreX,
                    config.WidgetCoreY);

                SetDesktopWidgetPosition(
                    SystemTelemetryCard,
                    config.WidgetSystemX,
                    config.WidgetSystemY);

                SetDesktopWidgetPosition(
                    VoiceListeningCard,
                    config.WidgetVoiceX,
                    config.WidgetVoiceY);

                SetDesktopWidgetPosition(
                    StorageWidgetCard,
                    config.WidgetStorageX,
                    config.WidgetStorageY);

                SetDesktopWidgetPosition(
                    NetworkWidgetCard,
                    config.WidgetNetworkX,
                    config.WidgetNetworkY);
            }
            else
            {
                _widgetPresetNeedsInitialLayout =
                    true;
            }
        }
        finally
        {
            _applyingWidgetPreferences =
                false;
        }
    }

    private void SaveWidgetPreferences()
    {
        if (
            _applyingWidgetPreferences
            || _config is null
            || CoreStatusCard is null
            || SystemTelemetryCard is null
            || VoiceListeningCard is null
            || StorageWidgetCard is null
            || NetworkWidgetCard is null
        )
        {
            return;
        }

        try
        {
            var config =
                _config.Load();

            var updated =
                config with
                {
                    WidgetCoreVisible =
                        CoreStatusCard.Visibility
                            == Visibility.Visible,

                    WidgetSystemVisible =
                        SystemTelemetryCard.Visibility
                            == Visibility.Visible,

                    WidgetVoiceVisible =
                        VoiceListeningCard.Visibility
                            == Visibility.Visible,

                    WidgetStorageVisible =
                        StorageWidgetCard.Visibility
                            == Visibility.Visible,

                    WidgetNetworkVisible =
                        NetworkWidgetCard.Visibility
                            == Visibility.Visible,

                    WidgetsAlignment =
                        _widgetsLayoutMode,

                    WidgetCoreX =
                        GetDesktopWidgetCoordinate(
                            CoreStatusCard,
                            horizontal: true),

                    WidgetCoreY =
                        GetDesktopWidgetCoordinate(
                            CoreStatusCard,
                            horizontal: false),

                    WidgetSystemX =
                        GetDesktopWidgetCoordinate(
                            SystemTelemetryCard,
                            horizontal: true),

                    WidgetSystemY =
                        GetDesktopWidgetCoordinate(
                            SystemTelemetryCard,
                            horizontal: false),

                    WidgetVoiceX =
                        GetDesktopWidgetCoordinate(
                            VoiceListeningCard,
                            horizontal: true),

                    WidgetVoiceY =
                        GetDesktopWidgetCoordinate(
                            VoiceListeningCard,
                            horizontal: false),

                    WidgetStorageX =
                        GetDesktopWidgetCoordinate(
                            StorageWidgetCard,
                            horizontal: true),

                    WidgetStorageY =
                        GetDesktopWidgetCoordinate(
                            StorageWidgetCard,
                            horizontal: false),

                    WidgetNetworkX =
                        GetDesktopWidgetCoordinate(
                            NetworkWidgetCard,
                            horizontal: true),

                    WidgetNetworkY =
                        GetDesktopWidgetCoordinate(
                            NetworkWidgetCard,
                            horizontal: false),

                    WidgetsLocked =
                        _widgetsLocked,
                };

            _config.Save(
                updated);
        }
        catch (Exception exception)
        {
            UiLog.Error(
                "Unable to save widget preferences.",
                exception);
        }
    }

    private static int GetDesktopWidgetCoordinate(
        FrameworkElement widget,
        bool horizontal)
    {
        var value =
            horizontal
                ? Canvas.GetLeft(
                    widget)
                : Canvas.GetTop(
                    widget);

        if (
            double.IsNaN(
                value)
            || double.IsInfinity(
                value)
        )
        {
            return 0;
        }

        return Math.Max(
            0,
            (int)Math.Round(
                value));
    }

    private static void SetDesktopWidgetPosition(
        FrameworkElement widget,
        double left,
        double top)
    {
        Canvas.SetLeft(
            widget,
            left);

        Canvas.SetTop(
            widget,
            top);
    }

    private void DesktopWidget_PointerPressed(
        object sender,
        PointerRoutedEventArgs e)
    {
        if (
            _widgetsLocked
            || sender is not FrameworkElement widget
            || IsPointerInsideButton(
                e.OriginalSource)
        )
        {
            return;
        }

        var point =
            e.GetCurrentPoint(
                Root);

        if (!point.Properties.IsLeftButtonPressed)
        {
            return;
        }

        _draggedDesktopWidget =
            widget;

        _desktopWidgetDragStartPointer =
            point.Position;

        _desktopWidgetDragStartLeft =
            NormalizeCanvasCoordinate(
                Canvas.GetLeft(
                    widget));

        _desktopWidgetDragStartTop =
            NormalizeCanvasCoordinate(
                Canvas.GetTop(
                    widget));

        widget.CapturePointer(
            e.Pointer);

        e.Handled =
            true;
    }

    private void DesktopWidget_PointerMoved(
        object sender,
        PointerRoutedEventArgs e)
    {
        if (
            _draggedDesktopWidget is null
            || !ReferenceEquals(
                sender,
                _draggedDesktopWidget)
        )
        {
            return;
        }

        var point =
            e.GetCurrentPoint(
                Root);

        if (!point.Properties.IsLeftButtonPressed)
        {
            FinishDesktopWidgetDrag();

            return;
        }

        var deltaX =
            point.Position.X
            - _desktopWidgetDragStartPointer.X;

        var deltaY =
            point.Position.Y
            - _desktopWidgetDragStartPointer.Y;

        const double snap =
            8.0;

        var targetLeft =
            Math.Round(
                (
                    _desktopWidgetDragStartLeft
                    + deltaX
                )
                / snap)
            * snap;

        var targetTop =
            Math.Round(
                (
                    _desktopWidgetDragStartTop
                    + deltaY
                )
                / snap)
            * snap;

        SetDesktopWidgetPosition(
            _draggedDesktopWidget,
            targetLeft,
            targetTop);

        ClampDesktopWidgetToWorkspace(
            _draggedDesktopWidget);

        _widgetsLayoutMode =
            "custom";

        SyncWidgetManagerUi();

        e.Handled =
            true;
    }

    private void DesktopWidget_PointerReleased(
        object sender,
        PointerRoutedEventArgs e)
    {
        if (
            _draggedDesktopWidget is null
            || !ReferenceEquals(
                sender,
                _draggedDesktopWidget)
        )
        {
            return;
        }

        FinishDesktopWidgetDrag();

        SaveWidgetPreferences();

        e.Handled =
            true;
    }

    private void DesktopWidget_PointerCanceled(
        object sender,
        PointerRoutedEventArgs e)
    {
        if (_draggedDesktopWidget is null)
        {
            return;
        }

        FinishDesktopWidgetDrag();

        SaveWidgetPreferences();
    }

    private void FinishDesktopWidgetDrag()
    {
        _draggedDesktopWidget
            ?.ReleasePointerCaptures();

        _draggedDesktopWidget =
            null;
    }

    private static double NormalizeCanvasCoordinate(
        double value)
    {
        return double.IsNaN(
                   value)
               || double.IsInfinity(
                   value)
            ? 0
            : value;
    }

    private static bool IsPointerInsideButton(
        object? originalSource)
    {
        var current =
            originalSource
            as DependencyObject;

        while (current is not null)
        {
            if (current is Button)
            {
                return true;
            }

            current =
                VisualTreeHelper.GetParent(
                    current);
        }

        return false;
    }

    private void ClampAllDesktopWidgetsToWorkspace()
    {
        foreach (
            var widget
            in new FrameworkElement[]
            {
                CoreStatusCard,
                SystemTelemetryCard,
                VoiceListeningCard,
                StorageWidgetCard,
                NetworkWidgetCard,
            })
        {
            ClampDesktopWidgetToWorkspace(
                widget);
        }
    }

    private void ClampDesktopWidgetToWorkspace(
        FrameworkElement widget)
    {
        if (
            Root.ActualWidth <= 0
            || Root.ActualHeight <= 0
        )
        {
            return;
        }

        var width =
            widget.ActualWidth > 0
                ? widget.ActualWidth
                : widget.Width;

        var height =
            widget.ActualHeight > 0
                ? widget.ActualHeight
                : widget.Height;

        if (
            double.IsNaN(
                width)
            || width <= 0
        )
        {
            width =
                202;
        }

        if (
            double.IsNaN(
                height)
            || height <= 0
        )
        {
            height =
                80;
        }

        var maxLeft =
            Math.Max(
                18,
                Root.ActualWidth
                    - width
                    - 18);

        var maxTop =
            Math.Max(
                18,
                GetFloatingWorkspaceBottom()
                    - height
                    - 12);

        Canvas.SetLeft(
            widget,
            Math.Clamp(
                NormalizeCanvasCoordinate(
                    Canvas.GetLeft(
                        widget)),
                18,
                maxLeft));

        Canvas.SetTop(
            widget,
            Math.Clamp(
                NormalizeCanvasCoordinate(
                    Canvas.GetTop(
                        widget)),
                18,
                maxTop));
    }

    private void Widgets_Click(
        object sender,
        RoutedEventArgs e)
    {
        if (
            RestorePrimaryPanelIfMinimized(
                WidgetManagerPanel)
        )
        {
            return;
        }

        SyncWidgetManagerUi();

        ToggleFloatingPanel(
            WidgetManagerPanel);

        UpdateDockWindowStates();

        UiLog.Info(
            "Widget manager toggled from dock.");
    }

    private void CloseWidgetManagerPanel_Click(
        object sender,
        RoutedEventArgs e)
    {
        WidgetManagerPanel.Visibility =
            Visibility.Collapsed;


        ForgetFloatingWindowState(
            WidgetManagerPanel);

        SavePrimaryWindowLayouts();
    }

    private void WidgetCoreToggle_Toggled(
        object sender,
        RoutedEventArgs e)
    {
        CoreStatusCard.Visibility =
            WidgetCoreToggle.IsOn
                ? Visibility.Visible
                : Visibility.Collapsed;

        SaveWidgetPreferences();
    }

    private void WidgetSystemToggle_Toggled(
        object sender,
        RoutedEventArgs e)
    {
        SystemTelemetryCard.Visibility =
            WidgetSystemToggle.IsOn
                ? Visibility.Visible
                : Visibility.Collapsed;

        SaveWidgetPreferences();
    }

    private void WidgetVoiceToggle_Toggled(
        object sender,
        RoutedEventArgs e)
    {
        VoiceListeningCard.Visibility =
            WidgetVoiceToggle.IsOn
                ? Visibility.Visible
                : Visibility.Collapsed;

        SaveWidgetPreferences();
    }

    private void WidgetStorageToggle_Toggled(
        object sender,
        RoutedEventArgs e)
    {
        StorageWidgetCard.Visibility =
            WidgetStorageToggle.IsOn
                ? Visibility.Visible
                : Visibility.Collapsed;

        SaveWidgetPreferences();
    }

    private void WidgetNetworkToggle_Toggled(
        object sender,
        RoutedEventArgs e)
    {
        NetworkWidgetCard.Visibility =
            WidgetNetworkToggle.IsOn
                ? Visibility.Visible
                : Visibility.Collapsed;

        SaveWidgetPreferences();
    }

    private void WidgetsEditModeToggle_Toggled(
        object sender,
        RoutedEventArgs e)
    {
        if (_applyingWidgetPreferences)
        {
            return;
        }

        _widgetsLocked =
            !WidgetsEditModeToggle.IsOn;

        SaveWidgetPreferences();
    }

    private void WidgetsReset_Click(
        object sender,
        RoutedEventArgs e)
    {
        ApplyDesktopWidgetPreset(
            HorizontalAlignment.Right,
            save: true);
    }

    private void WidgetsTopLeft_Click(
        object sender,
        RoutedEventArgs e)
    {
        SetDesktopWidgetsAlignment(
            HorizontalAlignment.Left);
    }

    private void WidgetsTopRight_Click(
        object sender,
        RoutedEventArgs e)
    {
        SetDesktopWidgetsAlignment(
            HorizontalAlignment.Right);
    }

    private void SetDesktopWidgetsAlignment(
        HorizontalAlignment alignment)
    {
        ApplyDesktopWidgetPreset(
            alignment,
            save: true);
    }

    private void ApplyDesktopWidgetPreset(
        HorizontalAlignment alignment,
        bool save)
    {
        if (
            Root.ActualWidth <= 0
            || Root.ActualHeight <= 0
        )
        {
            _widgetsLayoutMode =
                alignment
                    == HorizontalAlignment.Left
                        ? "left"
                        : "right";

            _widgetPresetNeedsInitialLayout =
                true;

            return;
        }

        _widgetPresetNeedsInitialLayout =
            false;

        var left =
            alignment
                == HorizontalAlignment.Left;

        _widgetsLayoutMode =
            left
                ? "left"
                : "right";

        var x =
            left
                ? 30.0
                : Math.Max(
                    30.0,
                    Root.ActualWidth
                        - 202.0
                        - 30.0);

        SetDesktopWidgetPosition(
            CoreStatusCard,
            left
                ? x
                : Math.Max(
                    30.0,
                    Root.ActualWidth
                        - 176.0
                        - 30.0),
            30);

        SetDesktopWidgetPosition(
            SystemTelemetryCard,
            x,
            96);

        var systemHeight =
            SystemTelemetryCard.ActualHeight > 0
                ? SystemTelemetryCard.ActualHeight
                : 258.0;

        SetDesktopWidgetPosition(
            VoiceListeningCard,
            x,
            96
                + systemHeight
                + 12);

        var voiceHeight =
            VoiceListeningCard.ActualHeight > 0
                ? VoiceListeningCard.ActualHeight
                : 142.0;

        SetDesktopWidgetPosition(
            StorageWidgetCard,
            x,
            96
                + systemHeight
                + 12
                + voiceHeight
                + 12);

        var storageHeight =
            StorageWidgetCard.ActualHeight > 0
                ? StorageWidgetCard.ActualHeight
                : 162.0;

        SetDesktopWidgetPosition(
            NetworkWidgetCard,
            x,
            96
                + systemHeight
                + 12
                + voiceHeight
                + 12
                + storageHeight
                + 12);

        ClampAllDesktopWidgetsToWorkspace();

        SyncWidgetManagerUi();

        if (save)
        {
            SaveWidgetPreferences();
        }
    }

    private void SyncWidgetManagerUi()
    {
        WidgetCoreToggle.IsOn =
            CoreStatusCard.Visibility
                == Visibility.Visible;

        WidgetSystemToggle.IsOn =
            SystemTelemetryCard.Visibility
                == Visibility.Visible;

        WidgetVoiceToggle.IsOn =
            VoiceListeningCard.Visibility
                == Visibility.Visible;

        WidgetStorageToggle.IsOn =
            StorageWidgetCard.Visibility
                == Visibility.Visible;

        WidgetNetworkToggle.IsOn =
            NetworkWidgetCard.Visibility
                == Visibility.Visible;

        _applyingWidgetPreferences =
            true;

        try
        {
            WidgetsEditModeToggle.IsOn =
                !_widgetsLocked;
        }
        finally
        {
            _applyingWidgetPreferences =
                false;
        }

        var left =
            string.Equals(
                _widgetsLayoutMode,
                "left",
                StringComparison.OrdinalIgnoreCase);

        var right =
            string.Equals(
                _widgetsLayoutMode,
                "right",
                StringComparison.OrdinalIgnoreCase);

        WidgetsTopLeftButton.Background =
            CreateBrush(
                left
                    ? "#33203A4B"
                    : "#251B2736");

        WidgetsTopLeftButton.BorderBrush =
            CreateBrush(
                left
                    ? "#4967BEE8"
                    : "#315D86A5");

        WidgetsTopRightButton.Background =
            CreateBrush(
                right
                    ? "#33203A4B"
                    : "#251B2736");

        WidgetsTopRightButton.BorderBrush =
            CreateBrush(
                right
                    ? "#4967BEE8"
                    : "#315D86A5");
    }

    private async void ExitAtlas_Click(
        object sender,
        RoutedEventArgs e)
    {
        var dialog =
            new ContentDialog
            {
                Title = "Quitter Atlas",
                Content =
                    "Voulez-vous fermer Atlas Desktop ?",
                PrimaryButtonText = "Quitter",
                CloseButtonText = "Annuler",
                DefaultButton =
                    ContentDialogButton.Close,
                XamlRoot =
                    Root.XamlRoot,
            };

        ApplyAtlasDialogStyle(
            dialog);

        var result =
            await dialog.ShowAsync();

        if (
            result
            != ContentDialogResult.Primary
        )
        {
            return;
        }

        UiLog.Info(
            "Atlas Desktop exit requested by user.");

        // Dès que l'utilisateur confirme, on arrête de protéger
        // l'affichage Atlas et on restaure Windows immédiatement.
        // La fermeture de l'UI ne doit jamais dépendre d'un pipe IPC.
        _taskbarGuardTimer.Stop();

        _taskbarVisibility.Restore();

        try
        {
            if (_coreProcess.OwnsCoreProcess)
            {
                var shutdownTask =
                    _ipc.SendCommandAsync(
                        "atlas.shutdown_core");

                // Le Named Pipe ne dispose pas actuellement d'un
                // CancellationToken par écriture. On lui laisse donc
                // un court délai, mais on ne bloque jamais la fermeture.
                await Task.WhenAny(
                    shutdownTask,
                    Task.Delay(
                        350));

                // Si le Core a reçu la commande, on lui laisse encore
                // un bref délai pour exécuter son arrêt propre.
                await _coreProcess
                    .WaitForOwnedCoreExitAsync(
                        TimeSpan.FromMilliseconds(
                            1200));

                // Dernier recours uniquement pour le Core que cette UI
                // a elle-même démarré.
                _coreProcess
                    .StopOwnedCoreIfStillRunning();
            }
        }
        catch (Exception exception)
        {
            UiLog.Error(
                "Atlas Core graceful shutdown failed; UI will still close.",
                exception);

            try
            {
                _coreProcess
                    .StopOwnedCoreIfStillRunning();
            }
            catch
            {
                // Rien ne doit empêcher la fermeture de l'interface.
            }
        }
        finally
        {
            // Toujours fermer Atlas Desktop, même si le Core ou l'IPC
            // ne répondent plus.
            Close();
        }
    }

    private sealed class SecondaryExplorerWindow
    {
        private readonly DesktopWindow _owner;
        private sealed class TabState
        {
            public Guid Id { get; } = Guid.NewGuid();
            public string Directory { get; set; } = string.Empty;
            public Stack<string> BackHistory { get; } = new();
            public Stack<string> ForwardHistory { get; } = new();
            public Button? Button { get; set; }
            public Border? Container { get; set; }
        }

        private readonly List<TabState> _tabs = new();
        private TabState? _activeTab;
        private readonly Stack<string> _fallbackBackHistory = new();
        private readonly Stack<string> _fallbackForwardHistory = new();

        private Stack<string> ActiveBackHistory =>
            _activeTab?.BackHistory ?? _fallbackBackHistory;

        private Stack<string> ActiveForwardHistory =>
            _activeTab?.ForwardHistory ?? _fallbackForwardHistory;

        private readonly HashSet<string> _selectedPaths =
            new(
                StringComparer.OrdinalIgnoreCase);

        private readonly Dictionary<string, Button> _entryButtons =
            new(
                StringComparer.OrdinalIgnoreCase);

        private readonly List<string> _visiblePaths =
            new();

        private string _currentDirectory;
        private string? _selectionAnchorPath;

        private readonly StackPanel _tabHost;
        private readonly TextBlock _breadcrumbText;
        private readonly TextBox _addressBox;
        private readonly TextBox _searchBox;
        private readonly StackPanel _folderList;
        private readonly TextBlock _statusText;
        private readonly TextBlock _selectionText;

        private readonly Button _cutButton;
        private readonly Button _copyButton;
        private readonly Button _pasteButton;
        private readonly Button _deleteButton;
        private readonly Button _renameButton;

        public Guid Id { get; } =
            Guid.NewGuid();

        public string DisplayTitle =>
            string.IsNullOrWhiteSpace(
                _currentDirectory)
                ? "Explorer Atlas"
                : IOPath.GetFileName(
                    _currentDirectory);

        public string CurrentDirectory =>
            _currentDirectory;

        public IReadOnlyList<string> TabDirectories =>
            _tabs
                .Select(
                    tab =>
                        tab.Directory)
                .ToArray();

        public int ActiveTabIndex =>
            _activeTab is null
                ? 0
                : Math.Max(
                    0,
                    _tabs.IndexOf(
                        _activeTab));

        public Border Panel { get; }

        public Button MaximizeButton { get; }

        public event EventHandler? Closed;

        public SecondaryExplorerWindow(
            DesktopWindow owner,
            string initialDirectory)
        {
            _owner =
                owner;

            _currentDirectory =
                ResolveInitialDirectory(
                    initialDirectory);

            _activeTab = new TabState
            {
                Directory = _currentDirectory,
            };

            _tabs.Add(_activeTab);

            Panel =
                new Border
                {
                    Width = 1120,
                    Height = 680,
                    MinWidth = 760,
                    MinHeight = 460,
                    HorizontalAlignment =
                        HorizontalAlignment.Left,
                    VerticalAlignment =
                        VerticalAlignment.Top,
                    CornerRadius =
                        new CornerRadius(
                            10),
                    Background =
                        owner.Root.Resources[
                            "AtlasWindowAcrylicBrush"]
                        as Brush,
                    BorderBrush =
                        owner.Root.Resources[
                            "AtlasWindowBorderBrush"]
                        as Brush,
                    BorderThickness =
                        new Thickness(
                            1),
                    Visibility =
                        Visibility.Visible,
                };

            Panel.PointerPressed +=
                owner.FloatingPanel_PointerPressed;

            Panel.DoubleTapped +=
                owner.FloatingPanel_DoubleTapped;

            Panel.KeyDown +=
                Panel_KeyDown;

            var root =
                new Grid();

            root.RowDefinitions.Add(
                new RowDefinition
                {
                    Height =
                        new GridLength(
                            58),
                });

            root.RowDefinitions.Add(
                new RowDefinition
                {
                    Height =
                        new GridLength(
                            54),
                });

            root.RowDefinitions.Add(
                new RowDefinition
                {
                    Height =
                        new GridLength(
                            1,
                            GridUnitType.Star),
                });

            root.RowDefinitions.Add(
                new RowDefinition
                {
                    Height =
                        new GridLength(
                            30),
                });

            Panel.Child =
                root;

            var top =
                new Grid
                {
                    Padding =
                        new Thickness(
                            14,
                            9,
                            14,
                            7),
                };

            top.ColumnDefinitions.Add(
                new ColumnDefinition
                {
                    Width =
                        GridLength.Auto,
                });

            top.ColumnDefinitions.Add(
                new ColumnDefinition
                {
                    Width =
                        new GridLength(
                            1,
                            GridUnitType.Star),
                });

            top.ColumnDefinitions.Add(
                new ColumnDefinition
                {
                    Width =
                        GridLength.Auto,
                });

            var commands =
                new StackPanel
                {
                    Orientation =
                        Orientation.Horizontal,
                    Spacing = 7,
                    VerticalAlignment =
                        VerticalAlignment.Center,
                };

            var newButton =
                CreateCommandButton(
                    "\uE710",
                    "New");

            newButton.Click +=
                async (_, _) =>
                {
                    await NewFolderAsync();
                };

            commands.Children.Add(
                newButton);

            _cutButton =
                CreateIconButton(
                    "\uE8C6",
                    "Couper");

            _cutButton.Click +=
                (_, _) =>
                {
                    CopySelection(
                        true);
                };

            commands.Children.Add(
                _cutButton);

            _copyButton =
                CreateIconButton(
                    "\uE8C8",
                    "Copier");

            _copyButton.Click +=
                (_, _) =>
                {
                    CopySelection(
                        false);
                };

            commands.Children.Add(
                _copyButton);

            _pasteButton =
                CreateIconButton(
                    "\uE77F",
                    "Coller");

            _pasteButton.Click +=
                async (_, _) =>
                {
                    await PasteAsync();
                };

            commands.Children.Add(
                _pasteButton);

            _deleteButton =
                CreateIconButton(
                    "\uE74D",
                    "Supprimer");

            _deleteButton.Click +=
                async (_, _) =>
                {
                    await DeleteSelectedAsync();
                };

            commands.Children.Add(
                _deleteButton);

            _renameButton =
                CreateIconButton(
                    "\uE712",
                    "Renommer");

            _renameButton.Click +=
                async (_, _) =>
                {
                    await RenameSelectedAsync();
                };

            commands.Children.Add(
                _renameButton);

            top.Children.Add(
                commands);

            _tabHost =
                new StackPanel
                {
                    Orientation =
                        Orientation.Horizontal,
                    Spacing = 8,
                    HorizontalAlignment =
                        HorizontalAlignment.Center,
                    VerticalAlignment =
                        VerticalAlignment.Center,
                };

            AddTabButton(
                _activeTab);

            var plusButton =
                CreateIconButton(
                    "\uE710",
                    "Nouvel onglet · Maj+clic : nouvelle fenêtre");

            plusButton.Click +=
                (_, _) =>
                {
                    if (IsModifierDown(VirtualKey.Shift))
                    {
                        _owner.OpenSecondaryExplorerWindow(
                            _currentDirectory);
                        return;
                    }

                    AddTab(_currentDirectory);
                };

            _tabHost.Children.Add(
                plusButton);

            Grid.SetColumn(
                _tabHost,
                1);

            top.Children.Add(
                _tabHost);

            var captionButtons =
                new StackPanel
                {
                    Orientation =
                        Orientation.Horizontal,
                    Spacing = 6,
                };

            var minimize =
                CreateIconButton(
                    "\uE921",
                    "Réduire");

            minimize.Width = 36;
            minimize.Height = 36;

            minimize.Click +=
                (_, _) =>
                {
                    _owner.MinimizeSecondaryExplorerWindow(
                        this);
                };

            captionButtons.Children.Add(
                minimize);

            MaximizeButton =
                CreateIconButton(
                    "\uE922",
                    "Agrandir");

            MaximizeButton.Width = 36;
            MaximizeButton.Height = 36;

            MaximizeButton.Click +=
                (_, _) =>
                {
                    _owner.ToggleFloatingWindowMaximize(
                        Panel,
                        MaximizeButton);
                };

            captionButtons.Children.Add(
                MaximizeButton);

            var close =
                CreateIconButton(
                    "\uE711",
                    "Fermer");

            close.Width = 36;
            close.Height = 36;

            close.Click +=
                (_, _) =>
                {
                    Closed?.Invoke(
                        this,
                        EventArgs.Empty);
                };

            captionButtons.Children.Add(
                close);

            Grid.SetColumn(
                captionButtons,
                2);

            top.Children.Add(
                captionButtons);

            root.Children.Add(
                top);

            var navigation =
                new Grid
                {
                    Padding =
                        new Thickness(
                            14,
                            0,
                            14,
                            9),
                    ColumnSpacing = 8,
                };

            navigation.ColumnDefinitions.Add(
                new ColumnDefinition
                {
                    Width =
                        GridLength.Auto,
                });

            navigation.ColumnDefinitions.Add(
                new ColumnDefinition
                {
                    Width =
                        new GridLength(
                            1,
                            GridUnitType.Star),
                });

            navigation.ColumnDefinitions.Add(
                new ColumnDefinition
                {
                    Width =
                        new GridLength(
                            290),
                });

            var navButtons =
                new StackPanel
                {
                    Orientation =
                        Orientation.Horizontal,
                    Spacing = 5,
                };

            var back =
                CreateIconButton(
                    "\uE72B",
                    "Retour");

            back.Click +=
                (_, _) =>
                {
                    GoBack();
                };

            navButtons.Children.Add(
                back);

            var forward =
                CreateIconButton(
                    "\uE72A",
                    "Suivant");

            forward.Click +=
                (_, _) =>
                {
                    GoForward();
                };

            navButtons.Children.Add(
                forward);

            var up =
                CreateIconButton(
                    "\uE74A",
                    "Dossier parent");

            up.Click +=
                (_, _) =>
                {
                    GoUp();
                };

            navButtons.Children.Add(
                up);

            var refresh =
                CreateIconButton(
                    "\uE72C",
                    "Actualiser");

            refresh.Click +=
                (_, _) =>
                {
                    RenderDirectory();
                };

            navButtons.Children.Add(
                refresh);

            navigation.Children.Add(
                navButtons);

            var breadcrumbBorder =
                CreateControlBorder();

            _breadcrumbText =
                new TextBlock
                {
                    VerticalAlignment =
                        VerticalAlignment.Center,
                    FontSize = 12,
                    Foreground =
                        DesktopWindow.CreateBrush(
                            "#D4ECF9"),
                    Margin =
                        new Thickness(
                            10,
                            0,
                            10,
                            0),
                };

            var breadcrumbGrid = new Grid();
            breadcrumbGrid.Children.Add(_breadcrumbText);

            _addressBox =
                new TextBox
                {
                    Visibility = Visibility.Collapsed,
                    Margin = new Thickness(4, 2, 4, 2),
                    Padding = new Thickness(8, 0, 8, 0),
                    VerticalContentAlignment = VerticalAlignment.Center,
                    Background = DesktopWindow.CreateBrush("#101924"),
                    BorderBrush = DesktopWindow.CreateBrush("#5475CFF5"),
                    BorderThickness = new Thickness(1),
                    CornerRadius = new CornerRadius(5),
                    FontSize = 12,
                    Foreground = DesktopWindow.CreateBrush("#ECF8FF"),
                };

            _addressBox.KeyDown += AddressBox_KeyDown;
            _addressBox.LostFocus += (_, _) => _addressBox.Visibility = Visibility.Collapsed;
            breadcrumbGrid.Children.Add(_addressBox);
            breadcrumbBorder.Child = breadcrumbGrid;

            Grid.SetColumn(
                breadcrumbBorder,
                1);

            navigation.Children.Add(
                breadcrumbBorder);

            var searchBorder =
                CreateControlBorder();

            var searchGrid =
                new Grid();

            searchGrid.ColumnDefinitions.Add(
                new ColumnDefinition
                {
                    Width =
                        new GridLength(
                            1,
                            GridUnitType.Star),
                });

            searchGrid.ColumnDefinitions.Add(
                new ColumnDefinition
                {
                    Width =
                        GridLength.Auto,
                });

            _searchBox =
                new TextBox
                {
                    Height = 40,
                    Background =
                        new SolidColorBrush(
                            Windows.UI.Color.FromArgb(0, 0, 0, 0)),
                    BorderThickness =
                        new Thickness(
                            0),
                    VerticalContentAlignment =
                        VerticalAlignment.Center,
                    Padding =
                        new Thickness(
                            10,
                            0,
                            0,
                            0),
                    FontSize = 12,
                };

            _searchBox.Resources[
                "TextControlBackground"] =
                new SolidColorBrush(
                    Windows.UI.Color.FromArgb(0, 0, 0, 0));

            _searchBox.Resources[
                "TextControlBackgroundPointerOver"] =
                new SolidColorBrush(
                    Windows.UI.Color.FromArgb(0, 0, 0, 0));

            _searchBox.Resources[
                "TextControlBackgroundFocused"] =
                new SolidColorBrush(
                    Windows.UI.Color.FromArgb(0, 0, 0, 0));

            _searchBox.Resources[
                "TextControlBorderBrush"] =
                new SolidColorBrush(
                    Windows.UI.Color.FromArgb(0, 0, 0, 0));

            _searchBox.Resources[
                "TextControlBorderBrushFocused"] =
                new SolidColorBrush(
                    Windows.UI.Color.FromArgb(0, 0, 0, 0));

            _searchBox.TextChanged +=
                (_, _) =>
                {
                    RenderDirectory();
                };

            searchGrid.Children.Add(
                _searchBox);

            var searchIcon =
                new FontIcon
                {
                    Glyph = "\uE721",
                    FontSize = 13,
                    Foreground =
                        DesktopWindow.CreateBrush(
                            "#8DB8D0"),
                    VerticalAlignment =
                        VerticalAlignment.Center,
                    Margin =
                        new Thickness(
                            7,
                            0,
                            10,
                            0),
                };

            Grid.SetColumn(
                searchIcon,
                1);

            searchGrid.Children.Add(
                searchIcon);

            searchBorder.Child =
                searchGrid;

            Grid.SetColumn(
                searchBorder,
                2);

            navigation.Children.Add(
                searchBorder);

            Grid.SetRow(
                navigation,
                1);

            root.Children.Add(
                navigation);

            var body =
                new Grid();

            body.ColumnDefinitions.Add(
                new ColumnDefinition
                {
                    Width =
                        new GridLength(
                            210),
                });

            body.ColumnDefinitions.Add(
                new ColumnDefinition
                {
                    Width =
                        new GridLength(
                            1),
                });

            body.ColumnDefinitions.Add(
                new ColumnDefinition
                {
                    Width =
                        new GridLength(
                            1,
                            GridUnitType.Star),
                });

            var leftNav =
                new StackPanel
                {
                    Padding =
                        new Thickness(
                            14,
                            12,
                            14,
                            12),
                    Spacing = 7,
                };

            AddLocationButton(
                leftNav,
                "Atlas",
                "\uE80F",
                () =>
                    NavigateTo(
                        _owner._workspaceRoot));

            AddLocationButton(
                leftNav,
                "Projects",
                "\uE8B7",
                () =>
                    NavigateKnownFolder(
                        "Projects"));

            AddLocationButton(
                leftNav,
                "Documents",
                "\uE8B7",
                () =>
                    NavigateKnownFolder(
                        "Documents"));

            AddLocationButton(
                leftNav,
                "Imports",
                "\uE8B7",
                () =>
                    NavigateKnownFolder(
                        "Imports"));

            body.Children.Add(
                leftNav);

            var divider =
                new Border
                {
                    Width = 1,
                    Background =
                        DesktopWindow.CreateBrush(
                            "#26575B6C"),
                };

            Grid.SetColumn(
                divider,
                1);

            body.Children.Add(
                divider);

            var contentSurface =
                new Grid
                {
                    Background =
                        new SolidColorBrush(
                            Windows.UI.Color.FromArgb(0, 0, 0, 0)),
                };

            contentSurface.RowDefinitions.Add(
                new RowDefinition
                {
                    Height =
                        new GridLength(
                            34),
                });

            contentSurface.RowDefinitions.Add(
                new RowDefinition
                {
                    Height =
                        new GridLength(
                            1,
                            GridUnitType.Star),
                });

            var header =
                new Grid
                {
                    Margin =
                        new Thickness(
                            12,
                            0,
                            12,
                            0),
                };

            AddHeaderColumn(
                header,
                "Nom",
                0,
                390);

            AddHeaderColumn(
                header,
                "Type",
                1,
                160);

            AddHeaderColumn(
                header,
                "Modifié",
                2,
                190);

            AddHeaderColumn(
                header,
                "Taille",
                3,
                120);

            contentSurface.Children.Add(
                header);

            _folderList =
                new StackPanel
                {
                    Spacing = 4,
                    Margin =
                        new Thickness(
                            8,
                            0,
                            8,
                            8),
                };

            var scroll =
                new ScrollViewer
                {
                    Content =
                        _folderList,
                    VerticalScrollBarVisibility =
                        Microsoft.UI.Xaml.Controls.ScrollBarVisibility.Auto,
                    HorizontalScrollBarVisibility =
                        Microsoft.UI.Xaml.Controls.ScrollBarVisibility.Disabled,
                };

            Grid.SetRow(
                scroll,
                1);

            contentSurface.Children.Add(
                scroll);

            contentSurface.PointerPressed +=
                (_, args) =>
                {
                    if (
                        !IsPointerOverEntry(
                            args.OriginalSource
                            as DependencyObject)
                    )
                    {
                        ClearSelection();
                    }
                };

            Grid.SetColumn(
                contentSurface,
                2);

            body.Children.Add(
                contentSurface);

            Grid.SetRow(
                body,
                2);

            root.Children.Add(
                body);

            var footer =
                new Grid
                {
                    Padding =
                        new Thickness(
                            12,
                            0,
                            12,
                            0),
                };

            footer.ColumnDefinitions.Add(
                new ColumnDefinition
                {
                    Width =
                        GridLength.Auto,
                });

            footer.ColumnDefinitions.Add(
                new ColumnDefinition
                {
                    Width =
                        GridLength.Auto,
                });

            _statusText =
                new TextBlock
                {
                    VerticalAlignment =
                        VerticalAlignment.Center,
                    FontSize = 10,
                    Foreground =
                        DesktopWindow.CreateBrush(
                            "#8F92A4"),
                };

            footer.Children.Add(
                _statusText);

            _selectionText =
                new TextBlock
                {
                    VerticalAlignment =
                        VerticalAlignment.Center,
                    FontSize = 10,
                    Margin =
                        new Thickness(
                            12,
                            0,
                            0,
                            0),
                    Foreground =
                        DesktopWindow.CreateBrush(
                            "#9AB7C8"),
                };

            Grid.SetColumn(
                _selectionText,
                1);

            footer.Children.Add(
                _selectionText);

            Grid.SetRow(
                footer,
                3);

            root.Children.Add(
                footer);

            NavigateTo(
                _currentDirectory,
                false);
        }

        public void RestoreTabs(
            IReadOnlyList<string> directories,
            int activeIndex)
        {
            if (
                directories.Count == 0
                || _tabHost.Children.Count == 0
            )
            {
                return;
            }

            var plusButton =
                _tabHost.Children[
                    _tabHost.Children.Count - 1];

            _tabHost.Children.Clear();
            _tabs.Clear();

            foreach (
                var directory
                in directories)
            {
                var tab =
                    new TabState
                    {
                        Directory =
                            ResolveInitialDirectory(
                                directory),
                    };

                _tabs.Add(
                    tab);

                AddTabButton(
                    tab);
            }

            _tabHost.Children.Add(
                plusButton);

            activeIndex =
                Math.Clamp(
                    activeIndex,
                    0,
                    _tabs.Count - 1);

            _activeTab =
                _tabs[
                    activeIndex];

            _currentDirectory =
                _activeTab.Directory;

            _searchBox.Text =
                string.Empty;

            NavigateTo(
                _currentDirectory,
                false);

            UpdateTabVisuals();
        }

        private void AddTab(
            string directory)
        {
            if (_activeTab is not null)
            {
                _activeTab.Directory =
                    _currentDirectory;
            }

            var tab =
                new TabState
                {
                    Directory =
                        ResolveInitialDirectory(
                            directory),
                };

            _tabs.Add(
                tab);

            AddTabButton(
                tab);

            ActivateTab(
                tab);

            _owner.SaveSecondaryExplorerLayouts();
        }

        private void AddTabButton(
            TabState tab)
        {
            var container =
                new Border
                {
                    Height = 34,
                    MinWidth = 82,
                    MaxWidth = 190,
                    CornerRadius =
                        new CornerRadius(
                            7),
                    BorderThickness =
                        new Thickness(
                            1),
                };

            var layout =
                new Grid();

            layout.ColumnDefinitions.Add(
                new ColumnDefinition
                {
                    Width =
                        new GridLength(
                            1,
                            GridUnitType.Star),
                });

            layout.ColumnDefinitions.Add(
                new ColumnDefinition
                {
                    Width =
                        GridLength.Auto,
                });

            var tabContent =
                new StackPanel
                {
                    Orientation =
                        Orientation.Horizontal,
                    Spacing = 7,
                };

            tabContent.Children.Add(
                new FontIcon
                {
                    Glyph = "\uE8B7",
                    FontSize = 14,
                    Foreground =
                        DesktopWindow.CreateBrush(
                            "#5FD0FF"),
                });

            var label =
                new TextBlock
                {
                    Text =
                        GetTabName(
                            tab.Directory),
                    FontSize = 12,
                    FontWeight =
                        Microsoft.UI.Text
                            .FontWeights.SemiBold,
                    Foreground =
                        DesktopWindow.CreateBrush(
                            "#E8E8EF"),
                    VerticalAlignment =
                        VerticalAlignment.Center,
                    TextTrimming =
                        TextTrimming.CharacterEllipsis,
                };

            tabContent.Children.Add(
                label);

            var button =
                new Button
                {
                    Height = 32,
                    MinWidth = 52,
                    MaxWidth = 154,
                    Padding =
                        new Thickness(
                            11,
                            0,
                            7,
                            0),
                    Background =
                        DesktopWindow.CreateBrush(
                            "#00000000"),
                    BorderThickness =
                        new Thickness(
                            0),
                    HorizontalContentAlignment =
                        HorizontalAlignment.Left,
                    Content =
                        tabContent,
                };

            button.Click +=
                (_, _) =>
                    ActivateTab(
                        tab);

            layout.Children.Add(
                button);

            var closeButton =
                new Button
                {
                    Width = 28,
                    Height = 28,
                    Padding =
                        new Thickness(
                            0),
                    Margin =
                        new Thickness(
                            0,
                            0,
                            3,
                            0),
                    Background =
                        DesktopWindow.CreateBrush(
                            "#00000000"),
                    BorderThickness =
                        new Thickness(
                            0),
                    CornerRadius =
                        new CornerRadius(
                            5),
                    Content =
                        new FontIcon
                        {
                            Glyph = "\uE711",
                            FontSize = 10,
                            Foreground =
                                DesktopWindow.CreateBrush(
                                    "#AEB2BF"),
                        },
                };

            ToolTipService.SetToolTip(
                closeButton,
                "Fermer l’onglet");

            closeButton.Click +=
                (_, _) =>
                    CloseTab(
                        tab);

            Grid.SetColumn(
                closeButton,
                1);

            layout.Children.Add(
                closeButton);

            container.Child =
                layout;

            tab.Button =
                button;

            tab.Container =
                container;

            var insertIndex =
                Math.Max(
                    0,
                    _tabHost.Children.Count - 1);

            if (_tabHost.Children.Count == 0)
            {
                _tabHost.Children.Add(
                    container);
            }
            else
            {
                _tabHost.Children.Insert(
                    insertIndex,
                    container);
            }
        }

        private void CloseTab(
            TabState tab)
        {
            var index =
                _tabs.IndexOf(
                    tab);

            if (index < 0)
            {
                return;
            }

            var wasActive =
                ReferenceEquals(
                    tab,
                    _activeTab);

            if (wasActive)
            {
                tab.Directory =
                    _currentDirectory;
            }

            if (
                tab.Container
                is not null
            )
            {
                _tabHost.Children.Remove(
                    tab.Container);
            }

            _tabs.RemoveAt(
                index);

            if (_tabs.Count == 0)
            {
                _activeTab =
                    null;

                Closed?.Invoke(
                    this,
                    EventArgs.Empty);

                return;
            }

            if (!wasActive)
            {
                UpdateTabVisuals();

                _owner.SaveSecondaryExplorerLayouts();

                return;
            }

            var nextIndex =
                Math.Min(
                    index,
                    _tabs.Count - 1);

            ActivateTab(
                _tabs[
                    nextIndex
                ]);
        }

        private void ActivateTab(
            TabState tab)
        {
            if (_activeTab is not null)
            {
                _activeTab.Directory =
                    _currentDirectory;
            }

            _activeTab =
                tab;

            _searchBox.Text =
                string.Empty;

            NavigateTo(
                tab.Directory,
                false);

            UpdateTabVisuals();

            _owner.SaveSecondaryExplorerLayouts();
        }

        private void UpdateTabVisuals()
        {
            foreach (
                var tab
                in _tabs
            )
            {
                if (
                    tab.Button is null
                )
                {
                    continue;
                }

                var active =
                    ReferenceEquals(
                        tab,
                        _activeTab);

                if (
                    tab.Container
                    is not null
                )
                {
                    tab.Container.Background =
                        active
                            ? _owner.Root.Resources[
                                "AtlasWindowControlBrush"]
                                as Brush
                            : DesktopWindow.CreateBrush(
                                "#161A2330");

                    tab.Container.BorderBrush =
                        active
                            ? DesktopWindow.CreateBrush(
                                "#4A62677A")
                            : _owner.Root.Resources[
                                "AtlasWindowInnerBorderBrush"]
                                as Brush;
                }

                if (
                    tab.Button.Content
                    is StackPanel content
                    && content.Children
                        .OfType<TextBlock>()
                        .FirstOrDefault()
                    is TextBlock label
                )
                {
                    label.Text =
                        GetTabName(
                            tab.Directory);
                }
            }
        }

        private string GetTabName(string directory)
        {
            try
            {
                var root = IOPath.GetFullPath(_owner._workspaceRoot);
                var resolved = IOPath.GetFullPath(directory);

                if (string.Equals(root, resolved, StringComparison.OrdinalIgnoreCase))
                {
                    return "Atlas";
                }

                var name = IOPath.GetFileName(resolved);
                return string.IsNullOrWhiteSpace(name) ? "Atlas" : name;
            }
            catch
            {
                return "Atlas";
            }
        }

        private string ResolveInitialDirectory(
            string directory)
        {
            try
            {
                var resolved =
                    IOPath.GetFullPath(
                        directory);

                var root =
                    IOPath.GetFullPath(
                        _owner._workspaceRoot);

                if (
                    Directory.Exists(
                        resolved)
                    && IsInsideWorkspace(
                        resolved,
                        root)
                )
                {
                    return resolved;
                }
            }
            catch
            {
            }

            return IOPath.GetFullPath(
                _owner._workspaceRoot);
        }

        private static bool IsInsideWorkspace(
            string path,
            string root)
        {
            var relative =
                IOPath.GetRelativePath(
                    root,
                    path);

            return (
                !relative.Equals(
                    "..",
                    StringComparison.Ordinal)
                && !relative.StartsWith(
                    ".."
                    + IOPath.DirectorySeparatorChar,
                    StringComparison.Ordinal)
                && !IOPath.IsPathRooted(
                    relative)
            );
        }

        private Border CreateControlBorder()
        {
            return new Border
            {
                Height = 40,
                CornerRadius =
                    new CornerRadius(
                        7),
                Background =
                    _owner.Root.Resources[
                        "AtlasWindowControlBrush"]
                    as Brush,
                BorderBrush =
                    _owner.Root.Resources[
                        "AtlasWindowInnerBorderBrush"]
                    as Brush,
                BorderThickness =
                    new Thickness(
                        1),
            };
        }

        private Button CreateIconButton(
            string glyph,
            string tooltip)
        {
            var button =
                new Button
                {
                    Width = 34,
                    Height = 34,
                    Padding =
                        new Thickness(
                            0),
                    Background =
                        new SolidColorBrush(
                            Windows.UI.Color.FromArgb(0, 0, 0, 0)),
                    BorderBrush =
                        _owner.Root.Resources[
                            "AtlasWindowInnerBorderBrush"]
                        as Brush,
                    BorderThickness =
                        new Thickness(
                            1),
                    CornerRadius =
                        new CornerRadius(
                            7),
                    Content =
                        new FontIcon
                        {
                            Glyph = glyph,
                            FontSize = 13,
                            Foreground =
                                DesktopWindow.CreateBrush(
                                    "#D8D9E2"),
                        },
                };

            ToolTipService.SetToolTip(
                button,
                tooltip);

            return button;
        }

        private Button CreateCommandButton(
            string glyph,
            string text)
        {
            var content =
                new StackPanel
                {
                    Orientation =
                        Orientation.Horizontal,
                    Spacing = 6,
                };

            content.Children.Add(
                new FontIcon
                {
                    Glyph = glyph,
                    FontSize = 13,
                });

            content.Children.Add(
                new TextBlock
                {
                    Text = text,
                    FontSize = 12,
                });

            return new Button
            {
                Height = 34,
                Padding =
                    new Thickness(
                        12,
                        0,
                        12,
                        0),
                Background =
                    new SolidColorBrush(
                        Windows.UI.Color.FromArgb(0, 0, 0, 0)),
                BorderBrush =
                    _owner.Root.Resources[
                        "AtlasWindowInnerBorderBrush"]
                    as Brush,
                BorderThickness =
                    new Thickness(
                        1),
                CornerRadius =
                    new CornerRadius(
                        7),
                Foreground =
                    DesktopWindow.CreateBrush(
                        "#E8E8EF"),
                Content =
                    content,
            };
        }

        private void AddLocationButton(
            Panel panel,
            string text,
            string glyph,
            Action action)
        {
            var content =
                new StackPanel
                {
                    Orientation =
                        Orientation.Horizontal,
                    Spacing = 10,
                };

            content.Children.Add(
                new FontIcon
                {
                    Glyph = glyph,
                    FontSize = 14,
                    Foreground =
                        DesktopWindow.CreateBrush(
                            "#5FD0FF"),
                });

            content.Children.Add(
                new TextBlock
                {
                    Text = text,
                    FontSize = 12,
                    Foreground =
                        DesktopWindow.CreateBrush(
                            "#E8E8EF"),
                });

            var button =
                new Button
                {
                    HorizontalAlignment =
                        HorizontalAlignment.Stretch,
                    HorizontalContentAlignment =
                        HorizontalAlignment.Left,
                    Padding =
                        new Thickness(
                            10,
                            8,
                            10,
                            8),
                    Background =
                        new SolidColorBrush(
                            Windows.UI.Color.FromArgb(0, 0, 0, 0)),
                    BorderThickness =
                        new Thickness(
                            0),
                    Content =
                        content,
                };

            button.Click +=
                (_, _) =>
                {
                    action();
                };

            panel.Children.Add(
                button);
        }

        private static void AddHeaderColumn(
            Grid grid,
            string text,
            int column,
            double width)
        {
            while (
                grid.ColumnDefinitions.Count
                <= column
            )
            {
                grid.ColumnDefinitions.Add(
                    new ColumnDefinition());
            }

            grid.ColumnDefinitions[
                column
            ].Width =
                new GridLength(
                    width);

            var label =
                new TextBlock
                {
                    Text = text,
                    FontSize = 10,
                    VerticalAlignment =
                        VerticalAlignment.Center,
                    Foreground =
                        new SolidColorBrush(
                            Windows.UI.Color.FromArgb(
                                210,
                                143,
                                146,
                                164)),
                };

            Grid.SetColumn(
                label,
                column);

            grid.Children.Add(
                label);
        }

        private void NavigateKnownFolder(
            string name)
        {
            var path =
                IOPath.Combine(
                    _owner._workspaceRoot,
                    name);

            if (Directory.Exists(path))
            {
                NavigateTo(
                    path);
            }
        }

        private void NavigateTo(
            string directory,
            bool addHistory = true)
        {
            try
            {
                var resolved =
                    IOPath.GetFullPath(
                        directory);

                var root =
                    IOPath.GetFullPath(
                        _owner._workspaceRoot);

                if (
                    !Directory.Exists(
                        resolved)
                    || !IsInsideWorkspace(
                        resolved,
                        root)
                )
                {
                    return;
                }

                if (
                    addHistory
                    && !string.IsNullOrWhiteSpace(
                        _currentDirectory)
                    && !string.Equals(
                        _currentDirectory,
                        resolved,
                        StringComparison.OrdinalIgnoreCase)
                )
                {
                    ActiveBackHistory.Push(
                        _currentDirectory);

                    ActiveForwardHistory.Clear();
                }

                _currentDirectory =
                    resolved;

                if (_activeTab is not null)
                {
                    _activeTab.Directory = resolved;
                }

                ClearSelection();

                var tabDisplayName =
                    GetTabName(
                        resolved);

                _breadcrumbText.Text =
                    BuildBreadcrumb(
                        resolved);

                _searchBox.PlaceholderText =
                    "Rechercher dans "
                    + tabDisplayName;

                UpdateTabVisuals();
                RenderDirectory();

                _owner.SaveSecondaryExplorerLayouts();
            }
            catch
            {
            }
        }

        private string BuildBreadcrumb(
            string directory)
        {
            var root =
                IOPath.GetFullPath(
                    _owner._workspaceRoot);

            if (
                string.Equals(
                    root,
                    directory,
                    StringComparison.OrdinalIgnoreCase)
            )
            {
                return "Atlas";
            }

            var relative =
                IOPath.GetRelativePath(
                    root,
                    directory);

            return "Atlas  ›  "
                + relative.Replace(
                    IOPath.DirectorySeparatorChar,
                    '›');
        }

        private async void Panel_KeyDown(
            object sender,
            KeyRoutedEventArgs e)
        {
            var ctrl = DesktopWindow.IsModifierDown(VirtualKey.Control);
            var alt = DesktopWindow.IsModifierDown(VirtualKey.Menu);
            var shift = DesktopWindow.IsModifierDown(VirtualKey.Shift);

            var textInputActive =
                e.OriginalSource
                is TextBox;

            if (
                textInputActive
                && (
                    (
                        ctrl
                        && (
                            e.Key == VirtualKey.A
                            || e.Key == VirtualKey.C
                            || e.Key == VirtualKey.X
                            || e.Key == VirtualKey.V
                        )
                    )
                    || e.Key == VirtualKey.F2
                    || e.Key == VirtualKey.Delete
                )
            )
            {
                return;
            }

            if (ctrl && e.Key == VirtualKey.A)
            {
                _selectedPaths.Clear();

                foreach (var path in _visiblePaths)
                {
                    _selectedPaths.Add(path);
                }

                _selectionAnchorPath =
                    _visiblePaths.LastOrDefault();

                UpdateSelectionUi();

                e.Handled = true;
                return;
            }

            if (ctrl && e.Key == VirtualKey.C)
            {
                CopySelection(false);
                e.Handled = true;
                return;
            }

            if (ctrl && e.Key == VirtualKey.X)
            {
                CopySelection(true);
                e.Handled = true;
                return;
            }

            if (ctrl && e.Key == VirtualKey.V)
            {
                await PasteAsync();
                e.Handled = true;
                return;
            }

            if (e.Key == VirtualKey.F2)
            {
                await RenameSelectedAsync();
                e.Handled = true;
                return;
            }

            if (e.Key == VirtualKey.Delete)
            {
                await DeleteSelectedAsync();
                e.Handled = true;
                return;
            }

            if (ctrl && e.Key == VirtualKey.T)
            {
                AddTab(_currentDirectory);
                e.Handled = true;
                return;
            }

            if (ctrl && e.Key == VirtualKey.W)
            {
                if (_activeTab is not null) CloseTab(_activeTab);
                e.Handled = true;
                return;
            }

            if (ctrl && e.Key == VirtualKey.L)
            {
                _addressBox.Text = _currentDirectory;
                _addressBox.Visibility = Visibility.Visible;
                _addressBox.Focus(FocusState.Programmatic);
                _addressBox.SelectAll();
                e.Handled = true;
                return;
            }

            if (ctrl && e.Key == VirtualKey.F)
            {
                _searchBox.Focus(
                    FocusState.Programmatic);

                _searchBox.SelectAll();

                e.Handled = true;
                return;
            }

            if (
                ctrl
                && shift
                && e.Key == VirtualKey.N
            )
            {
                await NewFolderAsync();

                e.Handled = true;
                return;
            }

            if (ctrl && e.Key == VirtualKey.N)
            {
                _owner.OpenSecondaryExplorerWindow(
                    _currentDirectory);

                e.Handled = true;
                return;
            }

            if (
                !textInputActive
                && e.Key == VirtualKey.Enter
            )
            {
                if (_selectedPaths.Count == 1)
                {
                    var selectedPath =
                        _selectedPaths.First();

                    ActivateEntry(
                        selectedPath);
                }

                e.Handled = true;
                return;
            }

            if (
                !textInputActive
                && e.Key == VirtualKey.Back
            )
            {
                GoBack();

                e.Handled = true;
                return;
            }

            if (e.Key == VirtualKey.F5)
            {
                RenderDirectory();

                e.Handled = true;
                return;
            }

            if (alt && e.Key == VirtualKey.Up)
            {
                GoUp();

                e.Handled = true;
                return;
            }

            if (alt && e.Key == VirtualKey.Left)
            {
                GoBack();
                e.Handled = true;
                return;
            }

            if (alt && e.Key == VirtualKey.Right)
            {
                GoForward();
                e.Handled = true;
            }
        }

        private void AddressBox_KeyDown(
            object sender,
            KeyRoutedEventArgs e)
        {
            if (e.Key == VirtualKey.Escape)
            {
                _addressBox.Visibility = Visibility.Collapsed;
                e.Handled = true;
                return;
            }

            if (e.Key == VirtualKey.Enter)
            {
                var requested = _addressBox.Text.Trim();
                _addressBox.Visibility = Visibility.Collapsed;
                if (!string.IsNullOrWhiteSpace(requested))
                {
                    NavigateTo(requested);
                }
                e.Handled = true;
            }
        }

        private void GoForward()
        {
            if (ActiveForwardHistory.Count == 0) return;

            if (!string.IsNullOrWhiteSpace(_currentDirectory))
            {
                ActiveBackHistory.Push(_currentDirectory);
            }

            NavigateTo(ActiveForwardHistory.Pop(), false);
        }

        private void GoBack()
        {
            if (ActiveBackHistory.Count == 0) return;

            if (!string.IsNullOrWhiteSpace(_currentDirectory))
            {
                ActiveForwardHistory.Push(_currentDirectory);
            }

            NavigateTo(ActiveBackHistory.Pop(), false);
        }

        private void GoUp()
        {
            var root =
                IOPath.GetFullPath(
                    _owner._workspaceRoot);

            if (
                string.Equals(
                    root,
                    _currentDirectory,
                    StringComparison.OrdinalIgnoreCase)
            )
            {
                return;
            }

            var parent =
                Directory.GetParent(
                    _currentDirectory);

            if (parent is not null)
            {
                NavigateTo(
                    parent.FullName);
            }
        }

        private void RenderDirectory()
        {
            _folderList.Children.Clear();
            _entryButtons.Clear();
            _visiblePaths.Clear();

            IEnumerable<string> entries;

            try
            {
                entries =
                    Directory
                        .EnumerateFileSystemEntries(
                            _currentDirectory);
            }
            catch
            {
                entries =
                    Array.Empty<string>();
            }

            var search =
                _searchBox.Text;

            if (
                !string.IsNullOrWhiteSpace(
                    search)
            )
            {
                entries =
                    entries.Where(
                        path =>
                            IOPath.GetFileName(
                                path)
                            .Contains(
                                search.Trim(),
                                StringComparison
                                    .CurrentCultureIgnoreCase));
            }

            entries =
                entries
                    .OrderByDescending(
                        Directory.Exists)
                    .ThenBy(
                        IOPath.GetFileName,
                        StringComparer
                            .CurrentCultureIgnoreCase);

            var list =
                entries.ToArray();

            _visiblePaths.AddRange(
                list);

            foreach (
                var path
                in list
            )
            {
                _folderList.Children.Add(
                    CreateRow(
                        path));
            }

            _statusText.Text =
                list.Length switch
                {
                    0 => "Aucun élément",
                    1 => "1 élément",
                    _ => $"{list.Length} éléments",
                };

            UpdateSelectionUi();
        }

        private Button CreateRow(
            string path)
        {
            var isDirectory =
                Directory.Exists(
                    path);

            var row =
                new Grid
                {
                    Height = 42,
                };

            row.ColumnDefinitions.Add(
                new ColumnDefinition
                {
                    Width =
                        new GridLength(
                            390),
                });

            row.ColumnDefinitions.Add(
                new ColumnDefinition
                {
                    Width =
                        new GridLength(
                            160),
                });

            row.ColumnDefinitions.Add(
                new ColumnDefinition
                {
                    Width =
                        new GridLength(
                            190),
                });

            row.ColumnDefinitions.Add(
                new ColumnDefinition
                {
                    Width =
                        new GridLength(
                            120),
                });

            var namePanel =
                new StackPanel
                {
                    Orientation =
                        Orientation.Horizontal,
                    Spacing = 9,
                    VerticalAlignment =
                        VerticalAlignment.Center,
                };

            namePanel.Children.Add(
                new FontIcon
                {
                    Glyph =
                        isDirectory
                            ? "\uE8B7"
                            : "\uE8A5",
                    FontSize = 15,
                    Foreground =
                        DesktopWindow.CreateBrush(
                            "#55C8FF"),
                });

            namePanel.Children.Add(
                new TextBlock
                {
                    Text =
                        IOPath.GetFileName(
                            path),
                    FontSize = 12,
                    FontWeight =
                        Microsoft.UI.Text
                            .FontWeights.SemiBold,
                    Foreground =
                        DesktopWindow.CreateBrush(
                            "#E8E8EF"),
                    VerticalAlignment =
                        VerticalAlignment.Center,
                });

            row.Children.Add(
                namePanel);

            var type =
                new TextBlock
                {
                    Text =
                        isDirectory
                            ? "Dossier"
                            : GetDisplayType(
                                path),
                    FontSize = 11,
                    Foreground =
                        DesktopWindow.CreateBrush(
                            "#9294A4"),
                    VerticalAlignment =
                        VerticalAlignment.Center,
                };

            Grid.SetColumn(
                type,
                1);

            row.Children.Add(
                type);

            DateTime modified;

            try
            {
                modified =
                    File.GetLastWriteTime(
                        path);
            }
            catch
            {
                modified =
                    DateTime.MinValue;
            }

            var modifiedText =
                new TextBlock
                {
                    Text =
                        modified
                        == DateTime.MinValue
                            ? ""
                            : modified.ToString(
                                "dd/MM/yyyy HH:mm"),
                    FontSize = 11,
                    Foreground =
                        DesktopWindow.CreateBrush(
                            "#9294A4"),
                    VerticalAlignment =
                        VerticalAlignment.Center,
                };

            Grid.SetColumn(
                modifiedText,
                2);

            row.Children.Add(
                modifiedText);

            var size =
                new TextBlock
                {
                    Text =
                        isDirectory
                            ? ""
                            : FormatSize(
                                GetFileSize(
                                    path)),
                    FontSize = 11,
                    Foreground =
                        DesktopWindow.CreateBrush(
                            "#9294A4"),
                    VerticalAlignment =
                        VerticalAlignment.Center,
                };

            Grid.SetColumn(
                size,
                3);

            row.Children.Add(
                size);

            var button =
                new Button
                {
                    Height = 42,
                    HorizontalAlignment =
                        HorizontalAlignment.Stretch,
                    HorizontalContentAlignment =
                        HorizontalAlignment.Stretch,
                    Padding =
                        new Thickness(
                            12,
                            0,
                            12,
                            0),
                    Background =
                        DesktopWindow.CreateBrush(
                            "#071B2734"),
                    BorderBrush =
                        DesktopWindow.CreateBrush(
                            "#14779EBB"),
                    BorderThickness =
                        new Thickness(
                            1),
                    CornerRadius =
                        new CornerRadius(
                            7),
                    Content =
                        row,
                    Tag =
                        path,
                };

            button.Click +=
                (_, _) =>
                {
                    SelectEntry(
                        path);
                };

            button.DoubleTapped +=
                (_, _) =>
                {
                    ActivateEntry(
                        path);
                };

            button.ContextFlyout =
                CreateContextMenu(
                    path);

            _entryButtons[
                path
            ] = button;

            return button;
        }

        private MenuFlyout CreateContextMenu(
            string path)
        {
            var menu =
                new MenuFlyout();

            var open =
                new MenuFlyoutItem
                {
                    Text = "Ouvrir",
                };

            open.Click +=
                (_, _) =>
                {
                    ActivateEntry(
                        path);
                };

            menu.Items.Add(
                open);

            var rename =
                new MenuFlyoutItem
                {
                    Text = "Renommer",
                };

            rename.Click +=
                async (_, _) =>
                {
                    SelectOnly(
                        path);

                    await RenameSelectedAsync();
                };

            menu.Items.Add(
                rename);

            var copy =
                new MenuFlyoutItem
                {
                    Text = "Copier",
                };

            copy.Click +=
                (_, _) =>
                {
                    SelectOnly(
                        path);

                    CopySelection(
                        false);
                };

            menu.Items.Add(
                copy);

            var cut =
                new MenuFlyoutItem
                {
                    Text = "Couper",
                };

            cut.Click +=
                (_, _) =>
                {
                    SelectOnly(
                        path);

                    CopySelection(
                        true);
                };

            menu.Items.Add(
                cut);

            var delete =
                new MenuFlyoutItem
                {
                    Text = "Supprimer",
                };

            delete.Click +=
                async (_, _) =>
                {
                    SelectOnly(
                        path);

                    await DeleteSelectedAsync();
                };

            menu.Items.Add(
                delete);

            return menu;
        }

        private bool IsPointerOverEntry(
            DependencyObject? source)
        {
            var current =
                source;

            while (current is not null)
            {
                if (
                    current is Button button
                    && button.Tag is string path
                    && _entryButtons.TryGetValue(
                        path,
                        out var known)
                    && ReferenceEquals(
                        button,
                        known)
                )
                {
                    return true;
                }

                current =
                    VisualTreeHelper.GetParent(
                        current);
            }

            return false;
        }

        private void SelectEntry(
            string path)
        {
            var control =
                IsModifierDown(
                    VirtualKey.Control);

            var shift =
                IsModifierDown(
                    VirtualKey.Shift);

            if (
                shift
                && !string.IsNullOrWhiteSpace(
                    _selectionAnchorPath)
            )
            {
                SelectRange(
                    _selectionAnchorPath,
                    path,
                    control);

                return;
            }

            if (control)
            {
                if (
                    !_selectedPaths.Add(
                        path)
                )
                {
                    _selectedPaths.Remove(
                        path);
                }

                _selectionAnchorPath =
                    path;

                UpdateSelectionUi();

                return;
            }

            SelectOnly(
                path);
        }

        private void SelectRange(
            string anchor,
            string current,
            bool preserveExisting)
        {
            var anchorIndex =
                _visiblePaths.FindIndex(
                    path =>
                        string.Equals(
                            path,
                            anchor,
                            StringComparison.OrdinalIgnoreCase));

            var currentIndex =
                _visiblePaths.FindIndex(
                    path =>
                        string.Equals(
                            path,
                            current,
                            StringComparison.OrdinalIgnoreCase));

            if (
                anchorIndex < 0
                || currentIndex < 0
            )
            {
                SelectOnly(
                    current);

                return;
            }

            if (!preserveExisting)
            {
                _selectedPaths.Clear();
            }

            var first =
                Math.Min(
                    anchorIndex,
                    currentIndex);

            var last =
                Math.Max(
                    anchorIndex,
                    currentIndex);

            for (
                var index = first;
                index <= last;
                index++
            )
            {
                _selectedPaths.Add(
                    _visiblePaths[
                        index
                    ]);
            }

            UpdateSelectionUi();
        }

        private void SelectOnly(
            string path)
        {
            _selectedPaths.Clear();

            _selectedPaths.Add(
                path);

            _selectionAnchorPath =
                path;

            UpdateSelectionUi();
        }

        private void ClearSelection()
        {
            _selectedPaths.Clear();

            _selectionAnchorPath =
                null;

            UpdateSelectionUi();
        }

        private void UpdateSelectionUi()
        {
            foreach (
                var pair
                in _entryButtons
            )
            {
                var selected =
                    _selectedPaths.Contains(
                        pair.Key);

                pair.Value.Background =
                    DesktopWindow.CreateBrush(
                        selected
                            ? "#372E5F7E"
                            : "#071B2734");

                pair.Value.BorderBrush =
                    DesktopWindow.CreateBrush(
                        selected
                            ? "#7855C8FF"
                            : "#14779EBB");
            }

            _selectionText.Text =
                _selectedPaths.Count switch
                {
                    0 => "",
                    1 => "1 sélectionné",
                    _ =>
                        $"{_selectedPaths.Count} sélectionnés",
                };

            var hasSelection =
                _selectedPaths.Count > 0;

            _cutButton.IsEnabled =
                hasSelection;

            _copyButton.IsEnabled =
                hasSelection;

            _deleteButton.IsEnabled =
                hasSelection;

            _renameButton.IsEnabled =
                _selectedPaths.Count == 1;

            _pasteButton.IsEnabled =
                _owner._clipboardPaths.Count > 0;
        }

        private void CopySelection(
            bool move)
        {
            if (_selectedPaths.Count == 0)
            {
                return;
            }

            _owner._clipboardPaths =
                _selectedPaths.ToArray();

            _owner._clipboardMove =
                move;

            _pasteButton.IsEnabled =
                true;

            _selectionText.Text =
                move
                    ? $"{_selectedPaths.Count} prêt(s) à déplacer"
                    : $"{_selectedPaths.Count} prêt(s) à copier";
        }

        private async Task NewFolderAsync()
        {
            if (_owner._workspaceFiles is null)
            {
                return;
            }

            var name =
                await _owner.PromptTextAsync(
                    "Nouveau dossier",
                    "Nom du dossier",
                    "Nouveau dossier");

            if (name is null)
            {
                return;
            }

            try
            {
                _owner._workspaceFiles
                    .CreateFolder(
                        _currentDirectory,
                        name);

                RenderDirectory();
            }
            catch (Exception exception)
            {
                await _owner.ShowMessageAsync(
                    "Création impossible",
                    exception.Message);
            }
        }

        private async Task RenameSelectedAsync()
        {
            if (
                _owner._workspaceFiles is null
                || _selectedPaths.Count != 1
            )
            {
                return;
            }

            var source =
                _selectedPaths.First();

            var currentName =
                IOPath.GetFileName(
                    source);

            var name =
                await _owner.PromptTextAsync(
                    "Renommer",
                    "Nouveau nom",
                    currentName);

            if (name is null)
            {
                return;
            }

            try
            {
                _owner._workspaceFiles
                    .Rename(
                        source,
                        name);

                ClearSelection();

                RenderDirectory();
            }
            catch (Exception exception)
            {
                await _owner.ShowMessageAsync(
                    "Renommage impossible",
                    exception.Message);
            }
        }

        private async Task DeleteSelectedAsync()
        {
            if (
                _owner._workspaceFiles is null
                || _selectedPaths.Count == 0
            )
            {
                return;
            }

            var dialog =
                new ContentDialog
                {
                    Title = "Supprimer",
                    Content =
                        _selectedPaths.Count == 1
                            ? "Supprimer définitivement cet élément ?"
                            : $"Supprimer définitivement les {_selectedPaths.Count} éléments sélectionnés ?",
                    PrimaryButtonText = "Supprimer",
                    CloseButtonText = "Annuler",
                    DefaultButton =
                        ContentDialogButton.Close,
                    XamlRoot =
                        _owner.Root.XamlRoot,
                };

            _owner.ApplyAtlasDialogStyle(
                dialog);

            if (
                await dialog.ShowAsync()
                != ContentDialogResult.Primary
            )
            {
                return;
            }

            try
            {
                _owner._workspaceFiles
                    .Delete(
                        _selectedPaths);

                ClearSelection();

                RenderDirectory();
            }
            catch (Exception exception)
            {
                await _owner.ShowMessageAsync(
                    "Suppression impossible",
                    exception.Message);
            }
        }

        private async Task PasteAsync()
        {
            if (
                _owner._workspaceFiles is null
                || _owner._clipboardPaths.Count == 0
            )
            {
                return;
            }

            try
            {
                _owner._workspaceFiles
                    .CopyIntoDirectory(
                        _owner._clipboardPaths,
                        _currentDirectory,
                        _owner._clipboardMove);

                if (_owner._clipboardMove)
                {
                    _owner._clipboardPaths =
                        Array.Empty<string>();

                    _owner._clipboardMove =
                        false;
                }

                RenderDirectory();
            }
            catch (Exception exception)
            {
                await _owner.ShowMessageAsync(
                    "Collage impossible",
                    exception.Message);
            }
        }

        private void ActivateEntry(
            string path)
        {
            if (Directory.Exists(path))
            {
                NavigateTo(
                    path);

                return;
            }

            try
            {
                System.Diagnostics.Process.Start(
                    new System.Diagnostics.ProcessStartInfo
                    {
                        FileName =
                            path,
                        UseShellExecute =
                            true,
                    });
            }
            catch
            {
            }
        }

        private static long GetFileSize(
            string path)
        {
            try
            {
                return new FileInfo(
                    path).Length;
            }
            catch
            {
                return 0;
            }
        }
    }

    private void UpdateStorageWidget()
    {
        try
        {
            var config =
                _config.Load();

            var storageRoot =
                string.IsNullOrWhiteSpace(
                    config.StorageRoot)
                    ? @"C:\Atlas"
                    : config.StorageRoot;

            StorageWidgetRootText.Text =
                storageRoot;

            var root =
                IOPath.GetPathRoot(
                    storageRoot);

            if (string.IsNullOrWhiteSpace(
                    root))
            {
                SetStorageWidgetUnavailable(
                    "Volume introuvable");

                return;
            }

            var drive =
                new System.IO.DriveInfo(
                    root);

            if (!drive.IsReady)
            {
                SetStorageWidgetUnavailable(
                    "Volume indisponible");

                return;
            }

            var total =
                drive.TotalSize;

            var free =
                drive.AvailableFreeSpace;

            var used =
                Math.Max(
                    0,
                    total
                    - free);

            var usagePercent =
                total > 0
                    ? (
                        double
                    )used
                    / total
                    * 100.0
                    : 0.0;

            StorageWidgetUsageBar.Value =
                Math.Clamp(
                    usagePercent,
                    0,
                    100);

            StorageWidgetUsageText.Text =
                $"{FormatStorageSize(used)} · {usagePercent:0.#} %";

            StorageWidgetFreeText.Text =
                FormatStorageSize(
                    free);

            StorageWidgetVolumeText.Text =
                string.IsNullOrWhiteSpace(
                    drive.VolumeLabel)
                    ? drive.Name
                    : drive.VolumeLabel;
        }
        catch (Exception exception)
        {
            UiLog.Error(
                "Unable to refresh storage widget.",
                exception);

            SetStorageWidgetUnavailable(
                "Indisponible");
        }
    }

    private void SetStorageWidgetUnavailable(
        string status)
    {
        StorageWidgetUsageBar.Value =
            0;

        StorageWidgetUsageText.Text =
            "--";

        StorageWidgetFreeText.Text =
            "--";

        StorageWidgetVolumeText.Text =
            status;
    }

    private static string FormatStorageSize(
        long bytes)
    {
        const double gigabyte =
            1024.0
            * 1024.0
            * 1024.0;

        const double terabyte =
            gigabyte
            * 1024.0;

        return bytes >= terabyte
            ? $"{bytes / terabyte:0.00} To"
            : $"{bytes / gigabyte:0.0} Go";
    }

    private void UpdateClock()
    {
        var now =
            DateTime.Now;

        ClockText.Text =
            now.ToString(
                "HH:mm");

        DateText.Text =
            now.ToString(
                "dd/MM/yyyy");
    }
}
