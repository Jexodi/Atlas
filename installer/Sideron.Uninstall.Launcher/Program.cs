using System.Diagnostics;
using System.Drawing;
using System.Windows.Forms;

namespace SIDERON.Uninstall;

internal enum UninstallChoice { Cancel, KeepUserData, RemoveEverything }

internal static class Program
{
    [STAThread]
    private static int Main(string[] args)
    {
        Application.SetHighDpiMode(HighDpiMode.PerMonitorV2);
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);

        try
        {
            bool quiet = args.Any(argument => string.Equals(
                argument, "--quiet", StringComparison.OrdinalIgnoreCase));

            UninstallChoice choice = quiet
                ? UninstallChoice.KeepUserData
                : ShowUninstallChoice();

            if (choice == UninstallChoice.Cancel)
            {
                return 0;
            }

            string installRoot = AppContext.BaseDirectory;
            string sourceScript = Path.Combine(
                installRoot, "installer", "uninstall_sideron.ps1");

            if (!File.Exists(sourceScript))
            {
                SideronMessageForm.ShowError(
                    "Le programme de désinstallation Sideron est incomplet.");
                return 2;
            }

            string temporaryDirectory = Path.Combine(
                Path.GetTempPath(), "SideronUninstall", Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(temporaryDirectory);

            string temporaryScript = Path.Combine(
                temporaryDirectory, "uninstall_sideron.ps1");
            File.Copy(sourceScript, temporaryScript, overwrite: true);

            var startInfo = new ProcessStartInfo
            {
                FileName = "powershell.exe",
                UseShellExecute = false,
                CreateNoWindow = true,
                WindowStyle = ProcessWindowStyle.Hidden,
                WorkingDirectory = temporaryDirectory,
            };

            startInfo.ArgumentList.Add("-NoProfile");
            startInfo.ArgumentList.Add("-ExecutionPolicy");
            startInfo.ArgumentList.Add("Bypass");
            startInfo.ArgumentList.Add("-File");
            startInfo.ArgumentList.Add(temporaryScript);
            startInfo.ArgumentList.Add("-InstalledRoot");
            startInfo.ArgumentList.Add(installRoot.TrimEnd(
                Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar));

            if (choice == UninstallChoice.RemoveEverything)
            {
                startInfo.ArgumentList.Add("-RemoveData");
            }

            if (quiet)
            {
                startInfo.ArgumentList.Add("-Quiet");
            }

            if (Process.Start(startInfo) is null)
            {
                SideronMessageForm.ShowError(
                    "Impossible de démarrer la désinstallation Sideron.");
                return 3;
            }

            // Le lanceur se ferme afin que le script temporaire puisse
            // supprimer le dossier d'installation, y compris cet exécutable.
            return 0;
        }
        catch (Exception exception)
        {
            SideronMessageForm.ShowError(
                "La désinstallation Sideron n'a pas pu démarrer.\n\n" +
                exception.Message);
            return 1;
        }
    }

    private static UninstallChoice ShowUninstallChoice()
    {
        using var form = new UninstallChoiceForm();
        form.ShowDialog();
        return form.Choice;
    }

    internal static void FitFormToCurrentScreen(Form form)
    {
        Rectangle workingArea = Screen.FromControl(form).WorkingArea;
        int maximumWidth = Math.Max(360, workingArea.Width - 24);
        int maximumHeight = Math.Max(220, workingArea.Height - 24);

        if (form.Width > maximumWidth || form.Height > maximumHeight)
        {
            float ratio = Math.Min(
                maximumWidth / (float)form.Width,
                maximumHeight / (float)form.Height);
            form.Scale(new SizeF(ratio, ratio));
        }

        form.Size = new Size(
            Math.Min(form.Width, maximumWidth),
            Math.Min(form.Height, maximumHeight));
        form.MaximumSize = new Size(maximumWidth, maximumHeight);

        form.Location = new Point(
            workingArea.Left + Math.Max(0, (workingArea.Width - form.Width) / 2),
            workingArea.Top + Math.Max(0, (workingArea.Height - form.Height) / 2));
    }
}

