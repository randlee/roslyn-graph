using Microsoft.CodeAnalysis;
using RoslynToRdf.Core.Extraction;
using RoslynToRdf.Core.Model;

namespace RoslynToRdf.Tests;

public class PhaseCSourceBodyTests
{
    [Fact]
    public void Deconstruction_EmitsSelectedAssignmentNestedAndForeachMethodsOnly()
    {
        var compilation = TestUtilities.CreateCompilation("""
            class AssignmentInput {}
            class OuterInput {}
            class InnerInput {}
            class ForeachInput {}
            class Decoy {}
            static class AssignmentExtensions {
                public static void Deconstruct(this AssignmentInput input, out int left, out int right) { left = right = 0; }
            }
            static class OuterExtensions {
                public static void Deconstruct(this OuterInput input, out InnerInput inner, out int right) { inner = null; right = 0; }
            }
            static class InnerExtensions {
                public static void Deconstruct(this InnerInput input, out int left, out int right) { left = right = 0; }
            }
            static class ForeachExtensions {
                public static void Deconstruct(this ForeachInput input, out int left, out int right) { left = right = 0; }
            }
            static class DecoyExtensions {
                public static void Deconstruct(this Decoy input, out int left, out int right) { left = right = 0; }
            }
            class Root {
                public void Assignment(AssignmentInput input) { var (left, right) = input; }
                public void Nested(OuterInput input) { var ((left, middle), right) = input; }
                public void Foreach(ForeachInput[] inputs) { foreach (var (left, right) in inputs) {} }
            }
            """);
        var (emitter, minter) = Extract(compilation);
        var rows = new (string Owner, string[] Targets)[]
        {
            ("Assignment", ["AssignmentExtensions"]),
            ("Nested", ["OuterExtensions", "InnerExtensions"]),
            ("Foreach", ["ForeachExtensions"])
        };
        foreach (var row in rows)
        {
            AssertUses(compilation, emitter, minter, "Root", row.Owner, row.Targets);
            var owner = minter.Member(compilation.GetTypeByMetadataName("Root")!.GetMembers(row.Owner).Single());
            foreach (var decoy in rows.Where(other => other.Owner != row.Owner).SelectMany(other => other.Targets).Append("DecoyExtensions"))
                Assert.DoesNotContain(emitter.Triples, triple => triple.Subject == owner
                    && triple.Predicate == minter.OntologyPrefix + "usesType"
                    && triple.Object == minter.Type(compilation.GetTypeByMetadataName(decoy)!));
        }
    }

    [Fact]
    public void UnsafeSourceRows_SeparatePointerFunctionPointerAndSizeOfTargets()
    {
        var compilation = TestUtilities.CreateCompilation("""
            struct PointerOnly { public int Value; }
            struct FunctionArg { public int Value; }
            struct FunctionReturn { public int Value; }
            struct SizeOnly { public int Value; }
            unsafe class Root {
                public void Pointer() { PointerOnly* value; }
                public void FunctionPointer() { delegate*<FunctionArg*, FunctionReturn> value; }
                public int Size() => sizeof(SizeOnly);
            }
            """, allowUnsafe: true);
        var (emitter, minter) = Extract(compilation);
        AssertUses(compilation, emitter, minter, "Root", "Pointer", "PointerOnly");
        AssertUses(compilation, emitter, minter, "Root", "FunctionPointer", "FunctionArg", "FunctionReturn");
        AssertUses(compilation, emitter, minter, "Root", "Size", "SizeOnly");
    }

