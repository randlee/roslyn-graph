# Solution profiles

## What the skill reads

The skill never evaluates or runs MSBuild. It reads:

1. the `.sln`/`.slnx` project list (only `.csproj` entries; solution folders are ignored);
2. each project file's `<AssemblyName>` (or the file name when absent; `$(...)` values need an
   `assembly_names` entry);
3. the build output `<output dir>/<AssemblyName>.dll`;
4. `obj/project.assets.json` of each project, for dependency folders and consumed package versions;
5. git state of the repository containing each project.

## Build check

`plan` rejects a component unless all of these hold:

| Code | Rule |
|---|---|
| `BUILD_OUTPUT_MISSING` | the DLL exists exactly where the TOML says (no directory scanning) |
| `BUILD_OUTPUT_STALE` | the DLL is newer than every source-like file in its project folder (`.cs`, `.csproj`, `.props`, `.targets`, `.resx`, `.xaml`, `.settings`, `.config`, `.json`, `.editorconfig`; `bin`/`obj` excluded) and every `fingerprint_files` entry |
| `SOURCE_DIRTY` | the owning repository has no uncommitted or untracked changes (or `--allow-dirty`, which hashes the dirty state into the identity) |
| `PACKAGE_VERSION_DRIFT` | every project that restored a `collect.packages` package restored the version its nuget profile pins |
| `PACKAGE_NOT_CONSUMED` | a listed package is actually restored by the solution |
| `PACKAGE_OUTPUT_DIFFERS` | the package DLL copied into `output_dir` is byte-identical to the isolated restore |

After extraction the assembly's own name must equal the expected output name (check `S5`).

**What the build check does not prove.** It does not show that the outputs were built with the profile's
configuration, platform or compile constants; `[profiles.<name>.build]` describes the build, and the
manifests record those values as stated. Producing a build that matches them is the responsibility of the
agent using the skill (see generate-initial, step 2).

## Choosing fingerprint_files

The fingerprint must change whenever the build *definition* changes in a way the commit of a project's
own repository does not capture. Include:

- the import chain that sets configuration, platform, compile constants and package versions
  (`rg.py discover` reports it as "imported by the project build", resolving `$(SolutionDir)`,
  `$(MSBuildThisFileDirectory)` and properties defined along the chain);
- `Directory.Build.props`/`.targets`, `Directory.Packages.props` and `global.json` that apply to the
  projects ("inherited by MSBuild or NuGet").

Do not include generated or "unrolled" copies of targets that the solution build does not import (for
example a flattened `Common.targets` written by a helper script for project-only builds). Hash the files
the solution build actually imports.

`discover` follows the common `Condition="'$(X)' == ''"` guard (a property already set, such as
`SolutionDir` in a solution build, is not overwritten). Other conditions are ignored; review
`unresolvedImports` by hand.

## Multi-repository solutions

Set `root` to the directory that contains all participating repositories (for example a checkout root
holding `App`, `Core` and `Build` side by side). Each component records its own repository's branch and
commit; the solution records the commit of the repository containing the `.sln`.

## Tests and projects with other output folders

Projects that do not write to `output_dir` (typically test projects with their own `bin/<cfg>/<tfm>`)
need an `outputs` entry; `discover` suggests them in `outputOverrides`. To leave a project out, add it to
`collect.exclude`.
