from pathlib import Path

import pytest

from roslyn_graph import config
from roslyn_graph.result import RgError

VALID = """
schema_version = 1

[tools]
oxigraph = "0.5.8"

[profiles.app]
root = "../src"
solution = "App/App.sln"
output_dir = "App/bin/Debug"
fingerprint_files = ["Directory.Build.props"]

[profiles.app.build]
configuration = "Debug"
target_framework = "net10.0"
platform = "X64"

[profiles.app.collect]
all_solution_projects = true
packages = ["lib_1_0"]

[profiles.app.outputs]
"App\\\\Tests\\\\Tests.csproj" = "App/Tests/bin/Debug/net10.0"

[profiles.lib_1_0]
kind = "nuget"
package = "Lib"
version = "1.0.0"
target_framework = "net10.0"
source = "https://example.invalid/v3/index.json"
dependency_sources = ["https://api.nuget.org/v3/index.json"]
credential_env = "LIB_TOKEN"

[profiles.overlay]
root = "../lib"
solution = "Lib.sln"
output_dir = "bin"

[profiles.overlay.build]
configuration = "Debug"
target_framework = "net10.0"

[profiles.overlay.collect]
projects = ["src/Lib.csproj"]

[policies.additive]
assemblies = ["Lib"]

[collections.app]
base = "app"

[collections.app_current]
base = "app"
overlays = ["overlay"]
logical_type_policy = "additive"
"""


def write(tmp_path: Path, text: str) -> Path:
    ws = tmp_path / "ws" / "workspace.toml"
    ws.parent.mkdir(parents=True, exist_ok=True)
    ws.write_text(text, encoding="utf-8")
    return ws


def codes(exc: RgError) -> list[str]:
    return [p.message for p in exc.problems]


def test_valid_workspace_resolves_paths_relative_to_the_file(tmp_path):
    ws = config.load(write(tmp_path, VALID))
    app = ws.profiles["app"]
    assert isinstance(app, config.SolutionProfile)
    assert app.root == (tmp_path / "src").resolve()
    assert app.solution == (tmp_path / "src" / "App" / "App.sln").resolve()
    assert app.fingerprint_files == [(tmp_path / "src" / "Directory.Build.props").resolve()]
    assert app.outputs == {"App/Tests/Tests.csproj": (tmp_path / "src" / "App" / "Tests" / "bin" / "Debug" / "net10.0").resolve()}
    lib = ws.profiles["lib_1_0"]
    assert isinstance(lib, config.NugetProfile) and lib.dependency_sources == ["https://api.nuget.org/v3/index.json"]
    assert ws.collections["app_current"].overlays == ["overlay"]
    assert ws.policies["additive"] == ["Lib"]
    assert len(ws.sha256) == 64


def test_every_problem_is_reported_in_one_pass(tmp_path):
    text = VALID.replace('version = "1.0.0"', 'version = "1.*"').replace("all_solution_projects = true", "").replace(
        'credential_env = "LIB_TOKEN"', 'credential_env = "ghp secret"')
    with pytest.raises(RgError) as info:
        config.load(write(tmp_path, text + '\n[profiles.app.extra]\nx = "y"\n'))
    messages = codes(info.value)
    assert any("profiles.lib_1_0.version" in m for m in messages)
    assert any("profiles.app.collect" in m and "exactly one" in m for m in messages)
    assert any("credential_env" in m for m in messages)
    assert any("profiles.app.extra: unknown key" in m for m in messages)
    assert all(p.hint is not None for p in info.value.problems)


def test_schema_version_must_be_one(tmp_path):
    with pytest.raises(RgError) as info:
        config.load(write(tmp_path, VALID.replace("schema_version = 1", "schema_version = 2")))
    assert info.value.problems[0].code == "TOML_SCHEMA_VERSION"


def test_collection_references_are_checked(tmp_path):
    text = VALID.replace('overlays = ["overlay"]', 'overlays = ["missing"]').replace('logical_type_policy = "additive"', 'logical_type_policy = "nope"')
    with pytest.raises(RgError) as info:
        config.load(write(tmp_path, text))
    messages = codes(info.value)
    assert any("'missing' is not a profile" in m for m in messages)
    assert any("'nope' is not defined" in m for m in messages)


def test_overlays_need_a_policy(tmp_path):
    with pytest.raises(RgError) as info:
        config.load(write(tmp_path, VALID.replace('logical_type_policy = "additive"', "")))
    assert any("needs logical_type_policy" in m for m in codes(info.value))


def test_collect_packages_must_name_nuget_profiles(tmp_path):
    with pytest.raises(RgError) as info:
        config.load(write(tmp_path, VALID.replace('packages = ["lib_1_0"]', 'packages = ["overlay"]')))
    assert any("not a nuget profile" in m for m in codes(info.value))


def test_toml_syntax_errors_are_reported(tmp_path):
    with pytest.raises(RgError) as info:
        config.load(write(tmp_path, "schema_version = \n"))
    assert info.value.problems[0].code == "TOML_SYNTAX"


def test_missing_file(tmp_path):
    with pytest.raises(RgError) as info:
        config.load(tmp_path / "nope.toml")
    assert info.value.problems[0].code == "WORKSPACE_NOT_FOUND"
