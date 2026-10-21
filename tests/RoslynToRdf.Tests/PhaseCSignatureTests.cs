using Microsoft.CodeAnalysis;
using System.Collections.Immutable;
using RoslynToRdf.Core.Extraction;
using RoslynToRdf.Core.Model;

namespace RoslynToRdf.Tests;

public class PhaseCSignatureTests
{
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void FunctionPointers_KeepAssemblyQualifiedConstituentsDistinct(bool metadata)
    {
        var left = Emit("Left", "namespace Shared { public struct Arg {} }");
        var right = Emit("Right", "namespace Shared { public struct Arg {} }");
        var consumer = TestUtilities.CreateCompilation("""
            extern alias left;
            extern alias right;
            public unsafe class Root {
                public delegate*<left::Shared.Arg, void> First;
                public delegate*<right::Shared.Arg, void> Second;
                public delegate*<delegate*<left::Shared.Arg[], void>, void> NestedLeft;
                public delegate*<delegate*<right::Shared.Arg[], void>, void> NestedRight;
            }
            """, "Root", allowUnsafe: true)
            .AddReferences(AliasedReference(left, "left"), AliasedReference(right, "right"));
        Assert.DoesNotContain(consumer.GetDiagnostics(), diagnostic => diagnostic.Severity == DiagnosticSeverity.Error);

        Compilation context = consumer;
        IAssemblySymbol assembly = consumer.Assembly;
        if (metadata)
        {
            var image = Emit(consumer);
            var rootReference = MetadataReference.CreateFromImage(image);
            context = TestUtilities.CreateCompilation("", "MetadataConsumer")
                .AddReferences(MetadataReference.CreateFromImage(left), MetadataReference.CreateFromImage(right), rootReference);
            assembly = (IAssemblySymbol)context.GetAssemblyOrModuleSymbol(rootReference)!;
        }

        var root = assembly.GetTypeByMetadataName("Root")!;
        var first = (IFunctionPointerTypeSymbol)((IFieldSymbol)root.GetMembers("First").Single()).Type;
        var second = (IFunctionPointerTypeSymbol)((IFieldSymbol)root.GetMembers("Second").Single()).Type;
        var nestedLeft = (IFunctionPointerTypeSymbol)((IFieldSymbol)root.GetMembers("NestedLeft").Single()).Type;
        var nestedRight = (IFunctionPointerTypeSymbol)((IFieldSymbol)root.GetMembers("NestedRight").Single()).Type;
        var minter = new IriMinter();
        Assert.NotEqual(minter.Type(first), minter.Type(second));
        Assert.NotEqual(minter.Type(nestedLeft), minter.Type(nestedRight));

        var emitter = Extract(context, assembly);
        AssertSignatureParameter(emitter, minter, first, first.Signature.Parameters.Single().Type);
        AssertSignatureParameter(emitter, minter, second, second.Signature.Parameters.Single().Type);
        var nestedLeftParameter = (IFunctionPointerTypeSymbol)nestedLeft.Signature.Parameters.Single().Type;
        var nestedRightParameter = (IFunctionPointerTypeSymbol)nestedRight.Signature.Parameters.Single().Type;
        Assert.NotEqual(minter.Type(nestedLeftParameter), minter.Type(nestedRightParameter));
        AssertSignatureParameter(emitter, minter, nestedLeft, nestedLeftParameter);
        AssertSignatureParameter(emitter, minter, nestedRight, nestedRightParameter);
        AssertSignatureParameter(emitter, minter, nestedLeftParameter, nestedLeftParameter.Signature.Parameters.Single().Type);
        AssertSignatureParameter(emitter, minter, nestedRightParameter, nestedRightParameter.Signature.Parameters.Single().Type);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void TypeParameterArraysAndPointers_KeepOwnerAssemblyDistinct(bool metadata)
    {
        const string owner = "public unsafe class Owner<T> where T : unmanaged { public T[] Array; public T* Pointer; }";
        (ITypeSymbol Array, ITypeSymbol Pointer, ITypeSymbol Parameter, TestEmitter Emitter) Wrappers(string assemblyName)
        {
            var source = TestUtilities.CreateCompilation(owner, assemblyName, allowUnsafe: true);
            Compilation context = source;
            IAssemblySymbol assembly = source.Assembly;
            if (metadata)
            {
                var reference = MetadataReference.CreateFromImage(Emit(source));
                context = TestUtilities.CreateCompilation("", assemblyName + "Consumer").AddReferences(reference);
                assembly = (IAssemblySymbol)context.GetAssemblyOrModuleSymbol(reference)!;
            }
            var type = assembly.GetTypeByMetadataName("Owner`1")!;
            return (((IFieldSymbol)type.GetMembers("Array").Single()).Type, ((IFieldSymbol)type.GetMembers("Pointer").Single()).Type,
                type.TypeParameters.Single(), Extract(context, assembly));
        }

        var minter = new IriMinter();
        var left = Wrappers("Left");
        var right = Wrappers("Right");
        Assert.NotEqual(minter.Type(left.Array), minter.Type(right.Array));
        Assert.NotEqual(minter.Type(left.Pointer), minter.Type(right.Pointer));
        Assert.Equal("http://dotnet.example/type/Left/0.0.0.0/T%3AOwner%601.T%5B%5D", minter.Type(left.Array));
        Assert.Equal("http://dotnet.example/type/Right/0.0.0.0/T%3AOwner%601.T%2A", minter.Type(right.Pointer));
        foreach (var side in new[] { left, right })
        {
            HasOnly(side.Emitter, minter.Type(side.Array), "arrayElementType", minter.Type(side.Parameter));
            HasOnly(side.Emitter, minter.Type(side.Pointer), "pointerElementType", minter.Type(side.Parameter));
        }
    }

    [Theory]
    [InlineData(false, false)]
    [InlineData(false, true)]
    [InlineData(true, false)]
    [InlineData(true, true)]
    public void FunctionPointers_KeepConstructedContainingTypeArgumentsDistinct(bool metadata, bool rightFirst)
    {
        var left = Emit("Left", "namespace Shared { public struct Arg {} }");
        var right = Emit("Right", "namespace Shared { public struct Arg {} }");
        var leftField = "public delegate*<Outer<left::Shared.Arg>.Inner, void> LeftNested;";
        var rightField = "public delegate*<Outer<right::Shared.Arg>.Inner, void> RightNested;";
        var consumer = TestUtilities.CreateCompilation($$"""
            extern alias left;
            extern alias right;
            public class Outer<T> { public class Inner {} }
            public unsafe class Root {
                {{(rightFirst ? rightField : leftField)}}
                {{(rightFirst ? leftField : rightField)}}
            }
            """, "Root", allowUnsafe: true)
            .AddReferences(AliasedReference(left, "left"), AliasedReference(right, "right"));
        Assert.DoesNotContain(consumer.GetDiagnostics(), diagnostic => diagnostic.Severity == DiagnosticSeverity.Error);

        Compilation context = consumer;
        IAssemblySymbol assembly = consumer.Assembly;
        if (metadata)
        {
            var rootReference = MetadataReference.CreateFromImage(Emit(consumer));
            context = TestUtilities.CreateCompilation("", "MetadataConsumer")
                .AddReferences(MetadataReference.CreateFromImage(left), MetadataReference.CreateFromImage(right), rootReference);
            assembly = (IAssemblySymbol)context.GetAssemblyOrModuleSymbol(rootReference)!;
        }

        var root = assembly.GetTypeByMetadataName("Root")!;
        var leftPointer = (IFunctionPointerTypeSymbol)((IFieldSymbol)root.GetMembers("LeftNested").Single()).Type;
        var rightPointer = (IFunctionPointerTypeSymbol)((IFieldSymbol)root.GetMembers("RightNested").Single()).Type;
        var minter = new IriMinter();
        Assert.NotEqual(minter.Type(leftPointer), minter.Type(rightPointer));

        var emitter = Extract(context, assembly);
        AssertSignatureParameter(emitter, minter, leftPointer, leftPointer.Signature.Parameters.Single().Type);
        AssertSignatureParameter(emitter, minter, rightPointer, rightPointer.Signature.Parameters.Single().Type);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void ArraysPointersAndGenericArguments_KeepAssemblyQualifiedElementsDistinct(bool metadata)
    {
        var left = Emit("Left", "namespace Shared { public struct Arg {} }");
        var right = Emit("Right", "namespace Shared { public struct Arg {} }");
        var consumer = TestUtilities.CreateCompilation("""
            extern alias left;
            extern alias right;
            using System.Collections.Generic;
            public unsafe class Root {
                public left::Shared.Arg[] LeftArray;
                public right::Shared.Arg[] RightArray;
                public left::Shared.Arg* LeftPointer;
                public right::Shared.Arg* RightPointer;
                public List<left::Shared.Arg> LeftList;
                public List<right::Shared.Arg> RightList;
                public List<left::Shared.Arg[]> LeftArrayList;
                public List<right::Shared.Arg[]> RightArrayList;
                public List<int> Ints;
            }
            """, "Root", allowUnsafe: true)
            .AddReferences(AliasedReference(left, "left"), AliasedReference(right, "right"));
        Assert.DoesNotContain(consumer.GetDiagnostics(), diagnostic => diagnostic.Severity == DiagnosticSeverity.Error);

        Compilation context = consumer;
        IAssemblySymbol assembly = consumer.Assembly;
        if (metadata)
        {
            var rootReference = MetadataReference.CreateFromImage(Emit(consumer));
            context = TestUtilities.CreateCompilation("", "MetadataConsumer")
                .AddReferences(MetadataReference.CreateFromImage(left), MetadataReference.CreateFromImage(right), rootReference);
            assembly = (IAssemblySymbol)context.GetAssemblyOrModuleSymbol(rootReference)!;
        }

        var root = assembly.GetTypeByMetadataName("Root")!;
        ITypeSymbol Field(string name) => ((IFieldSymbol)root.GetMembers(name).Single()).Type;
        var minter = new IriMinter();
        var emitter = Extract(context, assembly);

        foreach (var (l, r) in new[] { ("LeftArray", "RightArray"), ("LeftPointer", "RightPointer"),
                     ("LeftList", "RightList"), ("LeftArrayList", "RightArrayList") })
            Assert.NotEqual(minter.Type(Field(l)), minter.Type(Field(r)));

        foreach (var name in new[] { "LeftArray", "RightArray" })
        {
            var array = (IArrayTypeSymbol)Field(name);
            HasOnly(emitter, minter.Type(array), "arrayElementType", minter.Type(array.ElementType));
        }
        foreach (var name in new[] { "LeftPointer", "RightPointer" })
        {
            var pointer = (IPointerTypeSymbol)Field(name);
            HasOnly(emitter, minter.Type(pointer), "pointerElementType", minter.Type(pointer.PointedAtType));
        }
        foreach (var name in new[] { "LeftList", "RightList", "LeftArrayList", "RightArrayList" })
        {
            var list = (INamedTypeSymbol)Field(name);
            HasOnly(emitter, minter.Type(list) + "/typearg/0", "type", minter.Type(list.TypeArguments.Single()));
        }

        // Hand-authored expected identities: elements resolve to their own assembly, generic arguments from another
        // assembly are qualified, and the established same-assembly form is unchanged.
        const string type = "http://dotnet.example/type/";
        Assert.Equal(type + "Left/0.0.0.0/Shared.Arg%5B%5D", minter.Type(Field("LeftArray")));
        Assert.Equal(type + "Right/0.0.0.0/Shared.Arg%2A", minter.Type(Field("RightPointer")));
        Assert.EndsWith("/System.Collections.Generic.List%601%5B%5BLeft%2C0.0.0.0%5DShared.Arg%5D", minter.Type(Field("LeftList")));
        Assert.EndsWith("/System.Collections.Generic.List%601%5B%5BRight%2C0.0.0.0%5DShared.Arg%5B%5D%5D", minter.Type(Field("RightArrayList")));
        Assert.Contains("/type/Left/0.0.0.0/Shared.Arg", minter.Type(((IArrayTypeSymbol)Field("LeftArray")).ElementType));
        Assert.Contains("/type/Right/0.0.0.0/Shared.Arg%5B%5D", minter.Type(Field("RightArray")));
        Assert.EndsWith("/System.Collections.Generic.List%601%5BSystem.Int32%5D", minter.Type(Field("Ints")));
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void FunctionPointers_PreserveSignaturesAndGenericOwners(bool metadata)
    {
        var compilation = TestUtilities.CreateCompilation("""
            public unsafe class A<T> {
                public delegate*<ref T, out T, ref readonly T> Managed;
                public delegate* unmanaged[Cdecl, SuppressGCTransition]<int*, int*, void> Native;
                public delegate*<delegate*<int, int>, int> Nested;
            }
            public unsafe class B<T> {
                public delegate*<ref T, out T, ref readonly T> Managed;
            }
            """, allowUnsafe: true);
        WithAssembly(compilation, metadata, (context, assembly) =>
        {
            var emitter = Extract(context, assembly);
            var minter = new IriMinter();
            var owner = assembly.GetTypeByMetadataName("A`1")!;
            var other = assembly.GetTypeByMetadataName("B`1")!;
            var managed = (IFunctionPointerTypeSymbol)((IFieldSymbol)owner.GetMembers("Managed").Single()).Type;
            var otherPointer = ((IFieldSymbol)other.GetMembers("Managed").Single()).Type;
            Assert.NotEqual(minter.Type(managed), minter.Type(otherPointer));
            Has(emitter, minter.Type(managed), "signatureReturnRefKind", "In");
            Has(emitter, minter.Type(managed) + "/sigparam/0", "refKind", "Ref");
            Has(emitter, minter.Type(managed) + "/sigparam/1", "refKind", "Out");
            var native = (IFunctionPointerTypeSymbol)((IFieldSymbol)owner.GetMembers("Native").Single()).Type;
            Has(emitter, minter.Type(native), "callingConvention", "Unmanaged");
            Assert.Equal(2, native.Signature.UnmanagedCallingConventionTypes.Length);
            Assert.Equal(minter.Type(native.Signature.Parameters[0].Type), minter.Type(native.Signature.Parameters[1].Type));
            foreach (var field in owner.GetMembers().OfType<IFieldSymbol>())
                AssertPointer(emitter, minter, (IFunctionPointerTypeSymbol)field.Type);
            AssertPointer(emitter, minter, managed);
        });
    }

    [Fact]
    public void ReferenceStubs_PreserveNonNeutralCultureAndVersion()
    {
        var dependency = TestUtilities.CreateCompilation("""
            [assembly: System.Reflection.AssemblyCulture("fr-FR")]
            [assembly: System.Reflection.AssemblyVersion("2.3.4.5")]
            public class External {}
            """, "Dependency");
        using var image = new MemoryStream();
        var emitted = dependency.Emit(image);
        Assert.True(emitted.Success, string.Join(Environment.NewLine, emitted.Diagnostics));
        var reference = MetadataReference.CreateFromImage(image.ToArray());
        var compilation = TestUtilities.CreateCompilation("public class Owner { public External Value; }").AddReferences(reference);
        var emitter = Extract(compilation, compilation.Assembly);
        var assembly = (IAssemblySymbol)compilation.GetAssemblyOrModuleSymbol(reference)!;
        var subject = new IriMinter().Assembly(assembly);
        Has(emitter, subject, "culture", "fr-FR");
        Has(emitter, subject, "version", "2.3.4.5");
        Has(emitter, subject, "name", "Dependency");
        Assert.DoesNotContain(emitter.Triples, triple => triple.Subject == subject
            && triple.Predicate == "http://dotnet.example/ontology/publicKeyToken");
    }

    [Theory]
    [InlineData(false, false)]
    [InlineData(false, true)]
    [InlineData(true, false)]
    [InlineData(true, true)]
    public void Delegates_EmitInvokeSignature(bool visualBasic, bool metadata)
    {
        Compilation compilation = visualBasic
            ? TestUtilities.CreateVisualBasicCompilation("Public Delegate Function Mapper(Of T)(ByRef value As T) As T")
            : TestUtilities.CreateCompilation("public delegate T Mapper<T>(ref T value);");
        WithAssembly(compilation, metadata, (context, assembly) =>
        {
            var emitter = Extract(context, assembly);
            var minter = new IriMinter();
            var type = assembly.GetTypeByMetadataName("Mapper`1")!;
            var invoke = type.DelegateInvokeMethod!;
            Has(emitter, minter.Type(type), "hasMember", minter.Member(invoke));
            Has(emitter, minter.Member(invoke), "methodKind", "DelegateInvoke");
            Has(emitter, minter.Member(invoke), "returnType", minter.Type(invoke.ReturnType));
            Has(emitter, minter.Member(invoke), "hasParameter", minter.Parameter(invoke, invoke.Parameters[0]));
            Has(emitter, minter.Parameter(invoke, invoke.Parameters[0]), "parameterType", minter.Type(invoke.Parameters[0].Type));
            Has(emitter, minter.Parameter(invoke, invoke.Parameters[0]), "ordinal", "0");
        });
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void ReferenceStubs_PreserveIdentityWithoutDeclaringAnotherAssembly(bool metadata)
    {
        var compilation = TestUtilities.CreateCompilation("public class Inventory { public System.String Text; public System.Exception Error; }");
        WithAssembly(compilation, metadata, (context, assembly) =>
        {
            var emitter = Extract(context, assembly);
            var minter = new IriMinter();
            var field = (IFieldSymbol)assembly.GetTypeByMetadataName("Inventory")!.GetMembers("Text").Single();
            var reference = field.Type.ContainingAssembly;
            var assemblyIri = minter.Assembly(reference);
            Has(emitter, minter.Type(field.Type), "definedInAssembly", assemblyIri);
            Has(emitter, assemblyIri, "name", reference.Name);
            Has(emitter, assemblyIri, "version", reference.Identity.Version.ToString());
            Has(emitter, assemblyIri, "publicKeyToken", Convert.ToHexString(reference.Identity.PublicKeyToken.ToArray()).ToLowerInvariant());
            Assert.DoesNotContain(emitter.Triples, triple => triple.Subject == assemblyIri && triple.Predicate == DotNetOntology.Rdf + "type"
                && triple.Object == minter.OntologyPrefix + "Assembly");
            Assert.Single(emitter.Triples.Where(triple => triple.Predicate == DotNetOntology.Rdf + "type"
                && triple.Object == minter.OntologyPrefix + "Assembly"));
        });
    }

    private static void AssertPointer(TestEmitter emitter, IriMinter minter, IFunctionPointerTypeSymbol pointer)
    {
        var subject = minter.Type(pointer);
        Assert.Single(emitter.Triples.Where(triple => triple.Subject == subject
            && triple.Predicate == DotNetOntology.Rdf + "type" && triple.Object == minter.OntologyPrefix + "Type"));
        Has(emitter, subject, "typeKind", "FunctionPointer");
        Assert.Equal(pointer.Signature.Parameters.Length, emitter.Triples.Count(triple => triple.Subject == subject
            && triple.Predicate == minter.OntologyPrefix + "signatureParameter"));
        Has(emitter, subject, "signatureReturnRefKind", pointer.Signature.RefKind.ToString());
        Has(emitter, subject, "callingConvention", pointer.Signature.CallingConvention.ToString());
        if (!pointer.Signature.ReturnsVoid)
            Has(emitter, subject, "signatureReturnType", minter.Type(pointer.Signature.ReturnType));
        else
            Assert.DoesNotContain(emitter.Triples, triple => triple.Subject == subject
                && triple.Predicate == minter.OntologyPrefix + "signatureReturnType");
        foreach (var convention in pointer.Signature.UnmanagedCallingConventionTypes)
            Has(emitter, subject, "callingConventionType", minter.Type(convention));
        foreach (var parameter in pointer.Signature.Parameters)
        {
            var parameterIri = subject + "/sigparam/" + parameter.Ordinal;
            Assert.Contains(emitter.Triples, triple => triple.Subject == parameterIri
                && triple.Predicate == DotNetOntology.Rdf + "type" && triple.Object == minter.OntologyPrefix + "Parameter");
            Has(emitter, subject, "signatureParameter", parameterIri);
            Has(emitter, parameterIri, "ordinal", parameter.Ordinal.ToString());
            Has(emitter, parameterIri, "refKind", parameter.RefKind.ToString());
            Has(emitter, parameterIri, "parameterType", minter.Type(parameter.Type));
            if (parameter.Type is IFunctionPointerTypeSymbol nested)
                AssertPointer(emitter, minter, nested);
        }
        Assert.DoesNotContain(emitter.Triples, triple => triple.Subject == subject
            && (triple.Predicate == minter.OntologyPrefix + "hasParameter" || triple.Predicate == minter.OntologyPrefix + "returnType"));
    }

    private static void AssertSignatureParameter(TestEmitter emitter, IriMinter minter, IFunctionPointerTypeSymbol pointer, ITypeSymbol target)
    {
        HasOnly(emitter, minter.Type(pointer) + "/sigparam/0", "parameterType", minter.Type(target));
    }

    private static MetadataReference AliasedReference(byte[] image, string alias) =>
        MetadataReference.CreateFromImage(image, new MetadataReferenceProperties(aliases: ImmutableArray.Create(alias)));

    private static byte[] Emit(string assemblyName, string source) => Emit(TestUtilities.CreateCompilation(source, assemblyName));

    private static byte[] Emit(Compilation compilation)
    {
        using var stream = new MemoryStream();
        var result = compilation.Emit(stream);
        Assert.True(result.Success, string.Join(Environment.NewLine, result.Diagnostics));
        return stream.ToArray();
    }

    private static TestEmitter Extract(Compilation compilation, IAssemblySymbol assembly)
    {
        var emitter = new TestEmitter();
        new AssemblyGraphExtractor(emitter, new ExtractionOptions { IncludeAttributes = false }).Extract(compilation, assembly);
        return emitter;
    }

    // Exactly one value for (subject, predicate), and it is the expected one: a merged identity shows up as a
    // second value on the shared subject.
    private static void HasOnly(TestEmitter emitter, string subject, string predicate, string value)
    {
        var values = emitter.Triples.Where(triple => triple.Subject == subject
            && triple.Predicate == "http://dotnet.example/ontology/" + predicate).Select(triple => triple.Object).Distinct().ToList();
        Assert.Equal(new[] { value }, values);
    }

    private static void Has(TestEmitter emitter, string subject, string predicate, string value)
    {
        Assert.Contains(emitter.Triples, triple => triple.Subject == subject
            && triple.Predicate == "http://dotnet.example/ontology/" + predicate && triple.Object == value);
    }

    private static void WithAssembly(Compilation compilation, bool metadata, Action<Compilation, IAssemblySymbol> assert)
    {
        Assert.DoesNotContain(compilation.GetDiagnostics(), diagnostic => diagnostic.Severity == DiagnosticSeverity.Error);
        if (!metadata)
        {
            assert(compilation, compilation.Assembly);
            return;
        }
        using var image = new MemoryStream();
        var emitted = compilation.Emit(image);
        Assert.True(emitted.Success, string.Join(Environment.NewLine, emitted.Diagnostics));
        var reference = MetadataReference.CreateFromImage(image.ToArray());
        var context = TestUtilities.CreateCompilation("").AddReferences(reference);
        assert(context, (IAssemblySymbol)context.GetAssemblyOrModuleSymbol(reference)!);
    }
}
