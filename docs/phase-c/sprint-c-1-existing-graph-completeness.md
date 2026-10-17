# Sprint c-1 - Existing graph completeness

```yaml
id: c-1
closure_type: integration
target_boundary: rg-query-and-existing-graph
branch: sprint/c-1-existing-graph-completeness
recommended_agent: codex-developer
recommended_model: gpt-6.1-sol
parallel_safe: [c-2]
must_follow: []
vertical_rationale: bounded defect fixes in the existing query/traversal path, with its CLI and real-store tests
```

## Scope boundary

Every listed deliverable must land production-ready for this sprint's integration boundary; no stubs or silent deferral.

Own reviewed changes 1, 2, 5 and 6: remove tool-injected caps and follow existing pointer, constraint and enclosing-type facts. No extractor or ontology redesign. Query, traversal and export return the requested result by default; only explicit user limits cut it. Report cuts as partial and execution/resource failures as failures. Existing batches drain normally; they are not result caps.

## Owned paths

- `tools/rg/rg.py`
- `tools/rg/roslyn_graph/{traverse,explore}.py`
- `tools/rg/tests/{test_traverse,test_explore_maintain,test_saved,test_docs_contract}.py`
- `tools/rg/tests/test_phase_c_existing_graph.py`
- `.github/workflows/ci.yml` (existing plugin-matrix prerequisites for real-store tests)
- `plugins/roslyn-graph/skills/roslyn-graph-{create,explore}/scripts/rg.py`
- `plugins/roslyn-graph/skills/roslyn-graph-{create,explore}/scripts/roslyn_graph/{traverse,explore}.py`
- `plugins/roslyn-graph/skills/roslyn-graph-explore/queries/{find-type,logical-versions,unsafe-aggregates,unsafe-methods}.rq`
- `plugins/roslyn-graph/skills/roslyn-graph-explore/reference/graph-definitions.md`

Paths to delete: none. Edits to other paths require a demonstrated missing call site, not opportunistic cleanup.

## Authoritative deliverables

### D1. Unlimited defaults and explicit limit behavior

Landing: `tools/rg/roslyn_graph/traverse.py: Definition, parse_definition, expand`; `tools/rg/roslyn_graph/explore.py: query, export`; `tools/rg/rg.py: parser, cmd_export`. Apply the same edits to the packaged create/explore Python copies.

```python
max_types: int | None
max_types = expand.get("max_types")
if d.max_types is not None and len(seen) + len(added) > d.max_types:
    ...
```

Omitted `max_types` is unbounded; explicit values must be positive. Keep `max_depth=0` unlimited. Preserve existing explicit positive limits. When an explicit type cap stops expansion, retain `truncated=True` and the cut reason; do not report closure.

Fix the positive-depth exit in `expand`: when the depth bound is reached with a frontier and no earlier cut, probe that frontier once using the same follow, inverse, `_underlying` and `_own_names` logic. Do not add probe targets to `seen`. Any eligible target outside `seen` sets `truncated=True` with `stopped: "max_depth=<n>"`; retain probe edges whose endpoints are already selected, including cycle back-edges. If no eligible target is omitted, report complete. This is bounded lookahead, not recursive expansion or a new default depth.

```python
limit: int | None = None
query_text = text if limit is None else bounded_select(text, limit)
truncated = limit is not None and len(rows) > limit
selected = rows if limit is None else rows[:limit]
```

Keep SELECT-form validation on both branches. Set CLI `--limit` default to `None`; reject explicit nonpositive limits. Set export `max_triples: int | None = None`; add optional positive `--max-triples`, pass it through `cmd_export`, and guard only the existing `EXPORT_TOO_LARGE` check. Preserve loud timeout failures and existing `--unbounded` compatibility; reject `--unbounded` combined with `--max-triples` rather than ignoring the explicit limit. No ontology changes.

**Saved queries:** remove built-in `LIMIT` clauses from `plugins/roslyn-graph/skills/roslyn-graph-explore/queries/{find-type,logical-versions,unsafe-aggregates,unsafe-methods}.rq`. Do not rewrite user-supplied SPARQL or remove explicit user limits.

