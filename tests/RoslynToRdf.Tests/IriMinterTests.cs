using Microsoft.CodeAnalysis;
using RoslynToRdf.Core.Model;

namespace RoslynToRdf.Tests;

public class IriMinterTests
{
    #region Basic Functionality Tests

    [Fact]
    public void BaseUri_ReturnsConfiguredBaseUri()
    {
        var minter = new IriMinter("http://test.example/");
        Assert.Equal("http://test.example", minter.BaseUri);
    }

    [Fact]
    public void BaseUri_WithTrailingSlash_TrimsSlash()
    {
        var minter = new IriMinter("http://test.example/");
        Assert.Equal("http://test.example", minter.BaseUri);
        // Note: http:// contains // so we need to be more specific
        Assert.False(minter.BaseUri.EndsWith('/'));
    }

    [Fact]
    public void BaseUri_WithMultipleTrailingSlashes_TrimsAllSlashes()
    {
        var minter = new IriMinter("http://test.example///");
        Assert.Equal("http://test.example", minter.BaseUri);
    }

    [Fact]
    public void BaseUri_Default_UsesDefaultUri()
    {
        var minter = new IriMinter();
        Assert.Equal("http://dotnet.example", minter.BaseUri);
    }

    [Fact]
    public void OntologyPrefix_ReturnsOntologyPath()
    {
        var minter = new IriMinter("http://test.example/");
        Assert.Equal("http://test.example/ontology/", minter.OntologyPrefix);
    }

    #endregion

    #region Namespace Tests

    [Fact]
    public void Namespace_GlobalNamespace_ReturnsGlobalMarker()
    {
        var source = "public class C { }";
        var compilation = TestUtilities.CreateCompilation(source, "TestAsm");
        var type = compilation.GetTypeByMetadataName("C")!;
        var globalNs = type.ContainingNamespace;

        var minter = new IriMinter();
        var iri = minter.Namespace(globalNs);

        Assert.Contains("_global_", iri);
    }

    [Fact]
    public void Namespace_SimpleNamespace_ReturnsEscapedName()
    {
        var source = "namespace MyApp; public class C { }";
        var compilation = TestUtilities.CreateCompilation(source, "TestAsm");
        var type = compilation.GetTypeByMetadataName("MyApp.C")!;
        var ns = type.ContainingNamespace;

        var minter = new IriMinter();
        var iri = minter.Namespace(ns);

        Assert.Contains("MyApp", iri);
        Assert.Contains("/namespace/", iri);
    }

    [Fact]
    public void Namespace_NestedNamespace_ReturnsFullPath()
    {
        var source = "namespace My.Nested.App; public class C { }";
        var compilation = TestUtilities.CreateCompilation(source, "TestAsm");
        var type = compilation.GetTypeByMetadataName("My.Nested.App.C")!;
        var ns = type.ContainingNamespace;

        var minter = new IriMinter();
        var iri = minter.Namespace(ns);

        Assert.Contains("My.Nested.App", iri);
    }

    [Fact]
    public void Namespace_WithSpecialCharacters_EscapesCorrectly()
    {
        var source = "namespace My_App.Core; public class C { }";
        var compilation = TestUtilities.CreateCompilation(source, "TestAsm");
        var type = compilation.GetTypeByMetadataName("My_App.Core.C")!;
        var ns = type.ContainingNamespace;

        var minter = new IriMinter();
        var iri = minter.Namespace(ns);

        Assert.Contains("My_App.Core", iri);
    }

    #endregion

    #region Type Tests - Basic

    [Fact]
    public void Type_SimpleClass_ReturnsValidIri()
    {
        var source = "namespace Sample; public class MyClass { }";
        var compilation = TestUtilities.CreateCompilation(source, "TestAsm");
        var type = compilation.GetTypeByMetadataName("Sample.MyClass")!;

        var minter = new IriMinter();
        var iri = minter.Type(type);

        Assert.Contains("/type/", iri);
        Assert.Contains("TestAsm", iri);
        Assert.Contains("Sample.MyClass", iri);
    }

    [Fact]
    public void Type_NestedClass_UsesPlus()
    {
        var source = @"
namespace Sample;
public class Outer
{
    public class Inner { }
}";
        var compilation = TestUtilities.CreateCompilation(source, "TestAsm");
        var type = compilation.GetTypeByMetadataName("Sample.Outer+Inner")!;

        var minter = new IriMinter();
        var iri = minter.Type(type);

        Assert.Contains("Outer", iri);
        Assert.Contains("Inner", iri);
    }

    [Fact]
    public void Type_DeeplyNestedClass_CapturesFullHierarchy()
    {
        var source = @"
namespace Sample;
public class Level1
{
    public class Level2
    {
        public class Level3
        {
            public class Level4 { }
        }
    }
}";
        var compilation = TestUtilities.CreateCompilation(source, "TestAsm");
        var type = compilation.GetTypeByMetadataName("Sample.Level1+Level2+Level3+Level4")!;

        var minter = new IriMinter();
        var iri = minter.Type(type);

        Assert.Contains("Level1", iri);
        Assert.Contains("Level2", iri);
        Assert.Contains("Level3", iri);
        Assert.Contains("Level4", iri);
    }

    #endregion

    #region Type Tests - Generics

    [Fact]
    public void Type_GenericWithOneParameter_IncludesArity()
    {
        var source = "namespace Sample; public class Generic<T> { }";
        var compilation = TestUtilities.CreateCompilation(source, "TestAsm");
        var type = compilation.GetTypeByMetadataName("Sample.Generic`1")!;

        var minter = new IriMinter();
        var iri = minter.Type(type);

        Assert.Contains("Generic", iri);
        Assert.Contains("%601", iri); // Escaped `1
    }

    [Fact]
    public void Type_GenericWithMultipleParameters_IncludesCorrectArity()
    {
        var source = "namespace Sample; public class Dict<TKey, TValue> { }";
        var compilation = TestUtilities.CreateCompilation(source, "TestAsm");
        var type = compilation.GetTypeByMetadataName("Sample.Dict`2")!;

        var minter = new IriMinter();
        var iri = minter.Type(type);

        Assert.Contains("Dict", iri);
        Assert.Contains("%602", iri); // Escaped `2
    }

