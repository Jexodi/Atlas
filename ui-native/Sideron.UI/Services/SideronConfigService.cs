using Sideron.UI.Models;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Reflection;

namespace Sideron.UI.Services;

public sealed class SideronConfigService
{
    private const string DefaultStorageRoot =
        @"C:\SIDERON";

    public SideronConfig Load()
    {
        var path =
            EnsureRuntimeConfig();

        if (path is null)
        {
            return new SideronConfig(
                DefaultStorageRoot,
                null,
                0,
                false);
        }

        try
        {
            using var stream =
                File.OpenRead(
                    path);

            using var document =
                JsonDocument.Parse(
                    stream);

            var root =
                document.RootElement;

            var storageRoot =
                ReadString(
                    root,
                    "storage",
                    "root")
                ?? DefaultStorageRoot;

            var screenId =
                ReadString(
                    root,
                    "ui",
                    "screen_id");

            var screenIndex =
                ReadInt(
                    root,
                    "ui",
                    "screen_index")
                ?? 0;

            var startWithWindows =
                ReadBool(
                    root,
                    "ui",
                    "start_with_windows")
                ?? false;

            var widgetCoreVisible =
                ReadBool(
                    root,
                    "ui",
                    "widgets",
                    "core_visible")
                ?? true;

            var widgetSystemVisible =
                ReadBool(
                    root,
                    "ui",
                    "widgets",
                    "system_visible")
                ?? true;

            var widgetVoiceVisible =
                ReadBool(
                    root,
                    "ui",
                    "widgets",
                    "voice_visible")
                ?? true;

            var widgetStorageVisible =
                ReadBool(
                    root,
                    "ui",
                    "widgets",
                    "storage_visible")
                ?? true;

            var widgetNetworkVisible =
                ReadBool(
                    root,
                    "ui",
                    "widgets",
                    "network_visible")
                ?? true;

            var widgetsAlignment =
                ReadString(
                    root,
                    "ui",
                    "widgets",
                    "alignment")
                ?? "right";

            var widgetCoreX =
                ReadInt(
                    root,
                    "ui",
                    "widgets",
                    "core_x")
                ?? -1;

            var widgetCoreY =
                ReadInt(
                    root,
                    "ui",
                    "widgets",
                    "core_y")
                ?? -1;

            var widgetSystemX =
                ReadInt(
                    root,
                    "ui",
                    "widgets",
                    "system_x")
                ?? -1;

            var widgetSystemY =
                ReadInt(
                    root,
                    "ui",
                    "widgets",
                    "system_y")
                ?? -1;

            var widgetVoiceX =
                ReadInt(
                    root,
                    "ui",
                    "widgets",
                    "voice_x")
                ?? -1;

            var widgetVoiceY =
                ReadInt(
                    root,
                    "ui",
                    "widgets",
                    "voice_y")
                ?? -1;

            var widgetStorageX =
                ReadInt(
                    root,
                    "ui",
                    "widgets",
                    "storage_x")
                ?? -1;

            var widgetStorageY =
                ReadInt(
                    root,
                    "ui",
                    "widgets",
                    "storage_y")
                ?? -1;

            var widgetNetworkX =
                ReadInt(
                    root,
                    "ui",
                    "widgets",
                    "network_x")
                ?? -1;

            var widgetNetworkY =
                ReadInt(
                    root,
                    "ui",
                    "widgets",
                    "network_y")
                ?? -1;

            var widgetsLocked =
                ReadBool(
                    root,
                    "ui",
                    "widgets",
                    "locked")
                ?? true;

            var filesWindowX = ReadInt(root, "ui", "windows", "files_x") ?? -1;
            var filesWindowY = ReadInt(root, "ui", "windows", "files_y") ?? -1;
            var filesWindowWidth = ReadInt(root, "ui", "windows", "files_width") ?? -1;
            var filesWindowHeight = ReadInt(root, "ui", "windows", "files_height") ?? -1;
            var filesWindowMaximized = ReadBool(root, "ui", "windows", "files_maximized") ?? false;
            var filesWindowState = ReadString(root, "ui", "windows", "files_state") ?? "closed";

            var settingsWindowX = ReadInt(root, "ui", "windows", "settings_x") ?? -1;
            var settingsWindowY = ReadInt(root, "ui", "windows", "settings_y") ?? -1;
            var settingsWindowWidth = ReadInt(root, "ui", "windows", "settings_width") ?? -1;
            var settingsWindowHeight = ReadInt(root, "ui", "windows", "settings_height") ?? -1;
            var settingsWindowMaximized = ReadBool(root, "ui", "windows", "settings_maximized") ?? false;
            var settingsWindowState = ReadString(root, "ui", "windows", "settings_state") ?? "closed";

            var widgetsWindowX = ReadInt(root, "ui", "windows", "widgets_x") ?? -1;
            var widgetsWindowY = ReadInt(root, "ui", "windows", "widgets_y") ?? -1;
            var widgetsWindowWidth = ReadInt(root, "ui", "windows", "widgets_width") ?? -1;
            var widgetsWindowHeight = ReadInt(root, "ui", "windows", "widgets_height") ?? -1;
            var widgetsWindowMaximized = ReadBool(root, "ui", "windows", "widgets_maximized") ?? false;
            var widgetsWindowState = ReadString(root, "ui", "windows", "widgets_state") ?? "closed";

            var secondaryExplorerWindows =
                ReadSecondaryExplorerLayouts(
                    root);

            var primaryExplorerTabs =
                ReadStringArray(
                    root,
                    "ui",
                    "windows",
                    "primary_explorer_tabs");

            var primaryExplorerActiveTabIndex =
                ReadInt(
                    root,
                    "ui",
                    "windows",
                    "primary_explorer_active_tab")
                ?? 0;

            return new SideronConfig(
                storageRoot,
                screenId,
                screenIndex,
                startWithWindows)
            {
                WidgetCoreVisible =
                    widgetCoreVisible,

                WidgetSystemVisible =
                    widgetSystemVisible,

                WidgetVoiceVisible =
                    widgetVoiceVisible,

                WidgetStorageVisible =
                    widgetStorageVisible,

                WidgetNetworkVisible =
                    widgetNetworkVisible,

                WidgetsAlignment =
                    widgetsAlignment,

                WidgetCoreX =
                    widgetCoreX,

                WidgetCoreY =
                    widgetCoreY,

                WidgetSystemX =
                    widgetSystemX,

                WidgetSystemY =
                    widgetSystemY,

                WidgetVoiceX =
                    widgetVoiceX,

                WidgetVoiceY =
                    widgetVoiceY,

                WidgetStorageX =
                    widgetStorageX,

                WidgetStorageY =
                    widgetStorageY,

                WidgetNetworkX =
                    widgetNetworkX,

                WidgetNetworkY =
                    widgetNetworkY,

                WidgetsLocked = widgetsLocked,

                FilesWindowX = filesWindowX,
                FilesWindowY = filesWindowY,
                FilesWindowWidth = filesWindowWidth,
                FilesWindowHeight = filesWindowHeight,
                FilesWindowMaximized = filesWindowMaximized,
                FilesWindowState = filesWindowState,

                SettingsWindowX = settingsWindowX,
                SettingsWindowY = settingsWindowY,
                SettingsWindowWidth = settingsWindowWidth,
                SettingsWindowHeight = settingsWindowHeight,
                SettingsWindowMaximized = settingsWindowMaximized,
                SettingsWindowState = settingsWindowState,

                WidgetsWindowX = widgetsWindowX,
                WidgetsWindowY = widgetsWindowY,
                WidgetsWindowWidth = widgetsWindowWidth,
                WidgetsWindowHeight = widgetsWindowHeight,
                WidgetsWindowMaximized = widgetsWindowMaximized,
                WidgetsWindowState = widgetsWindowState,

                SecondaryExplorerWindows =
                    secondaryExplorerWindows,

                PrimaryExplorerTabs =
                    primaryExplorerTabs,

                PrimaryExplorerActiveTabIndex =
                    primaryExplorerActiveTabIndex,
            };
        }
        catch (Exception exception)
        {
            UiLog.Error(
                "Sideron configuration load failed.",
                exception);

            return new SideronConfig(
                DefaultStorageRoot,
                null,
                0,
                false);
        }
    }

