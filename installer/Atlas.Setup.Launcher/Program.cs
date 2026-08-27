using System.Diagnostics;
using System.Drawing;
using System.Windows.Forms;
using System.IO.Compression;
using System.Reflection;

namespace Atlas.Setup;

internal static class Program
{
    private const string PayloadResourceName = "AtlasSetup.Payload.zip";
    private const string IconResourceName = "AtlasSetup.Icon.ico";
    private const string SetupMutexName = @"Global\Atlas.Setup.Launcher";

    [STAThread]
    private static int Main(string[] args)
    {
        // Atlas.exe est installé dans C:\Program Files\Atlas et peut lancer
        // ce programme avec ce dossier comme répertoire courant. Même après
        // la fermeture d'Atlas.exe, Windows refuse alors de renommer le
        // dossier tant que ce processus en conserve le répertoire courant.
        // Basculer immédiatement vers un emplacement neutre libère ce verrou.
        Environment.CurrentDirectory =
            Path.GetTempPath();

        bool silentUpdate =
            args.Any(
                argument =>
                    string.Equals(
                        argument,
                        "--update",
                        StringComparison.OrdinalIgnoreCase))
            && args.Any(
                argument =>
                    string.Equals(
                        argument,
                        "--silent",
                        StringComparison.OrdinalIgnoreCase));

        string? progressFile =
            GetArgumentValue(
                args,
                "--progress-file");

        bool restartAtlas =
            args.Any(
                argument =>
                    string.Equals(
                        argument,
                        "--restart-atlas",
                        StringComparison.OrdinalIgnoreCase));

        int? waitForProcessId =
            GetPositiveIntegerArgumentValue(
                args,
                "--wait-for-process");

        string? temporaryRoot = null;
        bool ownsSetupMutex = false;
        Process? installerProcess = null;

        using var setupMutex = new Mutex(
            initiallyOwned: false,
            name: SetupMutexName);

        try
        {
            try
            {
                ownsSetupMutex = setupMutex.WaitOne(
                    TimeSpan.Zero,
                    exitContext: false);
            }
            catch (AbandonedMutexException)
            {
                ownsSetupMutex = true;
            }

            if (!ownsSetupMutex)
            {
                if (!silentUpdate)
                {
                    ShowError(
                        "Une autre fenêtre d'installation Atlas est déjà ouverte.");
                }

                return 4;
            }

            if (silentUpdate)
            {
                temporaryRoot =
                    CreateTemporaryInstallerDirectory();

                ExtractEmbeddedPayload(
                    temporaryRoot);

                string silentInstallerScript =
                    Path.Combine(
                        temporaryRoot,
                        "install_atlas.ps1");

                if (!File.Exists(
                        silentInstallerScript))
                {
                    throw new FileNotFoundException(
                        "Les fichiers internes de mise à jour Atlas sont incomplets.",
                        silentInstallerScript);
                }

                progressFile =
                    ResolveProgressFile(
                        progressFile);

                TryDeleteProgressFile(
                    progressFile);

                WaitForAtlasLauncherExit(
                    waitForProcessId);

                using Process? updateHostProcess =
                    StartUpdateHost(
                        temporaryRoot,
                        progressFile);

                int updateExitCode =
                    RunSilentUpdate(
                        temporaryRoot,
                        silentInstallerScript,
                        progressFile,
                        restartAtlas);

                if (
                    updateExitCode == 0
                    && updateHostProcess is not null
                    && !updateHostProcess.HasExited
                )
                {
                    updateHostProcess.WaitForExit(
                        5000);
                }

                return updateExitCode;
            }

            string readyEventName =
                "Local\\Atlas.Setup.Ready."
                + Guid.NewGuid().ToString("N");

            using var readyEvent = new EventWaitHandle(
                initialState: false,
                mode: EventResetMode.ManualReset,
                name: readyEventName);

            using var splash = CreateSplashWindow();

            Exception? startupException = null;

            splash.Shown += (_, _) =>
            {
                _ = Task.Run(
                    () =>
                    {
                        try
                        {
                            temporaryRoot =
                                CreateTemporaryInstallerDirectory();

                            ExtractEmbeddedPayload(
                                temporaryRoot);

                            string installerScript =
                                Path.Combine(
                                    temporaryRoot,
                                    "installer_gui.ps1");

                            if (!File.Exists(
                                    installerScript))
                            {
                                throw new FileNotFoundException(
                                    "Les fichiers internes de l'installateur Atlas sont incomplets.",
                                    installerScript);
                            }

                            var startInfo =
                                new ProcessStartInfo
                                {
                                    FileName = "powershell.exe",
                                    UseShellExecute = false,
                                    CreateNoWindow = true,
                                    WindowStyle =
                                        ProcessWindowStyle.Hidden,
                                    WorkingDirectory =
                                        temporaryRoot,
                                    RedirectStandardOutput = false,
                                    RedirectStandardError = false,
                                };

                            startInfo.Environment[
                                "ATLAS_SETUP_READY_EVENT"
                            ] = readyEventName;

                            startInfo.ArgumentList.Add(
                                "-NoProfile");
                            startInfo.ArgumentList.Add(
                                "-ExecutionPolicy");
                            startInfo.ArgumentList.Add(
                                "Bypass");
                            startInfo.ArgumentList.Add(
                                "-File");
                            startInfo.ArgumentList.Add(
                                installerScript);

                            installerProcess =
                                Process.Start(
                                    startInfo);

                            if (installerProcess is null)
                            {
                                throw new InvalidOperationException(
                                    "Impossible de démarrer l'installateur Atlas.");
                            }

                            using var processExitedEvent =
                                new ManualResetEvent(
                                    initialState: false);

                            installerProcess.EnableRaisingEvents = true;

                            installerProcess.Exited += (_, _) =>
                            {
                                try
                                {
                                    processExitedEvent.Set();
                                }
                                catch
                                {
                                }
                            };

                            if (installerProcess.HasExited)
                            {
                                processExitedEvent.Set();
                            }

                            int signal =
                                WaitHandle.WaitAny(
                                    new WaitHandle[]
                                    {
                                        readyEvent,
                                        processExitedEvent,
                                    });

                            if (signal == 1)
                            {
                                installerProcess.WaitForExit();

                                if (installerProcess.ExitCode != 0)
                                {
                                    throw new InvalidOperationException(
                                        "L'interface de l'installateur Atlas n'a pas pu démarrer.");
                                }

                                throw new InvalidOperationException(
                                    "L'interface de l'installateur Atlas s'est fermée avant son affichage.");
                            }
                        }
                        catch (Exception exception)
                        {
                            startupException =
                                exception;
                        }
                        finally
                        {
                            if (!splash.IsDisposed)
                            {
                                splash.BeginInvoke(
                                    new Action(
                                        splash.Close));
                            }
                        }
                    });
            };

            Application.Run(
                splash);

            if (startupException is not null)
            {
                throw startupException;
            }

            if (installerProcess is null)
            {
                throw new InvalidOperationException(
                    "Impossible de démarrer l'installateur Atlas.");
            }

            installerProcess.WaitForExit();
            int exitCode =
                installerProcess.ExitCode;

            installerProcess.Dispose();
            installerProcess = null;

            return exitCode;
        }
        catch (Exception exception)
        {
            if (!silentUpdate)
            {
                ShowError(
                    "Atlas Setup n'a pas pu démarrer.\n\n"
                    + exception.Message);
            }

            return 1;
        }
        finally
        {
            installerProcess?.Dispose();

            if (!string.IsNullOrWhiteSpace(
                    temporaryRoot))
            {
                TryDeleteTemporaryInstallerDirectory(
                    temporaryRoot);
            }

            if (ownsSetupMutex)
            {
                try
                {
                    setupMutex.ReleaseMutex();
                }
                catch
                {
                }
            }
        }
    }

