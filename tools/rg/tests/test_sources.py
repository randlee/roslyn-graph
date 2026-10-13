"""sources: names, MSBuild arguments, symbols, checkout drift, the index cache, locate, and a real MSBuild + Roslyn run."""

import json
import shutil
from pathlib import Path

import pytest

from conftest import REPO
from roslyn_graph import extractor, gitinfo, records, sources
from roslyn_graph.extractor import Extractor
from roslyn_graph.result import RgError
from roslyn_graph.util import Completed


def codes(exc: pytest.ExceptionInfo) -> list[str]:
    return [p.code for p in exc.value.problems]


def project(repository: Path, relative="src/A/A.csproj", commit="", dirty_hash="", build=None, solution=None) -> sources.Project:
    return sources.Project("urn:g", "A", repository, str(repository), commit, dirty_hash, relative, build or {}, solution)


@pytest.fixture
def fake_extractor(monkeypatch):
    monkeypatch.setattr(sources.extractor, "resolve", lambda: Extractor(Path("RoslynToRdf.Cli.dll"), "ext", "rt", "h", "test"))


@pytest.fixture(autouse=True)
def fresh_repo_state():
    gitinfo.repo_state.cache_clear()
    yield
    gitinfo.repo_state.cache_clear()


# ---- names ----------------------------------------------------------------------------------


@pytest.mark.parametrize("full, parts, generated, owner", [
    ("A.B.C", ["A", "B", "C"], False, "A.B.C"),
    ("A.Map<K, V.W>.Item", ["A", "Map<K, V.W>", "Item"], False, "A.Map<K, V.W>.Item"),
    ("A.C.<M>d__3", ["A", "C", "<M>d__3"], True, "A.C"),
    ("A.C.<>c__DisplayClass1_0.<>c", ["A", "C", "<>c__DisplayClass1_0", "<>c"], True, "A.C"),
    ("<PrivateImplementationDetails>", ["<PrivateImplementationDetails>"], True, ""),
])
def test_names(full, parts, generated, owner):
    assert sources.segments(full) == parts
    assert sources.compiler_generated(full) is generated
    assert sources.source_owner(full) == owner


# ---- MSBuild --------------------------------------------------------------------------------


def test_msbuild_command(monkeypatch):
    monkeypatch.delenv("ROSLYN_GRAPH_MSBUILD", raising=False)
    assert sources.msbuild_command() == ["dotnet", "msbuild"]
    monkeypatch.setenv("ROSLYN_GRAPH_MSBUILD", "C:/sdk/dotnet.exe")
    assert sources.msbuild_command() == ["C:/sdk/dotnet.exe", "msbuild"]
    monkeypatch.setenv("ROSLYN_GRAPH_MSBUILD", "C:/VS/MSBuild.exe")
    assert sources.msbuild_command() == ["C:/VS/MSBuild.exe"]


def test_msbuild_args_carry_the_build_and_the_solution_context(tmp_path, monkeypatch):
    monkeypatch.delenv("ROSLYN_GRAPH_MSBUILD", raising=False)
    solution = tmp_path / "All.sln"
    p = project(tmp_path, build={"configuration": "Release", "targetFramework": "net48", "platform": "x64"}, solution=solution)
    args = sources.msbuild_args(p)
    assert args[:4] == ["dotnet", "msbuild", str(tmp_path / "src/A/A.csproj"), "-nologo"]
    assert "-getItem:Compile" in args and "-getProperty:FinalDefineConstants" in args and "-t:AddImplicitDefineConstants" in args
    assert {"-p:Configuration=Release", "-p:TargetFramework=net48", "-p:Platform=x64", f"-p:SolutionPath={solution}",
            "-p:SolutionName=All", "-p:SolutionFileName=All.sln", "-p:SolutionExt=.sln"} <= set(args)
    assert any(a.startswith("-p:SolutionDir=") and a.endswith(("/", "\\")) for a in args)
    assert not any(a.startswith(("-p:Platform", "-p:Solution")) for a in sources.msbuild_args(project(tmp_path)))


def completed(code, stdout="", stderr=""):
    return Completed([], code, stdout, stderr)


