using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using RoslynToRdf.Core.Emitters;
using RoslynToRdf.Core.Extraction;
using RoslynToRdf.Core.Model;
using RoslynToRdf.Cli;

namespace RoslynToRdf.Tests;

public class UnsafeAnalysisTests
{
    [Fact]
    public void Extraction_ReportsUnsafeFactsForAccessorsAndInheritedNestedTypeContext()
    {
        var source = """
            using System;
            public class C
            {
                public int Value
                {
                    get { unsafe { int* p = stackalloc int[1]; return *p; } }
                    set { unsafe { int* p = &value; } }
                }
                public int this[int index]
                {
                    get { unsafe { int* p = stackalloc int[1]; return *p; } }
                    set { unsafe { int* p = &value; } }
                }
                public event Action Changed
                {
                    add { unsafe { int* p = stackalloc int[1]; } }
                    remove { unsafe { int* p = stackalloc int[1]; } }
                }
            }
            public unsafe class Outer
            {
                public class Nested { public void Ordinary() { } }
            }
            """;
        var compilation = TestUtilities.CreateCompilation(source, "UnsafeAccessors", allowUnsafe: true);
        var emitter = new TestEmitter();
        new AssemblyGraphExtractor(emitter, new ExtractionOptions { IncludePrivate = true })
            .Extract(compilation, compilation.Assembly);

        var c = compilation.Assembly.GlobalNamespace.GetTypeMembers("C").Single();
        foreach (var property in c.GetMembers().OfType<IPropertySymbol>())
        {
            var accessors = new[] { property.GetMethod, property.SetMethod }.OfType<IMethodSymbol>();
            foreach (var accessor in accessors)
                AssertUnsafeAccessor(emitter, accessor);
        }
        var evt = c.GetMembers("Changed").OfType<IEventSymbol>().Single();
        AssertUnsafeAccessor(emitter, evt.AddMethod!);
        AssertUnsafeAccessor(emitter, evt.RemoveMethod!);
        var cIri = new IriMinter().Type(c);
        Assert.Contains(emitter.Triples, triple => triple.Subject == cIri
            && triple.Predicate.EndsWith("/containsUnsafeCode", StringComparison.Ordinal) && triple.Object == "true");

        var propertyIri = new IriMinter().Member(c.GetMembers("Value").OfType<IPropertySymbol>().Single());
        Assert.Equal(2, emitter.Triples.Count(triple => triple.Subject == propertyIri
            && triple.Predicate.EndsWith("/hasAccessor", StringComparison.Ordinal)));
        Assert.DoesNotContain(emitter.Triples, triple => triple.Subject == new IriMinter().Member(c.GetMembers("Value").OfType<IPropertySymbol>().Single().GetMethod!)
            && triple.Predicate.EndsWith("/type", StringComparison.Ordinal));

        var nested = compilation.Assembly.GlobalNamespace.GetTypeMembers("Outer").Single().GetTypeMembers("Nested").Single();
        var nestedIri = new IriMinter().Type(nested);
        Assert.Contains(emitter.Triples, triple => triple.Subject == nestedIri
            && triple.Predicate.EndsWith("/containsUnsafeCode", StringComparison.Ordinal) && triple.Object == "true");
        var ordinary = nested.GetMembers("Ordinary").OfType<IMethodSymbol>().Single();
        var ordinaryIri = new IriMinter().Member(ordinary);
        Assert.DoesNotContain(emitter.Triples, triple => triple.Subject == ordinaryIri
            && triple.Predicate.EndsWith("/containsUnsafeCode", StringComparison.Ordinal));
    }

