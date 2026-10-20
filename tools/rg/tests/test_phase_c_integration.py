"""Mandatory producer-to-store integration; fixture code is compiled, never executed."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from roslyn_graph import artifacts, build, config, extractor, oxigraph, plan, traverse
from roslyn_graph.result import ProblemList
from roslyn_graph.util import DT, RG, sha256_file


REPO = Path(__file__).resolve().parents[3]


def checked(args, cwd=None):
    result = subprocess.run([str(arg) for arg in args], cwd=cwd, capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stdout + result.stderr
    return result


@pytest.fixture(scope="session")
def producer():
    assert shutil.which("dotnet"), "Phase C integration requires dotnet on PATH."
    assert shutil.which("oxigraph"), "Phase C integration requires Oxigraph on PATH."
    assert oxigraph.version() == "0.5.8", "Phase C integration requires Oxigraph 0.5.8."
    entry = REPO / "src/RoslynToRdf.Cli/bin/Release/net8.0/RoslynToRdf.Cli.dll"
    assert entry.is_file(), "Build RoslynToRdf.sln in Release before running integration tests."
    return entry


def compile_project(directory, source, language="cs", configuration="Release", references=()):
    directory.mkdir(parents=True, exist_ok=True)
    name = directory.name
    project = directory / f"{name}.{language}proj"
    project.write_text(
        '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><TargetFramework>net8.0</TargetFramework>'
        f"<AssemblyName>{name}</AssemblyName><RootNamespace></RootNamespace>"
        "<AllowUnsafeBlocks>true</AllowUnsafeBlocks><LangVersion>latest</LangVersion>"
        "<GenerateAssemblyInfo>false</GenerateAssemblyInfo></PropertyGroup><ItemGroup>"
        + "".join(f'<ProjectReference Include="{path.as_posix()}" />' for path in references)
        + "</ItemGroup></Project>", encoding="utf-8")
    (directory / f"Fixture.{language}").write_text(source, encoding="utf-8")
    checked(["dotnet", "build", project, "-c", configuration, "--nologo"])
    return project, directory / "bin" / configuration / "net8.0" / f"{name}.dll"


def extract_store(producer, directory, input_path, configuration="Release"):
    directory.mkdir(parents=True, exist_ok=True)
    output = directory / "producer.nt"
    checked(["dotnet", producer, input_path, "--output", output, "--include-private",
             "--include-attributes", "--configuration", configuration, "--quiet"])
    store = directory / "store.oxigraph"
    oxigraph.load(store, output, "urn:phase-c:producer")
    return store


def query(store, pattern, columns="*"):
    return oxigraph.select(store, f"PREFIX dt: <{DT}> SELECT {columns} WHERE {{ GRAPH ?graph {{ {pattern} }} }}")


def names(store):
    return {row["full"]: row["type"] for row in query(
        store, "?assembly a dt:Assembly . ?type dt:definedInAssembly ?assembly ; "
        "dt:accessibility ?access ; dt:fullName ?full .", "?type ?full")}


def reduce(store, root, expected, follow=None, max_depth=0, max_types=None):
    own = names(store)
    definition = SimpleNamespace(
        follow=follow or ["base_types", "interfaces", "member_types", "parameter_types",
                          "constraints", "enclosing_type", "body_types"],
        max_depth=max_depth, max_types=max_types, generic_arguments=True)
    selected, edges, stats, truncated = traverse.expand(store, definition, {own[root]: root})
    assert set(selected.values()) == set(expected)
    assert all(source != target for source, target in edges)
    return selected, edges, stats, truncated


CS = """
namespace Fixture {
public class Arg : Constraint { }
public class Ret { }
public class Constraint { }
public class Box<T> where T : Constraint { }
public delegate Ret D(Arg value);
public class CallableRoot { public System.Func<Arg, Ret> Function; public System.Action<Arg> Action; }
public class GenericRoot { public Box<Arg> Value; }
public class PrivateOnly { }
public class Decoy { }
public class Root { private void NeverCalled() { _ = new PrivateOnly(); } }
public class NameofOnly { }
public class NameofRoot { public string Name() => nameof(NameofOnly); }
public class InitOnly { }
public class InitRoot { private object field = new InitOnly(); public object Value { get; } = new InitOnly(); }
public class SelfRoot { public object Self() => new SelfRoot(); }
public class MarkerAttribute : System.Attribute {}
[Marker] public class AttributeOnly {}
public class MarkerSignature { public MarkerAttribute Value; }
public class MarkerBody { public object Body() => new MarkerAttribute(); }
public class LambdaOnly { }
public class OtherLambdaOnly { }
public class IteratorOnly {}
public class AsyncOnly {}
public class CaptureOnly {}
public class LocalOnly {}
public class SharedOnly {}
public class GeneratedHelpers {
 [System.Runtime.CompilerServices.CompilerGenerated]
 public static object Shared() => new SharedOnly();
}
public class GeneratedRoot {
 public System.Collections.Generic.IEnumerable<object> Iterator() { yield return new IteratorOnly(); }
 public async System.Threading.Tasks.Task Async() { await System.Threading.Tasks.Task.Yield(); _ = new AsyncOnly(); }
 public object Capture() { int value = 1; System.Func<object> thunk = () => value > 0 ? new CaptureOnly() : null; return thunk(); }
 public object Local() { object Nested() => new LocalOnly(); return Nested(); }
 public object ShareOne() => GeneratedHelpers.Shared();
 public object ShareTwo() => GeneratedHelpers.Shared();
}
public class LambdaRoot {
  public void One() { System.Action action = () => { _ = new LambdaOnly(); }; action(); }
  public void Two() { System.Action action = () => { _ = new OtherLambdaOnly(); }; action(); }
}
public struct PointerArg { }
public struct PointerRet { }
public unsafe struct S {
 public PointerArg* Pointer;
 public delegate*<PointerArg, PointerRet> Function;
 public delegate* unmanaged[Cdecl]<ref PointerArg, PointerRet> Unmanaged;
 public delegate* unmanaged[Cdecl, SuppressGCTransition]<PointerArg, PointerRet> Suppressed;
 public delegate*<PointerArg, PointerArg, PointerRet> Repeated;
 public delegate*<delegate*<PointerArg, PointerRet>, PointerRet> Nested;
}
public unsafe class A<T> { public delegate*<T, void> Function; }
public unsafe class B<T> { public delegate*<T, void> Function; }
}
"""

VB = """
Namespace Fixture
Public Class Arg
 Inherits Constraint
