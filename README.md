# RoslynToRdf

Extract .NET assembly type graphs to RDF format (N-Triples or Turtle) for loading into graph databases like Oxigraph.

## Installation

```bash
dotnet tool install --global RoslynToRdf
```

## Usage

```bash
# Basic usage - outputs to MyAssembly.nt
roslyn2rdf MyAssembly.dll

# Specify output file and format
roslyn2rdf MyAssembly.dll -o types.ttl -f turtle

# Custom base URI
roslyn2rdf MyAssembly.dll -b "http://mycompany.com/types/"

# Include private members
roslyn2rdf MyAssembly.dll --include-private

# Verbose output
roslyn2rdf MyAssembly.dll -v

# Add reference paths for dependencies
roslyn2rdf MyAssembly.dll -r /path/to/dependency.dll -s /path/to/deps/

# Require all assembly references to resolve
roslyn2rdf MyAssembly.dll --fail-on-missing-references

# Analyze an evaluated C# source project
roslyn2rdf MyProject.csproj -o source-graph.nt

# Install the bundled Claude Code and Codex skills in a repository
roslyn2rdf skill --install /path/to/repository

# Install for one host, or preview paths without writing
roslyn2rdf skill --install /path/to/repository --claude
roslyn2rdf skill --install /path/to/repository --dry-run

# Supply the solution build context when the project depends on it
roslyn2rdf MyProject.csproj -o source-graph.nt --solution-dir ./ --configuration Debug --platform AnyCPU --target-framework net8.0
```

`skill --install` installs both host plugins by default. Use `--claude` or `--codex` to select one host; the package includes the plugin manifests, skills, scripts, and reference assets.

## Options

| Option | Description |
|--------|-------------|
| `-o, --output` | Output file path (default: assembly name with .nt extension) |
| `-f, --format` | Output format: `ntriples` (default) or `turtle` |
| `-b, --base-uri` | Base URI for IRIs (default: `http://dotnet.example/`) |
| `--include-private` | Include private members |
| `--include-internal` | Include internal members (default: true) |
| `--include-attributes` | Include attribute information (default: excluded) |
| `--exclude-attributes` | Explicitly exclude attributes; incompatible with `--include-attributes` |
| `--exclude-external-types` | Exclude external/referenced types |
| `--extract-exceptions` | Extract exception types from XML docs (default: true) |
| `--extract-seealso` | Extract seealso references from XML docs (default: true) |
| `-r, --reference` | Additional assembly reference paths |
| `--strict`, `--fail-on-missing-references` | Fail on unresolved or unreadable references (DLL inputs only; default: false) |
| `-s, --search-dir` | Additional directories to search for dependencies |
| `--solution-dir` | Solution directory for source-project evaluation (defaults to the project directory) |
| `--configuration` | MSBuild configuration for source-project evaluation (defaults to `Debug`) |
| `--platform` | MSBuild platform for source-project evaluation |
| `--target-framework` | Target framework for source-project evaluation |
| `-v, --verbose` | Verbose output |
| `-q, --quiet` | Quiet output |

For DLL inputs, explicit `-r` files are matched by assembly name rather than filename, and their dependencies are
loaded recursively, including from directories beside those files. Unresolved dependencies and missing
or unreadable `-r` files produce warnings on stderr, including with `--quiet`. Extraction continues and
returns exit code 0 by default, although the graph may be incomplete. Use `--fail-on-missing-references`
to return exit code 1 before extracting an assembly with reference failures. An output file may already
exist, and a combined output may contain earlier assemblies. A missing or invalid target assembly is
always fatal. Both strict aliases are rejected for `.csproj` and `.vbproj` inputs; source projects use MSBuild resolution.

Passing a `.csproj` or `.vbproj` opens the evaluated C# or Visual Basic project with MSBuild and analyzes its Roslyn compilation,
including source syntax and, for C#, the evaluated `AllowUnsafeBlocks` setting. C# projects where that setting is
false still receive the ordinary type graph, while unsafe-method facts are omitted. Source generators
are represented when their generated trees are present in the compilation supplied by the workspace.
The MSBuild options above are passed as project-evaluation properties, without changing the caller's
environment. The `rg` generator supplies `SolutionDir`, `Configuration`, `Platform` and
`TargetFramework` from each solution profile automatically.
Unsafe reason nodes describe a method's own unsafe modifier or unsafe syntax and carry project-relative
source paths with one-based line and column numbers. An unsafe enclosing type contributes to type and
assembly `containsUnsafeCode` aggregates, but does not mark each ordinary method in that type unsafe.
Both source and DLL modes inventory statically bound body type dependencies as `dt:usesType`,
including generic constituents, unsafe pointer signatures and delegate/function-pointer signatures.
This is static analysis, not runtime inference. Source mode retains source-semantic dependencies
that compilation can erase; DLL mode reads emitted IL and does not invent missing source dependencies.
The `.dll` mode does not report source locations or method-body unsafe reason facts.