    [Fact]
    public void VisualBasic_SourceErasedConversionsAndAccessorOwnersHaveDistinctTargets()
    {
        var compilation = TestUtilities.CreateVisualBasicCompilation("""
            Imports System
            Imports System.Collections.Generic
            Imports System.Diagnostics
            Public Class ErasedOnly
                <Conditional("UNDEFINED")>
                Public Shared Sub CallIt()
                End Sub
            End Class
            Public Class ConstOnly
                Public Const Value As Integer = 1
            End Class
            Public Class TokenOnly
            End Class
            Public Class Converted
                Public Shared Narrowing Operator CType(value As Integer) As Converted
                    Return Nothing
                End Operator
            End Class
            Public Class GetterOnly
            End Class
            Public Class SetterOnly
            End Class
            Public Class IteratorOnly
            End Class
            Public Class Root
                Public Sub Erased()
                    ErasedOnly.CallIt()
                End Sub
                Public Function Constant() As Integer
                    Return ConstOnly.Value
                End Function
                Public Function Token() As Type
                    Return GetType(TokenOnly)
                End Function
                Public Function Conversion() As Object
                    Return CType(1, Converted)
                End Function
                Public Property Value As Object
                    Get
                        Return New GetterOnly()
                    End Get
                    Set(value As Object)
                        Dim result = New SetterOnly()
                    End Set
                End Property
                Public Iterator Function Items() As IEnumerable(Of Object)
                    Yield New IteratorOnly()
                End Function
            End Class
            """);
        var (emitter, minter) = Extract(compilation);
        var rows = new (string Owner, string[] Targets)[]
        {
            ("Erased", ["ErasedOnly"]), ("Constant", ["ConstOnly"]), ("Token", ["TokenOnly"]),
            ("Conversion", ["Converted"]), ("Value", ["GetterOnly", "SetterOnly"]), ("Items", ["IteratorOnly"])
        };
        foreach (var row in rows)
        {
            AssertUses(compilation, emitter, minter, "Root", row.Owner, row.Targets);
            var owner = minter.Member(compilation.GetTypeByMetadataName("Root")!.GetMembers(row.Owner).Single());
            foreach (var decoy in rows.Where(other => other.Owner != row.Owner).SelectMany(other => other.Targets))
                Assert.DoesNotContain(emitter.Triples, triple => triple.Subject == owner
                    && triple.Predicate == minter.OntologyPrefix + "usesType"
                    && triple.Object == minter.Type(compilation.GetTypeByMetadataName(decoy)!));
        }
    }

    [Fact]
    public void AdmittedProperty_IncludesPrivateSetterBodyWithoutPrivateMemberOption()
    {
        var compilation = TestUtilities.CreateCompilation("""
            public class SetterOnly {}
            public class UnrequestedOnly {}
            public class Root {
                public object Property { get => null; private set { _ = new SetterOnly(); } }
                private void Hidden() { _ = new UnrequestedOnly(); }
            }
            """);
        var emitter = new TestEmitter();
        var options = new ExtractionOptions { IncludePrivate = false };
        new AssemblyGraphExtractor(emitter, options).Extract(compilation, compilation.Assembly);
        var minter = new IriMinter(options.BaseUri);
        AssertUses(compilation, emitter, minter, "Root", "Property", "SetterOnly");
        Assert.DoesNotContain(emitter.Triples, triple => triple.Predicate == minter.OntologyPrefix + "usesType"
            && triple.Object == minter.Type(compilation.GetTypeByMetadataName("UnrequestedOnly")!));
    }

