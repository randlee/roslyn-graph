# Sprint c-2 - Extraction facts

```yaml
id: c-2
closure_type: boundary
target_boundary: dotnet-extraction-cli
branch: sprint/c-2-extraction-facts
recommended_agent: codex-developer
recommended_model: gpt-6.1-sol
parallel_safe: [c-1]
must_follow: []
vertical_rationale: extractor/CLI share writer contract
```

## Scope boundary

Implement producer changes 3, 4, 7, 8, 9; preserve other declarations/identities. Existing `--include-private`, `GetAllTypes`/`GetMembers` cover private/uncalled members. Analyze allocations without execution or caps. c-1 owns query limits/partial results; c-3 D6 owns registered-database selection/batched closure. Emit bound identities/RDF, not database queries.

## Owned paths

- `src/RoslynToRdf.Core/Extraction/AssemblyGraphExtractor*.cs`
- `src/RoslynToRdf.Core/Extraction/ExtractionOptions.cs`
- `src/RoslynToRdf.Core/Model/{IriMinter,DotNetOntology}.cs`
- `src/RoslynToRdf.Cli/{Program.cs,RoslynToRdf.Cli.csproj}`
- `ontology/dotnet-types.ttl`
- `plugins/roslyn-graph/skills/roslyn-graph-explore/ontology/dotnet-types.ttl`
- `plugins/roslyn-graph/skills/roslyn-graph-explore/reference/ontology.md`
- `tests/RoslynToRdf.Tests/{TestUtilities,AssemblyGraphExtractorTests,IriMinterTests,CliIntegrationTests}.cs`
- `tests/RoslynToRdf.Tests/PhaseC*Tests.cs`
- `tests/RoslynToRdf.Tests/Fixtures/PhaseC/**`

No deletions; c-3 consumes constants/references/ontology.

### Split decision

Keep one producer sprint: signatures and bodies share production entry points, not just test utilities. The following overlaps are verified against the existing code:

| Shared file/symbol | Signature/option work | Body work |
| --- | --- | --- |
| `AssemblyGraphExtractor.cs: Extract, ExtractType` | D1 delegate dispatch | D5 optional PE input on `Extract` and explicit-interface dispatch in `ExtractType` |
| `Program.cs: RunExtraction` | D3 attribute flags and D4 strict alias | D5 source/VB setup and the existing source/DLL `extractor.Extract` call sites |
| `DotNetOntology.cs`, both `dotnet-types.ttl` copies | D2 signature terms | D5 `MemberRels.UsesType` and its Member -> Type declaration |
| `TestUtilities.cs` | D1 language-neutral compilation helper | D5 source/DLL C#/VB fixture compilation |

`AssemblyGraphExtractor.Bodies.cs` is new, but depends on those edits and the hooks in `AssemblyGraphExtractor.Members.cs`. A signatures/body split is not independently buildable with disjoint owned paths: serializing it raises the critical path from two to three sprints without increasing usable width. Do not add stubs, partial-method seams or duplicated ontology literals to manufacture parallelism. c-1 remains genuinely parallel; c-3 closes the combined consumer behavior.

## Authoritative deliverables

### D1. Delegate Invoke/test helper

`AssemblyGraphExtractor.cs: ShouldIncludeMember, ExtractType`:

Exempt only `IMethodSymbol { MethodKind: MethodKind.DelegateInvoke }` from implicit rejection; allow it and call `ExtractMethod(typeIri, method)` once.

```text
INamedTypeSymbol.DelegateInvokeMethod
  -> <D> dt:hasMember <Invoke>
  -> <Invoke> a dt:Method; dt:methodKind "DelegateInvoke";
              dt:returnType <Ret>; dt:hasParameter <parameter>
  -> <parameter> dt:parameterType <Arg>; dt:ordinal 0
```

Use `member_types`/`parameter_types`; omit void returns.

`TestUtilities.cs`: add `CreateVisualBasicCompilation` using `VisualBasicSyntaxTree.ParseText`, `VisualBasicCompilation.Create`, `VisualBasicCompilationOptions(OutputKind.DynamicallyLinkedLibrary)` and existing references. `EmitToTempAssembly` accepts `Compilation`, not `CSharpCompilation`; keep C# helper.

