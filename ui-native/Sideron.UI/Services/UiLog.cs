namespace Sideron.UI.Services;

public static class UiLog
{
    private static readonly object Sync = new();

    public static string LogPath
    {
        get
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

            var logs =
                Path.Combine(
                    localAppData,
                    "SIDERON",
                    "logs");

            Directory.CreateDirectory(
                logs);

            return Path.Combine(
                logs,
                "atlas-ui.log");
        }
    }

    public static void Info(
        string message)
    {
        Write(
            "INFO",
            message);
    }

    public static void Error(
        string message,
        Exception? exception = null)
    {
        var details =
            exception is null
                ? message
                : (
                    message
                    + Environment.NewLine
                    + exception
                );

        Write(
            "ERROR",
            details);
    }

    private static void Write(
        string level,
        string message)
    {
        try
        {
            lock (Sync)
            {
                File.AppendAllText(
                    LogPath,
                    (
                        $"{DateTime.Now:yyyy-MM-dd HH:mm:ss.fff} "
                        + $"[{level}] {message}"
                        + Environment.NewLine
                    ));
            }
        }
        catch
        {
            // Le journal ne doit jamais faire planter Sideron.UI.
        }
    }
}
