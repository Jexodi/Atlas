using Microsoft.UI.Xaml;
using System.Runtime.InteropServices;
using WinRT.Interop;

namespace Atlas.UI.Services;

public static class DesktopIntegrationService
{
    private const int GWL_STYLE = -16;
    private const int GWL_EXSTYLE = -20;
    private const int GWLP_HWNDPARENT = -8;

    private const long WS_CAPTION = 0x00C00000L;
    private const long WS_THICKFRAME = 0x00040000L;
    private const long WS_MINIMIZEBOX = 0x00020000L;
    private const long WS_MAXIMIZEBOX = 0x00010000L;
    private const long WS_SYSMENU = 0x00080000L;
    private const long WS_BORDER = 0x00800000L;
    private const long WS_DLGFRAME = 0x00400000L;

    private const long WS_POPUP =
        unchecked((long)0x80000000);

    private const long WS_EX_TOOLWINDOW = 0x00000080L;
    private const long WS_EX_APPWINDOW = 0x00040000L;

    private const uint SWP_NOSIZE = 0x0001;
    private const uint SWP_NOMOVE = 0x0002;
    private const uint SWP_NOACTIVATE = 0x0010;
    private const uint SWP_FRAMECHANGED = 0x0020;
    private const uint SWP_SHOWWINDOW = 0x0040;

    private const int DWMWA_WINDOW_CORNER_PREFERENCE = 33;
    private const int DWMWA_BORDER_COLOR = 34;

    private const int DWMWCP_DONOTROUND = 1;
    private const uint DWM_COLOR_NONE = 0xFFFFFFFE;

    private static readonly IntPtr HWND_TOP =
        IntPtr.Zero;

    public static bool AttachInteractiveDesktop(
        Window window)
    {
        try
        {
            var hwnd =
                WindowNative.GetWindowHandle(
                    window);

            if (hwnd == IntPtr.Zero)
            {
                UiLog.Error(
                    "DesktopIntegration: HWND is null.");

                return false;
            }

            ConfigureBorderlessWindow(
                hwnd);

            var desktopOwner =
                FindDesktopOwnerWindow();

            if (desktopOwner == IntPtr.Zero)
            {
                UiLog.Error(
                    "DesktopIntegration: SHELLDLL_DefView/desktop owner not found.");

                return false;
            }

            UiLog.Info(
                $"DesktopIntegration: desktop owner = 0x{desktopOwner.ToInt64():X}.");

            SetWindowLongPtr(
                hwnd,
                GWLP_HWNDPARENT,
                desktopOwner);

            DisableDwmFrame(
                hwnd);

            SetWindowPos(
                hwnd,
                HWND_TOP,
                0,
                0,
                0,
                0,
                SWP_NOMOVE
                | SWP_NOSIZE
                | SWP_NOACTIVATE
                | SWP_FRAMECHANGED
                | SWP_SHOWWINDOW);

            UiLog.Info(
                "DesktopIntegration: Atlas Desktop attached to the shell.");

            return true;
        }
        catch (Exception exception)
        {
            UiLog.Error(
                "DesktopIntegration failed.",
                exception);

            return false;
        }
    }

    private static void ConfigureBorderlessWindow(
        IntPtr hwnd)
    {
        var style =
            GetWindowLongPtr(
                hwnd,
                GWL_STYLE)
            .ToInt64();

        style &=
            ~(WS_CAPTION
              | WS_THICKFRAME
              | WS_MINIMIZEBOX
              | WS_MAXIMIZEBOX
              | WS_SYSMENU
              | WS_BORDER
              | WS_DLGFRAME);

        style |= WS_POPUP;

        SetWindowLongPtr(
            hwnd,
            GWL_STYLE,
            new IntPtr(style));

        var extended =
            GetWindowLongPtr(
                hwnd,
                GWL_EXSTYLE)
            .ToInt64();

        // Atlas reste une fenêtre plein écran sans bordure, mais doit être
        // présenté comme une application normale dans la barre des tâches.
        extended &=
            ~WS_EX_TOOLWINDOW;

        extended |=
            WS_EX_APPWINDOW;

        SetWindowLongPtr(
            hwnd,
            GWL_EXSTYLE,
            new IntPtr(extended));
    }

    private static void DisableDwmFrame(
        IntPtr hwnd)
    {
        try
        {
            var corner =
                DWMWCP_DONOTROUND;

            DwmSetWindowAttribute(
                hwnd,
                DWMWA_WINDOW_CORNER_PREFERENCE,
                ref corner,
                Marshal.SizeOf<int>());

            var border =
                DWM_COLOR_NONE;

            DwmSetWindowAttribute(
                hwnd,
                DWMWA_BORDER_COLOR,
                ref border,
                Marshal.SizeOf<uint>());
        }
        catch
        {
            // Cosmetic only.
        }
    }

