using System.Diagnostics;
using System.IO.Compression;
using System.Text.Json;
using System.Xml.Linq;

namespace RoslynToRdf.Tests;

public class PluginInstallToolTests
{
    [Fact]
    public async Task PackedTool_InstallsBothOrSelectedHosts_AndDryRunDoesNotWrite()
    {
        var repository = FindRepositoryRoot();
        var tempRoot = Path.Combine(Path.GetTempPath(), "roslyn2rdf-tool-e2e-" + Guid.NewGuid().ToString("N"));
        var packageDirectory = Path.Combine(tempRoot, "packages");
        var toolDirectory = Path.Combine(tempRoot, "tool");
        Directory.CreateDirectory(packageDirectory);
        Directory.CreateDirectory(toolDirectory);

        try
        {
            await RunProcess("dotnet", [
                "pack", Path.Combine(repository, "src", "RoslynToRdf.Cli", "RoslynToRdf.Cli.csproj"),
                "--no-restore", "--configuration", "Release", "--output", packageDirectory
            ], repository, expectedExitCode: 0);

            var packagePath = Path.Combine(packageDirectory, "RoslynToRdf.0.1.0.nupkg");
            Assert.True(File.Exists(packagePath), $"Packed tool was not created at {packagePath}.");
            AssertPackagedBundle(packagePath, repository);

            await RunProcess("dotnet", [
                "tool", "install", "RoslynToRdf", "--version", "0.1.0", "--tool-path", toolDirectory,
                "--add-source", packageDirectory, "--ignore-failed-sources"
            ], repository, expectedExitCode: 0);

            var toolExecutable = Path.Combine(toolDirectory, OperatingSystem.IsWindows() ? "roslyn2rdf.exe" : "roslyn2rdf");
            Assert.True(File.Exists(toolExecutable), $"Installed tool was not created at {toolExecutable}.");

            var defaultTarget = NewTarget(tempRoot, "default");
            var existingPlugin = Path.Combine(defaultTarget, ".claude", "plugins", "roslyn-graph");
            Directory.CreateDirectory(existingPlugin);
            await File.WriteAllTextAsync(Path.Combine(existingPlugin, "user-notes.txt"), "keep me");
            var existingSkill = Path.Combine(existingPlugin, "skills", "roslyn-graph-create", "SKILL.md");
            Directory.CreateDirectory(Path.GetDirectoryName(existingSkill)!);
            await File.WriteAllTextAsync(existingSkill, "locally edited old copy");
            await RunProcess(toolExecutable, ["skill", "--install", defaultTarget], repository, expectedExitCode: 0);
            AssertHostInstalled(defaultTarget, ".claude", ".claude-plugin");
            AssertHostInstalled(defaultTarget, ".codex", ".codex-plugin");
            Assert.Equal("keep me", await File.ReadAllTextAsync(Path.Combine(existingPlugin, "user-notes.txt")));
            Assert.NotEqual("locally edited old copy", await File.ReadAllTextAsync(existingSkill));

            var claudeTarget = NewTarget(tempRoot, "claude-only");
            await RunProcess(toolExecutable, ["skill", "--install", claudeTarget, "--claude"], repository, expectedExitCode: 0);
            AssertHostInstalled(claudeTarget, ".claude", ".claude-plugin");
            Assert.False(Directory.Exists(Path.Combine(claudeTarget, ".codex")));

            var codexTarget = NewTarget(tempRoot, "codex-only");
            await RunProcess(toolExecutable, ["skill", "--install", codexTarget, "--codex"], repository, expectedExitCode: 0);
            AssertHostInstalled(codexTarget, ".codex", ".codex-plugin");
            Assert.False(Directory.Exists(Path.Combine(codexTarget, ".claude")));

            var dryRunTarget = NewTarget(tempRoot, "dry-run");
            var dryRun = await RunProcess(toolExecutable, ["skill", "--install", dryRunTarget, "--dry-run"], repository, expectedExitCode: 0);
            Assert.Contains("Claude", dryRun.Stdout);
            Assert.Contains("Codex", dryRun.Stdout);
            Assert.False(Directory.Exists(Path.Combine(dryRunTarget, ".claude")));
            Assert.False(Directory.Exists(Path.Combine(dryRunTarget, ".codex")));

            var missingTarget = Path.Combine(tempRoot, "does-not-exist");
            var invalid = await RunProcess(toolExecutable, ["skill", "--install", missingTarget, "--claude"], repository, expectedExitCode: 1);
            Assert.Contains("Target repository directory does not exist", invalid.Stderr);
        }
        finally
        {
            if (Directory.Exists(tempRoot))
                Directory.Delete(tempRoot, recursive: true);
        }
    }