    private static string ResolveProgressFile(
        string? progressFile)
    {
        if (!string.IsNullOrWhiteSpace(
                progressFile))
        {
            return Path.GetFullPath(
                progressFile);
        }

        string root =
            Environment.GetFolderPath(
                Environment.SpecialFolder.LocalApplicationData);

        return Path.Combine(
            root,
            "Atlas",
            "updates",
            "update-progress.json");
    }

    private static void TryDeleteProgressFile(
        string progressFile)
    {
        try
        {
            string? directory =
                Path.GetDirectoryName(
                    progressFile);

            if (!string.IsNullOrWhiteSpace(
                    directory))
            {
                Directory.CreateDirectory(
                    directory);
            }

            if (File.Exists(
                    progressFile))
            {
                File.Delete(
                    progressFile);
            }
        }
        catch
        {
        }
    }

    private static Process? StartUpdateHost(
        string workingDirectory,
        string progressFile)
    {
        string updateHostPath =
            Path.Combine(
                workingDirectory,
                "Atlas.UpdateHost.exe");

        if (!File.Exists(
                updateHostPath))
        {
            throw new FileNotFoundException(
                "L'interface de progression Atlas.UpdateHost.exe est introuvable.",
                updateHostPath);
        }

        var startInfo =
            new ProcessStartInfo
            {
                FileName =
                    updateHostPath,
                UseShellExecute =
                    false,
                WorkingDirectory =
                    workingDirectory,
            };

        startInfo.ArgumentList.Add(
            "--progress-file");

        startInfo.ArgumentList.Add(
            progressFile);

        Process? process =
            Process.Start(
                startInfo);

        if (process is null)
        {
            throw new InvalidOperationException(
                "Impossible de démarrer Atlas.UpdateHost.");
        }

        return process;
    }

