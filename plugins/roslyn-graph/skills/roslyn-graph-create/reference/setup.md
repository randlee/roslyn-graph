# Setup (once per machine)

| Requirement | Check | Install |
|---|---|---|
| Python 3.11+ | `python --version` | python.org or the OS package manager; standard library only |
| .NET SDK able to restore the profiles' target frameworks | `dotnet --list-sdks` | dot.net |
| .NET 8 runtime (the extractor runs on it) | `dotnet --list-runtimes` | dot.net |
| Oxigraph CLI, exactly `[tools].oxigraph` | `oxigraph --version` | `cargo install oxigraph-cli --version <v> --locked` (or set `ROSLYN_GRAPH_OXIGRAPH` to the executable) |
| git | `git --version` | git-scm.com |
| RoslynToRdf extractor | see below | see below |

## RoslynToRdf extractor

The extractor is an installed tool, like Oxigraph. From a checkout of the roslyn-graph repository:

```
dotnet pack src/RoslynToRdf.Cli -c Release -o <folder>
dotnet tool install --global RoslynToRdf --add-source <folder>
```

To update: `dotnet tool update --global RoslynToRdf --add-source <folder>`. Alternatively set
`ROSLYN_GRAPH_EXTRACTOR` to a built `RoslynToRdf.Cli.dll` (useful while developing the extractor).

The extractor's identity is a hash of every DLL beside `RoslynToRdf.Cli.dll`, the .NET runtime it rolls
forward to, and the fixed extraction flags (`--format Turtle --include-private`). Updating the extractor
therefore gives every assembly a new artifact ID on the next generate (see
[artifact-layout.md](artifact-layout.md)); that is intended, because its output can differ.

## Data root

Artifacts live in `<data-root>/.roslyn-graph`. Set the parent once:

```
# Windows (persistent)
setx ROSLYN_GRAPH_DATA_ROOT D:\
# POSIX shells
export ROSLYN_GRAPH_DATA_ROOT=/data
```

or pass `--data-root` to each command. Keep the data root short on Windows: published store paths must
stay within 240 characters (`ARTIFACT_PATH_TOO_LONG`).

## Credentials for private feeds

A NuGet profile's `credential_env` names an environment variable that holds a token. For GitHub
Packages the token needs `read:packages`; with the GitHub CLI logged in as an account that has it:

```
# PowerShell
$env:NUGET_CONTOSO_TOKEN = gh auth token --user <account>
# POSIX shells
export NUGET_CONTOSO_TOKEN=$(gh auth token --user <account>)
```

Never write the token into workspace.toml or any file.
