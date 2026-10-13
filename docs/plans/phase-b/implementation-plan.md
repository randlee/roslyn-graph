# Phase B implementation plan

Design: [README.md](README.md). The sprints are one stack of PRs on `integrate/phase-b`, which lands on `develop`
when the phase is done. Python only, standard library only, every
command returns one JSON object, and tests run on ubuntu, macos and windows in CI.

## B0: Experiments (no product code)

Answer the questions the design depends on, on a real P3 checkout. Throwaway scripts live under
`docs/plans/phase-b/experiments/` and are not part of `tools/rg`. Results go to `reference-run-<date>.md` with
commands, versions and numbers.

1. **Compile items.** Run `dotnet msbuild -getItem:Compile` on every P3 `.csproj` and `.vbproj` in the TT3X
   build (`Debug-Net10-TT3X`). Record failures, non-SDK projects that need Visual Studio MSBuild, run time, and
   linked files outside the project directory.
2. **Declaration-scan accuracy.** Prototype the C# and VB scanners. Take the types of the saved
   `measurement-database` graph and a random sample of at least 300 P3 types. Report found, multiple-file
   (partial), generated and not-found, and examine every not-found by hand. Check that full names match
   `dt:fullName` (`TypeNameFormat`: nesting, generic arity, `global::`).
3. **Ignore chain at file level.** Already passed with the README's example (2026-10-13). Repeat it with the
   chain generated for the real B0 scope.
4. **Scope adherence.** Run `openwiki code --init` three times on the same small scope: (a) file-level ignore with
   brief, (b) project-directory ignore with brief, (c) brief only. Measure reads outside the scoped types (from the
   run log), and how many briefed types the wiki covers.
5. **JSONL in the repository.** Run (a) again with the JSONL committed beside the brief, re-opened in the ignore
   file and named in the brief. Compare coverage, and check whether Grounded Claims cite the JSONL instead of code.
6. **Cost.** Time and tokens per run for 10, 50 and 200 types, to size how much one run can cover.

Exit: README amended where the results disagree with it. Open decisions 1-3 settled.

**Done 2026-10-13**: [reference-run-2026-10-13.md](reference-run-2026-10-13.md). Experiments 1-3 and the tool level
of 4 are complete. The model-level parts of 4-6 are blocked by a rejected API key. Their harness
(`experiments/run_openwiki.py`) is ready and they move to the acceptance checks. Changes the results made to the
design: manifest-based project resolution, MSBuild with solution context and `-t:AddImplicitDefineConstants`,
Roslyn declarations in the extractor instead of a Python lexer, and the `compiler-generated` / `generated`
statuses.

## B1: `records` command (store fields only)

- `records.py`: load `--graph` (`.nt` + `.context.json`) or `--selection` (`roslyn-graph-selection/2`); resolve
  the store; map logical IRIs to physical types; apply the filters; load and check the schema; query only the bound
  registry fields; validate the records; write JSONL or JSON sorted by `fullName`; write the context sidecar.
- `rg.py records` with `--graph | --selection`, `--manifest`, the filter flags, `--schema`, `--output`, `--format`,
  `--timeout`.
- The test schema lives with the tests. `files` and `locationStatus` are registered but fail with
  `RECORDS_FIELD_UNAVAILABLE` until B2.

Tests (`test_records.py`):

- Schema loader: each unsupported keyword, missing or unknown `x-rg-field`, cardinality mismatch, and several
  problems reported together.
- Validator: each supported keyword passing and failing.
- Filters: AND/OR semantics, `--exclude` last, per-filter counts, `RECORDS_EMPTY` hint.
- Inputs: graph with and without context, selection, `--manifest` override, unknown type name.
- Output: deterministic order and key order, JSONL vs JSON, sidecar contents including the schema SHA-256.
- `requires_oxigraph`: a small store with project provenance (extend the fixture of
  `test_type_to_project_provenance_query_returns_repo_and_relative_path`). The test exports every store field and
  covers a logical type with two physical versions in two projects.
- The registry table in `reference/records.md` matches the code.

## B2: Source locator

- Extractor (`RoslynToRdf`):
  - `DeclarationIndexer` in Core: parse files with the given language version and preprocessor symbols, build a
    reference-free compilation, and list every source-declared named type (`TypeNameFormat` name, kind, file, line;
    one entry per declaring file).
  - `roslyn2rdf declarations --request <file.json> --output <file.json>`: request
    `{language, langVersion, preprocessorSymbols, files}`, response `{type: "declarations", types: [...]}`.
