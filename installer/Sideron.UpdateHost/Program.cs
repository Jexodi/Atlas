using System.Diagnostics;
using System.Drawing.Drawing2D;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Sideron.UpdateHost;

internal static class Program
{
    [STAThread]
    private static void Main(string[] args)
    {
        Application.SetHighDpiMode(
            HighDpiMode.PerMonitorV2);

        ApplicationConfiguration.Initialize();

        string progressFile =
            GetArgumentValue(
                args,
                "--progress-file")
            ?? Path.Combine(
                Environment.GetFolderPath(
                    Environment.SpecialFolder.LocalApplicationData),
                "SIDERON",
                "updates",
                "update-progress.json");

        Application.Run(
            new UpdateForm(
                progressFile));
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
}

internal sealed class UpdateForm : Form
{
    private readonly string _progressFile;
    private readonly Label _titleLabel;
    private readonly Label _versionLabel;
    private readonly Label _statusLabel;
    private readonly Label _percentLabel;
    private readonly Panel _progressTrack;
    private readonly Panel _progressFill;
    private readonly Button _closeButton;
    private readonly System.Windows.Forms.Timer _pollTimer;

    private DateTime _lastProgressWriteUtc =
        DateTime.MinValue;

    private bool _terminalStateSeen;

    public UpdateForm(
        string progressFile)
    {
        _progressFile =
            progressFile;

        Text =
            "Mise à jour Sideron";

        StartPosition =
            FormStartPosition.CenterScreen;

        AutoScaleMode =
            AutoScaleMode.Dpi;

        AutoScaleDimensions =
            new SizeF(
                96F,
                96F);

        ClientSize =
            new Size(
                620,
                248);

        FormBorderStyle =
            FormBorderStyle.None;

        BackColor =
            Color.FromArgb(
                9,
                15,
                22);

        ForeColor =
            Color.FromArgb(
                229,
                244,
                252);

        TopMost =
            true;

        ShowInTaskbar =
            true;

        DoubleBuffered =
            true;

        Padding =
            new Padding(
                30,
                24,
                30,
                24);

        try
        {
            string iconPath =
                Path.Combine(
                    AppContext.BaseDirectory,
                    "sideron.ico");

            if (File.Exists(iconPath))
            {
                Icon =
                    new Icon(
                        iconPath);
            }
        }
        catch
        {
        }

        var root =
            new TableLayoutPanel
            {
                Dock = DockStyle.Fill,
                ColumnCount = 1,
                RowCount = 7,
                BackColor = BackColor,
            };

        root.RowStyles.Add(
            new RowStyle(
                SizeType.Percent,
                20));

        root.RowStyles.Add(
            new RowStyle(
                SizeType.Percent,
                14));

        root.RowStyles.Add(
            new RowStyle(
                SizeType.Percent,
                17));

        root.RowStyles.Add(
            new RowStyle(
                SizeType.Percent,
                22));

        root.RowStyles.Add(
            new RowStyle(
                SizeType.Percent,
                12));

        root.RowStyles.Add(
            new RowStyle(
                SizeType.Percent,
                15));

        root.RowStyles.Add(
            new RowStyle(
                SizeType.Absolute,
                0));

        _titleLabel =
            new Label
            {
                Text = "MISE À JOUR SIDERON",
                Dock = DockStyle.Fill,
                Font =
                    new Font(
                        "Segoe UI",
                        16F,
                        FontStyle.Bold),
                ForeColor =
                    Color.FromArgb(
                        225,
                        244,
                        252),
                TextAlign =
                    ContentAlignment.MiddleLeft,
            };

        _versionLabel =
            new Label
            {
                Text = "Préparation de la nouvelle version…",
                Dock = DockStyle.Fill,
                Font =
                    new Font(
                        "Segoe UI",
                        9F,
                        FontStyle.Regular),
                ForeColor =
                    Color.FromArgb(
                        114,
                        150,
                        169),
                TextAlign =
                    ContentAlignment.MiddleLeft,
            };

        _statusLabel =
            new Label
            {
                Text = "Initialisation…",
                Dock = DockStyle.Fill,
                Font =
                    new Font(
                        "Segoe UI",
                        10.5F,
                        FontStyle.Regular),
                ForeColor =
                    Color.FromArgb(
                        202,
                        226,
                        238),
                TextAlign =
                    ContentAlignment.BottomLeft,
            };

        var progressHost =
            new Panel
            {
                Dock = DockStyle.Fill,
                Padding =
                    new Padding(
                        0,
                        16,
                        0,
                        16),
                BackColor = BackColor,
            };

        _progressTrack =
            new RoundedPanel
            {
                Height = 10,
                Dock = DockStyle.Fill,
                BackColor =
                    Color.FromArgb(
                        25,
                        43,
                        55),
                CornerRadius = 5,
            };

        _progressFill =
            new RoundedPanel
            {
                Width = 0,
                Dock = DockStyle.Left,
                BackColor =
                    Color.FromArgb(
                        65,
                        206,
                        255),
                CornerRadius = 5,
            };

        _progressTrack.Controls.Add(
            _progressFill);

        progressHost.Controls.Add(
            _progressTrack);

        _percentLabel =
            new Label
            {
                Text = "0 %",
                Dock = DockStyle.Fill,
                Font =
                    new Font(
                        "Segoe UI",
                        9F,
                        FontStyle.Bold),
                ForeColor =
                    Color.FromArgb(
                        96,
                        211,
                        255),
                TextAlign =
                    ContentAlignment.MiddleRight,
            };

        _closeButton =
            new Button
            {
                Text = "Fermer",
                Width = 110,
                Height = 32,
                Anchor =
                    AnchorStyles.Right
                    | AnchorStyles.Top,
                Visible = false,
                FlatStyle =
                    FlatStyle.Flat,
                BackColor =
                    Color.FromArgb(
                        19,
                        35,
                        46),
                ForeColor =
                    Color.FromArgb(
                        226,
                        243,
                        251),
            };

        _closeButton.FlatAppearance.BorderColor =
            Color.FromArgb(
                53,
                108,
                134);

        _closeButton.Click +=
            (_, _) =>
            {
                Close();
            };

        var closeHost =
            new Panel
            {
                Dock = DockStyle.Fill,
                BackColor = BackColor,
            };

        closeHost.Controls.Add(
            _closeButton);

        _closeButton.Location =
            new Point(
                closeHost.Width
                    - _closeButton.Width,
                2);

        closeHost.Resize +=
            (_, _) =>
            {
                _closeButton.Height =
                    Math.Max(
                        1,
                        Math.Min(
                            32,
                            closeHost.ClientSize.Height - 2));

                _closeButton.Location =
                    new Point(
                        Math.Max(
                            0,
                            closeHost.ClientSize.Width
                                - _closeButton.Width),
                        Math.Max(
                            0,
                            (closeHost.ClientSize.Height - _closeButton.Height) / 2));
            };

        root.Controls.Add(
            _titleLabel,
            0,
            0);

        root.Controls.Add(
            _versionLabel,
            0,
            1);

        root.Controls.Add(
            _statusLabel,
            0,
            2);

        root.Controls.Add(
            progressHost,
            0,
            3);

        root.Controls.Add(
            _percentLabel,
            0,
            4);

        root.Controls.Add(
            closeHost,
            0,
            5);

        Controls.Add(
            root);

        _progressTrack.Resize +=
            (_, _) =>
            {
                ApplyProgressWidth(
                    ReadDisplayedPercent());
            };

        _pollTimer =
            new System.Windows.Forms.Timer
            {
                Interval = 150,
            };

        _pollTimer.Tick +=
            (_, _) =>
            {
                PollProgress();
            };

        Shown +=
            (_, _) =>
            {
                FitToCurrentScreen();
                _pollTimer.Start();
                PollProgress();
            };

        FormClosed +=
            (_, _) =>
            {
                _pollTimer.Stop();
                _pollTimer.Dispose();
            };
    }