    public SideronUpdateConfiguration LoadUpdateConfiguration()
    {
        var path =
            EnsureRuntimeConfig();

        if (path is null)
        {
            return SideronUpdateConfiguration.Default;
        }

        try
        {
            using var stream =
                File.OpenRead(
                    path);

            using var document =
                JsonDocument.Parse(
                    stream);

            var root =
                document.RootElement;

            var version =
                GetRunningSideronVersion();

            var enabled =
                ReadBool(
                    root,
                    "updates",
                    "enabled")
                ?? true;

            var runningChannel = GetReleaseChannel(version);
            var configuredChannel =
                ReadString(root, "updates", "channel")
                ?.Trim()
                .ToLowerInvariant();
            var channel = runningChannel == "dev"
                ? "dev"
                : configuredChannel is "rc" or "release"
                    ? configuredChannel
                    : runningChannel;

            var checkOnStartup =
                ReadBool(
                    root,
                    "updates",
                    "check_on_startup")
                ?? false;

            var manifestUrl =
                ReadString(
                    root,
                    "updates",
                    "manifest_url")
                ?? string.Empty;

            if (string.IsNullOrWhiteSpace(
                    manifestUrl))
            {
                manifestUrl =
                    GetDefaultUpdateManifestUrl(
                        channel);
            }

            return new SideronUpdateConfiguration(
                version,
                enabled,
                channel,
                checkOnStartup,
                manifestUrl);
        }
        catch (Exception exception)
        {
            UiLog.Error(
                "Sideron update configuration load failed.",
                exception);

            return SideronUpdateConfiguration.Default;
        }
    }

