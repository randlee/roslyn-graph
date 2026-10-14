# Phase B, model-level OpenWiki run: Radiant.Data (2026-10-13)

The first model-level run of the Phase B pipeline (experiment 4 at model level, plus cost). It replaces the P3
XCore run, which was blocked on the Anthropic key (see [reference-run-2026-10-13.md](reference-run-2026-10-13.md)).
The target is small on purpose: the Radiant.Data NuGet package and its published Python SDK.

## Setup

| Input | Value |
|---|---|
| Repository | `Radiant-Vision-Systems/data`, a worktree on `docs/openwiki-radiant-data` cut from `develop` (`8b7c1116`) |
| Profile | `data_src` in `workspace.toml`: `Radiant.Data.sln`, `Debug`, `net10.0`, the four `src/` projects only |
| Store | `generate` 18 s; 335 files, 46 MB (four project artifacts and the solution view) |
| Records | 282 types (6 duplicates merged in the scope: 276), 186 files; `records` about 1 s, no drift |
| Scope | `openwiki-scope --mode files`: 258 ignore rules, no warnings |
| Hand-added | Python SDK rules after the managed block (`bindings/python/sdk/radiant_data/`, README, FILE_CONTRACT, pyproject; no tests) and a brief section outside the managed block |
| Provider | OpenWiki 0.7.2, `openai-chatgpt` (Codex CLI ChatGPT login), model `gpt-6-luna` |
| Harness | `fs_trace.mjs` and `codex_usage.mjs` loaded through `NODE_OPTIONS`; `openwiki code --init -p` |

The type export filters out constructed generics (`FILTER NOT EXISTS { ?t dt:genericDefinition ?d }`); without it
`records` reports `RECORDS_TYPE_NOT_IN_STORE` for 34 of them.

The 9 `src/` `.cs` files outside the scope are all correct: `AssemblyInfo.cs` (no types), six `*.netstandard.cs`
partials (not compiled for `net10.0`), one file under `#if false` and one comment-only file.

OpenWiki's own matcher, run over `git ls-files` in the worktree, leaves 198 of 823 files readable: the 186 `.cs`
files, 11 SDK files and `openwiki/INSTRUCTIONS.md`.

## Results

| Measure | Result |
|---|---|
| Time | 398 s wall clock |
| API calls | 101, all `200`, all `gpt-6-luna` |
| Tokens | 1,248,648 input (253,952 cached), 20,483 output, 200 reasoning |
| Tool calls | `read_file` 91, `ls` 58, `grep` 10, `glob` 8, `submit_page` 8, `write_file` 7, `edit_file` 1, `submit_plan` 1 |
| Agent reads outside scope | none served. Of 91 `read_file` calls, 77 read scope files, 7 read OpenWiki's built-in `/skills/mermaid-diagrams/SKILL.md`, and 7 asked for an ignored path (one SDK test, six non-existent `/repo/src/...` paths) and were refused |
| Output | 22 files under `openwiki/`: 7 content pages, 5 indexes (`index.md` and one per section), the brief, 7 `.claims/*.json`, `.page-manifest.json`, `.last-update.json` |
| Size | 545 lines of wiki, excluding the brief |
| Coverage | 63 of 270 distinct short type names (67 of 276 types) appear in the pages; 61 distinct source files are cited, and every one exists |

The pages are `architecture/data-model`, `integrations/native-abi`, `testing/validation`,
`workflows/capture-results`, `workflows/python-sdk`, `workflows/serialization` and `quickstart`.

Findings:

1. **Enforcement holds at model level.** The agent probed outside the scope (`ls /tests`, `glob **/*python*test*`,
   `grep test_sdk_surface`, `read_file /bindings/python/sdk/tests/test_sdk_surface.py`) and got nothing back. The
   pages name `tests/test_sdk_surface.py` and `scripts/generate_python_sdk.py` only because in-scope files
   (`FILE_CONTRACT.md`, the SDK README) mention them.
2. **`grep` reads ignored files, then filters.** `fs_trace.mjs` shows the OpenWiki process reading 827 distinct
   paths, 611 of them ignored (`tests/`, `reports/`, `schema-output/`, `.claude/`). Almost all of those reads follow
   the agent's `grep` calls: the grep tool reads files outside the scope and drops them from its results. The
   results are filtered (after `grep test_sdk_surface` over `/`, the next call's input grew by 69 tokens), so the
   content does not reach the provider. But the scope limits what the agent receives, not what the process reads.
   This belongs in the upstream report next to the `glob` defect.
3. **Coverage is thematic, not per type.** 63 of the 270 short type names appear in the 7 content pages. The
   brief lists every type, but OpenWiki plans pages by topic. Per-type coverage would need the brief to ask for it.
4. **Side effects of `--init`.** OpenWiki adds an `OPENWIKI` block to `AGENTS.md` and `CLAUDE.md`, and writes
   `.github/workflows/openwiki-update.yml`: a daily `--update` job whose `openai-chatgpt` login cannot run
   unattended. The workflow was not committed.
5. **Cost follows calls, not scope size.** About 1.25 M input tokens (20 % cached) over 101 calls, roughly 12 k of
   context per call, for 7 content pages. The agent read 46 distinct files of the 198 readable (186 C# files,
   26,085 lines; 9,690 lines of SDK Python). A larger scope costs more mainly through more pages and calls, so
   per-page cost (about 180 k input tokens) is the better estimate; a linear guess from line counts (about 30 M for
   P3's 4,807 files) is only an upper bound. Runs on P3 should still stay scoped to one project or namespace.

## Reproduce

```text
rg.py generate --workspace F:/_r2609/.roslyn-graph/workspace.toml --collection radiant_data
rg.py export --manifest <solution manifest.json> --output radiant-data-types.nt --query '<CONSTRUCT of dt:fullName and dt:typeKind, filter above>'
rg.py records --graph radiant-data-types.nt --schema openwiki-type --output radiant-data.jsonl
rg.py openwiki-scope --records radiant-data.jsonl --repository data --repo-root <worktree>
# append the SDK rules to .openwikiignore and the SDK section to openwiki/INSTRUCTIONS.md, then:
OPENWIKI_PROVIDER=openai-chatgpt OPENWIKI_MODEL_ID=gpt-6-luna OPENWIKI_CHATGPT_* (from ~/.codex/auth.json) \
    NODE_OPTIONS="--import fs_trace.mjs --import codex_usage.mjs" openwiki code --init -p
```

`run_openwiki.py --provider openai-chatgpt --model gpt-6-luna` does the same for the clone-based P3 runs. Its
`requestsOutside` lists `read_file` requests for files outside the scope, taken from the tool inputs;
`processReadsOutside` counts ignored files the process read (mostly the `grep` tool), which the agent did not receive.

The Codex login is shared: if OpenWiki refreshes the access token (it does so within 60 s of expiry), it rotates the
refresh token, and the Codex CLI's copy in `~/.codex/auth.json` can stop working until `codex login`. The harness passes the
real expiry, so a run started with a fresh login does not refresh.
