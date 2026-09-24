# b) Generate the initial databases

Goal: every artifact of a collection published and validated, with a report the user can rely on.

## 1. Tools and environment

Follow [../reference/setup.md](../reference/setup.md) once per machine. Before running:
- `ROSLYN_GRAPH_DATA_ROOT` is set, or pass `--data-root` to every command;
- every `credential_env` named by the collection's NuGet profiles is set in this shell.

## 2. Solution builds

For each solution profile in the collection (base and overlays), make sure a successful build of the
recorded configuration exists and that the repositories are committed. The skill refuses outputs older
than their sources (`BUILD_OUTPUT_STALE`) and uncommitted repositories (`SOURCE_DIRTY`). Only pass
`--allow-dirty` when the user explicitly wants an uncommitted state captured.

## 3. Plan

```
python <plugin>/scripts/rg.py plan --workspace <workspace.toml> --collection <name>
```

On `type: "error"`, fix every listed problem (each has a hint; codes are explained in
[../reference/troubleshooting.md](../reference/troubleshooting.md)) and plan again. On `type: "plan"`,
confirm `summary.components` matches what the user expects (for example "57 projects + 2 packages").

## 4. Generate

```
python <plugin>/scripts/rg.py generate --workspace <workspace.toml> --collection <name>
```

This runs long (minutes for ~60 assemblies); run it in the background and wait. For every component it
extracts, loads, validates in staging, publishes atomically and validates again; then it composes the
solution store, builds the view when the collection has overlays, validates both deeply, and finally
re-plans to prove the run is idempotent.

## 5. Report

From the `type: "generate"` result, report to the user:
- `summary.solution` and `summary.view`: artifact IDs, paths, triple and graph counts;
- `summary.created` / `summary.reused`;
- `solutionManifest` and `viewManifest` paths (the explore skill starts from these);
- `pinsToRecord`: write each `sha256` into its NuGet profile in `workspace.toml` now, so future runs
  detect a feed serving different bytes for the same version;
- any `warnings`.

## 6. Optional full re-validation

```
python <plugin>/scripts/rg.py validate --manifest <solution or view manifest.json> --deep
```

`passed: true` means every check in [../reference/validation.md](../reference/validation.md) passed for
the store and all of its components.