## RDF Schema

### IRI Patterns

```
Assembly:   http://dotnet.example/assembly/{name}/{version}
Namespace:  http://dotnet.example/namespace/{fullName}
Type:       http://dotnet.example/type/{assembly}/{version}/{fullTypeName}
Member:     http://dotnet.example/type/{...}/member/{name}({signature})
Parameter:  http://dotnet.example/type/{...}/member/{...}/param/{ordinal}
```

Method signatures include generic arity (`M%60%601%28%29` for `M<T>()`) and conversion
operators include their target type (for example, `op_Implicit(C)~System.Int32`).
These signature components are percent-escaped in the IRI. Generic method and
conversion operator IRIs, including their parameter and type parameter IRIs,
have changed to prevent overload collisions.

Member signatures preserve open generic arguments, including generic arguments
on containing types. Generic parameters use ordinal positions with separate
markers for method and type parameters; nested type positions include the outer
types' arities. Thus overloads taking `List<T>` and `List<U>` have distinct member
identities, as do conversions to those targets. This changes affected member and
owned parameter and type parameter IRIs. Function pointer member signatures also
identify parameter and return types recursively, with passing modes and calling
conventions. Graph type nodes keep their existing representation of open generic
constructions as generic definitions.

Array type names preserve rank: `[]` for vectors, `[*]` for non-vector rank-one
arrays, `[,]` for rank two, and `[,,]` for rank three. Nested arrays preserve each
element's shape. Multi-dimensional and non-vector array IRIs, plus signatures
that contain them, have changed; `int[]` and `int[][]` IRIs remain stable.
Rebuild existing graphs to use these corrected identities. Method IRIs
without generic arity, conversion targets, open generic parameters, function
pointers, or affected array types retain their existing format.

### Key Relationships

- `dt:throws` - Exception type that may be thrown (from XML docs `<exception>`)
- `dt:relatedTo` - Related symbol (from XML docs `<seealso>`)
- `dt:inherits` - Type → Base type
- `dt:implements` - Type → Interface
- `dt:hasMember` - Type → Member

## Example SPARQL Queries

### Find methods that throw ArgumentNullException

```sparql
PREFIX dt: <http://dotnet.example/ontology/>

SELECT ?method ?methodName ?typeName WHERE {
  ?method a dt:Method ;
          dt:name ?methodName ;
          dt:throws ?ex ;
          dt:memberOf ?type .
  ?type dt:name ?typeName .
  ?ex dt:name "ArgumentNullException" .
}
```

### Find all classes implementing IDisposable

```sparql
PREFIX dt: <http://dotnet.example/ontology/>

SELECT ?class ?className WHERE {
  ?class a dt:Class ;
         dt:name ?className ;
         dt:implements ?iface .
  ?iface dt:name "IDisposable" .
}
```

## Website

GitHub Pages content lives under `site/`. The landing page and announcements are
hand-edited; the `roslyn2rdf` CLI reference is generated with [docli](https://github.com/randlee/docli)
from a checkout at `./docli` (CI) or a sibling `github/docli` tree (local worktrees):

```bash
git clone https://github.com/randlee/docli.git docli   # once, if not already a sibling
```

```bash
./scripts/regenerate-site.sh
```

That runs `scripts/regenerate-site-cli.sh`, which uses
`tools/RoslynToRdf.DocliExport/` and writes `site/cli/index.html`.

## Building

```bash
cd roslyn-graph
dotnet build
dotnet pack src/RoslynToRdf.Cli -c Release
dotnet tool install --global --add-source src/RoslynToRdf.Cli/nupkg RoslynToRdf
```

## Viewer tests

The standalone RDF viewer accepts both N-Triples and standard Turtle. Its parser tests run with Node.js:

```bash
cd viewer
npm ci
npm test
```

## License

MIT
