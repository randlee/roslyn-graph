"""result, util, oxigraph stderr handling and msbuild readers."""

import io
import os
import json
from pathlib import Path

import pytest

from roslyn_graph import msbuild, oxigraph, util
from roslyn_graph.result import ProblemList, RgError, emit, error_payload


def test_emit_requires_a_discriminator():
    with pytest.raises(ValueError):
        emit({"value": 1}, io.StringIO())


def test_error_payload_shape():
    problems = ProblemList()
    problems.add("A", "first", "fix a", key="x")
    problems.add("B", "second")
    with pytest.raises(RgError) as info:
        problems.raise_if_any()
    stream = io.StringIO()
    emit(error_payload(info.value), stream)
    payload = json.loads(stream.getvalue())
    assert payload == {"type": "error", "errors": [
        {"code": "A", "message": "first", "hint": "fix a", "context": {"key": "x"}},
        {"code": "B", "message": "second", "hint": "", "context": {}},
    ]}


@pytest.mark.parametrize("value,expected", [
    ("Contoso.Data", "Contoso.Data"),
    ("1.0.0.0", "1.0.0.0"),
    ("List`1", "List%601"),
    ("<Module>", "%3CModule%3E"),
    ("Outer+Inner", "Outer%2BInner"),
    ("é", "é"),
])
def test_iri_escape_matches_iriminter(value, expected):
    assert util.iri_escape(value) == expected


def test_nt_literal_escapes_control_characters():
    assert util.nt_literal('a\\b"c\nd\te') == '"a\\\\b\\"c\\nd\\te"'


def test_nt_iri_rejects_forbidden_characters():
    with pytest.raises(RgError):
        util.nt_iri("http://x/a b")


def test_oxigraph_advisories_are_ignored_but_errors_are_not():
    stderr = "\n".join([
        "Some files like Wikidata dumps contain invalid IRIs or language tags. If you want to load them anyway use the `--lenient` option.",
        "1027826 triples loaded in 0s (2091124 t/s) from x.nt",
        "Error while loading file x.ttl: Parser error at line 1 between columns 1 and 8: garbage is not a valid subject",
        "If you plan to run a read-heavy workload, consider running `oxigraph optimize -l store` before",
    ])
    assert oxigraph.unexpected_stderr(stderr) == [
        "Error while loading file x.ttl: Parser error at line 1 between columns 1 and 8: garbage is not a valid subject"
    ]


def test_oxigraph_missing_input_is_an_error():
    assert oxigraph.unexpected_stderr("Error while loading file a.nt: The system cannot find the file specified. (os error 2)")


def test_read_solution_keeps_only_csproj(tmp_path):
    sln = tmp_path / "App.sln"
    sln.write_text(
        'Project("{2150E333-8FDC-42A3-9474-1A3956D46DE8}") = "Folder", "Folder", "{11111111-1111-1111-1111-111111111111}"\n'
        'Project("{FAE04EC0-301F-11D3-BF4B-00C04F79EFBC}") = "Lib", "..\\Lib\\Lib.csproj", "{22222222-2222-2222-2222-222222222222}"\n'
        'Project("{F184B08F-C81C-45F6-A57F-5ABD9991F28F}") = "Vb", "Vb\\Vb.vbproj", "{33333333-3333-3333-3333-333333333333}"\n',
        encoding="utf-8-sig",
    )
    projects = msbuild.read_solution(sln)
    assert [(p.name, p.relative_path) for p in projects] == [("Lib", "../Lib/Lib.csproj")]
    assert projects[0].path == (tmp_path.parent / "Lib" / "Lib.csproj").resolve()


def test_read_slnx(tmp_path):
    sln = tmp_path / "App.slnx"
    sln.write_text('<Solution><Folder Name="/src/"><Project Path="src/A/A.csproj" /></Folder></Solution>')
    assert [p.name for p in msbuild.read_solution(sln)] == ["A"]


def test_read_project_assembly_name(tmp_path):
    project = tmp_path / "A.csproj"
    project.write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><AssemblyName>Custom.Name</AssemblyName>'
                       "<TargetFrameworks>net8.0;net10.0</TargetFrameworks></PropertyGroup></Project>")
    info = msbuild.read_project(project)
    assert (info.assembly_name, info.assembly_name_source, info.target_frameworks) == ("Custom.Name", "csproj", ["net8.0", "net10.0"])
    project.write_text('<Project><PropertyGroup><AssemblyName>$(Prefix).X</AssemblyName></PropertyGroup></Project>')
    with pytest.raises(RgError) as info:
        msbuild.read_project(project)
    assert info.value.problems[0].code == "ASSEMBLY_NAME_COMPUTED"
    project.write_text("<Project />")
    assert msbuild.read_project(project).assembly_name == "A"


def test_select_target():
    assert msbuild.select_target(["net10.0", "net10.0/win-x64"], "net10.0", Path("a")) == "net10.0"
    assert msbuild.select_target(["net8.0", "net10.0-windows7.0"], "net10.0", Path("a")) == "net10.0-windows7.0"
    with pytest.raises(RgError) as info:
        msbuild.select_target(["net8.0"], "net10.0", Path("a"))
    assert info.value.problems[0].code == "ASSETS_TARGET_MISSING"


def test_read_assets(tmp_path):
    folder = tmp_path / "packages"
    (folder / "lib.a" / "1.0.0" / "lib" / "net10.0").mkdir(parents=True)
    assets = tmp_path / "project.assets.json"
    assets.write_text(json.dumps({
        "targets": {"net10.0": {
            "Lib.A/1.0.0": {"type": "package", "compile": {"lib/net10.0/Lib.A.dll": {}}, "runtime": {"lib/net10.0/Lib.A.dll": {}}},
            "Meta/1.0.0": {"type": "package", "runtime": {"lib/net10.0/_._": {}}},
            "Other/1.0.0": {"type": "project"},
        }},
        "libraries": {"Lib.A/1.0.0": {"sha512": "abc", "type": "package", "path": "lib.a/1.0.0"}, "Meta/1.0.0": {"path": "meta/1.0.0"}},
        "packageFolders": {str(folder) + os.sep: {}},
    }))
    result = msbuild.read_assets(assets, "net10.0")
    assert set(result.packages) == {"lib.a", "meta"}
    lib = result.packages["lib.a"]
    assert lib.runtime == ("lib/net10.0/Lib.A.dll",) and lib.sha512 == "abc"
    assert lib.asset_dirs() == [folder / "lib.a" / "1.0.0" / "lib" / "net10.0"]
    assert result.packages["meta"].runtime == ()


def test_read_only_commands_retry_once_after_a_native_crash(monkeypatch):
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        return util.Completed(args, 0xC0000005 if len(calls) == 1 else 0, "ok", "")

    monkeypatch.setattr(oxigraph, "run", fake_run)
    assert oxigraph.invoke(["dump", "--location", "s"], "dumping") == "ok"
    assert len(calls) == 2


def test_loads_are_never_retried(monkeypatch):
    calls = []
    monkeypatch.setattr(oxigraph, "run", lambda args, **kw: calls.append(args) or util.Completed(args, 0xC0000005, "", ""))
    with pytest.raises(RgError):
        oxigraph.invoke(["load", "--location", "s"], "loading")
    assert len(calls) == 1
    assert oxigraph.crashed(-11) and oxigraph.crashed(0xC0000005) and not oxigraph.crashed(1)
