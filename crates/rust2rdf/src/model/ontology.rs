//! RDF vocabulary constants for the type graph ontology.
//!
//! - `tg:` prefix (http://typegraph.example/ontology/) -- shared cross-language predicates
//! - `rt:` prefix (http://rust.example/ontology/) -- Rust-specific extensions
//! - `dt:` prefix (http://dotnet.example/ontology/) -- .NET-specific extensions

/// Standard RDF/RDFS/XSD namespace URIs
pub mod standard {
    pub const RDF: &str = "http://www.w3.org/1999/02/22-rdf-syntax-ns#";
    pub const RDFS: &str = "http://www.w3.org/2000/01/rdf-schema#";
    pub const XSD: &str = "http://www.w3.org/2001/XMLSchema#";
    pub const RDF_TYPE: &str = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type";
    pub const RDFS_LABEL: &str = "http://www.w3.org/2000/01/rdf-schema#label";
    pub const RDFS_SUBCLASS_OF: &str = "http://www.w3.org/2000/01/rdf-schema#subClassOf";
    pub const XSD_STRING: &str = "http://www.w3.org/2001/XMLSchema#string";
    pub const XSD_BOOLEAN: &str = "http://www.w3.org/2001/XMLSchema#boolean";
    pub const XSD_INTEGER: &str = "http://www.w3.org/2001/XMLSchema#integer";
}

/// Shared type-graph ontology (`tg:` prefix) -- used by both .NET and Rust tools
pub mod tg {
    pub const PREFIX: &str = "tg";
    pub const NS: &str = "http://typegraph.example/ontology/";

    // Classes
    pub const ASSEMBLY: &str = "http://typegraph.example/ontology/Assembly";
    pub const NAMESPACE: &str = "http://typegraph.example/ontology/Namespace";
    pub const TYPE: &str = "http://typegraph.example/ontology/Type";
    pub const CLASS: &str = "http://typegraph.example/ontology/Class";
    pub const STRUCT: &str = "http://typegraph.example/ontology/Struct";
    pub const INTERFACE: &str = "http://typegraph.example/ontology/Interface";
    pub const ENUM: &str = "http://typegraph.example/ontology/Enum";
    pub const DELEGATE: &str = "http://typegraph.example/ontology/Delegate";
    pub const RECORD: &str = "http://typegraph.example/ontology/Record";
    pub const MEMBER: &str = "http://typegraph.example/ontology/Member";
    pub const METHOD: &str = "http://typegraph.example/ontology/Method";
    pub const CONSTRUCTOR: &str = "http://typegraph.example/ontology/Constructor";
    pub const PROPERTY: &str = "http://typegraph.example/ontology/Property";
    pub const FIELD: &str = "http://typegraph.example/ontology/Field";
    pub const EVENT: &str = "http://typegraph.example/ontology/Event";
    pub const PARAMETER: &str = "http://typegraph.example/ontology/Parameter";
    pub const TYPE_PARAMETER: &str = "http://typegraph.example/ontology/TypeParameter";
    pub const ATTRIBUTE: &str = "http://typegraph.example/ontology/Attribute";

    // Type properties
    pub const NAME: &str = "http://typegraph.example/ontology/name";
    pub const FULL_NAME: &str = "http://typegraph.example/ontology/fullName";
    pub const TYPE_KIND: &str = "http://typegraph.example/ontology/typeKind";
    pub const ACCESSIBILITY: &str = "http://typegraph.example/ontology/accessibility";
    pub const IS_ABSTRACT: &str = "http://typegraph.example/ontology/isAbstract";
    pub const IS_SEALED: &str = "http://typegraph.example/ontology/isSealed";
    pub const IS_STATIC: &str = "http://typegraph.example/ontology/isStatic";
    pub const IS_GENERIC: &str = "http://typegraph.example/ontology/isGeneric";
    pub const IS_VALUE_TYPE: &str = "http://typegraph.example/ontology/isValueType";
    pub const IS_RECORD: &str = "http://typegraph.example/ontology/isRecord";

    // Type relationships
    pub const DEFINED_IN_ASSEMBLY: &str = "http://typegraph.example/ontology/definedInAssembly";
    pub const IN_NAMESPACE: &str = "http://typegraph.example/ontology/inNamespace";
    pub const INHERITS: &str = "http://typegraph.example/ontology/inherits";
    pub const IMPLEMENTS: &str = "http://typegraph.example/ontology/implements";
    pub const NESTED_IN: &str = "http://typegraph.example/ontology/nestedIn";
    pub const HAS_MEMBER: &str = "http://typegraph.example/ontology/hasMember";
    pub const HAS_TYPE_PARAMETER: &str = "http://typegraph.example/ontology/hasTypeParameter";
    pub const HAS_ATTRIBUTE: &str = "http://typegraph.example/ontology/hasAttribute";
    pub const GENERIC_DEFINITION: &str = "http://typegraph.example/ontology/genericDefinition";
    pub const TYPE_ARGUMENT: &str = "http://typegraph.example/ontology/typeArgument";
    pub const ARRAY_ELEMENT_TYPE: &str = "http://typegraph.example/ontology/arrayElementType";
    pub const THROWS: &str = "http://typegraph.example/ontology/throws";
    pub const RELATED_TO: &str = "http://typegraph.example/ontology/relatedTo";

