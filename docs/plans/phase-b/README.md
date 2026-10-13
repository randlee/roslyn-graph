# Phase B: Schema-driven record export from query graphs

Status: plan, 2026-10-13. B0 experiments done: [reference-run-2026-10-13.md](reference-run-2026-10-13.md). The design
below includes their results.

## Objective

Turn a completed query graph into a file of records: one JSON object per type, filtered, with the fields set by a
schema. Records can include the source files that declare each type. The first consumer is OpenWiki, which can
then document exactly the types a graph selected inside a very large codebase.

Two new `rg.py` subcommands:

| Command | Does |
|---|---|
| `records` | completed graph (+ filters) + schema -> JSON Lines records, with a provenance sidecar. Resolves source files on demand |
| `openwiki-scope` | records in the `openwiki-type` schema -> `.openwikiignore` and an `openwiki/INSTRUCTIONS.md` brief for one repository |

`records` knows nothing about OpenWiki. OpenWiki is one built-in schema plus one small adapter.

## How OpenWiki takes scope (verified against openwiki 0.7.2)

OpenWiki has **no structured input**. In code mode it reads only the repository's source and tests. Its
connectors, including Custom MCP, feed only the personal wiki; the one code-mode connector is LangSmith traces.
Code reviewed in the installed package (`dist/agent/openwiki-ignore.js`, `dist/agent/docs-only-backend.js`,
`README.md`) shows two inputs that set scope:

| Input | Strength |
|---|---|
| **`.openwikiignore`** at the repository root | **Hard.** Every `read_file`, `ls`, `glob`, `grep` and write is checked against it |
| **`openwiki/INSTRUCTIONS.md`**, the user-written brief | **Advisory.** Read for scope and priorities on every run. `--init` keeps it, and runs never rewrite it |

Ignore rules follow gitignore style: `*`, `**`, `?`, a leading `/` anchors the pattern, a trailing `/` makes it
directory-only, `!` negates, and the last matching rule wins. Matching is case-insensitive. Each path is checked on
its own. `ls` and `glob` **refuse an ignored directory** and drop ignored entries, so every ancestor of an opened
path has to be re-opened. Writes are checked too, so a deny-all file must re-open `/openwiki/`.

Consequences for this design:

- The type list in the brief is advice to an LLM. **Only the ignore file enforces scope, and it works on paths.**
  So the scope is only as precise as the paths: opening the declaring *files* enforces it, while opening whole
  *project directories* exposes everything else in those projects. That is why records carry source files.
- The record format is ours to choose. **JSONL is the default**, because output from several graphs can just be
  concatenated (the adapter removes duplicates by `name`). `--format json` writes one array instead.

## Source locations: resolved on export, not stored in the graph

Stores are built from assembly metadata, so they hold no source paths. Putting every type's files into the initial
scan would grow every artifact for a field that few exports need. Instead, `records` resolves files only for the
types it exports, and only when the schema asks for them:

1. **Locate the project.** A type's named graph (`GRAPH ?g`) is one component's `graphIri`. That component's
   manifest (solution `components`, view `overlayComponents`) gives the checkout (`origin.repository`), the commit
   (`origin.commit`, `dirtyHash`) and the build (`build.project`, `build.solution`, configuration, platform, target
   framework). Every current artifact is `assembly/v2`, which has no `rg:builtFromProject` triples (B0 finding 0), and
   its `build.project` is relative to the profile root: the project is `repository.parent / project` when that file
   exists, else `repository / project`. For v3 artifacts `rg:projectRepository` / `rg:projectRelativePath`
   (`5adfb5c`) give the same answer and are checked against the manifest.
2. **Check the checkout.** `gitinfo.repo_state` must report the manifest's commit, and no uncommitted changes when
   the manifest had none. Otherwise the paths may not match the store. That is an error (`SOURCE_CHECKOUT_DRIFT`)
   unless `--allow-drift`, which records the drift as a warning. `--repo-root ID=PATH` points at a checkout that
   has moved.