def test_evaluate_retries_without_the_sdk_target_and_reports_failures(tmp_path, monkeypatch):
    calls = []
    document = {"Properties": {"DefineConstants": "A;B", "Language": "C#"},
                "Items": {"Compile": [{"Identity": "x.cs", "FullPath": str(tmp_path / "x.cs")}, {"Identity": "y.cs"}]}}
    replies = [completed(1, "error MSB4057: The target \"AddImplicitDefineConstants\" does not exist"), completed(0, "noise\n" + json.dumps(document))]
    monkeypatch.setattr(sources, "run", lambda args, cwd=None, timeout=None: calls.append(args) or replies.pop(0))
    p = project(tmp_path)
    items, properties = sources.evaluate(p)
    assert "-t:AddImplicitDefineConstants" in calls[0] and "-t:AddImplicitDefineConstants" not in calls[1]
    assert items == [tmp_path / "x.cs", tmp_path / "src/A/y.cs"] and properties["DefineConstants"] == "A;B"

    monkeypatch.setattr(sources, "run", lambda args, cwd=None, timeout=None: completed(1, "error MSB4019: imported project not found"))
    with pytest.raises(RgError) as info:
        sources.evaluate(p)
    assert codes(info) == ["MSBUILD_FAILED"] and "MSB4019" in info.value.problems[0].context["output"][-1]


def test_language_and_symbols(tmp_path):
    assert sources.language_of(project(tmp_path, "a.vbproj"), {}) == "VB"
    assert sources.language_of(project(tmp_path), {"Language": "VB"}) == "VB"
    assert sources.language_of(project(tmp_path), {}) == "C#"
    assert sources.symbols_of("C#", {"DefineConstants": " TRACE;DEBUG;;NET8_0,TRACE "}) == ["DEBUG", "NET8_0", "TRACE"]
    vb = {"DefineConstants": "X", "FinalDefineConstants": 'CONFIG="Debug, x64",DEBUG=-1,TRACE=-1,_MyType="Windows";TT3'}
    assert sources.symbols_of("VB", vb) == ['CONFIG="Debug, x64"', "DEBUG=-1", "TRACE=-1", '_MyType="Windows"', "TT3"]
    assert sources.symbols_of("VB", {"DefineConstants": "X=1"}) == ["X=1"]


# ---- declarations ---------------------------------------------------------------------------


@pytest.mark.parametrize("text, code", [
    ("Unrecognized command or argument 'declarations'.", "DECLARATIONS_UNSUPPORTED"),
    ("Error: request is not valid JSON", "DECLARATIONS_FAILED"),
])
def test_declarations_errors(monkeypatch, fake_extractor, text, code):
    monkeypatch.setattr(sources, "run", lambda args: completed(1, "", text))
    with pytest.raises(RgError) as info:
        sources.declarations({"language": "C#", "files": []})
    assert codes(info) == [code]


# ---- checkouts ------------------------------------------------------------------------------


def head(repo) -> str:
    return gitinfo.repo_state(repo).commit


def test_checkout_matching_moved_dirty_and_missing(git_repo, tmp_path):
    commit = head(git_repo)
    p = project(git_repo, commit=commit)
    sources.check_checkout(p)
    assert p.drift is None

    (git_repo / "new.txt").write_text("x")
    git_repo.git("add", ".")
    git_repo.git("commit", "-q", "-m", "next")
    gitinfo.repo_state.cache_clear()
    p = project(git_repo, commit=commit)
    sources.check_checkout(p)
    assert p.drift.startswith("checkout is at") and commit[:12] in p.drift

    (git_repo / "new.txt").write_text("changed")
    gitinfo.repo_state.cache_clear()
    p = project(git_repo, commit=head(git_repo))
    sources.check_checkout(p)
    assert p.drift == "the checkout has uncommitted changes"
    p = project(git_repo, commit=head(git_repo), dirty_hash=gitinfo.repo_state(git_repo).dirty_hash)
    sources.check_checkout(p)
    assert p.drift is None  # the store was built from exactly this dirty state

    with pytest.raises(RgError) as info:
        sources.check_checkout(project(tmp_path / "gone"))
    assert codes(info) == ["SOURCE_CHECKOUT_MISSING"]


def test_index_all_refuses_drift_unless_allowed_and_needs_the_project(git_repo, monkeypatch, fake_extractor):
    monkeypatch.setattr(sources, "index_project", lambda p, cache: None)
    (git_repo / "src" / "A").mkdir(parents=True)
    (git_repo / "src" / "A" / "A.csproj").write_text("<Project />")
    git_repo.git("add", ".")
    git_repo.git("commit", "-q", "-m", "project")
    with pytest.raises(RgError) as info:
        sources.index_all([project(git_repo, commit="0" * 40)], None, allow_drift=False)
    assert codes(info) == ["SOURCE_CHECKOUT_DRIFT"] and info.value.problems[0].context["drift"][0]["repository"] == "A"
    warnings = sources.index_all([project(git_repo, commit="0" * 40)], None, allow_drift=True)
    assert [w["code"] for w in warnings] == ["SOURCE_CHECKOUT_DRIFT"]
    assert sources.index_all([project(git_repo, commit=head(git_repo))], None, allow_drift=False) == []
    with pytest.raises(RgError) as info:
        sources.index_all([project(git_repo, "src/B/B.csproj", commit=head(git_repo))], None, allow_drift=False)
    assert codes(info) == ["SOURCE_PROJECT_MISSING"]


