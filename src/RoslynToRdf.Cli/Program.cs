using System.CommandLine;
using RoslynToRdf.Core.Emitters;
using RoslynToRdf.Core.Extraction;

namespace RoslynToRdf.Cli;

public class Program
{
    public static async Task<int> Main(string[] args)
    {
        var rootCommand = new RootCommand("Extract .NET assembly type graphs to RDF format") { Name = "roslyn2rdf" };

        var assemblyArg = new Argument<FileInfo>("assembly", "Path to the .NET assembly (.dll) to analyze");
        var outputOption = new Option<FileInfo?>(["--output", "-o"], "Output file path");
        var formatOption = new Option<OutputFormat>(["--format", "-f"], () => OutputFormat.NTriples, "Output format");
        var baseUriOption = new Option<string>(["--base-uri", "-b"], () => "http://dotnet.example/", "Base URI for IRIs");
        var includePrivateOption = new Option<bool>("--include-private", () => false, "Include private members");
        var includeInternalOption = new Option<bool>("--include-internal", () => true, "Include internal members");
        var excludeAttributesOption = new Option<bool>("--exclude-attributes", () => false, "Exclude attributes");
        var excludeExternalTypesOption = new Option<bool>("--exclude-external-types", () => false, "Exclude external types");
        var extractExceptionsOption = new Option<bool>("--extract-exceptions", () => true, "Extract exceptions from XML docs");
        var extractSeeAlsoOption = new Option<bool>("--extract-seealso", () => true, "Extract seealso from XML docs");
        var verboseOption = new Option<bool>(["--verbose", "-v"], () => false, "Verbose output");
        var quietOption = new Option<bool>(["--quiet", "-q"], () => false, "Quiet output");
        var refsOption = new Option<string[]>(["--reference", "-r"], () => [], "Additional assembly references");
        var searchDirOption = new Option<string[]>(["--search-dir", "-s"], () => [], "Search directories");

        rootCommand.AddArgument(assemblyArg);
        rootCommand.AddOption(outputOption);
        rootCommand.AddOption(formatOption);
        rootCommand.AddOption(baseUriOption);
        rootCommand.AddOption(includePrivateOption);
        rootCommand.AddOption(includeInternalOption);
        rootCommand.AddOption(excludeAttributesOption);
        rootCommand.AddOption(excludeExternalTypesOption);
        rootCommand.AddOption(extractExceptionsOption);
        rootCommand.AddOption(extractSeeAlsoOption);
        rootCommand.AddOption(verboseOption);
        rootCommand.AddOption(quietOption);
        rootCommand.AddOption(refsOption);
        rootCommand.AddOption(searchDirOption);

        rootCommand.SetHandler(async (context) =>
        {
            var assembly = context.ParseResult.GetValueForArgument(assemblyArg);
            var output = context.ParseResult.GetValueForOption(outputOption);
            var format = context.ParseResult.GetValueForOption(formatOption);
            var baseUri = context.ParseResult.GetValueForOption(baseUriOption)!;
            var includePrivate = context.ParseResult.GetValueForOption(includePrivateOption);
            var includeInternal = context.ParseResult.GetValueForOption(includeInternalOption);
            var excludeAttributes = context.ParseResult.GetValueForOption(excludeAttributesOption);
            var excludeExternalTypes = context.ParseResult.GetValueForOption(excludeExternalTypesOption);
            var extractExceptions = context.ParseResult.GetValueForOption(extractExceptionsOption);
            var extractSeeAlso = context.ParseResult.GetValueForOption(extractSeeAlsoOption);
            var verbose = context.ParseResult.GetValueForOption(verboseOption);
            var quiet = context.ParseResult.GetValueForOption(quietOption);
            var refs = context.ParseResult.GetValueForOption(refsOption)!;
            var searchDirs = context.ParseResult.GetValueForOption(searchDirOption)!;

            context.ExitCode = await RunExtraction(assembly, output, format, baseUri, includePrivate, includeInternal,
                excludeAttributes, excludeExternalTypes, extractExceptions, extractSeeAlso, verbose, quiet, refs, searchDirs);
        });

        return await rootCommand.InvokeAsync(args);
    }

    private static Task<int> RunExtraction(FileInfo assembly, FileInfo? output, OutputFormat format, string baseUri,
        bool includePrivate, bool includeInternal, bool excludeAttributes, bool excludeExternalTypes,
        bool extractExceptions, bool extractSeeAlso, bool verbose, bool quiet, string[] refs, string[] searchDirs)
    {
        if (!assembly.Exists)
        {
            Console.Error.WriteLine($"Assembly not found: {assembly.FullName}");
            return Task.FromResult(1);
        }

        var outputPath = output?.FullName ?? Path.ChangeExtension(assembly.FullName, format == OutputFormat.Turtle ? ".ttl" : ".nt");
        var options = new ExtractionOptions
        {
            BaseUri = baseUri,
            IncludePrivate = includePrivate,
            IncludeInternal = includeInternal,
            IncludeAttributes = !excludeAttributes,
            IncludeExternalTypes = !excludeExternalTypes,
            ExtractExceptions = extractExceptions,
            ExtractSeeAlso = extractSeeAlso,
            LogLevel = quiet ? LogLevel.Quiet : (verbose ? LogLevel.Verbose : LogLevel.Info)
        };

        Action<string>? log = quiet ? null : Console.WriteLine;

        try
        {
            log?.Invoke($"Loading assembly: {assembly.FullName}");

            var loader = new AssemblyLoader();
            foreach (var refPath in refs) loader.AddReferencePath(refPath);
            foreach (var searchDir in searchDirs) loader.AddSearchDirectory(searchDir);

            var (compilation, assemblySymbol) = loader.LoadAssembly(assembly.FullName);
            log?.Invoke($"Output file: {outputPath}");

            using ITriplesEmitter emitter = format == OutputFormat.Turtle
                ? new TurtleEmitter(outputPath)
                : new NTriplesEmitter(outputPath);

            var extractor = new AssemblyGraphExtractor(emitter, options, log);
            extractor.Extract(compilation, assemblySymbol);
            emitter.Flush();

            log?.Invoke($"Done. {emitter.TripleCount} triples written to {outputPath}");
            return Task.FromResult(0);
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine($"Error: {ex.Message}");
            if (verbose) Console.Error.WriteLine(ex.StackTrace);
            return Task.FromResult(1);
        }
    }
}

public enum OutputFormat { NTriples, Turtle }
