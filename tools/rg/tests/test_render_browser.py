"""End-to-end: a rendered explorer page shows its embedded graph in a real (headless) browser.

A Node-only check parses the embedded RDF but never runs the page's own loading order; this test does.
It needs Chrome/Chromium and network access for the page's CDN libraries, and is skipped without them.
"""

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from roslyn_graph import explore

CANDIDATES = [
    os.environ.get("CHROME_PATH", ""),
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    shutil.which("google-chrome") or "",
    shutil.which("chromium") or "",
    shutil.which("chromium-browser") or "",
]
CHROME = next((c for c in CANDIDATES if c and Path(c).is_file()), None)

DT = "http://dotnet.example/ontology/"
RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"


@pytest.mark.skipif(CHROME is None, reason="Chrome/Chromium is not installed")
def test_rendered_page_loads_the_embedded_graph(tmp_path):
    ns = "http://dotnet.example/namespace/Contoso.Data"
    lines = [f'<{ns}> <{DT}name> "Contoso.Data" .']
    for name, kind in (("IRepository", "Interface"), ("Repository", "Class"), ("Options", "Class")):
        iri = f"http://dotnet.example/type/Contoso.Data/1.0.0.0/Contoso.Data.{name}"
        lines += [f"<{iri}> <{RDF_TYPE}> <{DT}{kind}> .", f'<{iri}> <{DT}name> "{name}" .', f"<{iri}> <{DT}inNamespace> <{ns}> ."]
    data = tmp_path / "graph.nt"
    data.write_text("\n".join(lines) + "\n", encoding="utf-8")
    explore.write_context(data, {"generator": "graph", "source": {"manifest": "views/x/manifest.json"}})
    page = tmp_path / "graph.html"
    explore.render("explorer", data, page, "browser test")

    completed = subprocess.run(
        [CHROME, "--headless=new", "--disable-gpu", "--no-first-run", "--no-sandbox",
         f"--user-data-dir={tmp_path / 'profile'}", "--virtual-time-budget=15000", "--dump-dom", page.resolve().as_uri()],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
    )
    dom = completed.stdout
    assert dom, f"Chrome produced no DOM: {completed.stderr[-500:]}"
    if "cytoscape" not in dom:
        pytest.skip("the page's CDN libraries did not load (no network?)")
    type_count = re.search(r'id="type-count"[^>]*>([^<]*)<', dom)
    assert type_count and type_count.group(1).strip() == "3", f"type-count shows {type_count.group(1) if type_count else None!r}"
    assert "Load an RDF file to explore types" not in dom.split('id="roslyn-graph-data"')[0]
    copy_button = re.search(r'<button[^>]*id="copy-graph-btn"[^>]*>', dom)
    assert copy_button and "disabled" not in copy_button.group(0), "Copy for Claude stays disabled after the graph loads"
    assert "roslyn-graph-context" in dom