# ---- index and cache ------------------------------------------------------------------------


@pytest.fixture
def indexed(tmp_path, monkeypatch, fake_extractor):
    repo = tmp_path / "repo"
    calls = {"evaluate": 0, "declarations": 0}

    def evaluate(p):
        calls["evaluate"] += 1
        return [repo / "src/A/a.cs"], {"Language": "C#", "DefineConstants": "X", "LangVersion": "12"}

    def declarations(request):
        calls["declarations"] += 1
        assert request["language"] == "C#" and request["preprocessorSymbols"] == ["X"] and request["langVersion"] == "12"
        return {"languageVersion": "CSharp12", "types": [
            {"name": "A.P", "file": str(repo / "src/A/a.cs")}, {"name": "A.P", "file": str(repo / "src/A/b.cs")},
            {"name": "A.Gen", "file": str(repo / "src/A/obj/Debug/Gen.cs")}, {"name": "A.Pkg", "file": str(tmp_path / "nuget/Pkg.cs")}]}

    monkeypatch.setattr(sources, "evaluate", evaluate)
    monkeypatch.setattr(sources, "declarations", declarations)
    return repo, calls


def test_index_excludes_obj_and_outside_files_and_is_cached(tmp_path, indexed):
    repo, calls = indexed
    cache = tmp_path / "cache"
    p = project(repo, commit="c")
    sources.index_project(p, cache)
    assert p.index == {"A.P": ["src/A/a.cs", "src/A/b.cs"]} and not p.cached and p.language_version == "CSharp12"
    again = project(repo, commit="c")
    sources.index_project(again, cache)
    assert again.cached and again.index == p.index and again.symbols == ["X"] and calls == {"evaluate": 1, "declarations": 1}
    other = project(repo, commit="d")  # another commit is another key
    sources.index_project(other, cache)
    assert not other.cached and calls["evaluate"] == 2
    assert len(list(cache.glob("*.json"))) == 2


def test_a_drifted_checkout_is_never_read_from_or_written_to_the_cache(tmp_path, indexed):
    repo, calls = indexed
    cache = tmp_path / "cache"
    drifted = project(repo, commit="c")
    drifted.drift = "the checkout has uncommitted changes"
    sources.index_project(drifted, cache)
    assert not cache.exists()
    sources.index_project(project(repo, commit="c"), cache)
    drifted = project(repo, commit="c")
    drifted.drift = "the checkout has uncommitted changes"
    sources.index_project(drifted, cache)
    assert not drifted.cached and calls["evaluate"] == 3


def test_a_corrupt_cache_entry_is_rebuilt(tmp_path, indexed):
    repo, calls = indexed
    cache = tmp_path / "cache"
    sources.index_project(project(repo, commit="c"), cache)
    next(cache.glob("*.json")).write_text("{")
    p = project(repo, commit="c")
    sources.index_project(p, cache)
    assert not p.cached and p.index and calls["evaluate"] == 2


def test_cache_key_covers_the_build_and_the_extractor(tmp_path):
    base = project(tmp_path, commit="c", build={"configuration": "Release"})
    keys = {sources.cache_key(base, "e1"), sources.cache_key(base, "e2"),
            sources.cache_key(project(tmp_path, commit="c", build={"configuration": "Debug"}), "e1"),
            sources.cache_key(project(tmp_path, commit="c", dirty_hash="d", build={"configuration": "Release"}), "e1")}
    assert len(keys) == 4


# ---- locate ---------------------------------------------------------------------------------


def test_locate_every_status(tmp_path):
    p = project(tmp_path)
    p.index = {"A.C": ["a.cs", "b.cs"], "A.Map<K, V>": ["m.cs"]}
    assert sources.locate(p, "A.C") == ("found", ["a.cs", "b.cs"])
    assert sources.locate(p, "A.C.<M>d__3") == ("compiler-generated", ["a.cs", "b.cs"])
    assert sources.locate(p, "A.Map<K, V>.<>c") == ("compiler-generated", ["m.cs"])
    assert sources.locate(p, "<PrivateImplementationDetails>") == ("generated", [])
    assert sources.locate(p, "A.Missing.<>c") == ("generated", [])
    assert sources.locate(p, "A.FromObj") == ("generated", [])
    assert sources.locate(None, "A.C") == ("nuget", [])


