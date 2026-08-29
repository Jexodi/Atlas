using System.Globalization;
using IOPath = System.IO.Path;

namespace Sideron.UI.Services;

public sealed class WorkspaceFileService
{
    private readonly string _workspaceRoot;

    public WorkspaceFileService(
        string workspaceRoot)
    {
        if (string.IsNullOrWhiteSpace(
                workspaceRoot))
        {
            throw new ArgumentException(
                "La zone Sideron est vide.",
                nameof(workspaceRoot));
        }

        _workspaceRoot =
            NormalizeDirectory(
                workspaceRoot);
    }

    public string WorkspaceRoot =>
        _workspaceRoot;

    public string NormalizeInsideWorkspace(
        string path)
    {
        var full =
            IOPath.GetFullPath(
                path);

        if (!IsInsideWorkspace(
                full))
        {
            throw new InvalidOperationException(
                "Cette opération sortirait de la zone Sideron.");
        }

        return full;
    }

    public bool IsInsideWorkspace(
        string path)
    {
        var full =
            IOPath.GetFullPath(
                path);

        if (string.Equals(
                full,
                _workspaceRoot,
                StringComparison.OrdinalIgnoreCase))
        {
            return true;
        }

        var prefix =
            _workspaceRoot.EndsWith(
                IOPath.DirectorySeparatorChar)
                ? _workspaceRoot
                : _workspaceRoot
                  + IOPath.DirectorySeparatorChar;

        return full.StartsWith(
            prefix,
            StringComparison.OrdinalIgnoreCase);
    }

    public string CreateFolder(
        string parentDirectory,
        string requestedName)
    {
        var parent =
            NormalizeInsideWorkspace(
                parentDirectory);

        EnsureDirectory(
            parent);

        var name =
            SanitizeName(
                requestedName);

        var target =
            NormalizeInsideWorkspace(
                IOPath.Combine(
                    parent,
                    name));

        if (
            Directory.Exists(
                target)
            || File.Exists(
                target)
        )
        {
            throw new IOException(
                "Un élément portant ce nom existe déjà.");
        }

        Directory.CreateDirectory(
            target);

        return target;
    }

