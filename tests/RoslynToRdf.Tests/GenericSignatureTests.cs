using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using System.Text.RegularExpressions;
using RoslynToRdf.Core.Extraction;
using RoslynToRdf.Core.Model;

namespace RoslynToRdf.Tests;

public class GenericSignatureTests
{
    private const string Source = """
        using System.Collections.Generic;
        public class Box<T> { public class Inner<U> { } }
        public class C<A, B>
        {
            public void M<T, U>(List<T> value) { }
            public void M<T, U>(List<U> value) { }
            public void N<T>(List<T> value) { }
            public void N<T>(List<A> value) { }
            public void P(List<A> value) { }
            public void P(List<B> value) { }
            public void Q<T, U>(Box<T>.Inner<U[]> value) { }
            public void Q<T, U>(Box<U>.Inner<T[]> value) { }
            public static implicit operator List<A>(C<A, B> value) => null;
            public static implicit operator List<B>(C<A, B> value) => null;
            public int this[List<A> value] => 0;
            public int this[List<B> value] => 0;
        }
        public class Outer<A, Extra>
        {
            public class Inner<B>
            {
                public void M(List<A> value) { }
                public void M(List<B> value) { }
            }
        }
        """;

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void Member_OpenGenericSignatures_PreserveArgumentsAndParameterOwners(bool fromMetadata)
    {
        var compilation = CreateCompilation(fromMetadata);
        var minter = new IriMinter();

        foreach (var (typeName, memberName) in OverloadGroups())
        {
            var members = compilation.GetTypeByMetadataName(typeName)!.GetMembers(memberName);
            Assert.Equal(2, members.Length);
            Assert.Equal(2, members.Select(minter.Member).Distinct().Count());
        }

        var methods = compilation.GetTypeByMetadataName("C`2")!.GetMembers("M").OfType<IMethodSymbol>().ToArray();
        Assert.Contains("System.Collections.Generic.List`1[``0]", Uri.UnescapeDataString(minter.Member(methods[0])));
        Assert.Contains("System.Collections.Generic.List`1[``1]", Uri.UnescapeDataString(minter.Member(methods[1])));
        var nestedMethods = compilation.GetTypeByMetadataName("Outer`2+Inner`1")!.GetMembers("M").OfType<IMethodSymbol>().ToArray();
        Assert.Contains("System.Collections.Generic.List`1[`0]", Uri.UnescapeDataString(minter.Member(nestedMethods[0])));
        Assert.Contains("System.Collections.Generic.List`1[`2]", Uri.UnescapeDataString(minter.Member(nestedMethods[1])));
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void Extract_OpenGenericSignatures_PreserveMemberAndParameterNodes(bool fromMetadata)
    {
        var compilation = CreateCompilation(fromMetadata);
        var type = compilation.GetTypeByMetadataName("C`2")!;
        var emitter = new TestEmitter();
        var options = new ExtractionOptions { IncludeAttributes = false };
        new AssemblyGraphExtractor(emitter, options).Extract(compilation, type.ContainingAssembly);
        var minter = new IriMinter(options.BaseUri);

        foreach (var (typeName, memberName) in OverloadGroups())
        {
            var owner = compilation.GetTypeByMetadataName(typeName)!;
            var members = owner.GetMembers(memberName);
            var subjects = emitter.Triples.Where(triple => triple.Predicate == minter.OntologyPrefix + DotNetOntology.MemberProps.Name
                && triple.Object == memberName && triple.Subject.StartsWith(minter.Type(owner) + "/member/"))
                .Select(triple => triple.Subject).Distinct().ToArray();
            Assert.Equal(2, subjects.Length);

            foreach (var member in members)
            {
                var memberIri = minter.Member(member);
                Assert.Contains(memberIri, subjects);
                var parameter = Assert.Single(emitter.Triples.Where(triple => triple.Subject == memberIri
                    && triple.Predicate == minter.OntologyPrefix + DotNetOntology.MemberRels.HasParameter));
                Assert.Single(emitter.Triples.Where(triple => triple.Predicate == parameter.Predicate && triple.Object == parameter.Object));
                var typeParameters = emitter.Triples.Where(triple => triple.Subject == memberIri
                    && triple.Predicate == minter.OntologyPrefix + DotNetOntology.MemberRels.HasTypeParameter).ToArray();
                Assert.Equal(member is IMethodSymbol method ? method.Arity : 0, typeParameters.Length);
            }
        }

        var conversions = type.GetMembers("op_Implicit").OfType<IMethodSymbol>().ToArray();
        Assert.Equal(minter.Type(conversions[0].ReturnType), minter.Type(conversions[1].ReturnType));
        foreach (var conversion in conversions)
        {
            var returnType = Assert.Single(emitter.Triples.Where(triple => triple.Subject == minter.Member(conversion)
                && triple.Predicate == minter.OntologyPrefix + DotNetOntology.MemberRels.ReturnType));
            Assert.Equal(minter.Type(conversion.ReturnType), returnType.Object);
        }
    }

    [Fact]
    public void Member_ClosedGenericArguments_KeepExistingSignature()
    {
        var compilation = TestUtilities.CreateCompilation("""
            public class C { public void M(System.Collections.Generic.List<int> values) { } }
            """);
        var type = compilation.GetTypeByMetadataName("C")!;
        var minter = new IriMinter();

        Assert.Equal(minter.Type(type) + "/member/M(System.Collections.Generic.List`1[System.Int32])",
            Uri.UnescapeDataString(minter.Member(type.GetMembers("M").Single())));
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void Member_FunctionPointerSignatures_PreserveParameterOwnersAndCallingConventions(bool fromMetadata)
    {
        var compilation = CreateCompilation(fromMetadata, """
            public unsafe class C<T>
            {
                public void M<U>(delegate*<T, void> value) { }
                public void M<T>(delegate*<T, void> value) { }
                public void N<U>(delegate*<ref T, ref T> value) { }
                public void N<T>(delegate*<ref T, ref T> value) { }
                public void Convention(delegate* unmanaged[Cdecl]<int, void> value) { }
                public void Convention(delegate* unmanaged[Stdcall]<int, void> value) { }
            }
            """, allowUnsafe: true);
        var type = compilation.GetTypeByMetadataName("C`1")!;
        var minter = new IriMinter();
        var emitter = new TestEmitter();
        new AssemblyGraphExtractor(emitter, new ExtractionOptions { IncludeAttributes = false })
            .Extract(compilation, type.ContainingAssembly);

        foreach (var name in new[] { "M", "N", "Convention" })
        {
            var methods = type.GetMembers(name).OfType<IMethodSymbol>().ToArray();
            Assert.Equal(2, methods.Length);
            Assert.Equal(2, methods.Select(minter.Member).Distinct().Count());
            var subjects = emitter.Triples.Where(triple => triple.Predicate == minter.OntologyPrefix + DotNetOntology.MemberProps.Name
                && triple.Object == name).Select(triple => triple.Subject).Distinct();
            Assert.Equal(2, subjects.Count());
        }
    }

    [Fact]
    public void Member_GenericParameterNames_SourceMetadataAndRenamingKeepIdentity()
    {
        var source = CreateCompilation(false);
        var metadata = CreateCompilation(true);
        var renamed = TestUtilities.CreateCompilation(Regex.Replace(Regex.Replace(Source, @"\bT\b", "First"), @"\bU\b", "Second"));
        Assert.DoesNotContain(renamed.GetDiagnostics(), diagnostic => diagnostic.Severity == DiagnosticSeverity.Error);
        var minter = new IriMinter();

        foreach (var name in new[] { "M", "Q" })
        {
            var sourceIris = source.GetTypeByMetadataName("C`2")!.GetMembers(name).Select(minter.Member).ToArray();
            Assert.Equal(sourceIris, metadata.GetTypeByMetadataName("C`2")!.GetMembers(name).Select(minter.Member));
            Assert.Equal(sourceIris, renamed.GetTypeByMetadataName("C`2")!.GetMembers(name).Select(minter.Member));
        }
    }

    private static IEnumerable<(string TypeName, string MemberName)> OverloadGroups()
    {
        foreach (var name in new[] { "M", "N", "P", "Q", "op_Implicit", "this[]" })
            yield return ("C`2", name);
        yield return ("Outer`2+Inner`1", "M");
    }

    private static CSharpCompilation CreateCompilation(bool fromMetadata, string source = Source, bool allowUnsafe = false)
    {
        var compilation = TestUtilities.CreateCompilation(source, allowUnsafe: allowUnsafe);
        Assert.DoesNotContain(compilation.GetDiagnostics(), diagnostic => diagnostic.Severity == DiagnosticSeverity.Error);
        if (!fromMetadata)
            return compilation;

        using var stream = new MemoryStream();
        var result = compilation.Emit(stream);
        Assert.True(result.Success, string.Join(Environment.NewLine, result.Diagnostics));
        return TestUtilities.CreateCompilation("", "Consumer").AddReferences(MetadataReference.CreateFromImage(stream.ToArray()));
    }
}