3. **List the compiled files and symbols.** Run
   `dotnet msbuild <project> -getItem:Compile -getProperty:DefineConstants -getProperty:LangVersion -t:AddImplicitDefineConstants`
   with the build's `Configuration`, `TargetFramework` and `Platform`, plus the solution context a solution build
   sets (`SolutionDir`, `SolutionPath`, `SolutionName`, `SolutionFileName`, `SolutionExt` for `build.solution`). It
   returns the exact Compile items, including files linked from outside the project directory, `Condition`s,
   `Compile Remove` and items added by targets, and the complete preprocessor symbols. Without the solution context
   P3 projects skip `$(SolutionDir)Common.targets` and lose every TT3 symbol; without the target the `NET*` symbols
   are missing. Both errors are silent, which is why B0 measured them. `-getItem` needs SDK 8+ (10.0.401 is installed
   here) or Visual Studio MSBuild 17.8+ for non-SDK projects. `ROSLYN_GRAPH_MSBUILD` selects the executable, as
   `ROSLYN_GRAPH_OXIGRAPH` does for Oxigraph. 59 P3 projects take 6.8 s with 4 jobs.
4. **Find the declarations with Roslyn.** The extractor gains a `declarations` command. It takes the language, the
   language version, the preprocessor symbols and the Compile items, parses each file with
   `CSharpParseOptions`/`VisualBasicParseOptions` (no MSBuild, no references, so it is fast), and returns every
   declared named type with file and line. Names use the extractor's own `TypeNameFormat`, so they match
   `dt:fullName` by construction. Inactive `#if` branches are disabled text to Roslyn, and a type declared in several
   files (`partial` / `Partial`) gets all of them. B0's lexer prototype found every source-declared type once the
   symbols were right. It stays an experiment script, because Roslyn covers VB and every C# rule without a second
   implementation.
5. **Cache.** Results are stored under `<data-root>/.roslyn-graph/cache/source-index/`, keyed by the SHA-256 of
   repository ID, commit, dirty hash, project path and effective build properties. A clean commit's index never
   changes, so later exports skip MSBuild and the scan. Drifted checkouts are never cached.

Each type gets `files` (repo-relative, forward slashes) and a `locationStatus`:

| `locationStatus` | Meaning | OpenWiki adapter |
|---|---|---|
| `found` | declared in one or more Compile items inside the repository | opens those files |
| `compiler-generated` | a name segment starts with `<` (closures, state machines, `<PrivateImplementationDetails>`); `files` are the enclosing named type's | opens those files; not listed in the brief |
| `generated` | declared in no Compile item inside the repository: source generators, weavers (Fody), `<Module>`, test-SDK entry points | opens nothing; counted in the brief and the result |
| `nuget` | no source project | opens nothing; listed as an external dependency |

In the `measurement-database` graph (929 physical types), 685 are `found`, 202 `compiler-generated`, 3 `generated`
and 39 `nuget`. Of the 803 store types that no Compile item declares, B0 checked all of them: 801 are generator or
compiler output, and the other 2 are the cases in the table above. So `generated` does not open the project
directory: that would expose a whole project for output that is not in it.

If this proves its worth, the same index could later be written into a derived store as triples (for example
`rg:declaredIn`), so SPARQL can use it. That is out of scope here; B0 measures cost and accuracy first.

## Input: a completed query graph

`records` accepts exactly one of:

1. `--graph <name>.nt`: output of `rg.py graph` or `rg.py export`. Its `<name>.context.json` sidecar names the
   store (`source.manifest`). Types are the subjects of `dt:fullName` triples.
2. `--selection <file>.json`: a `roslyn-graph-selection/2` payload from the explorer (**📋 Copy for Claude** or
   **⬇ JSON**). This is the interactive filter. The user hides namespaces or picks one type in the viewer, and the
   payload lists exactly the types that were drawn.

`--manifest` overrides the store when the input has no context. Errors: `RECORDS_INPUT` (none or both inputs),
`RECORDS_NO_STORE` (no context and no `--manifest`), `STORE_NOT_FOUND` (existing), `RECORDS_TYPE_NOT_IN_STORE` (a
listed name is not a component type of the store).

**Logical graphs.** A graph made with `logical = true` holds logical IRIs. `records` maps each logical type to its
physical types through the view's logical graph (`rg:logicalType`, the reverse of `explore.logical_map`). Fields
that can differ across versions (assemblies, projects, files) are lists, so a logical type keeps every location.

## Filtering