internal sealed class UninstallChoiceForm : Form
{
    private static readonly Color BackgroundColor = Color.FromArgb(9, 15, 22);
    private static readonly Color BorderColor = Color.FromArgb(53, 108, 134);

    public UninstallChoice Choice { get; private set; } = UninstallChoice.Cancel;

    public UninstallChoiceForm()
    {
        Text = "Désinstallation Sideron";
        StartPosition = FormStartPosition.CenterScreen;
        AutoScaleMode = AutoScaleMode.Dpi;
        AutoScaleDimensions = new SizeF(96F, 96F);
        ClientSize = new Size(680, 400);
        FormBorderStyle = FormBorderStyle.None;
        BackColor = BackgroundColor;
        ForeColor = Color.FromArgb(229, 244, 252);
        ShowInTaskbar = true;
        TopMost = true;
        DoubleBuffered = true;
        Padding = new Padding(1);
        Shown += (_, _) => Program.FitFormToCurrentScreen(this);

        var root = new TableLayoutPanel
        {
            Dock = DockStyle.Fill,
            BackColor = BackgroundColor,
            Padding = new Padding(34, 25, 34, 28),
            ColumnCount = 1,
            RowCount = 6,
        };

        root.RowStyles.Add(new RowStyle(SizeType.Absolute, 38));
        root.RowStyles.Add(new RowStyle(SizeType.Absolute, 30));
        root.RowStyles.Add(new RowStyle(SizeType.Absolute, 58));
        root.RowStyles.Add(new RowStyle(SizeType.Absolute, 78));
        root.RowStyles.Add(new RowStyle(SizeType.Absolute, 92));
        root.RowStyles.Add(new RowStyle(SizeType.Percent, 100));

        var title = CreateLabel(
            "DÉSINSTALLATION SIDERON", 16F, FontStyle.Bold,
            Color.FromArgb(240, 250, 255));
        var subtitle = CreateLabel(
            "Choisissez les éléments à supprimer.", 9F, FontStyle.Regular,
            Color.FromArgb(82, 190, 234));
        var description = CreateLabel(
            "Sideron va être retiré de cet ordinateur. Vous pouvez conserver vos fichiers ou supprimer toutes les données gérées par Sideron.",
            10.5F, FontStyle.Regular, Color.FromArgb(202, 226, 238));
        description.Padding = new Padding(0, 10, 0, 6);

        var keepButton = CreateChoiceButton(
            "Conserver les données",
            "Supprime l'application et le service, mais conserve les fichiers utilisateur.",
            false);
        keepButton.Click += (_, _) =>
        {
            Choice = UninstallChoice.KeepUserData;
            Close();
        };

        var removeButton = CreateChoiceButton(
            "Désinstallation totale",
            "Supprime l'application, le service et toutes les données Sideron. Cette action est irréversible.",
            true);
        removeButton.Click += (_, _) =>
        {
            Choice = UninstallChoice.RemoveEverything;
            Close();
        };

        var footer = new FlowLayoutPanel
        {
            Dock = DockStyle.Fill,
            FlowDirection = FlowDirection.RightToLeft,
            WrapContents = false,
            Padding = new Padding(0),
            BackColor = BackgroundColor,
        };

        var cancelButton = CreateFlatButton("Annuler", 110);
        cancelButton.Margin = new Padding(3, 2, 3, 0);
        cancelButton.Click += (_, _) => Close();
        footer.Controls.Add(cancelButton);

        root.Controls.Add(title, 0, 0);
        root.Controls.Add(subtitle, 0, 1);
        root.Controls.Add(description, 0, 2);
        root.Controls.Add(keepButton, 0, 3);
        root.Controls.Add(removeButton, 0, 4);
        root.Controls.Add(footer, 0, 5);
        Controls.Add(root);

        MouseDown += (_, eventArgs) =>
        {
            if (eventArgs.Button == MouseButtons.Left)
            {
                Capture = false;
                Message message = Message.Create(
                    Handle, 0x00A1, new IntPtr(2), IntPtr.Zero);
                WndProc(ref message);
            }
        };
    }

