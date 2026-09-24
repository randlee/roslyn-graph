# Error codes

Every `rg.py` error carries `code`, `message`, `hint` and `context`. Failed staging directories are kept
(`context.staging`) until the user deletes them. For slow or hanging commands set `ROSLYN_GRAPH_TRACE=1`:
every Oxigraph call is logged to stderr with its duration and the start of its query. Read-only Oxigraph
commands that crash natively (for example Windows exit code 0xC0000005) are retried once automatically.

## Input and configuration

| Code | Meaning and fix |
|---|---|
| `USAGE` | wrong command-line arguments; run `rg.py <command> --help` |
| `PYTHON_TOO_OLD` | use Python 3.11 or newer |
| `WORKSPACE_NOT_FOUND` | the `--workspace` path does not exist; run design-toml |
| `TOML_SYNTAX` | TOML parse error at the reported line and column |
| `TOML_SCHEMA_VERSION` | `schema_version` must be 1; rewrite the file with design-toml |
| `TOML_INVALID` | a key is missing, unknown or malformed; `context.key` names it |
| `COLLECTION_NOT_FOUND` | the `--collection` name is not in the TOML |
| `DATA_ROOT_MISSING` | set `ROSLYN_GRAPH_DATA_ROOT` or pass `--data-root` |

## Tools

| Code | Meaning and fix |
|---|---|
| `TOOL_NOT_FOUND` | a required executable (dotnet, git, oxigraph) is not on PATH; see setup.md |
| `OXIGRAPH_VERSION_MISMATCH` | installed Oxigraph differs from `[tools].oxigraph`; install that version or change the TOML deliberately |
| `OXIGRAPH_VERSION_UNKNOWN` | `oxigraph --version` printed something unexpected; check the executable |
| `OXIGRAPH_FAILED` | an Oxigraph command failed or printed an error (parser error, missing file, locked store); read `context.stderr` |
| `OXIGRAPH_BAD_JSON`, `OXIGRAPH_BAD_SCALAR` | a query returned an unexpected shape; usually a bug in the query |
| `EXTRACTOR_NOT_FOUND` | install the RoslynToRdf tool or set `ROSLYN_GRAPH_EXTRACTOR`; see setup.md |
| `EXTRACTOR_RUNTIMECONFIG` | the extractor installation is incomplete; reinstall it |
| `EXTRACTOR_RUNTIME_MISSING` | install the .NET runtime the extractor targets |
| `EXTRACTION_FAILED` | the extractor could not load the assembly; usually a dependency missing from the search directories; check the build output and restore belong to the same build |
| `GIT_FAILED` | a project is not inside a git repository, or git failed |

## Solution build checks

| Code | Meaning and fix |
|---|---|
| `SOLUTION_NOT_FOUND`, `SOLUTION_UNSUPPORTED`, `SOLUTION_EMPTY` | check `root`/`solution`; only .sln/.slnx with C# projects are supported |
| `PROJECT_NOT_FOUND`, `PROJECT_UNREADABLE` | a project listed by the solution is missing or not valid XML |
| `PROJECT_NOT_IN_SOLUTION`, `EXCLUDE_NOT_SELECTED` | a path in `collect.projects`/`exclude` does not match a solution project (paths are relative to `root`) |
| `ASSEMBLY_NAME_COMPUTED` | add the evaluated name under `assembly_names` |
| `BUILD_OUTPUT_MISSING` | build the solution; or add an `outputs` entry for a project that writes elsewhere; or exclude it |
| `NO_OUTPUT_FOUND` | (discover) a project has no built DLL yet; build first |
| `BUILD_OUTPUT_STALE` | sources or fingerprint files are newer than the DLL; rebuild |
| `SOURCE_DIRTY` | commit the changes and rebuild, or pass `--allow-dirty` if the user wants that state captured |
| `FINGERPRINT_FILE_MISSING` | a `fingerprint_files` entry does not exist; fix the path |
| `ASSETS_NOT_FOUND` | a project has no `obj/project.assets.json`; restore/build the solution |
| `ASSETS_TARGET_MISSING`, `ASSETS_TARGET_AMBIGUOUS` | `target_framework` does not select exactly one restore target |
| `PACKAGE_NOT_CONSUMED` | a `collect.packages` entry is not restored by the solution; remove it |
| `PACKAGE_VERSION_DRIFT` | the solution restored another version than the nuget profile pins; update the profile |
| `PACKAGE_OUTPUT_DIFFERS` | the package DLL in the build output is not the package's DLL; rebuild after restore |
| `OVERLAY_NOT_IN_POLICY` | add the overlay's assembly to the policy, or remove the overlay |