    private static IntPtr FindDesktopOwnerWindow()
    {
        var progman =
            FindWindow(
                "Progman",
                null);

        if (progman != IntPtr.Zero)
        {
            // This undocumented shell message is the classic WorkerW
            // wallpaper technique. If Explorer ignores it, the rest of
            // the discovery still falls back safely.
            SendMessageTimeout(
                progman,
                0x052C,
                IntPtr.Zero,
                IntPtr.Zero,
                SendMessageTimeoutFlags.SMTO_NORMAL,
                1000,
                out _);

            var defView =
                FindWindowEx(
                    progman,
                    IntPtr.Zero,
                    "SHELLDLL_DefView",
                    null);

            if (defView != IntPtr.Zero)
            {
                return defView;
            }
        }

        IntPtr found =
            IntPtr.Zero;

        EnumWindows(
            (topLevel, _) =>
            {
                var defView =
                    FindWindowEx(
                        topLevel,
                        IntPtr.Zero,
                        "SHELLDLL_DefView",
                        null);

                if (defView == IntPtr.Zero)
                {
                    return true;
                }

                found =
                    defView;

                return false;
            },
            IntPtr.Zero);

        if (found != IntPtr.Zero)
        {
            return found;
        }

        // Last-resort fallback. This keeps the test window usable even
        // if Explorer's internal hierarchy changes on a future build.
        return GetShellWindow();
    }

    private static IntPtr GetWindowLongPtr(
        IntPtr hwnd,
        int index)
    {
        return IntPtr.Size == 8
            ? GetWindowLongPtr64(
                hwnd,
                index)
            : new IntPtr(
                GetWindowLong32(
                    hwnd,
                    index));
    }

    private static IntPtr SetWindowLongPtr(
        IntPtr hwnd,
        int index,
        IntPtr value)
    {
        return IntPtr.Size == 8
            ? SetWindowLongPtr64(
                hwnd,
                index,
                value)
            : new IntPtr(
                SetWindowLong32(
                    hwnd,
                    index,
                    value.ToInt32()));
    }

    private delegate bool EnumWindowsProc(
        IntPtr hwnd,
        IntPtr lParam);

    [Flags]
    private enum SendMessageTimeoutFlags : uint
    {
        SMTO_NORMAL = 0x0000,
    }

    [DllImport(
        "user32.dll",
        CharSet = CharSet.Unicode)]
    private static extern IntPtr FindWindow(
        string? className,
        string? windowName);

    [DllImport(
        "user32.dll",
        CharSet = CharSet.Unicode)]
    private static extern IntPtr FindWindowEx(
        IntPtr parent,
        IntPtr childAfter,
        string? className,
        string? windowName);

    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool EnumWindows(
        EnumWindowsProc callback,
        IntPtr lParam);

    [DllImport("user32.dll")]
    private static extern IntPtr GetShellWindow();

    [DllImport("user32.dll")]
    private static extern IntPtr SendMessageTimeout(
        IntPtr hwnd,
        uint message,
        IntPtr wParam,
        IntPtr lParam,
        SendMessageTimeoutFlags flags,
        uint timeout,
        out IntPtr result);

    [DllImport(
        "user32.dll",
        EntryPoint = "GetWindowLong")]
    private static extern int GetWindowLong32(
        IntPtr hwnd,
        int index);

    [DllImport(
        "user32.dll",
        EntryPoint = "GetWindowLongPtr")]
    private static extern IntPtr GetWindowLongPtr64(
        IntPtr hwnd,
        int index);

    [DllImport(
        "user32.dll",
        EntryPoint = "SetWindowLong")]
    private static extern int SetWindowLong32(
        IntPtr hwnd,
        int index,
        int value);

    [DllImport(
        "user32.dll",
        EntryPoint = "SetWindowLongPtr")]
    private static extern IntPtr SetWindowLongPtr64(
        IntPtr hwnd,
        int index,
        IntPtr value);

    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool SetWindowPos(
        IntPtr hwnd,
        IntPtr insertAfter,
        int x,
        int y,
        int width,
        int height,
        uint flags);

    [DllImport("dwmapi.dll")]
    private static extern int DwmSetWindowAttribute(
        IntPtr hwnd,
        int attribute,
        ref int value,
        int size);

    [DllImport("dwmapi.dll")]
    private static extern int DwmSetWindowAttribute(
        IntPtr hwnd,
        int attribute,
        ref uint value,
        int size);
}
