# a) Design workspace.toml

Goal: a `workspace.toml` that states exactly what to collect, so generation needs no further decisions.
Nothing is written under the data root in this workflow.

Schema: [../reference/workspace-toml.md](../reference/workspace-toml.md). Keep it open while writing.

## 1. Decide where the file lives

One `workspace.toml` per workspace, normally `<workspace>/.roslyn-graph/workspace.toml`. Relative paths in
it resolve against the file's directory. Ask the user if unsure. Do not put it inside a product repository
unless the user wants it versioned there.

## 2. Solution profiles

1. Make sure the solution has been **built successfully** in the configuration the user wants analyzed
   (you do the build; see the repository's build docs). Discovery needs the outputs.
2. Run discovery:

   ```
   python <plugin>/scripts/rg.py discover --solution <path.sln> --tfm <target framework> [--root <dir>]
   ```

   Use `--root` for multi-repository layouts where projects live beside the solution's folder (for
   example a checkout root holding several repositories). The result (`type: "discovery"`) suggests:
   - `suggestedRoot`, `suggestedOutputDir` and per-project `outputOverrides`;
   - `repositories` with their branch and commit;
   - `packages` restored by the solution, most-used first;
   - `fingerprintCandidates`: the build's resolved import chain and inherited MSBuild files;
   - `unresolvedImports` the user must decide on.
3. Resolve every project row that has a `problem` (for example `NO_OUTPUT_FOUND` means the build is
   incomplete or the project writes elsewhere).
4. Ask the user only what discovery cannot know:
   - collection scope: all solution projects, or an explicit `projects` list (and any `exclude`);
   - the configuration/platform names to record under `[profiles.<name>.build]`;
   - which restored packages to capture as package components (usually the ones whose newer source
     builds will be overlaid);
   - which `fingerprintCandidates` really define the build (keep the import chain and Directory.Build
     files; drop unrelated ones). See [../reference/solution-profiles.md](../reference/solution-profiles.md).
5. Write the profile. Every project-keyed table uses paths relative to `root` with forward slashes.

## 3. NuGet profiles

For each package: exact `version`, `target_framework`, the feed in `source`, the feeds for its
dependencies in `dependency_sources` (normally `https://api.nuget.org/v3/index.json`), and
`credential_env` if the feed needs a token. Leave `sha256` empty; the first generation reports it in
`pinsToRecord` and you then write it in. Details: [../reference/nuget-profiles.md](../reference/nuget-profiles.md).

## 4. Collections and policies

- A collection with only `base` produces one solution store.
- `overlays` add newer builds of some assemblies and produce a logical-type view. They require
  `logical_type_policy`, naming a `[policies.<name>]` table that lists the assembly names whose versions
  may be reconciled. Only add assemblies the user confirms are compatible across those versions.

## 5. Check before handing over

```
python <plugin>/scripts/rg.py check-workspace --workspace <workspace.toml>
python <plugin>/scripts/rg.py plan --workspace <workspace.toml> --collection <name>
```

`check-workspace` reports every schema problem at once. `plan` resolves every DLL, runs the build checks
and restores packages (it writes only the NuGet cache). Show the user the `summary`, the component count
per profile and any `warnings`, and get confirmation. Then continue with
[generate-initial](generate-initial.md).
