using System.Diagnostics;
using IOPath = System.IO.Path;

namespace Sideron.UI.Services;

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
                    "Sideron Core already connected; no process started.");

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
            FindSideronRoot();

        if (atlasRoot is null)
        {
            UiLog.Info(
                "Sideron Core autostart skipped: Sideron root not found.");

            return false;
        }

        var startInfo =
            BuildStartInfo(
                atlasRoot);

        if (startInfo is null)
        {
            UiLog.Info(
                "Sideron Core autostart skipped: no packaged Core or development Python found.");

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
                    "Sideron Core autostart failed: Process.Start returned null.");

                return false;
            }

            UiLog.Info(
                $"Sideron Core started automatically (PID {_ownedProcess.Id}).");

            return true;
        }
        catch (Exception exception)
        {
            UiLog.Error(
                "Sideron Core autostart failed.",
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
                "Owned Sideron Core process terminated after graceful-stop timeout.");
        }
        catch (Exception exception)
        {
            UiLog.Error(
                "Unable to terminate owned Sideron Core process.",
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
                    "SIDERON.Core.exe"),

                IOPath.Combine(
                    atlasRoot,
                    "core",
                    "SIDERON.Core.exe"),
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

            UiLog.Info(
                $"Sideron packaged Core selected: {executable}");

            packagedStartInfo.Environment[
                "SIDERON_CONFIG_PATH"
            ] = SideronConfigService.GetRuntimeConfigPath();

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

        UiLog.Info(
            $"Sideron development Core selected: {mainCore}");

        startInfo.ArgumentList.Add(
            mainCore);

        startInfo.Environment[
            "SIDERON_CONFIG_PATH"
        ] = SideronConfigService.GetRuntimeConfigPath();

        return startInfo;
    }

    private static string? FindSideronRoot()
    {
        var startingPoints =
            new[]
            {
                AppContext.BaseDirectory,
                Directory.GetCurrentDirectory(),
                @"C:\SIDERON",
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
                            "SIDERON.Core.exe"))
                    || File.Exists(
                        IOPath.Combine(
                            current.FullName,
                            "core",
                            "SIDERON.Core.exe"))
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
