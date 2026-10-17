# Sprint c-3 - New fact integration

```yaml
id: c-3
closure_type: integration
target_boundary: rdf-to-reduction-export
branch: sprint/c-3-new-fact-integration
recommended_agent: codex-developer
recommended_model: gpt-6.1-sol
parallel_safe: []
must_follow: [c-1, c-2]
vertical_rationale: integrate new RDF with production reduction/export
```

## Scope boundary

Consume c-2 delegate/function-pointer/usesType facts with c-1 unlimited/constraint/pointer/enclosing rules. Close consumer changes 3/4/7/9 and verified analyzed-dependency/external-identity gaps. Preserve c-1 limits/errors: no implicit caps, partial-as-complete output or replacement extraction.

## Owned paths

- `tools/rg/roslyn_graph/traverse.py`
- `tools/rg/roslyn_graph/records.py`
- `tools/rg/tests/{test_traverse,test_docs_contract}.py`
- `tools/rg/tests/test_records.py`
- `tools/rg/tests/test_phase_c_integration.py`
- `plugins/roslyn-graph/skills/roslyn-graph-{create,explore}/scripts/roslyn_graph/traverse.py`
- `plugins/roslyn-graph/skills/roslyn-graph-{create,explore}/scripts/roslyn_graph/records.py`
- `plugins/roslyn-graph/skills/roslyn-graph-explore/reference/graph-definitions.md`
- `ontology/roslyn-graph.ttl`
- `plugins/roslyn-graph/skills/roslyn-graph-explore/ontology/roslyn-graph.ttl`
- `plugins/roslyn-graph/skills/roslyn-graph-explore/reference/ontology.md`
- `.github/workflows/ci.yml`

No deletions/same-wave overlaps. Overlapping c-1/c-2 contracts must be pushed and their PRs land first.

## Authoritative deliverables

### D1. Function-pointer and delegate selection

In `traverse._underlying`, add:

```sparql
?t dt:signatureReturnType ?r
?t dt:signatureParameter ?parameter . ?parameter dt:parameterType ?r
?t dt:callingConventionType ?r
```

Use c-2 Type -> Parameter shape, no Method-domain hasParameter on Type or IRI parsing. Keep delegate Invoke member_types/parameter_types and c-1 pointer/array/generic expansion.

### D2. Body selection and export

Add `FOLLOW["body_types"]` and default follow:

```sparql
?t dt:hasMember ?member . ?member dt:usesType ?r
```

Add `?r dt:hasMember ?member . ?member dt:usesType ?t` to referenced_by. Preserve saved follow lists. Document/test body_types defaults in graph-definitions.md and existing tests.

`traverse.member_lines`: emit `_pairs(store, members, "?t dt:usesType ?r")` unchanged. Extend only roslyn-graph.ttl's rg:references derivation comment for body use. Export self-use; exclude projected self-edges.

### D3. Attribute inverse policy

`expand`: include both attribute-origin referenced_by patterns only if `"attributes" in d.follow`. Other inverse/forward patterns and published attribute triples remain unchanged.

### D4. Real producer/store regression

`test_phase_c_integration.py`: build c-2 fixtures, run real extractor CLI, load via existing Oxigraph support, call production reduction/export. Add Oxigraph/test execution to existing dotnet/Python CI; no skips/new runner.

**Samples [TX-G01/G02/G07-G14; TX-C04-C08/C12; TX-V01-V04/V06-V07].** Reuse c-2's planned `tests/RoslynToRdf.Tests/Fixtures/PhaseC/**`, D/Ret/Arg, A<T>/B<T>, PrivateOnly/Decoy. Filenames unassigned; rows specify oracles, not existing files. Build C#/VB; extract source/DLL independently. Sets exclude separately asserted framework/generated types; every case excludes disconnected Decoy.

