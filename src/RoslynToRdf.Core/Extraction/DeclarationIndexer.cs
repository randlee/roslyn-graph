using Microsoft.CodeAnalysis;
using CS = Microsoft.CodeAnalysis.CSharp;
using VB = Microsoft.CodeAnalysis.VisualBasic;

namespace RoslynToRdf.Core.Extraction;

/// <summary>What to index: one project's Compile items with the symbols and language version MSBuild evaluated.</summary>
/// <param name="Language">"C#" or "VB" (MSBuild's Language property; "csharp" and "vb" are accepted too).</param>
/// <param name="LangVersion">MSBuild LangVersion; empty or unknown means the newest version this Roslyn supports.</param>
/// <param name="PreprocessorSymbols">C#: symbol names. VB: NAME or NAME=value as in DefineConstants.</param>
/// <param name="Files">Absolute paths of the Compile items.</param>
/// <param name="RootNamespace">VB only: the project's RootNamespace, which prefixes every declaration.</param>
public sealed record DeclarationRequest(
    string Language,
    string? LangVersion,
    IReadOnlyList<string> PreprocessorSymbols,
    IReadOnlyList<string> Files,
    string? RootNamespace = null);

/// <summary>A named type declared in source. Name matches the extractor's dt:fullName for the compiled type.</summary>
public sealed record DeclaredType(string Name, string Kind, string File, int Line);

public sealed record DeclarationIndex(
    string Language,
    string LanguageVersion,
    IReadOnlyList<DeclaredType> Types,
    IReadOnlyList<string> MissingFiles,
    int ParseErrors);

/// <summary>
/// Lists the named types declared in a set of source files without MSBuild or references: each file is parsed
/// with the project's preprocessor symbols (inactive #if branches become disabled text), the trees form a
/// reference-free compilation, and every source type is named with the extractor's own display format.
/// A partial type declared in several files is listed once per file.
/// </summary>
public static class DeclarationIndexer
{
    public static DeclarationIndex Index(DeclarationRequest request)
    {
        var vb = IsVisualBasic(request.Language);
        var missing = request.Files.Where(f => !File.Exists(f)).ToList();
        var files = request.Files.Where(File.Exists).Distinct(StringComparer.OrdinalIgnoreCase).ToList();

        Compilation compilation;
        string version;
        if (vb)
        {
            var options = new VB.VisualBasicParseOptions(ParseVbVersion(request.LangVersion), DocumentationMode.None,
                SourceCodeKind.Regular, ParseVbSymbols(request.PreprocessorSymbols));
            var trees = files.Select(f => VB.VisualBasicSyntaxTree.ParseText(ReadText(f), options, f)).ToList();
            var compilationOptions = new VB.VisualBasicCompilationOptions(OutputKind.DynamicallyLinkedLibrary,
                rootNamespace: request.RootNamespace ?? "");
            compilation = VB.VisualBasicCompilation.Create("declarations", trees, options: compilationOptions);
            version = options.LanguageVersion.ToString();
        }
        else
        {
            var options = new CS.CSharpParseOptions(ParseCSharpVersion(request.LangVersion), DocumentationMode.None,
                SourceCodeKind.Regular, request.PreprocessorSymbols.Where(s => !string.IsNullOrWhiteSpace(s)).Select(s => s.Trim()));
            var trees = files.Select(f => CS.CSharpSyntaxTree.ParseText(ReadText(f), options, f)).ToList();
            compilation = CS.CSharpCompilation.Create("declarations", trees,
                options: new CS.CSharpCompilationOptions(OutputKind.DynamicallyLinkedLibrary));
            version = options.LanguageVersion.ToString();
        }

        var parseErrors = compilation.SyntaxTrees.Sum(t => t.GetDiagnostics().Count(d => d.Severity == DiagnosticSeverity.Error));
        var types = new List<DeclaredType>();
        Walk(compilation.Assembly.GlobalNamespace, types);
        types.Sort((a, b) =>
        {
            var byName = string.CompareOrdinal(a.Name, b.Name);
            return byName != 0 ? byName : string.CompareOrdinal(a.File, b.File);
        });
        return new DeclarationIndex(vb ? "VB" : "C#", version, types, missing, parseErrors);
    }

    private static void Walk(INamespaceOrTypeSymbol container, List<DeclaredType> types)
    {
        foreach (var member in container.GetMembers())
        {
            switch (member)
            {
                case INamespaceSymbol ns:
                    Walk(ns, types);
                    break;
                case INamedTypeSymbol type:
                    Add(type, types);
                    Walk(type, types);
                    break;
            }
        }
    }

    private static void Add(INamedTypeSymbol type, List<DeclaredType> types)
    {
        // C# display rules for VB symbols too: the extractor names every type, VB-built or not, from a C# compilation.
        var name = CS.SymbolDisplay.ToDisplayString(type, AssemblyGraphExtractor.TypeNameFormat);
        var kind = type.TypeKind == TypeKind.Module ? nameof(TypeKind.Class) : type.TypeKind.ToString(); // VB modules compile to classes
        foreach (var location in type.Locations.Where(l => l.IsInSource).GroupBy(l => l.SourceTree!.FilePath).Select(g => g.First()))
        {
            var line = location.GetLineSpan().StartLinePosition.Line + 1;
            types.Add(new DeclaredType(name, kind, location.SourceTree!.FilePath, line));
        }
    }

    private static Microsoft.CodeAnalysis.Text.SourceText ReadText(string path)
    {
        using var stream = File.OpenRead(path);
        return Microsoft.CodeAnalysis.Text.SourceText.From(stream, throwIfBinaryDetected: false);
    }

    public static bool IsVisualBasic(string language) =>
        language.Equals("VB", StringComparison.OrdinalIgnoreCase) || language.Equals("VisualBasic", StringComparison.OrdinalIgnoreCase)
        || language.Equals("Visual Basic", StringComparison.OrdinalIgnoreCase);

    public static bool IsCSharp(string language) =>
        language.Equals("C#", StringComparison.OrdinalIgnoreCase) || language.Equals("CSharp", StringComparison.OrdinalIgnoreCase);

    private static CS.LanguageVersion ParseCSharpVersion(string? value) =>
        !string.IsNullOrWhiteSpace(value) && CS.LanguageVersionFacts.TryParse(value.Trim(), out var parsed) ? parsed : CS.LanguageVersion.Preview;

    private static VB.LanguageVersion ParseVbVersion(string? value)
    {
        var parsed = VB.LanguageVersion.Latest;
        return !string.IsNullOrWhiteSpace(value) && VB.LanguageVersionFacts.TryParse(value.Trim(), ref parsed) ? parsed : VB.LanguageVersion.Latest;
    }

    /// <summary>VB DefineConstants entries: NAME (True), NAME=-1, NAME=True, NAME="text".</summary>
    internal static IEnumerable<KeyValuePair<string, object>> ParseVbSymbols(IEnumerable<string> entries)
    {
        foreach (var raw in entries)
        {
            var entry = raw.Trim();
            if (entry.Length == 0) continue;
            var eq = entry.IndexOf('=');
            if (eq < 0)
            {
                yield return new(entry, true);
                continue;
            }
            var name = entry[..eq].Trim();
            var text = entry[(eq + 1)..].Trim();
            object value = text.Length >= 2 && text[0] == '"' && text[^1] == '"' ? text[1..^1]
                : bool.TryParse(text, out var b) ? b
                : int.TryParse(text, out var i) ? i
                : text;
            yield return new(name, value);
        }
    }
}