    public string Rename(
        string source,
        string requestedName)
    {
        var current =
            NormalizeInsideWorkspace(
                source);

        if (string.Equals(
                current,
                _workspaceRoot,
                StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidOperationException(
                "La racine Sideron ne peut pas être renommée.");
        }

        var parent =
            IOPath.GetDirectoryName(
                current);

        if (string.IsNullOrWhiteSpace(
                parent))
        {
            throw new InvalidOperationException(
                "Impossible de déterminer le dossier parent.");
        }

        var name =
            SanitizeName(
                requestedName);

        var target =
            NormalizeInsideWorkspace(
                IOPath.Combine(
                    parent,
                    name));

        if (
            Directory.Exists(
                target)
            || File.Exists(
                target)
        )
        {
            throw new IOException(
                "Un élément portant ce nom existe déjà.");
        }

        if (Directory.Exists(
                current))
        {
            Directory.Move(
                current,
                target);

            return target;
        }

        if (File.Exists(
                current))
        {
            File.Move(
                current,
                target);

            return target;
        }

        throw new FileNotFoundException(
            "L’élément à renommer n’existe plus.",
            current);
    }

    public void Delete(
        IEnumerable<string> paths)
    {
        foreach (var raw in paths)
        {
            var path =
                NormalizeInsideWorkspace(
                    raw);

            if (string.Equals(
                    path,
                    _workspaceRoot,
                    StringComparison.OrdinalIgnoreCase))
            {
                throw new InvalidOperationException(
                    "La racine Sideron ne peut pas être supprimée.");
            }

            if (Directory.Exists(
                    path))
            {
                Directory.Delete(
                    path,
                    true);

                continue;
            }

            if (File.Exists(
                    path))
            {
                File.Delete(
                    path);
            }
        }
    }

    public IReadOnlyList<string> CopyIntoDirectory(
        IEnumerable<string> sources,
        string destinationDirectory,
        bool move)
    {
        var destination =
            NormalizeInsideWorkspace(
                destinationDirectory);

        EnsureDirectory(
            destination);

        var created =
            new List<string>();

        foreach (var rawSource in sources)
        {
            var source =
                NormalizeInsideWorkspace(
                    rawSource);

            if (string.Equals(
                    source,
                    _workspaceRoot,
                    StringComparison.OrdinalIgnoreCase))
            {
                throw new InvalidOperationException(
                    "La racine Sideron ne peut pas être copiée ou déplacée.");
            }

            var name =
                IOPath.GetFileName(
                    source);

            var target =
                GetAvailableTarget(
                    destination,
                    name);

            if (Directory.Exists(
                    source))
            {
                if (move)
                {
                    Directory.Move(
                        source,
                        target);
                }
                else
                {
                    CopyDirectory(
                        source,
                        target);
                }

                created.Add(
                    target);

                continue;
            }

            if (File.Exists(
                    source))
            {
                if (move)
                {
                    File.Move(
                        source,
                        target);
                }
                else
                {
                    File.Copy(
                        source,
                        target,
                        false);
                }

                created.Add(
                    target);
            }
        }

        return created;
    }

    private string GetAvailableTarget(
        string destination,
        string name)
    {
        var first =
            NormalizeInsideWorkspace(
                IOPath.Combine(
                    destination,
                    name));

        if (
            !Directory.Exists(
                first)
            && !File.Exists(
                first)
        )
        {
            return first;
        }

        var stem =
            IOPath.GetFileNameWithoutExtension(
                name);

        var extension =
            IOPath.GetExtension(
                name);

        for (
            var index = 2;
            index < 10_000;
            index++
        )
        {
            var candidateName =
                string.Create(
                    CultureInfo.InvariantCulture,
                    $"{stem} - Copie {index}{extension}");

            var candidate =
                NormalizeInsideWorkspace(
                    IOPath.Combine(
                        destination,
                        candidateName));

            if (
                !Directory.Exists(
                    candidate)
                && !File.Exists(
                    candidate)
            )
            {
                return candidate;
            }
        }

        throw new IOException(
            "Impossible de trouver un nom disponible.");
    }

    private static void CopyDirectory(
        string source,
        string destination)
    {
        Directory.CreateDirectory(
            destination);

        foreach (
            var file
            in Directory.EnumerateFiles(
                source)
        )
        {
            var target =
                IOPath.Combine(
                    destination,
                    IOPath.GetFileName(
                        file));

            File.Copy(
                file,
                target,
                false);
        }

        foreach (
            var directory
            in Directory.EnumerateDirectories(
                source)
        )
        {
            var target =
                IOPath.Combine(
                    destination,
                    IOPath.GetFileName(
                        directory));

            CopyDirectory(
                directory,
                target);
        }
    }

    private static string SanitizeName(
        string requestedName)
    {
        var name =
            requestedName.Trim();

        if (string.IsNullOrWhiteSpace(
                name))
        {
            throw new ArgumentException(
                "Le nom ne peut pas être vide.");
        }

        if (
            name == "."
            || name == ".."
        )
        {
            throw new ArgumentException(
                "Nom invalide.");
        }

        if (
            name.IndexOfAny(
                IOPath.GetInvalidFileNameChars())
            >= 0
        )
        {
            throw new ArgumentException(
                "Le nom contient des caractères interdits.");
        }

        return name;
    }

    private static string NormalizeDirectory(
        string path)
    {
        var full =
            IOPath.GetFullPath(
                path);

        return IOPath.TrimEndingDirectorySeparator(
            full);
    }

    private static void EnsureDirectory(
        string path)
    {
        if (!Directory.Exists(
                path))
        {
            throw new DirectoryNotFoundException(
                path);
        }
    }
}