    protected override void OnPaint(PaintEventArgs e)
    {
        base.OnPaint(e);
        using var pen = new Pen(BorderColor, 1F);
        Rectangle rectangle = ClientRectangle;
        rectangle.Width -= 1;
        rectangle.Height -= 1;
        e.Graphics.DrawRectangle(pen, rectangle);
    }

    private static Label CreateLabel(
        string text, float size, FontStyle style, Color color)
    {
        return new Label
        {
            Text = text,
            Dock = DockStyle.Fill,
            Font = new Font("Segoe UI", size, style),
            ForeColor = color,
            TextAlign = ContentAlignment.MiddleLeft,
        };
    }

    private static Button CreateChoiceButton(
        string title, string description, bool destructive)
    {
        var button = new Button
        {
            Dock = DockStyle.Fill,
            FlatStyle = FlatStyle.Flat,
            TextAlign = ContentAlignment.MiddleLeft,
            Padding = new Padding(16, 7, 16, 7),
            Margin = new Padding(0, 4, 0, 4),
            Font = new Font("Segoe UI", 10F, FontStyle.Bold),
            Text = title + Environment.NewLine + description,
            ForeColor = destructive
                ? Color.FromArgb(255, 218, 205)
                : Color.FromArgb(229, 244, 252),
            BackColor = destructive
                ? Color.FromArgb(47, 25, 25)
                : Color.FromArgb(16, 29, 39),
            Cursor = Cursors.Hand,
        };

        button.FlatAppearance.BorderSize = 1;
        button.FlatAppearance.BorderColor = destructive
            ? Color.FromArgb(142, 69, 61)
            : BorderColor;
        button.FlatAppearance.MouseOverBackColor = destructive
            ? Color.FromArgb(66, 32, 30)
            : Color.FromArgb(25, 50, 66);
        return button;
    }

    private static Button CreateFlatButton(string text, int width)
    {
        var button = new Button
        {
            Text = text,
            Width = width,
            Height = 34,
            FlatStyle = FlatStyle.Flat,
            BackColor = Color.FromArgb(16, 29, 39),
            ForeColor = Color.FromArgb(229, 244, 252),
            Font = new Font("Segoe UI", 9F),
            Cursor = Cursors.Hand,
        };
        button.FlatAppearance.BorderColor = BorderColor;
        button.FlatAppearance.MouseOverBackColor = Color.FromArgb(25, 50, 66);
        return button;
    }
}

internal sealed class SideronMessageForm : Form
{
    private SideronMessageForm(string message)
    {
        Text = "SIDERON";
        StartPosition = FormStartPosition.CenterScreen;
        AutoScaleMode = AutoScaleMode.Dpi;
        AutoScaleDimensions = new SizeF(96F, 96F);
        ClientSize = new Size(560, 250);
        FormBorderStyle = FormBorderStyle.None;
        BackColor = Color.FromArgb(9, 15, 22);
        ForeColor = Color.FromArgb(229, 244, 252);
        TopMost = true;
        Padding = new Padding(30, 24, 30, 24);
        Shown += (_, _) => Program.FitFormToCurrentScreen(this);

        var label = new Label
        {
            Text = message,
            Dock = DockStyle.Fill,
            Font = new Font("Segoe UI", 10F),
            ForeColor = ForeColor,
            TextAlign = ContentAlignment.MiddleLeft,
        };
        var button = new Button
        {
            Text = "Fermer",
            Dock = DockStyle.Bottom,
            Height = 34,
            FlatStyle = FlatStyle.Flat,
            BackColor = Color.FromArgb(16, 29, 39),
            ForeColor = ForeColor,
        };
        button.FlatAppearance.BorderColor = Color.FromArgb(53, 108, 134);
        button.Click += (_, _) => Close();
        Controls.Add(label);
        Controls.Add(button);
    }

    public static void ShowError(string message)
    {
        using var form = new SideronMessageForm(message);
        form.ShowDialog();
    }

    protected override void OnPaint(PaintEventArgs e)
    {
        base.OnPaint(e);
        using var pen = new Pen(Color.FromArgb(53, 108, 134), 1F);
        Rectangle rectangle = ClientRectangle;
        rectangle.Width -= 1;
        rectangle.Height -= 1;
        e.Graphics.DrawRectangle(pen, rectangle);
    }
}
