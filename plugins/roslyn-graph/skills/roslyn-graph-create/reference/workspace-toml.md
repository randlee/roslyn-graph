# workspace.toml (schema version 1)

`rg.py check-workspace` enforces everything on this page and reports every violation at once.
Unknown keys are errors, so typos never silently change behavior.

## Path rules

- `root` is relative to the directory containing `workspace.toml` (absolute paths are allowed).
- `solution`, `output_dir`, `fingerprint_files`, `search_dirs` and the *values* of `outputs` are relative to `root`.
- Project keys (`collect.projects`, `collect.exclude`, `outputs`, `assembly_names`) are project file paths
  relative to `root`, written with forward slashes, for example `"Core/Contoso.Logging/Contoso.Logging.csproj"`.

## Top level

```toml
schema_version = 1          # required, exactly 1

[tools]
oxigraph = "0.5.8"           # required: the installed Oxigraph must be this exact version
```

## Solution profile

```toml
[profiles.app]                             # name: letters, digits, '_' and '-'
kind = "solution"                          # optional; "solution" is the default
root = "../app-checkout"                   # required
solution = "App/App.sln"                   # required; .sln or .slnx
output_dir = "App/bin/Debug"               # required; where the build writes <AssemblyName>.dll
fingerprint_files = [                      # files whose content defines the build (hashed into the identity)
  "App/Common.targets",
  "Build/Platform.targets",
]
search_dirs = []                           # optional extra dependency directories for the extractor

[profiles.app.build]                       # describes the build that was run; the skill never builds
configuration = "Debug"                    # required
target_framework = "net10.0"               # required; also selects the restore target in project.assets.json
platform = "X64"                           # optional

[profiles.app.collect]                     # required; exactly one of the next two
all_solution_projects = true
# projects = ["src/Contoso.Data/Contoso.Data.csproj"]
exclude = []                               # optional; project paths removed from the selection
packages = ["contoso_data_2_4"]            # optional; nuget profiles this solution consumed

[profiles.app.outputs]                     # optional per-project output directory
"App/App.Tests/App.Tests.csproj" = "App/App.Tests/bin/Debug/net10.0"

[profiles.app.assembly_names]              # optional; only for projects whose AssemblyName uses $(...)
"src/Generated/Generated.csproj" = "Contoso.Generated"
```

What the skill derives (details in [solution-profiles.md](solution-profiles.md)):
- the DLL for a project: `outputs[project]` or `output_dir`, plus `/<AssemblyName>.dll`;
- the owning repository: the git repository containing the project; its folder name is the origin ID;
- the build fingerprint: `<configuration>-<target_framework>[-<platform>]-<16 hex>`, hashing those three
  values and every `fingerprint_files` entry's path and content;
- search directories: the DLL's folder, `output_dir`, `search_dirs`, and every package asset folder in
  the project's `obj/project.assets.json`.

## NuGet profile

```toml
[profiles.contoso_data_2_4]
kind = "nuget"
package = "Contoso.Data"                   # package ID
version = "2.4.0"                          # exact version; ranges and wildcards are rejected
target_framework = "net10.0"               # framework whose runtime assets are extracted
source = "https://nuget.pkg.github.com/contoso/index.json"     # the package must come from here
dependency_sources = ["https://api.nuget.org/v3/index.json"]   # feeds for its dependencies
credential_env = "NUGET_CONTOSO_TOKEN"     # optional; NAME of an environment variable holding a token
sha256 = "<64 hex>"                        # optional pin of the .nupkg; generate reports it in pinsToRecord
```

Details: [nuget-profiles.md](nuget-profiles.md).

## Policies and collections

```toml
[policies.contoso-additive]
assemblies = ["Contoso.Data"]              # assembly names whose versions may be reconciled

[collections.app_build]                    # base only: one solution store
base = "app"

[collections.app_with_current_data]        # base + overlays: solution store + logical-type view
base = "app"
overlays = ["data_current"]                # solution or nuget profiles
logical_type_policy = "contoso-additive"   # required when overlays are present
```

- `base` may be a solution profile or a nuget profile (a package on its own becomes a one-package "solution").
- Every overlay assembly must be listed in the policy (`OVERLAY_NOT_IN_POLICY`).
- A policy only reconciles *names*: list an assembly only after the user confirms the versions involved
  are compatible for the analysis. Types are linked by assembly name + full metadata name.

## Complete example

A multi-repository solution that consumes two internal packages, plus a newer source build of one of
them as an overlay. Names are placeholders.

```toml
schema_version = 1

[tools]
oxigraph = "0.5.8"

[profiles.app]
root = "../app-checkout"                       # holds App, Core and Build repositories side by side
solution = "App/App.sln"
output_dir = "App/bin/Debug"
fingerprint_files = [
  "App/Common.targets", "Build/Platform.targets", "Build/Shared/PackageVersions.targets",
  "Core/Directory.Build.props",
]

[profiles.app.build]
configuration = "Debug"
target_framework = "net10.0"
platform = "X64"

[profiles.app.collect]
all_solution_projects = true
packages = ["contoso_data_2_4", "contoso_model_1_9"]

[profiles.app.outputs]
"App/App.Tests/App.Tests.csproj" = "App/App.Tests/bin/Debug/net10.0"

[profiles.contoso_data_2_4]
kind = "nuget"
package = "Contoso.Data"
version = "2.4.0"
target_framework = "net10.0"
source = "https://nuget.pkg.github.com/contoso/index.json"
dependency_sources = ["https://api.nuget.org/v3/index.json"]
credential_env = "NUGET_CONTOSO_TOKEN"

[profiles.contoso_model_1_9]
kind = "nuget"
package = "Contoso.Model"
version = "1.9.0"
target_framework = "net10.0"
source = "https://nuget.pkg.github.com/contoso/index.json"
dependency_sources = ["https://api.nuget.org/v3/index.json"]
credential_env = "NUGET_CONTOSO_TOKEN"

[profiles.data_current]
root = "../contoso-data"
solution = "Contoso.Data.sln"
output_dir = "src/Contoso.Data/bin/Debug/net10.0"
fingerprint_files = ["Directory.Build.props"]

[profiles.data_current.build]
configuration = "Debug"
target_framework = "net10.0"

[profiles.data_current.collect]
projects = ["src/Contoso.Data/Contoso.Data.csproj"]

[policies.contoso-additive]
assemblies = ["Contoso.Data"]

[collections.app_build]
base = "app"

[collections.app_with_current_data]
base = "app"
overlays = ["data_current"]
logical_type_policy = "contoso-additive"
```