    public SideronUpdateConfiguration SaveUpdateChannel(
        string requestedChannel)
    {
        var path = GetRuntimeConfigPath();
        JsonObject root;

        try
        {
            root = File.Exists(path)
                ? JsonNode.Parse(File.ReadAllText(path)) as JsonObject
                    ?? new JsonObject()
                : new JsonObject();
        }
        catch
        {
            root = new JsonObject();
        }

        var runningChannel = GetReleaseChannel(GetRunningSideronVersion());
        var normalized = requestedChannel.Trim().ToLowerInvariant();
        var channel = runningChannel == "dev"
            ? "dev"
            : normalized is "rc" or "release"
                ? normalized
                : "release";
        var updates = root["updates"] as JsonObject ?? new JsonObject();
        root["updates"] = updates;
        updates["channel"] = channel;
        updates["manifest_url"] = GetDefaultUpdateManifestUrl(channel);
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        File.WriteAllText(
            path,
            root.ToJsonString(new JsonSerializerOptions { WriteIndented = true }));

        return LoadUpdateConfiguration();
    }

    private static string GetRunningSideronVersion()
    {
        try
        {
            var assembly =
                typeof(SideronConfigService)
                    .Assembly;

            var informationalVersion =
                assembly
                    .GetCustomAttribute<AssemblyInformationalVersionAttribute>()
                    ?.InformationalVersion;

            if (!string.IsNullOrWhiteSpace(
                    informationalVersion))
            {
                var cleanVersion =
                    informationalVersion
                        .Split(
                            '+',
                            2)[0]
                        .Trim();

                if (!string.IsNullOrWhiteSpace(
                        cleanVersion))
                {
                    return cleanVersion;
                }
            }

            var assemblyVersion =
                assembly
                    .GetName()
                    .Version;

            if (assemblyVersion is not null)
            {
                return
                    $"{assemblyVersion.Major}."
                    + $"{assemblyVersion.Minor}."
                    + $"{assemblyVersion.Build}";
            }
        }
        catch (Exception exception)
        {
            UiLog.Error(
                "Unable to resolve running Sideron version.",
                exception);
        }

        return "Inconnue";
    }

    private static string GetDefaultUpdateManifestUrl(
        string channel)
    {
        var manifestName =
            channel switch
            {
                "dev" =>
                    "dev.json",

                "rc" =>
                    "rc.json",

                _ =>
                    "release.json",
            };

        return
            "https://raw.githubusercontent.com/"
            + "Jexodi/SIDERON/main/updates/manifests/"
            + manifestName;
    }

