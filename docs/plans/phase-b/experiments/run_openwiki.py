"""B0 experiments 4-6: one OpenWiki run on a fresh clone with a generated scope, measured.

Clones the repository at the manifest commit, builds the scope (scope_build.py), runs `openwiki code --init -p`
with the file-system trace (fs_trace.mjs) and the usage proxy (usage_proxy.py), then reports reads outside the
scope, tool calls, tokens, time, and how many briefed types the generated wiki mentions.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def codex_env() -> dict[str, str]:
    """OpenWiki's openai-chatgpt credentials from the Codex CLI login. The expiry comes from the access token, so
    OpenWiki refreshes (and rotates the Codex CLI's refresh token) only when the token is about to lapse."""
    tokens = json.loads((Path.home() / ".codex" / "auth.json").read_text(encoding="utf-8"))["tokens"]
    payload = tokens["access_token"].split(".")[1]
    claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    return {"OPENAI_CHATGPT_ACCESS_TOKEN": tokens["access_token"], "OPENAI_CHATGPT_REFRESH_TOKEN": tokens["refresh_token"],
            "OPENAI_CHATGPT_ACCOUNT_ID": tokens["account_id"], "OPENAI_CHATGPT_EXPIRES_AT": str(claims["exp"] * 1000)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--source", required=True, help="local repository to clone")
    ap.add_argument("--commit", required=True)
    ap.add_argument("--scan", required=True)
    ap.add_argument("--repository", required=True)
    ap.add_argument("--count", type=int, required=True)
    ap.add_argument("--namespace-prefix", default="")
    ap.add_argument("--mode", choices=["files", "dirs", "brief-only"], required=True)
    ap.add_argument("--jsonl", action="store_true")
    ap.add_argument("--timeout", type=int, default=3600)
    ap.add_argument("--provider", choices=["anthropic", "openai-chatgpt"], default="anthropic",
                    help="openai-chatgpt uses the Codex CLI's ChatGPT login (~/.codex/auth.json)")
    ap.add_argument("--model", help="OPENWIKI_MODEL_ID, e.g. gpt-6-luna")
    a = ap.parse_args()

    work = Path(a.work)
    repo = work / a.name
    if repo.exists():
        shutil.rmtree(repo, onerror=lambda f, p, _: (os.chmod(p, 0o700), f(p)))
    subprocess.run(["git", "clone", "-q", "--no-checkout", a.source, str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "checkout", "-q", "-b", "openwiki-b0", a.commit], check=True)
    scope_cmd = [sys.executable, str(HERE / "scope_build.py"), "--scan", a.scan, "--repository", a.repository, "--count", str(a.count),
                 "--namespace-prefix", a.namespace_prefix, "--mode", a.mode, "--repo-root", str(repo)] + (["--jsonl"] if a.jsonl else [])
    print(subprocess.run(scope_cmd, check=True, capture_output=True, text=True).stdout.strip(), flush=True)
    scope = json.loads((work / f"{a.name}.scope.json").read_text(encoding="utf-8"))

    trace, usage = work / f"{a.name}.trace.jsonl", work / f"{a.name}.usage.jsonl"
    for p in (trace, usage):
        p.unlink(missing_ok=True)
    env = dict(os.environ, OPENWIKI_TRACE_ROOT=str(repo), OPENWIKI_TRACE_FILE=str(trace), OPENWIKI_TELEMETRY_DISABLED="1",
               OPENWIKI_PROVIDER=a.provider, NODE_OPTIONS=f"--import {(HERE / 'fs_trace.mjs').as_uri()}")
    if a.model:
        env["OPENWIKI_MODEL_ID"] = a.model
    proxy = None
    if a.provider == "anthropic":
        port = free_port()
        proxy = subprocess.Popen([sys.executable, str(HERE / "usage_proxy.py"), "--port", str(port), "--log", str(usage)])
        time.sleep(1.5)
        env["ANTHROPIC_BASE_URL"] = f"http://127.0.0.1:{port}"
    else:
        # The Codex backend URL is fixed, so usage is logged by a fetch hook instead of the proxy.
        env.update(codex_env(), OPENWIKI_USAGE_FILE=str(usage))
        env["NODE_OPTIONS"] += f" --import {(HERE / 'codex_usage.mjs').as_uri()}"
    openwiki = shutil.which("openwiki") or "openwiki"
    started = time.monotonic()
    try:
        done = subprocess.run([openwiki, "code", "--init", "-p"], cwd=repo, env=env, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=a.timeout)
        exit_code, stdout, stderr = done.returncode, done.stdout, done.stderr
    except subprocess.TimeoutExpired as exc:
        exit_code, stdout, stderr = "timeout", str(exc.stdout or ""), str(exc.stderr or "")
    seconds = round(time.monotonic() - started)
    if proxy:
        proxy.terminate()
    (work / f"{a.name}.out.txt").write_text(stdout, encoding="utf-8")
    (work / f"{a.name}.err.txt").write_text(stderr, encoding="utf-8")

    in_scope = set(scope["files"])
    ancestors = {"/".join(f.split("/")[:i]) for f in in_scope for i in range(1, f.count("/") + 1)} | {""}
    allowed_dirs = {f.rsplit("/", 1)[0] for f in in_scope} if a.mode == "dirs" else set()
    # The agent's read_file shows up as `open`; OpenWiki's own repository scan uses `readFile` on nearly every file.
    reads_outside: set[str] = set()
    scan_reads_outside: set[str] = set()
    listed_outside: set[str] = set()
    for line in trace.read_text(encoding="utf-8").splitlines() if trace.exists() else []:
        e = json.loads(line)
        p = e.get("path")
        if p is None or e["op"].startswith(("write:", "spawn")):
            continue
        if p.startswith((".git/", "openwiki/")) or p in (".git", "openwiki", ".openwikiignore", ".gitignore", "AGENTS.md", "CLAUDE.md", "README.md", ".github/workflows/openwiki-update.yml", ".github", ".github/workflows"):
            continue
        if p in in_scope or p in ancestors or any(p == d or p.startswith(d + "/") for d in allowed_dirs):
            continue
        if e["op"] in ("open", "openSync", "createReadStream"):
            reads_outside.add(p)
        elif e["op"] in ("readFile", "readFileSync"):
            scan_reads_outside.add(p)
        else:
            listed_outside.add(p)

    calls, tools, totals = 0, {}, {}
    model_paths: set[str] = set()
    for line in usage.read_text(encoding="utf-8").splitlines() if usage.exists() else []:
        e = json.loads(line)
        calls += 1
        for k, v in e["usage"].items():
            totals[k] = totals.get(k, 0) + v
        for t in e["tools"]:
            tools[t["name"]] = tools.get(t["name"], 0) + 1
            inp = t["input"] if isinstance(t["input"], dict) else {}
            for key in ("file_path", "path", "pattern"):
                if isinstance(inp.get(key), str):
                    model_paths.add(inp[key])

    wiki = sorted((repo / "openwiki").rglob("*.md")) if (repo / "openwiki").is_dir() else []
    pages = [p for p in wiki if p.name != "INSTRUCTIONS.md"]
    text = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in pages)
    covered = [t for t in scope["types"] if re.search(rf"\b{re.escape(t.rsplit('.', 1)[-1].split('<')[0])}\b", text)]
    cited = sorted(set(re.findall(r"[\w./-]+\.(?:cs|vb|jsonl)\b", text)))
    result = {
        "type": "openwiki-run", "name": a.name, "provider": a.provider, "model": a.model, "mode": a.mode, "jsonl": a.jsonl, "types": len(scope["types"]), "files": len(in_scope),
        "exit": exit_code, "seconds": seconds, "apiCalls": calls, "usage": totals, "tools": tools,
        "readsOutside": sorted(reads_outside), "scanReadsOutside": len(scan_reads_outside), "listedOutside": len(listed_outside), "listedOutsideExamples": sorted(listed_outside)[:15],
        "pages": len(pages), "wikiChars": len(text), "typesCovered": len(covered), "typesMissing": sorted(set(scope["types"]) - set(covered)),
        "citedFiles": [c for c in cited if c not in in_scope][:40], "citedInScope": len([c for c in cited if c in in_scope]),
        "citesJsonl": any(c.endswith(".jsonl") for c in cited), "modelPathsSample": sorted(model_paths)[:40],
    }
    (work / f"{a.name}.result.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k not in ("modelPathsSample", "citedFiles", "listedOutsideExamples")}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
