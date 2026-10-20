using System.Text;
using System.Text.Json;
using Microsoft.CodeAnalysis;
using RoslynToRdf.Cli;
using RoslynToRdf.Core.Extraction;
using RoslynToRdf.Core.Model;

namespace RoslynToRdf.Tests;

[Collection("ProcessConsole")]
public class DeclarationIndexerTests
{
    private static string WriteFiles(params (string Name, string Text)[] files)
    {
        var dir = Path.Combine(Path.GetTempPath(), "roslyn2rdf-tests", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(dir);
        foreach (var (name, text) in files)
            File.WriteAllText(Path.Combine(dir, name), text);
        return dir;
    }

    private static DeclarationIndex Index(string language, IEnumerable<string> symbols, params (string Name, string Text)[] files)
    {
        var dir = WriteFiles(files);
        return DeclarationIndexer.Index(new DeclarationRequest(language, null, symbols.ToList(),
            files.Select(f => Path.Combine(dir, f.Name)).ToList(), language == "VB" ? "Root" : null));
    }

    private static string[] Names(DeclarationIndex index) => index.Types.Select(t => t.Name).Distinct().ToArray();

    public static TheoryData<string, string[]> CSharpCases => new()
    {
        { "namespace A.B { class C { } namespace D { struct E { } } }", ["A.B.C", "A.B.D.E"] },
        { "namespace A.B;\npublic interface I { }\npublic enum E { X }", ["A.B.E", "A.B.I"] },
        { "namespace N; class Outer<T> { class Inner<U> { } struct S { } }", ["N.Outer<T>", "N.Outer<T>.Inner<U>", "N.Outer<T>.S"] },
        { "namespace N; record R(int X); record struct S(int Y); readonly record struct T; delegate int D<T>(T x);", ["N.D<T>", "N.R", "N.S", "N.T"] },
        { "class Global { } namespace N { class Dictionary<TKey, TValue> { } }", ["Global", "N.Dictionary<TKey, TValue>"] },
        { "namespace N; // class Comment { }\n/* class Block { } */ class Real { string s = \"class Str { }\"; string v = @\"class V { }\"; }", ["N.Real"] },
    };

    [Theory]
    [MemberData(nameof(CSharpCases))]
    public void CSharp_names_and_nesting(string source, string[] expected)
    {
        var index = Index("C#", [], ("a.cs", source));
        Assert.Equal(expected, Names(index));
        Assert.Equal(0, index.ParseErrors);
    }

    public static TheoryData<string[], string[]> IfCases => new()
    {
        { ["FOO"], ["N.Always", "N.Foo", "N.FooNested"] },
        { [], ["N.Always", "N.Neither"] },
        { ["BAR"], ["N.Always", "N.Bar"] },
        { ["FOO", "BAR", "BAZ"], ["N.Always", "N.Foo", "N.FooBaz", "N.FooNested"] },
    };

    [Theory]
    [MemberData(nameof(IfCases))]
    public void CSharp_preprocessor_branches(string[] symbols, string[] expected)
    {
        const string source = @"namespace N
{
    class Always { }
#if FOO
    class Foo { }
#  if BAZ
    class FooBaz { }
#  endif
    class FooNested { }
#elif BAR
    class Bar { }
#else
    class Neither { void M() { if (true) { { } } }
#endif
}
";
        Assert.Equal(expected, Names(Index("C#", symbols, ("a.cs", source))));
    }

    [Fact]
    public void CSharp_braces_inside_an_inactive_branch_do_not_break_nesting()
    {
        // B0: CameraExtensions.cs opens a class body in both #if branches; a brace counter without the symbols nests wrongly.
        const string source = @"namespace N
{
#if TT3
    public static class CameraExtensions
    {
#else
    public static class CameraExtensionsLegacy
    {
#endif
        public static void M() { }
    }
    public class After { }
}
";
        Assert.Equal(new[] { "N.After", "N.CameraExtensions" }, Names(Index("C#", ["TT3"], ("a.cs", source))));
        Assert.Equal(new[] { "N.After", "N.CameraExtensionsLegacy" }, Names(Index("C#", [], ("a.cs", source))));
    }

    [Fact]
    public void Partial_types_list_every_declaring_file_with_lines()
    {
        var index = Index("C#", [], ("a.cs", "namespace N;\n\npartial class P { }"), ("b.cs", "namespace N { partial class P { } }"));
        var entries = index.Types.Where(t => t.Name == "N.P").ToList();
        Assert.Equal(new[] { "a.cs", "b.cs" }, entries.Select(e => Path.GetFileName(e.File)).ToArray());
        Assert.Equal(new[] { 3, 1 }, entries.Select(e => e.Line).ToArray());
        Assert.All(entries, e => Assert.Equal("Class", e.Kind));
    }

    [Fact]
    public void Missing_files_are_reported_and_skipped()
    {
        var dir = WriteFiles(("a.cs", "class A { }"));
        var index = DeclarationIndexer.Index(new DeclarationRequest("C#", "latest", [], [Path.Combine(dir, "a.cs"), Path.Combine(dir, "gone.cs")]));
        Assert.Equal(new[] { "A" }, Names(index));
        Assert.Equal(new[] { Path.Combine(dir, "gone.cs") }, index.MissingFiles);
    }

    [Fact]
    public void Newer_language_versions_than_this_Roslyn_parse_as_preview()
    {
        var dir = WriteFiles(("a.cs", "namespace N; class A { }"));
        var index = DeclarationIndexer.Index(new DeclarationRequest("C#", "99", [], [Path.Combine(dir, "a.cs")]));
        Assert.Equal("Preview", index.LanguageVersion);
        Assert.Equal(new[] { "N.A" }, Names(index));
    }

    [Fact]
    public void VisualBasic_namespaces_partial_classes_modules_and_root_namespace()
    {
        var index = Index("VB", [],
            ("a.vb", "Namespace Data\n  Public Partial Class Widget(Of T)\n    Public Class Part\n    End Class\n  End Class\n  Public Module Helpers\n  End Module\n  Public Structure Point\n  End Structure\nEnd Namespace\n"),
            ("b.vb", "Namespace Data\n  Partial Class Widget(Of T)\n  End Class\nEnd Namespace\nPublic Interface IShape\nEnd Interface\n"));
        Assert.Equal(new[] { "Root.Data.Helpers", "Root.Data.Point", "Root.Data.Widget<T>", "Root.Data.Widget<T>.Part", "Root.IShape" }, Names(index));
        Assert.Equal("Class", index.Types.Single(t => t.Name == "Root.Data.Helpers").Kind);
        Assert.Equal(2, index.Types.Count(t => t.Name == "Root.Data.Widget<T>"));
    }

    [Theory]
    [InlineData(new[] { "TT3=-1", "CONFIG=\"Debug\"" }, "Root.OnlyTT3")]
    [InlineData(new[] { "TT3=True" }, "Root.OnlyTT3")]
    [InlineData(new[] { "TT3" }, "Root.OnlyTT3")]
    [InlineData(new[] { "TT3=0" }, "Root.NotTT3")]
    [InlineData(new string[0], "Root.NotTT3")]
    public void VisualBasic_if_uses_define_constants_values(string[] symbols, string expected)
    {
        const string source = "#If TT3 Then\nPublic Class OnlyTT3\nEnd Class\n#Else\nPublic Class NotTT3\nEnd Class\n#End If\n";
        Assert.Equal(new[] { expected }, Names(Index("VB", symbols, ("a.vb", source))));
    }

    [Fact]
    public void Names_equal_the_extractor_full_names_for_the_same_source()
    {
        const string source = @"
namespace Sample.Deep
{
    public class Outer<T> { public class Inner<U> { } public enum Mode { A } }
    public interface IRepo<TKey, TValue> where TKey : notnull { }
    public record Person(string Name);
    public record struct Point(int X);
    public delegate void Handler<T>(T value);
    internal static class Helpers { }
}
public class TopLevel { }
";
        var compilation = TestUtilities.CreateCompilation(source, "DeclarationNames");
        var emitter = new TestEmitter();
        new AssemblyGraphExtractor(emitter, new ExtractionOptions { BaseUri = "http://test.example/", IncludePrivate = true, IncludeInternal = true })
            .Extract(compilation, compilation.Assembly);
        var minter = new IriMinter("http://test.example/");
        var own = new List<INamedTypeSymbol>();
        void Collect(INamespaceOrTypeSymbol container)
        {
            foreach (var member in container.GetMembers())
            {
                if (member is INamespaceSymbol ns) Collect(ns);
                else if (member is INamedTypeSymbol type && !type.IsImplicitlyDeclared) { own.Add(type); Collect(type); }
            }
        }
        Collect(compilation.Assembly.GlobalNamespace);
        var fullName = minter.OntologyPrefix + DotNetOntology.TypeProps.FullName;
        var extracted = own.Select(t => emitter.Triples.Single(x => x.Subject == minter.Type(t) && x.Predicate == fullName).Object)
            .OrderBy(n => n, StringComparer.Ordinal).ToArray();

        var declared = Names(Index("C#", [], ("a.cs", source)));
        Assert.Equal(extracted, declared);
    }

    [Fact]
    public async Task Cli_declarations_reads_a_request_and_writes_json()
    {
        var dir = WriteFiles(("a.cs", "namespace N;\n#if X\nclass Y { }\n#endif\nclass Z { }"));
        var request = Path.Combine(dir, "request.json");
        var output = Path.Combine(dir, "out", "response.json");
        File.WriteAllText(request, JsonSerializer.Serialize(new
        {
            language = "C#", langVersion = "12", preprocessorSymbols = new[] { "X" }, files = new[] { Path.Combine(dir, "a.cs") },
        }));

        var originalErr = Console.Error;
        using var err = new StringWriter(new StringBuilder());
        Console.SetError(err);
        int exitCode;
        try { exitCode = await Program.Main(["declarations", "--request", request, "--output", output]); }
        finally { Console.SetError(originalErr); }

        Assert.Equal(0, exitCode);
        using var doc = JsonDocument.Parse(File.ReadAllText(output));
        var root = doc.RootElement;
        Assert.Equal("declarations", root.GetProperty("type").GetString());
        Assert.Equal("CSharp12", root.GetProperty("languageVersion").GetString());
        Assert.Equal(new[] { "N.Y", "N.Z" }, root.GetProperty("types").EnumerateArray().Select(t => t.GetProperty("name").GetString()!).ToArray());
        var first = root.GetProperty("types")[0];
        Assert.Equal(3, first.GetProperty("line").GetInt32());
        Assert.Equal("Class", first.GetProperty("kind").GetString());
    }

    [Fact]
    public async Task Cli_declarations_rejects_an_unknown_language()
    {
        var dir = WriteFiles();
        var request = Path.Combine(dir, "request.json");
        File.WriteAllText(request, "{\"language\":\"F#\",\"files\":[]}");
        var originalErr = Console.Error;
        using var err = new StringWriter(new StringBuilder());
        Console.SetError(err);
        int exitCode;
        try { exitCode = await Program.Main(["declarations", "--request", request, "--output", Path.Combine(dir, "o.json")]); }
        finally { Console.SetError(originalErr); }
        Assert.Equal(1, exitCode);
        Assert.Contains("Unsupported language", err.ToString());
    }
}
