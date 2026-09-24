# Ontology reference

<!-- Generated from the ontology/ files beside this skill by `python scripts/rg.py ontology-doc` (repository: python scripts/check_plugin_sync.py --fix). Do not edit by hand. -->

## Prefixes

| Prefix | IRI |
|---|---|
| `dt:` | `http://dotnet.example/ontology/` |
| `owl:` | `http://www.w3.org/2002/07/owl#` |
| `rdf:` | `http://www.w3.org/1999/02/22-rdf-syntax-ns#` |
| `rdfs:` | `http://www.w3.org/2000/01/rdf-schema#` |
| `rg:` | `http://roslyn-graph.example/ontology/` |
| `xsd:` | `http://www.w3.org/2001/XMLSchema#` |

## Physical .NET facts (`dt:`)

### Classes

| Class | Subclass of | Notes |
|---|---|---|
| `dt:Assembly` |  |  |
| `dt:Attribute` |  |  |
| `dt:Class` | `dt:Type` |  |
| `dt:Constructor` | `dt:Member` |  |
| `dt:Delegate` | `dt:Type` |  |
| `dt:Enum` | `dt:Type` |  |
| `dt:Event` | `dt:Member` |  |
| `dt:Field` | `dt:Member` |  |
| `dt:Interface` | `dt:Type` |  |
| `dt:Member` |  |  |
| `dt:Method` | `dt:Member` |  |
| `dt:Namespace` |  |  |
| `dt:Parameter` |  |  |
| `dt:Property` | `dt:Member` |  |
| `dt:Record` | `dt:Type` |  |
| `dt:Struct` | `dt:Type` |  |
| `dt:Type` |  |  |
| `dt:TypeParameter` |  |  |

### Properties

| Property | Domain | Range | Notes |
|---|---|---|---|
| `dt:culture` | `dt:Assembly` | `xsd:string` |  |
| `dt:isInteractive` | `dt:Assembly` | `xsd:boolean` |  |
| `dt:publicKeyToken` | `dt:Assembly` | `xsd:string` |  |
| `dt:version` | `dt:Assembly` | `xsd:string` |  |
| `dt:attributeClass` | `dt:Attribute` | `dt:Type` |  |
| `dt:attributeOf` | `dt:Attribute` |  |  |
| `dt:attributeType` | `dt:Attribute` | `dt:Type` |  |
| `dt:constructorArguments` | `dt:Attribute` | `xsd:string` |  |
| `dt:namedArguments` | `dt:Attribute` | `xsd:string` |  |
| `dt:enumUnderlyingType` | `dt:Enum` | `dt:Type` |  |
| `dt:eventType` | `dt:Event` | `dt:Type` |  |
| `dt:constValue` | `dt:Field` | `xsd:string` |  |
| `dt:fieldType` | `dt:Field` | `dt:Type` |  |
| `dt:isVolatile` | `dt:Field` | `xsd:boolean` |  |
| `dt:explicitInterfaceImplementation` | `dt:Member` | `dt:Member` |  |
| `dt:isExtern` | `dt:Member` | `xsd:boolean` |  |
| `dt:isRequired` | `dt:Member` | `xsd:boolean` |  |
| `dt:memberOf` | `dt:Member` | `dt:Type` |  |
| `dt:overridesMethod` | `dt:Member` | `dt:Member` |  |
| `dt:hasParameter` | `dt:Method` | `dt:Parameter` |  |
| `dt:isExtensionMethod` | `dt:Method` | `xsd:boolean` |  |
| `dt:isPartialDefinition` | `dt:Method` | `xsd:boolean` |  |
| `dt:methodKind` | `dt:Method` | `xsd:string` |  |
| `dt:returnType` | `dt:Method` | `dt:Type` |  |
| `dt:containsType` | `dt:Namespace` | `dt:Type` |  |
| `dt:parentNamespace` | `dt:Namespace` | `dt:Namespace` |  |
| `dt:defaultValue` | `dt:Parameter` | `xsd:string` |  |
| `dt:hasExplicitDefaultValue` | `dt:Parameter` | `xsd:boolean` |  |
| `dt:isDiscard` | `dt:Parameter` | `xsd:boolean` |  |
| `dt:isOptional` | `dt:Parameter` | `xsd:boolean` |  |
| `dt:isParams` | `dt:Parameter` | `xsd:boolean` |  |
| `dt:isThis` | `dt:Parameter` | `xsd:boolean` |  |
| `dt:parameterOf` | `dt:Parameter` | `dt:Method` |  |
| `dt:parameterType` | `dt:Parameter` | `dt:Type` |  |
| `dt:refKind` | `dt:Parameter` | `xsd:string` |  |
| `dt:getterAccessibility` | `dt:Property` | `xsd:string` |  |
| `dt:hasGetter` | `dt:Property` | `xsd:boolean` |  |
| `dt:hasSetter` | `dt:Property` | `xsd:boolean` |  |
| `dt:isInitOnly` | `dt:Property` | `xsd:boolean` |  |
| `dt:propertyType` | `dt:Property` | `dt:Type` |  |
| `dt:setterAccessibility` | `dt:Property` | `xsd:string` |  |
| `dt:arrayElementType` | `dt:Type` | `dt:Type` |  |
| `dt:arrayRank` | `dt:Type` | `xsd:integer` |  |
| `dt:definedInAssembly` | `dt:Type` | `dt:Assembly` |  |
| `dt:genericDefinition` | `dt:Type` | `dt:Type` |  |
| `dt:hasMember` | `dt:Type` | `dt:Member` |  |
| `dt:implements` | `dt:Type` | `dt:Interface` |  |
| `dt:inNamespace` | `dt:Type` | `dt:Namespace` |  |
| `dt:inherits` | `dt:Type` | `dt:Type` |  |
| `dt:isRefLikeType` | `dt:Type` | `xsd:boolean` |  |
| `dt:isUnmanagedType` | `dt:Type` | `xsd:boolean` |  |
| `dt:nestedIn` | `dt:Type` | `dt:Type` |  |
| `dt:pointerElementType` | `dt:Type` | `dt:Type` |  |
| `dt:specialType` | `dt:Type` | `xsd:string` | Roslyn SpecialType name for built-in types, such as System_Int32 |
| `dt:typeArgument` | `dt:Type` |  |  |
| `dt:typeKind` | `dt:Type` | `xsd:string` |  |
| `dt:constrainedToType` | `dt:TypeParameter` | `dt:Type` |  |
| `dt:hasConstructorConstraint` | `dt:TypeParameter` | `xsd:boolean` |  |
| `dt:hasNotNullConstraint` | `dt:TypeParameter` | `xsd:boolean` |  |
| `dt:hasReferenceTypeConstraint` | `dt:TypeParameter` | `xsd:boolean` |  |
| `dt:hasUnmanagedTypeConstraint` | `dt:TypeParameter` | `xsd:boolean` |  |
| `dt:hasValueTypeConstraint` | `dt:TypeParameter` | `xsd:boolean` |  |
| `dt:typeParameterOf` | `dt:TypeParameter` |  |  |
| `dt:variance` | `dt:TypeParameter` | `xsd:string` |  |
| `dt:accessibility` |  | `xsd:string` |  |
| `dt:fullName` |  | `xsd:string` |  |
| `dt:hasAttribute` |  | `dt:Attribute` |  |
| `dt:hasTypeParameter` |  | `dt:TypeParameter` |  |
| `dt:index` |  | `xsd:integer` | Zero-based position of a generic type argument node |
| `dt:isAbstract` |  | `xsd:boolean` |  |
| `dt:isAsync` |  | `xsd:boolean` |  |
| `dt:isConst` |  | `xsd:boolean` |  |
| `dt:isGeneric` |  | `xsd:boolean` |  |
| `dt:isOverride` |  | `xsd:boolean` |  |
| `dt:isReadOnly` |  | `xsd:boolean` |  |
| `dt:isRecord` |  | `xsd:boolean` |  |
| `dt:isSealed` |  | `xsd:boolean` |  |
| `dt:isStatic` |  | `xsd:boolean` |  |
| `dt:isValueType` |  | `xsd:boolean` |  |
| `dt:isVirtual` |  | `xsd:boolean` |  |
| `dt:name` |  | `xsd:string` |  |
| `dt:ordinal` |  | `xsd:integer` |  |
| `dt:relatedTo` |  |  | Related symbol from seealso |
| `dt:throws` |  | `dt:Type` | Exception type from XML docs |
| `dt:type` |  | `dt:Type` | Type supplied by a generic type argument node |

