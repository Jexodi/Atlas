using System.Net.Http;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Atlas.UI.Services;

public sealed class AtlasUpdateService
{
    private static readonly HttpClient HttpClient = new()
    {
        Timeout = TimeSpan.FromSeconds(15),
    };

    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNameCaseInsensitive = true,
    };

    public async Task<AtlasUpdateCheckResult> CheckAsync(
        string currentVersion,
        AtlasUpdateOptions options,
        CancellationToken cancellationToken = default)
    {
        if (!options.Enabled)
        {
            return AtlasUpdateCheckResult.Disabled(currentVersion);
        }

        if (string.IsNullOrWhiteSpace(options.ManifestUrl))
        {
            return AtlasUpdateCheckResult.NotConfigured(currentVersion);
        }

        using var response = await HttpClient.GetAsync(
            options.ManifestUrl,
            HttpCompletionOption.ResponseHeadersRead,
            cancellationToken);

        response.EnsureSuccessStatusCode();

        await using var stream = await response.Content.ReadAsStreamAsync(
            cancellationToken);

        var manifest = await JsonSerializer.DeserializeAsync<AtlasUpdateManifest>(
            stream,
            JsonOptions,
            cancellationToken);

        if (manifest is null)
        {
            throw new InvalidDataException(
                "Le manifeste de mise à jour Atlas est vide ou invalide.");
        }

        if (string.IsNullOrWhiteSpace(manifest.Version))
        {
            throw new InvalidDataException(
                "Le manifeste de mise à jour Atlas ne contient aucune version.");
        }

        if (!string.Equals(
                manifest.Channel,
                options.Channel,
                StringComparison.OrdinalIgnoreCase))
        {
            return AtlasUpdateCheckResult.ChannelMismatch(
                currentVersion,
                manifest);
        }

        var current = AtlasSemanticVersion.Parse(currentVersion);
        var available = AtlasSemanticVersion.Parse(manifest.Version);

        if (available <= current)
        {
            return AtlasUpdateCheckResult.UpToDate(
                currentVersion,
                manifest);
        }

        return AtlasUpdateCheckResult.UpdateAvailable(
            currentVersion,
            manifest);
    }

    public async Task<AtlasUpdateDownloadResult> VerifyDownloadedFileAsync(
        AtlasUpdateManifest manifest,
        string filePath,
        CancellationToken cancellationToken = default)
    {
        if (string.IsNullOrWhiteSpace(filePath) || !File.Exists(filePath))
        {
            throw new FileNotFoundException(
                "Le fichier de mise à jour Atlas est introuvable.",
                filePath);
        }

        if (string.IsNullOrWhiteSpace(manifest.Sha256))
        {
            throw new InvalidDataException(
                "Le manifeste Atlas ne contient aucun SHA-256.");
        }

        byte[] expectedHash;

        try
        {
            expectedHash = Convert.FromHexString(manifest.Sha256.Trim());
        }
        catch (FormatException exception)
        {
            throw new InvalidDataException(
                "Le SHA-256 du manifeste Atlas n'est pas valide.",
                exception);
        }

        if (expectedHash.Length != 32)
        {
            throw new InvalidDataException(
                "Le SHA-256 du manifeste Atlas doit contenir 64 caractères hexadécimaux.");
        }

        byte[] actualHash;

        await using (var downloadedFile = new FileStream(
            filePath,
            FileMode.Open,
            FileAccess.Read,
            FileShare.Read,
            128 * 1024,
            FileOptions.Asynchronous | FileOptions.SequentialScan))
        {
            actualHash = await SHA256.HashDataAsync(
                downloadedFile,
                cancellationToken);
        }

        if (!CryptographicOperations.FixedTimeEquals(expectedHash, actualHash))
        {
            throw new InvalidDataException(
                "Le SHA-256 du fichier téléchargé ne correspond plus au manifeste. L'installation a été bloquée.");
        }

        return new AtlasUpdateDownloadResult(
            filePath,
            Convert.ToHexString(actualHash),
            new FileInfo(filePath).Length);
    }

    public async Task<AtlasUpdateDownloadResult> DownloadAsync(
        AtlasUpdateManifest manifest,
        IProgress<double>? progress = null,
        CancellationToken cancellationToken = default)
    {
        if (string.IsNullOrWhiteSpace(
                manifest.Version))
        {
            throw new InvalidDataException(
                "La version de la mise à jour Atlas est absente.");
        }

        if (
            !Uri.TryCreate(
                manifest.DownloadUrl,
                UriKind.Absolute,
                out var downloadUri)
            || downloadUri.Scheme
                != Uri.UriSchemeHttps
        )
        {
            throw new InvalidDataException(
                "L'URL de téléchargement Atlas doit utiliser HTTPS.");
        }

        if (string.IsNullOrWhiteSpace(
                manifest.Sha256))
        {
            throw new InvalidDataException(
                "Le manifeste Atlas ne contient aucun SHA-256.");
        }

        byte[] expectedHash;

        try
        {
            expectedHash =
                Convert.FromHexString(
                    manifest.Sha256.Trim());
        }
        catch (FormatException exception)
        {
            throw new InvalidDataException(
                "Le SHA-256 du manifeste Atlas n'est pas valide.",
                exception);
        }

        if (expectedHash.Length != 32)
        {
            throw new InvalidDataException(
                "Le SHA-256 du manifeste Atlas doit contenir 64 caractères hexadécimaux.");
        }

        var fileName =
            Path.GetFileName(
                downloadUri.LocalPath);

        if (
            string.IsNullOrWhiteSpace(
                fileName)
            || !fileName.EndsWith(
                ".exe",
                StringComparison.OrdinalIgnoreCase)
        )
        {
            fileName =
                $"Atlas-{manifest.Version}.exe";
        }

        foreach (
            var invalidCharacter
            in Path.GetInvalidFileNameChars())
        {
            fileName =
                fileName.Replace(
                    invalidCharacter,
                    '_');
        }

        var downloadDirectory =
            Path.Combine(
                Environment.GetFolderPath(
                    Environment.SpecialFolder.LocalApplicationData),
                "Atlas",
                "updates",
                "downloads");

        Directory.CreateDirectory(
            downloadDirectory);

        var destinationPath =
            Path.Combine(
                downloadDirectory,
                fileName);

        var temporaryPath =
            destinationPath
            + ".part";

        if (File.Exists(
                temporaryPath))
        {
            File.Delete(
                temporaryPath);
        }

        try
        {
            using var response =
                await HttpClient.GetAsync(
                    downloadUri,
                    HttpCompletionOption.ResponseHeadersRead,
                    cancellationToken);

            response.EnsureSuccessStatusCode();

            var expectedLength =
                response.Content.Headers.ContentLength;

            await using (
                var source =
                    await response.Content.ReadAsStreamAsync(
                        cancellationToken)
            )
            await using (
                var destination =
                    new FileStream(
                        temporaryPath,
                        FileMode.CreateNew,
                        FileAccess.Write,
                        FileShare.None,
                        128 * 1024,
                        FileOptions.Asynchronous
                        | FileOptions.SequentialScan)
            )
            {
                var buffer =
                    new byte[
                        128 * 1024
                    ];

                long totalRead =
                    0;

                while (true)
                {
                    var read =
                        await source.ReadAsync(
                            buffer.AsMemory(
                                0,
                                buffer.Length),
                            cancellationToken);

                    if (read <= 0)
                    {
                        break;
                    }

                    await destination.WriteAsync(
                        buffer.AsMemory(
                            0,
                            read),
                        cancellationToken);

                    totalRead +=
                        read;

                    if (
                        expectedLength is > 0
                    )
                    {
                        progress?.Report(
                            Math.Clamp(
                                totalRead
                                * 100.0
                                / expectedLength.Value,
                                0,
                                100));
                    }
                }

                await destination.FlushAsync(
                    cancellationToken);
            }

            byte[] actualHash;

            await using (
                var downloadedFile =
                    new FileStream(
                        temporaryPath,
                        FileMode.Open,
                        FileAccess.Read,
                        FileShare.Read,
                        128 * 1024,
                        FileOptions.Asynchronous
                        | FileOptions.SequentialScan)
            )
            {
                actualHash =
                    await SHA256.HashDataAsync(
                        downloadedFile,
                        cancellationToken);
            }

            if (
                !CryptographicOperations.FixedTimeEquals(
                    expectedHash,
                    actualHash)
            )
            {
                throw new InvalidDataException(
                    "Le SHA-256 du fichier téléchargé ne correspond pas au manifeste. Le fichier a été rejeté.");
            }

            File.Move(
                temporaryPath,
                destinationPath,
                true);

            progress?.Report(
                100);

            return new AtlasUpdateDownloadResult(
                destinationPath,
                Convert.ToHexString(
                    actualHash),
                new FileInfo(
                    destinationPath).Length);
        }
        catch
        {
            try
            {
                if (File.Exists(
                        temporaryPath))
                {
                    File.Delete(
                        temporaryPath);
                }
            }
            catch
            {
                // Le fichier incomplet ne doit jamais masquer l'erreur initiale.
            }

            throw;
        }
    }
}