    [Fact]
    public void VisualBasicSourceRows_HaveIndependentBodyOnlyTargetsAndOwners()
    {
        var declarations = string.Join(Environment.NewLine, new[]
        {
            "ArrayOnly", "LocalOnly", "DefaultOnly", "TypeOnly", "AliasOnly", "NamedReturnOnly",
            "NamedParameterOnly", "GenericOnly", "CallParameterOnly", "CallReturnOnly",
            "GroupParameterOnly", "FieldOnly", "PropertyOnly", "IndexOnly", "EventOnly", "Decoy"
        }.Select(name => $"Public Class {name}{Environment.NewLine}End Class"));
        var compilation = TestUtilities.CreateVisualBasicCompilation("""
            Imports System
            Imports AliasName = AliasOnly
            Public Class CatchOnly
                Inherits Exception
            End Class
            Public Class ThrowOnly
                Inherits Exception
            End Class
            Public Class CallHost
                Public Shared Function Invoke(Of T)(Optional value As CallParameterOnly = Nothing) As CallReturnOnly
                    Return Nothing
                End Function
            End Class
            Public Class GroupHost
                Public Shared Sub Method(value As GroupParameterOnly)
                End Sub
            End Class
            Public Class NamedHost
                Public Shared Function Method(value As NamedParameterOnly) As NamedReturnOnly
                    Return Nothing
                End Function
            End Class
            Public Class FieldHost
                Public Shared Value As FieldOnly
            End Class
            Public Class PropertyHost
                Public Shared ReadOnly Property Value As PropertyOnly
                    Get
                        Return Nothing
                    End Get
                End Property
            End Class
            Public Class IndexHost
                Default Public ReadOnly Property Item(index As Integer) As IndexOnly
                    Get
                        Return Nothing
                    End Get
                End Property
            End Class
            Public Class EventHost
                Public Shared Event Changed As Action(Of EventOnly)
            End Class
            Public Class Root
                Public Sub Arrays()
                    Dim value = New ArrayOnly(0) {}
                End Sub
                Public Sub Locals()
                    Dim value As LocalOnly
                End Sub
                Public Sub Defaults()
                    Dim value = CType(Nothing, DefaultOnly)
                End Sub
                Public Sub Catches()
                    Try
                    Catch failure As CatchOnly
                    End Try
                End Sub
                Public Sub Throws(failure As ThrowOnly)
                    Throw failure
                End Sub
                Public Function Types(value As Object) As Boolean
                    Return TypeOf value Is TypeOnly
                End Function
                Public Function Aliases() As String
                    Return NameOf(AliasName)
                End Function
                Public Function NamedMember() As String
                    Return NameOf(NamedHost.Method)
                End Function
                Public Sub Invoke()
                    Dim value = CallHost.Invoke(Of GenericOnly)()
                End Sub
                Public Sub Group()
                    Dim callback As Action(Of GroupParameterOnly) = AddressOf GroupHost.Method
                End Sub
                Public Sub Fields()
                    Dim value = FieldHost.Value
                End Sub
                Public Sub Properties()
                    Dim value = PropertyHost.Value
                End Sub
                Public Sub Indexes(value As IndexHost)
                    Dim result = value(0)
                End Sub
                Public Sub Events()
                    AddHandler EventHost.Changed, Sub(value)
                                                 End Sub
                End Sub
            End Class
            """ + Environment.NewLine + declarations);
        var (emitter, minter) = Extract(compilation);
        var rows = new (string Owner, string[] Targets)[]
        {
            ("Arrays", ["ArrayOnly"]), ("Locals", ["LocalOnly"]), ("Defaults", ["DefaultOnly"]),
            ("Catches", ["CatchOnly"]), ("Throws", ["ThrowOnly"]), ("Types", ["TypeOnly"]),
            ("Aliases", ["AliasOnly"]), ("NamedMember", ["NamedHost", "NamedReturnOnly", "NamedParameterOnly"]),
            ("Invoke", ["CallHost", "CallParameterOnly", "CallReturnOnly", "GenericOnly"]),
            ("Group", ["GroupHost", "GroupParameterOnly"]), ("Fields", ["FieldHost", "FieldOnly"]),
            ("Properties", ["PropertyHost", "PropertyOnly"]), ("Indexes", ["IndexHost", "IndexOnly"]),
            ("Events", ["EventHost", "EventOnly"])
        };
        foreach (var row in rows)
        {
            AssertUses(compilation, emitter, minter, "Root", row.Owner, row.Targets);
            var owner = minter.Member(compilation.GetTypeByMetadataName("Root")!.GetMembers(row.Owner).Single());
            foreach (var decoy in rows.Where(other => other.Owner != row.Owner).SelectMany(other => other.Targets).Append("Decoy"))
                Assert.DoesNotContain(emitter.Triples, triple => triple.Subject == owner
                    && triple.Predicate == minter.OntologyPrefix + "usesType"
                    && triple.Object == minter.Type(compilation.GetTypeByMetadataName(decoy)!));
        }
    }

