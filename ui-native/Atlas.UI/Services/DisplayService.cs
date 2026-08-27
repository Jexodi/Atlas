using Atlas.UI.Models;
using System.Runtime.InteropServices;
using Windows.Graphics;

namespace Atlas.UI.Services;

public sealed class DisplayService
{
    public DisplayDescriptor? ResolveDisplay(
        string? configuredId,
        int legacyIndex)
    {
        var displays =
            EnumerateDisplays();

        if (displays.Count == 0)
        {
            return null;
        }

        var requestedDevice =
            ExtractDeviceName(
                configuredId);

        if (!string.IsNullOrWhiteSpace(
                requestedDevice))
        {
            var exact =
                displays.FirstOrDefault(
                    display =>
                        string.Equals(
                            display.DeviceName,
                            requestedDevice,
                            StringComparison
                                .OrdinalIgnoreCase));

            if (exact is not null)
            {
                return exact;
            }

            return displays.FirstOrDefault(
                       display =>
                           display.IsPrimary)
                   ?? displays[0];
        }

        if (
            legacyIndex >= 0
            && legacyIndex
                < displays.Count
        )
        {
            return displays[
                legacyIndex];
        }

        return displays.FirstOrDefault(
                   display =>
                       display.IsPrimary)
               ?? displays[0];
    }

    public IReadOnlyList<DisplayDescriptor>
        EnumerateDisplays()
    {
        var displays =
            new List<DisplayDescriptor>();

        EnumDisplayMonitors(
            IntPtr.Zero,
            IntPtr.Zero,
            (
                IntPtr monitor,
                IntPtr hdc,
                ref RECT rect,
                IntPtr data) =>
            {
                var info =
                    new MONITORINFOEX();

                info.cbSize =
                    Marshal.SizeOf<
                        MONITORINFOEX>();

                if (!GetMonitorInfo(
                        monitor,
                        ref info))
                {
                    return true;
                }

                var bounds =
                    new RectInt32(
                        info.rcMonitor.Left,
                        info.rcMonitor.Top,
                        info.rcMonitor.Right
                            - info.rcMonitor.Left,
                        info.rcMonitor.Bottom
                            - info.rcMonitor.Top);

                var workArea =
                    new RectInt32(
                        info.rcWork.Left,
                        info.rcWork.Top,
                        info.rcWork.Right
                            - info.rcWork.Left,
                        info.rcWork.Bottom
                            - info.rcWork.Top);

                var primary =
                    (
                        info.dwFlags
                        & MONITORINFOF_PRIMARY
                    ) != 0;

                var friendlyName =
                    GetFriendlyMonitorName(
                        info.szDevice);

                displays.Add(
                    new DisplayDescriptor(
                        info.szDevice,
                        friendlyName,
                        bounds,
                        workArea,
                        primary));

                return true;
            },
            IntPtr.Zero);

        displays.Sort(
            (left, right) =>
            {
                // On conserve le tri actuel utilisé par Atlas.
                // Le numéro affiché dans les Paramètres est extrait
                // de \\.\DISPLAYx, donc il reste identique à Windows.
                if (
                    left.IsPrimary
                    != right.IsPrimary
                )
                {
                    return left.IsPrimary
                        ? -1
                        : 1;
                }

                var byX =
                    left.Bounds.X.CompareTo(
                        right.Bounds.X);

                if (byX != 0)
                {
                    return byX;
                }

                return left.Bounds.Y.CompareTo(
                    right.Bounds.Y);
            });

        return displays;
    }

    private static string GetFriendlyMonitorName(
        string displayDeviceName)
    {
        var monitor =
            CreateDisplayDevice();

        if (
            EnumDisplayDevices(
                displayDeviceName,
                0,
                ref monitor,
                EDD_GET_DEVICE_INTERFACE_NAME)
        )
        {
            var value =
                NormalizeFriendlyName(
                    monitor.DeviceString);

            if (!string.IsNullOrWhiteSpace(
                    value))
            {
                return value;
            }
        }

        // Certains pilotes exposent le moniteur via plusieurs index.
        // On parcourt quelques entrées plutôt que de revenir
        // immédiatement au nom technique.
        for (
            uint index = 1;
            index < 8;
            index++
        )
        {
            monitor =
                CreateDisplayDevice();

            if (
                !EnumDisplayDevices(
                    displayDeviceName,
                    index,
                    ref monitor,
                    EDD_GET_DEVICE_INTERFACE_NAME)
            )
            {
                break;
            }

            var value =
                NormalizeFriendlyName(
                    monitor.DeviceString);

            if (!string.IsNullOrWhiteSpace(
                    value))
            {
                return value;
            }
        }

        return "Moniteur";
    }

