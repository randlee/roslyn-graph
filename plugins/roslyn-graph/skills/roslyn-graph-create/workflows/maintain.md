# c) Maintain existing databases

Goal: capture a new version without touching earlier artifacts, show what changed, and keep the data root
valid and tidy.

Artifacts are immutable and content-addressed ([../reference/artifact-layout.md](../reference/artifact-layout.md)).
A new commit, rebuilt DLL, package version, extractor build or build-file change produces new artifact
IDs; anything unchanged is reused by ID.

## New version of a solution or package

1. Update inputs:
   - **source change**: the user checks out the new commit; you build the solution successfully;
   - **package change**: edit the NuGet profile's `version`, clear its `sha256`; if a solution profile
     consumes it, the solution must have been restored/built against that version (otherwise plan
     reports `PACKAGE_VERSION_DRIFT`);
   - **new projects/packages**: edit the profile ([design-toml](design-toml.md), steps 2–4).
2. Plan and review what will be new:

   ```
   python <skill>/scripts/rg.py plan --workspace <workspace.toml> --collection <name>
   ```

   `summary.new` counts components that will be extracted; `summary.reused` those already published.
   `summary.solutionExists: true` with `new: 0` means nothing changed.
3. Generate exactly as in [generate-initial](generate-initial.md) steps 4–5. The result's
   `diffFromPrevious` compares the new solution with the previous one for the same profile: assemblies
   added, removed and changed (version, commit, triple delta). Report it. Record new `pinsToRecord`.

To compare any two solution stores directly:

```
python <skill>/scripts/rg.py diff --old <old manifest.json> --new <new manifest.json>
```

## Validate what exists

```
python <skill>/scripts/rg.py validate [--manifest <manifest.json>] [--deep]
```

Without `--manifest` every schema-2 artifact under the data root is checked. Report failures by check ID
([../reference/validation.md](../reference/validation.md)). A failed published artifact is never repaired
in place: regenerate it (remove it first, with approval, then `generate`).

## Clean up

```
python <skill>/scripts/rg.py inventory
```

Each artifact has a `status`: `latest`, `in-use` (referenced by another artifact), `superseded` (an older
solution or view), `unreferenced` (an assembly no store uses) or `legacy` (created before this skill; it
cannot be validated). `cleanupCandidates` lists removable artifacts in a safe order (views, solutions,
legacy, then assemblies).

1. Show the candidates to the user and get explicit approval for each path.
2. Preview, then remove, one path at a time:

   ```
   python <skill>/scripts/rg.py remove --path <artifact path>
   python <skill>/scripts/rg.py remove --path <artifact path> --confirm
   ```

   `remove` refuses anything still referenced (`REMOVE_REFERENCED`) and anything that is not a published
   artifact. Re-run `inventory` after each round: removing a solution can make its assemblies
   unreferenced.
3. `staging/` holds only failed runs kept for inspection; the user may delete those directories once the
   failure is understood.
