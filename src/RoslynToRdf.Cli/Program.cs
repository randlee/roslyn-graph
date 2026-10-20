using System.CommandLine;
using Microsoft.Build.Locator;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.MSBuild;
using RoslynToRdf.Core.Emitters;
using RoslynToRdf.Core.Extraction;

namespace RoslynToRdf.Cli;

public class Program
{
    // Source-project extraction can be invoked concurrently by hosts or tests.
    // MSBuildLocator permits registration only once, so the check and registration
    // must be one atomic operation rather than two racing reads/writes.
    private static readonly object MsBuildLocatorGate = new();

    public static async Task<int> Main(string[] args)
    {
        if (args.Length > 0 && string.Equals(args[0], "skill", StringComparison.OrdinalIgnoreCase))
        {
            var skillCommand = CreateSkillCommand();
            return await skillCommand.InvokeAsync(args[1..]);
        }

        var rootCommand = new RootCommand("Extract .NET assembly type graphs to RDF format") { Name = "roslyn2rdf" };
        rootCommand.AddCommand(CreateSkillCommand());

        var assemblyArg = new Argument<FileInfo>("assembly", "Path to a .NET assembly (.dll) or C#/VB source project (.csproj/.vbproj) to analyze");
        var additionalAssembliesOption = new Option<FileInfo[]>(["--assembly", "-a"], () => [], "Additional target assemblies to include in the same graph");
        var outputOption = new Option<FileInfo?>(["--output", "-o"], "Output file path");
        var formatOption = new Option<OutputFormat>(["--format", "-f"], () => OutputFormat.NTriples, "Output format");
        var baseUriOption = new Option<string>(["--base-uri", "-b"], () => "http://dotnet.example/", "Base URI for IRIs");
        var includePrivateOption = new Option<bool>("--include-private", () => false, "Include private members");
        var includeInternalOption = new Option<bool>("--include-internal", () => true, "Include internal members");
        var excludeAttributesOption = new Option<bool>("--exclude-attributes", () => false, "Exclude attributes");
        var includeAttributesOption = new Option<bool>("--include-attributes", () => false, "Include attributes (excluded by default)");
        var excludeExternalTypesOption = new Option<bool>("--exclude-external-types", () => false, "Exclude external types");
        var extractExceptionsOption = new Option<bool>("--extract-exceptions", () => true, "Extract exceptions from XML docs");
        var extractSeeAlsoOption = new Option<bool>("--extract-seealso", () => true, "Extract seealso from XML docs");
        var verboseOption = new Option<bool>(["--verbose", "-v"], () => false, "Verbose output");
        var quietOption = new Option<bool>(["--quiet", "-q"], () => false, "Quiet output");
        var refsOption = new Option<string[]>(["--reference", "-r"], () => [], "Additional assembly references");
        var failOnMissingReferencesOption = new Option<bool>("--fail-on-missing-references", () => false,
            "Fail on unresolved or unreadable assembly references (.dll inputs only)");
        failOnMissingReferencesOption.AddAlias("--strict");
        var searchDirOption = new Option<string[]>(["--search-dir", "-s"], () => [], "Search directories");
        var solutionDirOption = new Option<DirectoryInfo?>("--solution-dir", "Solution directory used to evaluate a source project (defaults to the project directory)");
        var configurationOption = new Option<string?>("--configuration", "MSBuild configuration used to evaluate a source project");
        var platformOption = new Option<string?>("--platform", "MSBuild platform used to evaluate a source project");
        var targetFrameworkOption = new Option<string?>("--target-framework", "Target framework used to evaluate a source project");

        rootCommand.AddArgument(assemblyArg);
        rootCommand.AddOption(additionalAssembliesOption);
        rootCommand.AddOption(outputOption);
        rootCommand.AddOption(formatOption);
        rootCommand.AddOption(baseUriOption);
        rootCommand.AddOption(includePrivateOption);
        rootCommand.AddOption(includeInternalOption);
        rootCommand.AddOption(excludeAttributesOption);
        rootCommand.AddOption(includeAttributesOption);
        rootCommand.AddOption(excludeExternalTypesOption);
        rootCommand.AddOption(extractExceptionsOption);
        rootCommand.AddOption(extractSeeAlsoOption);
        rootCommand.AddOption(verboseOption);
        rootCommand.AddOption(quietOption);
        rootCommand.AddOption(refsOption);
        rootCommand.AddOption(failOnMissingReferencesOption);
        rootCommand.AddOption(searchDirOption);
        rootCommand.AddOption(solutionDirOption);
        rootCommand.AddOption(configurationOption);
        rootCommand.AddOption(platformOption);
        rootCommand.AddOption(targetFrameworkOption);
        rootCommand.AddCommand(DeclarationsCommand.Create());

        rootCommand.SetHandler(async (context) =>
        {
            var assembly = context.ParseResult.GetValueForArgument(assemblyArg);
            var additionalAssemblies = context.ParseResult.GetValueForOption(additionalAssembliesOption)!;
            var output = context.ParseResult.GetValueForOption(outputOption);
            var format = context.ParseResult.GetValueForOption(formatOption);
            var baseUri = context.ParseResult.GetValueForOption(baseUriOption)!;
            var includePrivate = context.ParseResult.GetValueForOption(includePrivateOption);
            var includeInternal = context.ParseResult.GetValueForOption(includeInternalOption);
            var excludeAttributes = context.ParseResult.GetValueForOption(excludeAttributesOption);
            var includeAttributes = context.ParseResult.GetValueForOption(includeAttributesOption);
            var excludeExternalTypes = context.ParseResult.GetValueForOption(excludeExternalTypesOption);
            var extractExceptions = context.ParseResult.GetValueForOption(extractExceptionsOption);
            var extractSeeAlso = context.ParseResult.GetValueForOption(extractSeeAlsoOption);
            var verbose = context.ParseResult.GetValueForOption(verboseOption);
            var quiet = context.ParseResult.GetValueForOption(quietOption);
            var refs = context.ParseResult.GetValueForOption(refsOption)!;
            var failOnMissingReferences = context.ParseResult.GetValueForOption(failOnMissingReferencesOption);
            var searchDirs = context.ParseResult.GetValueForOption(searchDirOption)!;
            var solutionDir = context.ParseResult.GetValueForOption(solutionDirOption);
            var configuration = context.ParseResult.GetValueForOption(configurationOption);
            var platform = context.ParseResult.GetValueForOption(platformOption);
            var targetFramework = context.ParseResult.GetValueForOption(targetFrameworkOption);

            context.ExitCode = await RunExtraction([assembly, ..additionalAssemblies], output, format, baseUri, includePrivate, includeInternal,
                includeAttributes, excludeAttributes, excludeExternalTypes, extractExceptions, extractSeeAlso, verbose, quiet, refs, searchDirs,
                solutionDir?.FullName, configuration, platform, targetFramework, failOnMissingReferences);
        });

        return await rootCommand.InvokeAsync(args);
    }

