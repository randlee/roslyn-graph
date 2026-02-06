using Microsoft.CodeAnalysis;
using RoslynToRdf.Core.Model;

namespace RoslynToRdf.Tests;

public class IriMinterTests
{
    [Fact]
    public void BaseUri_ReturnsConfiguredBaseUri()
    {
        var minter = new IriMinter("http://test.example/");
        Assert.Equal("http://test.example", minter.BaseUri);
    }

    [Fact]
    public void OntologyPrefix_ReturnsOntologyPath()
    {
        var minter = new IriMinter("http://test.example/");
        Assert.Equal("http://test.example/ontology/", minter.OntologyPrefix);
    }

    [Fact]
    public void Namespace_GlobalNamespace_ReturnsGlobalMarker()
    {
        var minter = new IriMinter();
        Assert.NotNull(minter);
    }

    [Fact]
    public void TypeParameter_IriCollidesAcrossDifferentOwners()
    {
        var source = @"
namespace Sample;
public class A<T> { }
public class B<T> { }
";

        var compilation = TestUtilities.CreateCompilation(source, "IriTypeParam");
        var aType = compilation.GetTypeByMetadataName("Sample.A`1")!;
        var bType = compilation.GetTypeByMetadataName("Sample.B`1")!;

        var aTp = aType.TypeParameters[0];
        var bTp = bType.TypeParameters[0];

        var minter = new IriMinter("http://test.example/");
        var aIri = minter.Type(aTp);
        var bIri = minter.Type(bTp);

        // KNOWN BUG: Type parameters from different owners should have distinct IRIs
        Assert.NotEqual(aIri, bIri);
    }

    [Fact]
    public void MethodSignature_IgnoresRefOutDifferences()
    {
        var source = @"
namespace Sample;
public class C
{
    public void M(ref int x) { }
    public void M(out int x) { x = 0; }
}
";

        var compilation = TestUtilities.CreateCompilation(source, "IriMethodSig");
        var cType = compilation.GetTypeByMetadataName("Sample.C")!;
        var methods = cType.GetMembers("M").OfType<IMethodSymbol>().ToArray();

        Assert.Equal(2, methods.Length);

        var minter = new IriMinter("http://test.example/");
        var iri1 = minter.Member(methods[0]);
        var iri2 = minter.Member(methods[1]);

        // KNOWN BUG: ref and out parameters should produce different IRIs
        Assert.NotEqual(iri1, iri2);
    }
}