## Artifacts, solutions and logical types (`rg:`)

### Classes

| Class | Subclass of | Notes |
|---|---|---|
| `rg:LogicalType` |  | One display/query node per compatible type across versions. Never owl:sameAs its physical types. |
| `rg:LogicalTypeView` |  | A derived store that adds overlay components and a logical-type projection to an immutable solution store. |
| `rg:SolutionBuild` |  | One configured build composed into a solution store; described in the store's metadata named graph. |

### Properties

| Property | Domain | Range | Notes |
|---|---|---|---|
| `rg:logicalType` | `dt:Type` | `rg:LogicalType` | Links a physical, versioned dt:Type to its logical type |
| `rg:references` | `dt:Type` | `dt:Type` | Written only into exported traversal graphs: the subject type uses the object type as a base type, interface, member type, parameter type or generic argument |
| `rg:assemblyName` | `rg:LogicalType` | `xsd:string` |  |
| `rg:baseSolution` | `rg:LogicalTypeView` | `rg:SolutionBuild` |  |
| `rg:policy` | `rg:LogicalTypeView` | `xsd:string` |  |
| `rg:branch` | `rg:SolutionBuild` | `xsd:string` |  |
| `rg:buildFingerprint` | `rg:SolutionBuild` | `xsd:string` |  |
| `rg:commit` | `rg:SolutionBuild` | `xsd:string` |  |
| `rg:configuration` | `rg:SolutionBuild` | `xsd:string` |  |
| `rg:includesArtifact` | `rg:SolutionBuild` | `xsd:string` | Full SHA-256 artifact ID of a component |
| `rg:includesGraph` | `rg:SolutionBuild` |  | Named graph IRI of a component assembly artifact |
| `rg:name` | `rg:SolutionBuild` | `xsd:string` |  |
| `rg:platform` | `rg:SolutionBuild` | `xsd:string` |  |
| `rg:profile` | `rg:SolutionBuild` | `xsd:string` | workspace.toml profile that produced the build |
| `rg:repository` | `rg:SolutionBuild` | `xsd:string` |  |
| `rg:solutionPath` | `rg:SolutionBuild` | `xsd:string` |  |
| `rg:targetFramework` | `rg:SolutionBuild` | `xsd:string` |  |