    private static Command CreateSkillCommand()
    {
        var skillCommand = new Command("skill", "Install the bundled roslyn-graph plugin skills into a repository.");
        var installOption = new Option<DirectoryInfo>("--install", "Target repository directory") { IsRequired = true };
        var claudeOption = new Option<bool>("--claude", "Install only the Claude Code plugin location.");
        var codexOption = new Option<bool>("--codex", "Install only the Codex plugin location.");
        var dryRunOption = new Option<bool>("--dry-run", "Show the install paths without writing files.");
        skillCommand.AddOption(installOption);
        skillCommand.AddOption(claudeOption);
        skillCommand.AddOption(codexOption);
        skillCommand.AddOption(dryRunOption);
        skillCommand.SetHandler(context =>
        {
            context.ExitCode = PluginInstaller.Install(
                context.ParseResult.GetValueForOption(installOption)!,
                context.ParseResult.GetValueForOption(claudeOption),
                context.ParseResult.GetValueForOption(codexOption),
                context.ParseResult.GetValueForOption(dryRunOption),
                Console.Out,
                Console.Error);
        });
        return skillCommand;
    }

    private static async Task<int> RunExtraction(IEnumerable<FileInfo> requestedAssemblies, FileInfo? output, OutputFormat format, string baseUri,
        bool includePrivate, bool includeInternal, bool includeAttributes, bool excludeAttributes, bool excludeExternalTypes,
        bool extractExceptions, bool extractSeeAlso, bool verbose, bool quiet, string[] refs, string[] searchDirs,
        string? solutionDir, string? configuration, string? platform, string? targetFramework, bool failOnMissingReferences)
    {
        var assemblies = requestedAssemblies
            .GroupBy(assembly => assembly.FullName, StringComparer.OrdinalIgnoreCase)
            .Select(group => group.First())
            .ToArray();

        if (includeAttributes && excludeAttributes)
        {
            Console.Error.WriteLine("--include-attributes and --exclude-attributes cannot be combined.");
            return 1;
        }

        var sourceProjects = assemblies.Where(file =>
            file.Extension.Equals(".csproj", StringComparison.OrdinalIgnoreCase)
            || file.Extension.Equals(".vbproj", StringComparison.OrdinalIgnoreCase)).ToArray();
        if (sourceProjects.Length > 0 && (sourceProjects.Length != 1 || assemblies.Length != 1))
        {
            Console.Error.WriteLine("A source project must be extracted alone; it cannot be combined with --assembly.");
            return 1;
        }

        if (sourceProjects.Length > 0 && failOnMissingReferences)
        {
            Console.Error.WriteLine("--fail-on-missing-references is supported only for assembly (.dll) inputs, not source projects.");
            return 1;
        }

        var missingAssemblies = assemblies.Where(assembly => !assembly.Exists).ToArray();
        if (missingAssemblies.Length > 0)
        {
            foreach (var assembly in missingAssemblies)
                Console.Error.WriteLine($"Assembly not found: {assembly.FullName}");
            return 1;
        }

        if (assemblies.Length > 1 && output is null)
        {
            Console.Error.WriteLine("--output is required when extracting more than one assembly.");
            return 1;
        }

        var outputPath = output?.FullName ?? Path.ChangeExtension(assemblies[0].FullName, format == OutputFormat.Turtle ? ".ttl" : ".nt");
        var options = new ExtractionOptions
        {
            BaseUri = baseUri,
            SourceRoot = sourceProjects.Length == 1 ? Path.GetDirectoryName(sourceProjects[0].FullName) : null,
            IncludePrivate = includePrivate,
            IncludeInternal = includeInternal,
            IncludeAttributes = includeAttributes,
            IncludeExternalTypes = !excludeExternalTypes,
            ExtractExceptions = extractExceptions,
            ExtractSeeAlso = extractSeeAlso,
            LogLevel = quiet ? LogLevel.Quiet : (verbose ? LogLevel.Verbose : LogLevel.Info)
        };

        Action<string>? log = quiet ? null : Console.WriteLine;

        try
        {
            log?.Invoke($"Output file: {outputPath}");

            using ITriplesEmitter emitter = format == OutputFormat.Turtle
                ? new TurtleEmitter(outputPath)
                : new NTriplesEmitter(outputPath);

            if (sourceProjects.Length == 1)
            {
                var projectPath = sourceProjects[0].FullName;
                log?.Invoke($"Loading source project: {projectPath}");
                EnsureMsBuildLocatorRegistered();

                var projectDirectory = Path.GetDirectoryName(projectPath)!;
                var properties = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
                {
                    ["SolutionDir"] = EnsureTrailingSeparator(Path.GetFullPath(solutionDir ?? projectDirectory)),
                    ["Configuration"] = configuration ?? "Debug"
                };
                if (!string.IsNullOrWhiteSpace(platform)) properties["Platform"] = platform;
                if (!string.IsNullOrWhiteSpace(targetFramework)) properties["TargetFramework"] = targetFramework;

                using var workspace = MSBuildWorkspace.Create(properties);
                workspace.WorkspaceFailed += (_, args) => log?.Invoke($"MSBuild workspace: {args.Diagnostic.Message}");
                var project = await workspace.OpenProjectAsync(projectPath);
                if (project.Language != LanguageNames.CSharp && project.Language != LanguageNames.VisualBasic)
                    throw new InvalidOperationException("Only C# and Visual Basic source projects are supported.");
                var compilation = await project.GetCompilationAsync()
                    ?? throw new InvalidOperationException("MSBuild did not provide a compilation for the project.");
                if (compilation.Options is CSharpCompilationOptions { AllowUnsafe: false })
                    log?.Invoke("AllowUnsafeBlocks is false; unsafe-method analysis is skipped for this project.");
                var extractor = new AssemblyGraphExtractor(emitter, options, log);
                extractor.Extract(compilation, compilation.Assembly);
            }
            else
            {
                foreach (var assembly in assemblies)
                {
                    log?.Invoke($"Loading assembly: {assembly.FullName}");

                    var loader = new AssemblyLoader();
                    foreach (var refPath in refs) loader.AddReferencePath(refPath);
                    foreach (var searchDir in searchDirs) loader.AddSearchDirectory(searchDir);

                    var (compilation, assemblySymbol) = loader.LoadAssembly(assembly.FullName);
                    foreach (var diagnostic in loader.ReferenceDiagnostics)
                    {
                        var referencePath = diagnostic.ReferencePath == null ? "" : $" at '{diagnostic.ReferencePath}'";
                        var referencedBy = diagnostic.ReferencedBy == null ? " (explicit --reference)" : $" referenced by '{diagnostic.ReferencedBy}'";
                        Console.Error.WriteLine($"Warning: Assembly reference '{diagnostic.AssemblyName}'{referencePath}{referencedBy} could not be loaded: {diagnostic.Reason} Supply --reference (-r) or --search-dir (-s) to resolve dependencies.");
                    }
                    if (failOnMissingReferences && loader.ReferenceDiagnostics.Count > 0)
                    {
                        Console.Error.WriteLine("Error: Assembly references could not be loaded (--fail-on-missing-references).");
                        return 1;
                    }
                    var extractor = new AssemblyGraphExtractor(emitter, options, log);
                    extractor.Extract(compilation, assemblySymbol, peImagePath: assembly.FullName);
                }
            }
            emitter.Flush();

            log?.Invoke($"Done. {emitter.TripleCount} triples written to {outputPath}");
            return 0;
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine($"Error: {ex.Message}");
            if (verbose) Console.Error.WriteLine(ex.StackTrace);
            return 1;
        }
    }

    private static string EnsureTrailingSeparator(string path)
    {
        var separator = Path.DirectorySeparatorChar;
        return path.EndsWith(separator) || path.EndsWith(Path.AltDirectorySeparatorChar)
            ? path
            : path + separator;
    }

    private static void EnsureMsBuildLocatorRegistered()
    {
        if (MSBuildLocator.IsRegistered)
            return;

        lock (MsBuildLocatorGate)
        {
            if (!MSBuildLocator.IsRegistered)
                MSBuildLocator.RegisterDefaults();
        }
    }
}

public enum OutputFormat { NTriples, Turtle }
