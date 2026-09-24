# Saved queries and graphs: list, run, save, update, check

Users keep reusable explorations in their workspace, beside `workspace.toml`:

```
<workspace>/.roslyn-graph/
  workspace.toml
  queries/<name>.rq            SELECT or CONSTRUCT queries
  graphs/<name>.graph.toml     traversal graphs (see ../reference/graph-definitions.md)
  graphs/out/                  generated .nt/.html (derived; suggest adding it to .gitignore)
```

Names are lower-case, hyphenated and describe the result (`measurement-database-closure.graph.toml`,
`implementers-of.rq`).

## List

```
python <plugin>/scripts/rg.py saved list --workspace <workspace>/.roslyn-graph/workspace.toml
```

Returns (`type: "saved"`) every query with its title, store, kind (`select`/`construct`), parameters
(description and example) and header `problems`, and every graph definition with its title and store.
Use it to answer "what saved queries do I have?" and to find a query before writing a new one.

## Run

- SELECT: `rg.py query --manifest <manifest> --query-file <file.rq> --param NAME=VALUE ...`
- CONSTRUCT: `rg.py export ... --output <out>.nt [--logical]`, then `rg.py render --data <out>.nt --output <out>.html --open`
- Graph: `rg.py graph --definition <file.graph.toml> --open`

The manifest is the latest artifact of the query's `# Store:` collection (`rg.py inventory`, status
`latest`; views for collections with overlays, otherwise solutions).

## Save a new query

Save when the user asks, or offer to when a request will clearly be repeated. Only save a query after it
ran successfully and the user accepted the result.

1. Start the file with this header (exact keys; `Description` optional):

   ```sparql
   # Title: Implementers of an interface
   # Store: app_with_current_data
   # Description: every implementer in all physical versions, viewer-ready.
   # Parameters:
   #   INTERFACE  full name of the interface (example: Contoso.Data.IRecord)
   PREFIX dt: <http://dotnet.example/ontology/>
   CONSTRUCT { ... }
   ```

   - `Store` is a collection name from `workspace.toml`, never a path or artifact ID, so the query keeps
     working after the collection is regenerated.
   - Replace values the user may vary with `{{NAME}}` placeholders inside string literals, and declare
     each one under `Parameters` with a real `(example: ...)` value from the store. `saved check` runs
     the query with those examples.
2. Write it to `<workspace>/.roslyn-graph/queries/<name>.rq`.
3. Run `saved list`; the new entry must show `problems: []`.

For a traversal ("these types, their implementations and everything they reference") save a
`.graph.toml` in `graphs/` instead ([../reference/graph-definitions.md](../reference/graph-definitions.md)).

## Update

1. Run `saved list` to read the current header and parameters.
2. Edit the query or definition; keep the header in sync (add/remove parameters, refresh examples, update
   the title if the meaning changed). Do not rename a file the user refers to by name without asking.
3. Run it once with the example parameters, show the user the difference, then run `saved check`.

## Check after regeneration or ontology changes

```
python <plugin>/scripts/rg.py saved check --workspace <workspace>/.roslyn-graph/workspace.toml
```

Runs every saved query with its example parameters and every graph definition against the latest store
of its collection. Each result has `status`: `pass`, `empty` (a SELECT returned no rows: the example may
no longer exist) or `fail` with the problems. Outputs go to `graphs/out/check/`. Run it after `generate`
(new versions) and after changing the ontology; fix failures by updating the query or its examples.
