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


def test_repository_is_in_sync():
    assert sync.check(fix=False) == []


def test_every_copy_has_a_source():
    for source, copy in sync.COPIES.items():
        assert (sync.REPO / source).is_file(), source
        assert copy.startswith("plugins/roslyn-graph/")
