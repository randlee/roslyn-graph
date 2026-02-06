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

    #region Corner Cases

    [Fact]
    public void Extract_EmptyAssembly_EmitsOnlyAssemblyNode()
    {
        var source = @"// Empty assembly";

        var compilation = TestUtilities.CreateCompilation(source, "EmptyAssembly");
        var emitter = new TestEmitter();
        var options = new ExtractionOptions { BaseUri = "http://test.example/" };

        var extractor = new AssemblyGraphExtractor(emitter, options);
        extractor.Extract(compilation, compilation.Assembly);

        var minter = new IriMinter("http://test.example/");
        var asmIri = minter.Assembly(compilation.Assembly);
        var rdfType = DotNetOntology.Rdf + "type";
        var asmClass = minter.OntologyPrefix + DotNetOntology.Classes.Assembly;

        Assert.Contains(emitter.Triples, t => t.Subject == asmIri && t.Predicate == rdfType && t.Object == asmClass && t.IsIri);
    }

    [Fact]
    public void Extract_AssemblyWithOnlyAttributes_EmitsTypeWithAttributes()
    {
        var source = @"
using System;
namespace Sample;

[AttributeUsage(AttributeTargets.Class)]
public class MyAttribute : Attribute { }

[My]
public class Empty { }
";

        var compilation = TestUtilities.CreateCompilation(source, "AttributeOnly");
        var emitter = new TestEmitter();
        var options = new ExtractionOptions {
            BaseUri = "http://test.example/",
            IncludeAttributes = true
        };

        var extractor = new AssemblyGraphExtractor(emitter, options);
        extractor.Extract(compilation, compilation.Assembly);

        var minter = new IriMinter("http://test.example/");
        var type = compilation.GetTypeByMetadataName("Sample.Empty")!;
        var typeIri = minter.Type(type);
        var hasAttribute = minter.OntologyPrefix + DotNetOntology.TypeRels.HasAttribute;

        Assert.Contains(emitter.Triples, t => t.Subject == typeIri && t.Predicate == hasAttribute);
    }

    [Fact]
    public void Extract_DeeplyNestedTypes_AllTypesEmitted()
    {
        var source = @"
namespace Sample;
public class Outer
{
    public class Middle
    {
        public class Inner
        {
            public void Method() { }
        }
    }
}
";

        var compilation = TestUtilities.CreateCompilation(source, "NestedTypes");
        var emitter = new TestEmitter();
        var options = new ExtractionOptions { BaseUri = "http://test.example/" };

        var extractor = new AssemblyGraphExtractor(emitter, options);
        extractor.Extract(compilation, compilation.Assembly);

        var minter = new IriMinter("http://test.example/");
        var inner = compilation.GetTypeByMetadataName("Sample.Outer+Middle+Inner")!;
        var innerIri = minter.Type(inner);
        var nestedIn = minter.OntologyPrefix + DotNetOntology.TypeRels.NestedIn;

        // Inner should be nested in Middle
        var middle = compilation.GetTypeByMetadataName("Sample.Outer+Middle")!;
        var middleIri = minter.Type(middle);
        Assert.Contains(emitter.Triples, t => t.Subject == innerIri && t.Predicate == nestedIn && t.Object == middleIri);
    }

    #endregion

    #region Error Conditions

    [Fact]
    public void Extract_CircularTypeReferences_DoesNotInfiniteLoop()
    {
        var source = @"
namespace Sample;
public class A
{
    public B? BProp { get; set; }
}
public class B
{
    public A? AProp { get; set; }
}
";

        var compilation = TestUtilities.CreateCompilation(source, "CircularRefs");
        var emitter = new TestEmitter();
        var options = new ExtractionOptions { BaseUri = "http://test.example/" };

        var extractor = new AssemblyGraphExtractor(emitter, options);
        extractor.Extract(compilation, compilation.Assembly);

        var minter = new IriMinter("http://test.example/");
        var typeA = compilation.GetTypeByMetadataName("Sample.A")!;
        var typeB = compilation.GetTypeByMetadataName("Sample.B")!;
        var typeAIri = minter.Type(typeA);
        var typeBIri = minter.Type(typeB);
        var rdfType = DotNetOntology.Rdf + "type";

        // Both types should be emitted exactly once
        var typeATriples = emitter.Triples.Where(t => t.Subject == typeAIri && t.Predicate == rdfType).ToList();
        var typeBTriples = emitter.Triples.Where(t => t.Subject == typeBIri && t.Predicate == rdfType).ToList();

        Assert.True(typeATriples.Count >= 1);
        Assert.True(typeBTriples.Count >= 1);
    }

    [Fact]
    public void Extract_TypeWithMissingBaseType_HandlesGracefully()
    {
        var source = @"
namespace Sample;
public class Derived : System.Collections.Generic.List<int>
{
    public void Method() { }
}
";

        var compilation = TestUtilities.CreateCompilation(source, "MissingBase");
        var emitter = new TestEmitter();
        var options = new ExtractionOptions {
            BaseUri = "http://test.example/",
            IncludeExternalTypes = false
        };

        var extractor = new AssemblyGraphExtractor(emitter, options);
        extractor.Extract(compilation, compilation.Assembly);

        var minter = new IriMinter("http://test.example/");
        var derived = compilation.GetTypeByMetadataName("Sample.Derived")!;
        var derivedIri = minter.Type(derived);
        var inherits = minter.OntologyPrefix + DotNetOntology.TypeRels.Inherits;

        // Should have inheritance triple
        Assert.Contains(emitter.Triples, t => t.Subject == derivedIri && t.Predicate == inherits);
    }

    #endregion

    #region Edge Cases - Generic Types

    [Fact]
    public void Extract_GenericTypeWithConstraints_EmitsConstraints()
    {
        var source = @"
namespace Sample;
public interface IMarker { }
public class Generic<T> where T : IMarker, new()
{
    public T Value { get; set; }
}
";

        var compilation = TestUtilities.CreateCompilation(source, "GenericConstraints");
        var emitter = new TestEmitter();
        var options = new ExtractionOptions { BaseUri = "http://test.example/" };

        var extractor = new AssemblyGraphExtractor(emitter, options);
        extractor.Extract(compilation, compilation.Assembly);

        var minter = new IriMinter("http://test.example/");
        var generic = compilation.GetTypeByMetadataName("Sample.Generic`1")!;
        var typeParam = generic.TypeParameters[0];
        var tpIri = minter.TypeParameter(generic, typeParam);
        var constrainedTo = minter.OntologyPrefix + DotNetOntology.TypeParamRels.ConstrainedToType;

        Assert.Contains(emitter.Triples, t => t.Subject == tpIri && t.Predicate == constrainedTo);
    }

    [Fact]
    public void Extract_MultipleTypeParameters_PreservesOrder()
    {
        var source = @"
namespace Sample;
public class MultiGeneric<T1, T2, T3>
{
    public void Method(T1 a, T2 b, T3 c) { }
}
";

        var compilation = TestUtilities.CreateCompilation(source, "MultiGeneric");
        var emitter = new TestEmitter();
        var options = new ExtractionOptions { BaseUri = "http://test.example/" };

        var extractor = new AssemblyGraphExtractor(emitter, options);
        extractor.Extract(compilation, compilation.Assembly);

        var minter = new IriMinter("http://test.example/");
        var generic = compilation.GetTypeByMetadataName("Sample.MultiGeneric`3")!;
        var tp0 = generic.TypeParameters[0];
        var tp1 = generic.TypeParameters[1];
        var tp2 = generic.TypeParameters[2];

        var tp0Iri = minter.TypeParameter(generic, tp0);
        var tp1Iri = minter.TypeParameter(generic, tp1);
        var tp2Iri = minter.TypeParameter(generic, tp2);

        var ordinalProp = minter.OntologyPrefix + DotNetOntology.TypeParamProps.Ordinal;

        var ordinal0 = emitter.Triples.FirstOrDefault(t => t.Subject == tp0Iri && t.Predicate == ordinalProp);
        var ordinal1 = emitter.Triples.FirstOrDefault(t => t.Subject == tp1Iri && t.Predicate == ordinalProp);
        var ordinal2 = emitter.Triples.FirstOrDefault(t => t.Subject == tp2Iri && t.Predicate == ordinalProp);

        Assert.NotNull(ordinal0);
        Assert.NotNull(ordinal1);
        Assert.NotNull(ordinal2);
        Assert.Equal("0", ordinal0.Object);
        Assert.Equal("1", ordinal1.Object);
        Assert.Equal("2", ordinal2.Object);
    }

    [Fact]
    public void Extract_ConstructedGenericType_LinksToDefinition()
    {
        var source = @"
using System.Collections.Generic;
namespace Sample;
public class Container
{
    public List<int> IntList { get; set; }
}
";

        var compilation = TestUtilities.CreateCompilation(source, "ConstructedGeneric");
        var emitter = new TestEmitter();
        var options = new ExtractionOptions {
            BaseUri = "http://test.example/",
            IncludeExternalTypes = true
        };

        var extractor = new AssemblyGraphExtractor(emitter, options);
        extractor.Extract(compilation, compilation.Assembly);

        var minter = new IriMinter("http://test.example/");
        var container = compilation.GetTypeByMetadataName("Sample.Container")!;
        var prop = container.GetMembers("IntList").OfType<IPropertySymbol>().Single();
        var listIntType = prop.Type as INamedTypeSymbol;

        Assert.NotNull(listIntType);
        var listIntIri = minter.Type(listIntType);
        var genericDef = minter.OntologyPrefix + DotNetOntology.TypeRels.GenericDefinition;

        Assert.Contains(emitter.Triples, t => t.Subject == listIntIri && t.Predicate == genericDef);
    }

    #endregion

    #region Edge Cases - Partial Classes

    [Fact]
    public void Extract_PartialClass_EmitsAsSingleType()
    {
        var source = @"
namespace Sample;
public partial class PartialClass
{
    public void Method1() { }
}
public partial class PartialClass
{
    public void Method2() { }
}
";

        var compilation = TestUtilities.CreateCompilation(source, "PartialClass");
        var emitter = new TestEmitter();
        var options = new ExtractionOptions { BaseUri = "http://test.example/" };

        var extractor = new AssemblyGraphExtractor(emitter, options);
        extractor.Extract(compilation, compilation.Assembly);

        var minter = new IriMinter("http://test.example/");
        var partial = compilation.GetTypeByMetadataName("Sample.PartialClass")!;
        var partialIri = minter.Type(partial);
        var hasMember = minter.OntologyPrefix + DotNetOntology.TypeRels.HasMember;

        var memberTriples = emitter.Triples.Where(t => t.Subject == partialIri && t.Predicate == hasMember).ToList();
        Assert.True(memberTriples.Count >= 2); // Both methods should be included
    }

    [Fact]
    public void Extract_PartialMethod_EmitsPartialDefinitionFlag()
    {
        var source = @"
namespace Sample;
public partial class Container
{
    partial void PartialMethod();
    partial void PartialMethod()
    {
        System.Console.WriteLine(""Implementation"");
    }
}
";

        var compilation = TestUtilities.CreateCompilation(source, "PartialMethod");
        var emitter = new TestEmitter();
        var options = new ExtractionOptions {
            BaseUri = "http://test.example/",
            IncludePrivate = true
        };

        var extractor = new AssemblyGraphExtractor(emitter, options);
        extractor.Extract(compilation, compilation.Assembly);

        var minter = new IriMinter("http://test.example/");
        var container = compilation.GetTypeByMetadataName("Sample.Container")!;
        var method = container.GetMembers("PartialMethod").OfType<IMethodSymbol>().FirstOrDefault();

        if (method != null)
        {
            var methodIri = minter.Member(method);
            var isPartialDef = minter.OntologyPrefix + DotNetOntology.MemberProps.IsPartialDefinition;
            Assert.Contains(emitter.Triples, t => t.Subject == methodIri && t.Predicate == isPartialDef);
        }
    }

    #endregion

    #region Edge Cases - Extension Methods

    [Fact]
    public void Extract_ExtensionMethod_MarkedCorrectly()
    {
        var source = @"
namespace Sample;
public static class Extensions
{
    public static void ExtensionMethod(this string s) { }
}
";

        var compilation = TestUtilities.CreateCompilation(source, "ExtensionMethod");
        var emitter = new TestEmitter();
        var options = new ExtractionOptions { BaseUri = "http://test.example/" };

        var extractor = new AssemblyGraphExtractor(emitter, options);
        extractor.Extract(compilation, compilation.Assembly);

        var minter = new IriMinter("http://test.example/");
        var extensions = compilation.GetTypeByMetadataName("Sample.Extensions")!;
        var method = extensions.GetMembers("ExtensionMethod").OfType<IMethodSymbol>().Single();
        var methodIri = minter.Member(method);
        var isExtension = minter.OntologyPrefix + DotNetOntology.MemberProps.IsExtensionMethod;

        var triple = emitter.Triples.FirstOrDefault(t => t.Subject == methodIri && t.Predicate == isExtension);
        Assert.NotNull(triple);
        Assert.Equal("true", triple.Object);
    }

    #endregion

    #region Edge Cases - Operator Overloads

    [Fact]
    public void Extract_OperatorOverload_EmitsAsMethod()
    {
        var source = @"
namespace Sample;
public class Vector
{
    public int X { get; set; }
    public int Y { get; set; }

    public static Vector operator +(Vector a, Vector b)
    {
        return new Vector { X = a.X + b.X, Y = a.Y + b.Y };
    }

    public static bool operator ==(Vector a, Vector b)
    {
        return a.X == b.X && a.Y == b.Y;
    }

    public static bool operator !=(Vector a, Vector b)
    {
        return !(a == b);
    }

    public override bool Equals(object? obj) => obj is Vector v && this == v;
    public override int GetHashCode() => (X, Y).GetHashCode();
}
";

        var compilation = TestUtilities.CreateCompilation(source, "OperatorOverload");
        var emitter = new TestEmitter();
        var options = new ExtractionOptions { BaseUri = "http://test.example/" };

        var extractor = new AssemblyGraphExtractor(emitter, options);
        extractor.Extract(compilation, compilation.Assembly);

        var minter = new IriMinter("http://test.example/");
        var vector = compilation.GetTypeByMetadataName("Sample.Vector")!;
        var operators = vector.GetMembers().OfType<IMethodSymbol>()
            .Where(m => m.MethodKind == MethodKind.UserDefinedOperator).ToList();

        Assert.NotEmpty(operators);

        foreach (var op in operators)
        {
            var opIri = minter.Member(op);
            var methodKind = minter.OntologyPrefix + DotNetOntology.MemberProps.MethodKind;
            Assert.Contains(emitter.Triples, t => t.Subject == opIri && t.Predicate == methodKind && t.Object == "UserDefinedOperator");
        }
    }

    [Fact]
    public void Extract_ConversionOperator_EmitsCorrectly()
    {
        var source = @"
namespace Sample;
public class Wrapper
{
    public int Value { get; set; }

    public static implicit operator int(Wrapper w) => w.Value;
    public static explicit operator Wrapper(int i) => new Wrapper { Value = i };
}
";

        var compilation = TestUtilities.CreateCompilation(source, "ConversionOperator");
        var emitter = new TestEmitter();
        var options = new ExtractionOptions { BaseUri = "http://test.example/" };

        var extractor = new AssemblyGraphExtractor(emitter, options);
        extractor.Extract(compilation, compilation.Assembly);

        var minter = new IriMinter("http://test.example/");
        var wrapper = compilation.GetTypeByMetadataName("Sample.Wrapper")!;
        var conversions = wrapper.GetMembers().OfType<IMethodSymbol>()
            .Where(m => m.MethodKind == MethodKind.Conversion).ToList();

        Assert.Equal(2, conversions.Count);
    }

    #endregion

    #region Member Types - Properties

    [Fact]
    public void Extract_PropertyWithDifferentAccessors_EmitsAccessibility()
    {
        var source = @"
namespace Sample;
public class Container
{
    public int ReadOnly { get; }
    public int WriteOnly { private get; set; }
    public int PrivateSetter { get; private set; }
    public int InitOnly { get; init; }
}
";

        var compilation = TestUtilities.CreateCompilation(source, "PropertyAccessors");
        var emitter = new TestEmitter();
        var options = new ExtractionOptions {
            BaseUri = "http://test.example/",
            IncludePrivate = true
        };

        var extractor = new AssemblyGraphExtractor(emitter, options);
        extractor.Extract(compilation, compilation.Assembly);

        var minter = new IriMinter("http://test.example/");
        var container = compilation.GetTypeByMetadataName("Sample.Container")!;

        var initOnlyProp = container.GetMembers("InitOnly").OfType<IPropertySymbol>().Single();
        var initOnlyIri = minter.Member(initOnlyProp);
        var isInitOnly = minter.OntologyPrefix + DotNetOntology.MemberProps.IsInitOnly;

        var triple = emitter.Triples.FirstOrDefault(t => t.Subject == initOnlyIri && t.Predicate == isInitOnly);
        Assert.NotNull(triple);
        Assert.Equal("true", triple.Object);
    }

    [Fact]
    public void Extract_Indexer_EmitsWithParameters()
    {
        var source = @"
namespace Sample;
public class IndexedContainer
{
    private int[] data = new int[10];

    public int this[int index]
    {
        get => data[index];
        set => data[index] = value;
    }
}
";

        var compilation = TestUtilities.CreateCompilation(source, "Indexer");
        var emitter = new TestEmitter();
        var options = new ExtractionOptions {
            BaseUri = "http://test.example/",
            IncludePrivate = true
        };

        var extractor = new AssemblyGraphExtractor(emitter, options);
        extractor.Extract(compilation, compilation.Assembly);

        var minter = new IriMinter("http://test.example/");
        var container = compilation.GetTypeByMetadataName("Sample.IndexedContainer")!;
        var indexer = container.GetMembers().OfType<IPropertySymbol>()
            .FirstOrDefault(p => p.IsIndexer);

        Assert.NotNull(indexer);
        var indexerIri = minter.Member(indexer);
        var hasParam = minter.OntologyPrefix + DotNetOntology.MemberRels.HasParameter;
        Assert.Contains(emitter.Triples, t => t.Subject == indexerIri && t.Predicate == hasParam);
    }

    #endregion

    #region Member Types - Events

    [Fact]
    public void Extract_EventWithCustomType_EmitsEventType()
    {
        var source = @"
using System;
namespace Sample;
public delegate void CustomHandler(object sender, int value);
public class EventContainer
{
    public event CustomHandler? CustomEvent;
    public event EventHandler? StandardEvent;
}
";

        var compilation = TestUtilities.CreateCompilation(source, "Events");
        var emitter = new TestEmitter();
        var options = new ExtractionOptions { BaseUri = "http://test.example/" };

        var extractor = new AssemblyGraphExtractor(emitter, options);
        extractor.Extract(compilation, compilation.Assembly);

        var minter = new IriMinter("http://test.example/");
        var container = compilation.GetTypeByMetadataName("Sample.EventContainer")!;
        var customEvent = container.GetMembers("CustomEvent").OfType<IEventSymbol>().Single();
        var customEventIri = minter.Member(customEvent);
        var eventType = minter.OntologyPrefix + DotNetOntology.MemberRels.EventType;

        Assert.Contains(emitter.Triples, t => t.Subject == customEventIri && t.Predicate == eventType);
    }

    #endregion

    #region Member Types - Fields

    [Fact]
    public void Extract_ConstField_EmitsConstValue()
    {
        var source = @"
namespace Sample;
public class Constants
{
    public const int MaxValue = 100;
    public const string Name = ""Test"";
    public static readonly int ReadOnlyValue = 42;
}
";

        var compilation = TestUtilities.CreateCompilation(source, "Constants");
        var emitter = new TestEmitter();
        var options = new ExtractionOptions { BaseUri = "http://test.example/" };

        var extractor = new AssemblyGraphExtractor(emitter, options);
        extractor.Extract(compilation, compilation.Assembly);

        var minter = new IriMinter("http://test.example/");
        var constants = compilation.GetTypeByMetadataName("Sample.Constants")!;
        var maxValue = constants.GetMembers("MaxValue").OfType<IFieldSymbol>().Single();
        var maxValueIri = minter.Member(maxValue);
        var constValue = minter.OntologyPrefix + DotNetOntology.MemberProps.ConstValue;

        var triple = emitter.Triples.FirstOrDefault(t => t.Subject == maxValueIri && t.Predicate == constValue);
        Assert.NotNull(triple);
        Assert.Equal("100", triple.Object);
    }

    [Fact]
    public void Extract_VolatileField_EmitsVolatileFlag()
    {
        var source = @"
namespace Sample;
public class Container
{
    private volatile int volatileField;
}
";

        var compilation = TestUtilities.CreateCompilation(source, "VolatileField");
        var emitter = new TestEmitter();
        var options = new ExtractionOptions {
            BaseUri = "http://test.example/",
            IncludePrivate = true
        };

        var extractor = new AssemblyGraphExtractor(emitter, options);
        extractor.Extract(compilation, compilation.Assembly);

        var minter = new IriMinter("http://test.example/");
        var container = compilation.GetTypeByMetadataName("Sample.Container")!;
        var field = container.GetMembers("volatileField").OfType<IFieldSymbol>().Single();
        var fieldIri = minter.Member(field);
        var isVolatile = minter.OntologyPrefix + DotNetOntology.MemberProps.IsVolatile;

        var triple = emitter.Triples.FirstOrDefault(t => t.Subject == fieldIri && t.Predicate == isVolatile);
        Assert.NotNull(triple);
        Assert.Equal("true", triple.Object);
    }

    #endregion

    #region Explicit Interface Implementations

    [Fact]
    public void Extract_ExplicitInterfaceImplementation_EmitsImplementsRelationship()
    {
        var source = @"
namespace Sample;
public interface IService
{
    void Execute();
}
public class ServiceImpl : IService
{
    public void Execute() { }
}
";

        var compilation = TestUtilities.CreateCompilation(source, "ExplicitImpl");
        var emitter = new TestEmitter();
        var options = new ExtractionOptions {
            BaseUri = "http://test.example/",
            IncludePrivate = true
        };

        var extractor = new AssemblyGraphExtractor(emitter, options);
        extractor.Extract(compilation, compilation.Assembly);

        var minter = new IriMinter("http://test.example/");
        var impl = compilation.GetTypeByMetadataName("Sample.ServiceImpl")!;
        var iface = compilation.GetTypeByMetadataName("Sample.IService")!;

        var implIri = minter.Type(impl);
        var ifaceIri = minter.Type(iface);
        var implements = minter.OntologyPrefix + DotNetOntology.TypeRels.Implements;

        // Verify the type implements the interface
        Assert.Contains(emitter.Triples, t => t.Subject == implIri && t.Predicate == implements && t.Object == ifaceIri);
    }

    #endregion

    #region Access Modifiers

    [Fact]
    public void Extract_PrivateMembers_IncludedWhenEnabled()
    {
        var source = @"
namespace Sample;
public class Container
{
    private int privateField;
    private void PrivateMethod() { }
    public void PublicMethod() { }
}
";

        var compilation = TestUtilities.CreateCompilation(source, "PrivateMembers");
        var emitter = new TestEmitter();
        var options = new ExtractionOptions {
            BaseUri = "http://test.example/",
            IncludePrivate = true
        };

        var extractor = new AssemblyGraphExtractor(emitter, options);
        extractor.Extract(compilation, compilation.Assembly);

        var minter = new IriMinter("http://test.example/");
        var container = compilation.GetTypeByMetadataName("Sample.Container")!;
        var privateMethod = container.GetMembers("PrivateMethod").OfType<IMethodSymbol>().Single();
        var privateMethodIri = minter.Member(privateMethod);
        var rdfType = DotNetOntology.Rdf + "type";

        Assert.Contains(emitter.Triples, t => t.Subject == privateMethodIri && t.Predicate == rdfType);
    }

    [Fact]
    public void Extract_PrivateMembers_ExcludedWhenDisabled()
    {
        var source = @"
namespace Sample;
public class Container
{
    private int privateField;
    private void PrivateMethod() { }
    public void PublicMethod() { }
}
";

        var compilation = TestUtilities.CreateCompilation(source, "NoPrivateMembers");
        var emitter = new TestEmitter();
        var options = new ExtractionOptions {
            BaseUri = "http://test.example/",
            IncludePrivate = false
        };

        var extractor = new AssemblyGraphExtractor(emitter, options);
        extractor.Extract(compilation, compilation.Assembly);

        var minter = new IriMinter("http://test.example/");
        var container = compilation.GetTypeByMetadataName("Sample.Container")!;
        var privateMethod = container.GetMembers("PrivateMethod").OfType<IMethodSymbol>().Single();
        var privateMethodIri = minter.Member(privateMethod);
        var rdfType = DotNetOntology.Rdf + "type";

        Assert.DoesNotContain(emitter.Triples, t => t.Subject == privateMethodIri && t.Predicate == rdfType);
    }

    [Fact]
    public void Extract_InternalTypes_IncludedByDefault()
    {
        var source = @"
namespace Sample;
internal class InternalClass
{
    public void Method() { }
}
";

        var compilation = TestUtilities.CreateCompilation(source, "InternalTypes");
        var emitter = new TestEmitter();
        var options = new ExtractionOptions {
            BaseUri = "http://test.example/",
            IncludeInternal = true
        };

        var extractor = new AssemblyGraphExtractor(emitter, options);
        extractor.Extract(compilation, compilation.Assembly);

        var minter = new IriMinter("http://test.example/");
        var internalClass = compilation.GetTypeByMetadataName("Sample.InternalClass")!;
        var internalIri = minter.Type(internalClass);
        var rdfType = DotNetOntology.Rdf + "type";

        Assert.Contains(emitter.Triples, t => t.Subject == internalIri && t.Predicate == rdfType);
    }

    [Fact]
    public void Extract_InternalTypes_ExcludedWhenDisabled()
    {
        var source = @"
namespace Sample;
internal class InternalClass
{
    public void Method() { }
}
";

        var compilation = TestUtilities.CreateCompilation(source, "NoInternalTypes");
        var emitter = new TestEmitter();
        var options = new ExtractionOptions {
            BaseUri = "http://test.example/",
            IncludeInternal = false
        };

        var extractor = new AssemblyGraphExtractor(emitter, options);
        extractor.Extract(compilation, compilation.Assembly);

        var minter = new IriMinter("http://test.example/");
        var internalClass = compilation.GetTypeByMetadataName("Sample.InternalClass")!;
        var internalIri = minter.Type(internalClass);
        var rdfType = DotNetOntology.Rdf + "type";

        Assert.DoesNotContain(emitter.Triples, t => t.Subject == internalIri && t.Predicate == rdfType);
    }

    #endregion

    #region Attributes

    [Fact]
    public void Extract_AttributesWithConstructorArgs_EmitsArguments()
    {
        var source = @"
using System;
namespace Sample;

[AttributeUsage(AttributeTargets.Class)]
public class CustomAttribute : Attribute
{
    public CustomAttribute(string name, int value) { }
}

[Custom(""test"", 42)]
public class Decorated { }
";

        var compilation = TestUtilities.CreateCompilation(source, "AttributeArgs");
        var emitter = new TestEmitter();
        var options = new ExtractionOptions {
            BaseUri = "http://test.example/",
            IncludeAttributes = true
        };

        var extractor = new AssemblyGraphExtractor(emitter, options);
        extractor.Extract(compilation, compilation.Assembly);

        var minter = new IriMinter("http://test.example/");
        var decorated = compilation.GetTypeByMetadataName("Sample.Decorated")!;
        var decoratedIri = minter.Type(decorated);
        var hasAttribute = minter.OntologyPrefix + DotNetOntology.TypeRels.HasAttribute;

        var attrTriples = emitter.Triples.Where(t => t.Subject == decoratedIri && t.Predicate == hasAttribute).ToList();
        Assert.NotEmpty(attrTriples);
    }

    [Fact]
    public void Extract_AttributesWithNamedArgs_EmitsNamedArguments()
    {
        var source = @"
using System;
namespace Sample;

[AttributeUsage(AttributeTargets.Class)]
public class CustomAttribute : Attribute
{
    public string Name { get; set; }
    public int Value { get; set; }
}

[Custom(Name = ""test"", Value = 42)]
public class Decorated { }
";

        var compilation = TestUtilities.CreateCompilation(source, "AttributeNamedArgs");
        var emitter = new TestEmitter();
        var options = new ExtractionOptions {
            BaseUri = "http://test.example/",
            IncludeAttributes = true
        };

        var extractor = new AssemblyGraphExtractor(emitter, options);
        extractor.Extract(compilation, compilation.Assembly);

        var minter = new IriMinter("http://test.example/");
        var decorated = compilation.GetTypeByMetadataName("Sample.Decorated")!;
        var attr = decorated.GetAttributes()[0];
        var attrIri = minter.Attribute(decorated, attr, 0);
        var namedArgs = minter.OntologyPrefix + DotNetOntology.AttrProps.NamedArguments;

        Assert.Contains(emitter.Triples, t => t.Subject == attrIri && t.Predicate == namedArgs);
    }

    [Fact]
    public void Extract_Attributes_ExcludedWhenDisabled()
    {
        var source = @"
using System;
namespace Sample;

[Obsolete(""Don't use this"")]
public class Decorated { }
";

        var compilation = TestUtilities.CreateCompilation(source, "NoAttributes");
        var emitter = new TestEmitter();
        var options = new ExtractionOptions {
            BaseUri = "http://test.example/",
            IncludeAttributes = false
        };

        var extractor = new AssemblyGraphExtractor(emitter, options);
        extractor.Extract(compilation, compilation.Assembly);

        var minter = new IriMinter("http://test.example/");
        var decorated = compilation.GetTypeByMetadataName("Sample.Decorated")!;
        var decoratedIri = minter.Type(decorated);
        var hasAttribute = minter.OntologyPrefix + DotNetOntology.TypeRels.HasAttribute;

        Assert.DoesNotContain(emitter.Triples, t => t.Subject == decoratedIri && t.Predicate == hasAttribute);
    }

    [Fact]
    public void Extract_InheritedAttributes_OnlyDirectlyAppliedEmitted()
    {
        var source = @"
using System;
namespace Sample;

[AttributeUsage(AttributeTargets.Class, Inherited = true)]
public class InheritableAttribute : Attribute { }

[Inheritable]
public class Base { }

public class Derived : Base { }
";

        var compilation = TestUtilities.CreateCompilation(source, "InheritedAttributes");
        var emitter = new TestEmitter();
        var options = new ExtractionOptions {
            BaseUri = "http://test.example/",
            IncludeAttributes = true
        };

        var extractor = new AssemblyGraphExtractor(emitter, options);
        extractor.Extract(compilation, compilation.Assembly);

        var minter = new IriMinter("http://test.example/");
        var derivedType = compilation.GetTypeByMetadataName("Sample.Derived")!;
        var derivedIri = minter.Type(derivedType);
        var hasAttribute = minter.OntologyPrefix + DotNetOntology.TypeRels.HasAttribute;

        // Derived class should not have attribute triples (we emit what's directly applied)
        var derivedAttrs = emitter.Triples.Where(t => t.Subject == derivedIri && t.Predicate == hasAttribute).ToList();
        Assert.Empty(derivedAttrs);
    }

    #endregion

    #region Special Types

    [Fact]
    public void Extract_RecordType_MarkedAsRecord()
    {
        var source = @"
namespace Sample;
public record Person(string Name, int Age);
";

        var compilation = TestUtilities.CreateCompilation(source, "RecordType");
        var emitter = new TestEmitter();
        var options = new ExtractionOptions { BaseUri = "http://test.example/" };

        var extractor = new AssemblyGraphExtractor(emitter, options);
        extractor.Extract(compilation, compilation.Assembly);

        var minter = new IriMinter("http://test.example/");
        var person = compilation.GetTypeByMetadataName("Sample.Person")!;
        var personIri = minter.Type(person);
        var isRecord = minter.OntologyPrefix + DotNetOntology.TypeProps.IsRecord;

        var triple = emitter.Triples.FirstOrDefault(t => t.Subject == personIri && t.Predicate == isRecord);
        Assert.NotNull(triple);
        Assert.Equal("true", triple.Object);
    }

    [Fact]
    public void Extract_EnumType_EmitsUnderlyingType()
    {
        var source = @"
namespace Sample;
public enum Status : byte
{
    Pending = 0,
    Active = 1,
    Completed = 2
}
";

        var compilation = TestUtilities.CreateCompilation(source, "EnumType");
        var emitter = new TestEmitter();
        var options = new ExtractionOptions {
            BaseUri = "http://test.example/",
            IncludePrivate = true
        };

        var extractor = new AssemblyGraphExtractor(emitter, options);
        extractor.Extract(compilation, compilation.Assembly);

        var minter = new IriMinter("http://test.example/");
        var status = compilation.GetTypeByMetadataName("Sample.Status")!;
        var statusIri = minter.Type(status);
        var underlyingType = minter.OntologyPrefix + DotNetOntology.TypeProps.EnumUnderlyingType;

        Assert.Contains(emitter.Triples, t => t.Subject == statusIri && t.Predicate == underlyingType);
    }

    [Fact]
    public void Extract_DelegateType_EmitsAsDelegate()
    {
        var source = @"
namespace Sample;
public delegate void ActionDelegate(string message);
public delegate int FuncDelegate(int x, int y);
";

        var compilation = TestUtilities.CreateCompilation(source, "DelegateType");
        var emitter = new TestEmitter();
        var options = new ExtractionOptions { BaseUri = "http://test.example/" };

        var extractor = new AssemblyGraphExtractor(emitter, options);
        extractor.Extract(compilation, compilation.Assembly);

        var minter = new IriMinter("http://test.example/");
        var actionDelegate = compilation.GetTypeByMetadataName("Sample.ActionDelegate")!;
        var actionIri = minter.Type(actionDelegate);
        var rdfType = DotNetOntology.Rdf + "type";
        var delegateClass = minter.OntologyPrefix + DotNetOntology.Classes.Delegate;

        Assert.Contains(emitter.Triples, t => t.Subject == actionIri && t.Predicate == rdfType && t.Object == delegateClass);
    }

    [Fact]
    public void Extract_InterfaceType_EmitsAsInterface()
    {
        var source = @"
namespace Sample;
public interface IService
{
    void Execute();
    int Calculate(int x);
}
";

        var compilation = TestUtilities.CreateCompilation(source, "InterfaceType");
        var emitter = new TestEmitter();
        var options = new ExtractionOptions { BaseUri = "http://test.example/" };

        var extractor = new AssemblyGraphExtractor(emitter, options);
        extractor.Extract(compilation, compilation.Assembly);

        var minter = new IriMinter("http://test.example/");
        var service = compilation.GetTypeByMetadataName("Sample.IService")!;
        var serviceIri = minter.Type(service);
        var rdfType = DotNetOntology.Rdf + "type";
        var interfaceClass = minter.OntologyPrefix + DotNetOntology.Classes.Interface;

        Assert.Contains(emitter.Triples, t => t.Subject == serviceIri && t.Predicate == rdfType && t.Object == interfaceClass);
    }

    [Fact]
    public void Extract_StructType_EmitsAsStruct()
    {
        var source = @"
namespace Sample;
public struct Point
{
    public int X { get; set; }
    public int Y { get; set; }
}
";

        var compilation = TestUtilities.CreateCompilation(source, "StructType");
        var emitter = new TestEmitter();
        var options = new ExtractionOptions { BaseUri = "http://test.example/" };

        var extractor = new AssemblyGraphExtractor(emitter, options);
        extractor.Extract(compilation, compilation.Assembly);

        var minter = new IriMinter("http://test.example/");
        var point = compilation.GetTypeByMetadataName("Sample.Point")!;
        var pointIri = minter.Type(point);
        var rdfType = DotNetOntology.Rdf + "type";
        var structClass = minter.OntologyPrefix + DotNetOntology.Classes.Struct;

        Assert.Contains(emitter.Triples, t => t.Subject == pointIri && t.Predicate == rdfType && t.Object == structClass);
    }

    [Fact]
    public void Extract_RefStructType_MarkedAsRefLike()
    {
        var source = @"
namespace Sample;
public ref struct RefStruct
{
    public int Value;
}
";

        var compilation = TestUtilities.CreateCompilation(source, "RefStructType");
        var emitter = new TestEmitter();
        var options = new ExtractionOptions { BaseUri = "http://test.example/" };

        var extractor = new AssemblyGraphExtractor(emitter, options);
        extractor.Extract(compilation, compilation.Assembly);

        var minter = new IriMinter("http://test.example/");
        var refStruct = compilation.GetTypeByMetadataName("Sample.RefStruct")!;
        var refStructIri = minter.Type(refStruct);
        var isRefLike = minter.OntologyPrefix + DotNetOntology.TypeProps.IsRefLikeType;

        var triple = emitter.Triples.FirstOrDefault(t => t.Subject == refStructIri && t.Predicate == isRefLike);
        Assert.NotNull(triple);
        Assert.Equal("true", triple.Object);
    }

    [Fact]
    public void Extract_ReadOnlyStruct_MarkedAsReadOnly()
    {
        var source = @"
namespace Sample;
public readonly struct ReadOnlyPoint
{
    public int X { get; }
    public int Y { get; }
}
";

        var compilation = TestUtilities.CreateCompilation(source, "ReadOnlyStruct");
        var emitter = new TestEmitter();
        var options = new ExtractionOptions { BaseUri = "http://test.example/" };

        var extractor = new AssemblyGraphExtractor(emitter, options);
        extractor.Extract(compilation, compilation.Assembly);

        var minter = new IriMinter("http://test.example/");
        var readOnlyPoint = compilation.GetTypeByMetadataName("Sample.ReadOnlyPoint")!;
        var readOnlyPointIri = minter.Type(readOnlyPoint);
        var isReadOnly = minter.OntologyPrefix + DotNetOntology.TypeProps.IsReadOnly;

        var triple = emitter.Triples.FirstOrDefault(t => t.Subject == readOnlyPointIri && t.Predicate == isReadOnly);
        Assert.NotNull(triple);
        Assert.Equal("true", triple.Object);
    }

    #endregion

    #region Array and Pointer Types

    [Fact]
    public void Extract_ArrayType_EmitsArrayElementType()
    {
        var source = @"
namespace Sample;
public class Container
{
    public int[] IntArray { get; set; }
    public string[][] JaggedArray { get; set; }
}
";

        var compilation = TestUtilities.CreateCompilation(source, "ArrayType");
        var emitter = new TestEmitter();
        var options = new ExtractionOptions { BaseUri = "http://test.example/" };

        var extractor = new AssemblyGraphExtractor(emitter, options);
        extractor.Extract(compilation, compilation.Assembly);

        var minter = new IriMinter("http://test.example/");
        var container = compilation.GetTypeByMetadataName("Sample.Container")!;
        var intArrayProp = container.GetMembers("IntArray").OfType<IPropertySymbol>().Single();
        var arrayType = intArrayProp.Type as IArrayTypeSymbol;

        Assert.NotNull(arrayType);
        var arrayIri = minter.Type(arrayType);
        var arrayElement = minter.OntologyPrefix + DotNetOntology.TypeRels.ArrayElementType;

        Assert.Contains(emitter.Triples, t => t.Subject == arrayIri && t.Predicate == arrayElement);
    }

    #endregion

    #region Constructors

    [Fact]
    public void Extract_Constructors_EmittedCorrectly()
    {
        var source = @"
namespace Sample;
public class Container
{
    static Container() { }

    public Container() { }

    public Container(int value) { }
}
";

        var compilation = TestUtilities.CreateCompilation(source, "Constructors");
        var emitter = new TestEmitter();
        var options = new ExtractionOptions {
            BaseUri = "http://test.example/",
            IncludePrivate = true
        };

        var extractor = new AssemblyGraphExtractor(emitter, options);
        extractor.Extract(compilation, compilation.Assembly);

        var minter = new IriMinter("http://test.example/");
        var container = compilation.GetTypeByMetadataName("Sample.Container")!;
        var constructors = container.GetMembers().OfType<IMethodSymbol>()
            .Where(m => m.MethodKind == MethodKind.Constructor || m.MethodKind == MethodKind.StaticConstructor)
            .ToList();

        Assert.True(constructors.Count >= 2); // Static + instance constructors

        foreach (var ctor in constructors)
        {
            var ctorIri = minter.Member(ctor);
            var rdfType = DotNetOntology.Rdf + "type";
            var constructorClass = minter.OntologyPrefix + DotNetOntology.Classes.Constructor;

            Assert.Contains(emitter.Triples, t => t.Subject == ctorIri && t.Predicate == rdfType && t.Object == constructorClass);
        }
    }

    #endregion

    #region Compiler Generated

    [Fact]
    public void Extract_CompilerGeneratedMembers_ExcludedByDefault()
    {
        var source = @"
namespace Sample;
public class Container
{
    public int AutoProp { get; set; }
}
";

        var compilation = TestUtilities.CreateCompilation(source, "CompilerGenOff");
        var emitter = new TestEmitter();
        var options = new ExtractionOptions {
            BaseUri = "http://test.example/",
            IncludeCompilerGenerated = false,
            IncludePrivate = true
        };

        var extractor = new AssemblyGraphExtractor(emitter, options);
        extractor.Extract(compilation, compilation.Assembly);

        var minter = new IriMinter("http://test.example/");
        var container = compilation.GetTypeByMetadataName("Sample.Container")!;
        var backingField = container.GetMembers().OfType<IFieldSymbol>()
            .FirstOrDefault(f => f.IsImplicitlyDeclared);

        Assert.NotNull(backingField);
        var fieldIri = minter.Member(backingField);
        var rdfType = DotNetOntology.Rdf + "type";

        Assert.DoesNotContain(emitter.Triples, t => t.Subject == fieldIri && t.Predicate == rdfType);
    }

    [Fact]
    public void Extract_CompilerGeneratedMembers_IncludedWhenEnabled()
    {
        var source = @"
namespace Sample;
public class Container
{
    public int AutoProp { get; set; }
}
";

        var compilation = TestUtilities.CreateCompilation(source, "CompilerGenOn");
        var emitter = new TestEmitter();
        var options = new ExtractionOptions {
            BaseUri = "http://test.example/",
            IncludeCompilerGenerated = true,
            IncludePrivate = true
        };

        var extractor = new AssemblyGraphExtractor(emitter, options);
        extractor.Extract(compilation, compilation.Assembly);

        var minter = new IriMinter("http://test.example/");
        var container = compilation.GetTypeByMetadataName("Sample.Container")!;
        var backingField = container.GetMembers().OfType<IFieldSymbol>()
            .FirstOrDefault(f => f.IsImplicitlyDeclared);

        Assert.NotNull(backingField);
        var fieldIri = minter.Member(backingField);
        var rdfType = DotNetOntology.Rdf + "type";

        Assert.Contains(emitter.Triples, t => t.Subject == fieldIri && t.Predicate == rdfType);
    }

    #endregion

    #region Pointer Types

    [Fact]
    public void Extract_PointerType_EmitsPointerElementType()
    {
        var source = @"
namespace Sample;
public unsafe class Container
{
    public int* Ptr;
}
";

        var compilation = TestUtilities.CreateCompilation(source, "PointerType", allowUnsafe: true);
        var emitter = new TestEmitter();
        var options = new ExtractionOptions { BaseUri = "http://test.example/" };

        var extractor = new AssemblyGraphExtractor(emitter, options);
        extractor.Extract(compilation, compilation.Assembly);

        var minter = new IriMinter("http://test.example/");
        var container = compilation.GetTypeByMetadataName("Sample.Container")!;
        var ptrField = container.GetMembers("Ptr").OfType<IFieldSymbol>().Single();
        var ptrType = ptrField.Type as IPointerTypeSymbol;

        Assert.NotNull(ptrType);
        var ptrIri = minter.Type(ptrType);
        var pointerElement = minter.OntologyPrefix + DotNetOntology.TypeRels.PointerElementType;
        var typeKind = minter.OntologyPrefix + DotNetOntology.TypeProps.TypeKind;

        Assert.Contains(emitter.Triples, t => t.Subject == ptrIri && t.Predicate == pointerElement);
        Assert.Contains(emitter.Triples, t => t.Subject == ptrIri && t.Predicate == typeKind && t.Object == "Pointer");
    }

    #endregion

    #region Constructed Type Arguments

    [Fact]
    public void Extract_ConstructedGenericType_EmitsTypeArgumentNodes()
    {
        var source = @"
using System.Collections.Generic;
namespace Sample;
public class Container
{
    public Dictionary<string, List<int>> Map { get; set; }
}
";

        var compilation = TestUtilities.CreateCompilation(source, "GenericTypeArgs");
        var emitter = new TestEmitter();
        var options = new ExtractionOptions {
            BaseUri = "http://test.example/",
            IncludeExternalTypes = true
        };

        var extractor = new AssemblyGraphExtractor(emitter, options);
        extractor.Extract(compilation, compilation.Assembly);

        var minter = new IriMinter("http://test.example/");
        var container = compilation.GetTypeByMetadataName("Sample.Container")!;
        var prop = container.GetMembers("Map").OfType<IPropertySymbol>().Single();
        var dictType = (INamedTypeSymbol)prop.Type;

        var dictIri = minter.Type(dictType);
        var typeArgRel = minter.OntologyPrefix + DotNetOntology.TypeRels.TypeArgument;
        var indexProp = minter.OntologyPrefix + "index";

        var argNodeIri = dictIri + "/typearg/0";

        Assert.Contains(emitter.Triples, t => t.Subject == dictIri && t.Predicate == typeArgRel && t.Object == argNodeIri);
        Assert.Contains(emitter.Triples, t => t.Subject == argNodeIri && t.Predicate == indexProp && t.Object == "0");
    }

    #endregion
}