| Case / producer contract | Exact consumer oracle |
| --- | --- |
| C#/VB D(Arg) -> Ret, c-2 D1 | Seed D: {D, Arg, Ret}; preserve Invoke ownership and parameter ordinal 0. Func/Action cases use the same Arg/Ret constituents while framework delegate definitions remain external. |
| C#/VB generic signature, c-2 D5 + c-1 constraints | GenericRoot contains Box<Arg>; Box<T> constrains T to Constraint and Arg derives Constraint. Seed GenericRoot: {GenericRoot, Box<T>, Arg, Constraint}; generic placeholders are not concrete targets. |
| C#/VB private allocation, c-2 AC4 | Root.NeverCalled contains only `new PrivateOnly()` / `New PrivateOnly()`: {Root, PrivateOnly}, owner NeverCalled. Do not execute Root or include the target in a root signature. |
| C#/VB foreach/For Each, c-2 AC8 | LoopRoot uses Sequence -> Enumerator -> Element: {LoopRoot, Sequence, Enumerator, Element}. Assert GetEnumerator/MoveNext/Current-selected targets, not a similarly named disconnected Decoy enumerator. |
| C#/VB explicit await, c-2 AC8 | AwaitRoot awaits Awaitable using extension helper AwaitExtensions, returning Awaiter then AwaitResult: {AwaitRoot, Awaitable, AwaitExtensions, Awaiter, AwaitResult}. Assert extension-bound helper, not name-matched alternatives. |
| C# unsafe/callables, c-2 D2 | S has Arg* and delegate*<Arg, Ret>: {S, Arg, Ret}; convention types external. A<T>/B<T> retain distinct generic-owner identities; nested/repeated signature positions remain distinct. No nonexistent VB pointer syntax fixture. |
| C# compiler-bound disposal, c-2 AC8 | UsingRoot uses ref-struct Resource.Dispose: {UsingRoot, Resource}. AsyncUsingRoot uses AsyncResource.DisposeAsync -> DisposeAwaitable -> DisposeAwaiter: those four types only. AsyncLoopRoot uses AsyncSequence/AsyncEnumerator plus MoveAwaitable/MoveAwaiter and DisposeAwaitable/DisposeAwaiter: exactly root plus those six targets. Assert implicit-await targets even when ChildOperations omits them. |
| Ownership/mode controls, c-2 AC4/AC5 | InitRoot field/property initializer uses InitOnly: {InitRoot, InitOnly} in both modes, source owner field/property versus IL .ctor/.cctor. Async/iterator/lambda/captured-closure and C# local-function body-only targets map to original owner; two owners sharing a generated method retain both edges, separate lambdas sharing a cache never cross-contaminate. NameofRoot mentions NameofOnly only in nameof/NameOf: source {NameofRoot, NameofOnly}, DLL {NameofRoot}. |

Use existing test filters; vary Debug/Release/PDB for lowering/erasure. Hand-author owner/predicate/target oracles before reduction/after export, never production-derived. D5-D7 cover library/package/boundary/missing/ambiguous artifacts; AC3/AC6 attributes/strict. No producer duplication.

### D5. Complete library and composed dependency regressions

In `test_phase_c_integration.py`, add `test_full_library_inventory_includes_private_uncalled_members` and `test_composed_analyzed_dependency_closure`. Preserve `extractor.extract` FLAGS (`--include-private`, internals on), `AssemblyGraphExtractor.GetAllTypes`/`type.GetMembers()`, `build.compose`/`build.build_view`/`traverse.run`. No execution/public-only filter.

Whole-library A: query all roots by physical assembly IRI; put returned full names in `[seeds].types`, `implementations = "none"`, no limits, members default on:

```sparql
SELECT DISTINCT ?t ?full WHERE { GRAPH ?g {
  <A-assembly-IRI> a dt:Assembly .
  ?t dt:definedInAssembly <A-assembly-IRI> ; dt:accessibility ?access ; dt:fullName ?full .
} }
```

Run `python tools/rg/rg.py graph --definition <fixture.graph.toml> --output-dir <out>`. Exact own types: {A.Root, internal A.Hidden, private nested A.Root.PrivateNested, A.PrivateOnly}. Root declares instance/static constructors, public Run, private NeverCalled, property Value, field State, event Changed: assert `dt:hasMember` and c-2 accessor ownership. NeverCalled alone uses A.PrivateOnly; separately seed Root alone to prove body reachability, not whole-library seeding. Synthesized declarations follow c-2 source/IL oracle, not assumed equality.

Compose A/P/Q with `build.compose`/`build.build_view`; seed A.Root only. Root uses P.Entry; Entry's uncalled private member uses Q.Leaf. `_own_names`: `VALUES ?t { <referenced-physical-IRI> } GRAPH ?g { ?asm a dt:Assembly . ?t dt:definedInAssembly ?asm ; dt:accessibility ?access ; dt:fullName ?full }`. Default body_types selects {A.Root, P.Entry, Q.Leaf}, not P.Decoy/Q.Decoy. Assert original `dt:usesType` and manifest graph/artifact provenance; never seed P/Q wholesale. D6 tests databases absent from the view.

### D6. Admit referenced definitions from registered, already-analyzed artifacts

Defect: one-store `traverse.run`/`_own_names` miss separate assemblies. Add read-only `traverse.DependencyStores` for `_pairs`/`_inverse_pairs`/`_own_names`/`find_seeds`/export. Preserve batching/iterative frontier/visited; no engine replacement, published-store mutation or regeneration.