    [Fact]
    public void SourceRows_HaveIndependentBodyOnlyTargetsAndOwners()
    {
        var compilation = TestUtilities.CreateCompilation("""
            using System;
            using Alias = AliasOnly;
            class ArrayOnly {}
            class LocalOnly {}
            class DefaultOnly {}
            class CatchOnly : Exception {}
            class ThrowOnly : Exception {}
            class DeclarationOnly {}
            class TypeOnly {}
            class AliasOnly {}
            class NamedReturnOnly {}
            class NamedParameterOnly {}
            class GenericOnly {}
            class CallParameterOnly {}
            class CallReturnOnly {}
            class GroupParameterOnly {}
            class FieldOnly {}
            class PropertyOnly {}
            class IndexOnly {}
            class EventOnly {}
            class Decoy {}
            static class CallHost {
                public static CallReturnOnly Call<T>(CallParameterOnly parameter = null) => null;
            }
            static class GroupHost { public static void Method(GroupParameterOnly value) {} }
            static class NamedHost { public static NamedReturnOnly Method(NamedParameterOnly value) => null; }
            static class FieldHost { public static FieldOnly Value; }
            static class PropertyHost { public static PropertyOnly Value => null; }
            class IndexHost { public IndexOnly this[int index] => null; }
            static class EventHost { public static event Action<EventOnly> Changed; }
            class Root {
                public void Array() { _ = new ArrayOnly[1]; }
                public void Local() { LocalOnly value; }
                public void Default() { _ = default(DefaultOnly); }
                public void Catch() { try {} catch (CatchOnly) {} }
                public void Throw(ThrowOnly failure) { throw failure; }
                public bool Declaration(object value) => value is DeclarationOnly captured;
                public int Type(object value) => value switch { TypeOnly => 1, _ => 0 };
                public string Aliases() => nameof(Alias);
                public string NamedMember() => nameof(NamedHost.Method);
                public void Invoke() { _ = CallHost.Call<GenericOnly>(); }
                public void Group() { Action<GroupParameterOnly> callback = GroupHost.Method; }
                public void Field() { _ = FieldHost.Value; }
                public void Property() { _ = PropertyHost.Value; }
                public void Index(IndexHost value) { _ = value[0]; }
                public void Event() { EventHost.Changed += value => {}; }
            }
            """);
        var (emitter, minter) = Extract(compilation);
        var rows = new (string Owner, string[] Targets)[]
        {
            ("Array", ["ArrayOnly"]), ("Local", ["LocalOnly"]), ("Default", ["DefaultOnly"]),
            ("Catch", ["CatchOnly"]), ("Throw", ["ThrowOnly"]), ("Declaration", ["DeclarationOnly"]),
            ("Type", ["TypeOnly"]), ("Aliases", ["AliasOnly"]),
            ("NamedMember", ["NamedHost", "NamedReturnOnly", "NamedParameterOnly"]),
            ("Invoke", ["CallHost", "CallParameterOnly", "CallReturnOnly", "GenericOnly"]),
            ("Group", ["GroupHost", "GroupParameterOnly"]), ("Field", ["FieldHost", "FieldOnly"]),
            ("Property", ["PropertyHost", "PropertyOnly"]), ("Index", ["IndexHost", "IndexOnly"]),
            ("Event", ["EventHost", "EventOnly"])
        };
        foreach (var row in rows)
        {
            AssertUses(compilation, emitter, minter, "Root", row.Owner, row.Targets);
            var owner = minter.Member(compilation.GetTypeByMetadataName("Root")!.GetMembers(row.Owner).Single());
            foreach (var decoy in rows.Where(other => other.Owner != row.Owner).SelectMany(other => other.Targets).Append("Decoy"))
                Assert.DoesNotContain(emitter.Triples, triple => triple.Subject == owner
                    && triple.Predicate == minter.OntologyPrefix + "usesType"
                    && triple.Object == minter.Type(compilation.GetTypeByMetadataName(decoy)!));
        }
    }

    [Fact]
    public void IteratorAndCapturedLambda_KeepSelfUseButNeverTypeParameterTargets()
    {
        var compilation = TestUtilities.CreateCompilation("""
            using System;
            using System.Collections.Generic;
            class IteratorOnly {}
            class CaptureOnly {}
            class Decoy {}
            class Root<T> {
                public IEnumerable<object> Body(object captured) {
                    T unused = default;
                    _ = new Root<T>();
                    Func<object> lambda = () => captured ?? new CaptureOnly();
                    yield return new IteratorOnly();
                }
            }
            """);
        var (emitter, minter) = Extract(compilation);
        AssertUses(compilation, emitter, minter, "Root`1", "Body", "Root`1", "IteratorOnly", "CaptureOnly");
        var type = compilation.GetTypeByMetadataName("Root`1")!;
        var owner = minter.Member(type.GetMembers("Body").Single());
        Assert.DoesNotContain(emitter.Triples, triple => triple.Subject == owner
            && triple.Predicate == minter.OntologyPrefix + "usesType"
            && (triple.Object == minter.Type(type.TypeParameters.Single())
                || triple.Object == minter.Type(compilation.GetTypeByMetadataName("Decoy")!)));
    }