Update the owned `reference/graph-definitions.md` example/default and result-reporting sections: omitted `max_types` is unlimited, explicit finite values remain examples rather than defaults, and `truncated` includes depth cuts. Document optional `--max-triples` and its conflict with `--unbounded`; preserve explicit saved limits. Extend `test_docs_contract.py` to check these changed default/option descriptions against the CLI/definition contract.

### D2. Pointer constituents

**Change:** `tools/rg/roslyn_graph/traverse.py: _underlying`, plus its packaged copies.

Existing API/triple in `AssemblyGraphExtractor.Helpers.cs: EnsurePointerTypeEmitted` stays unchanged:

```text
IPointerTypeSymbol.PointedAtType
    -> <pointer> dt:pointerElementType <pointed-at type>
```

Add exactly this pattern to the existing iterative wrapper expansion:

```sparql
?t dt:pointerElementType ?r
```

No new ontology term or extractor edit.

### D3. Constraints

**Change:** `traverse.py: FOLLOW, INVERSE_FOLLOW, parse_definition`, plus packaged copies. Extraction remains unchanged:

```text
ITypeParameterSymbol.ConstraintTypes
    -> <owner> dt:hasTypeParameter <parameter>
    -> <parameter> dt:constrainedToType <constraint>
```

Set omitted follow to `["base_types", "interfaces", "member_types", "parameter_types", "constraints", "enclosing_type"]`. Keep `attributes` absent unless explicitly requested; do not turn it on when adding `constraints`. Define:

```sparql
?t dt:hasTypeParameter ?parameter . ?parameter dt:constrainedToType ?r
?t dt:hasMember ?method . ?method dt:hasTypeParameter ?parameter .
?parameter dt:constrainedToType ?r
```

Add inverse forms to `referenced_by` by exchanging only endpoint variables `?t` and `?r`. Keep explicit saved follow lists unchanged. Retain `expand`'s frontier/seen sets and `_underlying`'s stack/visited sets; drain every `_pairs` batch, including cycle back-edges. Document `constraints` in `plugins/roslyn-graph/skills/roslyn-graph-explore/reference/graph-definitions.md`; retain `test_every_follow_relation_is_documented`. No new ontology.

### D4. Enclosing type

**Change:** `traverse.py: FOLLOW, parse_definition`, plus packaged copies.

```text
INamedTypeSymbol.ContainingType -> <Inner> dt:nestedIn <Outer>
```

Keep extraction unchanged. Add `enclosing_type` to default follow:

```sparql
?t dt:nestedIn ?r
```

Keep explicit saved follow lists unchanged. Do not add an inverse-follow rule in this fix. Document `enclosing_type` in `plugins/roslyn-graph/skills/roslyn-graph-explore/reference/graph-definitions.md` for the existing follow-key documentation test.

## Authoritative acceptance criteria

Source fixtures use a temporary test-local .NET harness referencing the existing Core project: construct C#/VB `Compilation` with `CSharpCompilation.Create` / `VisualBasicCompilation.Create` and call the existing `AssemblyGraphExtractor.Extract(compilation, compilation.Assembly)`. DLL cases use the existing extractor CLI. The Python fixture owns this harness in its temporary directory; it neither edits c-2's `TestUtilities.cs` nor requires c-2's new `.vbproj` CLI support.