public sealed record AtlasUpdateOptions(
    bool Enabled,
    string Channel,
    bool CheckOnStartup,
    string ManifestUrl);

public sealed record AtlasUpdateDownloadResult(
    string FilePath,
    string Sha256,
    long SizeBytes);


public sealed class AtlasUpdateManifest
{
    [JsonPropertyName("version")]
    public string Version { get; init; } = string.Empty;

    [JsonPropertyName("channel")]
    public string Channel { get; init; } = string.Empty;

    [JsonPropertyName("url")]
    public string DownloadUrl { get; init; } = string.Empty;

    [JsonPropertyName("sha256")]
    public string Sha256 { get; init; } = string.Empty;

    [JsonPropertyName("notes")]
    public string Notes { get; init; } = string.Empty;

    [JsonPropertyName("published_utc")]
    public DateTimeOffset? PublishedUtc { get; init; }
}

public sealed record AtlasUpdateCheckResult(
    AtlasUpdateStatus Status,
    string CurrentVersion,
    AtlasUpdateManifest? Manifest,
    string Message)
{
    public static AtlasUpdateCheckResult Disabled(
        string currentVersion)
        => new(
            AtlasUpdateStatus.Disabled,
            currentVersion,
            null,
            "Les mises à jour Atlas sont désactivées.");

    public static AtlasUpdateCheckResult NotConfigured(
        string currentVersion)
        => new(
            AtlasUpdateStatus.NotConfigured,
            currentVersion,
            null,
            "Aucune source de mise à jour Atlas n'est encore configurée.");

    public static AtlasUpdateCheckResult ChannelMismatch(
        string currentVersion,
        AtlasUpdateManifest manifest)
        => new(
            AtlasUpdateStatus.ChannelMismatch,
            currentVersion,
            manifest,
            "Le manifeste appartient à un autre canal Atlas.");

    public static AtlasUpdateCheckResult UpToDate(
        string currentVersion,
        AtlasUpdateManifest manifest)
        => new(
            AtlasUpdateStatus.UpToDate,
            currentVersion,
            manifest,
            "Atlas est à jour.");

    public static AtlasUpdateCheckResult UpdateAvailable(
        string currentVersion,
        AtlasUpdateManifest manifest)
        => new(
            AtlasUpdateStatus.UpdateAvailable,
            currentVersion,
            manifest,
            $"Atlas {manifest.Version} est disponible.");
}