    private static string GetReleaseChannel(
        string version)
    {
        if (
            version.Contains(
                "-dev",
                StringComparison.OrdinalIgnoreCase)
        )
        {
            return "dev";
        }

        if (
            version.Contains(
                "-rc.",
                StringComparison.OrdinalIgnoreCase)
        )
        {
            return "rc";
        }

        return "release";
    }

    public void Save(
        SideronConfig config)
    {
        var path =
            GetRuntimeConfigPath();

        JsonObject root;

        try
        {
            if (File.Exists(
                    path))
            {
                root =
                    JsonNode.Parse(
                        File.ReadAllText(
                            path))
                    as JsonObject
                    ?? new JsonObject();
            }
            else
            {
                root =
                    new JsonObject();
            }
        }
        catch
        {
            root =
                new JsonObject();
        }

        var ui =
            root[
                "ui"
            ] as JsonObject
            ?? new JsonObject();

        var storage =
            root[
                "storage"
            ] as JsonObject
            ?? new JsonObject();

        var widgets =
            ui[
                "widgets"
            ] as JsonObject
            ?? new JsonObject();

        var windows =
            ui[
                "windows"
            ] as JsonObject
            ?? new JsonObject();

        root[
            "ui"
        ] = ui;

        root[
            "storage"
        ] = storage;

        ui[
            "widgets"
        ] = widgets;

        ui[
            "windows"
        ] = windows;

        ui[
            "screen_id"
        ] = config.ScreenId;

        ui[
            "screen_index"
        ] = config.ScreenIndex;

        ui[
            "start_with_windows"
        ] = config.StartWithWindows;

        widgets[
            "core_visible"
        ] = config.WidgetCoreVisible;

        widgets[
            "system_visible"
        ] = config.WidgetSystemVisible;

        widgets[
            "voice_visible"
        ] = config.WidgetVoiceVisible;

        widgets[
            "storage_visible"
        ] = config.WidgetStorageVisible;

        widgets[
            "network_visible"
        ] = config.WidgetNetworkVisible;

        widgets[
            "alignment"
        ] = config.WidgetsAlignment;

        widgets[
            "core_x"
        ] = config.WidgetCoreX;

        widgets[
            "core_y"
        ] = config.WidgetCoreY;

        widgets[
            "system_x"
        ] = config.WidgetSystemX;

        widgets[
            "system_y"
        ] = config.WidgetSystemY;

        widgets[
            "voice_x"
        ] = config.WidgetVoiceX;

        widgets[
            "voice_y"
        ] = config.WidgetVoiceY;

        widgets[
            "storage_x"
        ] = config.WidgetStorageX;

        widgets[
            "storage_y"
        ] = config.WidgetStorageY;

        widgets[
            "network_x"
        ] = config.WidgetNetworkX;

        widgets[
            "network_y"
        ] = config.WidgetNetworkY;

        widgets[
            "locked"
        ] = config.WidgetsLocked;

        windows["files_x"] = config.FilesWindowX;
        windows["files_y"] = config.FilesWindowY;
        windows["files_width"] = config.FilesWindowWidth;
        windows["files_height"] = config.FilesWindowHeight;
        windows["files_maximized"] = config.FilesWindowMaximized;
        windows["files_state"] = config.FilesWindowState;

        windows["settings_x"] = config.SettingsWindowX;
        windows["settings_y"] = config.SettingsWindowY;
        windows["settings_width"] = config.SettingsWindowWidth;
        windows["settings_height"] = config.SettingsWindowHeight;
        windows["settings_maximized"] = config.SettingsWindowMaximized;
        windows["settings_state"] = config.SettingsWindowState;

        windows["widgets_x"] = config.WidgetsWindowX;
        windows["widgets_y"] = config.WidgetsWindowY;
        windows["widgets_width"] = config.WidgetsWindowWidth;
        windows["widgets_height"] = config.WidgetsWindowHeight;
        windows["widgets_maximized"] = config.WidgetsWindowMaximized;
        windows["widgets_state"] = config.WidgetsWindowState;

        var secondaryExplorers =
            new JsonArray();

        foreach (
            var layout
            in config.SecondaryExplorerWindows)
        {
            secondaryExplorers.Add(
                new JsonObject
                {
                    ["directory"] = layout.Directory,
                    ["x"] = layout.X,
                    ["y"] = layout.Y,
                    ["width"] = layout.Width,
                    ["height"] = layout.Height,
                    ["maximized"] = layout.Maximized,
                    ["minimized"] = layout.Minimized,
                    ["active_tab"] = layout.ActiveTabIndex,
                    ["tabs"] =
                        new JsonArray(
                            layout.Tabs
                                .Select(
                                    directory =>
                                        (JsonNode?)directory)
                                .ToArray()),
                });
        }

        windows[
            "secondary_explorers"
        ] = secondaryExplorers;

        windows[
            "primary_explorer_tabs"
        ] =
            new JsonArray(
                config.PrimaryExplorerTabs
                    .Select(
                        directory =>
                            (JsonNode?)directory)
                    .ToArray());

        windows[
            "primary_explorer_active_tab"
        ] = config.PrimaryExplorerActiveTabIndex;

        storage[
            "root"
        ] = config.StorageRoot;

        var parent =
            Path.GetDirectoryName(
                path);

        if (!string.IsNullOrWhiteSpace(
                parent))
        {
            Directory.CreateDirectory(
                parent);
        }

        var options =
            new JsonSerializerOptions
            {
                WriteIndented =
                    true,
            };

        File.WriteAllText(
            path,
            root.ToJsonString(
                options)
            + Environment.NewLine);

        UiLog.Info(
            $"Sideron configuration saved: {path}");
    }

