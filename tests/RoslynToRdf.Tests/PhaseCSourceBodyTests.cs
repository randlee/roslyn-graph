using Microsoft.CodeAnalysis;
using RoslynToRdf.Core.Extraction;
using RoslynToRdf.Core.Model;

namespace RoslynToRdf.Tests;

public class PhaseCSourceBodyTests
{
    [Fact]
    public void SourceBodies_PrimaryConstructorsDoNotOwnUnrelatedMembersAndPartialBodiesAreIncluded()
    {
        var compilation = TestUtilities.CreateCompilation("""
            class Base { public Base(object value) {} }
            class BaseArgument {}
            class OtherOnly {}
            class PartialOnly {}
            partial class Root(int value) : Base(new BaseArgument()) {
                public void Other() { _ = new OtherOnly(); }
                partial void Part();
            }
            partial class Root {
                partial void Part() { _ = new PartialOnly(); }
            }
            """);
        var (emitter, minter) = Extract(compilation);
        AssertUses(compilation, emitter, minter, "Root", ".ctor", "BaseArgument");
        AssertUses(compilation, emitter, minter, "Root", "Part", "PartialOnly");
        var constructor = minter.Member(compilation.GetTypeByMetadataName("Root")!.InstanceConstructors.Single());
        Assert.DoesNotContain(emitter.Triples, triple => triple.Subject == constructor
            && triple.Predicate == minter.OntologyPrefix + "usesType"
            && triple.Object == minter.Type(compilation.GetTypeByMetadataName("OtherOnly")!));
    }

    [Fact]
    public void SourceBodies_CoverAccessorConstructorsUnsafeAndErasedCalls()
    {
        var compilation = TestUtilities.CreateCompilation("""
            using System;
            using System.Diagnostics;
            class GetterOnly {}
            class SetterOnly {}
            class AddOnly {}
            class RemoveOnly {}
            class ConstructorOnly {}
            class ErasedOnly { [Conditional("UNDEFINED")] public static void Call() {} }
            class ConstOnly { public const int Value = 1; }
            struct PointerOnly { public int Value; }
            struct SizeOnly { public int Value; }
            interface Contract { void Body(); }
            unsafe class Root : Contract {
                Root() { _ = new ConstructorOnly(); }
                object Property { get { return new GetterOnly(); } set { _ = new SetterOnly(); } }
                event Action Event {
                    add { _ = new AddOnly(); }
                    remove { _ = new RemoveOnly(); }
                }
                void Contract.Body() {
                    ErasedOnly.Call();
                    _ = ConstOnly.Value;
                    PointerOnly* pointer = null;
                    _ = sizeof(SizeOnly);
                    delegate*<PointerOnly*, SizeOnly> callable = null;
                    _ = default(PointerOnly);
                }
            }
            """, allowUnsafe: true);
        var (emitter, minter) = Extract(compilation);
        AssertUses(compilation, emitter, minter, "Root", ".ctor", "ConstructorOnly");
        AssertUses(compilation, emitter, minter, "Root", "Property", "GetterOnly", "SetterOnly");
        AssertUses(compilation, emitter, minter, "Root", "Event", "AddOnly", "RemoveOnly");
        AssertUses(compilation, emitter, minter, "Root", "Contract.Body", "ErasedOnly", "ConstOnly", "PointerOnly", "SizeOnly");
    }

    [Fact]
    public void CompilerSelectedMembers_IncludeForeachAwaitAndUsingInsideNestedFunctions()
    {
        var compilation = TestUtilities.CreateCompilation("""
            using System;
            using System.Runtime.CompilerServices;
            using System.Threading.Tasks;
            class Element {}
            class Enumerable { public Enumerator GetEnumerator() => null; }
            class Enumerator {
                public Element Current => null;
                public bool MoveNext() => false;
            }
            class Awaitable {}
            class AwaitResult {}
            struct Awaiter : INotifyCompletion {
                public bool IsCompleted => true;
                public AwaitResult GetResult() => null;
                public void OnCompleted(Action continuation) {}
            }
            static class Extensions { public static Awaiter GetAwaiter(this Awaitable value) => default; }
            ref struct Resource { public void Dispose() {} }
            class Decoy {}
            class Root {
                public async Task Body() {
                    foreach (var item in new Enumerable()) {}
                    _ = await new Awaitable();
                    void Local() { using var resource = new Resource(); }
                    Action lambda = () => { using var resource = new Resource(); };
                }
            }
            """);
        var (emitter, minter) = Extract(compilation);
        AssertUses(compilation, emitter, minter, "Root", "Body",
            "Enumerable", "Enumerator", "Element", "Awaitable", "Awaiter", "AwaitResult", "Extensions", "Resource");
        Assert.DoesNotContain(emitter.Triples, triple => triple.Predicate == minter.OntologyPrefix + "usesType"
            && triple.Object == minter.Type(compilation.GetTypeByMetadataName("Decoy")!));
    }