End Class
Public Class Ret
End Class
Public Class Constraint
End Class
Public Class Box(Of T As Constraint)
End Class
Public Delegate Function D(value As Arg) As Ret
Public Class CallableRoot
 Public Func As System.Func(Of Arg, Ret)
 Public Action As System.Action(Of Arg)
End Class
Public Class GenericRoot
 Public Value As Box(Of Arg)
End Class
Public Class PrivateOnly
End Class
Public Class Decoy
End Class
Public Class Root
 Private Sub NeverCalled()
  Dim value = New PrivateOnly()
 End Sub
End Class
Public Class NameofOnly
End Class
Public Class NameofRoot
 Public Function Name() As String
  Return NameOf(NameofOnly)
 End Function
End Class
Public Class InitOnly
End Class
Public Class InitRoot
 Private field As Object = New InitOnly()
 Public ReadOnly Property Value As Object = New InitOnly()
End Class
Public Class SelfRoot
 Public Function Self() As Object
  Return New SelfRoot()
 End Function
End Class
Public Class MarkerAttribute
 Inherits System.Attribute
End Class
<Marker> Public Class AttributeOnly
End Class
Public Class MarkerSignature
 Public Value As MarkerAttribute
End Class
Public Class MarkerBody
 Public Function Body() As Object
  Return New MarkerAttribute()
 End Function
End Class
Public Class LambdaOnly
End Class
Public Class OtherLambdaOnly
End Class
Public Class IteratorOnly
End Class
Public Class AsyncOnly
End Class
Public Class CaptureOnly
End Class
Public Class SharedOnly
End Class
Public Class GeneratedHelpers
 <System.Runtime.CompilerServices.CompilerGenerated>
 Public Shared Function SharedBody() As Object
  Return New SharedOnly()
 End Function
End Class
Public Class GeneratedRoot
 Public Function ShareOne() As Object
  Return GeneratedHelpers.SharedBody()
 End Function
 Public Function ShareTwo() As Object
  Return GeneratedHelpers.SharedBody()
 End Function
 Public Iterator Function Iterate() As System.Collections.Generic.IEnumerable(Of Object)
  Yield New IteratorOnly()
 End Function
 Public Async Function AsyncBody() As System.Threading.Tasks.Task
  Await System.Threading.Tasks.Task.Yield()
  Dim value = New AsyncOnly()
 End Function
 Public Function Capture() As Object
  Dim value = 1
  Dim thunk As System.Func(Of Object) = Function() If(value > 0, New CaptureOnly(), Nothing)
  Return thunk()
 End Function
End Class
Public Class LambdaRoot
 Public Sub One()
  Dim action As System.Action = Sub()
    Dim value = New LambdaOnly()
   End Sub
  action()
 End Sub
 Public Sub Two()
  Dim action As System.Action = Sub()
    Dim value = New OtherLambdaOnly()
   End Sub
  action()
 End Sub