    private static int RunSilentUpdate(
        string workingDirectory,
        string installerScript,
        string? progressFile,
        bool restartAtlas)
    {
        var startInfo =
            new ProcessStartInfo
            {
                FileName = "powershell.exe",
                UseShellExecute = false,
                CreateNoWindow = true,
                WindowStyle =
                    ProcessWindowStyle.Hidden,
                WorkingDirectory =
                    workingDirectory,
                RedirectStandardOutput = false,
                RedirectStandardError = false,
            };

        startInfo.ArgumentList.Add(
            "-NoProfile");
        startInfo.ArgumentList.Add(
            "-ExecutionPolicy");
        startInfo.ArgumentList.Add(
            "Bypass");
        startInfo.ArgumentList.Add(
            "-File");
        startInfo.ArgumentList.Add(
            installerScript);
        startInfo.ArgumentList.Add(
            "-Update");
        startInfo.ArgumentList.Add(
            "-Silent");

        if (restartAtlas)
        {
            startInfo.ArgumentList.Add(
                "-RestartAtlas");
        }

        if (!string.IsNullOrWhiteSpace(
                progressFile))
        {
            startInfo.ArgumentList.Add(
                "-ProgressFile");
            startInfo.ArgumentList.Add(
                progressFile);
        }

        using Process? process =
            Process.Start(
                startInfo);

        if (process is null)
        {
            throw new InvalidOperationException(
                "Impossible de démarrer le moteur de mise à jour Atlas.");
        }

        process.WaitForExit();

        return process.ExitCode;
    }

    private static string? GetArgumentValue(
        string[] args,
        string name)
    {
        for (
            int index = 0;
            index < args.Length - 1;
            index++)
        {
            if (string.Equals(
                    args[index],
                    name,
                    StringComparison.OrdinalIgnoreCase))
            {
                return args[index + 1];
            }
        }

        return null;
    }

    private static int? GetPositiveIntegerArgumentValue(
        string[] args,
        string name)
    {
        string? value =
            GetArgumentValue(
                args,
                name);

        if (
            int.TryParse(
                value,
                out int parsed)
            && parsed > 0
        )
        {
            return parsed;
        }

        return null;
    }

    private static void WaitForAtlasLauncherExit(
        int? processId)
    {
        if (
            processId is null
            || processId.Value == Environment.ProcessId
        )
        {
            return;
        }

        try
        {
            using Process process =
                Process.GetProcessById(
                    processId.Value);

            if (
                !process.HasExited
                && !process.WaitForExit(
                    60000)
            )
            {
                throw new TimeoutException(
                    "Atlas.exe ne s'est pas arrêté dans le délai prévu.");
            }
        }
        catch (ArgumentException)
        {
            // Le processus s'est déjà terminé entre le lancement et la
            // recherche de son PID.
        }

        // Laisse Windows libérer les derniers handles d'image et de dossier.
        Thread.Sleep(
            750);
    }

