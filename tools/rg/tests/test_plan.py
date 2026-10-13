import os
import subprocess
import time
from pathlib import Path

import pytest

from roslyn_graph import config, discover, gitinfo, plan
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
    assert components[0].extraction_path == git_repo / "src" / "Alpha" / "Alpha.csproj"
    assert components[0].manifest["extraction"]["inputKind"] == "source-project"


def test_project_path_is_relative_to_owning_repository_when_nested(git_repo):
    nested = git_repo / "src" / "NestedRepo"
    nested.mkdir(parents=True)
    (nested / ".git").mkdir()
    subprocess.run(["git", "-C", str(nested), "init", "-q", "-b", "main"], check=True)
    subprocess.run(["git", "-C", str(nested), "config", "user.email", "test@example.invalid"], check=True)
    subprocess.run(["git", "-C", str(nested), "config", "user.name", "Test"], check=True)
    project = nested / "src" / "Lib"
    project.mkdir(parents=True)
    (project / "Lib.csproj").write_text('<Project Sdk="Microsoft.NET.Sdk" />')
    (project / "Code.cs").write_text("class C {}")
    (nested / ".gitignore").write_text("bin/\n")
    subprocess.run(["git", "-C", str(nested), "add", "."], check=True)
    subprocess.run(["git", "-C", str(nested), "commit", "-q", "-m", "nested project"], check=True)
    gitinfo.repo_state.cache_clear()
    (git_repo / "App.sln").write_text(
        'Project("{FAE04EC0-301F-11D3-BF4B-00C04F79EFBC}") = "Lib", "src\\NestedRepo\\src\\Lib\\Lib.csproj", "{22222222-2222-2222-2222-222222222222}"\n'
    )
    (git_repo / "Directory.Build.props").write_text("<Project />")
    out = git_repo / "bin" / "Debug"
    out.mkdir(parents=True)
    dll = out / "Lib.dll"
    dll.write_bytes(b"Lib")
    os.utime(dll, (time.time() + 5, time.time() + 5))

    problems = ProblemList()
    components = plan._solution_components(profile(git_repo), "base", TOOL, False, problems)
    assert not problems
    assert components[0].manifest["origin"]["id"] == "NestedRepo"
    assert components[0].manifest["build"]["project"] == "src/Lib/Lib.csproj"


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


@pytest.mark.parametrize(
    ("project_extension", "output_type"),
    [("csproj", "Exe"), ("csproj", "WinExe"), ("vbproj", "Exe"), ("vbproj", "WinExe")],
)
def test_executable_project_output_resolution(git_repo, project_extension, output_type):
    project_dir = git_repo / "src" / "DesktopApp"
    project_dir.mkdir(parents=True)
    project = project_dir / f"DesktopApp.{project_extension}"
    project.write_text(
        f'<Project><PropertyGroup><AssemblyName>DesktopApp</AssemblyName><OutputType>{output_type}</OutputType></PropertyGroup></Project>'
    )
    source_extension = "cs" if project_extension == "csproj" else "vb"
    (project_dir / f"Program.{source_extension}").write_text("class Program {}")
    (git_repo / "App.sln").write_text(
        f'Project("{{FAE04EC0-301F-11D3-BF4B-00C04F79EFBC}}") = "DesktopApp", "src\\DesktopApp\\DesktopApp.{project_extension}", "{{22222222-2222-2222-2222-222222222222}}"\n'
    )
    (git_repo / "Directory.Build.props").write_text("<Project />")
    git_repo.git("add", ".")
    git_repo.git("commit", "-q", "-m", f"add {project_extension} {output_type} project")
    gitinfo.repo_state.cache_clear()

    output_dir = git_repo / "bin" / "Debug"
    output_dir.mkdir(parents=True)
    executable = output_dir / "DesktopApp.exe"
    executable.write_bytes(b"managed executable")
    os.utime(executable, (time.time() + 5, time.time() + 5))

    if project_extension == "vbproj":
        source = project_dir / f"Program.{source_extension}"
        source_time = time.time() + 60
        os.utime(source, (source_time, source_time))
        stale_problems = ProblemList()
        plan._solution_components(profile(git_repo), "base", TOOL, True, stale_problems)
        assert [problem.code for problem in stale_problems.items] == ["BUILD_OUTPUT_STALE"]
        os.utime(executable, (source_time + 5, source_time + 5))

    problems = ProblemList()
    components = plan._solution_components(profile(git_repo), "base", TOOL, True, problems)

    assert not problems
    assert len(components) == 1
    assert components[0].assembly_path == executable
    assert components[0].manifest["assembly"]["inputPath"] == str(executable)
    if project_extension == "csproj":
        assert components[0].extraction_path == project
        assert components[0].manifest["extraction"]["inputKind"] == "source-project"
    else:
        assert components[0].extraction_path == executable
        assert components[0].manifest["extraction"]["inputKind"] == "assembly"


def test_discovery_finds_winexe_project_output(git_repo):
    project_dir = git_repo / "src" / "DesktopApp"
    project_dir.mkdir(parents=True)
    project = project_dir / "DesktopApp.vbproj"
    project.write_text('<Project><PropertyGroup><OutputType>WinExe</OutputType></PropertyGroup></Project>')
    (project_dir / "Program.vb").write_text("Module Program\nEnd Module\n")
    solution = git_repo / "App.sln"
    solution.write_text(
        'Project("{FAE04EC0-301F-11D3-BF4B-00C04F79EFBC}") = "DesktopApp", "src\\DesktopApp\\DesktopApp.vbproj", "{22222222-2222-2222-2222-222222222222}"\n'
    )
    output = git_repo / "bin" / "Debug" / "DesktopApp.exe"
    output.parent.mkdir(parents=True)
    output.write_bytes(b"managed executable")
    git_repo.git("add", ".")
    git_repo.git("commit", "-q", "-m", "add WinExe project")
    gitinfo.repo_state.cache_clear()

    result = discover.solution(solution, git_repo, None)

    assert result["projects"][0]["outputType"] == "WinExe"
    assert result["projects"][0]["assemblyExtension"] == ".exe"
    assert result["projects"][0]["outputCandidates"] == [str(output)]


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


def test_two_projects_with_the_same_output_are_an_error(git_repo):
    make_solution(git_repo)
    build_outputs(git_repo, names=("Alpha",))
    p = profile(git_repo, assembly_names={"src/Beta/Beta.csproj": "Alpha"})  # Beta also builds Alpha.dll
    problems = ProblemList()
    components = plan._solution_components(p, "base", TOOL, True, problems)
    fake = plan.Plan(workspace=None, collection=None, root=git_repo, extractor=TOOL, oxigraph_version="0", components=components)
    with pytest.raises(RgError) as info:
        plan._check_duplicates(fake)
    problem = info.value.problems[0]
    assert problem.code == "DUPLICATE_OUTPUT"
    assert any("src/Alpha/Alpha.csproj" in s for s in problem.context["sources"])
    assert any("src/Beta/Beta.csproj" in s for s in problem.context["sources"])