End Class
End Namespace
"""


@pytest.fixture(scope="module", params=[("cs", "Debug"), ("cs", "Release"), ("vb", "Debug"), ("vb", "Release")])
def real_stores(request, tmp_path_factory, producer):
    language, configuration = request.param
    directory = tmp_path_factory.mktemp(f"producer-{language}-{configuration}")
    project, assembly = compile_project(directory / "Inventory", CS if language == "cs" else VB, language, configuration)
    source = extract_store(producer, directory / "source", project, configuration)
    if configuration == "Release":
        assembly.with_suffix(".pdb").unlink()
    metadata = extract_store(producer, directory / "metadata", assembly, configuration)
    return language, source, metadata


CS += """
namespace Patterns {
public class Element {}
public class Sequence { public Enumerator GetEnumerator() => null; }
public class Enumerator { public Element Current => null; public bool MoveNext() => false; }
public class LoopRoot { public void Body() { foreach (var item in new Sequence()) {} } }
public class Awaitable {}
public class AwaitResult {}
public class Awaiter : System.Runtime.CompilerServices.INotifyCompletion {
 public bool IsCompleted => true;
 public AwaitResult GetResult() => null;
 public void OnCompleted(System.Action continuation) {}
}
public static class AwaitExtensions { public static Awaiter GetAwaiter(this Awaitable value) => null; }
public class AwaitRoot { public async System.Threading.Tasks.Task Body() { var value = await new Awaitable(); } }
public class Decoy { public Decoy GetEnumerator() => this; public Decoy GetAwaiter() => this; }
public ref struct Resource { public void Dispose() {} }
public class UsingRoot { public void Body() { using var resource = new Resource(); } }
public class AsyncResource { public DisposeAwaitable DisposeAsync() => default; }
public struct DisposeAwaitable { public DisposeAwaiter GetAwaiter() => default; }
public struct DisposeAwaiter : System.Runtime.CompilerServices.INotifyCompletion {
 public bool IsCompleted => true; public void GetResult() {} public void OnCompleted(System.Action continuation) {}
}
public class AsyncUsingRoot { public async System.Threading.Tasks.Task Body() { await using var resource = new AsyncResource(); } }
public class AsyncSequence { public AsyncEnumerator GetAsyncEnumerator(System.Threading.CancellationToken token = default) => null; }
public class AsyncEnumerator {
 public object Current => null;
 public MoveAwaitable MoveNextAsync() => default;
 public DisposeAwaitable DisposeAsync() => default;
}
public struct MoveAwaitable { public MoveAwaiter GetAwaiter() => default; }
public struct MoveAwaiter : System.Runtime.CompilerServices.INotifyCompletion {
 public bool IsCompleted => true; public bool GetResult() => false; public void OnCompleted(System.Action continuation) {}
}
public class AsyncLoopRoot { public async System.Threading.Tasks.Task Body() { await foreach (var item in new AsyncSequence()) {} } }
}
"""

VB += """
Namespace Patterns
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
Public Class LoopRoot
 Public Sub Body()
  For Each item In New Sequence()
  Next
 End Sub
End Class
Public Class Awaitable
End Class
Public Class AwaitResult
End Class
Public Class Awaiter
 Implements System.Runtime.CompilerServices.INotifyCompletion
 Public ReadOnly Property IsCompleted As Boolean
  Get
   Return True
  End Get
 End Property
 Public Function GetResult() As AwaitResult
  Return Nothing
 End Function
 Public Sub OnCompleted(continuation As System.Action) Implements System.Runtime.CompilerServices.INotifyCompletion.OnCompleted
 End Sub
End Class
Public Module AwaitExtensions
 <System.Runtime.CompilerServices.Extension>
 Public Function GetAwaiter(value As Awaitable) As Awaiter
  Return Nothing
 End Function
End Module
Public Class AwaitRoot
 Public Async Function Body() As System.Threading.Tasks.Task
  Dim value = Await New Awaitable()
 End Function