    private static void AssertUnsafeAccessor(TestEmitter emitter, IMethodSymbol accessor)
    {
        var accessorIri = new IriMinter().Member(accessor);
        Assert.Contains(emitter.Triples, triple => triple.Subject == accessorIri
            && triple.Predicate.EndsWith("/containsUnsafeCode", StringComparison.Ordinal) && triple.Object == "true");
        Assert.Contains(emitter.Triples, triple => triple.Subject == accessorIri
            && triple.Predicate.EndsWith("/requiresUnsafeCompilation", StringComparison.Ordinal) && triple.Object == "true");
        var facts = emitter.Triples.Where(triple => triple.Subject == accessorIri
            && triple.Predicate.EndsWith("/hasUnsafeFact", StringComparison.Ordinal)).Select(triple => triple.Object).ToHashSet();
        Assert.NotEmpty(facts);
        var reasons = emitter.Triples.Where(triple => facts.Contains(triple.Subject)
            && triple.Predicate.EndsWith("/unsafeReason", StringComparison.Ordinal)).Select(triple => triple.Object).ToHashSet();
        Assert.Contains("UnsafeBlock", reasons);
        Assert.Contains("PointerType", reasons);
        Assert.Contains(emitter.Triples, triple => facts.Contains(triple.Subject)
            && triple.Predicate.EndsWith("/unsafeLocation", StringComparison.Ordinal));
    }

    [Fact]
    public void Extraction_ReportsUnsafeReasonsAndOmitsSafeStackalloc()
    {
        var source = """
            using System;
            using System.Collections.Generic;
            using System.Threading.Tasks;
            namespace UnsafeSample;
            public class SafeCases
            {
                public void Ordinary() { }
                public void SpanStackalloc() { Span<int> values = stackalloc int[4]; }
                public void ReadOnlySpanStackalloc() { ReadOnlySpan<int> values = stackalloc int[4]; }
            }
            public unsafe class UnsafeCases
            {
                public void InheritedContext() { }
                public unsafe void Modified() { }
                public void Block() { unsafe { int* p = null; } }
                public int* Pointer(int* value) => value;
                public void FunctionPointer(delegate* unmanaged[Cdecl]<int, int> callback) { _ = callback(1); }
                public void Fixed(int[] values) { fixed (int* p = values) { _ = *p; } }
                public void Address() { int value = 0; int* pointer = &value; }
                public int PointerMember(Sample* pointer) => pointer->Value;
                public void PointerStackalloc() { int* values = stackalloc int[4]; }
                public int Generic<T>(T value) => value is null ? 0 : 1;
                public async Task<int> Async() => await Task.FromResult(1);
                public IEnumerable<int> Iterator() { yield return 1; }
                public void NestedExecutables()
                {
                    Action lambda = () => { unsafe { int* p = null; } };
                    void Local() { unsafe { int* p = null; } }
                    Local();
                }
                public class NestedType { public void NestedMethod() { } }
            }
            public static unsafe class SpanExtensionsBCL
            {
                public static Span<int> AsSpan(int[] values) => values;
            }
            """;
        var compilation = TestUtilities.CreateCompilation(source + "\npublic struct Sample { public int Value; }", "UnsafeCases", allowUnsafe: true);
        compilation = compilation.AddSyntaxTrees(CSharpSyntaxTree.ParseText(
            "namespace UnsafeSample; public unsafe class GeneratedCases { public void GeneratedPointer(int* p) { } }",
            path: "Generated.g.cs"));
        var emitter = new TestEmitter();

        new AssemblyGraphExtractor(emitter, new ExtractionOptions { IncludePrivate = true })
            .Extract(compilation, compilation.Assembly);

        AssertMethodUnsafe(compilation, emitter, "Ordinary", false);
        AssertMethodUnsafe(compilation, emitter, "SpanStackalloc", false);
        AssertMethodUnsafe(compilation, emitter, "ReadOnlySpanStackalloc", false);
        AssertMethodUnsafe(compilation, emitter, "InheritedContext", false);
        AssertMethodUnsafe(compilation, emitter, "Modified", true, "UnsafeMethodModifier");
        AssertMethodUnsafe(compilation, emitter, "Block", true, "UnsafeBlock", "PointerType");
        AssertMethodUnsafe(compilation, emitter, "Pointer", true, "PointerType");
        AssertMethodUnsafe(compilation, emitter, "FunctionPointer", true, "FunctionPointerType");
        AssertMethodUnsafe(compilation, emitter, "Fixed", true, "FixedStatement", "PointerType", "PointerDereference");
        AssertMethodUnsafe(compilation, emitter, "Address", true, "PointerAddressOf", "PointerType");
        AssertMethodUnsafe(compilation, emitter, "PointerMember", true, "PointerMemberAccess", "PointerType");
        AssertMethodUnsafe(compilation, emitter, "PointerStackalloc", true, "PointerStackAlloc", "PointerType");
        AssertMethodUnsafe(compilation, emitter, "Generic", false);
        AssertMethodUnsafe(compilation, emitter, "Async", false);
        AssertMethodUnsafe(compilation, emitter, "Iterator", false);
        AssertMethodUnsafe(compilation, emitter, "NestedExecutables", true, "UnsafeBlock");
        AssertMethodUnsafe(compilation, emitter, "NestedMethod", false);
        AssertMethodUnsafe(compilation, emitter, "GeneratedPointer", true, "PointerType");
        AssertMethodUnsafe(compilation, emitter, "AsSpan", false);

        var unsafeClass = GetType(compilation, "UnsafeCases");
        var unsafeClassIri = new IriMinter().Type(unsafeClass);
        Assert.Contains(emitter.Triples, triple => triple.Subject == unsafeClassIri
                                                   && triple.Predicate.EndsWith("/containsUnsafeCode", StringComparison.Ordinal)
                                                   && triple.Object == "true");
        var spanExtensions = compilation.Assembly.GlobalNamespace.GetNamespaceMembers()
            .Single(ns => ns.Name == "UnsafeSample").GetTypeMembers("SpanExtensionsBCL").Single();
        var spanExtensionsIri = new IriMinter().Type(spanExtensions);
        Assert.Contains(emitter.Triples, triple => triple.Subject == spanExtensionsIri
                                                   && triple.Predicate.EndsWith("/containsUnsafeCode", StringComparison.Ordinal)
                                                   && triple.Object == "true");
        var assemblyIri = new IriMinter().Assembly(compilation.Assembly);
        Assert.Contains(emitter.Triples, triple => triple.Subject == assemblyIri
                                                   && triple.Predicate.EndsWith("/containsUnsafeCode", StringComparison.Ordinal)
                                                   && triple.Object == "true");
        Assert.Contains(emitter.Triples, triple => triple.Predicate.EndsWith("/unsafeLocation", StringComparison.Ordinal)
                                                   && triple.Object.StartsWith("<source>:", StringComparison.Ordinal));
    }