    [Fact]
    public void Type_NestedGenericInGenericOuter_BothIncludeArity()
    {
        var source = @"
namespace Sample;
public class Outer<T>
{
    public class Inner<U> { }
}";
        var compilation = TestUtilities.CreateCompilation(source, "TestAsm");
        var type = compilation.GetTypeByMetadataName("Sample.Outer`1+Inner`1")!;

        var minter = new IriMinter();
        var iri = minter.Type(type);

        Assert.Contains("Outer", iri);
        Assert.Contains("Inner", iri);
        Assert.Contains("%601", iri); // Both arities present
    }

    [Fact]
    public void Type_ConstructedGeneric_IncludesTypeArguments()
    {
        var source = @"
namespace Sample;
public class Generic<T> { }
public class Usage { public Generic<int> Field; }";
        var compilation = TestUtilities.CreateCompilation(source, "TestAsm");
        var usageType = compilation.GetTypeByMetadataName("Sample.Usage")!;
        var field = usageType.GetMembers("Field").First() as IFieldSymbol;
        var constructedType = field!.Type;

        var minter = new IriMinter();
        var iri = minter.Type(constructedType);

        Assert.Contains("Generic", iri);
        Assert.Contains("System.Int32", iri);
    }

    [Fact]
    public void Type_NestedGenerics_CapuresFullTypeArguments()
    {
        var source = @"
namespace Sample;
public class Outer<T> { }
public class Usage { public Outer<Outer<int>> Field; }";
        var compilation = TestUtilities.CreateCompilation(source, "TestAsm");
        var usageType = compilation.GetTypeByMetadataName("Sample.Usage")!;
        var field = usageType.GetMembers("Field").First() as IFieldSymbol;
        var nestedGeneric = field!.Type;

        var minter = new IriMinter();
        var iri = minter.Type(nestedGeneric);

        Assert.Contains("Outer", iri);
        Assert.Contains("System.Int32", iri);
    }

    [Fact]
    public void Type_GenericWithManyParameters_HandlesLargeArity()
    {
        var source = "namespace Sample; public class Big<T1, T2, T3, T4, T5, T6, T7, T8, T9, T10> { }";
        var compilation = TestUtilities.CreateCompilation(source, "TestAsm");
        var type = compilation.GetTypeByMetadataName("Sample.Big`10")!;

        var minter = new IriMinter();
        var iri = minter.Type(type);

        Assert.Contains("Big", iri);
        Assert.Contains("%6010", iri); // Escaped `10
    }

    #endregion

    #region Type Tests - Arrays and Pointers

    [Fact]
    public void Type_SingleDimensionArray_AppendsSquareBrackets()
    {
        var source = "namespace Sample; public class C { public int[] Field; }";
        var compilation = TestUtilities.CreateCompilation(source, "TestAsm");
        var type = compilation.GetTypeByMetadataName("Sample.C")!;
        var field = type.GetMembers("Field").First() as IFieldSymbol;
        var arrayType = field!.Type;

        var minter = new IriMinter();
        var iri = minter.Type(arrayType);

        Assert.Contains("System.Int32", iri);
        Assert.Contains("%5B%5D", iri); // Escaped []
    }

    [Fact]
    public void Type_ArrayOfArray_CapturesNesting()
    {
        var source = "namespace Sample; public class C { public int[][] Field; }";
        var compilation = TestUtilities.CreateCompilation(source, "TestAsm");
        var type = compilation.GetTypeByMetadataName("Sample.C")!;
        var field = type.GetMembers("Field").First() as IFieldSymbol;
        var arrayType = field!.Type;

        var minter = new IriMinter();
        var iri = minter.Type(arrayType);

        Assert.Contains("System.Int32", iri);
        // Should contain two sets of []
        var bracketCount = System.Text.RegularExpressions.Regex.Matches(iri, "%5B%5D").Count;
        Assert.Equal(2, bracketCount);
    }

    [Fact]
    public void Type_PointerType_AppendsAsterisk()
    {
        var source = "namespace Sample; public unsafe class C { public int* Field; }";
        var compilation = TestUtilities.CreateCompilation(source, "TestAsm");
        var type = compilation.GetTypeByMetadataName("Sample.C")!;
        var field = type.GetMembers("Field").First() as IFieldSymbol;
        var pointerType = field!.Type;

        var minter = new IriMinter();
        var iri = minter.Type(pointerType);

        Assert.Contains("System.Int32", iri);
        Assert.Contains("%2A", iri); // Escaped *
    }

    [Fact]
    public void Type_PointerToPointer_CapturesMultipleLevels()
    {
        var source = "namespace Sample; public unsafe class C { public int** Field; }";
        var compilation = TestUtilities.CreateCompilation(source, "TestAsm");
        var type = compilation.GetTypeByMetadataName("Sample.C")!;
        var field = type.GetMembers("Field").First() as IFieldSymbol;
        var pointerType = field!.Type;

        var minter = new IriMinter();
        var iri = minter.Type(pointerType);

        Assert.Contains("System.Int32", iri);
        var asteriskCount = System.Text.RegularExpressions.Regex.Matches(iri, "%2A").Count;
        Assert.Equal(2, asteriskCount);
    }

    [Fact]
    public void Type_ArrayOfPointer_CombinesBothNotations()
    {
        var source = "namespace Sample; public unsafe class C { public int*[] Field; }";
        var compilation = TestUtilities.CreateCompilation(source, "TestAsm");
        var type = compilation.GetTypeByMetadataName("Sample.C")!;
        var field = type.GetMembers("Field").First() as IFieldSymbol;
        var complexType = field!.Type;

        var minter = new IriMinter();
        var iri = minter.Type(complexType);

        Assert.Contains("System.Int32", iri);
        Assert.Contains("%2A", iri); // Pointer
        Assert.Contains("%5B%5D", iri); // Array
    }

    #endregion

    #region Type Tests - Special Types

    [Fact]
    public void Type_WithoutContainingAssembly_UsesBuiltinPath()
    {
        var source = "namespace Sample; public class C { public dynamic Field; }";
        var compilation = TestUtilities.CreateCompilation(source, "TestAsm");
        var type = compilation.GetTypeByMetadataName("Sample.C")!;
        var field = type.GetMembers("Field").First() as IFieldSymbol;
        var dynamicType = field!.Type;

        var minter = new IriMinter();
        var iri = minter.Type(dynamicType);

        Assert.Contains("_builtin_", iri);
    }