End Class
Public Class Decoy
End Class
End Namespace
"""


def test_real_compiler_selected_pattern_relationships(real_stores):
    language, source, metadata = real_stores
    cases = {
        "LoopRoot": {"LoopRoot", "Sequence", "Enumerator", "Element"},
        "AwaitRoot": {"AwaitRoot", "Awaitable", "AwaitExtensions", "Awaiter", "AwaitResult"},
    }
    if language == "cs":
        cases.update({
            "UsingRoot": {"UsingRoot", "Resource"},
            "AsyncUsingRoot": {"AsyncUsingRoot", "AsyncResource", "DisposeAwaitable", "DisposeAwaiter"},
            "AsyncLoopRoot": {"AsyncLoopRoot", "AsyncSequence", "AsyncEnumerator", "MoveAwaitable", "MoveAwaiter",
                              "DisposeAwaitable", "DisposeAwaiter"},
        })
    for store in (source, metadata):
        for root, expected in cases.items():
            generated = set()
            if store == metadata and root in {"AwaitRoot", "AsyncUsingRoot", "AsyncLoopRoot"}:
                generated = {f"Patterns.{root}.<Body>d__0"} if language == "cs" else {
                    f"Patterns.{root}.VB$StateMachine_1_Body"}
            reduce(store, f"Patterns.{root}", {f"Patterns.{name}" for name in expected} | generated)
            targets = {row["name"] for row in query(
                store, f'?root dt:fullName "Patterns.{root}" ; dt:hasMember ?owner . '
                '?owner dt:name "Body" ; dt:usesType ?target . ?target dt:fullName ?name .', "?name")}
            assert {f"Patterns.{name}" for name in expected - {root}} <= targets
            assert "Patterns.Decoy" not in targets


def test_real_delegate_generic_private_and_unsafe_closure(real_stores):
    language, source, metadata = real_stores
    for store in (source, metadata):
        reduce(store, "Fixture.D", {"Fixture.D", "Fixture.Arg", "Fixture.Ret", "Fixture.Constraint"})
        reduce(store, "Fixture.CallableRoot", {"Fixture.CallableRoot", "Fixture.Arg", "Fixture.Ret", "Fixture.Constraint"})
        assert query(store, '?delegate dt:fullName "Fixture.D" ; dt:hasMember ?invoke . '
                     '?invoke dt:name "Invoke" ; dt:returnType ?return ; dt:hasParameter ?parameter . '
                     '?return dt:fullName "Fixture.Ret" . ?parameter dt:ordinal 0 ; dt:parameterType ?arg . '
                     '?arg dt:fullName "Fixture.Arg" .')
        generic = "Fixture.Box<T>" if language == "cs" else "Fixture.Box(Of T)"
        if store == metadata:
            generic = "Fixture.Box<T>"
        reduce(store, "Fixture.GenericRoot", {"Fixture.GenericRoot", generic, "Fixture.Arg", "Fixture.Constraint"})
        selected, edges, _, truncated = reduce(store, "Fixture.Root", {"Fixture.Root", "Fixture.PrivateOnly"})
        assert not truncated
        rows = query(store, '?type dt:fullName "Fixture.Root" ; dt:hasMember ?owner . '
                     '?owner dt:name "NeverCalled" ; dt:usesType ?target . '
                     '?target dt:fullName "Fixture.PrivateOnly" .', "?owner ?target")
        assert len(rows) == 1
        exported = set(traverse.member_lines(store, sorted(selected)))
        assert f'<{rows[0]["owner"]}> <{DT}usesType> <{rows[0]["target"]}> .' in exported
        if language == "cs":
            reduce(store, "Fixture.S", {"Fixture.S", "Fixture.PointerArg", "Fixture.PointerRet"})
            assert query(store, '?fp dt:signatureParameter ?parameter . ?parameter dt:ordinal 0 ; '
                         'dt:parameterType ?arg . ?arg dt:fullName "Fixture.PointerArg" .')
            conventions = query(store, '?type dt:fullName "Fixture.S" ; dt:hasMember ?field . '
                                '?field dt:name "Unmanaged" ; dt:fieldType ?fp . '
                                '?fp dt:callingConvention ?convention ; dt:signatureParameter ?parameter . '
                                '?parameter dt:ordinal 0 ; dt:refKind ?refKind .', "?convention ?refKind")
            assert conventions == [{"convention": "CDecl", "refKind": "Ref"}]
            convention_types = query(store, '?type dt:fullName "Fixture.S" ; dt:hasMember ?field . '
                                     '?field dt:name "Suppressed" ; dt:fieldType ?fp . '
                                     '?fp dt:callingConventionType ?convention . ?convention dt:fullName ?name .', "?name")
            assert {row["name"] for row in convention_types} == {
                "System.Runtime.CompilerServices.CallConvCdecl",
                "System.Runtime.CompilerServices.CallConvSuppressGCTransition"}
            repeated = query(store, '?type dt:fullName "Fixture.S" ; dt:hasMember ?field . '
                             '?field dt:name "Repeated" ; dt:fieldType ?fp . '
                             '?fp dt:signatureParameter ?parameter . ?parameter dt:ordinal ?ordinal ; '
                             'dt:parameterType ?target . ?target dt:fullName "Fixture.PointerArg" .',
                             "?parameter ?ordinal")
            assert {row["ordinal"] for row in repeated} == {"0", "1"}
            assert len({row["parameter"] for row in repeated}) == 2
            nested = query(store, '?type dt:fullName "Fixture.S" ; dt:hasMember ?field . '
                           '?field dt:name "Nested" ; dt:fieldType ?outer . '
                           '?outer dt:signatureParameter ?outerParameter ; dt:signatureReturnType ?ret . '
                           '?outerParameter dt:ordinal 0 ; dt:parameterType ?inner . '
                           '?inner dt:signatureParameter ?innerParameter ; dt:signatureReturnType ?ret . '
                           '?innerParameter dt:ordinal 0 ; dt:parameterType ?arg . '
                           '?arg dt:fullName "Fixture.PointerArg" . ?ret dt:fullName "Fixture.PointerRet" .',
                           "?outer ?outerParameter ?inner ?innerParameter")
            assert len(nested) == 1
            assert nested[0]["outer"] != nested[0]["inner"]
            assert nested[0]["outerParameter"] != nested[0]["innerParameter"]
            owners = query(store, '?type dt:fullName ?full ; dt:hasMember ?field . '
                           'FILTER(?full IN ("Fixture.A<T>", "Fixture.B<T>")) '
                           '?field dt:name "Function" ; dt:fieldType ?fp . '
                           '?fp dt:signatureParameter ?parameter . ?parameter dt:parameterType ?target .',
                           "?full ?fp ?target")
            assert len(owners) == 2
            assert len({row["fp"] for row in owners}) == 2
            assert len({row["target"] for row in owners}) == 2


def test_real_erasure_initializers_generated_ownership_and_self_use(real_stores):
    language, source, metadata = real_stores
    for store in (source, metadata):
        reduce(store, "Fixture.InitRoot", {"Fixture.InitRoot", "Fixture.InitOnly"})
        initializer_owners = {row["name"] for row in query(
            store, '?root dt:fullName "Fixture.InitRoot" ; dt:hasMember ?owner . '
            '?owner dt:name ?name ; dt:usesType ?target . ?target dt:fullName "Fixture.InitOnly" .', "?name")}
        assert initializer_owners == ({"field", "Value"} if store == source else {".ctor"})
        selected, edges, _, _ = reduce(store, "Fixture.SelfRoot", {"Fixture.SelfRoot"})
        self_iri = next(iter(selected))
        assert query(store, f"<{self_iri}> dt:hasMember ?member . ?member dt:usesType <{self_iri}> .")
        assert not edges
        for owner, target, decoy in (("One", "LambdaOnly", "OtherLambdaOnly"), ("Two", "OtherLambdaOnly", "LambdaOnly")):
            rows = query(store, f'?root dt:fullName "Fixture.LambdaRoot" ; dt:hasMember ?owner . '
                         f'?owner dt:name "{owner}" ; dt:usesType ?target . ?target dt:fullName ?name .', "?name")
            values = {row["name"] for row in rows}
            assert f"Fixture.{target}" in values
            assert f"Fixture.{decoy}" not in values
        owners = {"Iterator" if language == "cs" else "Iterate": "IteratorOnly",
                  "Async" if language == "cs" else "AsyncBody": "AsyncOnly",
                  "Capture": "CaptureOnly"}
        if language == "cs":
            owners["Local"] = "LocalOnly"
        for owner, target in owners.items():
            values = {row["name"] for row in query(
                store, '?root dt:fullName "Fixture.GeneratedRoot" ; dt:hasMember ?owner . '
                f'?owner dt:name "{owner}" ; dt:usesType ?target . ?target dt:fullName ?name .', "?name")}
            assert f"Fixture.{target}" in values
            assert {name for name in values if name in {f"Fixture.{value}" for value in owners.values()}} == {
                f"Fixture.{target}"}
        for owner in ("ShareOne", "ShareTwo"):
            shared = query(store, '?root dt:fullName "Fixture.GeneratedRoot" ; dt:hasMember ?owner . '
                           f'?owner dt:name "{owner}" ; dt:usesType ?target . ?target dt:fullName "Fixture.SharedOnly" .')
            assert bool(shared) == (store == metadata)
    reduce(source, "Fixture.NameofRoot", {"Fixture.NameofRoot", "Fixture.NameofOnly"})
    reduce(metadata, "Fixture.NameofRoot", {"Fixture.NameofRoot"})


def test_real_attribute_inverse_is_opt_in(real_stores):
    _, source, metadata = real_stores
    ordinary = {"Fixture.MarkerAttribute", "Fixture.MarkerSignature", "Fixture.MarkerBody"}
    for store in (source, metadata):
        reduce(store, "Fixture.MarkerAttribute", ordinary, follow=["referenced_by"])
        reduce(store, "Fixture.MarkerAttribute", ordinary | {"Fixture.AttributeOnly"},
               follow=["referenced_by", "attributes"])


def test_real_producer_body_chain_exceeds_1500_without_limits(tmp_path, producer):
    count = 1503
    declarations = [
        f"public class T{index} {{ private object NeverCalled() => new T{(index + 1) % count}(); }}"
        for index in range(count)
    ]
    _, assembly = compile_project(tmp_path / "Large", "namespace Chain {" + "\n".join(declarations) + "}")
    store = extract_store(producer, tmp_path / "graph", assembly)
    expected = {f"Chain.T{index}" for index in range(count)}
    selected, edges, _, truncated = reduce(store, "Chain.T0", expected)
    assert not truncated and len(selected) == count and len(edges) == count
    exported = traverse.member_lines(store, sorted(selected))
    assert sum(f"<{DT}usesType>" in line and "/Chain.T" in line for line in exported) >= count
    _, _, _, truncated = reduce(store, "Chain.T0", {"Chain.T0", "Chain.T1"}, max_depth=1)
    assert truncated


@pytest.fixture(scope="module")
def libraries(tmp_path_factory, producer):
    return build_libraries(tmp_path_factory.mktemp("libraries"), producer, full_inventory=True)


@pytest.fixture(scope="module")
def dependency_libraries(tmp_path_factory, producer):
    return build_libraries(tmp_path_factory.mktemp("dependencies"), producer, full_inventory=False)


def build_libraries(directory, producer, full_inventory):
    q_project, q_dll = compile_project(directory / "Q", """