### D2. Function-pointer RDF

`Helpers.cs.EnsureTypeEmitted`, new `EnsureFunctionPointerTypeEmitted`; `DotNetOntology.TypeRels`; both `dotnet-types.ttl`. c-3 owns queries.

Before non-named fallback handle `IFunctionPointerTypeSymbol` via `_iris.Type(pointer)`, constituent `EnsureTypeEmitted` and emitted guard.

```text
pointer.Signature.ReturnType -> <fp> dt:signatureReturnType <Ret>
pointer.Signature.Parameters[i] ->
    <fp> dt:signatureParameter <fp/sigparam/i>
    <fp/sigparam/i> a dt:Parameter;
        dt:ordinal i; dt:parameterType <Arg>; dt:refKind parameter.RefKind
pointer.Signature.RefKind -> <fp> dt:signatureReturnRefKind "..."
pointer.Signature.CallingConvention -> <fp> dt:callingConvention "..."
pointer.Signature.UnmanagedCallingConventionTypes ->
    <fp> dt:callingConventionType <convention type>
```

Domains/ranges: `signatureReturnType`/`callingConventionType`: Type -> Type; `signatureParameter`: Type -> Parameter; `signatureReturnRefKind`/`callingConvention`: Type -> xsd:string. Emit `<fp> a dt:Type; dt:typeKind "FunctionPointer"`; omit void returns. No Method-domain `hasParameter`/`returnType` on Type or IRI parsing for ref/conventions.

`IriMinter.GetFullMetadataName`: remove function-pointer `forMemberSignature &&` restriction; recursive convention/parameter/return calls pass caller `forMemberSignature`, not `true`. Type IRIs retain generic-owner qualification, member signatures ordinal form; other identities unchanged.

### D3. Attribute opt-in

`ExtractionOptions.IncludeAttributes` defaults false. `Program.cs`: add `--include-attributes`, retain `--exclude-attributes`, reject both; set `IncludeAttributes = includeAttributes`. Python fixed flags stay unchanged: new extractions are attribute-free, keyed by existing extractor-binary identity. No assumed per-run wrapper option or store mutation.

```text
ISymbol.GetAttributes() -> existing ExtractAttribute(...)
    -> <owner> dt:hasAttribute <attribute>
    -> <attribute> dt:attributeType <attribute class>
```

Same vocabulary; c-3 filters inverse traversal.

### D4. Strict alias

`Program.cs`, when creating `failOnMissingReferencesOption`:

```csharp
failOnMissingReferencesOption.AddAlias("--strict");
```

Keep false default, diagnostics, assembly-input failure and `--fail-on-missing-references`; no resolver/diagnostic/RDF/query redesign.

### D5. Source/DLL bodies

Add `AssemblyGraphExtractor.Bodies.cs`, called by `ExtractMethod`/`ExtractProperty`/`ExtractEvent`, and `ExtractField` for source initializers only (no DLL field body). Optional `Extract.peImagePath` receives CLI input DLL; source retains Compilation. Reuse member IRIs, type emission and artifact graphs.

Add `DotNetOntology.MemberRels.UsesType` and, in both ontology copies:

```turtle
dt:usesType a rdf:Property ; rdfs:domain dt:Member ; rdfs:range dt:Type .
```

Emit `<owner> dt:usesType <target>` once per pair via `EnsureTypeEmitted`. Owner: `_iris.Member(method)` for methods/constructors, existing property/event IRI for accessors; no new accessor identity.

Add `MethodKind.ExplicitInterfaceImplementation` to `ExtractType` allowlist for existing `ExtractMethod`/`dt:explicitInterfaceImplementation`. Roots: ordinary methods, instance/static constructors, destructors, operators/conversions, explicit implementations, DelegateInvoke, property get/set/init, event add/remove/raise. Preserve explicit visibility filters: excluded members are unrequested, not analyzed-empty. Wrapper includes private members; no entry-point reachability filter. Operation stack/generated-method queue use visited identities, no depth/count cap.

No `usesType` to `ITypeParameterSymbol`/unresolved placeholders; retain item 5 constraints/substituted targets. Keep self-use (projection alone drops self-edges); deduplicate all owner bodies/accessors.

### DLL bodies/tokens

