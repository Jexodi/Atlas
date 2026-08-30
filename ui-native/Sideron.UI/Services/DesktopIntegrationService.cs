using Microsoft.UI.Xaml;
using System.Runtime.InteropServices;
using WinRT.Interop;

namespace Sideron.UI.Services;

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

    private static readonly IntPtr HWND_TOPMOST =
        new(-1);

    private static readonly IntPtr HWND_NOTOPMOST =
        new(-2);

    private const int SW_HIDE = 0;
    private const int SW_SHOW = 5;
    private const int SW_RESTORE = 9;

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

            // Ne pas donner la fenêtre du bureau Windows comme propriétaire à
            // SIDERON. Une fenêtre top-level possédée par le shell est exclue
            // de la barre des tâches, même avec WS_EX_APPWINDOW.
            //
            // SIDERON reste visuellement intégré au bureau grâce à sa fenêtre
            // sans bordure positionnée sur la WorkArea, mais demeure une vraie
            // fenêtre d'application afin que Windows crée son bouton dans la
            // barre des tâches et permette d'y revenir facilement.
            SetWindowLongPtr(
                hwnd,
                GWLP_HWNDPARENT,
                IntPtr.Zero);

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
                | SWP_FRAMECHANGED);

            // Explorer décide normalement tout seul si une fenêtre doit avoir
            // un bouton dans la barre des tâches. Comme SIDERON utilise une
            // fenêtre WinUI sans bordure de type WS_POPUP, on force ici le
            // rafraîchissement du Shell puis on l'enregistre explicitement
            // auprès d'ITaskbarList. Cela évite le cas observé où la fenêtre
            // apparaît dans Alt+Tab mais pas dans la barre des tâches.
            RefreshTaskbarRegistration(hwnd);

            UiLog.Info(
                "DesktopIntegration: Sideron Desktop registered as a top-level taskbar application window.");

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

    public static bool BringToForeground(
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

            // Si Windows a minimisé la fenêtre via son bouton de barre des
            // tâches, on la restaure avant de la remettre au sommet du Z-order.
            if (IsIconic(hwnd))
            {
                ShowWindow(
                    hwnd,
                    SW_RESTORE);
            }

            // La barre des tâches Explorer est elle-même topmost. Pour que le
            // plein écran SIDERON la recouvre uniquement lorsque SIDERON est
            // l'application active, on élève temporairement la fenêtre au
            // niveau TOPMOST. Le handler Activated retire cet état dès que la
            // fenêtre perd le focus.
            SetWindowPos(
                hwnd,
                HWND_TOPMOST,
                0,
                0,
                0,
                0,
                SWP_NOMOVE
                | SWP_NOSIZE
                | SWP_SHOWWINDOW);

            BringWindowToTop(hwnd);
            SetForegroundWindow(hwnd);

            return true;
        }
        catch (Exception exception)
        {
            UiLog.Error(
                "DesktopIntegration: unable to bring Sideron to foreground.",
                exception);

            return false;
        }
    }


    public static bool SetForegroundPriority(
        Window window,
        bool active)
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

            SetWindowPos(
                hwnd,
                active
                    ? HWND_TOPMOST
                    : HWND_NOTOPMOST,
                0,
                0,
                0,
                0,
                SWP_NOMOVE
                | SWP_NOSIZE
                | SWP_NOACTIVATE);

            return true;
        }
        catch (Exception exception)
        {
            UiLog.Error(
                "DesktopIntegration: unable to update Sideron foreground priority.",
                exception);

            return false;
        }
    }

    public static bool EnsureTaskbarButton(
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

            // Le Shell ne doit voir ni owner ni WS_EX_TOOLWINDOW.
            SetWindowLongPtr(
                hwnd,
                GWLP_HWNDPARENT,
                IntPtr.Zero);

            var extended =
                GetWindowLongPtr(
                    hwnd,
                    GWL_EXSTYLE)
                .ToInt64();

            extended &=
                ~WS_EX_TOOLWINDOW;

            extended |=
                WS_EX_APPWINDOW;

            SetWindowLongPtr(
                hwnd,
                GWL_EXSTYLE,
                new IntPtr(extended));

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
                | SWP_FRAMECHANGED);

            RefreshTaskbarRegistration(hwnd);
            return true;
        }
        catch (Exception exception)
        {
            UiLog.Error(
                "DesktopIntegration: unable to ensure taskbar button.",
                exception);

            return false;
        }
    }

    private static void RefreshTaskbarRegistration(
        IntPtr hwnd)
    {
        // Un Hide/Show après un changement de style force Explorer à
        // réévaluer l'éligibilité de la fenêtre pour la barre des tâches.
        ShowWindow(
            hwnd,
            SW_HIDE);

        ShowWindow(
            hwnd,
            SW_SHOW);

        try
        {
            var taskbar =
                (ITaskbarList)new CTaskbarList();

            taskbar.HrInit();
            taskbar.AddTab(hwnd);
            taskbar.ActivateTab(hwnd);

            if (Marshal.IsComObject(taskbar))
            {
                Marshal.FinalReleaseComObject(taskbar);
            }
        }
        catch (Exception exception)
        {
            // Le style WS_EX_APPWINDOW reste le mécanisme standard.
            // ITaskbarList est un renfort explicite pour les builds Explorer
            // qui ne recréent pas spontanément le bouton après le changement.
            UiLog.Error(
                "DesktopIntegration: explicit ITaskbarList registration failed.",
                exception);
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

        // Sideron reste une fenêtre plein écran sans bordure, mais doit être
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

    [ComImport]
    [Guid("56FDF344-FD6D-11D0-958A-006097C9A090")]
    private class CTaskbarList
    {
    }

    [ComImport]
    [Guid("56FDF342-FD6D-11D0-958A-006097C9A090")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface ITaskbarList
    {
        void HrInit();
        void AddTab(IntPtr hwnd);
        void DeleteTab(IntPtr hwnd);
        void ActivateTab(IntPtr hwnd);
        void SetActiveAlt(IntPtr hwnd);
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

    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool ShowWindow(
        IntPtr hwnd,
        int command);

    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool SetForegroundWindow(
        IntPtr hwnd);

    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool BringWindowToTop(
        IntPtr hwnd);

    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool IsIconic(
        IntPtr hwnd);

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