    [Fact]
    public void CompilerSelectedMembers_IncludeImplicitAsyncPatternAwaiters()
    {
        var compilation = TestUtilities.CreateCompilation("""
            using System;
            using System.Runtime.CompilerServices;
            using System.Threading;
            using System.Threading.Tasks;
            class Item {}
            class AsyncSequence { public AsyncEnumerator GetAsyncEnumerator(CancellationToken cancellation = default) => null; }
            class AsyncEnumerator {
                public Item Current => null;
                public MoveAwaitable MoveNextAsync() => default;
                public DisposeAwaitable DisposeAsync() => default;
            }
            class AsyncResource { public DisposeAwaitable DisposeAsync() => default; }
            struct MoveAwaitable {}
            struct DisposeAwaitable {}
            struct MoveAwaiter : INotifyCompletion {
                public bool IsCompleted => true;
                public bool GetResult() => false;
                public void OnCompleted(Action continuation) {}
            }
            struct DisposeAwaiter : INotifyCompletion {
                public bool IsCompleted => true;
                public void GetResult() {}
                public void OnCompleted(Action continuation) {}
            }
            static class AwaitExtensions {
                public static MoveAwaiter GetAwaiter(this MoveAwaitable value) => default;
                public static DisposeAwaiter GetAwaiter(this DisposeAwaitable value) => default;
            }
            class Root {
                public async Task Body() {
                    await foreach (var item in new AsyncSequence()) {}
                    await using var resource = new AsyncResource();
                }
            }
            """);
        var (emitter, minter) = Extract(compilation);
        AssertUses(compilation, emitter, minter, "Root", "Body",
            "AsyncSequence", "AsyncEnumerator", "Item", "MoveAwaitable", "MoveAwaiter",
            "DisposeAwaitable", "DisposeAwaiter", "AwaitExtensions", "AsyncResource");
    }

    [Fact]
    public void VisualBasicBodies_IncludeBlocksInitializersAndCompilerPatterns()
    {
        var compilation = TestUtilities.CreateVisualBasicCompilation("""
            Imports System
            Imports System.Runtime.CompilerServices
            Imports System.Threading.Tasks
            Public Class InitializerOnly
            End Class
            Public Class PrivateOnly
            End Class
            Public Class LambdaOnly
            End Class
            Public Class NamedOnly
            End Class
            Public Class Element
            End Class
            Public Class Sequence
                Public Function GetEnumerator() As Enumerator
                    Return Nothing
                End Function
            End Class
            Public Class Enumerator
                Public ReadOnly Property Current As Element
                    Get
                        Return Nothing
                    End Get
                End Property
                Public Function MoveNext() As Boolean
                    Return False
                End Function
            End Class
            Public Class Awaitable
                Public Function GetAwaiter() As Awaiter
                    Return Nothing
                End Function
            End Class
            Public Class AwaitResult
            End Class
            Public Class Awaiter
                Implements INotifyCompletion
                Public ReadOnly Property IsCompleted As Boolean
                    Get
                        Return True
                    End Get
                End Property
                Public Function GetResult() As AwaitResult
                    Return Nothing
                End Function
                Public Sub OnCompleted(action As Action) Implements INotifyCompletion.OnCompleted
                End Sub
            End Class
            Public Class Root
                Private field As New InitializerOnly()
                Private Sub Hidden()
                    Dim value = New PrivateOnly()
                End Sub
                Public Async Function Body() As Task
                    For Each value In New Sequence()
                    Next
                    Dim result = Await New Awaitable()
                    Dim name = NameOf(NamedOnly)
                    Dim lambda As Func(Of Object) = Function() New LambdaOnly()
                End Function
            End Class
            """);
        var (emitter, minter) = Extract(compilation);
        AssertUses(compilation, emitter, minter, "Root", "Body",
            "Sequence", "Enumerator", "Element", "Awaitable", "Awaiter", "AwaitResult", "NamedOnly", "LambdaOnly");
        AssertUses(compilation, emitter, minter, "Root", "field", "InitializerOnly");
        AssertUses(compilation, emitter, minter, "Root", "Hidden", "PrivateOnly");
    }