```csharp
var handle = (MethodDefinitionHandle)MetadataTokens.Handle(method.MetadataToken);
var definition = reader.GetMethodDefinition(handle);
var body = peReader.GetMethodBody(definition.RelativeVirtualAddress);
```

Input-module tokens only; skip legitimate RVA-zero bodies. `MetadataTokens.MethodDefinitionHandle` takes row ID, not token. Read present `GetMethod`/`SetMethod`/`AddMethod`/`RemoveMethod`/`RaiseMethod` bodies under property/event owners.

Detect generated methods by method/type `CompilerGeneratedAttribute`, even with attributes off; never names or PE `IsImplicitlyDeclared` (false). Preserve generated declarations, but do not start generated-owned walks.

Per original owner, enqueue generated targets of `ldftn`/`ldvirtftn`/`call`/`callvirt`/`newobj`, including constructors; attribute facts to that owner. Generated type/field references must not enqueue every method of shared cache/display classes. Resolve owner `AsyncStateMachineAttribute`/`IteratorStateMachineAttribute`/`AsyncIteratorStateMachineAttribute` type arguments; enqueue `MoveNext` and reached generated methods. Roslyn-omitted symbols use metadata handles. Visited key: `(owner IRI, module identity, MethodDefinitionHandle)`; never recurse into ordinary callees.

| Exact API/input | Target type facts |
| --- | --- |
| `MethodBodyBlock.GetILReader()`; `InlineType`, `InlineTok`, `InlineMethod`, `InlineField` | ECMA operand widths/handles, never byte-scanning for tokens. |
| `TypeDefinition.GetDeclaringType()`, `TypeReference.ResolutionScope` | Nested names via bound `IAssemblySymbol.GetTypeByMetadataName`; `ResolveForwardedType` for forwards. AssemblyReference identity via `Compilation.GetAssemblyOrModuleSymbol`, never newest/name-only. |
| `TypeSpecification.DecodeSignature` | Generic definition/every argument, array/pointer/byref constituents -> named usesType targets. |
| `MemberReference.Parent` and `DecodeMethodSignature` / `DecodeFieldSignature` | Declaring type plus parameter/return/field constituents. |
| `MethodDefinition.GetDeclaringType()` / `FieldDefinition.GetDeclaringType()` and `DecodeSignature` | Declaring type plus signature constituents. |
| `MethodSpecification.Method`, `DecodeSignature` | Underlying method/all instantiation arguments; substitute type/method arguments in decoding context. |
| `MethodBodyBlock.LocalSignature` -> `StandaloneSignature.DecodeLocalSignature` | Include local-type constituents. |
| `InlineSig` -> `StandaloneSignature.DecodeMethodSignature` | Include calli parameter/return constituents. |
| `MethodBodyBlock.ExceptionRegions`, catch-region `CatchType` | Include the exception type. |

Share `ISignatureTypeProvider` with declaring-type/method generic arguments. Keep all bound named targets (primitive/external too); diagnose unresolved bindings. Preserve physical identities for c-3, never newest/name-only rebinding. Unregistered packages stay identified external references: no acquisition/extraction/body walk. IL cannot claim erased source facts.

Nested `TypeReference`: outer type then `GetTypeMembers(name, arity)`. `ModuleDefinition`: input module; `ModuleReference`: diagnose unavailable multi-module resolution. Nil scope: `ExportedType` implementation/forwarding records. Failed lookup is not empty dependencies.

### Source body access

`Compilation.GetSemanticModel(tree).GetOperation(node)` supplies bodies/initializers; stack-walk implicit and explicit `IOperation.ChildOperations`. Roots use emitted members; anonymous/local functions use enclosing emitted owner; field/property/event initializers use their member.

Roots: admitted `DeclaringSyntaxReferences`, including accessors; deduplicate tree/span/owner. Include constructor bodies/base/this, field/property and parameter initializers, not just blocks. For operation-less VB statements inspect containing declaration block; no C#-only body cast. Source initializer owners are field/property/event versus IL `.ctor`/`.cctor`; type dependencies agree.

