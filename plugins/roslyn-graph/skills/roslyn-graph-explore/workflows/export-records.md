# Export records (and scope OpenWiki)

Trigger: the user wants the types of a graph or explorer selection as structured data. That might be JSON
lines for another tool, the source files that declare them, or "document these types with OpenWiki".
References: [../reference/records.md](../reference/records.md) and
[../reference/openwiki-scope.md](../reference/openwiki-scope.md).

## 1. Get the types

| The user has | Input |
|---|---|
| a saved or new graph (`rg.py graph`) or a CONSTRUCT export (`rg.py export`) | `--graph out/<name>.nt`; its `.context.json` names the store |
| an explorer selection, pasted or saved (`roslyn-graph-selection/2`) | save it to a file, then `--selection <file>.json`. It holds exactly the types the user drew, so hiding namespaces in the explorer is the interactive filter |
| neither | build a graph first ([visualize.md](visualize.md)), scoped to what they asked for |

Use a **logical** graph from a view when the user wants each type once across versions (P3 with current
Radiant, for example). Its records list every version's assemblies, projects and files.

## 2. Pick or write the schema

- To document with OpenWiki, use `--schema openwiki-type`.
- Otherwise write a schema with only the fields the user needs ([../reference/records.md](../reference/records.md),
  field registry). Fields cost what they fetch: `files` and `locationStatus` run MSBuild for the projects
  involved (cached after the first run), while store fields are cheap. Put the schema in the user's
  workspace, not in the skill.

## 3. Run `records`

```
python <skill>/scripts/rg.py records --graph out/billing.nt --schema openwiki-type --output out/billing.jsonl
```

Narrow it with filters when the graph holds more than was asked for, such as `--kind Interface`,
`--namespace "Billing.*"`, `--origin source` or `--exclude "*Tests*"`. Repeating an option ORs its values;
different options AND.

Read the result:
- `count` is the number of types written.
- `filters.removed` is what each filter dropped.
- `locations.types` shows how many types are `found`, `compiler-generated`, `generated` or `nuget`.
- `locations.cacheHits` counts projects served from the cache.
- `warnings` lists any problems.

If it fails:

| Code | Do |
|---|---|
| `SOURCE_CHECKOUT_DRIFT` | the checkout moved past the build. Ask whether to check out the recorded commit (`context.drift`), or accept files from the current checkout with `--allow-drift` (say that paths may not match the store) |
| `SOURCE_CHECKOUT_MISSING` | the checkout moved; ask where it is, then pass `--repo-root <id>=<path>` |
| `DECLARATIONS_UNSUPPORTED` | the extractor predates the `declarations` command; the user must update it ([setup](../../roslyn-graph-create/reference/setup.md)). Updating changes the extractor ID, so the next `generate` rebuilds every artifact |
| `RECORD_SCHEMA_VIOLATION` | show the first violations; relax the schema or narrow the input |
| `RECORD_AMBIGUOUS_FIELD` | a logical type spans repositories; bind `repositories` instead of `repository`, or use a physical graph |

## 4. Scope OpenWiki (optional)

```
python <skill>/scripts/rg.py openwiki-scope --records out/billing.jsonl --repository p3 --dry-run
```

1. Run with `--dry-run` first and show the user:
   - `types` and `files`;
   - `excluded.otherRepositories`, since each repository needs its own run with its own `--repo-root`;
   - the start of `brief.text`.
2. Then run without `--dry-run`. It writes managed blocks into `<repo>/.openwikiignore` and
   `<repo>/openwiki/INSTRUCTIONS.md` and keeps the user's own lines.
3. Tell the user to run `openwiki code --init` (new wiki) or `openwiki code --update` in the repository.
   `rg.py` never runs OpenWiki.

To combine several graphs, pass several `--records` files, or concatenate JSONL exports. Duplicates are
merged either way.