## NuGet

| Code | Meaning and fix |
|---|---|
| `NUGET_CREDENTIAL_MISSING` | set the environment variable named by `credential_env` |
| `NUGET_RESTORE_FAILED` | read `context.messages`: NU1101/NU1102 the package or a dependency is not on the configured sources (add `dependency_sources`); NU1301 or 401 credentials; NU1603/NU1605 version drift |
| `NUGET_PACKAGE_MISSING`, `NUGET_VERSION_MISMATCH` | restore did not produce the pinned package/version |
| `NUGET_NO_RUNTIME_ASSETS` | the package has no runtime DLL for `target_framework` |
| `NUGET_HASH_MISMATCH` | the feed serves different bytes for this version; investigate before changing the pin |
| `NUGET_NUSPEC_UNREADABLE`, `NUGET_NUSPEC_MISMATCH` | the package metadata does not match the profile |
| `NUGET_SOURCE_MISMATCH` | the package was not restored from `source`; delete `cache/nuget/<hash>` and retry |
| `NUGET_SIGNATURE_INVALID` | a signed package fails verification; do not use it |

## Artifacts and publication

| Code | Meaning and fix |
|---|---|
| `ARTIFACT_DIR_WITHOUT_MANIFEST` | an unknown directory occupies an artifact path; inspect and remove it by hand |
| `ARTIFACT_ID_COLLISION` | all prefixes are taken by other artifacts (practically impossible); report it |
| `ARTIFACT_PATH_TOO_LONG` | use a shorter data root |
| `ARTIFACT_LOCKED` | another run is publishing the same artifact; wait, or delete a stale lock file |
| `ARTIFACT_DESTINATION_TAKEN` | a different artifact appeared at the destination during the run; re-run |
| `ASSEMBLY_NODE_COUNT` | the extraction produced zero or several `dt:Assembly` nodes |
| `IDENTITY_DRIFT` | inputs changed between planning and extraction (for example a rebuild); re-run |
| `PHYSICAL_IDENTITY_AMBIGUOUS` | two components define the same type IRI (same assembly name and version from different builds); bump one assembly version |
| `VALIDATION_FAILED` | one or more checks failed; `context.failed` lists them (see validation.md) |
| `NOT_IDEMPOTENT` | inputs changed during the run; generate again |
| `PATH_SEGMENT_EMPTY`, `INVALID_IRI` | a name cannot be used in a path or IRI; report the input |
| `MANIFEST_UNREADABLE` | a manifest is not valid JSON |
| `MANIFEST_UNSUPPORTED` | the manifest is legacy or not an artifact manifest; regenerate |

## Maintenance

| Code | Meaning and fix |
|---|---|
| `REMOVE_OUTSIDE_ARTIFACTS`, `REMOVE_NOT_ARTIFACT` | `remove` only deletes published artifact directories |
| `REMOVE_REFERENCED` | remove the artifacts listed in `context.referencedBy` first |

## Exploration

| Code | Meaning and fix |
|---|---|
| `STORE_NOT_FOUND` | the manifest's `store.oxigraph` is missing |
| `QUERY_ARGUMENT`, `QUERY_FILE` | pass exactly one readable `--query` or `--query-file` |
| `QUERY_PARAM_MISSING`, `QUERY_PARAM_INVALID` | pass every `{{NAME}}` placeholder as `--param NAME=VALUE` (upper-case name) |
| `EXPORT_NEEDS_CONSTRUCT`, `EXPORT_EMPTY`, `EXPORT_UNSAFE` | exports need a CONSTRUCT query that returns triples without `</script` |
| `LOGICAL_NEEDS_VIEW` | `--logical` works only on view manifests |
| `GRAPH_DEFINITION_NOT_FOUND`, `GRAPH_DEFINITION_INVALID` | fix the `.graph.toml` path or the key named in `context.key` (see the explore skill's graph-definitions.md) |
| `GRAPH_SOURCE_NOT_FOUND` | the definition's collection or manifest has no published artifact; generate it first |
| `GRAPH_SEED_NOT_FOUND` | a seed name or pattern matches no component type; look names up with find-type.rq |
| `VISUALIZER_UNKNOWN`, `VISUALIZER_UNSUPPORTED`, `VISUALIZER_TEMPLATE` | the visualizer name or its template is wrong; list them with `rg.py visualizers` |
| `ONTOLOGY_DOC_STALE`, `ONTOLOGY_PARSE` | (maintainers) regenerate the ontology reference or fix the ontology file |

## Always

| Code | Meaning and fix |
|---|---|
| `INTERNAL` | an unexpected exception; this is a bug in rg.py; report `context.traceback` |
