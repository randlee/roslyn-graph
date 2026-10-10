namespace RoslynToRdf.Cli;
public static class PluginInstaller
{
    public static string SourceRoot() => Environment.GetEnvironmentVariable("ROSLYN2RDF_PLUGIN_ROOT") ?? Path.Combine(AppContext.BaseDirectory, "roslyn-graph");
    public static int Install(DirectoryInfo target, bool claude, bool codex, bool dryRun, TextWriter output, TextWriter error)
    {
        if (!claude && !codex) claude = codex = true;
        var source = new DirectoryInfo(SourceRoot());
        if (!source.Exists) { error.WriteLine($"Bundled roslyn-graph plugin not found: {source.FullName}"); return 1; }
        foreach (var host in Hosts(target.FullName, claude, codex))
        {
            output.WriteLine($"{(dryRun ? "Would install" : "Installing")} roslyn-graph for {host.Name}: {host.Path}");
            if (!dryRun) Copy(source, new DirectoryInfo(host.Path));
        }
        return 0;
    }
    private static IEnumerable<(string Name, string Path)> Hosts(string target, bool claude, bool codex)
    { if (claude) yield return ("Claude", Path.Combine(target, ".claude", "plugins", "roslyn-graph")); if (codex) yield return ("Codex", Path.Combine(target, ".codex", "plugins", "roslyn-graph")); }
    private static void Copy(DirectoryInfo source, DirectoryInfo destination)
    { foreach (var file in source.EnumerateFiles("*", SearchOption.AllDirectories)) { var target = Path.Combine(destination.FullName, Path.GetRelativePath(source.FullName, file.FullName)); Directory.CreateDirectory(Path.GetDirectoryName(target)!); file.CopyTo(target, true); } }
}