- `DependencyStores.registered(root, definition, manifest)` reads `config.load` once. Registered means selected collection base/overlay profiles plus packages of every selected solution profile, matching `plan.build_plan`, not DLL/cache contents. Enumerate sorted `(root / "assemblies").rglob("manifest.json")`; call `artifacts.read_manifest(path)` in a per-path try/except `(RgError, UnicodeError)`, recording unreadable paths and continuing. Reject non-dict JSON before field access. Do not use `iter_manifests`, whose generator aborts on its first corrupt file. Admit published schema-2 assembly manifests matching resolved `workspace.path` and registered profile. Explicit-manifest input uses recorded workspace/collection; if unavailable, retain listed components and report unresolved registration. No unrelated workspaces, build-plan execution, regeneration, restore/download or extraction. Example: selected solution A's overlay profile registers package P, and P has a published schema-2 artifact in that workspace; P is a candidate, admitted only after the identity/TFM checks below. A cached but unregistered package E is not a candidate and remains an external boundary.
- Index by `dt:definedInAssembly` and exact referenced physical type IRI, never names. Query `SELECT ?name ?version ?culture ?token WHERE { <assembly-IRI> dt:name ?name ; dt:version ?version . OPTIONAL { <assembly-IRI> dt:culture ?culture } OPTIONAL { <assembly-IRI> dt:publicKeyToken ?token } }`. Standalone assemblies use default graph; solutions/views wrap patterns in `GRAPH ?g`. Compare available bound name/version/culture/token; require configured TFM and supported ontology namespace/schema. No inferred version compatibility or same-name substitution. Different extractor hash alone is allowed; unavailable capabilities report incomplete coverage, never false from absent `dt:usesType`.
- Existing manifests have no affirmative body-coverage certificate. Missing coverage evidence means unknown/incomplete, even when some `dt:usesType` triples exist; neither their presence nor an extractor hash proves full analysis. Keep usable known facts. Do not invent a capability field or claim this sprint supplies extraction-completeness certification.
- `resolve(refs)` probes only frontier-unresolved refs with `VALUES ?t { ... } ?t dt:definedInAssembly ?asm ; dt:accessibility ?access ; dt:fullName ?full . ?asm a dt:Assembly` in candidate default graphs. Exactly one compatible artifact admits the definition; deduplicate identical artifact IDs. Multiple distinct candidates: retain reference, report candidate IDs, continue other branches. Missing/incompatible/unreadable registrations likewise report; no newest/name fallback or new graph `--strict` (c-2 strict stays extractor-only).
- Add each store once; `_pairs` unions/deduplicates original named-graph and admitted default-graph tuples for selected subjects only. Reached P.Entry follows all members, including private uncalled bodies, then Q in the next frontier; unrelated P types remain excluded. Type/artifact visited sets terminate cycles; batching never caps results.
- Context `additionalComponents` pins `artifactId`, `graphIri`, `manifestPath`, `origin`, `package`, `assembly`, plus diagnostics/incomplete-coverage status; source manifest stays unchanged. `records.Store` reads pins from `GraphInput.context`, validates IDs on reopen, and routes `pairs`, `own_graphs`, `own_by_name`, `logical_types` and component provenance through that context, never rediscovering newer artifacts. Physical IDs stay physical. Logical output uses `build.logical_iri` for newly admitted own types and pins physical-to-logical mappings for reopening; preserve the existing view's mapping policy.

### D7. Retain external boundary identity without expanding package contents

Defect: `expand` drops non-own targets; `export_lines` omits their identity. After D6, collect unresolved named targets of enabled relations separately from selected components, never in the frontier/type count. Export original owner/predicate/target and existing ontology identity:

```sparql
VALUES ?t { <boundary-or-selected-type-IRIs> }
?t dt:definedInAssembly ?assembly .
OPTIONAL { ?t dt:name ?name }
OPTIONAL { ?t dt:fullName ?full }
OPTIONAL { ?t dt:typeKind ?kind }
```

Copy present `rdf:type`, `dt:definedInAssembly`, `dt:name`, `dt:fullName`, `dt:typeKind` and assembly `dt:name`, `dt:version`, `dt:culture`, `dt:publicKeyToken`. c-2 emits new-stub assembly literals; legacy stubs retain assembly IRI and report missing fields, never parse IRIs or invent metadata. Preserve connecting wrapper/signature witnesses: `dt:genericDefinition`, `dt:typeArgument`/`dt:type`, `dt:pointerElementType`, `dt:arrayElementType` and c-2 signature relations. Attribute-only boundaries remain opt-in. Keep component `rg:references`; external evidence is typed RDF plus context `externalReferences` (owner, predicate, target, assembly, reason, known manifest package identity). Never invent NuGet IDs from assembly names.

