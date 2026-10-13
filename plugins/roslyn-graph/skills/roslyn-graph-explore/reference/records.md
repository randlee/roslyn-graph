# Records: schema-driven export of a graph's types

`rg.py records` writes one JSON record per type of a completed graph. A JSON Schema says which fields each
record has. It knows nothing about any consumer; OpenWiki is one built-in schema plus
[openwiki-scope](openwiki-scope.md).

```
python <skill>/scripts/rg.py records --graph out/billing.nt --schema openwiki-type --output out/billing.jsonl
python <skill>/scripts/rg.py records --selection picked.selection.json --schema my-type.schema.json --output out/picked.jsonl
```

## Input

Exactly one of:

| Option | Input | Types |
|---|---|---|
| `--graph <name>.nt` | output of `rg.py graph` or `rg.py export`, beside its `<name>.context.json` | the subjects of `dt:fullName` triples (namespaces, assemblies and members are skipped) |
| `--selection <file>.json` | a `roslyn-graph-selection/2` payload from the explorer ([selection-format.md](selection-format.md)) | exactly the types the user had drawn |

The store comes from the input's context (`source.manifest`, or `store` in a selection); `--manifest` overrides
it. A **logical** graph (made with `logical = true` from a view) holds logical type IRIs. Each one is mapped to
its physical versions, list fields collect every version's values, and a scalar that differs between versions
writes the first value in sorted order and warns `RECORD_FIELD_VARIES`.

## Filters

Filters run before any field is fetched or any checkout is scanned. Repeating an option ORs its values;
different options AND; `--exclude` is applied last. Globs: `*` any run of characters (dots included), `?` one.

| Option | Matches |
|---|---|
| `--include GLOB`, `--exclude GLOB` | full name |
| `--kind KIND` | `dt:typeKind`: `Class`, `Interface`, `Struct`, `Enum`, `Delegate` |
| `--namespace GLOB` | namespace full name |
| `--assembly GLOB` | defining assembly name |
| `--project GLOB` | repository-relative project path, e.g. `src/Billing/**` |
| `--accessibility VALUE` | `dt:accessibility` as stored (`Public`, `Internal`, ...) |
| `--origin source\|nuget` | whether the type comes from a source project |

The result reports `filters.typesIn`, `typesOut` and `removed` per option. Removing every type fails with
`RECORDS_EMPTY`, and the hint names the filter that removed the most.

## Schema

A schema is a JSON Schema (2020-12 subset) for one record. `--schema NAME` names a built-in in this skill's
`schemas/` folder (`openwiki-type`); anything with a path separator or ending in `.json` is a file.

Every property has exactly one of:
- `x-rg-field`: a field from the registry below;
- `const`: a fixed value written into every record.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "doc-type",
  "type": "object",
  "x-rg-record": "type",
  "properties": {
    "name":   {"type": "string", "x-rg-field": "fullName"},
    "kind":   {"type": "string", "enum": ["Class", "Interface", "Struct", "Enum", "Delegate"], "x-rg-field": "kind"},
    "base":   {"type": ["string", "null"], "x-rg-field": "baseType"},
    "files":  {"type": "array", "items": {"type": "string"}, "x-rg-field": "files"},
    "source": {"const": "roslyn-graph"}
  },
  "required": ["name", "kind", "files"],
  "additionalProperties": false
}
```

Supported keywords:

| Kind | Keywords |
|---|---|
| Validation | `type` (one or a list), `properties`, `required`, `additionalProperties`, `items`, `enum`, `const`, `minItems`, `minLength` |
| Annotations | `$schema`, `$id`, `title`, `description`, `default`, `examples`, `x-rg-*` |

Any other keyword fails with `SCHEMA_UNSUPPORTED_KEYWORD`, so a schema never looks enforced when it is not.

Checks when the schema is loaded:
- A list field bound to a non-array property, or a scalar field bound to an array property, fails with
  `SCHEMA_FIELD_CARDINALITY`.
- `x-rg-record` must be `type`; member records are reserved.
- All problems are reported together.

Every record is validated before anything is written. Failures raise `RECORD_SCHEMA_VIOLATION` and list the
first 20 records. To relax a rule, allow `null` or drop it from `required`.

**Cost follows the schema.** Only bound fields are fetched. Source fields (`files`, `locationStatus`) run
MSBuild and the declaration scan, and only for the projects behind the exported types. A schema without them
never touches a checkout.

### Pydantic

`rg.py` uses the standard library only, but a Pydantic model is a convenient way to write a schema:

```python
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

def rg(name: str):
    return Field(json_schema_extra={"x-rg-field": name})

class DocType(BaseModel):
    model_config = ConfigDict(extra="forbid", title="doc-type", json_schema_extra={"x-rg-record": "type"})
    name: str = rg("fullName")
    kind: Literal["Class", "Interface", "Struct", "Enum", "Delegate"] = rg("kind")
    files: list[str] = rg("files")

