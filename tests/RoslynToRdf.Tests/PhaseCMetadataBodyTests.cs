using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.Emit;
using Microsoft.CodeAnalysis.Text;
using System.Text;
using Microsoft.CodeAnalysis.VisualBasic;
using System.Reflection.Metadata;
using System.Reflection.PortableExecutable;
using System.Reflection.Metadata.Ecma335;
using System.Reflection;
using RoslynToRdf.Core.Extraction;
using RoslynToRdf.Core.Model;

namespace RoslynToRdf.Tests;

public class PhaseCMetadataBodyTests
{
    [Fact]
    public void MetadataBodies_DeconstructionRetainsEmittedExtensionAndSignatureTargets()
    {
        const string source = """
            using System;
            public class DeconstructionInput {}
            public class FirstComponent {}
            public class SecondComponent {}
            public class Decoy {}
            public static class DeconstructionExtensions {
                public static void Deconstruct(this DeconstructionInput input,
                    out FirstComponent first, out SecondComponent second) {
                    first = null;
                    second = null;
                }
            }
            public class Root {
                public void Body(DeconstructionInput input) {
                    var (first, second) = input;
                    GC.KeepAlive(first);
                    GC.KeepAlive(second);
                }
            }
            """;
        VerifyMetadata(TestUtilities.CreateCompilation(source, "DeconstructionBody"), false, (assembly, minter, triples) =>
        {
            var owner = assembly.GetTypeByMetadataName("Root")!.GetMembers("Body").Single();
            foreach (var target in new[] { "DeconstructionInput", "DeconstructionExtensions", "FirstComponent", "SecondComponent" })
                AssertUse(triples, minter, assembly, owner, target);
            Assert.DoesNotContain(triples.Triples, triple => triple.Subject == minter.Member(owner)
                && triple.Predicate == minter.OntologyPrefix + "usesType"
                && triple.Object == minter.Type(assembly.GetTypeByMetadataName("Decoy")!));
        });
    }

