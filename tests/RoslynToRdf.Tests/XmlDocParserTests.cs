using Microsoft.CodeAnalysis;
using RoslynToRdf.Core.Extraction;

namespace RoslynToRdf.Tests;

public class XmlDocParserTests
{
    [Fact]
    public void GetExceptionTypes_ReturnsExceptionFromXmlDoc()
    {
        var source = @"
namespace Sample;
public class C
{
    /// <summary>Test</summary>
    /// <exception cref=""System.ArgumentNullException"" />
    public void M(string s) { }
}
";

        var compilation = TestUtilities.CreateCompilation(source, "XmlDocExceptions");
        var type = compilation.GetTypeByMetadataName("Sample.C")!;
        var method = type.GetMembers("M").OfType<IMethodSymbol>().Single();

        var parser = new XmlDocParser(compilation);
        var exTypes = parser.GetExceptionTypes(method).ToArray();

        Assert.Single(exTypes);
        Assert.Equal("System.ArgumentNullException", exTypes[0].ToDisplayString());
    }

    [Fact]
    public void GetSeeAlsoReferences_ReturnsTypeFromXmlDoc()
    {
        var source = @"
namespace Sample;
public class D { }
public class C
{
    /// <summary>Test</summary>
    /// <seealso cref=""Sample.D"" />
    public void M() { }
}
";

        var compilation = TestUtilities.CreateCompilation(source, "XmlDocSeeAlso");
        var type = compilation.GetTypeByMetadataName("Sample.C")!;
        var method = type.GetMembers("M").OfType<IMethodSymbol>().Single();

        var parser = new XmlDocParser(compilation);
        var refs = parser.GetSeeAlsoReferences(method).ToArray();

        Assert.Single(refs);
        Assert.Equal("Sample.D", refs[0].ToDisplayString());
    }
}