    [Fact]
    public void SourceBodies_KeepLexicalOwnersAndErasedReferences()
    {
        var compilation = TestUtilities.CreateCompilation("""
            using System;
            class Allocated {}
            class PrivateOnly {}
            class LambdaOnly {}
            class LocalOnly {}
            class InitializerOnly {}
            class GetterOnly {}
            class NamedOnly {}
            class PatternOnly {}
            class Decoy {}
            class Root {
                object field = new InitializerOnly();
                object Property => new GetterOnly();
                private void Hidden() { _ = new PrivateOnly(); }
                public void Body(object input) {
                    _ = new Allocated();
                    Func<object> lambda = () => new LambdaOnly();
                    object Local() => new LocalOnly();
                    _ = nameof(NamedOnly);
                    if (input is PatternOnly) {}
                }
            }
            """);
        var (emitter, minter) = Extract(compilation);
        AssertUses(compilation, emitter, minter, "Root", "Body", "Allocated", "LambdaOnly", "LocalOnly", "NamedOnly", "PatternOnly");
        AssertUses(compilation, emitter, minter, "Root", "Hidden", "PrivateOnly");
        AssertUses(compilation, emitter, minter, "Root", "field", "InitializerOnly");
        AssertUses(compilation, emitter, minter, "Root", "Property", "GetterOnly");
        Assert.DoesNotContain(emitter.Triples, triple => triple.Predicate == minter.OntologyPrefix + "usesType"
            && triple.Object == minter.Type(compilation.GetTypeByMetadataName("Decoy")!));
        var body = minter.Member(compilation.GetTypeByMetadataName("Root")!.GetMembers("Body").Single());
        Assert.DoesNotContain(emitter.Triples, triple => triple.Subject == body
            && triple.Predicate == minter.OntologyPrefix + "usesType"
            && triple.Object == minter.Type(compilation.GetTypeByMetadataName("PrivateOnly")!));
    }

    [Fact]
    public void SourceBodies_IncludeConversionsCatchTokensAndGenericArguments()
    {
        var compilation = TestUtilities.CreateCompilation("""
            using System;
            class Token {}
            class Arg {}
            class Box<T> {}
            class Failure : Exception {}
            class Converted { public static explicit operator Converted(int value) => null; }
            class Root {
                public void Body() {
                    _ = typeof(Token);
                    Box<Arg>[] local = new Box<Arg>[1];
                    _ = (Converted)1;
                    try { throw new Failure(); } catch (Failure) {}
                }
            }
            """);
        var (emitter, minter) = Extract(compilation);
        AssertUses(compilation, emitter, minter, "Root", "Body", "Token", "Arg", "Failure", "Converted");
    }

    private static (TestEmitter emitter, IriMinter minter) Extract(Compilation compilation)
    {
        Assert.DoesNotContain(compilation.GetDiagnostics(), diagnostic => diagnostic.Severity == DiagnosticSeverity.Error);
        var emitter = new TestEmitter();
        var options = new ExtractionOptions { IncludePrivate = true, IncludeInternal = true };
        var diagnostics = new List<string>();
        new AssemblyGraphExtractor(emitter, options, diagnostics.Add).Extract(compilation, compilation.Assembly);
        Assert.DoesNotContain(diagnostics, message => message.StartsWith("Could not", StringComparison.Ordinal));
        return (emitter, new IriMinter(options.BaseUri));
    }

    private static void AssertUses(Compilation compilation, TestEmitter emitter, IriMinter minter,
        string ownerType, string member, params string[] targets)
    {
        var owner = minter.Member(compilation.GetTypeByMetadataName(ownerType)!.GetMembers(member).Single());
        foreach (var target in targets)
            Assert.Single(emitter.Triples.Where(triple => triple.Subject == owner
                && triple.Predicate == minter.OntologyPrefix + "usesType"
                && triple.Object == minter.Type(compilation.GetTypeByMetadataName(target)!)));
    }
}