`records.read_graph` / `resolve_units` exclude only context-listed external keys from own-component inventory, retaining their evidence in records provenance. Do not suppress other `RECORDS_TYPE_NOT_IN_STORE` errors. A/P/Q remain movable records; E remains dependency evidence. Missing/ambiguous registrations mean incomplete coverage; ordinary unregistered packages are intentional boundaries. Resource/query failure fails, never returns complete partial output.

## Authoritative acceptance criteria

- **AC1 [req:TX-G08].** D selects {D, Ret, Arg}; function-pointer S selects {S, Arg, Ret}; assert external convention targets. Store retains ref/convention/position facts and distinct nested/repeated/generic-owner identities. No Decoy.
- **AC2 [req:TX-G01, TX-G09-TX-G14].** Reduce C#/VB source/DLL counterparts: hand-authored body_types/inverse relationships include generic/delegate constituents; pointers C#-only. Uncalled `new AllocOnly()` selects AllocOnly without execution. Export exact owner/usesType/target; source erasure/initializer-owner differences use c-2 oracles, not false equality. Compile only, never execute to infer targets.
- **AC3 [req:TX-O01].** From attribute-containing stores, default inverse excludes attribute-only consumers; opt-in includes them. Same type's signature/body uses remain selectable with attributes off.
- **AC4 [req:TX-V02, TX-V03, TX-V06].** Independent positive/negative sets cover generated ownership, shared lambda caches, decoys, unexecuted methods and self-use without projected self-edges. Validate actual predicates against ontology; prose is not evidence.
- **AC5 [anchor:no-silent-truncation; req:TX-G19 regression].** Real producer/store body chain >1,500 types is complete with omitted limits. Explicit cuts report partial/reason; simulated resource/query failure fails, never partial-as-complete. Cycles/batches impose no cap. Keep c-1 query/export regressions.
- **AC6 [req:TX-O04].** Real missing-reference CLI: default retains facts/diagnostics; --strict/--fail-on-missing-references fail identically. Source rejection explicit. Test c-2 alias, no second resolver.
- **AC7 [req:TX-G02; anchor:ANC-007].** D5 A root/member sets match oracle, including private/internal/nested/uncalled declarations. Reached P.Entry includes other private members' dependencies regardless of calls. No entry-point execution filter.
- **AC8 [req:TX-G16; anchor:ANC-009].** D5 A -> P -> Q closure/provenance/decoys match physical/logical output. Repeat A-only store with separate registered P/Q: exactly {A.Root, P.Entry, Q.Leaf}, including private uncalled P body, cross-artifact facts, no decoys. P -> A cycle terminates. Wrong version/token/TFM/other workspace never substitute; two matching artifacts report ambiguity while other branches finish. Old facts remain usable; absent body capability remains incomplete.
- **AC9 [req:TX-G17; anchor:ANC-010].** A.Root references unregistered E.External with cached DLL. Export E identity/typed edge as boundary, never expand/count movable. No restore/download/`build.run_all`/`plan.build_plan`/`extractor.extract` during reduction. Legacy missing identity diagnoses. Attributes off/on control attribute-only boundaries.
- **AC8-catalog [req:TX-G16/G18].** Admit Q via overlay packages. Malformed JSON, invalid UTF-8 and non-object manifests preceding Q diagnose without hiding Q. Zero/partial-body legacy facts remain usable, coverage unknown; usesType presence never certifies completeness.
- **AC10 [req:TX-G02, TX-G16, TX-G17].** `rg.py records --graph <out.nt> --schema <fixture.schema.json> --output <out.jsonl>` reopens pinned A/P/Q records, retaining E provenance. Catalog changes never alter pins; deleted/mismatched artifacts fail, no rediscovery/guess/removal. Verify `dt:definedInAssembly`, package/source provenance and original owner-to-type RDF against producer/store.

## Authoritative validation

Require repo .NET SDK, Python/pytest, Oxigraph, Node/npm viewer regression tools. Missing tools never justify required-test skips.

```powershell
dotnet build RoslynToRdf.sln --configuration Release
dotnet test RoslynToRdf.sln --configuration Release
python -m pytest tools/rg/tests/test_phase_c_integration.py -q
python -m pytest tools/rg/tests scripts/tests -q
python scripts/check_plugin_sync.py
```

Run `npm ci` then `npm test` in `viewer/`. QA checks APIs, RDF/queries and fixture oracles. No redesign of working viewer/extractor/batching; illustrative examples are not verified bugs.

## Non-closure

No acquisition, general resolver, workbench, runtime inference, COM or executable reconstruction. D6 only admits registered analyzed artifacts by exact bound identity; preserve working composition, no arbitrary packages. No unrelated requirement closure. #91 requires full body-extraction acceptance, not one allocation fixture or planning approval.
