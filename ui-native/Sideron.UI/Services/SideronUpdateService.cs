using System.Net.Http;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Sideron.UI.Services;

public sealed class SideronUpdateService
{
    private static readonly HttpClient SharedHttpClient = new()
    {
        Timeout = TimeSpan.FromSeconds(15),
    };

    private readonly HttpClient HttpClient;

    public SideronUpdateService(HttpClient? client = null)
    {
        HttpClient = client ?? SharedHttpClient;
    }

    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNameCaseInsensitive = true,
    };

    public async Task<SideronUpdateCheckResult> CheckAsync(
        string currentVersion,
        SideronUpdateOptions options,
        CancellationToken cancellationToken = default)
    {
        if (!options.Enabled)
        {
            return SideronUpdateCheckResult.Disabled(currentVersion);
        }

        if (string.IsNullOrWhiteSpace(options.ManifestUrl))
        {
            return SideronUpdateCheckResult.NotConfigured(currentVersion);
        }

        using var response = await HttpClient.GetAsync(
            options.ManifestUrl,
            HttpCompletionOption.ResponseHeadersRead,
            cancellationToken);

        response.EnsureSuccessStatusCode();

        await using var stream = await response.Content.ReadAsStreamAsync(
            cancellationToken);

        var manifest = await JsonSerializer.DeserializeAsync<SideronUpdateManifest>(
            stream,
            JsonOptions,
            cancellationToken);

        if (manifest is null)
        {
            throw new InvalidDataException(
                "Le manifeste de mise à jour Sideron est vide ou invalide.");
        }

        if (string.IsNullOrWhiteSpace(manifest.Version))
        {
            throw new InvalidDataException(
                "Le manifeste de mise à jour Sideron ne contient aucune version.");
        }

        if (!string.Equals(
                manifest.Channel,
                options.Channel,
                StringComparison.OrdinalIgnoreCase))
        {
            return SideronUpdateCheckResult.ChannelMismatch(
                currentVersion,
                manifest);
        }

        var current = SideronSemanticVersion.Parse(currentVersion);
        var available = SideronSemanticVersion.Parse(manifest.Version);

        if (options.Channel.Equals("release", StringComparison.OrdinalIgnoreCase))
        {
            if (available.Stage != SideronReleaseStage.Release)
                throw new InvalidDataException("Le manifeste Release ne contient pas une version stable.");
            if (available <= current)
                return new SideronUpdateCheckResult(SideronUpdateStatus.ReinstallAvailable,
                    currentVersion, manifest, $"La Release {manifest.Version} peut être réinstallée ou restaurée.");
        }
        if (options.Channel.Equals("rc", StringComparison.OrdinalIgnoreCase))
        {
            if (available.Stage != SideronReleaseStage.ReleaseCandidate)
                throw new InvalidDataException("Le manifeste Experimental ne contient pas une RC.");
            // Fail closed if the stable reference cannot be fetched or validated.
            var stableUri = new Uri(new Uri(options.ManifestUrl), "release.json");
            using var stableResponse = await HttpClient.GetAsync(stableUri, cancellationToken);
            stableResponse.EnsureSuccessStatusCode();
            await using var stableStream = await stableResponse.Content.ReadAsStreamAsync(cancellationToken);
            var stable = await JsonSerializer.DeserializeAsync<SideronUpdateManifest>(stableStream, JsonOptions, cancellationToken);
            if (stable is null || !string.Equals(stable.Channel, "release", StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException("Référence Release absente ou invalide : téléchargement RC bloqué.");
            var stableVersion = SideronSemanticVersion.Parse(stable.Version);
            if (stableVersion.Stage != SideronReleaseStage.Release)
                throw new InvalidDataException("La référence Release doit être stable.");
            if (available <= stableVersion)
                return new SideronUpdateCheckResult(SideronUpdateStatus.UpToDate, currentVersion, manifest,
                    $"Experimental {manifest.Version} n’est pas supérieur à la Release {stable.Version}. Téléchargement désactivé.");
        }

        if (available <= current)
        {
            return SideronUpdateCheckResult.UpToDate(
                currentVersion,
                manifest);
        }

        return SideronUpdateCheckResult.UpdateAvailable(
            currentVersion,
            manifest);
    }

    public async Task<SideronUpdateDownloadResult> VerifyDownloadedFileAsync(
        SideronUpdateManifest manifest,
        string filePath,
        CancellationToken cancellationToken = default)
    {
        if (string.IsNullOrWhiteSpace(filePath) || !File.Exists(filePath))
        {
            throw new FileNotFoundException(
                "Le fichier de mise à jour Sideron est introuvable.",
                filePath);
        }

        if (string.IsNullOrWhiteSpace(manifest.Sha256))
        {
            throw new InvalidDataException(
                "Le manifeste Sideron ne contient aucun SHA-256.");
        }

        byte[] expectedHash;

        try
        {
            expectedHash = Convert.FromHexString(manifest.Sha256.Trim());
        }
        catch (FormatException exception)
        {
            throw new InvalidDataException(
                "Le SHA-256 du manifeste Sideron n'est pas valide.",
                exception);
        }

        if (expectedHash.Length != 32)
        {
            throw new InvalidDataException(
                "Le SHA-256 du manifeste Sideron doit contenir 64 caractères hexadécimaux.");
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

        return new SideronUpdateDownloadResult(
            filePath,
            Convert.ToHexString(actualHash),
            new FileInfo(filePath).Length);
    }

    public async Task<SideronUpdateDownloadResult> DownloadAsync(
        SideronUpdateManifest manifest,
        IProgress<double>? progress = null,
        CancellationToken cancellationToken = default)
    {
        if (string.IsNullOrWhiteSpace(
                manifest.Version))
        {
            throw new InvalidDataException(
                "La version de la mise à jour Sideron est absente.");
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
                "L'URL de téléchargement Sideron doit utiliser HTTPS.");
        }

        if (string.IsNullOrWhiteSpace(
                manifest.Sha256))
        {
            throw new InvalidDataException(
                "Le manifeste Sideron ne contient aucun SHA-256.");
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
                "Le SHA-256 du manifeste Sideron n'est pas valide.",
                exception);
        }

        if (expectedHash.Length != 32)
        {
            throw new InvalidDataException(
                "Le SHA-256 du manifeste Sideron doit contenir 64 caractères hexadécimaux.");
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
                $"Sideron-{manifest.Version}.exe";
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
                "SIDERON",
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

            return new SideronUpdateDownloadResult(
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

public sealed record SideronUpdateOptions(
    bool Enabled,
    string Channel,
    bool CheckOnStartup,
    string ManifestUrl);

public sealed record SideronUpdateDownloadResult(
    string FilePath,
    string Sha256,
    long SizeBytes);


public sealed class SideronUpdateManifest
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

public sealed record SideronUpdateCheckResult(
    SideronUpdateStatus Status,
    string CurrentVersion,
    SideronUpdateManifest? Manifest,
    string Message)
{
    public static SideronUpdateCheckResult Disabled(
        string currentVersion)
        => new(
            SideronUpdateStatus.Disabled,
            currentVersion,
            null,
            "Les mises à jour Sideron sont désactivées.");

    public static SideronUpdateCheckResult NotConfigured(
        string currentVersion)
        => new(
            SideronUpdateStatus.NotConfigured,
            currentVersion,
            null,
            "Aucune source de mise à jour Sideron n'est encore configurée.");

    public static SideronUpdateCheckResult ChannelMismatch(
        string currentVersion,
        SideronUpdateManifest manifest)
        => new(
            SideronUpdateStatus.ChannelMismatch,
            currentVersion,
            manifest,
            "Le manifeste appartient à un autre canal Sideron.");

    public static SideronUpdateCheckResult UpToDate(
        string currentVersion,
        SideronUpdateManifest manifest)
        => new(
            SideronUpdateStatus.UpToDate,
            currentVersion,
            manifest,
            "Sideron est à jour.");

    public static SideronUpdateCheckResult UpdateAvailable(
        string currentVersion,
        SideronUpdateManifest manifest)
        => new(
            SideronUpdateStatus.UpdateAvailable,
            currentVersion,
            manifest,
            $"Sideron {manifest.Version} est disponible.");
}

public enum SideronUpdateStatus
{
    Disabled,
    NotConfigured,
    ChannelMismatch,
    UpToDate,
    UpdateAvailable,
    ReinstallAvailable,
}

internal readonly record struct SideronSemanticVersion(
    int Major,
    int Minor,
    int Patch,
    SideronReleaseStage Stage,
    int StageNumber) : IComparable<SideronSemanticVersion>
{
    public static SideronSemanticVersion Parse(
        string value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            throw new FormatException("Version Sideron vide.");
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
                $"Version Sideron invalide : {value}");
        }

        if (mainAndSuffix.Length == 1)
        {
            return new(
                major,
                minor,
                patch,
                SideronReleaseStage.Release,
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
                SideronReleaseStage.Dev,
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
                SideronReleaseStage.ReleaseCandidate,
                rcNumber);
        }

        throw new FormatException(
            $"Suffixe de version Sideron invalide : {value}");
    }

    public int CompareTo(
        SideronSemanticVersion other)
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
        SideronSemanticVersion left,
        SideronSemanticVersion right)
        => left.CompareTo(right) <= 0;

    public static bool operator >=(
        SideronSemanticVersion left,
        SideronSemanticVersion right)
        => left.CompareTo(right) >= 0;
}

internal enum SideronReleaseStage
{
    Dev = 0,
    ReleaseCandidate = 1,
    Release = 2,
}
