using Microsoft.CodeAnalysis;
using RoslynToRdf.Core.Extraction;
using RoslynToRdf.Core.Model;

namespace RoslynToRdf.Tests;

public class PhaseCSignatureTests
{
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

    private static TestEmitter Extract(Compilation compilation, IAssemblySymbol assembly)
    {
        var emitter = new TestEmitter();
        new AssemblyGraphExtractor(emitter, new ExtractionOptions { IncludeAttributes = false }).Extract(compilation, assembly);
        return emitter;
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
