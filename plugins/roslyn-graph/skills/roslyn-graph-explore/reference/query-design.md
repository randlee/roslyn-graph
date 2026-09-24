# Query design

## Store structure

| Store | Named graphs | Default graph |
|---|---|---|
| solution | one graph per component assembly (`urn:roslyn-graph:assembly:<id>`) + `…solution:<id>:metadata` | empty |
| view | the base solution's graphs + one per overlay assembly + `…view:<id>:logical-types` | empty |

Each component graph holds the complete extraction of one assembly: its own types (with
`dt:definedInAssembly` pointing at the graph's single `dt:Assembly`) **and** stub nodes for every
external type it references (framework types, other components' types). The same external IRI therefore
appears in many graphs.

Physical IRIs contain the assembly version: `http://dotnet.example/type/<assembly>/<version>/<metadata name>`.
Two versions of an assembly produce two nodes for the same type. In a view, the logical-types graph links
each physical type of a policy assembly to one `rg:LogicalType` (`rg:logicalType`), which carries
`rg:assemblyName`, `dt:fullName` and `dt:name`.

Solution metadata (`rg:SolutionBuild`, see [../queries/solution-metadata.rq](../queries/solution-metadata.rq))
records the profile, repository, branch, commit, configuration, platform and target framework.

## Rules that keep queries fast

1. **Scope to the defining graph.** Put the type patterns inside `GRAPH ?g { … }` and start from the
   assembly: `?asm a dt:Assembly . ?t dt:definedInAssembly ?asm ; …`. There is one `dt:Assembly` per graph,
   so this enumerates each component's own types exactly once. On a 2.5-million-triple view this pattern
   answers in well under a second; the same question without `GRAPH` scoping ran for minutes.
2. **Do not use `--union`** unless the query is tiny. It makes every pattern match across all graphs.
3. **Avoid `FILTER EXISTS` / `NOT EXISTS` over other graphs** per result row; restructure as a join or
   drop the filter (the explorer ignores edges to nodes that are not exported).
4. **Never combine an outer `VALUES` with `UNION` or `OPTIONAL`.** Oxigraph does not push the `VALUES`
   bindings into the branches: a 60 ms lookup became 10 s with a `UNION` and 87 s with `OPTIONAL` +
   `FILTER`. Run one query per branch instead (the `graph` command does this internally).
5. **Prefer positive patterns to "is not" filters.** "A component's fully extracted type" is
   `?asm a dt:Assembly . ?t dt:definedInAssembly ?asm ; dt:accessibility ?any` (stubs and constructed
   generics have no accessibility), not `FILTER NOT EXISTS { ?t dt:genericDefinition ?d }`.
6. **Measure.** Set `ROSLYN_GRAPH_TRACE=1` to log every Oxigraph call with its duration and query start
   on stderr; stop and restructure any query that takes more than a second or two.
7. **Bound results:** `LIMIT` on SELECTs; narrow CONSTRUCTs to what will be drawn.
8. **Use `VALUES` for class sets** (`VALUES ?class { dt:Class dt:Struct dt:Interface dt:Record }`);
   every type is typed both `dt:Type` and its specific class.

## Patterns

Own types of every component:

```sparql
GRAPH ?g { ?asm a dt:Assembly ; dt:name ?assembly ; dt:version ?version .
           ?t dt:definedInAssembly ?asm ; a dt:Interface ; dt:fullName ?full . }
```

Relationship to a type by name, across all its versions (match the literal, not the versioned IRI):

```sparql
GRAPH ?g { ?asm a dt:Assembly . ?t dt:definedInAssembly ?asm ; dt:implements ?i . ?i dt:fullName "{{INTERFACE}}" . }
```

Only relationships between component types (drop framework targets) — join on the target's own graph:

```sparql
GRAPH ?g  { ?asm a dt:Assembly . ?t dt:definedInAssembly ?asm ; dt:inherits ?base . }
GRAPH ?bg { ?basm a dt:Assembly . ?base dt:definedInAssembly ?basm . }
```

Physical to logical (views):

```sparql
GRAPH ?lg { ?physical rg:logicalType ?logical . ?logical dt:fullName ?full ; rg:assemblyName ?assembly . }
```

Members, parameters and signatures: `dt:hasMember`, then `dt:returnType` / `dt:propertyType` /
`dt:fieldType` / `dt:eventType`, `dt:hasParameter` with `dt:ordinal` and `dt:parameterType`; generic
arguments are nodes reached by `dt:typeArgument` carrying `dt:index` and `dt:type`
(see [ontology.md](ontology.md)).

## Parameters

Query files use `{{NAME}}` placeholders inside string literals. Pass `--param NAME=VALUE`; values are
escaped as literal content, and a missing parameter is an error (`QUERY_PARAM_MISSING`).

## Viewer-ready CONSTRUCT

For the explorer every drawn type needs `a <class>`, `dt:name` and (for grouping) `dt:inNamespace ?ns`
with `?ns dt:name`. Label namespaces with their full name: `?ns dt:fullName ?nsFull` in WHERE and
`?ns dt:name ?nsFull` in the template. Edges are `dt:implements` and `dt:inherits`.