    private void FitToCurrentScreen()
    {
        Rectangle workingArea =
            Screen.FromControl(this).WorkingArea;

        int maximumWidth =
            Math.Max(
                360,
                workingArea.Width - 24);

        int maximumHeight =
            Math.Max(
                220,
                workingArea.Height - 24);

        if (
            Width > maximumWidth
            || Height > maximumHeight
        )
        {
            float ratio =
                Math.Min(
                    maximumWidth / (float)Width,
                    maximumHeight / (float)Height);

            Scale(
                new SizeF(
                    ratio,
                    ratio));
        }

        Size =
            new Size(
                Math.Min(Width, maximumWidth),
                Math.Min(Height, maximumHeight));

        // MaximumSize doit être appliqué après Scale(). Sinon WinForms borne
        // d'abord la fenêtre mais agrandit encore ses contrôles pour le DPI,
        // ce qui rogne la dernière ligne et les boutons.
        MaximumSize =
            new Size(
                maximumWidth,
                maximumHeight);

        Location =
            new Point(
                workingArea.Left
                    + Math.Max(0, (workingArea.Width - Width) / 2),
                workingArea.Top
                    + Math.Max(0, (workingArea.Height - Height) / 2));
    }

    protected override void OnPaint(
        PaintEventArgs e)
    {
        base.OnPaint(e);

        using var pen =
            new Pen(
                Color.FromArgb(
                    53,
                    108,
                    134),
                1F);

        var rectangle =
            ClientRectangle;

        rectangle.Width -=
            1;

        rectangle.Height -=
            1;

        e.Graphics.DrawRectangle(
            pen,
            rectangle);
    }