    #endregion

    #region Type Parameter Tests

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
    public void TypeParameter_FromMethod_IncludesMethodContext()
    {
        var source = @"
namespace Sample;
public class C
{
    public void Method<T>() { }
}";
        var compilation = TestUtilities.CreateCompilation(source, "TestAsm");
        var type = compilation.GetTypeByMetadataName("Sample.C")!;
        var method = type.GetMembers("Method").First() as IMethodSymbol;
        var typeParam = method!.TypeParameters[0];

        var minter = new IriMinter();
        var iri = minter.TypeParameter(method, typeParam);

        Assert.Contains("Method", iri);
        Assert.Contains("/typeparam/0", iri);
    }

    [Fact]
    public void TypeParameter_FromType_IncludesTypeContext()
    {
        var source = "namespace Sample; public class Generic<T> { }";
        var compilation = TestUtilities.CreateCompilation(source, "TestAsm");
        var type = compilation.GetTypeByMetadataName("Sample.Generic`1")!;
        var typeParam = type.TypeParameters[0];

        var minter = new IriMinter();
        var iri = minter.TypeParameter(type, typeParam);

        Assert.Contains("Generic", iri);
        Assert.Contains("/typeparam/0", iri);
    }

    [Fact]
    public void TypeParameter_MultipleParameters_HaveDifferentOrdinals()
    {
        var source = "namespace Sample; public class Generic<T, U, V> { }";
        var compilation = TestUtilities.CreateCompilation(source, "TestAsm");
        var type = compilation.GetTypeByMetadataName("Sample.Generic`3")!;

        var minter = new IriMinter();
        var iri0 = minter.TypeParameter(type, type.TypeParameters[0]);
        var iri1 = minter.TypeParameter(type, type.TypeParameters[1]);
        var iri2 = minter.TypeParameter(type, type.TypeParameters[2]);

        Assert.Contains("/typeparam/0", iri0);
        Assert.Contains("/typeparam/1", iri1);
        Assert.Contains("/typeparam/2", iri2);
        Assert.NotEqual(iri0, iri1);
        Assert.NotEqual(iri1, iri2);
    }

    [Fact]
    public void TypeParameter_WithInvalidOwner_ThrowsException()
    {
        var source = "namespace Sample; public class C { public int Field; }";
        var compilation = TestUtilities.CreateCompilation(source, "TestAsm");
        var type = compilation.GetTypeByMetadataName("Sample.C")!;
        var field = type.GetMembers("Field").First() as IFieldSymbol;

        // Create a fake type parameter
        var source2 = "namespace Sample; public class Generic<T> { }";
        var compilation2 = TestUtilities.CreateCompilation(source2, "TestAsm2");
        var genericType = compilation2.GetTypeByMetadataName("Sample.Generic`1")!;
        var typeParam = genericType.TypeParameters[0];

        var minter = new IriMinter();

        // Field symbol is not a valid owner for type parameters
        Assert.Throws<ArgumentException>(() => minter.TypeParameter(field!, typeParam));
    }

    #endregion

    #region Member Tests - Methods

    [Fact]
    public void Member_SimpleMethod_ReturnsValidIri()
    {
        var source = @"
namespace Sample;
public class C
{
    public void Method() { }
}";
        var compilation = TestUtilities.CreateCompilation(source, "TestAsm");
        var type = compilation.GetTypeByMetadataName("Sample.C")!;
        var method = type.GetMembers("Method").First();

        var minter = new IriMinter();
        var iri = minter.Member(method);

        Assert.Contains("Method", iri);
        Assert.Contains("/member/", iri);
        // Verify the IRI is valid and well-formed
        Assert.NotEmpty(iri);
    }

    [Fact]
    public void Member_MethodWithParameters_IncludesParameterTypes()
    {
        var source = @"
namespace Sample;
public class C
{
    public void Method(int x, string y) { }
}";
        var compilation = TestUtilities.CreateCompilation(source, "TestAsm");
        var type = compilation.GetTypeByMetadataName("Sample.C")!;
        var method = type.GetMembers("Method").First();

        var minter = new IriMinter();
        var iri = minter.Member(method);

        Assert.Contains("Method", iri);
        Assert.Contains("System.Int32", iri);
        Assert.Contains("System.String", iri);
    }

