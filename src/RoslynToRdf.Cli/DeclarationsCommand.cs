using System.CommandLine;
using System.Text.Json;
using System.Text.Json.Serialization;
using RoslynToRdf.Core.Extraction;

namespace RoslynToRdf.Cli;

/// <summary>
/// <c>roslyn2rdf declarations --request req.json --output out.json</c>: the named types declared in a project's
/// Compile items, for locating source files on export. JSON in and out, so callers need no Roslyn of their own.
/// Request: <c>{language, langVersion, preprocessorSymbols, files, rootNamespace}</c>.
/// Response: <c>{type: "declarations", language, languageVersion, parseErrors, missingFiles, types: [{name, kind, file, line}]}</c>.
/// </summary>
public static class DeclarationsCommand
{
    private static readonly JsonSerializerOptions Json = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        PropertyNameCaseInsensitive = true,
        DefaultIgnoreCondition = JsonIgnoreCondition.Never,
    };

    public static Command Create()
    {
        var requestOption = new Option<FileInfo>("--request", "Request JSON file") { IsRequired = true };
        var outputOption = new Option<FileInfo>("--output", "Response JSON file") { IsRequired = true };
        var command = new Command("declarations", "List the named types declared in source files (syntax only, no MSBuild)");
        command.AddOption(requestOption);
        command.AddOption(outputOption);
        command.SetHandler(context =>
        {
            context.ExitCode = Run(context.ParseResult.GetValueForOption(requestOption)!, context.ParseResult.GetValueForOption(outputOption)!);
        });
        return command;
    }

    public static int Run(FileInfo requestFile, FileInfo outputFile)
    {
        try
        {
            var request = JsonSerializer.Deserialize<DeclarationRequest>(File.ReadAllText(requestFile.FullName), Json)
                ?? throw new InvalidDataException("The request is empty.");
            if (!DeclarationIndexer.IsCSharp(request.Language) && !DeclarationIndexer.IsVisualBasic(request.Language))
                throw new InvalidDataException($"Unsupported language '{request.Language}'; use C# or VB.");
            var index = DeclarationIndexer.Index(request with
            {
                PreprocessorSymbols = request.PreprocessorSymbols ?? [],
                Files = request.Files ?? [],
            });
            var response = new
            {
                type = "declarations",
                language = index.Language,
                languageVersion = index.LanguageVersion,
                parseErrors = index.ParseErrors,
                missingFiles = index.MissingFiles,
                types = index.Types,
            };
            Directory.CreateDirectory(outputFile.DirectoryName!);
            File.WriteAllText(outputFile.FullName, JsonSerializer.Serialize(response, Json));
            return 0;
        }
        catch (Exception ex) when (ex is IOException or JsonException or InvalidDataException or UnauthorizedAccessException)
        {
            Console.Error.WriteLine($"Error: {ex.Message}");
            return 1;
        }
    }
}
