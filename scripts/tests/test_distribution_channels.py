import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).parents[2] / ".github" / "scripts" / "distribution_channels.py"
SPEC = importlib.util.spec_from_file_location("distribution_channels", SCRIPT)
distribution_channels = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(distribution_channels)


def release_data():
    version = "1.2.3"
    names = distribution_channels.expected_names(version)
    return {
        "repo": "randlee/roslyn-graph",
        "tag": "v" + version,
        "version": version,
        "assets": {name: "0" * 64 for name in names},
    }


def test_distribution_generators_use_roslyn_graph_public_names(tmp_path):
    data = release_data()

    formula_path = tmp_path / "Formula" / "roslyn-graph.rb"
    distribution_channels.formula(data, formula_path)
    formula = formula_path.read_text(encoding="utf-8")
    assert "class RoslynGraph < Formula" in formula
    assert '=> "roslyn2rdf"' in formula

    scoop_path = tmp_path / "bucket" / "roslyn-graph.json"
    distribution_channels.scoop(data, scoop_path)
    manifest = scoop_path.read_text(encoding="utf-8")
    assert '"bin": [' in manifest
    assert '"roslyn2rdf"' in manifest

    winget_path = tmp_path / "winget"
    distribution_channels.winget(data, winget_path)
    assert sorted(path.name for path in winget_path.iterdir()) == [
        "Randlee.Roslyn-Graph.installer.yaml",
        "Randlee.Roslyn-Graph.version.yaml",
        "Randlee.Roslyn-Graph.yaml",
    ]
    locale = (winget_path / "Randlee.Roslyn-Graph.yaml").read_text(encoding="utf-8")
    installer = (winget_path / "Randlee.Roslyn-Graph.installer.yaml").read_text(encoding="utf-8")
    assert "PackageName: roslyn-graph" in locale
    assert "PortableCommandAlias: roslyn2rdf.exe" in installer
