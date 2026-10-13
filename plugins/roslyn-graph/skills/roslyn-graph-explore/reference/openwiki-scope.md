# openwiki-scope: an OpenWiki scope from records

`rg.py openwiki-scope` turns [records](records.md) in the built-in `openwiki-type` schema into the two files
OpenWiki (verified with 0.7.2) reads its scope from. It never runs OpenWiki.

```
python <skill>/scripts/rg.py openwiki-scope --records out/billing.jsonl [--records out/payments.jsonl] \
    [--repository p3] [--repo-root D:/work/p3] [--max-listed-types 400] [--dry-run]
```

| File in the repository | Strength | What is written |
|---|---|---|
| `.openwikiignore` | **enforced**: every OpenWiki read, `ls`, `glob`, `grep` and write is checked | a deny-all chain that opens exactly the declaring files |
| `openwiki/INSTRUCTIONS.md` | **advisory**: read on every run, kept by `--init` and `--update` | the brief: which types to document, and how to reach them |

Both are **managed blocks** between `BEGIN roslyn-graph openwiki-scope` and `END` lines. A new block goes at
the top of the file; a later run replaces it in place. Every other line is kept, so user exclusions after the
block (such as `secrets/`) still apply inside the opened paths. Unpaired markers fail with
`OPENWIKI_BLOCK_BROKEN`.

## Input

- One or more `--records` files (JSONL or a JSON array), each validated against `openwiki-type`. Records with
  the same `name` and `repository` are merged: their files are joined, and the first `locationStatus` in the
  order `found`, `compiler-generated`, `generated`, `nuget` is kept. Concatenating exports therefore gives the
  same result as passing them separately.
- OpenWiki runs on one repository at a time.
  - `--repository` picks the repository, and may be left out when the records hold only one.
  - Records of other repositories are counted in `excluded.otherRepositories`. Run the command again with the
    other repository's ID and checkout to scope it.
- `--repo-root` is the checkout. It defaults to the checkout recorded in the records' `.context.json`.

## Ignore chain

```text
# BEGIN roslyn-graph openwiki-scope (generated; edit below the END line)
*
!/openwiki/
!/src/
/src/*
!/src/Billing/
/src/Billing/*
!/src/Billing/Order.cs
# END roslyn-graph openwiki-scope
```

How the chain works:
- Rules use gitignore style, and the last match wins.
- After `*`, each ancestor directory is re-opened (`!/src/`) and its other children ignored again (`/src/*`).
  OpenWiki's `ls` and `glob` refuse an ignored directory, so every ancestor must be open.
- `/openwiki/` stays writable.
- `found` and `compiler-generated` types open their files.
- `generated` and `nuget` types open nothing.
- A type without files opens its project directories instead, and warns `OPENWIKI_DIRECTORY_FALLBACK`.
- Paths containing `*`, `?`, `!` or `..`, or not repository-relative, fail with `OPENWIKI_PATH_UNSUPPORTED`,
  because no rule would match exactly them.
- Opened paths missing from the checkout warn `OPENWIKI_FILE_MISSING`.

## Brief

The brief contains:
- a scope statement;
- the advice to search from the repository root with a directory-prefixed `glob`. In 0.7.2, a `glob` given a
  search directory returns relative paths that the ignore filter rejects;
- the `found` types, grouped by project directory and namespace, with kind and files;
- counts of compiler-generated and generated types;
- the NuGet dependencies;
- provenance (store, graph, commit, export time) from each records file's `.context.json`.

Above `--max-listed-types` (default 400), the brief lists namespaces with type counts instead, and warns
`OPENWIKI_BRIEF_SUMMARIZED`. The ignore file still opens every file, so the shorter list reduces the advice,
not the scope.

## Result

```json
{"type": "openwiki-scope", "repository": "p3", "repoRoot": "D:/work/p3", "dryRun": false,
 "types": {"inScope": 163, "listed": 88, "found": 88, "compiler-generated": 75, "generated": 0, "nuget": 0},
 "files": 86, "directories": [], "duplicates": 0,
 "excluded": {"otherRepositories": {"XCore": 537}, "external": 0},
 "ignore": {"path": ".../.openwikiignore", "rules": 148}, "brief": {"path": ".../openwiki/INSTRUCTIONS.md", "summarized": false},
 "warnings": []}
```

With `--dry-run` nothing is written, and `ignore.text` and `brief.text` hold exactly what would be.

## Then

In the repository, run `openwiki code --init` for a new wiki or `openwiki code --update` for an existing one.
Both files are part of the checkout, so commit them if the scope should persist for other runs.