    [Fact]
    public void Extraction_SkipsUnsafeAnalysisWhenCompilationDisallowsUnsafe()
    {
        var compilation = TestUtilities.CreateCompilation(
            "public class C { public unsafe void M() { int* pointer = null; } }", "UnsafeDisabled", allowUnsafe: false);
        var emitter = new TestEmitter();

        new AssemblyGraphExtractor(emitter, new ExtractionOptions { IncludePrivate = true })
            .Extract(compilation, compilation.Assembly);

        Assert.DoesNotContain(emitter.Triples, triple => triple.Predicate.EndsWith("/containsUnsafeCode", StringComparison.Ordinal));
        Assert.DoesNotContain(emitter.Triples, triple => triple.Predicate.EndsWith("/unsafeReason", StringComparison.Ordinal));
    }

    [Fact]
    public void Extraction_AllowsUnsafeOptionWithoutFlaggingSafeMethodsOrAggregates()
    {
        var compilation = TestUtilities.CreateCompilation(
            "using System; public class C { public void M() { Span<int> values = stackalloc int[2]; } }",
            "SafeUnsafeEnabled", allowUnsafe: true);
        var emitter = new TestEmitter();

        new AssemblyGraphExtractor(emitter).Extract(compilation, compilation.Assembly);

        Assert.DoesNotContain(emitter.Triples, triple => triple.Predicate.EndsWith("/containsUnsafeCode", StringComparison.Ordinal));
        Assert.DoesNotContain(emitter.Triples, triple => triple.Predicate.EndsWith("/unsafeReason", StringComparison.Ordinal));
    }

