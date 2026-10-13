"""openwiki-scope: ignore chain, managed blocks, brief, records merge, and the chain checked by OpenWiki's own matcher."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import SCRIPTS
from roslyn_graph import openwiki
from roslyn_graph.result import RgError


def codes(exc: pytest.ExceptionInfo) -> list[str]:
    return [p.code for p in exc.value.problems]


# ---- chain ----------------------------------------------------------------------------------


def test_chain_one_file_at_the_root_and_deep():
    assert openwiki.chain(["README.md"]) == ["*", "!/openwiki/", "!/README.md"]
    assert openwiki.chain(["a/b/c/D.cs"]) == ["*", "!/openwiki/", "!/a/", "/a/*", "!/a/b/", "/a/b/*", "!/a/b/c/", "/a/b/c/*", "!/a/b/c/D.cs"]


def test_chain_siblings_share_ancestors_and_the_readme_example():
    lines = openwiki.chain(["src/Billing/Orders/OrderLine.cs", "src/Billing/Payments/", "src/Billing/Orders/Order.cs", "src/Billing/Orders/Order.cs"])
    assert lines == ["*", "!/openwiki/", "!/src/", "/src/*", "!/src/Billing/", "/src/Billing/*", "!/src/Billing/Orders/", "/src/Billing/Orders/*",
                     "!/src/Billing/Orders/Order.cs", "!/src/Billing/Orders/OrderLine.cs", "!/src/Billing/Payments/"]


def test_chain_drops_paths_inside_an_opened_directory():
    assert openwiki.chain(["src/A/", "src/A/x.cs", "src/A/deep/", "src/AB/y.cs"]) == \
        ["*", "!/openwiki/", "!/src/", "/src/*", "!/src/A/", "!/src/AB/", "/src/AB/*", "!/src/AB/y.cs"]


def test_chain_is_case_insensitive_like_openwiki():
    assert openwiki.chain(["common/x.cs", "Common/y.cs"]) == \
        ["*", "!/openwiki/", "!/Common/", "/Common/*", "!/Common/x.cs", "!/Common/y.cs"]
    assert openwiki.chain(["src/a/", "src/A/x.cs", "SRC/b.cs"]) == ["*", "!/openwiki/", "!/SRC/", "/SRC/*", "!/SRC/A/", "!/SRC/b.cs"]
    assert openwiki.chain(["A.cs", "a.cs"]) == ["*", "!/openwiki/", "!/A.cs"]
    # JavaScript's /i folds simply: 'ß' is not 'ss' to OpenWiki, so these stay two directories.
    assert openwiki.chain(["Straße/a.cs", "STRASSE/b.cs"]) == \
        ["*", "!/openwiki/", "!/STRASSE/", "/STRASSE/*", "!/STRASSE/b.cs", "!/Straße/", "/Straße/*", "!/Straße/a.cs"]
    # ...but it does fold final sigma and capital sharp s, which str.lower does not.
    assert openwiki.chain(["ς/i.cs", "Σ/ß.cs"]) == ["*", "!/openwiki/", "!/Σ/", "/Σ/*", "!/Σ/i.cs", "!/Σ/ß.cs"]
    assert openwiki.fold("ẞΣςİK") == "ßσσİk"


@pytest.mark.parametrize("path", ["src/*.cs", "src/a?.cs", "src/!x.cs", "/abs.cs", "../up.cs", "src/./x.cs", "src//x.cs", " x.cs",
                                  "src\\x.cs", "C:/x.cs", "#x.cs", ""])
def test_chain_rejects_paths_a_rule_cannot_match_exactly(path):
    with pytest.raises(RgError) as info:
        openwiki.chain(["ok.cs", path])
    assert codes(info) == ["OPENWIKI_PATH_UNSUPPORTED"]


def test_chain_reports_every_bad_path():
    with pytest.raises(RgError) as info:
        openwiki.chain(["a*", "b?"])
    assert codes(info) == ["OPENWIKI_PATH_UNSUPPORTED"] * 2


# ---- managed blocks -------------------------------------------------------------------------


def test_block_created_at_the_top_then_replaced_in_place():
    created = openwiki.merge_block(None, ["*"], False, "f")
    assert created == f"# {openwiki.BEGIN} (generated; edit below the END line)\n*\n# {openwiki.END}\n"
    user = "secrets/\n*.log\n"
    first = openwiki.merge_block(user, ["*", "!/a.cs"], False, "f")
    assert first.splitlines()[-2:] == ["secrets/", "*.log"] and first.splitlines()[1:3] == ["*", "!/a.cs"]
    edited = "# mine\n" + first + "tmp/\n"
    second = openwiki.merge_block(edited, ["*", "!/b.cs"], False, "f")
    lines = second.splitlines()
    assert lines[0] == "# mine" and lines[2:4] == ["*", "!/b.cs"] and lines[-3:] == ["secrets/", "*.log", "tmp/"]
    assert "!/a.cs" not in lines
    assert openwiki.merge_block(second, ["*", "!/b.cs"], False, "f") == second


def test_markdown_block_keeps_user_text():
    text = openwiki.merge_block("# My notes\n\nKeep this.\r\n", ["# Scope"], True, "f")
    assert text.startswith("<!-- BEGIN") and text.endswith("# My notes\n\nKeep this.\n")
    again = openwiki.merge_block(text.replace("# Scope", "# Old"), ["# Scope 2"], True, "f")
    assert "# Old" not in again and "# Scope 2" in again and again.endswith("Keep this.\n")


@pytest.mark.parametrize("existing", [f"# {openwiki.BEGIN}\n*\n", f"# {openwiki.END}\n# {openwiki.BEGIN}\n",
                                      f"# {openwiki.BEGIN}\n# {openwiki.END}\n# {openwiki.BEGIN}\n# {openwiki.END}\n"])
def test_damaged_blocks_are_refused(existing):
    with pytest.raises(RgError) as info:
        openwiki.merge_block(existing, ["*"], False, "f")
    assert codes(info) == ["OPENWIKI_BLOCK_BROKEN"]


# ---- records, brief and the command ---------------------------------------------------------


def rec(name, files=(), status="found", repository="p3", kind="Class", dirs=("src/Billing/",), origin="source", namespace=None, **extra):
    ns = namespace if namespace is not None else name.rsplit(".", 1)[0]
    return {"name": name, "kind": kind, "namespace": ns, "assemblies": ["Billing"], "repository": repository,
            "projectDirs": list(dirs), "files": list(files), "locationStatus": status, "origin": origin, **extra}


RECORDS = [
    rec("Billing.Orders.Order", ["src/Billing/Orders/Order.cs"]),
    rec("Billing.Orders.OrderLine", ["src/Billing/Orders/OrderLine.cs"]),
    rec("Billing.Orders.Order.<>c", ["src/Billing/Orders/Order.cs"], status="compiler-generated"),
    rec("Billing.Generated.Weaved", status="generated"),
    rec("Billing.Pay.Payment", ["src/Pay/Payment.cs"], dirs=["src/Pay/"]),
    rec("Contoso.Money", [], status="nuget", repository=None, dirs=[], origin="nuget"),
    rec("Radiant.Core.Device", ["Core/Device.cs"], repository="radiant", dirs=["Core/"]),
]


@pytest.fixture
def checkout(tmp_path):
    root = tmp_path / "p3"
    for f in ("src/Billing/Orders/Order.cs", "src/Billing/Orders/OrderLine.cs", "src/Billing/Orders/OrderMapper.cs", "src/Pay/Payment.cs"):
        (root / f).parent.mkdir(parents=True, exist_ok=True)
        (root / f).write_text("x")
    return root


def write_records(path: Path, rows, context=None, fmt="jsonl") -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows) if fmt == "json" else "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    if context is not None:
        path.with_suffix(".context.json").write_text(json.dumps(context), encoding="utf-8")
    return str(path)


CONTEXT = {"format": "roslyn-graph-context/1", "createdUtc": "2026-10-13T12:00:00Z", "source": {"artifactId": "view-abc"},
           "input": {"kind": "graph", "path": "D:/out/measurement-database.nt"}, "repositories": {"p3": {"commit": "0123456789abcdef0123"}}}


def test_scope_for_one_repository(tmp_path, checkout):
    path = write_records(tmp_path / "r.jsonl", RECORDS, CONTEXT)
    result = openwiki.run([path], "p3", str(checkout))
    assert result["types"] == {"inScope": 5, "listed": 3, "found": 3, "compiler-generated": 1, "generated": 1, "nuget": 0}
    assert result["files"] == 3 and result["directories"] == [] and result["warnings"] == []
    assert result["excluded"] == {"otherRepositories": {"radiant": 1}, "external": 1}
    ignore = (checkout / ".openwikiignore").read_text(encoding="utf-8").splitlines()
    assert ignore[1:-1] == openwiki.chain(["src/Billing/Orders/Order.cs", "src/Billing/Orders/OrderLine.cs", "src/Pay/Payment.cs"])
    brief = (checkout / "openwiki" / "INSTRUCTIONS.md").read_text(encoding="utf-8")
    assert "Document the 3 types listed below from the `p3` repository" in brief
    assert "### src/Billing/\n\n#### Billing.Orders\n\n- `Billing.Orders.Order` (class): `src/Billing/Orders/Order.cs`\n" in brief
    assert "### src/Pay/" in brief and "<>c" not in brief and "Weaved" not in brief and "Radiant" not in brief
    assert "Not listed: 1 compiler-generated types (closures, state machines; their owners' files are open) and 1 generated types" in brief
    assert "such as `src/Billing/**/*`" in brief
    assert "## External dependencies (NuGet)" in brief and "- `Contoso.Money`" in brief
    assert "- `r.jsonl`, store view-abc, graph measurement-database, commit 0123456789ab, exported 2026-10-13T12:00:00Z" in brief
    assert "directory-prefixed pattern" in brief


def test_dry_run_writes_nothing_and_returns_the_text(tmp_path, checkout):
    path = write_records(tmp_path / "r.jsonl", RECORDS)
    result = openwiki.run([path], "p3", str(checkout), dry_run=True)
    assert not (checkout / ".openwikiignore").exists() and not (checkout / "openwiki").exists()
    assert result["ignore"]["text"].startswith("# BEGIN") and result["brief"]["text"].startswith("<!-- BEGIN")
    openwiki.run([path], "p3", str(checkout))
    assert (checkout / ".openwikiignore").read_text(encoding="utf-8") == result["ignore"]["text"]


def test_user_exclusions_after_the_block_are_kept(tmp_path, checkout):
    (checkout / ".openwikiignore").write_text("secrets/\n", encoding="utf-8")
    (checkout / "openwiki").mkdir()
    (checkout / "openwiki" / "INSTRUCTIONS.md").write_text("Write in British English.\n", encoding="utf-8")
    path = write_records(tmp_path / "r.jsonl", RECORDS)
    openwiki.run([path], "p3", str(checkout))
    openwiki.run([path], "p3", str(checkout))
    ignore = (checkout / ".openwikiignore").read_text(encoding="utf-8")
    assert ignore.endswith(f"# {openwiki.END}\nsecrets/\n") and ignore.count(openwiki.BEGIN) == 1
    assert (checkout / "openwiki" / "INSTRUCTIONS.md").read_text(encoding="utf-8").endswith("\n\nWrite in British English.\n")


def test_concatenated_exports_equal_separate_exports_merged(tmp_path, checkout):
    a, b = RECORDS[:3], RECORDS[2:]
    one = openwiki.run([write_records(tmp_path / "a.jsonl", a), write_records(tmp_path / "b.json", b, fmt="json")], "p3", str(checkout), dry_run=True)
    both = openwiki.run([write_records(tmp_path / "ab.jsonl", a + b)], "p3", str(checkout), dry_run=True)
    assert one["duplicates"] == both["duplicates"] == 1
    assert one["ignore"]["text"] == both["ignore"]["text"] and one["brief"]["text"] == both["brief"]["text"]


def test_duplicates_merge_files_and_best_status(tmp_path, checkout):
    rows = [rec("Billing.P", ["src/Billing/Orders/Order.cs"]), rec("Billing.P", ["src/Billing/Orders/OrderLine.cs"], status="generated")]
    merged, duplicates = openwiki.merge(rows)
    assert duplicates == 1 and merged[0]["files"] == ["src/Billing/Orders/Order.cs", "src/Billing/Orders/OrderLine.cs"]
    assert merged[0]["locationStatus"] == "found"


def test_brief_cap_lists_namespaces(tmp_path, checkout):
    path = write_records(tmp_path / "r.jsonl", RECORDS)
    result = openwiki.run([path], "p3", str(checkout), max_listed=2, dry_run=True)
    text = result["brief"]["text"]
    assert result["brief"]["summarized"] and [w["code"] for w in result["warnings"]] == ["OPENWIKI_BRIEF_SUMMARIZED"]
    assert "## Namespaces" in text and "- `Billing.Orders`: 2 types" in text and "- `Billing.Pay`: 1 types" in text
    assert "OrderLine.cs" not in text
    assert "!/src/Billing/Orders/OrderLine.cs" in result["ignore"]["text"]  # the cap shortens the advice, not the scope


def test_fallback_directories_missing_files_and_global_namespace(tmp_path, checkout):
    rows = [rec("Billing.Orders.Order", ["src/Billing/Orders/Order.cs"]), rec("NoFiles", [], dirs=["src/Pay/"], namespace=""),
            rec("Billing.Gone", ["src/Billing/Gone.cs"])]
    result = openwiki.run([write_records(tmp_path / "r.jsonl", rows)], None, str(checkout), dry_run=True)
    assert result["repository"] == "p3" and result["directories"] == ["src/Pay/"]
    assert {w["code"]: w for w in result["warnings"]}["OPENWIKI_DIRECTORY_FALLBACK"]["directories"] == ["src/Pay/"]
    assert {w["code"]: w for w in result["warnings"]}["OPENWIKI_FILE_MISSING"]["files"] == ["src/Billing/Gone.cs"]
    assert "!/src/Pay/" in result["ignore"]["text"] and "#### (global)" in result["brief"]["text"]


def test_repo_root_from_the_context_sidecar(tmp_path, checkout):
    context = {**CONTEXT, "repositories": {"p3": {"repository": "D:/elsewhere", "checkout": str(checkout), "commit": "c"}}}
    result = openwiki.run([write_records(tmp_path / "r.jsonl", RECORDS, context)], "p3", None, dry_run=True)
    assert result["repoRoot"] == str(checkout)


@pytest.mark.parametrize("rows, repository, root, code", [
    (RECORDS, None, "ok", "OPENWIKI_REPOSITORY_REQUIRED"),
    (RECORDS, "nope", "ok", "OPENWIKI_REPOSITORY_EMPTY"),
    (RECORDS, "p3", None, "OPENWIKI_REPO_ROOT_REQUIRED"),
    (RECORDS, "p3", "missing", "OPENWIKI_REPO_ROOT_MISSING"),
    ([{"name": "X"}], "p3", "ok", "OPENWIKI_RECORDS_INVALID"),
    ([rec("A", ["src/*.cs"])], "p3", "ok", "OPENWIKI_PATH_UNSUPPORTED"),
])
def test_errors(tmp_path, checkout, rows, repository, root, code):
    root_arg = {"ok": str(checkout), "missing": str(tmp_path / "missing"), None: None}[root]
    with pytest.raises(RgError) as info:
        openwiki.run([write_records(tmp_path / "r.jsonl", rows)], repository, root_arg, dry_run=True)
    assert codes(info) == [code]


def test_unreadable_and_non_json_record_files(tmp_path, checkout):
    with pytest.raises(RgError) as info:
        openwiki.run([str(tmp_path / "none.jsonl")], "p3", str(checkout))
    assert codes(info) == ["OPENWIKI_RECORDS_NOT_FOUND"]
    (tmp_path / "bad.jsonl").write_text("{\n")
    with pytest.raises(RgError) as info:
        openwiki.run([str(tmp_path / "bad.jsonl")], "p3", str(checkout))
    assert codes(info) == ["OPENWIKI_RECORDS_INVALID"]


def test_a_root_project_is_never_opened(tmp_path, checkout):
    rows = [rec("App.Root", dirs=("./",), namespace="App"), rec("App.Order", files=["src/Pay/Payment.cs"], namespace="App")]
    result = openwiki.run([write_records(tmp_path / "r.jsonl", rows)], "p3", str(checkout), dry_run=True)
    assert [w["code"] for w in result["warnings"]] == ["OPENWIKI_ROOT_PROJECT"] and result["warnings"][0]["types"] == ["App.Root"]
    assert result["ignore"]["text"].splitlines()[1:-1] == ["*", "!/openwiki/", "!/src/", "/src/*", "!/src/Pay/", "/src/Pay/*",
                                                           "!/src/Pay/Payment.cs"]
    rows = [rec("Root.Program", files=["Program.cs"], dirs=("./",), namespace="Root"), rows[1]]
    brief = openwiki.run([write_records(tmp_path / "r2.jsonl", rows)], "p3", str(checkout), dry_run=True)["brief"]["text"]
    assert "### (repository root)" in brief and "such as `src/Billing/**/*`" in brief and "./" not in brief


def test_non_utf8_inputs_fail_cleanly(tmp_path, checkout):
    bad = tmp_path / "bad.jsonl"
    bad.write_bytes(b"\xff\xfe{")
    with pytest.raises(RgError) as info:
        openwiki.run([str(bad)], "p3", str(checkout))
    assert codes(info) == ["OPENWIKI_RECORDS_INVALID"]
    good = write_records(tmp_path / "r.jsonl", RECORDS)
    (tmp_path / "r.context.json").write_bytes(b"\xff")  # an unreadable sidecar only loses provenance
    (checkout / ".openwikiignore").write_bytes(b"secrets/\n\xff\n")
    with pytest.raises(RgError) as info:
        openwiki.run([good], "p3", str(checkout))
    assert codes(info) == ["OPENWIKI_FILE_UNREADABLE"]


def test_cli(tmp_path, checkout):
    path = write_records(tmp_path / "r.jsonl", RECORDS)
    proc = subprocess.run([sys.executable, str(SCRIPTS / "rg.py"), "openwiki-scope", "--records", path, "--repository", "p3",
                           "--repo-root", str(checkout), "--dry-run"], capture_output=True, text=True, encoding="utf-8")
    result = json.loads(proc.stdout)
    assert proc.returncode == 0 and result["type"] == "openwiki-scope" and result["dryRun"], result
    proc = subprocess.run([sys.executable, str(SCRIPTS / "rg.py"), "openwiki-scope", "--records", path, "--repo-root", str(checkout)],
                          capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 1 and json.loads(proc.stdout)["errors"][0]["code"] == "OPENWIKI_REPOSITORY_REQUIRED"


# ---- OpenWiki's own matcher -----------------------------------------------------------------


def _openwiki_ignore_js() -> Path | None:
    npm = shutil.which("npm")
    if shutil.which("node") is None or npm is None or shutil.which("openwiki") is None:
        return None
    root = subprocess.run([npm, "root", "-g"], capture_output=True, text=True).stdout.strip()
    path = Path(root) / "openwiki" / "dist" / "agent" / "openwiki-ignore.js"
    return path if path.is_file() else None


OPENWIKI_IGNORE_JS = _openwiki_ignore_js()
requires_openwiki = pytest.mark.skipif(OPENWIKI_IGNORE_JS is None, reason="needs node and a global openwiki install")

PROBE = """
import { OpenWikiIgnore } from %s;
let input = "";
for await (const chunk of process.stdin) input += chunk;
const { text, probes } = JSON.parse(input);
const ignore = OpenWikiIgnore.parse(text);
console.log(JSON.stringify(probes.map(([p, dir]) => ignore.ignores(p, dir))));
"""


@requires_openwiki
def test_chain_against_openwiki_matcher(tmp_path):
    script = tmp_path / "probe.mjs"
    script.write_text(PROBE % json.dumps(OPENWIKI_IGNORE_JS.as_uri()), encoding="utf-8")
    body = openwiki.chain(["src/Billing/Orders/Order.cs", "src/Billing/Orders/OrderLine.cs", "src/Billing/Payments/", "Top.cs",
                           "Common/y.cs", "common/x.cs", "ς/i.cs", "Σ/ß.cs", "Straße/a.cs", "STRASSE/b.cs"])
    text = openwiki.merge_block("secrets/\n", body, False, "f")
    allowed = [("src", True), ("src/Billing", True), ("src/Billing/Orders", True), ("src/Billing/Orders/Order.cs", False),
               ("SRC/billing/orders/order.cs", False), ("src/Billing/Orders/OrderLine.cs", False), ("src/Billing/Payments", True),
               ("src/Billing/Payments/Deep/Pay.cs", False), ("Top.cs", False), ("openwiki", True), ("openwiki/x.md", False),
               ("Common", True), ("common", True), ("Common/y.cs", False), ("common/x.cs", False),
               ("ς/i.cs", False), ("Σ/ß.cs", False), ("Straße/a.cs", False), ("STRASSE/b.cs", False)]
    ignored = [("src/Billing/Orders/OrderMapper.cs", False), ("src/Billing/Other", True), ("src/Billing/Other/X.cs", False),
               ("src/Other.cs", False), ("Common/z.cs", False), ("lib", True), ("lib/A.cs", False), ("README.md", False),
               ("src/Billing/Payments/secrets", True), ("src/Billing/Payments/secrets/key.txt", False)]
    probes = allowed + ignored
    proc = subprocess.run(["node", str(script)], input=json.dumps({"text": text, "probes": probes}), capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    verdicts = dict(zip([p for p, _ in probes], json.loads(proc.stdout)))
    assert [p for p, _ in allowed if verdicts[p]] == []
    assert [p for p, _ in ignored if not verdicts[p]] == []
