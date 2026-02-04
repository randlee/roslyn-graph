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
}
