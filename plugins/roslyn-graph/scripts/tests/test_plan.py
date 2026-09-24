import os
import time
from pathlib import Path

import pytest

from roslyn_graph import config, gitinfo, plan
from roslyn_graph.extractor import Extractor
from roslyn_graph.result import ProblemList, RgError

TOOL = Extractor(Path("RoslynToRdf.Cli.dll"), "ext1", "Microsoft.NETCore.App 8.0.0", "hash", "test")
SLN = 'Project("{{FAE04EC0-301F-11D3-BF4B-00C04F79EFBC}}") = "{name}", "src\\{name}\\{name}.csproj", "{{22222222-2222-2222-2222-22222222222{i}}}"\n'


def make_solution(repo: Path, names=("Alpha", "Beta")) -> None:
    (repo / "App.sln").write_text("".join(SLN.format(name=n, i=i) for i, n in enumerate(names)))
    for name in names:
        project = repo / "src" / name
        project.mkdir(parents=True)
        (project / f"{name}.csproj").write_text('<Project Sdk="Microsoft.NET.Sdk" />')
        (project / "Code.cs").write_text("class C {}")
    (repo / "Directory.Build.props").write_text("<Project />")
    (repo / ".gitignore").write_text("bin/\nobj/\n")
    repo.git("add", ".")
    repo.git("commit", "-q", "-m", "solution")
    gitinfo.repo_state.cache_clear()


def build_outputs(repo: Path, names=("Alpha", "Beta")) -> None:
    out = repo / "bin" / "Debug"
    out.mkdir(parents=True, exist_ok=True)
    later = time.time() + 5
    for name in names:
        dll = out / f"{name}.dll"
        dll.write_bytes(name.encode())
        os.utime(dll, (later, later))


def profile(repo: Path, **overrides) -> config.SolutionProfile:
    values = dict(
        name="app", root=repo, solution=repo / "App.sln", output_dir=repo / "bin" / "Debug", configuration="Debug",
        target_framework="net10.0", platform="", fingerprint_files=[repo / "Directory.Build.props"], search_dirs=[],
        all_solution_projects=True, projects=[], exclude=[], packages=[], outputs={}, assembly_names={},
    )
    values.update(overrides)
    return config.SolutionProfile(**values)


def test_fingerprint_is_deterministic_and_tracks_file_content(git_repo):
    make_solution(git_repo)
    first = plan.fingerprint(profile(git_repo))
    assert first.startswith("debug-net10.0-") and first == plan.fingerprint(profile(git_repo))
    (git_repo / "Directory.Build.props").write_text("<Project><PropertyGroup /></Project>")
    assert plan.fingerprint(profile(git_repo)) != first


def test_components_record_exact_provenance(git_repo):
    make_solution(git_repo)
    build_outputs(git_repo)
    problems = ProblemList()
    components = plan._solution_components(profile(git_repo), "base", TOOL, False, problems)
    assert not problems
    assert [c.expected_name for c in components] == ["Alpha", "Beta"]
    origin = components[0].manifest["origin"]
    assert origin["id"] == "repo" and len(origin["commit"]) == 40 and origin["dirtyHash"] == ""
    assert components[0].manifest["build"]["project"] == "src/Alpha/Alpha.csproj"
    assert components[0].search_dirs[0] == (git_repo / "bin" / "Debug").resolve()


def test_missing_output_is_reported_with_a_fix(git_repo):
    make_solution(git_repo)
    build_outputs(git_repo, names=("Alpha",))
    problems = ProblemList()
    plan._solution_components(profile(git_repo), "base", TOOL, False, problems)
    assert [p.code for p in problems.items] == ["BUILD_OUTPUT_MISSING"]
    assert "outputs" in problems.items[0].hint


def test_stale_output_is_rejected(git_repo):
    make_solution(git_repo)
    build_outputs(git_repo)
    future = time.time() + 60
    os.utime(git_repo / "src" / "Beta" / "Code.cs", (future, future))
    problems = ProblemList()
    plan._solution_components(profile(git_repo), "base", TOOL, True, problems)
    assert [p.code for p in problems.items] == ["BUILD_OUTPUT_STALE"]


def test_dirty_repository_needs_allow_dirty(git_repo):
    make_solution(git_repo)
    build_outputs(git_repo)
    (git_repo / "untracked.txt").write_text("x")
    gitinfo.repo_state.cache_clear()
    problems = ProblemList()
    plan._solution_components(profile(git_repo), "base", TOOL, False, problems)
    assert {p.code for p in problems.items} == {"SOURCE_DIRTY"}
    problems = ProblemList()
    components = plan._solution_components(profile(git_repo), "base", TOOL, True, problems)
    assert not problems and components[0].manifest["origin"]["dirtyHash"]


def test_explicit_projects_must_be_in_the_solution(git_repo):
    make_solution(git_repo)
    problems = ProblemList()
    selected = plan.select_projects(profile(git_repo, all_solution_projects=False, projects=["src/Alpha/Alpha.csproj", "src/Nope/Nope.csproj"],
                                            exclude=["src/Gamma/Gamma.csproj"]),
                                    plan.msbuild.read_solution(git_repo / "App.sln"), problems)
    assert [p.name for p in selected] == ["Alpha"]
    assert [p.code for p in problems.items] == ["PROJECT_NOT_IN_SOLUTION", "EXCLUDE_NOT_SELECTED"]


def test_output_overrides_and_assembly_names(git_repo):
    make_solution(git_repo)
    build_outputs(git_repo, names=("Alpha",))
    special = git_repo / "src" / "Beta" / "bin"
    special.mkdir(parents=True)
    (special / "Renamed.dll").write_bytes(b"x")
    later = time.time() + 5
    os.utime(special / "Renamed.dll", (later, later))
    p = profile(git_repo, outputs={"src/Beta/Beta.csproj": special}, assembly_names={"src/Beta/Beta.csproj": "Renamed"})
    problems = ProblemList()
    components = plan._solution_components(p, "base", TOOL, True, problems)
    assert not problems
    assert components[1].assembly_path == special / "Renamed.dll"


def test_newest_input_skips_build_folders(tmp_path):
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "x.cs").write_text("")
    future = time.time() + 100
    os.utime(tmp_path / "bin" / "x.cs", (future, future))
    (tmp_path / "a.cs").write_text("")
    newest, path = plan.newest_input(tmp_path)
    assert path == tmp_path / "a.cs"


def test_missing_fingerprint_file(git_repo):
    make_solution(git_repo)
    with pytest.raises(RgError) as info:
        plan.fingerprint(profile(git_repo, fingerprint_files=[git_repo / "nope.targets"]))
    assert info.value.problems[0].code == "FINGERPRINT_FILE_MISSING"
