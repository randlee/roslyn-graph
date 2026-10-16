using System.CommandLine;

namespace RoslynToRdf.DocliExport;

/// <summary>
/// Command tree mirror for docli export. Keep aligned with
/// <c>src/RoslynToRdf.Cli/Program.cs</c> and <c>DeclarationsCommand.cs</c>.
/// </summary>
internal static class RoslynGraphDocliCommandTree
{
    internal static Command CreateRootCommand()
    {
        var root = new Command("roslyn2rdf", "Extract .NET assembly type graphs to RDF format");
        root.Subcommands.Add(CreateSkillCommand());
        root.Subcommands.Add(CreateDeclarationsCommand());

        var assemblyArg = new Argument<FileInfo>("assembly")
        {
            Description = "Path to a .NET assembly (.dll) or C# source project (.csproj) to analyze",
        };
        root.Arguments.Add(assemblyArg);

        root.Options.Add(new Option<FileInfo[]>("--assembly", "-a")
        {
            Description = "Additional target assemblies to include in the same graph",
            Arity = ArgumentArity.ZeroOrMore,
        });
        root.Options.Add(new Option<FileInfo?>("--output", "-o") { Description = "Output file path" });
        root.Options.Add(new Option<string>("--format", "-f")
        {
            Description = "Output format",
            DefaultValueFactory = _ => "ntriples",
        });
        root.Options.Add(new Option<string>("--base-uri", "-b")
        {
            Description = "Base URI for IRIs",
            DefaultValueFactory = _ => "http://dotnet.example/",
        });
        root.Options.Add(new Option<bool>("--include-private") { Description = "Include private members" });
        root.Options.Add(new Option<bool>("--include-internal")
        {
            Description = "Include internal members",
            DefaultValueFactory = _ => true,
        });
        root.Options.Add(new Option<bool>("--exclude-attributes") { Description = "Exclude attributes" });
        root.Options.Add(new Option<bool>("--exclude-external-types") { Description = "Exclude external types" });
        root.Options.Add(new Option<bool>("--extract-exceptions")
        {
            Description = "Extract exceptions from XML docs",
            DefaultValueFactory = _ => true,
        });
        root.Options.Add(new Option<bool>("--extract-seealso")
        {
            Description = "Extract seealso from XML docs",
            DefaultValueFactory = _ => true,
        });
        root.Options.Add(new Option<bool>("--verbose", "-v") { Description = "Verbose output" });
        root.Options.Add(new Option<bool>("--quiet", "-q") { Description = "Quiet output" });
        root.Options.Add(new Option<bool>("--fail-on-missing-references")
        {
            Description = "Fail on unresolved or unreadable assembly references (.dll inputs only)",
        });
        root.Options.Add(new Option<string[]>("--reference", "-r")
        {
            Description = "Additional assembly references",
            Arity = ArgumentArity.ZeroOrMore,
        });
        root.Options.Add(new Option<string[]>("--search-dir", "-s")
        {
            Description = "Search directories",
            Arity = ArgumentArity.ZeroOrMore,
        });
        root.Options.Add(new Option<DirectoryInfo?>("--solution-dir")
        {
            Description = "Solution directory used to evaluate a source project (defaults to the project directory)",
        });
        root.Options.Add(new Option<string?>("--configuration")
        {
            Description = "MSBuild configuration used to evaluate a source project",
        });
        root.Options.Add(new Option<string?>("--platform")
        {
            Description = "MSBuild platform used to evaluate a source project",
        });
        root.Options.Add(new Option<string?>("--target-framework")
        {
            Description = "Target framework used to evaluate a source project",
        });

        return root;
    }

    private static Command CreateSkillCommand()
    {
        var skill = new Command("skill", "Install the bundled roslyn-graph plugin skills into a repository.");
        skill.Options.Add(new Option<DirectoryInfo>("--install")
        {
            Description = "Target repository directory",
            Required = true,
        });
        skill.Options.Add(new Option<bool>("--claude") { Description = "Install only the Claude Code plugin location." });
        skill.Options.Add(new Option<bool>("--codex") { Description = "Install only the Codex plugin location." });
        skill.Options.Add(new Option<bool>("--dry-run") { Description = "Show the install paths without writing files." });
        return skill;
    }

    private static Command CreateDeclarationsCommand()
    {
        var declarations = new Command(
            "declarations",
            "List the named types declared in source files (syntax only, no MSBuild)");
        declarations.Options.Add(new Option<FileInfo>("--request")
        {
            Description = "Request JSON file",
            Required = true,
        });
        declarations.Options.Add(new Option<FileInfo>("--output")
        {
            Description = "Response JSON file",
            Required = true,
        });
        return declarations;
    }
}