    [Fact]
    public void UnreachableAsyncUsing_StillIncludesCompilerSelectedAwaiter()
    {
        var compilation = TestUtilities.CreateCompilation("""
            using System;
            using System.Runtime.CompilerServices;
            using System.Threading.Tasks;
            class Resource { public Awaitable DisposeAsync() => default; }
            struct Awaitable {}
            struct Awaiter : INotifyCompletion {
                public bool IsCompleted => true;
                public void GetResult() {}
                public void OnCompleted(Action action) {}
            }
            static class Extensions { public static Awaiter GetAwaiter(this Awaitable value) => default; }
            class Root {
                public async Task Body() {
                    if (false) { await using var resource = new Resource(); }
                }
            }
            """);
        var (emitter, minter) = Extract(compilation);
        AssertUses(compilation, emitter, minter, "Root", "Body", "Resource", "Awaitable", "Awaiter", "Extensions");
    }

    [Fact]
    public void PositionalPatterns_IncludeBoundExtensionDeconstructButNotUnusedOverloads()
    {
        var compilation = TestUtilities.CreateCompilation("""
            class Input {}
            class Decoy {}
            static class DeconstructExtensions {
                public static void Deconstruct(this Input input, out int first, out int second) { first = second = 0; }
            }
            static class UnusedExtensions {
                public static void Deconstruct(this Decoy input, out int first, out int second) { first = second = 0; }
            }
            class Root {
                public bool Body(Input input) => input is (0, 0);
            }
            """);
        var (emitter, minter) = Extract(compilation);
        AssertUses(compilation, emitter, minter, "Root", "Body", "Input", "DeconstructExtensions");
        var owner = minter.Member(compilation.GetTypeByMetadataName("Root")!.GetMembers("Body").Single());
        Assert.DoesNotContain(emitter.Triples, triple => triple.Subject == owner
            && triple.Predicate == minter.OntologyPrefix + "usesType"
            && triple.Object == minter.Type(compilation.GetTypeByMetadataName("UnusedExtensions")!));
    }

    [Fact]
    public void InitializerLambdas_IncludeImplicitDisposalUnderTheirFieldOrPropertyOwner()
    {
        var compilation = TestUtilities.CreateCompilation("""
            using System;
            using System.Runtime.CompilerServices;
            using System.Threading.Tasks;
            class Resource { public Awaitable DisposeAsync() => default; }
            struct Awaitable {}
            struct Awaiter : INotifyCompletion {
                public bool IsCompleted => true;
                public void GetResult() {}
                public void OnCompleted(Action action) {}
            }
            static class Extensions { public static Awaiter GetAwaiter(this Awaitable value) => default; }
            class Decoy {}
            class Root {
                public Func<Task> Property { get; } = async () => { await using var value = new Resource(); };
                public Func<Task> Field = async () => { await using var value = new Resource(); };
                public void Other() { _ = new Decoy(); }
            }
            """);
        var (emitter, minter) = Extract(compilation);
        foreach (var member in new[] { "Property", "Field" })
        {
            AssertUses(compilation, emitter, minter, "Root", member, "Resource", "Awaitable", "Awaiter", "Extensions");
            var owner = minter.Member(compilation.GetTypeByMetadataName("Root")!.GetMembers(member).Single());
            Assert.DoesNotContain(emitter.Triples, triple => triple.Subject == owner
                && triple.Predicate == minter.OntologyPrefix + "usesType"
                && triple.Object == minter.Type(compilation.GetTypeByMetadataName("Decoy")!));
        }
    }

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
        var extractor = new AssemblyGraphExtractor(emitter, options);
        extractor.Extract(compilation, compilation.Assembly);
        Assert.Empty(extractor.BodyResolutionDiagnostics);
        return (emitter, new IriMinter(options.BaseUri));
    }

    private static void AssertUses(Compilation compilation, TestEmitter emitter, IriMinter minter,
        string ownerType, string member, params string[] targets)
    {
        var owner = minter.Member(compilation.GetTypeByMetadataName(ownerType)!.GetMembers(member).Single());
        foreach (var target in targets)
        {
            var matches = emitter.Triples.Where(triple => triple.Subject == owner
                && triple.Predicate == minter.OntologyPrefix + "usesType"
                && triple.Object == minter.Type(compilation.GetTypeByMetadataName(target)!)).ToArray();
            Assert.True(matches.Length == 1, $"{ownerType}.{member} -> {target}: expected one usesType, found {matches.Length}");
        }
    }
}
