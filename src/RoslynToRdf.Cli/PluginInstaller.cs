using System.Text.Json;

namespace RoslynToRdf.Cli;

/// <summary>Installs the bundled Claude Code and Codex plugin into a target repository.</summary>
public static class PluginInstaller
{
    private const string PluginDirectoryName = "roslyn-graph";

    /// <summary>The plugin bundle is copied alongside the NuGet tool executable.</summary>
    public static string BundledPluginDirectory => Path.Combine(AppContext.BaseDirectory, PluginDirectoryName);

    public static int Install(
        DirectoryInfo target,
        bool claude,
        bool codex,
        bool dryRun,
        TextWriter output,
        TextWriter error,
        string? sourceDirectory = null)
    {
        ArgumentNullException.ThrowIfNull(target);
        ArgumentNullException.ThrowIfNull(output);
        ArgumentNullException.ThrowIfNull(error);

        // No selector means install the plugin for both hosts.
        if (!claude && !codex)
            claude = codex = true;

        string targetPath;
        try
        {
            targetPath = Path.GetFullPath(target.FullName);
        }
        catch (Exception ex) when (ex is ArgumentException or IOException or NotSupportedException)
        {
            error.WriteLine($"Invalid target repository path: {ex.Message}");
            return 1;
        }

        if (!Directory.Exists(targetPath))
        {
            error.WriteLine($"Target repository directory does not exist: {targetPath}");
            return 1;
        }

        var sourcePath = Path.GetFullPath(sourceDirectory ?? BundledPluginDirectory);
        if (!Directory.Exists(sourcePath))
        {
            error.WriteLine($"Bundled roslyn-graph plugin not found: {sourcePath}");
            return 1;
        }

        try
        {
            ValidateBundle(sourcePath);
            var files = EnumerateBundleFiles(sourcePath).ToArray();
            var destinations = GetDestinations(targetPath, claude, codex).ToArray();

            foreach (var destination in destinations)
            {
                output.WriteLine($"{(dryRun ? "Would install" : "Installing")} roslyn-graph for {destination.Name}: {destination.Path}");
                if (!dryRun)
                    CopyBundle(files, sourcePath, destination.Path);
            }

            return 0;
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or JsonException or InvalidDataException or ArgumentException)
        {
            error.WriteLine($"Could not install roslyn-graph: {ex.Message}");
            return 1;
        }
    }

    private static IEnumerable<(string Name, string Path)> GetDestinations(string target, bool claude, bool codex)
    {
        if (claude)
            yield return ("Claude", Path.Combine(target, ".claude", "plugins", PluginDirectoryName));
        if (codex)
            yield return ("Codex", Path.Combine(target, ".codex", "plugins", PluginDirectoryName));
    }

    private static void ValidateBundle(string source)
    {
        var claudeVersion = ValidateManifest(Path.Combine(source, ".claude-plugin", "plugin.json"), "roslyn-graph", "./skills/roslyn-graph-create", "./skills/roslyn-graph-explore");
        var codexVersion = ValidateManifest(Path.Combine(source, ".codex-plugin", "plugin.json"), "roslyn-graph");
        if (!string.Equals(claudeVersion, codexVersion, StringComparison.Ordinal))
            throw new InvalidDataException("The Claude and Codex plugin manifests have different versions.");

        var skills = Path.Combine(source, "skills");
        if (!Directory.Exists(Path.Combine(skills, "roslyn-graph-create")) ||
            !Directory.Exists(Path.Combine(skills, "roslyn-graph-explore")))
            throw new InvalidDataException("The bundled plugin must contain both roslyn-graph skills.");
    }

    private static string ValidateManifest(string path, string expectedName, params string[] expectedSkills)
    {
        if (!File.Exists(path))
            throw new InvalidDataException($"Plugin manifest is missing: {path}");

        using var document = JsonDocument.Parse(File.ReadAllText(path));
        var root = document.RootElement;
        if (root.ValueKind != JsonValueKind.Object ||
            !root.TryGetProperty("name", out var name) || name.GetString() != expectedName ||
            !root.TryGetProperty("version", out var version) || string.IsNullOrWhiteSpace(version.GetString()))
            throw new InvalidDataException($"Plugin manifest is invalid: {path}");

        var manifestVersion = version.GetString()!;
        if (expectedSkills.Length == 0)
            return manifestVersion;

        if (!root.TryGetProperty("skills", out var skills) || skills.ValueKind != JsonValueKind.Array)
            throw new InvalidDataException($"Claude plugin manifest has no skills list: {path}");
        var actualSkills = skills.EnumerateArray().Select(value => value.GetString()).ToHashSet(StringComparer.Ordinal);
        if (expectedSkills.Any(skill => !actualSkills.Contains(skill)))
            throw new InvalidDataException($"Claude plugin manifest does not reference all bundled skills: {path}");
        return manifestVersion;
    }

    private static IEnumerable<string> EnumerateBundleFiles(string source)
    {
        foreach (var file in Directory.EnumerateFiles(source, "*", SearchOption.AllDirectories))
        {
            var attributes = File.GetAttributes(file);
            if ((attributes & FileAttributes.ReparsePoint) != 0)
                throw new InvalidDataException($"The plugin bundle contains a symbolic link or reparse point: {file}");
            yield return file;
        }
    }

    private static void CopyBundle(IReadOnlyCollection<string> files, string source, string destination)
    {
        foreach (var file in files)
        {
            var relativePath = Path.GetRelativePath(source, file);
            var targetFile = Path.GetFullPath(Path.Combine(destination, relativePath));
            EnsureChildPath(destination, targetFile);

            var targetDirectory = Path.GetDirectoryName(targetFile)!;
            EnsureNoReparsePoints(destination, targetDirectory);
            if (File.Exists(targetFile) && (File.GetAttributes(targetFile) & FileAttributes.ReparsePoint) != 0)
                throw new InvalidDataException($"Refusing to overwrite a symbolic link or reparse point: {targetFile}");
            Directory.CreateDirectory(targetDirectory);

            // Replace bundled files atomically; leave unrelated user files and folders untouched.
            var temporaryFile = Path.Combine(targetDirectory, $".{Path.GetFileName(targetFile)}.{Guid.NewGuid():N}.tmp");
            try
            {
                File.Copy(file, temporaryFile);
                File.Move(temporaryFile, targetFile, overwrite: true);
            }
            finally
            {
                if (File.Exists(temporaryFile))
                    File.Delete(temporaryFile);
            }
        }
    }

    private static void EnsureChildPath(string root, string candidate)
    {
        var fullRoot = Path.GetFullPath(root).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
        var relative = Path.GetRelativePath(fullRoot, candidate);
        if (relative == "." || relative == ".." || relative.StartsWith($"..{Path.DirectorySeparatorChar}", StringComparison.Ordinal) || Path.IsPathRooted(relative))
            throw new InvalidDataException($"Plugin asset path escapes its install directory: {candidate}");
    }

    private static void EnsureNoReparsePoints(string root, string directory)
    {
        var relative = Path.GetRelativePath(root, directory);
        var current = Path.GetFullPath(root);
        if (relative == ".")
            return;

        foreach (var segment in relative.Split([Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar], StringSplitOptions.RemoveEmptyEntries))
        {
            current = Path.Combine(current, segment);
            if (Directory.Exists(current) && (File.GetAttributes(current) & FileAttributes.ReparsePoint) != 0)
                throw new InvalidDataException($"Refusing to write through a symbolic link or reparse point: {current}");
        }
    }
}
