using System.Runtime.InteropServices;
using System.Text;
using Windows.Graphics;

namespace Atlas.UI.Services;

public sealed class TaskbarVisibilityService
{
    private const int SW_HIDE = 0;
    private const int SW_SHOW = 5;

    private readonly HashSet<nint>
        _hiddenTaskbars =
            new();

    private RectInt32?
        _targetMonitor;

    public void HideOnMonitor(
        RectInt32 monitorBounds)
    {
        _targetMonitor =
            monitorBounds;

        Refresh();
    }

    public void Refresh()
    {
        if (_targetMonitor is null)
        {
            return;
        }

        var bounds =
            _targetMonitor.Value;

        EnumWindows(
            (
                hwnd,
                _) =>
            {
                if (!IsTaskbarWindow(
                        hwnd))
                {
                    return true;
                }

                if (!GetWindowRect(
                        hwnd,
                        out var rect))
                {
                    return true;
                }

                if (!IntersectsMonitor(
                        rect,
                        bounds))
                {
                    return true;
                }

                ShowWindow(
                    hwnd,
                    SW_HIDE);

                _hiddenTaskbars.Add(
                    hwnd);

                return true;
            },
            nint.Zero);
    }

    public void Restore()
    {
        foreach (
            var hwnd
            in _hiddenTaskbars.ToArray()
        )
        {
            if (IsWindow(
                    hwnd))
            {
                ShowWindow(
                    hwnd,
                    SW_SHOW);
            }
        }

        _hiddenTaskbars.Clear();

        _targetMonitor =
            null;
    }

    private static bool IsTaskbarWindow(
        nint hwnd)
    {
        var className =
            GetWindowClassName(
                hwnd);

        return string.Equals(
                   className,
                   "Shell_TrayWnd",
                   StringComparison.Ordinal)
               || string.Equals(
                   className,
                   "Shell_SecondaryTrayWnd",
                   StringComparison.Ordinal);
    }

    private static string GetWindowClassName(
        nint hwnd)
    {
        var builder =
            new StringBuilder(
                256);

        var length =
            GetClassName(
                hwnd,
                builder,
                builder.Capacity);

        return length <= 0
            ? string.Empty
            : builder.ToString();
    }

    private static bool IntersectsMonitor(
        RECT taskbar,
        RectInt32 monitor)
    {
        var left =
            Math.Max(
                taskbar.Left,
                monitor.X);

        var top =
            Math.Max(
                taskbar.Top,
                monitor.Y);

        var right =
            Math.Min(
                taskbar.Right,
                monitor.X
                + monitor.Width);

        var bottom =
            Math.Min(
                taskbar.Bottom,
                monitor.Y
                + monitor.Height);

        return (
            right > left
            && bottom > top
        );
    }

    private delegate bool
        EnumWindowsProc(
            nint hwnd,
            nint lParam);

    [StructLayout(
        LayoutKind.Sequential)]
    private struct RECT
    {
        public int Left;
        public int Top;
        public int Right;
        public int Bottom;
    }

    [DllImport("user32.dll")]
    [return: MarshalAs(
        UnmanagedType.Bool)]
    private static extern bool
        EnumWindows(
            EnumWindowsProc callback,
            nint lParam);

    [DllImport(
        "user32.dll",
        CharSet = CharSet.Unicode)]
    private static extern int
        GetClassName(
            nint hwnd,
            StringBuilder className,
            int maxCount);

    [DllImport("user32.dll")]
    [return: MarshalAs(
        UnmanagedType.Bool)]
    private static extern bool
        GetWindowRect(
            nint hwnd,
            out RECT rect);

    [DllImport("user32.dll")]
    [return: MarshalAs(
        UnmanagedType.Bool)]
    private static extern bool
        ShowWindow(
            nint hwnd,
            int command);

    [DllImport("user32.dll")]
    [return: MarshalAs(
        UnmanagedType.Bool)]
    private static extern bool
        IsWindow(
            nint hwnd);
}