import json, pathlib
pathlib.Path("doc-type.schema.json").write_text(json.dumps(DocType.model_json_schema(), indent=1))
```

Pydantic adds a `title` to every property, which is allowed. Avoid `Optional[...]` and `X | None`: Pydantic
writes them as `anyOf`, which is not supported. Write `type: ["string", "null"]` by hand, or post-process the
schema.

## Field registry (type records)

| Field | Value type | Needs | Value |
|---|---|---|---|
| `iri` | string | graph | the type IRI as it appears in the input (logical or physical) |
| `fullName` | string | store | `dt:fullName` |
| `name` | string | store | `dt:name` |
| `kind` | string | store | `dt:typeKind` |
| `accessibility` | string | store | `dt:accessibility` |
| `namespace` | string or null | store | full name of `dt:inNamespace` |
| `isAbstract` | boolean | store | `dt:isAbstract` (false when absent) |
| `isSealed` | boolean | store | `dt:isSealed` (false when absent) |
| `isStatic` | boolean | store | `dt:isStatic` (false when absent) |
| `isGeneric` | boolean | store | `dt:isGeneric` (false when absent) |
| `assemblies` | list of string | store | names of the defining assemblies (several for a logical type) |
| `origin` | string | manifest | `source`, `nuget`, or `mixed` (a logical type with both) |
| `repository` | string or null | manifest | repository ID of the source project; null for NuGet. A type spanning repositories fails with `RECORD_AMBIGUOUS_FIELD` |
| `repositories` | list of string | manifest | repository IDs |
| `projects` | list of string | manifest | repository-relative project paths |
| `projectDirs` | list of string | manifest | directories of `projects`, with a trailing `/` |
| `files` | list of string | source | repository-relative declaring files (source locator) |
| `locationStatus` | string | source | `found`, `compiler-generated`, `generated` or `nuget` |
| `baseType` | string or null | store | full name of the base type's generic definition |
| `interfaces` | list of string | store | full names of the implemented interfaces' generic definitions |
| `referencesInGraph` | list of string | graph | full names this type points to in the input graph |
| `referencedByInGraph` | list of string | graph | full names pointing to this type in the input graph |
| `memberCount` | integer | store | number of `dt:hasMember` (the largest version for a logical type) |

*Needs*:

| Value | Where the field comes from |
|---|---|
| store | the Oxigraph store |
| manifest | the component manifests |
| graph | the input graph. The edge fields need `--graph`; with a selection they fail with `RECORDS_FIELD_UNAVAILABLE` |
| source | the source locator below |

## Source locations

Stores hold no source paths. `files` and `locationStatus` are resolved on export, from the build that made
the store. For each source project behind the exported types:

1. **Find the project.** The component manifest gives the checkout (`origin.repository`), the commit and the
   build: project, solution, configuration, target framework and platform.
2. **Check the checkout.** It must be at the recorded commit, with the same uncommitted changes as the build
   (usually none). Otherwise the export fails with `SOURCE_CHECKOUT_DRIFT`.
   - `--allow-drift` resolves from the current checkout anyway, with a warning. The index is then not cached.
   - `--repo-root ID=PATH` points at a checkout that has moved. It is repeatable, and the ID is the
     repository ID of the workspace profile.
3. **Ask MSBuild.** `dotnet msbuild -getItem:Compile` lists the exact Compile items and preprocessor symbols.
   It covers linked files, `Condition`s, `Compile Remove`, `$(SolutionDir)` imports and the SDK's implicit
   `NET*` symbols, with the build's configuration and solution context. This needs .NET SDK 8+, or Visual
   Studio MSBuild 17.8+ for non-SDK projects (`ROSLYN_GRAPH_MSBUILD` selects the executable).
4. **Ask Roslyn.** The extractor's `declarations` command parses those files with those symbols, for C# and
   VB, and names every declared type exactly as `dt:fullName`. An extractor without the command fails with
   `DECLARATIONS_UNSUPPORTED`; update it ([setup](../../roslyn-graph-create/reference/setup.md)).
5. **Cache.** Clean checkouts are cached under `<data-root>/.roslyn-graph/cache/source-index/`, keyed by
   repository, commit, project, build and extractor. A re-export skips MSBuild and the scan (`cacheHits`).

| `locationStatus` | Meaning | `files` |
|---|---|---|
| `found` | declared in Compile items inside the repository | the declaring files; several for `partial` types |
| `compiler-generated` | a name segment starts with `<` (closures, state machines, `<PrivateImplementationDetails>`) | the enclosing named type's files |
| `generated` | declared in no Compile item inside the repository: source generators, weavers, files under `obj/` | empty |
| `nuget` | no source project | empty |

For a logical type, `files` is the union across its versions, and `locationStatus` is the first of those four
values that any version has.

## Output

- `--output` is required, because records never go to stdout. The default format is JSONL: one record per
  line, so exports from several graphs can be concatenated. `--format json` writes one array instead.
- Keys follow the schema's property order. Records are sorted by full name and `files` is sorted, so
  re-exports are byte-identical.
- `<output>.context.json` (`roslyn-graph-context/1`, `generator: "records"`) records the following, so the
  export can be reproduced:
  - the store;
  - the input;
  - the filters;
  - the schema path and SHA-256;
  - each repository's commit, checkout and drift.
- Stdout is the result:
  `{"type": "records", "output", "context", "count", "format", "schema", "filters", "locations", "warnings"}`.
  `locations` counts types per status and lists each project with `cached`, `declaredTypes` and
  `languageVersion`.

Error codes are listed in the create skill's
[troubleshooting.md](../../roslyn-graph-create/reference/troubleshooting.md), under Records and Source locations.