def test_repo_root_parsing():
    assert records.parse_repo_roots(["p3=D:/work/p3", "lib=x=y"]) == {"p3": Path("D:/work/p3"), "lib": Path("x=y")}
    for bad in (["p3"], ["=D:/x"], ["p3="]):
        with pytest.raises(RgError) as info:
            records.parse_repo_roots(bad)
        assert codes(info) == ["USAGE"]


# ---- MSBuild and Roslyn for real ------------------------------------------------------------

BUILT_EXTRACTOR = next((p for c in ("Release", "Debug") if (p := REPO / "src/RoslynToRdf.Cli/bin" / c / "net8.0" / extractor.ENTRY).is_file()), None)
requires_dotnet = pytest.mark.skipif(shutil.which("dotnet") is None or BUILT_EXTRACTOR is None,
                                     reason="needs the dotnet SDK and a built RoslynToRdf.Cli (dotnet build)")


@requires_dotnet
def test_real_project_with_solution_constants_linked_removed_and_conditional_items(git_repo, monkeypatch):
    monkeypatch.setenv("ROSLYN_GRAPH_EXTRACTOR", str(BUILT_EXTRACTOR))
    monkeypatch.delenv("ROSLYN_GRAPH_MSBUILD", raising=False)
    extractor.resolve.cache_clear()
    files = {
        "All.sln": "",
        "Common.targets": "<Project><PropertyGroup><DefineConstants>$(DefineConstants);TT3</DefineConstants></PropertyGroup></Project>",
        "Shared/Linked.cs": "namespace Shared; public class Linked { }",
        "src/A/A.csproj": """<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup><TargetFramework>net8.0</TargetFramework><LangVersion>12</LangVersion></PropertyGroup>
  <Import Project="$(SolutionDir)Common.targets" Condition="Exists('$(SolutionDir)Common.targets')" />
  <ItemGroup>
    <Compile Remove="Old/**" />
    <Compile Include="../../Shared/Linked.cs" Link="Linked.cs" />
    <Compile Include="../../Shared/Release.cs" Condition="'$(Configuration)' == 'Release'" />
  </ItemGroup>
</Project>""",
        "src/A/Camera.cs": "namespace A {\n#if TT3\n  public class Camera3 { }\n#else\n  public class CameraLegacy { }\n#endif\n#if NET8_0_OR_GREATER\n  public class Modern { }\n#endif\n}",
        "src/A/Partial1.cs": "namespace A; public partial class P { void M() { System.Action a = () => { }; } }",
        "src/A/Partial2.cs": "namespace A; public partial class P { }",
        "src/A/Old/Gone.cs": "namespace A; public class Gone { }",
        "Shared/Release.cs": "namespace Shared; public class ReleaseOnly { }",
    }
    for name, text in files.items():
        (git_repo / name).parent.mkdir(parents=True, exist_ok=True)
        (git_repo / name).write_text(text, encoding="utf-8")
    git_repo.git("add", ".")
    git_repo.git("commit", "-q", "-m", "project")

    def run(configuration):
        p = project(git_repo, commit=head(git_repo), build={"configuration": configuration, "targetFramework": "net8.0"},
                    solution=git_repo / "All.sln")
        sources.index_all([p], None, allow_drift=False)
        return p

    debug = run("Debug")
    assert debug.index == {"A.Camera3": ["src/A/Camera.cs"], "A.Modern": ["src/A/Camera.cs"],
                           "A.P": ["src/A/Partial1.cs", "src/A/Partial2.cs"], "Shared.Linked": ["Shared/Linked.cs"]}
    assert "TT3" in debug.symbols and "NET8_0_OR_GREATER" in debug.symbols and debug.language_version == "CSharp12"
    assert sources.locate(debug, "A.P.<>c") == ("compiler-generated", ["src/A/Partial1.cs", "src/A/Partial2.cs"])
    assert "Shared.ReleaseOnly" in run("Release").index

    no_solution = project(git_repo, commit=head(git_repo), build={"configuration": "Debug"})
    sources.index_all([no_solution], None, allow_drift=False)
    assert "A.CameraLegacy" in no_solution.index and "A.Camera3" not in no_solution.index  # TT3 comes from $(SolutionDir)