namespace Q { public class Leaf { } public class Decoy { } }
""")
    p_project, p_dll = compile_project(directory / "P", """
namespace P { public class Entry { private object NeverCalled() => new Q.Leaf(); }
public class Decoy { } }
""", references=[q_project])
    a_project, a_dll = compile_project(directory / "A", """
namespace A {
internal class Hidden { }
public class PrivateOnly { }
public class Root {
 private class PrivateNested { }
 static Root() { }
 public Root() { }
 public object Run() => new P.Entry();
 private object NeverCalled() => new PrivateOnly();
 public object Value { get => new PrivateOnly(); set { } }
 public object State;
 public event System.Action Changed { add { _ = new PrivateOnly(); } remove { } }
}}
""" if full_inventory else """
namespace A { public class Root { public object Run() => new P.Entry(); } }
""", references=[p_project])
    workspace_path = directory / "workspace.toml"
    workspace_path.write_text("""
schema_version = 1
[tools]
oxigraph = "0.5.8"
[profiles.app]
root = "."
solution = "Fixture.sln"
output_dir = "A/bin/Release/net8.0"
[profiles.app.build]
configuration = "Release"
target_framework = "net8.0"
[profiles.app.collect]
all_solution_projects = true
packages = ["p", "q"]
[profiles.p]
kind = "nuget"
package = "Fixture.P"
source = "https://example.invalid/v3/index.json"
version = "1.0.0"
target_framework = "net8.0"
[profiles.q]
kind = "nuget"
package = "Fixture.Q"
source = "https://example.invalid/v3/index.json"
version = "1.0.0"
target_framework = "net8.0"
[policies.all]
assemblies = ["A", "P", "Q"]
[collections.fixture]
base = "app"
logical_type_policy = "all"
""", encoding="utf-8")
    workspace = config.load(workspace_path)
    root = directory / ".roslyn-graph"
    tool = extractor.Extractor(producer, sha256_file(producer), "net8.0", sha256_file(producer), "integration fixture")
    graph_plan = plan.Plan(workspace, workspace.collections["fixture"], root, tool, "0.5.8")
    for name, project, dll in (("A", a_project, a_dll), ("P", p_project, p_dll), ("Q", q_project, q_dll)):
        manifest = {
            "origin": {"kind": "source", "id": "fixture", "commit": "a" * 40, "dirtyHash": ""},
            "build": {"fingerprint": f"fixture-{name}", "project": f"{name}/{name}.csproj", "targetFramework": "net8.0"},
            "assembly": {"sha256": sha256_file(dll), "expectedName": name},
            "extraction": {"extractorId": tool.id},
        }
        if name == "A":
            manifest["extraction"]["inputKind"] = "source-project"
        artifact_id = artifacts.artifact_id(artifacts.assembly_identity(manifest))
        component = plan.Component(
            "app" if name == "A" else name.lower(), "base", dll, name, [dll.parent], manifest,
            extraction_path=project if name == "A" else None,
            artifact_id=artifact_id, destination=root / "assemblies" / artifact_id[:20])
        graph_plan.components.append(component)
        build.snapshot(graph_plan, component)
    solution_fields = {
        "profile": "app", "name": "Fixture", "repository": "fixture", "relativePath": "Fixture.sln",
        "path": str(directory / "Fixture.sln"), "commit": "a" * 40, "dirtyHash": "", "fingerprint": "fixture",
        "targetFramework": "net8.0", "configuration": "Release", "platform": "",
    }
    for label, components in (("composed", graph_plan.components), ("single", graph_plan.components[:1])):
        current = plan.Plan(workspace, graph_plan.collection, root, tool, "0.5.8", list(components))
        manifest = {"solution": solution_fields, "components": [{"artifactId": component.artifact_id} for component in components]}
        artifact_id = artifacts.artifact_id(artifacts.solution_identity(manifest))
        current.solution = {"artifactId": artifact_id, "destination": f"solutions/{artifact_id[:20]}",
                            "exists": False, "manifest": manifest}
        build.compose(current)
        plan._plan_view(current, ProblemList())
        build.build_view(current)
        setattr(graph_plan, label, current)
    return directory, graph_plan


def graph_definition(directory, manifest, seeds, logical=False):
    path = directory / "inventory.graph.toml"
    path.write_text(
        'schema_version = 1\n[source]\n'
        f"manifest = {json.dumps(str(manifest))}\nlogical = {str(logical).lower()}\n"
        '[seeds]\nimplementations = "none"\n'
        f"types = {json.dumps(seeds)}\n", encoding="utf-8")
    return path


def test_full_library_inventory_preserves_body_and_composed_facts(libraries):
    directory, graph_plan = libraries
    current = graph_plan.composed
    manifest = graph_plan.root / current.solution["destination"] / "manifest.json"
    store = manifest.parent / "store.oxigraph"
    rows = query(store, '?assembly a dt:Assembly ; dt:name "A" . '
                 '?type dt:definedInAssembly ?assembly ; dt:accessibility ?access ; dt:fullName ?full .', "?type ?full")
    expected = {"A.Root", "A.Root.PrivateNested", "A.Hidden", "A.PrivateOnly"}
    assert {row["full"] for row in rows} == expected
    definition = graph_definition(directory, manifest, sorted(expected))
    result = traverse.run(definition, str(directory), directory / "whole", False)
    assert result["types"] == 6 and not result["truncated"]
    memberships = query(store, '?type dt:fullName "A.Root" ; dt:hasMember ?member . ?member dt:name ?name .', "?name")
    assert {".ctor", ".cctor", "Run", "NeverCalled", "Value", "State", "Changed"} <= {row["name"] for row in memberships}
    reduce(store, "A.Root", {"A.Root", "A.PrivateOnly", "P.Entry", "Q.Leaf"})
    exported = Path(result["data"]).read_text(encoding="utf-8")
    for owner in ("NeverCalled", "Value", "Changed"):
        rows = query(store, '?type dt:fullName "A.Root" ; dt:hasMember ?owner . '
                     f'?owner dt:name "{owner}" ; dt:usesType ?target . ?target dt:fullName "A.PrivateOnly" .',
                     "?owner ?target")
        assert len(rows) == 1
        assert f'<{rows[0]["owner"]}> <{DT}usesType> <{rows[0]["target"]}> .' in exported


@pytest.mark.parametrize("separate", [False, True])
@pytest.mark.parametrize("logical", [False, True])
def test_composed_analyzed_dependency_closure(dependency_libraries, separate, logical):
    directory, graph_plan = dependency_libraries
    current = graph_plan.single if separate else graph_plan.composed
    source = current.view if logical else current.solution
    manifest = graph_plan.root / source["destination"] / "manifest.json"
    definition = graph_definition(directory, manifest, ["A.Root"], logical)
    result = traverse.run(definition, str(directory), directory / f"closure-{separate}-{logical}", False)
    assert result["types"] == 3 and not result["truncated"]
    output = Path(result["data"]).read_text(encoding="utf-8")
    for full in ("A.Root", "P.Entry", "Q.Leaf"):
        assert f'<{DT}fullName> "{full}"' in output
    assert f'<{DT}fullName> "P.Decoy"' not in output
    assert f'<{DT}fullName> "Q.Decoy"' not in output
    if logical:
        for assembly, full in (("A", "A.Root"), ("P", "P.Entry"), ("Q", "Q.Leaf")):
            assert build.logical_iri(assembly, full) in output


@pytest.fixture(scope="module")
def records_dependency_library(tmp_path_factory, dependency_libraries):
    directory, graph_plan = dependency_libraries
    fresh = tmp_path_factory.mktemp("records-dependencies")
    external_project, _ = compile_project(fresh / "E", """
