using Atlas.UI.Services;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace Atlas.UI.Views;

public sealed partial class SettingsPage : Page
{
    private readonly AtlasConfigService
        _config;

    private readonly DisplayService
        _displayService;

    private readonly AtlasUpdateService
        _updateService;

    private AtlasUpdateConfiguration
        _updateConfiguration =
            AtlasUpdateConfiguration.Default;

    private bool _syncingUpdateChannel;

    public SettingsPage()
    {
        InitializeComponent();

        _config =
            new AtlasConfigService();

        _displayService =
            new DisplayService();

        _updateService =
            new AtlasUpdateService();

        Loaded +=
            async (_, _) =>
            {
                LoadSnapshot();
                await CheckUpdatesAsync();
            };
    }

    private void LoadSnapshot()
    {
        var atlasConfig =
            _config.Load();

        StorageValue.Text =
            atlasConfig.StorageRoot;

        var display =
            _displayService.ResolveDisplay(
                atlasConfig.ScreenId,
                atlasConfig.ScreenIndex);

        ScreenValue.Text =
            display is null
                ? "Non détecté"
                : display.DeviceName;

        _updateConfiguration =
            _config.LoadUpdateConfiguration();

        VersionValue.Text =
            _updateConfiguration.Version;

        _syncingUpdateChannel = true;
        UpdateChannelComboBox.Items.Clear();

        if (_updateConfiguration.Channel == "dev")
        {
            UpdateChannelComboBox.Items.Add(
                new ComboBoxItem { Content = "DEV", Tag = "dev" });
            UpdateChannelComboBox.SelectedIndex = 0;
            UpdateChannelComboBox.IsEnabled = false;
        }
        else
        {
            UpdateChannelComboBox.Items.Add(
                new ComboBoxItem { Content = "Experimental", Tag = "rc" });
            UpdateChannelComboBox.Items.Add(
                new ComboBoxItem { Content = "Release", Tag = "release" });
            UpdateChannelComboBox.SelectedIndex =
                _updateConfiguration.Channel == "rc" ? 0 : 1;
            UpdateChannelComboBox.IsEnabled = true;
        }

        _syncingUpdateChannel = false;

        UpdateSourceValue.Text =
            string.IsNullOrWhiteSpace(
                _updateConfiguration.ManifestUrl)
                ? "Non configurée"
                : _updateConfiguration.ManifestUrl;

        UpdateStatusValue.Text =
            _updateConfiguration.Enabled
                ? "Non vérifié"
                : "Mises à jour désactivées";

        AvailableVersionValue.Text =
            "—";

        UpdateNotesValue.Text =
            string.Empty;

        UpdateNotesValue.Visibility =
            Visibility.Collapsed;
    }

    private async void UpdateChannelComboBox_SelectionChanged(
        object sender,
        SelectionChangedEventArgs e)
    {
        if (_syncingUpdateChannel
            || UpdateChannelComboBox.SelectedItem is not ComboBoxItem item
            || item.Tag is not string channel)
        {
            return;
        }

        _updateConfiguration = _config.SaveUpdateChannel(channel);
        UpdateSourceValue.Text = _updateConfiguration.ManifestUrl;
        await CheckUpdatesAsync();
    }

    private async Task CheckUpdatesAsync()
    {

        UpdateProgress.IsActive =
            true;

        UpdateProgress.Visibility =
            Visibility.Visible;

        UpdateStatusValue.Text =
            "Vérification en cours…";

        AvailableVersionValue.Text =
            "—";

        UpdateNotesValue.Visibility =
            Visibility.Collapsed;

        try
        {
            _updateConfiguration =
                _config.LoadUpdateConfiguration();

            var options =
                new AtlasUpdateOptions(
                    _updateConfiguration.Enabled,
                    _updateConfiguration.Channel,
                    _updateConfiguration.CheckOnStartup,
                    _updateConfiguration.ManifestUrl);

            var result =
                await _updateService.CheckAsync(
                    _updateConfiguration.Version,
                    options);

            UpdateStatusValue.Text =
                result.Message;

            AvailableVersionValue.Text =
                result.Manifest?.Version
                ?? "—";

            UpdateSourceValue.Text =
                string.IsNullOrWhiteSpace(
                    _updateConfiguration.ManifestUrl)
                    ? "Non configurée"
                    : _updateConfiguration.ManifestUrl;

            var notes =
                result.Manifest?.Notes;

            if (!string.IsNullOrWhiteSpace(
                    notes))
            {
                UpdateNotesValue.Text =
                    notes;

                UpdateNotesValue.Visibility =
                    Visibility.Visible;
            }
        }
        catch (HttpRequestException exception)
        {
            UpdateStatusValue.Text =
                $"Impossible de contacter le serveur de mise à jour : {exception.Message}";

            UiLog.Error(
                "Atlas update HTTP check failed.",
                exception);
        }
        catch (TaskCanceledException exception)
        {
            UpdateStatusValue.Text =
                "La vérification des mises à jour a expiré.";

            UiLog.Error(
                "Atlas update check timed out.",
                exception);
        }
        catch (Exception exception)
        {
            UpdateStatusValue.Text =
                $"Échec de la vérification : {exception.Message}";

            UiLog.Error(
                "Atlas update check failed.",
                exception);
        }
        finally
        {
            UpdateProgress.IsActive =
                false;

            UpdateProgress.Visibility =
                Visibility.Collapsed;

        }
    }
}
