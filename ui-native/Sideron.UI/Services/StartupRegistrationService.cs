using Microsoft.Win32;

namespace Sideron.UI.Services;

public sealed class StartupRegistrationService
{
    private const string RunKeyPath =
        @"Software\Microsoft\Windows\CurrentVersion\Run";

    private const string ValueName =
        "SIDERON";

    public StartupRegistrationStatus GetStatus()
    {
        try
        {
            using var key =
                Registry.CurrentUser
                    .OpenSubKey(
                        RunKeyPath,
                        writable:
                            false);

            var rawValue =
                key?.GetValue(
                    ValueName)
                as string;

            if (string.IsNullOrWhiteSpace(
                    rawValue))
            {
                return new StartupRegistrationStatus(
                    false,
                    string.Empty);
            }

            return new StartupRegistrationStatus(
                true,
                rawValue.Trim());
        }
        catch (Exception exception)
        {
            UiLog.Error(
                "Unable to read Sideron Windows startup registration.",
                exception);

            return new StartupRegistrationStatus(
                false,
                string.Empty);
        }
    }

    public void Apply(
        bool enabled)
    {
        try
        {
            using var key =
                Registry.CurrentUser
                    .CreateSubKey(
                        RunKeyPath,
                        writable:
                            true);

            if (key is null)
            {
                UiLog.Info(
                    "Unable to open Windows startup registry key.");

                return;
            }

            if (!enabled)
            {
                key.DeleteValue(
                    ValueName,
                    throwOnMissingValue:
                        false);

                UiLog.Info(
                    "Sideron Windows startup disabled.");

                return;
            }

            var executable =
                Environment.ProcessPath;

            if (
                string.IsNullOrWhiteSpace(
                    executable)
                || !File.Exists(
                    executable)
            )
            {
                UiLog.Info(
                    "Sideron Windows startup not registered: executable path unavailable.");

                return;
            }

            key.SetValue(
                ValueName,
                $"\"{executable}\"",
                RegistryValueKind.String);

            UiLog.Info(
                $"Sideron Windows startup registered: {executable}");
        }
        catch (Exception exception)
        {
            UiLog.Error(
                "Unable to update Sideron Windows startup.",
                exception);
        }
    }
}

public sealed record StartupRegistrationStatus(
    bool Enabled,
    string Command);
