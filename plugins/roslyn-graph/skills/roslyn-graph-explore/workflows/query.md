# Query workflow

## 1. Identify the store

Use the manifest the user named, or pick from `rg.py inventory` (solutions and views with status
`latest`). Note from the manifest: component assemblies and versions, and for views the policy
assemblies that have logical types.

## 2. Find the vocabulary

Look up the classes and predicates in [../reference/ontology.md](../reference/ontology.md). Remember:
- a type's `dt:fullName` is its C# display name with namespace and generic parameters
  (`Contoso.Data.IRepository<TItem>`); `dt:name` is the simple name;
- a namespace's `dt:name` is its last segment; use `dt:fullName` for the full namespace;
- external types referenced by a component are present in that component's graph but have no
  `dt:definedInAssembly` pointing at a component `dt:Assembly`.

Unsure what a store contains? Inspect one real node before writing a larger query, for example with
[../queries/find-type.rq](../queries/find-type.rq):

```
python <plugin>/scripts/rg.py query --manifest <manifest.json> --query-file <skill>/queries/find-type.rq --param NAME=Repository
```

## 3. Write the query

Start from the closest file in [../queries/](../queries/) and follow the rules in
[../reference/query-design.md](../reference/query-design.md) — above all, **scope patterns with
`GRAPH ?g { ?asm a dt:Assembly . ?t dt:definedInAssembly ?asm ... }`**. Unscoped patterns over the union
of graphs can take minutes instead of milliseconds.

Save the query in a scratch file and run it:

```
python <plugin>/scripts/rg.py query --manifest <manifest.json> --query-file <file.rq> [--param NAME=VALUE ...] [--limit N]
```

The result has `rowCount`, `truncated` and `rows` (values as strings). `--limit` (default 2000) is enforced
inside Oxigraph: the query runs as a subquery of `SELECT * ... LIMIT limit+1`, so a broad query stops early
and `truncated: true` says more rows exist. Queries stop after `--timeout` seconds (default 120) with
`QUERY_TIMEOUT`; if a query takes more than a few seconds, restructure it rather than raising the timeout.

## 4. Answer

Report what the rows show, including assembly names and versions where they matter. When physical
versions differ (the same `fullName` from two assembly versions), say which version each fact comes from.