    // Member properties
    pub const IS_VIRTUAL: &str = "http://typegraph.example/ontology/isVirtual";
    pub const IS_OVERRIDE: &str = "http://typegraph.example/ontology/isOverride";
    pub const IS_ASYNC: &str = "http://typegraph.example/ontology/isAsync";
    pub const IS_CONST: &str = "http://typegraph.example/ontology/isConst";
    pub const IS_READ_ONLY: &str = "http://typegraph.example/ontology/isReadOnly";

    // Member relationships
    pub const MEMBER_OF: &str = "http://typegraph.example/ontology/memberOf";
    pub const RETURN_TYPE: &str = "http://typegraph.example/ontology/returnType";
    pub const PROPERTY_TYPE: &str = "http://typegraph.example/ontology/propertyType";
    pub const FIELD_TYPE: &str = "http://typegraph.example/ontology/fieldType";
    pub const EVENT_TYPE: &str = "http://typegraph.example/ontology/eventType";
    pub const HAS_PARAMETER: &str = "http://typegraph.example/ontology/hasParameter";
    pub const OVERRIDES_METHOD: &str = "http://typegraph.example/ontology/overridesMethod";

    // Parameter properties
    pub const ORDINAL: &str = "http://typegraph.example/ontology/ordinal";
    pub const PARAMETER_TYPE: &str = "http://typegraph.example/ontology/parameterType";
    pub const PARAMETER_OF: &str = "http://typegraph.example/ontology/parameterOf";
    pub const IS_OPTIONAL: &str = "http://typegraph.example/ontology/isOptional";
    pub const REF_KIND: &str = "http://typegraph.example/ontology/refKind";
    pub const DEFAULT_VALUE: &str = "http://typegraph.example/ontology/defaultValue";

    // Type parameter properties
    pub const VARIANCE: &str = "http://typegraph.example/ontology/variance";
    pub const TYPE_PARAMETER_OF: &str = "http://typegraph.example/ontology/typeParameterOf";
    pub const CONSTRAINED_TO_TYPE: &str = "http://typegraph.example/ontology/constrainedToType";

    // Assembly properties
    pub const VERSION: &str = "http://typegraph.example/ontology/version";

    // Namespace relationships
    pub const PARENT_NAMESPACE: &str = "http://typegraph.example/ontology/parentNamespace";
    pub const CONTAINS_TYPE: &str = "http://typegraph.example/ontology/containsType";

    // Attribute properties
    pub const ATTRIBUTE_OF: &str = "http://typegraph.example/ontology/attributeOf";
    pub const ATTRIBUTE_TYPE: &str = "http://typegraph.example/ontology/attributeType";

    // Language tag
    pub const LANGUAGE: &str = "http://typegraph.example/ontology/language";
}

/// Rust-specific extensions (`rt:` prefix)
pub mod rt {
    pub const PREFIX: &str = "rt";
    pub const NS: &str = "http://rust.example/ontology/";

    // Classes
    pub const CRATE: &str = "http://rust.example/ontology/Crate";
    pub const MODULE: &str = "http://rust.example/ontology/Module";
    pub const TRAIT: &str = "http://rust.example/ontology/Trait";
    pub const UNION: &str = "http://rust.example/ontology/Union";
    pub const TYPE_ALIAS: &str = "http://rust.example/ontology/TypeAlias";
    pub const ENUM_VARIANT: &str = "http://rust.example/ontology/EnumVariant";
    pub const TRAIT_IMPL: &str = "http://rust.example/ontology/TraitImpl";
    pub const INHERENT_IMPL: &str = "http://rust.example/ontology/InherentImpl";
    pub const LIFETIME: &str = "http://rust.example/ontology/Lifetime";
    pub const CONST_PARAM: &str = "http://rust.example/ontology/ConstParam";
    pub const MACRO: &str = "http://rust.example/ontology/Macro";
    pub const STATIC: &str = "http://rust.example/ontology/Static";
    pub const CONSTANT: &str = "http://rust.example/ontology/Constant";

    // Predicates
    pub const DEPENDS_ON: &str = "http://rust.example/ontology/dependsOn";
    pub const SUPER_TRAIT: &str = "http://rust.example/ontology/superTrait";
    pub const IMPL_FOR: &str = "http://rust.example/ontology/implFor";
    pub const IMPL_TRAIT: &str = "http://rust.example/ontology/implTrait";
    pub const HAS_IMPL: &str = "http://rust.example/ontology/hasImpl";
    pub const HAS_VARIANT: &str = "http://rust.example/ontology/hasVariant";
    pub const VARIANT_KIND: &str = "http://rust.example/ontology/variantKind";
    pub const VARIANT_FIELD: &str = "http://rust.example/ontology/variantField";
    pub const HAS_LIFETIME: &str = "http://rust.example/ontology/hasLifetime";
    pub const LIFETIME_BOUND: &str = "http://rust.example/ontology/lifetimeBound";
    pub const IS_UNSAFE: &str = "http://rust.example/ontology/isUnsafe";
    pub const IS_MUTABLE: &str = "http://rust.example/ontology/isMutable";
    pub const IS_EXHAUSTIVE: &str = "http://rust.example/ontology/isExhaustive";
    pub const ERROR_TYPE: &str = "http://rust.example/ontology/errorType";
    pub const DERIVES: &str = "http://rust.example/ontology/derives";
    pub const TRAIT_BOUND: &str = "http://rust.example/ontology/traitBound";
}