    private static DISPLAY_DEVICE
        CreateDisplayDevice()
    {
        var device =
            new DISPLAY_DEVICE();

        device.cb =
            Marshal.SizeOf<
                DISPLAY_DEVICE>();

        return device;
    }

    private static string? NormalizeFriendlyName(
        string? value)
    {
        if (string.IsNullOrWhiteSpace(
                value))
        {
            return null;
        }

        var name =
            value.Trim();

        // Évite d'afficher les libellés génériques Windows lorsque
        // le pilote ne fournit pas réellement le modèle du moniteur.
        if (
            string.Equals(
                name,
                "Generic PnP Monitor",
                StringComparison.OrdinalIgnoreCase)
            || string.Equals(
                name,
                "Moniteur Plug-and-Play générique",
                StringComparison.OrdinalIgnoreCase)
            || string.Equals(
                name,
                "Generic Non-PnP Monitor",
                StringComparison.OrdinalIgnoreCase)
        )
        {
            return null;
        }

        return name;
    }

    private static string? ExtractDeviceName(
        string? configuredId)
    {
        if (string.IsNullOrWhiteSpace(
                configuredId))
        {
            return null;
        }

        var first =
            configuredId
                .Split(
                    '|',
                    StringSplitOptions
                        .RemoveEmptyEntries)
                .FirstOrDefault();

        return string.IsNullOrWhiteSpace(
                first)
            ? null
            : first.Trim();
    }

    private const uint
        MONITORINFOF_PRIMARY =
            0x00000001;

    private const uint
        EDD_GET_DEVICE_INTERFACE_NAME =
            0x00000001;

    private delegate bool
        MonitorEnumProc(
            IntPtr hMonitor,
            IntPtr hdcMonitor,
            ref RECT lprcMonitor,
            IntPtr dwData);

    [DllImport("user32.dll")]
    [return: MarshalAs(
        UnmanagedType.Bool)]
    private static extern bool
        EnumDisplayMonitors(
            IntPtr hdc,
            IntPtr lprcClip,
            MonitorEnumProc callback,
            IntPtr dwData);

    [DllImport(
        "user32.dll",
        CharSet = CharSet.Unicode)]
    [return: MarshalAs(
        UnmanagedType.Bool)]
    private static extern bool
        GetMonitorInfo(
            IntPtr hMonitor,
            ref MONITORINFOEX info);

    [DllImport(
        "user32.dll",
        CharSet = CharSet.Unicode)]
    [return: MarshalAs(
        UnmanagedType.Bool)]
    private static extern bool
        EnumDisplayDevices(
            string? lpDevice,
            uint iDevNum,
            ref DISPLAY_DEVICE lpDisplayDevice,
            uint dwFlags);

    [StructLayout(
        LayoutKind.Sequential)]
    private struct RECT
    {
        public int Left;
        public int Top;
        public int Right;
        public int Bottom;
    }

    [StructLayout(
        LayoutKind.Sequential,
        CharSet = CharSet.Unicode)]
    private struct MONITORINFOEX
    {
        public int cbSize;
        public RECT rcMonitor;
        public RECT rcWork;
        public uint dwFlags;

        [MarshalAs(
            UnmanagedType.ByValTStr,
            SizeConst = 32)]
        public string szDevice;
    }

    [StructLayout(
        LayoutKind.Sequential,
        CharSet = CharSet.Unicode)]
    private struct DISPLAY_DEVICE
    {
        public int cb;

        [MarshalAs(
            UnmanagedType.ByValTStr,
            SizeConst = 32)]
        public string DeviceName;

        [MarshalAs(
            UnmanagedType.ByValTStr,
            SizeConst = 128)]
        public string DeviceString;

        public uint StateFlags;

        [MarshalAs(
            UnmanagedType.ByValTStr,
            SizeConst = 128)]
        public string DeviceID;

        [MarshalAs(
            UnmanagedType.ByValTStr,
            SizeConst = 128)]
        public string DeviceKey;
    }
}