    private void PollProgress()
    {
        if (_terminalStateSeen)
        {
            return;
        }

        try
        {
            if (!File.Exists(
                    _progressFile))
            {
                return;
            }

            var info =
                new FileInfo(
                    _progressFile);

            if (
                info.LastWriteTimeUtc
                    == _lastProgressWriteUtc
            )
            {
                return;
            }

            _lastProgressWriteUtc =
                info.LastWriteTimeUtc;

            string json =
                File.ReadAllText(
                    _progressFile);

            var progress =
                JsonSerializer.Deserialize<UpdateProgressState>(
                    json);

            if (progress is null)
            {
                return;
            }

            int percent =
                Math.Clamp(
                    progress.Percent,
                    0,
                    100);

            _percentLabel.Text =
                $"{percent} %";

            ApplyProgressWidth(
                percent);

            if (!string.IsNullOrWhiteSpace(
                    progress.TargetVersion))
            {
                _versionLabel.Text =
                    $"Installation d’Sideron {progress.TargetVersion}";
            }

            if (!string.IsNullOrWhiteSpace(
                    progress.Message))
            {
                _statusLabel.Text =
                    progress.Message;
            }

            if (string.Equals(
                    progress.State,
                    "failed",
                    StringComparison.OrdinalIgnoreCase))
            {
                _terminalStateSeen =
                    true;

                _titleLabel.Text =
                    "MISE À JOUR INTERROMPUE";

                _percentLabel.Text =
                    "Échec";

                _closeButton.Visible =
                    true;

                TopMost =
                    false;

                return;
            }

            if (
                percent >= 100
                && (
                    string.Equals(
                        progress.State,
                        "completed",
                        StringComparison.OrdinalIgnoreCase)
                    || string.Equals(
                        progress.State,
                        "restarted",
                        StringComparison.OrdinalIgnoreCase)
                )
            )
            {
                _terminalStateSeen =
                    true;

                _statusLabel.Text =
                    "Sideron a été mis à jour. Redémarrage…";

                _ = CloseAfterSuccessAsync();
            }
        }
        catch
        {
            // Une écriture peut être observée entre deux opérations atomiques.
            // On réessaie simplement au tick suivant.
        }
    }

    private async Task CloseAfterSuccessAsync()
    {
        await Task.Delay(
            1400);

        if (!IsDisposed)
        {
            BeginInvoke(
                new Action(
                    Close));
        }
    }

    private int ReadDisplayedPercent()
    {
        string text =
            _percentLabel.Text
                .Replace(
                    "%",
                    string.Empty)
                .Trim();

        return int.TryParse(
            text,
            out int value)
            ? Math.Clamp(
                value,
                0,
                100)
            : 0;
    }

    private void ApplyProgressWidth(
        int percent)
    {
        int available =
            Math.Max(
                0,
                _progressTrack.ClientSize.Width);

        _progressFill.Width =
            (int)Math.Round(
                available
                * (
                    percent
                    / 100.0));
    }
}

internal sealed class RoundedPanel : Panel
{
    public int CornerRadius { get; set; } = 6;

    protected override void OnSizeChanged(
        EventArgs e)
    {
        base.OnSizeChanged(e);
        UpdateRegion();
    }

    private void UpdateRegion()
    {
        if (
            Width <= 0
            || Height <= 0
        )
        {
            return;
        }

        int radius =
            Math.Max(
                1,
                Math.Min(
                    CornerRadius,
                    Math.Min(
                        Width,
                        Height)
                    / 2));

        int diameter =
            radius * 2;

        using var path =
            new GraphicsPath();

        path.AddArc(
            0,
            0,
            diameter,
            diameter,
            180,
            90);

        path.AddArc(
            Width - diameter,
            0,
            diameter,
            diameter,
            270,
            90);

        path.AddArc(
            Width - diameter,
            Height - diameter,
            diameter,
            diameter,
            0,
            90);

        path.AddArc(
            0,
            Height - diameter,
            diameter,
            diameter,
            90,
            90);

        path.CloseFigure();

        Region =
            new Region(
                path);
    }
}

internal sealed class UpdateProgressState
{
    [JsonPropertyName("target_version")]
    public string? TargetVersion { get; set; }

    [JsonPropertyName("percent")]
    public int Percent { get; set; }

    [JsonPropertyName("state")]
    public string? State { get; set; }

    [JsonPropertyName("message")]
    public string? Message { get; set; }
}