Filters narrow the graph's types before any field is queried or any file is scanned. A repeated flag ORs its
values. Different flags AND together. `--exclude` is applied last.

| Flag | Matches |
|---|---|
| `--include GLOB`, `--exclude GLOB` | full name (`traverse.glob_regex`: `*` any run, `?` one character) |
| `--kind KIND` | `dt:typeKind` (`Class`, `Interface`, `Struct`, `Enum`, `Delegate`) |
| `--namespace GLOB` | namespace full name |
| `--assembly GLOB` | defining assembly name |
| `--project GLOB` | repository-relative project path, for example `src/Billing/**` |
| `--accessibility VALUE` | `dt:accessibility` as stored |
| `--origin source\|nuget` | whether the type comes from a source project |

The result reports `typesIn`, `typesOut` and how many types each filter removed. A filter that leaves nothing fails
with `RECORDS_EMPTY` (like `EXPORT_EMPTY`), and the hint names the filter that removed the most. The filters are
recorded in the output's context sidecar, so the export can be reproduced without another file format.

## Schema

A schema is a **JSON Schema** (2020-12 subset) for one record. Each property says which registry field fills it.
The built-in `openwiki-type`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "openwiki-type",
  "type": "object",
  "x-rg-record": "type",
  "properties": {
    "name":           {"type": "string", "x-rg-field": "fullName"},
    "kind":           {"type": "string", "x-rg-field": "kind"},
    "namespace":      {"type": "string", "x-rg-field": "namespace"},
    "assemblies":     {"type": "array", "items": {"type": "string"}, "x-rg-field": "assemblies"},
    "repository":     {"type": ["string", "null"], "x-rg-field": "repository"},
    "projectDirs":    {"type": "array", "items": {"type": "string"}, "x-rg-field": "projectDirs"},
    "files":          {"type": "array", "items": {"type": "string"}, "x-rg-field": "files"},
    "locationStatus": {"type": "string", "enum": ["found", "compiler-generated", "generated", "nuget"], "x-rg-field": "locationStatus"},
    "origin":         {"type": "string", "enum": ["source", "nuget", "mixed"], "x-rg-field": "origin"}
  },
  "required": ["name", "kind", "repository", "projectDirs", "files", "locationStatus", "origin"],
  "additionalProperties": false
}
```

- **Why JSON Schema and not Pydantic.** The skills must run when their folder is installed alone, with the
  standard library only. A Pydantic model is still a first-class way to write a schema: declare
  `Field(json_schema_extra={"x-rg-field": "fullName"})` and write `Model.model_json_schema()` to a file. `rg.py`
  never imports Pydantic. The reference shows a worked model.
- **Supported keywords.** Validation keywords: `type` (single or list), `properties`, `required`,
  `additionalProperties`, `items`, `enum`, `const`, `minItems`, `minLength`. Annotations: `$schema`, `$id`, `title`,
  `description`, `default`, `examples`, `x-rg-*`. Any other keyword fails with `SCHEMA_UNSUPPORTED_KEYWORD`, so a
  schema never looks validated when it is not. Every problem in a schema is reported at once (`ProblemList`).
- **Field binding.** A property has either `x-rg-field` (a registry name) or `const` (a fixed value). A list
  field bound to a non-array property fails with `SCHEMA_FIELD_CARDINALITY` when the schema is loaded, not part way
  through an export.
- **Cost follows the schema.** Store fields are queried only when bound. Source fields (`files`,
  `locationStatus`) run MSBuild and the scan only when bound, so a schema without them never touches a checkout.
- **Built-in schemas** live in the explore skill at `schemas/<name>.schema.json` and are found with
  `util.resource`. `--schema openwiki-type` names a built-in. Anything with a path separator or `.json` is a file.
- **Every record is validated** before the file is written. Violations fail with `RECORD_SCHEMA_VIOLATION` and
  the first 20 offending records.

### Field registry (type records, v1)

The registry is one table in `records.py`: name -> source, cardinality and JSON type. Store queries follow the
existing performance rules: batches of 250 IRIs in `VALUES`, one graph pattern per query, never `UNION`
(`traverse._pairs`).

| Field | Kind | Value |
|---|---|---|
| `iri` | scalar | the type IRI as it appears in the graph (logical or physical) |
| `fullName`, `name`, `kind`, `accessibility` | scalar | the matching `dt:` literal |
| `namespace` | scalar | full name of `dt:inNamespace` |
| `isAbstract`, `isSealed`, `isStatic`, `isGeneric` | scalar boolean | the matching `dt:` literal |
| `assemblies` | list | names of the defining assemblies (several for a logical type) |
| `origin` | scalar | `source`, `nuget`, or `mixed` (a logical type with both) |
| `repository` | scalar or null | `rg:projectRepository`. If one logical type spans repositories, the export fails with `RECORD_AMBIGUOUS_FIELD`; use `repositories` |
| `repositories`, `projects`, `projectDirs` | list | repository IDs, repo-relative project paths, and their directories with a trailing `/` |
| `files` | list | repo-relative declaring files (source locator) |
| `locationStatus` | scalar | see [Source locations](#source-locations-resolved-on-export-not-stored-in-the-graph) |
| `baseType` | scalar or null | full name of the base type's generic definition |
| `interfaces` | list | full names of implemented interfaces |
| `referencesInGraph`, `referencedByInGraph` | list | full names at the other end of this type's edges in the input graph |
| `memberCount` | scalar integer | number of `dt:hasMember` |

A test fails when a registry field is missing from the reference table, as `test_every_follow_relation_is_documented`
already does for follow relations.

## Output

- `--output <file>.jsonl` is required. Records never go to stdout. Stdout stays the single result object every
  command prints: `{"type": "records", "output", "context", "count", "schema", "filters", "locations", "warnings"}`.
  `locations` counts types per `locationStatus` and reports cache hits.
- One record per line, UTF-8, `\n` line endings. Keys follow the schema's property order, records are sorted by
  `fullName`, and `files` is sorted, so re-exports diff cleanly.
- `<file>.context.json` (`roslyn-graph-context/1`, `generator: "records"`) records the store, the input graph or
  selection, the filters, the schema path with its SHA-256, and for each repository the checkout, commit and drift.

## OpenWiki adapter

```text
python rg.py openwiki-scope --records billing.jsonl --records payments.jsonl \
    --repository p3 --repo-root F:\work\p3 [--max-listed-types 400] [--dry-run]