    [Fact]
    public async Task Cli_SourceProjectUsesEvaluatedAllowUnsafeBlocks()
    {
        var directory = Path.Combine(Path.GetTempPath(), "roslyn2rdf-unsafe-project", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(directory);
        try
        {
            var project = Path.Combine(directory, "UnsafeProject.csproj");
            var source = Path.Combine(directory, "Class1.cs");
            await File.WriteAllTextAsync(source, "public unsafe class C { public void M(int* pointer) { } }");
            await File.WriteAllTextAsync(project, "<Project Sdk=\"Microsoft.NET.Sdk\"><PropertyGroup><TargetFramework>net8.0</TargetFramework><AllowUnsafeBlocks>true</AllowUnsafeBlocks></PropertyGroup></Project>");
            var output = Path.Combine(directory, "unsafe.nt");

            var result = await Program.Main([project, "--output", output, "--quiet"]);

            Assert.Equal(0, result);
            var graph = await File.ReadAllTextAsync(output);
            Assert.Contains("containsUnsafeCode", graph);
            Assert.Contains("unsafeReason", graph);
            Assert.Contains("Class1.cs", graph);

            await File.WriteAllTextAsync(project, "<Project Sdk=\"Microsoft.NET.Sdk\"><PropertyGroup><TargetFramework>net8.0</TargetFramework><AllowUnsafeBlocks>false</AllowUnsafeBlocks></PropertyGroup></Project>");
            var disabledOutput = Path.Combine(directory, "disabled.nt");
            result = await Program.Main([project, "--output", disabledOutput, "--quiet"]);
            Assert.Equal(0, result);
            var disabledGraph = await File.ReadAllTextAsync(disabledOutput);
            Assert.DoesNotContain("unsafeReason", disabledGraph);
            Assert.DoesNotContain("containsUnsafeCode", disabledGraph);
        }
        finally
        {
            Directory.Delete(directory, recursive: true);
        }
    }

    private static void AssertMethodUnsafe(
        Compilation compilation,
        TestEmitter emitter,
        string name,
        bool expected,
        params string[] expectedReasons)
    {
        var method = GetType(compilation, "UnsafeCases")
            .GetMembers(name).OfType<IMethodSymbol>().SingleOrDefault()
            ?? GetType(compilation, "SafeCases")
                .GetMembers(name).OfType<IMethodSymbol>().SingleOrDefault()
            ?? compilation.Assembly.GlobalNamespace.GetNamespaceMembers().Single(ns => ns.Name == "UnsafeSample")
                .GetTypeMembers("GeneratedCases").SingleOrDefault()?
                .GetMembers(name).OfType<IMethodSymbol>().SingleOrDefault()
            ?? compilation.Assembly.GlobalNamespace.GetNamespaceMembers().Single(ns => ns.Name == "UnsafeSample")
                .GetTypeMembers("SpanExtensionsBCL").SingleOrDefault()?.GetMembers(name).OfType<IMethodSymbol>().SingleOrDefault()
            ?? GetType(compilation, "UnsafeCases")
                .GetTypeMembers("NestedType").SingleOrDefault()?.GetMembers(name).OfType<IMethodSymbol>().SingleOrDefault();
        Assert.NotNull(method);
        var methodIri = new IriMinter().Member(method!);
        var facts = emitter.Triples.Where(triple => triple.Subject == methodIri).ToArray();
        Assert.Equal(expected, facts.Any(triple => triple.Predicate.EndsWith("/containsUnsafeCode", StringComparison.Ordinal)
                                                   && triple.Object == "true"));
        if (!expected)
            return;
        Assert.Contains(facts, triple => triple.Predicate.EndsWith("/requiresUnsafeCompilation", StringComparison.Ordinal)
                                         && triple.Object == "true");
        var factIris = facts.Where(triple => triple.Predicate.EndsWith("/hasUnsafeFact", StringComparison.Ordinal))
            .Select(triple => triple.Object).ToHashSet(StringComparer.Ordinal);
        var reasons = emitter.Triples.Where(triple => factIris.Contains(triple.Subject)
                                                       && triple.Predicate.EndsWith("/unsafeReason", StringComparison.Ordinal))
            .Select(triple => triple.Object).ToHashSet(StringComparer.Ordinal);
        foreach (var reason in expectedReasons)
            Assert.Contains(reason, reasons);
    }

    private static INamedTypeSymbol GetType(Compilation compilation, string name) =>
        compilation.Assembly.GlobalNamespace.GetNamespaceMembers().Single(ns => ns.Name == "UnsafeSample")
            .GetTypeMembers(name).Single();
}