`Program.cs.RunExtraction`: `sourceProjects` recognizes `.csproj`/`.vbproj` with `OrdinalIgnoreCase`; update help. Accept `LanguageNames.CSharp`/`LanguageNames.VisualBasic`; keep `MSBuildWorkspace.OpenProjectAsync`/`GetCompilationAsync`, neutral null diagnostic and CSharpCompilationOptions unsafe guard. Beside CSharp.Workspaces in `RoslynToRdf.Cli.csproj`, add `<PackageReference Include="Microsoft.CodeAnalysis.VisualBasic.Workspaces" Version="4.9.2" />`. CLI-test real `.vbproj`.

| Roslyn operation/property | Target passed to `EnsureTypeEmitted` |
| --- | --- |
| `IObjectCreationOperation.Type`, `.Constructor` | Allocation plus constructor declaring/signature types. |
| `IArrayCreationOperation.Type`, `IVariableDeclaratorOperation.Symbol.Type` | Array element/local type constituents. |
| `IInvocationOperation.TargetMethod`, `IMethodReferenceOperation.Method` | Containing type, type arguments, parameter types and return type. |
| `IFieldReferenceOperation.Field`, `IPropertyReferenceOperation.Property`, `IEventReferenceOperation.Event` | Containing type and field/property/event type; property parameter types where present. |
| `IConversionOperation.Type`, `.OperatorMethod`, `ITypeOfOperation.TypeOperand` | Conversion target/operator signature and type-token target. |
| `INameOfOperation.Argument` | Visit bound argument; type-name without result Type uses `SemanticModel.GetSymbolInfo(argument.Syntax).Symbol`. Include type/member containing/signature types. |
| `IDefaultValueOperation.Type`, `ISizeOfOperation.TypeOperand` | default/sizeof target. |
| `ITypePatternOperation.MatchedType`, `IDeclarationPatternOperation.MatchedType` | Pattern type even with null operation Type. |
| `ICatchClauseOperation.ExceptionType`, `IThrowOperation.Exception` | Catch type and thrown expression/type, not throw statement's null Type. |
| Other visited `IOperation.Type` values | Static result constituents plus bound-member targets; void calls retain declaring/signature types. |

Retain bound const/conditional-call targets; resolve aliases semantically. Attributes require opt-in. Test source/IL nameof/const/conditional erasure separately, not false equality.

**Compiler-selected patterns (TX-G13, Roslyn 4.9.2).** ChildOperations omits these members; emit their containing/signature types through the same owner/usesType writer:

| Input | Exact semantic source |
| --- | --- |
| C# foreach/await foreach | `CSharpExtensions.GetForEachStatementInfo(model, CommonForEachStatementSyntax)`: GetEnumeratorMethod, MoveNextMethod, CurrentProperty, DisposeMethod, ElementType and CurrentConversion/ElementConversion.MethodSymbol. |
| VB For Each | `VisualBasicExtensions.GetForEachStatementInfo(model, ForEachBlockSyntax)`, same member/type/conversion properties. |
| Explicit C#/VB await | Language extension `GetAwaitExpressionInfo(model, AwaitExpressionSyntax)`: GetAwaiterMethod, IsCompletedProperty, GetResultMethod. |
| using/await using, including declarations | `ControlFlowGraph.Create` on admitted root; visit all Operations/BranchValue even when !IsReachable. IInvocationOperation.TargetMethod selects Dispose/DisposeAsync. Nested CFGs: GetLocalFunctionControlFlowGraph/GetAnonymousFunctionControlFlowGraph; retain lexical owner. |

Implicit MoveNextAsync/DisposeAsync awaits: bind synthetic await in original C# lexical/generic scope:

```csharp
var statement = SyntaxFactory.ExpressionStatement(SyntaxFactory.AwaitExpression(
    SyntaxFactory.DefaultExpression(SyntaxFactory.ParseTypeName(
        selectedMethod.ReturnType.ToDisplayString(SymbolDisplayFormat.FullyQualifiedFormat)))));
model.TryGetSpeculativeSemanticModel(originalSyntax.SpanStart, statement, out var speculative);
var info = speculative.GetAwaitExpressionInfo((AwaitExpressionSyntax)statement.Expression);
```

Check boolean/model; emit GetAwaiterMethod/IsCompletedProperty/GetResultMethod. Diagnose failed binding; never infer GetAwaiter by name or substitute IL semantics.

### D6. Reference-stub assembly identity