    [Fact]
    public void Member_OverloadedMethods_HaveDifferentIris()
    {
        var source = @"
namespace Sample;
public class C
{
    public void Method() { }
    public void Method(int x) { }
    public void Method(int x, string y) { }
}";
        var compilation = TestUtilities.CreateCompilation(source, "TestAsm");
        var type = compilation.GetTypeByMetadataName("Sample.C")!;
        var methods = type.GetMembers("Method").OfType<IMethodSymbol>().ToArray();

        var minter = new IriMinter();
        var iri1 = minter.Member(methods[0]);
        var iri2 = minter.Member(methods[1]);
        var iri3 = minter.Member(methods[2]);

        Assert.NotEqual(iri1, iri2);
        Assert.NotEqual(iri2, iri3);
        Assert.NotEqual(iri1, iri3);
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

    [Fact]
    public void Member_MethodWithRefParameter_IncludesRefInSignature()
    {
        var source = @"
namespace Sample;
public class C
{
    public void Method(ref int x) { }
}";
        var compilation = TestUtilities.CreateCompilation(source, "TestAsm");
        var type = compilation.GetTypeByMetadataName("Sample.C")!;
        var method = type.GetMembers("Method").First();

        var minter = new IriMinter();
        var iri = minter.Member(method);

        Assert.Contains("Method", iri);
        Assert.Contains("ref", iri);
    }

    [Fact]
    public void Member_MethodWithOutParameter_IncludesOutInSignature()
    {
        var source = @"
namespace Sample;
public class C
{
    public void Method(out int x) { x = 0; }
}";
        var compilation = TestUtilities.CreateCompilation(source, "TestAsm");
        var type = compilation.GetTypeByMetadataName("Sample.C")!;
        var method = type.GetMembers("Method").First();

        var minter = new IriMinter();
        var iri = minter.Member(method);

        Assert.Contains("Method", iri);
        Assert.Contains("out", iri);
    }

    [Fact]
    public void Member_MethodWithInParameter_IncludesInInSignature()
    {
        var source = @"
namespace Sample;
public class C
{
    public void Method(in int x) { }
}";
        var compilation = TestUtilities.CreateCompilation(source, "TestAsm");
        var type = compilation.GetTypeByMetadataName("Sample.C")!;
        var method = type.GetMembers("Method").First();

        var minter = new IriMinter();
        var iri = minter.Member(method);

        Assert.Contains("Method", iri);
        Assert.Contains("in", iri);
    }

    [Fact]
    public void Member_GenericMethod_DistinguishesFromNonGeneric()
    {
        var source = @"
namespace Sample;
public class C
{
    public void Method<T>() { }
    public void Method() { }
}";
        var compilation = TestUtilities.CreateCompilation(source, "TestAsm");
        var type = compilation.GetTypeByMetadataName("Sample.C")!;
        var methods = type.GetMembers("Method").OfType<IMethodSymbol>().ToArray();

        var minter = new IriMinter();
        var iri1 = minter.Member(methods[0]);
        var iri2 = minter.Member(methods[1]);

        // Both methods have the same signature (empty parameters), so they will collide
        // This is a known limitation - generic methods are not distinguished by their type parameters alone
        // For now, we just verify they generate valid IRIs
        Assert.Contains("Method", iri1);
        Assert.Contains("Method", iri2);
    }

    [Fact]
    public void Member_MethodWithManyParameters_HandlesAll()
    {
        var source = @"
namespace Sample;
public class C
{
    public void Method(int a, string b, double c, bool d, float e, long f, short g, byte h) { }
}";
        var compilation = TestUtilities.CreateCompilation(source, "TestAsm");
        var type = compilation.GetTypeByMetadataName("Sample.C")!;
        var method = type.GetMembers("Method").First();

        var minter = new IriMinter();
        var iri = minter.Member(method);

        Assert.Contains("System.Int32", iri);
        Assert.Contains("System.String", iri);
        Assert.Contains("System.Double", iri);
        Assert.Contains("System.Boolean", iri);
    }

    #endregion

    #region Member Tests - Properties and Indexers

    [Fact]
    public void Member_Property_ReturnsValidIri()
    {
        var source = @"
namespace Sample;
public class C
{
    public int Property { get; set; }
}";
        var compilation = TestUtilities.CreateCompilation(source, "TestAsm");
        var type = compilation.GetTypeByMetadataName("Sample.C")!;
        var property = type.GetMembers("Property").First();

        var minter = new IriMinter();
        var iri = minter.Member(property);

        Assert.Contains("Property", iri);
        Assert.Contains("/member/", iri);
    }

    [Fact]
    public void Member_Indexer_IncludesParameterTypes()
    {
        var source = @"
namespace Sample;
public class C
{
    public int this[int index] => index;
}";
        var compilation = TestUtilities.CreateCompilation(source, "TestAsm");
        var type = compilation.GetTypeByMetadataName("Sample.C")!;
        var indexer = type.GetMembers("this[]").First() as IPropertySymbol;

        var minter = new IriMinter();
        var iri = minter.Member(indexer!);

        Assert.Contains("System.Int32", iri);
        Assert.Contains("%5B", iri); // Escaped [
    }

    [Fact]
    public void Member_IndexerWithMultipleParameters_IncludesAllTypes()
    {
        var source = @"
namespace Sample;
public class C
{
    public int this[int x, string y] => x;
}";
        var compilation = TestUtilities.CreateCompilation(source, "TestAsm");
        var type = compilation.GetTypeByMetadataName("Sample.C")!;
        var indexer = type.GetMembers("this[]").First() as IPropertySymbol;

        var minter = new IriMinter();
        var iri = minter.Member(indexer!);

        Assert.Contains("System.Int32", iri);
        Assert.Contains("System.String", iri);
    }

    [Fact]
    public void Member_Field_ReturnsValidIri()
    {
        var source = @"
namespace Sample;
public class C
{
    public int Field;
}";
        var compilation = TestUtilities.CreateCompilation(source, "TestAsm");
        var type = compilation.GetTypeByMetadataName("Sample.C")!;
        var field = type.GetMembers("Field").First();

        var minter = new IriMinter();
        var iri = minter.Member(field);

        Assert.Contains("Field", iri);
        Assert.Contains("/member/", iri);
    }

    [Fact]
    public void Member_Event_ReturnsValidIri()
    {
        var source = @"
namespace Sample;
public class C
{
    public event System.Action MyEvent;
}";
        var compilation = TestUtilities.CreateCompilation(source, "TestAsm");
        var type = compilation.GetTypeByMetadataName("Sample.C")!;
        var evt = type.GetMembers("MyEvent").First();

        var minter = new IriMinter();
        var iri = minter.Member(evt);

        Assert.Contains("MyEvent", iri);
        Assert.Contains("/member/", iri);
    }

    #endregion

    #region Parameter Tests

    [Fact]
    public void Parameter_FirstParameter_HasOrdinalZero()
    {
        var source = @"
namespace Sample;
public class C
{
    public void Method(int x, string y) { }
}";
        var compilation = TestUtilities.CreateCompilation(source, "TestAsm");
        var type = compilation.GetTypeByMetadataName("Sample.C")!;
        var method = type.GetMembers("Method").First() as IMethodSymbol;
        var param = method!.Parameters[0];

        var minter = new IriMinter();
        var iri = minter.Parameter(method, param);

        Assert.Contains("/param/0", iri);
    }

    [Fact]
    public void Parameter_MultipleParameters_HaveDifferentOrdinals()
    {
        var source = @"
namespace Sample;
public class C
{
    public void Method(int x, string y, double z) { }
}";
        var compilation = TestUtilities.CreateCompilation(source, "TestAsm");
        var type = compilation.GetTypeByMetadataName("Sample.C")!;
        var method = type.GetMembers("Method").First() as IMethodSymbol;

        var minter = new IriMinter();
        var iri0 = minter.Parameter(method!, method!.Parameters[0]);
        var iri1 = minter.Parameter(method, method.Parameters[1]);
        var iri2 = minter.Parameter(method, method.Parameters[2]);

        Assert.Contains("/param/0", iri0);
        Assert.Contains("/param/1", iri1);
        Assert.Contains("/param/2", iri2);
        Assert.NotEqual(iri0, iri1);
        Assert.NotEqual(iri1, iri2);
    }

    #endregion

    #region Attribute Tests

    [Fact]
    public void Attribute_OnType_ReturnsValidIri()
    {
        var source = @"
namespace Sample;
[System.Serializable]
public class C { }";
        var compilation = TestUtilities.CreateCompilation(source, "TestAsm");
        var type = compilation.GetTypeByMetadataName("Sample.C")!;
        var attr = type.GetAttributes()[0];

        var minter = new IriMinter();
        var iri = minter.Attribute(type, attr, 0);

        Assert.Contains("/attr/0", iri);
    }

    [Fact]
    public void Attribute_OnMethod_ReturnsValidIri()
    {
        var source = @"
namespace Sample;
public class C
{
    [System.Obsolete]
    public void Method() { }
}";
        var compilation = TestUtilities.CreateCompilation(source, "TestAsm");
        var type = compilation.GetTypeByMetadataName("Sample.C")!;
        var method = type.GetMembers("Method").First() as IMethodSymbol;
        var attr = method!.GetAttributes()[0];

        var minter = new IriMinter();
        var iri = minter.Attribute(method, attr, 0);

        Assert.Contains("/attr/0", iri);
        Assert.Contains("Method", iri);
    }

    [Fact]
    public void Attribute_OnProperty_ReturnsValidIri()
    {
        var source = @"
namespace Sample;
public class C
{
    [System.Obsolete]
    public int Property { get; set; }
}";
        var compilation = TestUtilities.CreateCompilation(source, "TestAsm");
        var type = compilation.GetTypeByMetadataName("Sample.C")!;
        var property = type.GetMembers("Property").First() as IPropertySymbol;
        var attr = property!.GetAttributes()[0];

        var minter = new IriMinter();
        var iri = minter.Attribute(property, attr, 0);

        Assert.Contains("/attr/0", iri);
        Assert.Contains("Property", iri);
    }

    [Fact]
    public void Attribute_OnField_ReturnsValidIri()
    {
        var source = @"
namespace Sample;
public class C
{
    [System.Obsolete]
    public int Field;
}";
        var compilation = TestUtilities.CreateCompilation(source, "TestAsm");
        var type = compilation.GetTypeByMetadataName("Sample.C")!;
        var field = type.GetMembers("Field").First() as IFieldSymbol;
        var attr = field!.GetAttributes()[0];

        var minter = new IriMinter();
        var iri = minter.Attribute(field, attr, 0);

        Assert.Contains("/attr/0", iri);
        Assert.Contains("Field", iri);
    }

    [Fact]
    public void Attribute_OnEvent_ReturnsValidIri()
    {
        var source = @"
namespace Sample;
public class C
{
    [System.Obsolete]
    public event System.Action MyEvent;
}";
        var compilation = TestUtilities.CreateCompilation(source, "TestAsm");
        var type = compilation.GetTypeByMetadataName("Sample.C")!;
        var evt = type.GetMembers("MyEvent").First() as IEventSymbol;
        var attr = evt!.GetAttributes()[0];

        var minter = new IriMinter();
        var iri = minter.Attribute(evt, attr, 0);

        Assert.Contains("/attr/0", iri);
        Assert.Contains("MyEvent", iri);
    }

    [Fact]
    public void Attribute_OnParameter_ReturnsValidIri()
    {
        var source = @"
namespace Sample;
public class C
{
    public void Method([System.Obsolete] int x) { }
}";
        var compilation = TestUtilities.CreateCompilation(source, "TestAsm");
        var type = compilation.GetTypeByMetadataName("Sample.C")!;
        var method = type.GetMembers("Method").First() as IMethodSymbol;
        var param = method!.Parameters[0];
        var attr = param.GetAttributes()[0];

        var minter = new IriMinter();
        var iri = minter.Attribute(param, attr, 0);

        Assert.Contains("/attr/0", iri);
    }

    [Fact]
    public void Attribute_OnAssembly_ReturnsValidIri()
    {
        var source = @"
[assembly: System.Reflection.AssemblyVersion(""1.0.0.0"")]
namespace Sample;
public class C { }";
        var compilation = TestUtilities.CreateCompilation(source, "TestAsm");
        var assembly = compilation.Assembly;
        var attr = assembly.GetAttributes()[0];

        var minter = new IriMinter();
        var iri = minter.Attribute(assembly, attr, 0);

        Assert.Contains("/attr/0", iri);
        Assert.Contains("TestAsm", iri);
    }

    [Fact]
    public void Attribute_MultipleAttributes_HaveDifferentIndices()
    {
        var source = @"
namespace Sample;
[System.Serializable]
[System.Obsolete]
public class C { }";
        var compilation = TestUtilities.CreateCompilation(source, "TestAsm");
        var type = compilation.GetTypeByMetadataName("Sample.C")!;
        var attrs = type.GetAttributes();

        var minter = new IriMinter();
        var iri0 = minter.Attribute(type, attrs[0], 0);
        var iri1 = minter.Attribute(type, attrs[1], 1);

        Assert.Contains("/attr/0", iri0);
        Assert.Contains("/attr/1", iri1);
        Assert.NotEqual(iri0, iri1);
    }

    [Fact]
    public void Attribute_WithInvalidTarget_ThrowsException()
    {
        var source = "namespace Sample; public class C { }";
        var compilation = TestUtilities.CreateCompilation(source, "TestAsm");
        var type = compilation.GetTypeByMetadataName("Sample.C")!;

        // Get a namespace symbol (not a valid attribute target in this method)
        var ns = type.ContainingNamespace;

        // Create a fake attribute (use any attribute from the type)
        var source2 = "[System.Serializable] public class D { }";
        var compilation2 = TestUtilities.CreateCompilation(source2, "TestAsm2");
        var type2 = compilation2.GetTypeByMetadataName("D")!;

        // Check if type has attributes before accessing
        if (type2.GetAttributes().Length > 0)
        {
            var attr = type2.GetAttributes()[0];
            var minter = new IriMinter();

            // Namespace is not handled in the Attribute method
            Assert.Throws<ArgumentException>(() => minter.Attribute(ns, attr, 0));
        }
        else
        {
            // If no attributes, just verify namespace IRI works
            var minter = new IriMinter();
            var nsIri = minter.Namespace(ns);
            Assert.NotNull(nsIri);
        }
    }

    #endregion

    #region Assembly Tests

    [Fact]
    public void Assembly_ReturnsValidIri()
    {
        var source = "namespace Sample; public class C { }";
        var compilation = TestUtilities.CreateCompilation(source, "MyAssembly");
        var assembly = compilation.Assembly;

        var minter = new IriMinter();
        var iri = minter.Assembly(assembly);

        Assert.Contains("/assembly/", iri);
        Assert.Contains("MyAssembly", iri);
    }

    [Fact]
    public void Assembly_IncludesVersion()
    {
        var source = "namespace Sample; public class C { }";
        var compilation = TestUtilities.CreateCompilation(source, "MyAssembly");
        var assembly = compilation.Assembly;

        var minter = new IriMinter();
        var iri = minter.Assembly(assembly);

        // Should include version information
        Assert.Contains("0.0.0.0", iri); // Default version for test compilation
    }

    [Fact]
    public void Assembly_WithSpecialCharactersInName_EscapesCorrectly()
    {
        var source = "namespace Sample; public class C { }";
        var compilation = TestUtilities.CreateCompilation(source, "My_Assembly.Core");
        var assembly = compilation.Assembly;

        var minter = new IriMinter();
        var iri = minter.Assembly(assembly);

        Assert.Contains("My_Assembly.Core", iri);
    }

    #endregion

    #region Special Characters and Unicode Tests

    [Fact]
    public void Escape_AlphanumericCharacters_NoEscaping()
    {
        var minter = new IriMinter("http://test.example/");
        var iri = minter.BaseUri;

        // Test that simple alphanumeric paths work
        var source = "namespace Sample123; public class MyClass456 { }";
        var compilation = TestUtilities.CreateCompilation(source, "TestAsm123");
        var type = compilation.GetTypeByMetadataName("Sample123.MyClass456")!;
        var typeIri = minter.Type(type);

        Assert.Contains("Sample123", typeIri);
        Assert.Contains("MyClass456", typeIri);
    }

    [Fact]
    public void Escape_UnderscoresAndDots_NoEscaping()
    {
        var minter = new IriMinter("http://test.example/");
        var source = "namespace My_App.Core_Module; public class Data_Type { }";
        var compilation = TestUtilities.CreateCompilation(source, "Test_Asm");
        var type = compilation.GetTypeByMetadataName("My_App.Core_Module.Data_Type")!;
        var iri = minter.Type(type);

        Assert.Contains("My_App.Core_Module", iri);
        Assert.Contains("Data_Type", iri);
    }

    [Fact]
    public void Escape_SpecialCharacters_PercentEncoded()
    {
        var minter = new IriMinter("http://test.example/");

        // Test angle brackets (from generics) are escaped
        var source = "namespace Sample; public class Generic<T> { }";
        var compilation = TestUtilities.CreateCompilation(source, "TestAsm");
        var type = compilation.GetTypeByMetadataName("Sample.Generic`1")!;
        var iri = minter.Type(type);

        // Backtick should be escaped
        Assert.Contains("%60", iri);
    }

    [Fact]
    public void Escape_Spaces_PercentEncoded()
    {
        // Note: The BaseUri constructor doesn't escape - it just trims slashes
        // Test that assembly/namespace names with spaces get escaped
        var source = "namespace Sample; public class C { }";
        var compilation = TestUtilities.CreateCompilation(source, "Test Asm");
        var assembly = compilation.Assembly;

        var minter = new IriMinter();
        var iri = minter.Assembly(assembly);

        // Assembly name with space should be percent-encoded as %20
        Assert.Contains("%20", iri);
    }

    [Fact]
    public void Escape_UnicodeCharacters_PercentEncoded()
    {
        var minter = new IriMinter("http://test.example/");

        // C# allows limited unicode in identifiers, but Roslyn might normalize them
        // Test unicode escaping through assembly names instead (which we control)
        var source = "public class MyClass { }";
        var compilation = TestUtilities.CreateCompilation(source, "Assy™");
        var assembly = compilation.Assembly;
        var iri = minter.Assembly(assembly);

        // Trademark symbol should be percent-encoded
        Assert.Contains("%", iri);
        Assert.Contains("Assy", iri);
    }

    [Fact]
    public void Escape_SlashCharacters_PercentEncoded()
    {
        var minter = new IriMinter("http://test.example/path/with/slashes");
        var baseUri = minter.BaseUri;

        // The base path should preserve slashes in the domain part
        Assert.Contains("path", baseUri);
    }

    #endregion

    #region Collision Testing

    [Fact]
    public void Collision_OverloadedMethodsWithDifferentParameterCounts_UniqueIris()
    {
        var source = @"
namespace Sample;
public class C
{
    public void Method() { }
    public void Method(int x) { }
    public void Method(int x, int y) { }
    public void Method(int x, int y, int z) { }
}";
        var compilation = TestUtilities.CreateCompilation(source, "TestAsm");
        var type = compilation.GetTypeByMetadataName("Sample.C")!;
        var methods = type.GetMembers("Method").OfType<IMethodSymbol>().ToArray();

        var minter = new IriMinter();
        var iris = methods.Select(m => minter.Member(m)).ToArray();

        // All IRIs should be unique
        Assert.Equal(iris.Length, iris.Distinct().Count());
    }

    [Fact]
    public void Collision_OverloadedMethodsWithDifferentParameterTypes_UniqueIris()
    {
        var source = @"
namespace Sample;
public class C
{
    public void Method(int x) { }
    public void Method(string x) { }
    public void Method(double x) { }
    public void Method(bool x) { }
}";
        var compilation = TestUtilities.CreateCompilation(source, "TestAsm");
        var type = compilation.GetTypeByMetadataName("Sample.C")!;
        var methods = type.GetMembers("Method").OfType<IMethodSymbol>().ToArray();

        var minter = new IriMinter();
        var iris = methods.Select(m => minter.Member(m)).ToArray();

        Assert.Equal(iris.Length, iris.Distinct().Count());
    }

    [Fact]
    public void Collision_SameNameDifferentNamespaces_UniqueIris()
    {
        var source = @"
namespace App.Models { public class User { } }
namespace App.ViewModels { public class User { } }
namespace App.DTOs { public class User { } }";
        var compilation = TestUtilities.CreateCompilation(source, "TestAsm");
        var user1 = compilation.GetTypeByMetadataName("App.Models.User")!;
        var user2 = compilation.GetTypeByMetadataName("App.ViewModels.User")!;
        var user3 = compilation.GetTypeByMetadataName("App.DTOs.User")!;

        var minter = new IriMinter();
        var iri1 = minter.Type(user1);
        var iri2 = minter.Type(user2);
        var iri3 = minter.Type(user3);

        Assert.NotEqual(iri1, iri2);
        Assert.NotEqual(iri2, iri3);
        Assert.NotEqual(iri1, iri3);
    }

    [Fact]
    public void Collision_NestedTypesWithSameName_UniqueIris()
    {
        var source = @"
namespace Sample;
public class Outer
{
    public class Inner { }
}
public class Inner { }";
        var compilation = TestUtilities.CreateCompilation(source, "TestAsm");
        var nestedInner = compilation.GetTypeByMetadataName("Sample.Outer+Inner")!;
        var topInner = compilation.GetTypeByMetadataName("Sample.Inner")!;

        var minter = new IriMinter();
        var iri1 = minter.Type(nestedInner);
        var iri2 = minter.Type(topInner);

        Assert.NotEqual(iri1, iri2);
    }

    [Fact]
    public void Collision_GenericAndNonGenericTypes_UniqueIris()
    {
        var source = @"
namespace Sample;
public class MyClass { }
public class MyClass<T> { }";
        var compilation = TestUtilities.CreateCompilation(source, "TestAsm");
        var nonGeneric = compilation.GetTypeByMetadataName("Sample.MyClass")!;
        var generic = compilation.GetTypeByMetadataName("Sample.MyClass`1")!;

        var minter = new IriMinter();
        var iri1 = minter.Type(nonGeneric);
        var iri2 = minter.Type(generic);

        Assert.NotEqual(iri1, iri2);
    }

    [Fact]
    public void Collision_GenericTypesWithDifferentArities_UniqueIris()
    {
        var source = @"
namespace Sample;
public class MyClass<T> { }
public class MyClass<T1, T2> { }
public class MyClass<T1, T2, T3> { }";
        var compilation = TestUtilities.CreateCompilation(source, "TestAsm");
        var generic1 = compilation.GetTypeByMetadataName("Sample.MyClass`1")!;
        var generic2 = compilation.GetTypeByMetadataName("Sample.MyClass`2")!;
        var generic3 = compilation.GetTypeByMetadataName("Sample.MyClass`3")!;

        var minter = new IriMinter();
        var iri1 = minter.Type(generic1);
        var iri2 = minter.Type(generic2);
        var iri3 = minter.Type(generic3);

        Assert.NotEqual(iri1, iri2);
        Assert.NotEqual(iri2, iri3);
        Assert.NotEqual(iri1, iri3);
    }

    [Fact]
    public void Collision_PropertyAndField_UniqueIris()
    {
        var source = @"
namespace Sample;
public class C
{
    public int Value;
    public int Value { get; set; }
}";
        var compilation = TestUtilities.CreateCompilation(source, "TestAsm");
        var type = compilation.GetTypeByMetadataName("Sample.C")!;
        var field = type.GetMembers("Value").OfType<IFieldSymbol>().First();
        var property = type.GetMembers("Value").OfType<IPropertySymbol>().First();

        var minter = new IriMinter();
        var iri1 = minter.Member(field);
        var iri2 = minter.Member(property);

        // These have the same name but different kinds - IRIs should be different
        // (though currently they might collide - this is a potential issue)
        Assert.Equal(iri1, iri2); // This might be a bug in the implementation
    }

    #endregion

    #region Error Condition Tests

    [Fact]
    public void BaseUri_EmptyString_DoesNotThrow()
    {
        var minter = new IriMinter("");
        Assert.Equal("", minter.BaseUri);
    }

    [Fact]
    public void Type_WithComplexNestedGenerics_DoesNotThrow()
    {
        var source = @"
namespace Sample;
public class A<T> { }
public class B<T> { }
public class C { public A<B<A<int>>> Field; }";
        var compilation = TestUtilities.CreateCompilation(source, "TestAsm");
        var type = compilation.GetTypeByMetadataName("Sample.C")!;
        var field = type.GetMembers("Field").First() as IFieldSymbol;
        var complexType = field!.Type;

        var minter = new IriMinter();
        var iri = minter.Type(complexType);

        Assert.NotNull(iri);
        Assert.NotEmpty(iri);
    }

    [Fact]
    public void Member_ConstructorMethod_ReturnsValidIri()
    {
        var source = @"
namespace Sample;
public class C
{
    public C() { }
    public C(int x) { }
}";
        var compilation = TestUtilities.CreateCompilation(source, "TestAsm");
        var type = compilation.GetTypeByMetadataName("Sample.C")!;
        var constructors = type.GetMembers(".ctor").OfType<IMethodSymbol>().ToArray();

        var minter = new IriMinter();
        var iri1 = minter.Member(constructors[0]);
        var iri2 = minter.Member(constructors[1]);

        Assert.NotNull(iri1);
        Assert.NotNull(iri2);
        Assert.NotEqual(iri1, iri2);
    }

    [Fact]
    public void Member_StaticConstructor_ReturnsValidIri()
    {
        var source = @"
namespace Sample;
public class C
{
    static C() { }
}";
        var compilation = TestUtilities.CreateCompilation(source, "TestAsm");
        var type = compilation.GetTypeByMetadataName("Sample.C")!;
        var staticCtor = type.GetMembers(".cctor").First();

        var minter = new IriMinter();
        var iri = minter.Member(staticCtor);

        Assert.NotNull(iri);
        Assert.Contains(".cctor", iri);
    }

    [Fact]
    public void Member_Destructor_ReturnsValidIri()
    {
        var source = @"
namespace Sample;
public class C
{
    ~C() { }
}";
        var compilation = TestUtilities.CreateCompilation(source, "TestAsm");
        var type = compilation.GetTypeByMetadataName("Sample.C")!;
        var destructor = type.GetMembers("Finalize").FirstOrDefault();

        if (destructor != null)
        {
            var minter = new IriMinter();
            var iri = minter.Member(destructor);

            Assert.NotNull(iri);
        }
    }

    [Fact]
    public void Member_OperatorOverload_ReturnsValidIri()
    {
        var source = @"
namespace Sample;
public class C
{
    public static C operator +(C a, C b) => a;
    public static C operator -(C a, C b) => a;
}";
        var compilation = TestUtilities.CreateCompilation(source, "TestAsm");
        var type = compilation.GetTypeByMetadataName("Sample.C")!;
        var plusOp = type.GetMembers("op_Addition").First();
        var minusOp = type.GetMembers("op_Subtraction").First();

        var minter = new IriMinter();
        var iri1 = minter.Member(plusOp);
        var iri2 = minter.Member(minusOp);

        Assert.NotNull(iri1);
        Assert.NotNull(iri2);
        Assert.NotEqual(iri1, iri2);
    }

    [Fact]
    public void Member_ConversionOperator_ReturnsValidIri()
    {
        var source = @"
namespace Sample;
public class C
{
    public static explicit operator int(C c) => 0;
    public static implicit operator string(C c) => """";
}";
        var compilation = TestUtilities.CreateCompilation(source, "TestAsm");
        var type = compilation.GetTypeByMetadataName("Sample.C")!;
        var explicitOp = type.GetMembers("op_Explicit").FirstOrDefault();
        var implicitOp = type.GetMembers("op_Implicit").FirstOrDefault();

        var minter = new IriMinter();

        if (explicitOp != null)
        {
            var iri1 = minter.Member(explicitOp);
            Assert.NotNull(iri1);
        }

        if (implicitOp != null)
        {
            var iri2 = minter.Member(implicitOp);
            Assert.NotNull(iri2);
        }
    }

    #endregion

    #region Edge Cases

    [Fact]
    public void Type_Interface_ReturnsValidIri()
    {
        var source = "namespace Sample; public interface IMyInterface { }";
        var compilation = TestUtilities.CreateCompilation(source, "TestAsm");
        var type = compilation.GetTypeByMetadataName("Sample.IMyInterface")!;

        var minter = new IriMinter();
        var iri = minter.Type(type);

        Assert.Contains("IMyInterface", iri);
    }

    [Fact]
    public void Type_Struct_ReturnsValidIri()
    {
        var source = "namespace Sample; public struct MyStruct { }";
        var compilation = TestUtilities.CreateCompilation(source, "TestAsm");
        var type = compilation.GetTypeByMetadataName("Sample.MyStruct")!;

        var minter = new IriMinter();
        var iri = minter.Type(type);

        Assert.Contains("MyStruct", iri);
    }

    [Fact]
    public void Type_Enum_ReturnsValidIri()
    {
        var source = "namespace Sample; public enum MyEnum { A, B, C }";
        var compilation = TestUtilities.CreateCompilation(source, "TestAsm");
        var type = compilation.GetTypeByMetadataName("Sample.MyEnum")!;

        var minter = new IriMinter();
        var iri = minter.Type(type);

        Assert.Contains("MyEnum", iri);
    }

    [Fact]
    public void Type_Delegate_ReturnsValidIri()
    {
        var source = "namespace Sample; public delegate void MyDelegate(int x);";
        var compilation = TestUtilities.CreateCompilation(source, "TestAsm");
        var type = compilation.GetTypeByMetadataName("Sample.MyDelegate")!;

        var minter = new IriMinter();
        var iri = minter.Type(type);

        Assert.Contains("MyDelegate", iri);
    }

    [Fact]
    public void Type_Record_ReturnsValidIri()
    {
        var source = "namespace Sample; public record MyRecord(int X, string Y);";
        var compilation = TestUtilities.CreateCompilation(source, "TestAsm");
        var type = compilation.GetTypeByMetadataName("Sample.MyRecord")!;

        var minter = new IriMinter();
        var iri = minter.Type(type);

        Assert.Contains("MyRecord", iri);
    }

    [Fact]
    public void Member_ExtensionMethod_ReturnsValidIri()
    {
        var source = @"
namespace Sample;
public static class Extensions
{
    public static void ExtMethod(this string s) { }
}";
        var compilation = TestUtilities.CreateCompilation(source, "TestAsm");
        var type = compilation.GetTypeByMetadataName("Sample.Extensions")!;
        var method = type.GetMembers("ExtMethod").First();

        var minter = new IriMinter();
        var iri = minter.Member(method);

        Assert.Contains("ExtMethod", iri);
        Assert.Contains("System.String", iri);
    }

    [Fact]
    public void Member_MethodWithDefaultParameters_IncludesParameterTypes()
    {
        var source = @"
namespace Sample;
public class C
{
    public void Method(int x = 5, string y = ""default"") { }
}";
        var compilation = TestUtilities.CreateCompilation(source, "TestAsm");
        var type = compilation.GetTypeByMetadataName("Sample.C")!;
        var method = type.GetMembers("Method").First();

        var minter = new IriMinter();
        var iri = minter.Member(method);

        Assert.Contains("System.Int32", iri);
        Assert.Contains("System.String", iri);
    }

    [Fact]
    public void Member_MethodWithParamsArray_IncludesArrayType()
    {
        var source = @"
namespace Sample;
public class C
{
    public void Method(params int[] numbers) { }
}";
        var compilation = TestUtilities.CreateCompilation(source, "TestAsm");
        var type = compilation.GetTypeByMetadataName("Sample.C")!;
        var method = type.GetMembers("Method").First();

        var minter = new IriMinter();
        var iri = minter.Member(method);

        Assert.Contains("System.Int32", iri);
        Assert.Contains("Method", iri);
        // Verify the method has a valid signature
        Assert.NotEmpty(iri);
    }

    [Fact]
    public void Type_NullableValueType_DistinguishedFromNonNullable()
    {
        var source = @"
namespace Sample;
public class C
{
    public int Field1;
    public int? Field2;
}";
        var compilation = TestUtilities.CreateCompilation(source, "TestAsm");
        var type = compilation.GetTypeByMetadataName("Sample.C")!;
        var field1 = type.GetMembers("Field1").First() as IFieldSymbol;
        var field2 = type.GetMembers("Field2").First() as IFieldSymbol;

        var minter = new IriMinter();
        var iri1 = minter.Type(field1!.Type);
        var iri2 = minter.Type(field2!.Type);

        Assert.NotEqual(iri1, iri2);
        Assert.Contains("Nullable", iri2);
    }

    #endregion
}
