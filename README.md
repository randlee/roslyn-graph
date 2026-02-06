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
```

## Options

| Option | Description |
|--------|-------------|
| `-o, --output` | Output file path (default: assembly name with .nt extension) |
| `-f, --format` | Output format: `ntriples` (default) or `turtle` |
| `-b, --base-uri` | Base URI for IRIs (default: `http://dotnet.example/`) |
| `--include-private` | Include private members |
| `--include-internal` | Include internal members (default: true) |
| `--exclude-attributes` | Exclude attribute information |
| `--exclude-external-types` | Exclude external/referenced types |
| `--extract-exceptions` | Extract exception types from XML docs (default: true) |
| `--extract-seealso` | Extract seealso references from XML docs (default: true) |
| `-r, --reference` | Additional assembly reference paths |
| `-s, --search-dir` | Additional directories to search for dependencies |
| `-v, --verbose` | Verbose output |
| `-q, --quiet` | Quiet output |

## RDF Schema

### IRI Patterns

```
Assembly:   http://dotnet.example/assembly/{name}/{version}
Namespace:  http://dotnet.example/namespace/{fullName}
Type:       http://dotnet.example/type/{assembly}/{version}/{fullTypeName}
Member:     http://dotnet.example/type/{...}/member/{name}({signature})
Parameter:  http://dotnet.example/type/{...}/member/{...}/param/{ordinal}
```

### Key Relationships

- `tg:throws` - Exception type that may be thrown (from XML docs `<exception>`)
- `tg:relatedTo` - Related symbol (from XML docs `<seealso>`)
- `tg:inherits` - Type → Base type
- `tg:implements` - Type → Interface
- `tg:hasMember` - Type → Member

## Example SPARQL Queries

### Find methods that throw ArgumentNullException

```sparql
PREFIX tg: <http://typegraph.example/ontology/>

SELECT ?method ?methodName ?typeName WHERE {
  ?method a tg:Method ;
          tg:name ?methodName ;
          tg:throws ?ex ;
          tg:memberOf ?type .
  ?type tg:name ?typeName .
  ?ex tg:name "ArgumentNullException" .
}
```

### Find all classes implementing IDisposable

```sparql
PREFIX tg: <http://typegraph.example/ontology/>

SELECT ?class ?className WHERE {
  ?class a tg:Class ;
         tg:name ?className ;
         tg:implements ?iface .
  ?iface tg:name "IDisposable" .
}
```

## Building

```bash
cd roslyn-graph
dotnet build
dotnet pack src/RoslynToRdf.Cli -c Release
dotnet tool install --global --add-source src/RoslynToRdf.Cli/nupkg RoslynToRdf
```

## License

MIT
