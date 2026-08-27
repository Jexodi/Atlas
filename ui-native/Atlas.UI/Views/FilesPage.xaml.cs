using Atlas.UI.Services;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using IOPath = System.IO.Path;

namespace Atlas.UI.Views;

public sealed partial class FilesPage : Page
{
    private readonly AtlasConfigService
        _config;

    public FilesPage()
    {
        InitializeComponent();

        _config =
            new AtlasConfigService();

        Loaded +=
            (_, _) =>
            {
                RefreshFolders();
            };
    }

    private void RefreshFolders()
    {
        FolderList.Children.Clear();

        var atlasConfig =
            _config.Load();

        var root =
            atlasConfig.StorageRoot;

        WorkspacePathText.Text =
            root;

        string[] folders;

        try
        {
            folders =
                Directory
                    .EnumerateDirectories(
                        root,
                        "*",
                        SearchOption.TopDirectoryOnly)
                    .OrderBy(
                        path =>
                            IOPath.GetFileName(
                                path),
                        StringComparer
                            .CurrentCultureIgnoreCase)
                    .ToArray();
        }
        catch
        {
            folders =
                Array.Empty<string>();
        }

        if (folders.Length == 0)
        {
            FolderList.Children.Add(
                CreateEmptyState());

            return;
        }

        foreach (var folder in folders)
        {
            FolderList.Children.Add(
                CreateFolderRow(
                    folder));
        }
    }

    private static UIElement CreateEmptyState()
    {
        return new Border
        {
            Style =
                Application.Current.Resources[
                    "AtlasCardStyle"]
                as Style,
            Child =
                new TextBlock
                {
                    Text =
                        "Aucun dossier n’est disponible dans la zone de travail Atlas.",
                    TextWrapping =
                        TextWrapping.Wrap,
                    FontSize = 13,
                    Foreground =
                        Application.Current.Resources[
                            "AtlasSecondaryTextBrush"]
                        as Brush,
                },
        };
    }

    private static UIElement CreateFolderRow(
        string folder)
    {
        var name =
            IOPath.GetFileName(
                folder);

        var grid =
            new Grid();

        grid.ColumnDefinitions.Add(
            new ColumnDefinition
            {
                Width =
                    new GridLength(48),
            });

        grid.ColumnDefinitions.Add(
            new ColumnDefinition
            {
                Width =
                    new GridLength(
                        1,
                        GridUnitType.Star),
            });

        grid.ColumnDefinitions.Add(
            new ColumnDefinition
            {
                Width =
                    GridLength.Auto,
            });

        var icon =
            new FontIcon
            {
                Glyph = "\uE8B7",
                FontSize = 22,
                Foreground =
                    Application.Current.Resources[
                        "AtlasAccentBrush"]
                    as Brush,
                VerticalAlignment =
                    VerticalAlignment.Center,
            };

        Grid.SetColumn(
            icon,
            0);

        grid.Children.Add(
            icon);

        var textPanel =
            new StackPanel
            {
                Spacing = 2,
                VerticalAlignment =
                    VerticalAlignment.Center,
            };

        textPanel.Children.Add(
            new TextBlock
            {
                Text = name,
                FontSize = 15,
                FontWeight =
                    Microsoft.UI.Text
                        .FontWeights.SemiBold,
                Foreground =
                    Application.Current.Resources[
                        "AtlasTextBrush"]
                    as Brush,
            });

        textPanel.Children.Add(
            new TextBlock
            {
                Text = "DOSSIER",
                FontSize = 10,
                CharacterSpacing = 120,
                Foreground =
                    Application.Current.Resources[
                        "AtlasSecondaryTextBrush"]
                    as Brush,
            });

        Grid.SetColumn(
            textPanel,
            1);

        grid.Children.Add(
            textPanel);

        var chevron =
            new FontIcon
            {
                Glyph = "\uE76C",
                FontSize = 13,
                Opacity = 0.66,
                Foreground =
                    Application.Current.Resources[
                        "AtlasSecondaryTextBrush"]
                    as Brush,
                VerticalAlignment =
                    VerticalAlignment.Center,
            };

        Grid.SetColumn(
            chevron,
            2);

        grid.Children.Add(
            chevron);

        return new Border
        {
            Style =
                Application.Current.Resources[
                    "AtlasCardStyle"]
                as Style,
            Padding =
                new Thickness(
                    20,
                    15,
                    20,
                    15),
            Child =
                grid,
        };
    }
}
