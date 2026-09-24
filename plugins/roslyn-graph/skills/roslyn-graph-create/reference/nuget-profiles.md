# NuGet profiles

A NuGet profile is complete on its own: the TOML plus this skill are everything needed to produce and
validate its stores.

## Isolated restore

For each profile the skill writes, under `<artifact-root>/cache/nuget/<hash>/`:

- `restore.csproj`: one `<PackageReference Include="<package>" Version="[<version>]" />` for
  `target_framework`, with `RestorePackagesPath=packages`;
- `nuget.config`: `<clear />`, then only `source` and `dependency_sources`.

It runs `dotnet restore` with `ImportDirectoryBuildProps/Targets`, `ImportDirectoryPackagesProps` and
central package management disabled, so nothing from the machine or surrounding folders influences the
result. Credentials come from `credential_env` through NuGet's
`NuGetPackageSourceCredentials_<source>` environment variable, only for `source`.

Any `NU####` warning or error fails the restore (`NUGET_RESTORE_FAILED`), including NU1603/NU1605
(dependency resolved to a different version).

## What gets extracted

The DLLs are the package's **runtime** assets for the restore target in `obj/project.assets.json`, the
same files NuGet would deploy. `lib/<tfm>` is never guessed. A package with several runtime DLLs yields
one component per DLL.

Search directories for the extractor: the package's own asset folder plus the asset folders of every
dependency in the restore graph.

## Checks

| Code | Rule |
|---|---|
| `NUGET_VERSION_MISMATCH` | restore resolved exactly `version` |
| `NUGET_HASH_MISMATCH` | the `.nupkg` SHA-256 equals `sha256` when pinned |
| `NUGET_NUSPEC_MISMATCH` | the `.nuspec` declares the same ID and version |
| `NUGET_SOURCE_MISMATCH` | `.nupkg.metadata` shows the package came from `source` |
| `NUGET_SIGNATURE_INVALID` | `dotnet nuget verify --all` passes for signed packages (unsigned packages are recorded as `signed: false`) |
| `NUGET_NO_RUNTIME_ASSETS` | at least one runtime DLL exists for the target |

## Identity

`nuget | <id> | <version> | <nupkg sha256> | <asset path> | <dependency-set hash> | <restore target> | <dll sha256> | <extractor id>`

The dependency-set hash covers every dependency's ID, version and SHA-512 from the restore, because
resolving different dependencies can change the extracted external-type triples.

## Pinning

Leave `sha256` empty the first time. `generate` returns `pinsToRecord`; write each value into its profile.
After that, a feed that serves different bytes for the same version fails with `NUGET_HASH_MISMATCH`.
Only clear a pin when the user deliberately changes `version`.
