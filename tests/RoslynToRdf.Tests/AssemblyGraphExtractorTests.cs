using Microsoft.CodeAnalysis;
using RoslynToRdf.Core.Extraction;
using RoslynToRdf.Core.Model;

namespace RoslynToRdf.Tests;

public class AssemblyGraphExtractorTests
{
    [Fact]
    public void Extract_EmitsTypeAndMembers()
    {
        var source = @"
using System;
namespace Sample;
public class C
{
    public int Field;
    public event EventHandler? Ev;
    public int Prop { get; set; }
    public void M(string s) { }
}
";

        var compilation = TestUtilities.CreateCompilation(source, "ExtractorBasic");
        var emitter = new TestEmitter();
        var options = new ExtractionOptions
        {
            BaseUri = "http://test.example/",
            IncludePrivate = true,
            IncludeInternal = true,
            IncludeAttributes = false,
            IncludeExternalTypes = true,
            ExtractExceptions = false,
            ExtractSeeAlso = false
        };

        var extractor = new AssemblyGraphExtractor(emitter, options);
        extractor.Extract(compilation, compilation.Assembly);

        var minter = new IriMinter("http://test.example/");
        var type = compilation.GetTypeByMetadataName("Sample.C")!;
        var typeIri = minter.Type(type);

        var rdfType = DotNetOntology.Rdf + "type";
        var typeClass = minter.OntologyPrefix + DotNetOntology.Classes.Class;

        Assert.Contains(emitter.Triples, t => t.Subject == typeIri && t.Predicate == rdfType && t.Object == typeClass && t.IsIri);

        var method = type.GetMembers("M").OfType<IMethodSymbol>().Single();
        var methodIri = minter.Member(method);
        var hasMember = minter.OntologyPrefix + DotNetOntology.TypeRels.HasMember;

        Assert.Contains(emitter.Triples, t => t.Subject == typeIri && t.Predicate == hasMember && t.Object == methodIri);
    }

    [Fact]
    public void Extract_ExternalTypes_AreReferencedButNotEmitted_WhenDisabled()
    {
        var source = @"
using System.Collections.Generic;
namespace Sample;
public class C
{
    public List<int> Prop { get; }
}
";

        var compilation = TestUtilities.CreateCompilation(source, "ExtractorExternal");
        var emitter = new TestEmitter();
        var options = new ExtractionOptions
        {
            BaseUri = "http://test.example/",
            IncludeExternalTypes = false,
            IncludeAttributes = false,
            ExtractExceptions = false,
            ExtractSeeAlso = false
        };

        var extractor = new AssemblyGraphExtractor(emitter, options);
        extractor.Extract(compilation, compilation.Assembly);

        var minter = new IriMinter("http://test.example/");
        var listType = compilation.GetTypeByMetadataName("System.Collections.Generic.List`1")!;
        var listIri = minter.Type(listType);

        var rdfType = DotNetOntology.Rdf + "type";
        var anyTypeTriple = emitter.Triples.Any(t => t.Subject == listIri && t.Predicate == rdfType);

        Assert.False(anyTypeTriple);
    }
}