    private static IReadOnlyList<string>
        ReadStringArray(
            JsonElement root,
            string section,
            string subsection,
            string key)
    {
        var result =
            new List<string>();

        if (
            !root.TryGetProperty(
                section,
                out var sectionNode)
            || sectionNode.ValueKind
                != JsonValueKind.Object
            || !sectionNode.TryGetProperty(
                subsection,
                out var subsectionNode)
            || subsectionNode.ValueKind
                != JsonValueKind.Object
            || !subsectionNode.TryGetProperty(
                key,
                out var arrayNode)
            || arrayNode.ValueKind
                != JsonValueKind.Array
        )
        {
            return result;
        }

        foreach (
            var item
            in arrayNode.EnumerateArray())
        {
            if (item.ValueKind != JsonValueKind.String)
            {
                continue;
            }

            var value =
                item.GetString();

            if (!string.IsNullOrWhiteSpace(value))
            {
                result.Add(value);
            }
        }

        return result;
    }

    private static IReadOnlyList<SecondaryExplorerLayout>
        ReadSecondaryExplorerLayouts(
            JsonElement root)
    {
        var result =
            new List<SecondaryExplorerLayout>();

        if (
            !root.TryGetProperty(
                "ui",
                out var uiNode)
            || uiNode.ValueKind
                != JsonValueKind.Object
            || !uiNode.TryGetProperty(
                "windows",
                out var windowsNode)
            || windowsNode.ValueKind
                != JsonValueKind.Object
            || !windowsNode.TryGetProperty(
                "secondary_explorers",
                out var explorersNode)
            || explorersNode.ValueKind
                != JsonValueKind.Array
        )
        {
            return result;
        }

        foreach (
            var item
            in explorersNode.EnumerateArray())
        {
            if (
                item.ValueKind
                    != JsonValueKind.Object
            )
            {
                continue;
            }

            var directory =
                item.TryGetProperty(
                    "directory",
                    out var directoryNode)
                && directoryNode.ValueKind
                    == JsonValueKind.String
                    ? directoryNode.GetString()
                    : null;

            if (string.IsNullOrWhiteSpace(
                    directory))
            {
                continue;
            }

            var tabs =
                new List<string>();

            if (
                item.TryGetProperty(
                    "tabs",
                    out var tabsNode)
                && tabsNode.ValueKind
                    == JsonValueKind.Array
            )
            {
                foreach (
                    var tabNode
                    in tabsNode.EnumerateArray())
                {
                    if (
                        tabNode.ValueKind
                            == JsonValueKind.String
                    )
                    {
                        var tabDirectory =
                            tabNode.GetString();

                        if (!string.IsNullOrWhiteSpace(
                                tabDirectory))
                        {
                            tabs.Add(
                                tabDirectory);
                        }
                    }
                }
            }

            if (tabs.Count == 0)
            {
                tabs.Add(
                    directory);
            }

            var activeTabIndex =
                Math.Clamp(
                    ReadInt(
                        item,
                        "active_tab")
                    ?? 0,
                    0,
                    tabs.Count - 1);

            result.Add(
                new SecondaryExplorerLayout(
                    directory,
                    ReadInt(item, "x") ?? 20,
                    ReadInt(item, "y") ?? 20,
                    ReadInt(item, "width") ?? 1120,
                    ReadInt(item, "height") ?? 680,
                    ReadBool(item, "maximized") ?? false,
                    ReadBool(item, "minimized") ?? false,
                    tabs,
                    activeTabIndex));
        }

        return result;
    }

