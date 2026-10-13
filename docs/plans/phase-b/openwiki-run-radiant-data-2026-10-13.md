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
| Agent reads outside scope | none: every `read_file` was a scope file, except OpenWiki's built-in `/skills/mermaid-diagrams/SKILL.md` |
| Output | 22 files under `openwiki/`: 7 content pages, 5 indexes (`index.md` and one per section), the brief, 7 `.claims/*.json`, `.page-manifest.json`, `.last-update.json` |
| Size | 545 lines of wiki, excluding the brief |
| Coverage | 59 of 272 distinct type names appear in the pages; 61 distinct source files are cited, and every one exists |

The pages are `architecture/data-model`, `integrations/native-abi`, `testing/validation`,
`workflows/capture-results`, `workflows/python-sdk`, `workflows/serialization` and `quickstart`.

Findings:

1. **Enforcement holds at model level.** The agent probed outside the scope (`ls /tests`, `glob **/*python*test*`,
   `grep test_sdk_surface`) and got nothing back. The pages name `tests/test_sdk_surface.py` and
   `scripts/generate_python_sdk.py` only because in-scope files (`FILE_CONTRACT.md`, the SDK README) mention them.
2. **The process reads everything.** `fs_trace.mjs` shows OpenWiki's own code (not the agent) opening 827 distinct
   paths, nearly every file in the repository, including `.claude/` and `.just/`. That is its repository scan; the
   ignore file limits only what the model can request. Content outside the scope does not reach the provider
   through tool calls, but a scope is not a guarantee that no file is read on the machine.
3. **Coverage is thematic, not per type.** The wiki explains 59 of the 272 type names in 7 workflow pages. The
   brief lists every type, but OpenWiki plans pages by topic. Per-type coverage would need the brief to ask for it.
4. **Side effects of `--init`.** OpenWiki adds an `OPENWIKI` block to `AGENTS.md` and `CLAUDE.md`, and writes
   `.github/workflows/openwiki-update.yml`: a daily `--update` job whose `openai-chatgpt` login cannot run
   unattended. The workflow was not committed.
5. **Cost.** About 1.25 M input tokens for 186 C# files (about 26,700 lines) plus 9,800 lines of Python: roughly 34
   input tokens per source line, 20 % cached. A P3-sized scope (4,807 files) would be in the order of 30 M input
   tokens, so runs there should stay scoped to one project or namespace.

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

`run_openwiki.py --provider openai-chatgpt --model gpt-6-luna` does the same for the clone-based P3 runs.