```

- Validates every input file against the built-in `openwiki-type` schema and removes duplicates by `name`.
- OpenWiki runs on one repository at a time, but a graph can span repositories (P3 and Radiant are separate
  repositories). Records for `--repository` are written. The others are counted in the result
  (`excluded.otherRepositories`), so the same records can be run again with the other repository's root.
- Opens `files` for `found` and `compiler-generated` types. `generated` and `nuget` types open nothing, and the
  result counts them. Only `found` types are listed in the brief.
- Writes nothing with `--dry-run`. The result then holds the exact text it would write.
- It never runs OpenWiki. The user runs `openwiki code --init` (or `--update`) in the repository afterwards.

### Ignore chain

The adapter writes a managed block at the **top** of `<repo-root>/.openwikiignore` and keeps all other lines. Since
the last match wins, the user's own exclusions (`secrets/` and so on) come after the block and still apply inside
what it opens. For two files and one fallback project directory:

```text
# BEGIN roslyn-graph openwiki-scope (generated; edit below the END line)
*
!/openwiki/
!/src/
/src/*
!/src/Billing/
/src/Billing/*
!/src/Billing/Orders/
/src/Billing/Orders/*
!/src/Billing/Orders/Order.cs
!/src/Billing/Orders/OrderLine.cs
!/src/Billing/Payments/
# END roslyn-graph openwiki-scope
```

Each ancestor is re-opened (`!/src/`), and then its other children are ignored again (`/src/*`). A file is the
last step of its chain, and a directory opens everything below it. Generating the chain is a pure function over a
set of paths: it removes duplicates, drops paths inside an opened directory, and sorts. A path containing `*`, `?`
or `!` fails with `OPENWIKI_PATH_UNSUPPORTED` instead of producing a rule that matches something else.

This example, followed by a user `secrets/` rule, was run through openwiki 0.7.2's own `OpenWikiIgnore` on
2026-10-13, and all 14 probe paths behaved as designed:
- the opened files, their ancestors, and everything under the fallback `src/Billing/Payments/` were allowed;
- sibling files (`OrderMapper.cs`), sibling directories and other projects were ignored;
- `openwiki/` was allowed;
- `secrets/` inside an opened directory stayed ignored.

### Brief

The adapter writes the same kind of managed block into `<repo-root>/openwiki/INSTRUCTIONS.md`, creating the file if
needed and keeping any text the user wrote outside the block:

- a scope statement: document these types and how they relate, and do not describe other code;
- how to reach the files: use `ls`, `grep`, or a `glob` from the root with a directory-prefixed pattern. In
  openwiki 0.7.2 a `glob` with a search directory returns directory-relative paths, which the ignore filter then
  rejects, so under a deny-all chain it finds nothing (B0 experiment 4);
- the types grouped by project, then namespace, with kind and declaring files;
- external (NuGet) dependencies as a separate list;
- provenance: store artifact ID, graph title, commit, export time.

Briefs over `--max-listed-types` (default 400) list namespaces with type counts instead of every type, with a
warning, because the brief is part of every OpenWiki prompt. With file-level ignore rules, the agent can only reach
the scoped files anyway, so the shorter list mainly reduces the advice, not the enforcement.

## Skill and repository changes

| Where | Change |
|---|---|
| `tools/rg/roslyn_graph/records.py` | inputs, filters, registry, schema loader/validator, writer |
| `tools/rg/roslyn_graph/sources.py` | project resolution from manifests, checkout check, MSBuild Compile items and symbols, `declarations` call, cache |
| `src/RoslynToRdf.Core/Extraction/DeclarationIndexer.cs` | Roslyn syntax-only declaration index for C# and VB |
| `src/RoslynToRdf.Cli/DeclarationsCommand.cs` | `roslyn2rdf declarations --request <file.json>`: JSON in, JSON out |
| `tools/rg/roslyn_graph/openwiki.py` | ignore-chain generator, managed-block merge, brief writer |
| `tools/rg/rg.py` | `records` and `openwiki-scope` subcommands |
| `tools/rg/tests/` | `test_records.py`, `test_sources.py`, `test_openwiki.py` |
| explore skill `schemas/` | `openwiki-type.schema.json` |
| explore skill `reference/` | `records.md` (schema subset, registry table, Pydantic example), `openwiki-scope.md` |
| explore skill `workflows/` | `export-records.md`; `SKILL.md` router gains one line |
| `scripts/check_plugin_sync.py` | no change needed: new modules match `roslyn_graph/*.py` and are copied into both skills |

## Decisions

Taken:

- Source files are resolved **on export** from MSBuild Compile items and a Roslyn declaration pass in the extractor.
  The initial scan does not change.
- Command names `records` and `openwiki-scope`.
- File-level ignore chains by default: exact for 10, 50 and 200 types (B0 experiment 3). Directory-level chains
  exposed 1.6 to 2.9 times as many files.
- JSONL by default. JSON Schema with `x-rg-field` is the one schema format, and Pydantic works through
  `model_json_schema()`.
- The type list goes in `INSTRUCTIONS.md`, not in `-p`, so `--update` runs keep the same scope.

Settled by B0 and B7:

1. Scanner accuracy. No source-declared type was missed once the preprocessor symbols were right; B2 uses Roslyn.
2. Enforcement. OpenWiki's backend gives the agent no way to read outside a file-level scope: reads, `ls`, `grep`
   and `glob` are filtered, and shell access is limited to `pwd` and `git rev-parse HEAD`.

3. Model-level adherence and cost ([openwiki-run-radiant-data-2026-10-13.md](openwiki-run-radiant-data-2026-10-13.md),
   Radiant.Data with `gpt-6-luna`): the agent read no file outside the scope, the wiki covers the scope by topic
   (63 of 270 type names), and 7 pages over a 186-file scope cost about 1.25 M input tokens in 398 s.

Still open:

- The P3 XCore runs (experiment 4 b and c, experiments 5 and 6 at 50 and 200 types). They were not run, to keep
  model runs small; `run_openwiki.py --provider openai-chatgpt --model gpt-6-luna` runs them.
- OpenWiki's process (not the agent) reads nearly every repository file during its scan. Worth reporting upstream
  alongside the `glob` defect.

See [implementation-plan.md](implementation-plan.md) for the sprints and acceptance checks.