    private static int? ReadInt(
        JsonElement node,
        string key)
    {
        if (
            !node.TryGetProperty(
                key,
                out var value)
            || value.ValueKind
                != JsonValueKind.Number
        )
        {
            return null;
        }

        return value.TryGetInt32(
            out var result)
            ? result
            : null;
    }

    private static bool? ReadBool(
        JsonElement node,
        string key)
    {
        if (
            !node.TryGetProperty(
                key,
                out var value)
        )
        {
            return null;
        }

        return value.ValueKind switch
        {
            JsonValueKind.True => true,
            JsonValueKind.False => false,
            _ => null,
        };
    }

    public static string GetRuntimeConfigPath()
    {
        var localAppData =
            Environment.GetFolderPath(
                Environment.SpecialFolder.LocalApplicationData);

        if (string.IsNullOrWhiteSpace(
                localAppData))
        {
            localAppData =
                Path.GetTempPath();
        }

        return Path.Combine(
            localAppData,
            "SIDERON",
            "config",
            "sideron.json");
    }

    private static string? EnsureRuntimeConfig()
    {
        var runtimePath =
            GetRuntimeConfigPath();

        if (File.Exists(
                runtimePath))
        {
            return runtimePath;
        }

        var legacyRuntimePath =
            Path.Combine(
                Environment.GetFolderPath(
                    Environment.SpecialFolder.LocalApplicationData),
                "Atlas",
                "config",
                "atlas.json");

        if (File.Exists(legacyRuntimePath))
        {
            var runtimeDirectory = Path.GetDirectoryName(runtimePath);
            if (!string.IsNullOrWhiteSpace(runtimeDirectory))
            {
                Directory.CreateDirectory(runtimeDirectory);
            }

            File.Copy(legacyRuntimePath, runtimePath, overwrite: false);
            UiLog.Info($"Legacy Atlas configuration migrated to SIDERON: {runtimePath}");
            return runtimePath;
        }

        var installedPath =
            FindInstalledSideronConfig();

        if (installedPath is null)
        {
            return null;
        }

        try
        {
            var parent =
                Path.GetDirectoryName(
                    runtimePath);

            if (!string.IsNullOrWhiteSpace(
                    parent))
            {
                Directory.CreateDirectory(
                    parent);
            }

            File.Copy(
                installedPath,
                runtimePath,
                overwrite: false);

            UiLog.Info(
                $"Sideron runtime configuration initialized: {runtimePath}");

            return runtimePath;
        }
        catch (IOException)
        {
            if (File.Exists(
                    runtimePath))
            {
                return runtimePath;
            }

            throw;
        }
    }

