import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "check_plugin_sync.py"
spec = importlib.util.spec_from_file_location("check_plugin_sync", SCRIPT)
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


def test_emitted_terms_include_constants_and_inline_terms():
    terms = sync.emitted_terms()
    assert {"definedInAssembly", "implements", "arrayRank", "index", "type", "Interface"} <= terms
    assert "http" not in terms and "dt" not in terms


def test_every_skill_with_the_cli_gets_every_master_module():
    mapping = sync.copies()
    masters = {p.relative_to(sync.MASTER).as_posix() for p in [sync.MASTER / "rg.py", *(sync.MASTER / "roslyn_graph").glob("*.py")]}
    for skill in sync.SKILLS_WITH_CLI:
        carried = {c.relative_to(sync.SKILLS / skill / "scripts").as_posix() for c in mapping if c.is_relative_to(sync.SKILLS / skill / "scripts")}
        assert carried == masters
    assert not any("tests" in c.parts for c in mapping), "tests stay in tools/rg"


def test_every_copy_has_a_master_inside_the_repo():
    for copy, master in sync.copies().items():
        assert master.is_file(), master
        assert copy.is_relative_to(sync.SKILLS)


def test_repository_is_in_sync():
    assert sync.check(fix=False) == []
