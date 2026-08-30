using Sideron.UI.Desktop;
using Sideron.UI.Services;
using Microsoft.UI.Xaml;

namespace Sideron.UI;

public partial class App : Application
{
    private DesktopWindow? _desktopWindow;

    public App()
    {
        InitializeComponent();

        UnhandledException +=
            OnUnhandledException;

        UiLog.Info(
            "Sideron.UI application created.");
    }

    protected override void OnLaunched(
        LaunchActivatedEventArgs args)
    {
        try
        {
            UiLog.Info(
                "Creating DesktopWindow.");

            _desktopWindow =
                new DesktopWindow();

            UiLog.Info(
                "Activating DesktopWindow.");

            _desktopWindow.Activate();

            _desktopWindow.DispatcherQueue.TryEnqueue(
                () =>
                {
                    try
                    {
                        _desktopWindow.InitializeDesktop();

                        UiLog.Info(
                            "DesktopWindow initialized.");
                    }
                    catch (Exception exception)
                    {
                        UiLog.Error(
                            "DesktopWindow initialization failed.",
                            exception);
                    }
                });
        }
        catch (Exception exception)
        {
            UiLog.Error(
                "Sideron.UI launch failed.",
                exception);
        }
    }

    private static void OnUnhandledException(
        object sender,
        Microsoft.UI.Xaml.UnhandledExceptionEventArgs args)
    {
        UiLog.Error(
            "Unhandled WinUI exception.",
            args.Exception);

        args.Handled = true;
    }
}