    [Fact]
    public void MetadataBodies_NonVectorRankOneArrayDoesNotInventVectorInstantiation()
    {
        var metadata = new MetadataBuilder();
        metadata.AddModule(0, metadata.GetOrAddString("NonVectorBody.dll"), metadata.GetOrAddGuid(Guid.NewGuid()), default, default);
        metadata.AddAssembly(metadata.GetOrAddString("NonVectorBody"), new Version(1, 0, 0, 0), default, default, default, default);
        var core = typeof(object).Assembly.GetName();
        var coreReference = metadata.AddAssemblyReference(metadata.GetOrAddString(core.Name!), core.Version!, default,
            metadata.GetOrAddBlob(core.GetPublicKeyToken()!), default, default);
        var objectReference = metadata.AddTypeReference(coreReference, metadata.GetOrAddString("System"), metadata.GetOrAddString("Object"));
        var listReference = metadata.AddTypeReference(coreReference, metadata.GetOrAddString("System.Collections.Generic"), metadata.GetOrAddString("List`1"));
        metadata.AddTypeDefinition(TypeAttributes.NotPublic, default, metadata.GetOrAddString("<Module>"), default,
            MetadataTokens.FieldDefinitionHandle(1), MetadataTokens.MethodDefinitionHandle(1));
        metadata.AddTypeDefinition(TypeAttributes.Public, default, metadata.GetOrAddString("Holder"), objectReference,
            MetadataTokens.FieldDefinitionHandle(1), MetadataTokens.MethodDefinitionHandle(1));
        var fieldSignature = new BlobBuilder();
        new BlobEncoder(fieldSignature).FieldSignature().GenericInstantiation(listReference, 1, false).AddArgument()
            .Array(element => element.Int32(), shape => shape.Shape(1, [], []));
        var field = metadata.AddFieldDefinition(FieldAttributes.Public | FieldAttributes.Static,
            metadata.GetOrAddString("Value"), metadata.GetOrAddBlob(fieldSignature));
        var instructions = new BlobBuilder();
        var encoder = new InstructionEncoder(instructions);
        encoder.OpCode(ILOpCode.Ldsfld);
        encoder.Token(field);
        encoder.OpCode(ILOpCode.Ret);
        var il = new BlobBuilder();
        var body = new MethodBodyStreamEncoder(il).AddMethodBody(encoder);
        var signature = new BlobBuilder();
        new BlobEncoder(signature).MethodSignature().Parameters(0, result => result.Type().Object(), parameters => { });
        metadata.AddMethodDefinition(MethodAttributes.Public | MethodAttributes.Static, MethodImplAttributes.IL,
            metadata.GetOrAddString("Read"), metadata.GetOrAddBlob(signature), body, MetadataTokens.ParameterHandle(1));
        var image = new BlobBuilder();
        new ManagedPEBuilder(new PEHeaderBuilder(imageCharacteristics: Characteristics.ExecutableImage | Characteristics.Dll),
            new MetadataRootBuilder(metadata), il).Serialize(image);
        var directory = Path.Combine(Path.GetTempPath(), "roslyn2rdf-tests", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(directory);
        var path = Path.Combine(directory, "NonVectorBody.dll");
        try
        {
            File.WriteAllBytes(path, image.ToArray());
            var reference = MetadataReference.CreateFromFile(path);
            var compilation = TestUtilities.CreateCompilation("").AddReferences(reference);
            var assembly = (IAssemblySymbol)compilation.GetAssemblyOrModuleSymbol(reference)!;
            var holder = assembly.GetTypeByMetadataName("Holder")!;
            var importedField = (IFieldSymbol)holder.GetMembers("Value").Single();
            Assert.False(((IArrayTypeSymbol)((INamedTypeSymbol)importedField.Type).TypeArguments[0]).IsSZArray);
            var emitter = new TestEmitter();
            var options = new ExtractionOptions();
            var extractor = new AssemblyGraphExtractor(emitter, options);
            extractor.Extract(compilation, assembly, path);
            Assert.Empty(extractor.BodyResolutionDiagnostics);
            var minter = new IriMinter(options.BaseUri);
            var list = compilation.GetTypeByMetadataName("System.Collections.Generic.List`1")!;
            var integer = compilation.GetSpecialType(SpecialType.System_Int32);
            var owner = minter.Member(holder.GetMembers("Read").Single());
            foreach (var target in new ITypeSymbol[] { list, integer })
                Assert.Contains(emitter.Triples, triple => triple.Subject == owner
                    && triple.Predicate == minter.OntologyPrefix + "usesType" && triple.Object == minter.Type(target));
            var fabricated = list.Construct(compilation.CreateArrayTypeSymbol(integer));
            Assert.DoesNotContain(emitter.Triples, triple => triple.Subject == owner
                && triple.Predicate == minter.OntologyPrefix + "usesType" && triple.Object == minter.Type(fabricated));
        }
        finally
        {
            Directory.Delete(directory, true);
        }
    }

    [Fact]
    public void MetadataBodies_GenericGeneratedStateMachinesPreserveConstructedTargetsPerOwner()
    {
        const string source = """
            using System;
            using System.Collections.Generic;
            using System.Runtime.CompilerServices;
            using System.Threading.Tasks;
            public class FirstOnly {}
            public class SecondOnly {}
            public class Box<T> {}
            public class GenericAsync {
                public Task<object> First() => Work<FirstOnly>();
                public Task<object> Second() => Work<SecondOnly>();
                public IEnumerable<object> Iterate() => Iteration<FirstOnly>();
                [CompilerGenerated] private static async Task<object> Work<T>() {
                    await Task.Yield();
                    return typeof(Box<T[]>);
                }
                [CompilerGenerated] private static IEnumerable<object> Iteration<T>() {
                    yield return typeof(Box<T[]>);
                }
            }
            """;
        var compilation = TestUtilities.CreateCompilation(source, "GenericStateMachines");
        VerifyMetadata(compilation, false, (assembly, minter, triples) =>
        {
            var root = assembly.GetTypeByMetadataName("GenericAsync")!;
            var box = assembly.GetTypeByMetadataName("Box`1")!;
            foreach (var pair in new[] { ("First", "FirstOnly"), ("Second", "SecondOnly"), ("Iterate", "FirstOnly") })
            {
                var target = box.Construct(compilation.CreateArrayTypeSymbol(assembly.GetTypeByMetadataName(pair.Item2)!));
                Assert.Contains(triples.Triples, triple => triple.Subject == minter.Member(root.GetMembers(pair.Item1).Single())
                    && triple.Predicate == minter.OntologyPrefix + "usesType" && triple.Object == minter.Type(target));
            }
            var wrongTarget = box.Construct(compilation.CreateArrayTypeSymbol(assembly.GetTypeByMetadataName("SecondOnly")!));
            Assert.DoesNotContain(triples.Triples, triple => triple.Subject == minter.Member(root.GetMembers("First").Single())
                && triple.Predicate == minter.OntologyPrefix + "usesType" && triple.Object == minter.Type(wrongTarget));
        });
    }

    [Fact]
    public void MetadataBodies_PrivateSetterBelongsToAdmittedProperty()
    {
        const string source = """
            using System;
            public class SetterOnly {}
            public class Root {
                public object Property {
                    get => null;
                    private set { GC.KeepAlive(new SetterOnly()); }
                }
            }
            """;
        VerifyMetadata(TestUtilities.CreateCompilation(source, "PrivateAccessor"), false, (assembly, minter, triples) =>
            AssertUse(triples, minter, assembly, assembly.GetTypeByMetadataName("Root")!.GetMembers("Property").Single(), "SetterOnly"),
            includePrivate: false);
    }

    [Fact]
    public void MetadataBodies_DoNotInventErasedNameofConstOrConditionalFacts()
    {
        const string source = """
            using System;
            using System.Diagnostics;
            public class NameOnly {}
            public class ConstOnly { public const int Value = 1; }
            public class ConditionalArgument {}
            public class ConditionalOwner {
                [Conditional("NOT_DEFINED")] public static void Invoke(ConditionalArgument value) {}
            }
            public class Root {
                public void Erased() {
                    GC.KeepAlive(nameof(NameOnly));
                    GC.KeepAlive(ConstOnly.Value);
                    ConditionalOwner.Invoke(new ConditionalArgument());
                }
            }
            """;
        var compilation = TestUtilities.CreateCompilation(source, "ErasedFacts");
        var sourceEmitter = new TestEmitter();
        var options = new ExtractionOptions();
        new AssemblyGraphExtractor(sourceEmitter, options).Extract(compilation, compilation.Assembly);
        var sourceMinter = new IriMinter(options.BaseUri);
        foreach (var target in new[] { "NameOnly", "ConstOnly", "ConditionalOwner", "ConditionalArgument" })
            AssertUse(sourceEmitter, sourceMinter, compilation.Assembly, compilation.GetTypeByMetadataName("Root")!.GetMembers("Erased").Single(), target);
        VerifyMetadata(compilation, false, (assembly, minter, triples) =>
        {
            var owner = minter.Member(assembly.GetTypeByMetadataName("Root")!.GetMembers("Erased").Single());
            foreach (var target in new[] { "NameOnly", "ConstOnly", "ConditionalOwner", "ConditionalArgument" })
                Assert.DoesNotContain(triples.Triples, triple => triple.Subject == owner
                    && triple.Predicate == minter.OntologyPrefix + "usesType"
                    && triple.Object == minter.Type(assembly.GetTypeByMetadataName(target)!));
        });
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void MetadataBodies_ExternalTypesUseBoundAssemblyIdentity(bool retargetable)
    {
        var source = """
            using System.Reflection;
            [assembly: AssemblyVersion("2.3.4.5")]
            """ + (retargetable ? "[assembly: AssemblyFlags(AssemblyNameFlags.Retargetable)]" : "") + """
            public class ExternalOnly {}
            public class ExternalDecoy {}
            """;
        var dependency = TestUtilities.CreateCompilation(source, "BodyDependency");
        var (path, directory) = TestUtilities.EmitToTempAssembly(dependency);
        try
        {
            var compilation = TestUtilities.CreateCompilation(
                "public class Consumer { public object Body() => new ExternalOnly(); }", "ExternalConsumer")
                .AddReferences(MetadataReference.CreateFromFile(path));
            VerifyMetadata(compilation, false, (assembly, minter, triples) =>
            {
                var bound = assembly.Modules.First().ReferencedAssemblySymbols.Single(symbol => symbol.Name == "BodyDependency");
                Assert.Equal(new Version(2, 3, 4, 5), bound.Identity.Version);
                Assert.Equal(retargetable, bound.Identity.IsRetargetable);
                var target = bound.GetTypeByMetadataName("ExternalOnly")!;
                var owner = assembly.GetTypeByMetadataName("Consumer")!.GetMembers("Body").Single();
                Assert.Contains(triples.Triples, triple => triple.Subject == minter.Member(owner)
                    && triple.Predicate == minter.OntologyPrefix + "usesType" && triple.Object == minter.Type(target));
                Assert.Contains(triples.Triples, triple => triple.Subject == minter.Type(target)
                    && triple.Predicate == minter.OntologyPrefix + "definedInAssembly" && triple.Object == minter.Assembly(bound));
                Assert.DoesNotContain(triples.Triples, triple => triple.Subject == minter.Member(owner)
                    && triple.Predicate == minter.OntologyPrefix + "usesType"
                    && triple.Object == minter.Type(bound.GetTypeByMetadataName("ExternalDecoy")!));
            });
        }
        finally
        {
            Directory.Delete(directory, true);
        }
    }

    [Theory]
    [InlineData(OptimizationLevel.Debug)]
    [InlineData(OptimizationLevel.Release)]
    public void MetadataBodies_CompilerPatternsRetainSelectedAwaitersAndEnumeratorSignatures(OptimizationLevel optimization)
    {
        const string source = """
            using System;
            using System.Runtime.CompilerServices;
            using System.Threading.Tasks;
            public class ElementTarget {}
            public class ElementSource {
                public static implicit operator ElementTarget(ElementSource value) => null;
            }
            public class Items { public EnumeratorOnly GetEnumerator() => null; }
            public class EnumeratorOnly : IDisposable {
                public ElementSource Current => null;
                public bool MoveNext() => false;
                public void Dispose() {}
            }
            public ref struct GuardOnly { public void Dispose() {} }
            public struct MoveAwaitable { public MoveAwaiterOnly GetAwaiter() => default; }
            public struct MoveAwaiterOnly : INotifyCompletion {
                public bool IsCompleted => true;
                public bool GetResult() => false;
                public void OnCompleted(Action continuation) {}
            }
            public struct DisposeAwaitable { public DisposeAwaiterOnly GetAwaiter() => default; }
            public struct DisposeAwaiterOnly : INotifyCompletion {
                public bool IsCompleted => true;
                public void GetResult() {}
                public void OnCompleted(Action continuation) {}
            }
            public class AsyncItems { public AsyncEnumeratorOnly GetAsyncEnumerator() => null; }
            public class AsyncEnumeratorOnly {
                public int Current => 0;
                public MoveAwaitable MoveNextAsync() => default;
                public DisposeAwaitable DisposeAsync() => default;
            }
            public class AsyncGuardOnly { public DisposeAwaitable DisposeAsync() => default; }
            public class AwaitResultOnly {}
            public struct Awaitable { public AwaiterOnly GetAwaiter() => default; }
            public struct AwaiterOnly : INotifyCompletion {
                public bool IsCompleted => true;
                public AwaitResultOnly GetResult() => null;
                public void OnCompleted(Action continuation) {}
            }
            public class Decoy {}
            public class Patterns {
                public void Synchronous() {
                    foreach (ElementTarget value in new Items()) { GC.KeepAlive(value); }
                    using var guard = new GuardOnly();
                }
                public async Task Asynchronous() {
                    await foreach (var value in new AsyncItems()) { GC.KeepAlive(value); }
                    await using var guard = new AsyncGuardOnly();
                    GC.KeepAlive(await new Awaitable());
                }
            }
            """;
        var compilation = TestUtilities.CreateCompilation(source, "PePatterns")
            .WithOptions(TestUtilities.CreateCompilation("").Options.WithOptimizationLevel(optimization));
        VerifyMetadata(compilation, false, (assembly, minter, triples) =>
        {
            var type = assembly.GetTypeByMetadataName("Patterns")!;
            foreach (var target in new[] { "EnumeratorOnly", "ElementSource", "ElementTarget", "GuardOnly" })
                AssertUse(triples, minter, assembly, type.GetMembers("Synchronous").Single(), target);
            foreach (var target in new[] { "AsyncEnumeratorOnly", "MoveAwaiterOnly", "DisposeAwaiterOnly",
                "AsyncGuardOnly", "AwaiterOnly", "AwaitResultOnly" })
                AssertUse(triples, minter, assembly, type.GetMembers("Asynchronous").Single(), target);
            Assert.DoesNotContain(triples.Triples, triple => triple.Predicate == minter.OntologyPrefix + "usesType"
                && triple.Object == minter.Type(assembly.GetTypeByMetadataName("Decoy")!));
        });
    }

    [Theory]
    [InlineData(OptimizationLevel.Debug, false)]
    [InlineData(OptimizationLevel.Release, true)]
    public void MetadataBodies_VisualBasicGeneratedOwnersAndBodyTokens(OptimizationLevel optimization, bool pdb)
    {
        const string source = """
            Imports System
            Imports System.Collections.Generic
            Imports System.Threading.Tasks
            Public Class DirectOnly
            End Class
            Public Class LambdaOnly
            End Class
            Public Class OtherLambdaOnly
            End Class
            Public Class IteratorOnly
            End Class
            Public Class AsyncOnly
            End Class
            Public Class PrivateOnly
            End Class
            Public Class TokenOnly
            End Class
            Public Class CatchOnly
                Inherits Exception
            End Class
            Public Class GenericOnly
            End Class
            Public Class Decoy
            End Class
            Public Class Inventory
                Public Function Direct() As Object
                    Return New DirectOnly()
                End Function
                Public Function Lambda() As Func(Of Object)
                    Return Function() New LambdaOnly()
                End Function
                Public Function OtherLambda() As Func(Of Object)
                    Return Function() New OtherLambdaOnly()
                End Function
                Public Iterator Function Iterate() As IEnumerable(Of Object)
                    Yield New IteratorOnly()
                End Function
                Public Async Function AsyncBody() As Task(Of Object)
                    Await Task.Yield()
                    Return New AsyncOnly()
                End Function
                Private Function Uncalled() As Object
                    Return New PrivateOnly()
                End Function
                Public Sub Tokens()
                    GC.KeepAlive(GetType(TokenOnly))
                    GC.KeepAlive(New List(Of GenericOnly)())
                    Try
                        GC.KeepAlive(Me)
                    Catch exception As CatchOnly
                        GC.KeepAlive(exception)
                    End Try
                End Sub
            End Class
            """;
        var sourceCompilation = TestUtilities.CreateVisualBasicCompilation(source, "VbBodyInventory")
            .AddReferences(MetadataReference.CreateFromFile(typeof(Microsoft.VisualBasic.Constants).Assembly.Location))
            .AddReferences(MetadataReference.CreateFromFile(Path.Combine(Path.GetDirectoryName(typeof(object).Assembly.Location)!, "System.Runtime.dll")))
            .WithOptions(new VisualBasicCompilationOptions(OutputKind.DynamicallyLinkedLibrary, optimizationLevel: optimization));
        VerifyMetadata(sourceCompilation, pdb, (assembly, minter, triples) =>
        {
            var type = assembly.GetTypeByMetadataName("Inventory")!;
            foreach (var pair in new[] { ("Direct", "DirectOnly"), ("Lambda", "LambdaOnly"),
                ("OtherLambda", "OtherLambdaOnly"), ("Iterate", "IteratorOnly"), ("AsyncBody", "AsyncOnly"),
                ("Uncalled", "PrivateOnly"), ("Tokens", "TokenOnly"), ("Tokens", "CatchOnly"), ("Tokens", "GenericOnly") })
                AssertUse(triples, minter, assembly, type.GetMembers(pair.Item1).Single(), pair.Item2);
            Assert.DoesNotContain(triples.Triples, triple => triple.Subject == minter.Member(type.GetMembers("Lambda").Single())
                && triple.Predicate == minter.OntologyPrefix + "usesType"
                && triple.Object == minter.Type(assembly.GetTypeByMetadataName("OtherLambdaOnly")!));
            Assert.DoesNotContain(triples.Triples, triple => triple.Predicate == minter.OntologyPrefix + "usesType"
                && triple.Object == minter.Type(assembly.GetTypeByMetadataName("Decoy")!));
        });
    }

    [Fact]
    public void MetadataBodies_RejectInvalidImageAndWrongModuleAndReleaseFileHandles()
    {
        var original = TestUtilities.CreateCompilation("public class Root { public object Body() => new object(); }", "ImageIdentity");
        var (path, directory) = TestUtilities.EmitToTempAssembly(original);
        var (differentPath, differentDirectory) = TestUtilities.EmitToTempAssembly(
            TestUtilities.CreateCompilation("public class Root { public object Body() => null; }", "ImageIdentity"));
        try
        {
            var reference = MetadataReference.CreateFromFile(path);
            var compilation = TestUtilities.CreateCompilation("").AddReferences(reference);
            var assembly = (IAssemblySymbol)compilation.GetAssemblyOrModuleSymbol(reference)!;
            Assert.Throws<BadImageFormatException>(() =>
                new AssemblyGraphExtractor(new TestEmitter()).Extract(compilation, assembly, differentPath));
            File.WriteAllBytes(differentPath, new byte[] { 0x4d, 0x5a, 0 });
            Assert.Throws<BadImageFormatException>(() =>
                new AssemblyGraphExtractor(new TestEmitter()).Extract(compilation, assembly, differentPath));
            using var exclusive = File.Open(differentPath, FileMode.Open, FileAccess.ReadWrite, FileShare.None);
        }
        finally
        {
            Directory.Delete(directory, true);
            Directory.Delete(differentDirectory, true);
        }
    }

    [Fact]
    public void MetadataBodies_MalformedIlPropagatesInsteadOfEmptySuccess()
    {
        var original = TestUtilities.CreateCompilation("public class Root { public object Body() => new object(); }", "InvalidBody");
        var (path, directory) = TestUtilities.EmitToTempAssembly(original);
        try
        {
            var bytes = File.ReadAllBytes(path);
            using (var pe = new PEReader(new MemoryStream(bytes)))
            {
                var reader = pe.GetMetadataReader();
                var method = reader.MethodDefinitions.Select(reader.GetMethodDefinition)
                    .Single(method => reader.GetString(method.Name) == "Body");
                var section = pe.PEHeaders.SectionHeaders.Single(section =>
                    method.RelativeVirtualAddress >= section.VirtualAddress
                    && method.RelativeVirtualAddress < section.VirtualAddress + section.VirtualSize);
                var offset = section.PointerToRawData + method.RelativeVirtualAddress - section.VirtualAddress;
                var headerLength = (bytes[offset] & 3) == 2 ? 1 : (bytes[offset + 1] >> 4) * 4;
                bytes[offset + headerLength] = 0xff;
            }
            File.WriteAllBytes(path, bytes);
            var reference = MetadataReference.CreateFromFile(path);
            var compilation = TestUtilities.CreateCompilation("").AddReferences(reference);
            var assembly = (IAssemblySymbol)compilation.GetAssemblyOrModuleSymbol(reference)!;
            Assert.Throws<BadImageFormatException>(() =>
                new AssemblyGraphExtractor(new TestEmitter()).Extract(compilation, assembly, path));
            using var exclusive = File.Open(path, FileMode.Open, FileAccess.ReadWrite, FileShare.None);
        }
        finally
        {
            Directory.Delete(directory, true);
        }
    }

    [Theory]
    [InlineData(OptimizationLevel.Debug, false)]
    [InlineData(OptimizationLevel.Debug, true)]
    [InlineData(OptimizationLevel.Release, false)]
    [InlineData(OptimizationLevel.Release, true)]
    public void MetadataBodies_DecodeTokensSignaturesLocalsCatchAndCalli(OptimizationLevel optimization, bool pdb)
    {
        const string source = """
            using System;
            public class TokenOnly {}
            public class PatternOnly {}
            public class ArrayOnly {}
            public struct SizeOnly { public long Value; }
            public class CatchOnly : Exception {}
            public class FieldOnly {}
            public class MethodArgument {}
            public class GenericArgument {}
            public class OuterArgument {}
            public class InnerArgument {}
            public class CalliArgument {}
            public class CalliReturn {}
            public class LocalOnly {}
            public class GetterOnly {}
            public class SetterOnly {}
            public class AddOnly {}
            public class RemoveOnly {}
            public class InitializerOnly {}
            public class Decoy {}
            public class GenericBox<T> { public static T Value; public static T Take(T value) => value; }
            public class Outer<T> { public class Inner<U> { public static U Take(T value) => default; } }
            public class Helpers {
                public static FieldOnly Field;
                public static void Accept<T>() {}
            }
            public unsafe class Matrix {
                public object Field = new InitializerOnly();
                public object Tokens(object value) {
                    LocalOnly local = null;
                    GC.KeepAlive(local);
                    GC.KeepAlive(typeof(TokenOnly));
                    GC.KeepAlive(value is PatternOnly);
                    GC.KeepAlive(new ArrayOnly[1]);
                    var matrix = new ArrayOnly[2, 2];
                    matrix[0, 0] = null;
                    GC.KeepAlive(matrix[0, 0]);
                    GC.KeepAlive(sizeof(SizeOnly));
                    GC.KeepAlive(Helpers.Field);
                    Helpers.Accept<MethodArgument>();
                    GC.KeepAlive(GenericBox<GenericArgument>.Take(null));
                    GC.KeepAlive(GenericBox<GenericArgument>.Value);
                    GC.KeepAlive(Outer<OuterArgument>.Inner<InnerArgument>.Take(null));
                    try { GC.KeepAlive(value); } catch (CatchOnly) { return null; }
                    return value;
                }
                public CalliReturn Indirect(delegate*<CalliArgument, CalliReturn> pointer) => pointer(null);
                public object Property { get => new GetterOnly(); set { GC.KeepAlive(new SetterOnly()); } }
                public event Action Changed {
                    add { GC.KeepAlive(new AddOnly()); }
                    remove { GC.KeepAlive(new RemoveOnly()); }
                }
            }
            """;
        var compilation = TestUtilities.CreateCompilation(source, "TokenMatrix", allowUnsafe: true)
            .WithOptions(TestUtilities.CreateCompilation("", allowUnsafe: true).Options.WithOptimizationLevel(optimization));
        VerifyMetadata(compilation, pdb, (assembly, minter, triples) =>
        {
            var type = assembly.GetTypeByMetadataName("Matrix")!;
            var method = type.GetMembers("Tokens").OfType<IMethodSymbol>().Single();
            var expected = new[] { "TokenOnly", "PatternOnly", "ArrayOnly", "SizeOnly", "CatchOnly",
                "FieldOnly", "MethodArgument", "GenericArgument", "OuterArgument", "InnerArgument" };
            foreach (var target in expected)
                AssertUse(triples, minter, assembly, method, target);
            if (optimization == OptimizationLevel.Debug)
                AssertUse(triples, minter, assembly, method, "LocalOnly");
            else
                Assert.DoesNotContain(triples.Triples, triple => triple.Subject == minter.Member(method)
                    && triple.Predicate == minter.OntologyPrefix + "usesType"
                    && triple.Object == minter.Type(assembly.GetTypeByMetadataName("LocalOnly")!));
            AssertUse(triples, minter, assembly, type.GetMembers("Indirect").Single(), "CalliArgument");
            AssertUse(triples, minter, assembly, type.GetMembers("Indirect").Single(), "CalliReturn");
            AssertUse(triples, minter, assembly, type.GetMembers("Property").Single(), "GetterOnly");
            AssertUse(triples, minter, assembly, type.GetMembers("Property").Single(), "SetterOnly");
            AssertUse(triples, minter, assembly, type.GetMembers("Changed").Single(), "AddOnly");
            AssertUse(triples, minter, assembly, type.GetMembers("Changed").Single(), "RemoveOnly");
            AssertUse(triples, minter, assembly, type.InstanceConstructors.Single(), "InitializerOnly");
            Assert.DoesNotContain(triples.Triples, triple => triple.Predicate == minter.OntologyPrefix + "usesType"
                && triple.Object == minter.Type(assembly.GetTypeByMetadataName("Decoy")!));
        });
    }

    [Fact]
    public void MetadataBodies_GeneratedCyclesAndSharedTargetsRetainEachOriginalOwner()
    {
        const string source = """
            using System;
            using System.Runtime.CompilerServices;
            public class SharedOnly {}
            public class CycleOnly {}
            public class GenericOnly {}
            public class ClosureOnly {}
            public class Decoy {}
            public class Generated {
                public object First() => Shared();
                public object Second() => Shared();
                [CompilerGenerated] private static object Shared() { CycleA(); return new SharedOnly(); }
                [CompilerGenerated] private static void CycleA() { CycleB(); }
                [CompilerGenerated] private static void CycleB() { GC.KeepAlive(new CycleOnly()); CycleA(); }
                public object GenericLocal() { object Local<T>() => new GenericOnly(); return Local<int>(); }
                public Func<object> Closure(int capture) => () => capture == 0 ? new ClosureOnly() : null;
            }
            """;
        VerifyMetadata(TestUtilities.CreateCompilation(source, "GeneratedCycles"), false, (assembly, minter, triples) =>
        {
            var type = assembly.GetTypeByMetadataName("Generated")!;
            foreach (var name in new[] { "First", "Second" })
            {
                AssertUse(triples, minter, assembly, type.GetMembers(name).Single(), "SharedOnly");
                AssertUse(triples, minter, assembly, type.GetMembers(name).Single(), "CycleOnly");
            }
            AssertUse(triples, minter, assembly, type.GetMembers("GenericLocal").Single(), "GenericOnly");
            AssertUse(triples, minter, assembly, type.GetMembers("Closure").Single(), "ClosureOnly");
            Assert.DoesNotContain(triples.Triples, triple => triple.Subject == minter.Member(type.GetMembers("Shared").Single())
                && triple.Predicate == minter.OntologyPrefix + "usesType");
        });
    }

    private static void AssertUse(TestEmitter triples, IriMinter minter, IAssemblySymbol assembly, ISymbol owner, string target)
    {
        Assert.Contains(triples.Triples, triple => triple.Subject == minter.Member(owner)
            && triple.Predicate == minter.OntologyPrefix + "usesType"
            && triple.Object == minter.Type(assembly.GetTypeByMetadataName(target)!));
    }

    private static void VerifyMetadata(Compilation source, bool pdb, Action<IAssemblySymbol, IriMinter, TestEmitter> verify,
        bool includePrivate = true)
    {
        var directory = Path.Combine(Path.GetTempPath(), "roslyn2rdf-tests", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(directory);
        var path = Path.Combine(directory, source.AssemblyName + ".dll");
        try
        {
            if (pdb)
            {
                source = source.RemoveAllSyntaxTrees().AddSyntaxTrees(source.SyntaxTrees.Select(tree =>
                    tree.WithChangedText(SourceText.From(tree.GetText().ToString(), Encoding.UTF8))));
            }
            using (var image = File.Create(path))
            using (var symbols = pdb ? File.Create(Path.ChangeExtension(path, ".pdb")) : null)
            {
                var result = source.Emit(image, symbols, options: new EmitOptions(debugInformationFormat: DebugInformationFormat.PortablePdb));
                Assert.True(result.Success, string.Join(Environment.NewLine, result.Diagnostics));
            }
            var reference = MetadataReference.CreateFromFile(path);
            var compilation = TestUtilities.CreateCompilation("")
                .WithOptions(TestUtilities.CreateCompilation("").Options.WithMetadataImportOptions(MetadataImportOptions.All))
                .RemoveAllReferences().AddReferences(source.References)
                .AddReferences(reference);
            var assembly = (IAssemblySymbol)compilation.GetAssemblyOrModuleSymbol(reference)!;
            var emitter = new TestEmitter();
            var options = new ExtractionOptions { IncludePrivate = includePrivate, IncludeInternal = true };
            var extractor = new AssemblyGraphExtractor(emitter, options);
            extractor.Extract(compilation, assembly, peImagePath: path);
            Assert.Empty(extractor.BodyResolutionDiagnostics);
            verify(assembly, new IriMinter(options.BaseUri), emitter);
        }
        finally
        {
            Directory.Delete(directory, true);
        }
    }

    [Theory]
    [InlineData(OptimizationLevel.Debug)]
    [InlineData(OptimizationLevel.Release)]
    public void MetadataBodies_KeepLexicalOwnersAndDoNotExpandOrdinaryCallees(OptimizationLevel optimization)
    {
        const string source = """
            using System;
            using System.Collections.Generic;
            using System.Threading.Tasks;
            public class DirectOnly {}
            public class LambdaOnly {}
            public class OtherLambdaOnly {}
            public class IteratorOnly {}
            public class AsyncOnly {}
            public class PrivateOnly {}
            public class CalleeOnly {}
            public class Decoy {}
            public class Inventory {
              public object Direct() => new DirectOnly();
              public Func<object> Lambda() => () => new LambdaOnly();
              public Func<object> OtherLambda() => () => new OtherLambdaOnly();
              public IEnumerable<object> Iterator() { yield return new IteratorOnly(); }
              public async Task<object> Async() { await Task.Yield(); return new AsyncOnly(); }
              private object Uncalled() => new PrivateOnly();
              public object Caller() => Callee();
              public object Callee() => new CalleeOnly();
            }
            """;
        var sourceCompilation = TestUtilities.CreateCompilation(source, "BodyInventory")
            .WithOptions(TestUtilities.CreateCompilation("").Options.WithOptimizationLevel(optimization));
        var (path, directory) = TestUtilities.EmitToTempAssembly(sourceCompilation);
        try
        {
            var reference = MetadataReference.CreateFromFile(path);
            var compilation = TestUtilities.CreateCompilation("")
                .WithOptions(TestUtilities.CreateCompilation("").Options.WithMetadataImportOptions(MetadataImportOptions.All))
                .AddReferences(reference);
            var assembly = (IAssemblySymbol)compilation.GetAssemblyOrModuleSymbol(reference)!;
            var emitter = new TestEmitter();
            var options = new ExtractionOptions { IncludePrivate = true, IncludeInternal = true };
            new AssemblyGraphExtractor(emitter, options).Extract(compilation, assembly, peImagePath: path);
            var minter = new IriMinter(options.BaseUri);
            var root = assembly.GetTypeByMetadataName("Inventory")!;
            foreach (var pair in new[] {
                ("Direct", "DirectOnly"), ("Lambda", "LambdaOnly"), ("OtherLambda", "OtherLambdaOnly"),
                ("Iterator", "IteratorOnly"), ("Async", "AsyncOnly"), ("Uncalled", "PrivateOnly") })
            {
                var owner = minter.Member(root.GetMembers(pair.Item1).OfType<IMethodSymbol>().Single());
                var target = minter.Type(assembly.GetTypeByMetadataName(pair.Item2)!);
                Assert.Contains(emitter.Triples, triple => triple.Subject == owner
                    && triple.Predicate == minter.OntologyPrefix + "usesType" && triple.Object == target);
            }
            foreach (var pair in new[] { ("Lambda", "OtherLambdaOnly"), ("OtherLambda", "LambdaOnly"),
                ("Caller", "CalleeOnly"), ("Direct", "Decoy") })
            {
                var owner = minter.Member(root.GetMembers(pair.Item1).OfType<IMethodSymbol>().Single());
                var target = minter.Type(assembly.GetTypeByMetadataName(pair.Item2)!);
                Assert.DoesNotContain(emitter.Triples, triple => triple.Subject == owner
                    && triple.Predicate == minter.OntologyPrefix + "usesType" && triple.Object == target);
            }
        }
        finally
        {
            Directory.Delete(directory, true);
        }
    }
}