- `sources.py`:
  - project resolution from the type's named graph and the component manifests, with the v2 profile-root rule, and
    the v3 provenance triples as a cross-check;
  - checkout check against the manifest commit and dirty hash (`SOURCE_CHECKOUT_DRIFT`, `--allow-drift`,
    `--repo-root ID=PATH`);
  - MSBuild Compile items, `DefineConstants` and `LangVersion` with the build properties, solution context and
    `-t:AddImplicitDefineConstants` (`ROSLYN_GRAPH_MSBUILD`, `MSBUILD_FAILED` carrying MSBuild's output);
  - the `declarations` call through `extractor.resolve()` (`DECLARATIONS_UNSUPPORTED` when the installed extractor
    predates the command, with the update hint);
  - statuses `found`, `compiler-generated` (owner's files), `generated`, `nuget`;
  - source-index cache under `<data-root>/.roslyn-graph/cache/source-index/`.
- `records` gains `files` and `locationStatus`, and the `locations` summary in its result.

Tests:

- C# (`DeclarationIndexerTests`), table-driven:
  - block and file-scoped namespaces, nested and generic types (`Outer<T>.Inner<U>`), `partial` across files,
    `record`, `record struct`, delegates, enums;
  - `#if` with and without the symbol, `#elif`, nested `#if`, braces inside inactive branches (the B0
    `CameraExtensions.cs` case);
  - VB: `Namespace`, `Partial Class`, `Module`, `#If ... Then`;
  - names equal to what the extractor emits for the same source compiled as an assembly.
- Python (`test_sources.py`):
  - project resolution for v2 (profile-root-relative) and v3 manifests;
  - MSBuild argument construction: build properties, solution context, the implicit-symbols target;
  - checkout check: matching, other commit, dirty, and `--allow-drift`;
  - cache: hit, miss on a different commit, never written for a drifted checkout;
  - `locationStatus` for every value, with the owner rule for compiler-generated names;
  - `requires_dotnet` (skipped without the SDK and a built extractor): a fixture SDK project with a linked file
    outside its directory, a `Compile Remove`, a `Condition`ed item and a `#if` on a custom constant set in an
    imported `$(SolutionDir)` file. The Compile items, symbols and resulting `files` are exactly right.

## B3: OpenWiki adapter

- `schemas/openwiki-type.schema.json` in the explore skill.
- `openwiki.py`: ignore-chain generator (pure function), managed-block merge for `.openwikiignore` and
  `INSTRUCTIONS.md`, brief writer with `--max-listed-types`.
- `rg.py openwiki-scope` with `--records` (repeatable), `--repository`, `--repo-root`, `--max-listed-types`,
  `--dry-run`.

Tests (`test_openwiki.py`):

- Chain: one file, sibling files, a file inside an opened directory (dropped), fallback directories, a deep path,
  the `openwiki/` re-include, and rejected glob characters.
- **Against the real matcher:** marked `requires_openwiki` (skipped when `node` or a global `openwiki` is
  missing). A small Node script imports `openwiki/dist/agent/openwiki-ignore.js`. For a generated chain, it checks
  that opened paths and their ancestors are allowed, siblings are ignored, and `openwiki/x.md` is writable.
- Managed blocks: create, replace in place, keep user lines before and after, and keep the user's exclusions in
  force inside opened paths.
- Brief: grouping, files, NuGet dependency list, cap with namespace summary and warning.
- Records: duplicates removed across files, other repositories counted, files that fail the schema rejected.

## B4: Skill integration

- `workflows/export-records.md` covers graph or explorer selection -> `records` -> `openwiki-scope` -> run OpenWiki.
- `reference/records.md` and `reference/openwiki-scope.md`. `SKILL.md` gets one router line.
- `python scripts/check_plugin_sync.py --fix`, then confirm CI's sync check passes.

## Acceptance checks

- With a working model key, B0 experiments 4-6 at model level (`experiments/run_openwiki.py`): reads outside the
  scope (expected none), types covered, and time and tokens for 10, 50 and 200 types.

- `records` with `--schema openwiki-type` on the saved `measurement-database` graph (`p3_with_current_radiant`,
  logical) writes one valid record per drawn type.
  - Running it again gives a byte-identical file and a cache hit for every project.
  - At least the B0-measured share of source types is `found`.
- An explorer selection with namespaces hidden exports only the drawn types.
- Concatenating two JSONL exports and running `openwiki-scope` on them gives the same result as running it on
  each file separately and merging.
- In the P3 repository, `openwiki-scope` followed by `openwiki code --init` produces a wiki covering the briefed
  types, and the run log shows no reads outside the opened paths.
- Every error path returns `{"type": "error"}` with a code, message and hint, and exits with status 1.

## Out of scope

- Writing source locations into stores (`rg:declaredIn`); revisit after B0 and B2.
- Record kinds other than `type` (`x-rg-record` reserves the name for members).
- Running OpenWiki from `rg.py`.