public enum AtlasUpdateStatus
{
    Disabled,
    NotConfigured,
    ChannelMismatch,
    UpToDate,
    UpdateAvailable,
}

internal readonly record struct AtlasSemanticVersion(
    int Major,
    int Minor,
    int Patch,
    AtlasReleaseStage Stage,
    int StageNumber) : IComparable<AtlasSemanticVersion>
{
    public static AtlasSemanticVersion Parse(
        string value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            throw new FormatException("Version Atlas vide.");
        }

        var normalized = value.Trim();

        var mainAndSuffix = normalized.Split(
            '-',
            2,
            StringSplitOptions.RemoveEmptyEntries);

        var numbers = mainAndSuffix[0].Split('.');

        if (numbers.Length != 3
            || !int.TryParse(numbers[0], out var major)
            || !int.TryParse(numbers[1], out var minor)
            || !int.TryParse(numbers[2], out var patch))
        {
            throw new FormatException(
                $"Version Atlas invalide : {value}");
        }

        if (mainAndSuffix.Length == 1)
        {
            return new(
                major,
                minor,
                patch,
                AtlasReleaseStage.Release,
                0);
        }

        var suffix = mainAndSuffix[1];

        if (suffix.Equals(
                "dev",
                StringComparison.OrdinalIgnoreCase))
        {
            return new(
                major,
                minor,
                patch,
                AtlasReleaseStage.Dev,
                0);
        }

        if (suffix.StartsWith(
                "rc.",
                StringComparison.OrdinalIgnoreCase)
            && int.TryParse(
                suffix[3..],
                out var rcNumber))
        {
            return new(
                major,
                minor,
                patch,
                AtlasReleaseStage.ReleaseCandidate,
                rcNumber);
        }

        throw new FormatException(
            $"Suffixe de version Atlas invalide : {value}");
    }

    public int CompareTo(
        AtlasSemanticVersion other)
    {
        var result = Major.CompareTo(other.Major);

        if (result != 0)
        {
            return result;
        }

        result = Minor.CompareTo(other.Minor);

        if (result != 0)
        {
            return result;
        }

        result = Patch.CompareTo(other.Patch);

        if (result != 0)
        {
            return result;
        }

        result = Stage.CompareTo(other.Stage);

        if (result != 0)
        {
            return result;
        }

        return StageNumber.CompareTo(other.StageNumber);
    }

    public static bool operator <=(
        AtlasSemanticVersion left,
        AtlasSemanticVersion right)
        => left.CompareTo(right) <= 0;

    public static bool operator >=(
        AtlasSemanticVersion left,
        AtlasSemanticVersion right)
        => left.CompareTo(right) >= 0;
}

internal enum AtlasReleaseStage
{
    Dev = 0,
    ReleaseCandidate = 1,
    Release = 2,
}