namespace E { public class External { public object Unused() => new Decoy(); } public class Decoy {} }
""")
    project, assembly = compile_project(fresh / "A", """
namespace A { public unsafe class Root {
 public object Run() => new P.Entry();
 private object NeverCalled() => new E.External();
 public System.Collections.Generic.List<P.Entry> Generic;
 public P.Entry[] Array;
 public delegate*<P.Entry, void> Callback;
} }
""", references=[directory / "P" / "P.csproj", external_project])
    component_manifest = {
        "origin": {"kind": "source", "id": "fixture", "commit": "a" * 40, "dirtyHash": ""},
        "build": {"fingerprint": "records-fixture", "project": "A/A.csproj", "targetFramework": "net8.0"},
        "assembly": {"sha256": sha256_file(assembly), "expectedName": "A"},
        "extraction": {"extractorId": graph_plan.extractor.id, "inputKind": "source-project"},
    }
    artifact_id = artifacts.artifact_id(artifacts.assembly_identity(component_manifest))
    component = plan.Component(
        "app", "base", assembly, "A", [assembly.parent], component_manifest,
        extraction_path=project, artifact_id=artifact_id,
        destination=graph_plan.root / "assemblies" / artifact_id[:20])
    current = plan.Plan(graph_plan.workspace, graph_plan.collection, graph_plan.root,
                        graph_plan.extractor, "0.5.8", [component])
    build.snapshot(current, component)
    solution_manifest = {
        "solution": dict(graph_plan.single.solution["manifest"]["solution"], fingerprint="records-fixture"),
        "components": [{"artifactId": component.artifact_id}],
    }
    solution_id = artifacts.artifact_id(artifacts.solution_identity(solution_manifest))
    current.solution = {"artifactId": solution_id, "destination": f"solutions/{solution_id[:20]}",
                        "exists": False, "manifest": solution_manifest}
    build.compose(current)
    plan._plan_view(current, ProblemList())
    build.build_view(current)
    return directory, fresh, graph_plan, current


@pytest.mark.parametrize("logical", [False, True])
def test_records_cli_reopens_real_dependency_pins_and_external_evidence(records_dependency_library, logical):
    import sys

    directory, fresh, graph_plan, current = records_dependency_library
    source = current.view if logical else current.solution
    manifest = graph_plan.root / source["destination"] / "manifest.json"
    definition = graph_definition(fresh, manifest, ["A.Root"], logical)
    output_dir = fresh / f"records-{logical}"
    result = traverse.run(definition, str(directory), output_dir, False)
    assert result["types"] == 3 and not result["truncated"]
    graph = Path(result["data"])
    context = json.loads(graph.with_suffix(".context.json").read_text(encoding="utf-8"))
    pins = context["additionalComponents"]
    assert {pin["assembly"]["name"] for pin in pins} == {"P", "Q"}
    assert {pin["artifactId"] for pin in pins} == {
        component.artifact_id for component in graph_plan.components if component.expected_name in {"P", "Q"}}
    data = graph.read_text(encoding="utf-8")
    external_rows = query(manifest.parent / "store.oxigraph",
                          '?root dt:fullName "A.Root" ; dt:hasMember ?owner . '
                          '?owner dt:name "NeverCalled" ; dt:usesType ?target . '
                          '?target dt:fullName "E.External" ; dt:definedInAssembly ?assembly .',
                          "?root ?owner ?target ?assembly")
    assert len(external_rows) == 1
    external = external_rows[0]
    owner = external["owner"].replace(external["root"], build.logical_iri("A", "A.Root"), 1) if logical else external["owner"]
    assert f'<{owner}> <{DT}usesType> <{external["target"]}> .' in data
    assert f'<{external["target"]}> <{DT}definedInAssembly> <{external["assembly"]}> .' in data
    assert f'<{DT}fullName> "E.Decoy"' not in data
    for predicate in ("genericDefinition", "typeArgument", "arrayElementType", "signatureParameter"):
        assert f"<{DT}{predicate}>" in data
    wrappers = query(manifest.parent / "store.oxigraph",
                     '?root dt:fullName "A.Root" ; dt:hasMember ?field . '
                     '?field dt:name "Generic" ; dt:fieldType ?wrapper . '
                     '?wrapper dt:genericDefinition ?definition .', "?wrapper")
    assert len(wrappers) == 1
    assert any(entry["target"] == wrappers[0]["wrapper"] for entry in context["externalReferences"])
    evidence = [entry for entry in context["externalReferences"] if entry["target"] == external["target"]]
    assert evidence == [{"owner": owner, "predicate": DT + "usesType", "target": external["target"],
                         "assembly": external["assembly"], "reason": "external-boundary"}]
    for component in graph_plan.components:
        if component.expected_name != "P":
            continue
        rows = oxigraph.select(component.destination / "store.oxigraph",
                                f'PREFIX dt: <{DT}> SELECT ?type ?owner ?target WHERE {{ '
                                '?type dt:fullName "P.Entry" ; dt:hasMember ?owner . '
                                '?owner dt:name "NeverCalled" ; dt:usesType ?target . '
                                '?target dt:fullName "Q.Leaf" . }')
        assert len(rows) == 1
        target = build.logical_iri("Q", "Q.Leaf") if logical else rows[0]["target"]
        owner = rows[0]["owner"].replace(rows[0]["type"], build.logical_iri("P", "P.Entry"), 1) if logical else rows[0]["owner"]
        assert f'<{owner}> <{DT}usesType> <{target}> .' in data
    schema = output_dir / "records.schema.json"
    schema.write_text(json.dumps({"type": "object", "properties": {
        "iri": {"type": "string", "x-rg-field": "iri"},
        "name": {"type": "string", "x-rg-field": "fullName"},
        "assemblies": {"type": "array", "x-rg-field": "assemblies"},
        "projects": {"type": "array", "x-rg-field": "projects"},
        "origin": {"type": "string", "x-rg-field": "origin"},
    }}), encoding="utf-8")
    output = output_dir / "records.jsonl"
    command = [sys.executable, REPO / "tools/rg/rg.py", "records", "--graph", graph,
               "--schema", schema, "--output", output]
    checked(command)
    before = output.read_bytes()
    records = [json.loads(line) for line in before.decode("utf-8").splitlines()]
    assert [record["name"] for record in records] == ["A.Root", "P.Entry", "Q.Leaf"]
    for record in records:
        name = record["name"].split(".")[0]
        assert record["assemblies"] == [name]
        assert record["projects"] == [f"{name}/{name}.csproj"]
        assert record["origin"] == "source"
        if logical:
            assert record["iri"] == build.logical_iri(name, record["name"])
        else:
            assert not record["iri"].startswith("urn:roslyn-graph:logical-type:")
    changed = graph_plan.root / "assemblies" / f"later-catalog-{logical}"
    changed.mkdir()
    (changed / "manifest.json").write_text("{", encoding="utf-8")
    checked(command)
    assert output.read_bytes() == before
    provenance = json.loads(output.with_suffix(".context.json").read_text(encoding="utf-8"))
    assert provenance["input"]["context"]["additionalComponents"] == pins
    assert provenance["input"]["context"]["externalReferences"] == context["externalReferences"]
    assert provenance["input"]["context"]["logicalTypeMappings"] == context["logicalTypeMappings"]