    private static Form CreateSplashWindow()
    {
        var splash =
            new Form
            {
                Text = "Installation Atlas",
                StartPosition =
                    FormStartPosition.CenterScreen,
                ClientSize =
                    new Size(
                        760,
                        360),
                FormBorderStyle =
                    FormBorderStyle.None,
                MaximizeBox = false,
                MinimizeBox = false,
                BackColor =
                    Color.FromArgb(
                        9,
                        15,
                        22),
                ForeColor =
                    Color.FromArgb(
                        229,
                        244,
                        252),
                ShowInTaskbar = true,
                TopMost = true,
                Padding = new Padding(1),
            };

        Icon? atlasIcon =
            LoadEmbeddedAtlasIcon();

        if (atlasIcon is not null)
        {
            splash.Icon =
                atlasIcon;
        }

        var frame =
            new Panel
            {
                Dock = DockStyle.Fill,
                BackColor =
                    Color.FromArgb(
                        53,
                        108,
                        134),
                Padding = new Padding(1),
            };

        var content =
            new TableLayoutPanel
            {
                Dock = DockStyle.Fill,
                ColumnCount = 1,
                RowCount = 6,
                BackColor = splash.BackColor,
                Padding = new Padding(
                    42,
                    78,
                    42,
                    62),
            };

        content.RowStyles.Add(new RowStyle(SizeType.Absolute, 36F));
        content.RowStyles.Add(new RowStyle(SizeType.Absolute, 28F));
        content.RowStyles.Add(new RowStyle(SizeType.Absolute, 42F));
        content.RowStyles.Add(new RowStyle(SizeType.Absolute, 24F));
        content.RowStyles.Add(new RowStyle(SizeType.Absolute, 20F));
        content.RowStyles.Add(new RowStyle(SizeType.Percent, 100F));

        var title =
            new Label
            {
                Dock = DockStyle.Fill,
                Text = "INSTALLATION ATLAS",
                Font = new Font(
                    "Segoe UI",
                    16F,
                    FontStyle.Bold),
                ForeColor = Color.FromArgb(225, 244, 252),
                TextAlign = ContentAlignment.MiddleLeft,
            };

        var subtitle =
            new Label
            {
                Dock = DockStyle.Fill,
                Text = "Préparation de l’assistant…",
                ForeColor = Color.FromArgb(114, 150, 169),
                Font = new Font("Segoe UI", 9F, FontStyle.Regular),
                TextAlign = ContentAlignment.MiddleLeft,
            };

        var status =
            new Label
            {
                Dock = DockStyle.Fill,
                Text = "Initialisation des composants Atlas…",
                ForeColor = Color.FromArgb(202, 226, 238),
                Font = new Font("Segoe UI", 10.5F, FontStyle.Regular),
                TextAlign = ContentAlignment.MiddleLeft,
            };

        var progressHost =
            new Panel
            {
                Dock = DockStyle.Fill,
                Padding = new Padding(0, 7, 0, 7),
                BackColor = splash.BackColor,
            };

        var progressTrack =
            new Panel
            {
                Dock = DockStyle.Fill,
                Height = 8,
                BackColor = Color.FromArgb(25, 43, 55),
            };

        var progressFill =
            new Panel
            {
                Height = 8,
                Width = 120,
                Left = -120,
                Top = 0,
                BackColor = Color.FromArgb(65, 206, 255),
            };

        progressTrack.Controls.Add(progressFill);
        progressHost.Controls.Add(progressTrack);

        var animationTimer =
            new System.Windows.Forms.Timer
            {
                Interval = 18,
            };

        animationTimer.Tick +=
            (_, _) =>
            {
                int next = progressFill.Left + 8;

                if (next > progressTrack.ClientSize.Width)
                {
                    next = -progressFill.Width;
                }

                progressFill.Left = next;
            };

        splash.Shown +=
            (_, _) => animationTimer.Start();

        splash.FormClosed +=
            (_, _) =>
            {
                animationTimer.Stop();
                animationTimer.Dispose();
            };

        var progressLabel =
            new Label
            {
                Dock = DockStyle.Fill,
                Text = "CHARGEMENT",
                ForeColor = Color.FromArgb(96, 211, 255),
                Font = new Font("Segoe UI", 8.5F, FontStyle.Bold),
                TextAlign = ContentAlignment.MiddleRight,
            };

        content.Controls.Add(title, 0, 0);
        content.Controls.Add(subtitle, 0, 1);
        content.Controls.Add(status, 0, 2);
        content.Controls.Add(progressHost, 0, 3);
        content.Controls.Add(progressLabel, 0, 4);

        frame.Controls.Add(content);
        splash.Controls.Add(frame);

        return splash;
    }