- **AC1 [req:TX-G19; anchor:no-silent-truncation].** update `test_valid_definition_and_defaults` in `tools/rg/tests/test_traverse.py` to assert `max_types is None` and the default follow keys added below. Extend traversal and query/export tests: default selection exceeds 1,500 types; default SELECT returns 2,500 rows; default export returns 600,000 triples. Explicit limits still stop/report partial or fail loudly as appropriate. Execute the four shipped queries with more matches than their former limits and assert all matches. Simulated query/export failure never returns a success result containing partial data. Existing batching remains unchanged.
- **AC2 [req:TX-G07, pointer portion].** A real extracted `unsafe struct S { P** F; } struct P {}` plus Decoy reduces from S to exactly fixture types {S, P}, with S -> P and no Decoy; existing array/generic tests remain green.
- **AC1-depth [req:TX-G19].** A -> B -> C at `max_depth=1` selects {A,B} and reports the depth cut; A -> B with no successor reports complete at 1. A -> B -> A retains both edges and terminates complete. Omitted/zero depth selects the entire chain. Run equivalent inverse-follow cases; explicit saved depth remains honored.
- **AC3 [req:TX-G01, TX-G06].** Real C# `S<T> where T : IFoo` and VB `S(Of T As IFoo)` select exactly fixture types {S, IFoo}; C# `H.M<U>() where U : IBar` and VB `H.M(Of U As IBar)` select {H, IBar}. Run each as source and compiled DLL input. Assert the hasTypeParameter/constrainedToType facts and reduction edges, excluding Decoy. Existing array/generic-argument cases stay green; AC2 unsafe-pointer syntax is C#-only, not a VB exclusion for equivalent supported constructs.
- **AC4 [req:TX-G01, TX-G06].** Real C#/VB nested-type fixtures in source/DLL modes select {Outer.Inner, Outer} with Inner -> Outer; disconnected OtherOuter.OtherInner is absent. Explicit saved follow lists remain unchanged. These fixtures require equal C#/VB semantics, not language-specific spelling.
- **AC5 [req:TX-G04, TX-O01].** Use `explore.export` with `CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }`, union=true, logical=false. Compare the full source fixture RDF set, including `rdf:type`, `dt:hasMember`, `dt:memberOf`, `dt:returnType`, `dt:fieldType`, `dt:definedInAssembly`, `rg:builtFromProject` and constraint/pointer/nesting facts. Assert existing `.context.json` `source.manifest`, `source.store`, `source.artifactId` identify the artifact; typed RDF and source context are distinct assertions. The exact default follow list excludes attributes; explicit attributes follow selects its attribute-only target. c-3 tests inverse filtering.
- **AC6 [req:TX-G02].** In the >1,500-type regression use `[seeds].patterns = ["*"]` against a single-library fixture extracted with the existing `--include-private` wrapper. Assert every fixture-owned type is selected, including internal/nested types, and `member_lines` preserves every declared member, including a private uncalled method. Expected membership comes from hand-authored fixture declarations, not reachability from an entry point. c-3 adds the separately registered dependency-library case.

## Authoritative validation

Run from repository root with Python/pytest, .NET SDK and Oxigraph installed. A skipped required real-store case is not a pass.

In the owned `test_phase_c_existing_graph.py`, use a mandatory session fixture that fails when `dotnet`/`oxigraph` is unavailable or Oxigraph differs from the fixture pin `0.5.8`; do not use the optional `requires_oxigraph` marker.

In `.github/workflows/ci.yml`'s existing `plugin` OS matrix, before Python tests, add .NET SDK 8/10 setup and Rust setup, install `oxigraph-cli` with `cargo install oxigraph-cli --version 0.5.8 --locked` (the existing fixture/config version), and build `RoslynToRdf.sln --configuration Release`. Keep the Windows/macOS/Linux matrix, Python and viewer steps. Verify the existing `tools/rg/tests` invocation collects and executes the mandatory module on every OS; c-1 must pass CI without waiting for c-3.

```powershell
python -m pytest tools/rg/tests/test_traverse.py tools/rg/tests/test_explore_maintain.py tools/rg/tests/test_saved.py tools/rg/tests/test_docs_contract.py tools/rg/tests/test_phase_c_existing_graph.py -q
python -m pytest tools/rg/tests scripts/tests -q
python scripts/check_plugin_sync.py
dotnet build RoslynToRdf.sln --configuration Release
```

Use the existing sync script to copy only changed masters; do not edit generated copies independently. QA checks D1-D4 against code/test diffs: every change has a named verified defect, exact query or default change and positive/negative oracle. No example is treated as a new defect; no working extractor, identity or batching path is replaced.

## Non-closure

This sprint repairs existing signature/generic/pointer traversal. c-2 D1/D2/D5 emit missing delegate/function-pointer/body facts; c-3 D1/D2 consume them and D6 admits separately registered databases by bound identity. Those are mandatory successor contracts, not omissions from the completed inventory. Preserve existing physical type/assembly IRIs for that handoff. No extractor, viewer, classification or diagnostics redesign here.