    private static void AssertPackagedBundle(string packagePath, string repository)
    {
        using var archive = ZipFile.OpenRead(packagePath);
        var names = archive.Entries.Select(entry => entry.FullName.Replace('\\', '/')).ToHashSet(StringComparer.Ordinal);
        const string packageRoot = "tools/net8.0/any/roslyn-graph/";
        var pluginRoot = Path.Combine(repository, "plugins", "roslyn-graph");
        foreach (var sourceFile in Directory.EnumerateFiles(pluginRoot, "*", SearchOption.AllDirectories))
        {
            var relative = Path.GetRelativePath(pluginRoot, sourceFile).Replace('\\', '/');
            Assert.Contains(packageRoot + relative, names);
        }

        var claude = ReadManifest(archive, packageRoot + ".claude-plugin/plugin.json");
        var codex = ReadManifest(archive, packageRoot + ".codex-plugin/plugin.json");
        Assert.Equal("roslyn-graph", claude.GetProperty("name").GetString());
        Assert.Equal("roslyn-graph", codex.GetProperty("name").GetString());
        Assert.Equal(claude.GetProperty("version").GetString(), codex.GetProperty("version").GetString());
        using var nuspec = archive.GetEntry("RoslynToRdf.nuspec")!.Open();
        var metadata = XDocument.Load(nuspec).Descendants().Single(element => element.Name.LocalName == "metadata");
        var packageVersion = metadata.Elements().Single(element => element.Name.LocalName == "version").Value;
        Assert.Equal(packageVersion, claude.GetProperty("version").GetString());
        Assert.Contains("./skills/roslyn-graph-create", claude.GetProperty("skills").EnumerateArray().Select(item => item.GetString()));
        Assert.Contains("./skills/roslyn-graph-explore", claude.GetProperty("skills").EnumerateArray().Select(item => item.GetString()));
    }

    private static JsonElement ReadManifest(ZipArchive archive, string path)
    {
        using var stream = archive.GetEntry(path)!.Open();
        using var document = JsonDocument.Parse(stream);
        return document.RootElement.Clone();
    }

    private static void AssertHostInstalled(string target, string host, string manifestDirectory)
    {
        var plugin = Path.Combine(target, host, "plugins", "roslyn-graph");
        var manifestPath = Path.Combine(plugin, manifestDirectory, "plugin.json");
        Assert.True(File.Exists(manifestPath));
        using var manifest = JsonDocument.Parse(File.ReadAllText(manifestPath));
        Assert.Equal("roslyn-graph", manifest.RootElement.GetProperty("name").GetString());
        Assert.True(Directory.Exists(Path.Combine(plugin, "skills", "roslyn-graph-create", "scripts", "roslyn_graph")));
        Assert.True(Directory.Exists(Path.Combine(plugin, "skills", "roslyn-graph-explore", "ontology")));
    }

    private static string NewTarget(string root, string name)
    {
        var target = Path.Combine(root, "targets", name);
        Directory.CreateDirectory(target);
        using var process = Process.Start(new ProcessStartInfo("git")
        {
            WorkingDirectory = target,
            UseShellExecute = false,
            CreateNoWindow = true,
            ArgumentList = { "init", "--quiet" }
        }) ?? throw new InvalidOperationException("Could not start git to initialize the disposable target repository.");
        process.WaitForExit();
        if (process.ExitCode != 0)
            throw new InvalidOperationException($"git init failed for disposable target repository {target}.");
        return target;
    }

    private static string FindRepositoryRoot()
    {
        for (var directory = new DirectoryInfo(AppContext.BaseDirectory); directory is not null; directory = directory.Parent)
            if (File.Exists(Path.Combine(directory.FullName, "RoslynToRdf.sln")))
                return directory.FullName;
        throw new DirectoryNotFoundException("Could not locate the RoslynToRdf repository root.");
    }

    private static async Task<(string Stdout, string Stderr)> RunProcess(string executable, IEnumerable<string> arguments, string workingDirectory, int expectedExitCode)
    {
        var startInfo = new ProcessStartInfo(executable)
        {
            WorkingDirectory = workingDirectory,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            UseShellExecute = false
        };
        foreach (var argument in arguments)
            startInfo.ArgumentList.Add(argument);

        using var process = Process.Start(startInfo) ?? throw new InvalidOperationException($"Could not start {executable}.");
        var stdoutTask = process.StandardOutput.ReadToEndAsync();
        var stderrTask = process.StandardError.ReadToEndAsync();
        await process.WaitForExitAsync();
        var stdout = await stdoutTask;
        var stderr = await stderrTask;
        Assert.True(process.ExitCode == expectedExitCode,
            $"{Path.GetFileName(executable)} exited {process.ExitCode}, expected {expectedExitCode}.\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}");
        return (stdout, stderr);
    }
}