    private static string? FindInstalledSideronConfig()
    {
        var explicitRoot =
            Environment.GetEnvironmentVariable(
                "SIDERON_ROOT")
            ?? Environment.GetEnvironmentVariable(
                "ATLAS_ROOT");

        if (!string.IsNullOrWhiteSpace(
                explicitRoot))
        {
            var explicitPath =
                Path.Combine(
                    explicitRoot,
                    "config",
                    "sideron.json");

            if (File.Exists(
                    explicitPath))
            {
                return explicitPath;
            }
        }

        foreach (
            var start
            in new[]
            {
                AppContext.BaseDirectory,
                Environment.CurrentDirectory,
                @"C:\Program Files\SIDERON",
                @"C:\Program Files\Atlas",
            })
        {
            var directory =
                new DirectoryInfo(
                    start);

            for (
                var depth = 0;
                depth < 10
                && directory is not null;
                depth++,
                directory =
                    directory.Parent)
            {
                var candidate =
                    Path.Combine(
                        directory.FullName,
                        "config",
                        "sideron.json");

                if (File.Exists(
                        candidate))
                {
                    return candidate;
                }
            }
        }

        return null;
    }

    private static string? ReadString(
        JsonElement root,
        string section,
        string key)
    {
        if (
            !root.TryGetProperty(
                section,
                out var sectionNode)
            || !sectionNode.TryGetProperty(
                key,
                out var value)
            || value.ValueKind
                != JsonValueKind.String
        )
        {
            return null;
        }

        return value.GetString();
    }

    private static string? ReadString(
        JsonElement root,
        string section,
        string subsection,
        string key)
    {
        if (
            !root.TryGetProperty(
                section,
                out var sectionNode)
            || sectionNode.ValueKind
                != JsonValueKind.Object
            || !sectionNode.TryGetProperty(
                subsection,
                out var subsectionNode)
            || subsectionNode.ValueKind
                != JsonValueKind.Object
            || !subsectionNode.TryGetProperty(
                key,
                out var value)
            || value.ValueKind
                != JsonValueKind.String
        )
        {
            return null;
        }

        return value.GetString();
    }

    private static int? ReadInt(
        JsonElement root,
        string section,
        string key)
    {
        if (
            !root.TryGetProperty(
                section,
                out var sectionNode)
            || !sectionNode.TryGetProperty(
                key,
                out var value)
            || value.ValueKind
                != JsonValueKind.Number
        )
        {
            return null;
        }

        return value.TryGetInt32(
            out var result)
            ? result
            : null;
    }

    private static int? ReadInt(
        JsonElement root,
        string section,
        string subsection,
        string key)
    {
        if (
            !root.TryGetProperty(
                section,
                out var sectionNode)
            || sectionNode.ValueKind
                != JsonValueKind.Object
            || !sectionNode.TryGetProperty(
                subsection,
                out var subsectionNode)
            || subsectionNode.ValueKind
                != JsonValueKind.Object
            || !subsectionNode.TryGetProperty(
                key,
                out var value)
            || value.ValueKind
                != JsonValueKind.Number
        )
        {
            return null;
        }

        return value.TryGetInt32(
            out var result)
            ? result
            : null;
    }

    private static bool? ReadBool(
        JsonElement root,
        string section,
        string key)
    {
        if (
            !root.TryGetProperty(
                section,
                out var sectionNode)
            || !sectionNode.TryGetProperty(
                key,
                out var value)
        )
        {
            return null;
        }

        if (
            value.ValueKind
            == JsonValueKind.True
        )
        {
            return true;
        }

        if (
            value.ValueKind
            == JsonValueKind.False
        )
        {
            return false;
        }

        return null;
    }

    private static bool? ReadBool(
        JsonElement root,
        string section,
        string subsection,
        string key)
    {
        if (
            !root.TryGetProperty(
                section,
                out var sectionNode)
            || sectionNode.ValueKind
                != JsonValueKind.Object
            || !sectionNode.TryGetProperty(
                subsection,
                out var subsectionNode)
            || subsectionNode.ValueKind
                != JsonValueKind.Object
            || !subsectionNode.TryGetProperty(
                key,
                out var value)
        )
        {
            return null;
        }

        if (
            value.ValueKind
            == JsonValueKind.True
        )
        {
            return true;
        }

        if (
            value.ValueKind
            == JsonValueKind.False
        )
        {
            return false;
        }

        return null;
    }
}

public sealed record SideronUpdateConfiguration(
    string Version,
    bool Enabled,
    string Channel,
    bool CheckOnStartup,
    string ManifestUrl)
{
    public static SideronUpdateConfiguration Default { get; } =
        new(
            "Inconnue",
            true,
            "release",
            false,
            string.Empty);
}