    private static Icon? LoadEmbeddedAtlasIcon()
    {
        Assembly assembly =
            Assembly.GetExecutingAssembly();

        Stream? iconStream =
            assembly.GetManifestResourceStream(
                IconResourceName);

        if (iconStream is null)
        {
            return null;
        }

        using (iconStream)
        {
            using var sourceIcon =
                new Icon(
                    iconStream);

            return new Icon(
                sourceIcon,
                new Size(
                    256,
                    256));
        }
    }

    private static string CreateTemporaryInstallerDirectory()
    {
        string root = Path.Combine(
            Path.GetTempPath(),
            "AtlasSetup",
            Guid.NewGuid().ToString("N"));

        Directory.CreateDirectory(root);
        return root;
    }

    private static void ExtractEmbeddedPayload(string destination)
    {
        Assembly assembly = Assembly.GetExecutingAssembly();

        using Stream? payloadStream =
            assembly.GetManifestResourceStream(PayloadResourceName);

        if (payloadStream is null)
        {
            throw new InvalidOperationException(
                "Le payload interne Atlas est introuvable.");
        }

        using var archive = new ZipArchive(
            payloadStream,
            ZipArchiveMode.Read,
            leaveOpen: false);

        string destinationRoot = Path.GetFullPath(destination)
            .TrimEnd(
                Path.DirectorySeparatorChar,
                Path.AltDirectorySeparatorChar)
            + Path.DirectorySeparatorChar;

        foreach (ZipArchiveEntry entry in archive.Entries)
        {
            string destinationPath = Path.GetFullPath(
                Path.Combine(destination, entry.FullName));

            if (!destinationPath.StartsWith(
                    destinationRoot,
                    StringComparison.OrdinalIgnoreCase))
            {
                throw new InvalidDataException(
                    "Le payload Atlas contient un chemin non autorisé.");
            }

            if (string.IsNullOrEmpty(entry.Name))
            {
                Directory.CreateDirectory(destinationPath);
                continue;
            }

            string? parentDirectory =
                Path.GetDirectoryName(destinationPath);

            if (!string.IsNullOrWhiteSpace(parentDirectory))
            {
                Directory.CreateDirectory(parentDirectory);
            }

            entry.ExtractToFile(
                destinationPath,
                overwrite: true);
        }
    }

    private static void TryDeleteTemporaryInstallerDirectory(string path)
    {
        try
        {
            if (Directory.Exists(path))
            {
                Directory.Delete(
                    path,
                    recursive: true);
            }

            string? parent = Directory.GetParent(path)?.FullName;

            if (!string.IsNullOrWhiteSpace(parent) &&
                Directory.Exists(parent) &&
                !Directory.EnumerateFileSystemEntries(parent).Any())
            {
                Directory.Delete(parent);
            }
        }
        catch
        {
        }
    }

    private static void ShowError(string message)
    {
        const uint MB_OK = 0x00000000;
        const uint MB_ICONERROR = 0x00000010;

        NativeMethods.MessageBox(
            IntPtr.Zero,
            message,
            "Atlas",
            MB_OK | MB_ICONERROR);
    }

    private static class NativeMethods
    {
        [System.Runtime.InteropServices.DllImport(
            "user32.dll",
            CharSet = System.Runtime.InteropServices.CharSet.Unicode)]
        internal static extern int MessageBox(
            IntPtr hWnd,
            string text,
            string caption,
            uint type);
    }
}
