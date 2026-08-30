using Microsoft.UI.Xaml;
using System.Runtime.InteropServices;
using WinRT.Interop;

namespace Sideron.UI.Services;

public static class NativeWindowService
{
    private const int GWL_STYLE = -16;
    private const int GWL_EXSTYLE = -20;

    private const long WS_CAPTION = 0x00C00000L;
    private const long WS_THICKFRAME = 0x00040000L;
    private const long WS_MINIMIZEBOX = 0x00020000L;
    private const long WS_MAXIMIZEBOX = 0x00010000L;
    private const long WS_SYSMENU = 0x00080000L;
    private const long WS_BORDER = 0x00800000L;
    private const long WS_DLGFRAME = 0x00400000L;

    private const long WS_POPUP =
        unchecked(
            (long)0x80000000);

    private const long WS_EX_TOOLWINDOW = 0x00000080L;
    private const long WS_EX_APPWINDOW = 0x00040000L;

    private const uint SWP_NOSIZE = 0x0001;
    private const uint SWP_NOMOVE = 0x0002;
    private const uint SWP_NOZORDER = 0x0004;
    private const uint SWP_NOACTIVATE = 0x0010;
    private const uint SWP_FRAMECHANGED = 0x0020;

    private const int
        DWMWA_WINDOW_CORNER_PREFERENCE = 33;

    private const int
        DWMWA_BORDER_COLOR = 34;

    private const int
        DWMWCP_DONOTROUND = 1;

    private const uint
        DWM_COLOR_NONE = 0xFFFFFFFE;

    public static bool ConfigureSideronDesktop(
        Window window)
    {
        try
        {
            var hwnd =
                WindowNative.GetWindowHandle(
                    window);

            if (hwnd == IntPtr.Zero)
            {
                return false;
            }

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

            var extendedStyle =
                GetWindowLongPtr(
                    hwnd,
                    GWL_EXSTYLE)
                .ToInt64();

            extendedStyle &=
                ~WS_EX_TOOLWINDOW;

            extendedStyle |=
                WS_EX_APPWINDOW;

            SetWindowLongPtr(
                hwnd,
                GWL_EXSTYLE,
                new IntPtr(
                    extendedStyle));

            var cornerPreference =
                DWMWCP_DONOTROUND;

            DwmSetWindowAttribute(
                hwnd,
                DWMWA_WINDOW_CORNER_PREFERENCE,
                ref cornerPreference,
                Marshal.SizeOf<int>());

            var borderColor =
                DWM_COLOR_NONE;

            DwmSetWindowAttribute(
                hwnd,
                DWMWA_BORDER_COLOR,
                ref borderColor,
                Marshal.SizeOf<uint>());

            SetWindowPos(
                hwnd,
                IntPtr.Zero,
                0,
                0,
                0,
                0,
                SWP_NOMOVE
                | SWP_NOSIZE
                | SWP_NOZORDER
                | SWP_NOACTIVATE
                | SWP_FRAMECHANGED);

            return true;
        }
        catch
        {
            return false;
        }
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
        IntPtr newValue)
    {
        return IntPtr.Size == 8
            ? SetWindowLongPtr64(
                hwnd,
                index,
                newValue)
            : new IntPtr(
                SetWindowLong32(
                    hwnd,
                    index,
                    newValue.ToInt32()));
    }

    [DllImport("dwmapi.dll")]
    private static extern int
        DwmSetWindowAttribute(
            IntPtr hwnd,
            int attribute,
            ref int value,
            int size);

    [DllImport("dwmapi.dll")]
    private static extern int
        DwmSetWindowAttribute(
            IntPtr hwnd,
            int attribute,
            ref uint value,
            int size);

    [DllImport(
        "user32.dll",
        EntryPoint = "GetWindowLong")]
    private static extern int
        GetWindowLong32(
            IntPtr hwnd,
            int index);

    [DllImport(
        "user32.dll",
        EntryPoint = "GetWindowLongPtr")]
    private static extern IntPtr
        GetWindowLongPtr64(
            IntPtr hwnd,
            int index);

    [DllImport(
        "user32.dll",
        EntryPoint = "SetWindowLong")]
    private static extern int
        SetWindowLong32(
            IntPtr hwnd,
            int index,
            int newValue);

    [DllImport(
        "user32.dll",
        EntryPoint = "SetWindowLongPtr")]
    private static extern IntPtr
        SetWindowLongPtr64(
            IntPtr hwnd,
            int index,
            IntPtr newValue);

    [DllImport("user32.dll")]
    [return: MarshalAs(
        UnmanagedType.Bool)]
    private static extern bool
        SetWindowPos(
            IntPtr hwnd,
            IntPtr insertAfter,
            int x,
            int y,
            int width,
            int height,
            uint flags);
}
