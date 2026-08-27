using System.Diagnostics;
using IOPath = System.IO.Path;

namespace Atlas.UI.Services;

public sealed class CoreProcessService
    : IDisposable
{
    private Process?
        _ownedProcess;

    public bool OwnsCoreProcess =>
        _ownedProcess is not null
        && !_ownedProcess.HasExited;

    public async Task<bool> EnsureStartedAsync(
        Func<bool> isConnected,
        TimeSpan existingCoreGracePeriod)
    {
        var deadline =
            DateTime.UtcNow
            + existingCoreGracePeriod;

        while (
            DateTime.UtcNow < deadline
        )
        {
            if (isConnected())
            {
                UiLog.Info(
                    "Atlas Core already connected; no process started.");

                return false;
            }

            await Task.Delay(
                150);
        }

        if (isConnected())
        {
            return false;
        }

        var atlasRoot =
            FindAtlasRoot();

        if (atlasRoot is null)
        {
            UiLog.Info(
                "Atlas Core autostart skipped: Atlas root not found.");

            return false;
        }

        var startInfo =
            BuildStartInfo(
                atlasRoot);

        if (startInfo is null)
        {
            UiLog.Info(
                "Atlas Core autostart skipped: no packaged Core or development Python found.");

            return false;
        }

        try
        {
            _ownedProcess =
                Process.Start(
                    startInfo);

            if (_ownedProcess is null)
            {
                UiLog.Info(
                    "Atlas Core autostart failed: Process.Start returned null.");

                return false;
            }

            UiLog.Info(
                $"Atlas Core started automatically (PID {_ownedProcess.Id}).");

            return true;
        }
        catch (Exception exception)
        {
            UiLog.Error(
                "Atlas Core autostart failed.",
                exception);

            return false;
        }
    }

    public async Task WaitForOwnedCoreExitAsync(
        TimeSpan timeout)
    {
        var process =
            _ownedProcess;

        if (
            process is null
            || process.HasExited
        )
        {
            return;
        }

        using var cancellation =
            new CancellationTokenSource(
                timeout);

        try
        {
            await process.WaitForExitAsync(
                cancellation.Token);
        }
        catch (
            OperationCanceledException
        )
        {
            // The caller may decide whether to force termination.
        }
        catch (
            InvalidOperationException
        )
        {
            // Process already disappeared.
        }
    }

    public void StopOwnedCoreIfStillRunning()
    {
        var process =
            _ownedProcess;

        if (
            process is null
            || process.HasExited
        )
        {
            return;
        }

        try
        {
            process.Kill(
                entireProcessTree:
                    true);

            UiLog.Info(
                "Owned Atlas Core process terminated after graceful-stop timeout.");
        }
        catch (Exception exception)
        {
            UiLog.Error(
                "Unable to terminate owned Atlas Core process.",
                exception);
        }
    }

    private static ProcessStartInfo? BuildStartInfo(
        string atlasRoot)
    {
        var packagedCandidates =
            new[]
            {
                IOPath.Combine(
                    atlasRoot,
                    "Atlas.Core.exe"),

                IOPath.Combine(
                    atlasRoot,
                    "core",
                    "Atlas.Core.exe"),
            };

        foreach (
            var executable
            in packagedCandidates
        )
        {
            if (!File.Exists(
                    executable))
            {
                continue;
            }

            var packagedStartInfo =
                new ProcessStartInfo
                {
                    FileName =
                        executable,

                    WorkingDirectory =
                        atlasRoot,

                    UseShellExecute =
                        false,

                    CreateNoWindow =
                        true,
                };

            packagedStartInfo.Environment[
                "ATLAS_CONFIG_PATH"
            ] = AtlasConfigService.GetRuntimeConfigPath();

            return packagedStartInfo;
        }

        var python =
            IOPath.Combine(
                atlasRoot,
                ".venv",
                "Scripts",
                "python.exe");

        var mainCore =
            IOPath.Combine(
                atlasRoot,
                "main_core.py");

        if (
            !File.Exists(
                python)
            || !File.Exists(
                mainCore)
        )
        {
            return null;
        }

        var startInfo =
            new ProcessStartInfo
            {
                FileName =
                    python,

                WorkingDirectory =
                    atlasRoot,

                UseShellExecute =
                    false,

                CreateNoWindow =
                    true,
            };

        startInfo.ArgumentList.Add(
            mainCore);

        startInfo.Environment[
            "ATLAS_CONFIG_PATH"
        ] = AtlasConfigService.GetRuntimeConfigPath();

        return startInfo;
    }

    private static string? FindAtlasRoot()
    {
        var startingPoints =
            new[]
            {
                Directory.GetCurrentDirectory(),
                AppContext.BaseDirectory,
                @"C:\Atlas",
            };

        foreach (
            var startingPoint
            in startingPoints)
        {
            var current =
                new DirectoryInfo(
                    startingPoint);

            for (
                var depth = 0;
                current is not null
                && depth < 10;
                depth++,
                current =
                    current.Parent)
            {
                if (
                    File.Exists(
                        IOPath.Combine(
                            current.FullName,
                            "main_core.py"))
                    || File.Exists(
                        IOPath.Combine(
                            current.FullName,
                            "Atlas.Core.exe"))
                    || File.Exists(
                        IOPath.Combine(
                            current.FullName,
                            "core",
                            "Atlas.Core.exe"))
                )
                {
                    return current.FullName;
                }
            }
        }

        return null;
    }

    public void Dispose()
    {
        _ownedProcess?.Dispose();
        _ownedProcess = null;
    }
}