`AssemblyGraphExtractor.Helpers.cs.EnsureTypeEmitted`, named-type/ContainingAssembly branch: keep `<target> dt:definedInAssembly <asm>`; add `<asm> dt:name assembly.Name; dt:version assembly.Identity.Version.ToString()`, nonempty `dt:culture`, lowercase hex `dt:publicKeyToken` via `DotNetOntology.AsmProps`. Only owner assembly has `a dt:Assembly` (`build.snapshot` requires exactly one). No new vocabulary/resolver/IRI parsing; c-3 preserves facts/source-manifest provenance.



## Authoritative acceptance criteria

Extraction checks; c-3 owns selection/export.

- **AC1 [boundary:dotnet-extraction-cli/delegates].** C#/VB source/PE emit exact D1 Invoke/parameter/return triples; ordinary member filtering unchanged.
- **AC2 [boundary:dotnet-extraction-cli/function-pointers].** D2 ordinals/targets/ref/return/convention facts and A<T>/B<T> identities match; nested/repeated arguments retain positions. Declaration/member identity regressions pass.
- **AC3 [boundary:dotnet-extraction-cli/options].** Default: no hasAttribute; opt-in: existing shape; conflicting flags fail. Both strict spellings fail the same missing-reference DLL; default retains facts/diagnostics. Source strict rejection remains.
- **AC4 [boundary:dotnet-extraction-cli/body-facts].** Cross-reference: TX-G02. Real C#/VB samples cover every D5 operation/token row with unique body-only targets and Decoy. Assert owner/usesType in source/DLL, relevant Debug/Release, PDB present/absent. Internal root's uncalled private method uses only PrivateOnly: extraction includes type/member/target regardless of entry-point reachability. Cover accessor/initializer owner differences, explicit interfaces, catch/pattern/token/generic/calli and source-erased bindings.
- **AC5 [boundary:dotnet-extraction-cli/generated-ownership].** Async/iterator/lambda/captured-closure/C# local-function-only targets retain original owners. Shared generated method retains both owners; shared lambda cache never cross-contaminates. Generated declarations unchanged; no type-parameter usesType targets; retain self-use.
- **AC6 [boundary:dotnet-extraction-cli/vb-workspace].** Real .vbproj via MSBuildWorkspace emits bodies beyond direct-compilation tests. C# unsafe guard preserved; workspace package exactly 4.9.2.
- **AC7 [boundary:dotnet-extraction-cli/reference-identity].** Cross-references: TX-G03, TX-G04, TX-G17. External reference retains assembly name/version/culture/token and owner/usesType without registered DB. Assert D6 predicates, no acquisition, unchanged owner artifact graph. An analyzed-library fixture shares bound identity; c-3 follows its definition/preserves export provenance.
- **AC8 [boundary:dotnet-extraction-cli/compiler-selected-bodies].** Cross-reference: TX-G13. C#/VB foreach/await retain custom enumerator/result/extension-awaiter helpers. C# ref-struct using/declaration and async foreach/using retain custom Dispose, MoveNextAsync/DisposeAsync awaiter targets omitted by ChildOperations. Include generic/nested lambda/local-function owners and decoys. Exact source/DLL owner/usesType pairs; compile/analyze, never execute.
- **AC9 [boundary:dotnet-extraction-cli/body-failure-and-termination].** Cross-reference: TX-G19. Invalid PE/unwritable output reach `Program.cs` exception exit 1, no `Done`. Body-reader/writer exceptions propagate, never empty-success. Generated-method cycles terminate by owner/module/handle while retaining all types; no recursion/count cutoff. c-1 owns query-cut tests; CLI adds no cut option.

## Authoritative validation

```powershell
dotnet build RoslynToRdf.sln --configuration Release
dotnet test tests/RoslynToRdf.Tests/RoslynToRdf.Tests.csproj --configuration Release
python scripts/check_plugin_sync.py
python -m pytest scripts/tests -q
```

Existing tooling, hand-authored triples, no generated oracles/skipped modes. Sync changed ontology only. QA: API -> RDF, no placeholders/runtime inference/refactor.

## Non-closure

c-3 must deliver closure, inverse attribute filtering and exported bodies. This producer alone does not close requirements.md.
