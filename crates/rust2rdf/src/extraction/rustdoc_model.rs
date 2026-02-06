//! Serde model for rustdoc JSON output format.
//!
//! These types match the rustdoc JSON schema. We only model fields we need
//! for extraction. Unknown fields are silently ignored via serde defaults.
//!
//! Design notes:
//! - We use `#[serde(default)]` liberally for forward/backward compatibility.
//! - Enums with `#[serde(other)]` place the Unknown variant last (serde requirement).
//! - We do NOT use `#[serde(deny_unknown_fields)]` -- unknown fields are ignored.
//! - Aliases handle both old (snake_case) and newer naming conventions.

use serde::Deserialize;
use std::collections::HashMap;

/// Newtype for rustdoc item IDs.
#[derive(Debug, Clone, PartialEq, Eq, Hash, Deserialize)]
pub struct Id(pub String);

/// Top-level rustdoc JSON output.
#[derive(Debug, Deserialize)]
pub struct Crate {
    /// Root module item ID.
    pub root: Id,
    /// The crate version, if available.
    #[serde(default)]
    pub crate_version: Option<String>,
    /// All items indexed by ID.
    #[serde(default)]
    pub index: HashMap<String, Item>,
    /// Path information for external items.
    #[serde(default)]
    pub paths: HashMap<String, ItemSummary>,
    /// External crate metadata.
    #[serde(default)]
    pub external_crates: HashMap<String, ExternalCrate>,
    /// Format version of the JSON output.
    #[serde(default)]
    pub format_version: u32,
}

/// Summary of an item's path (used for external references).
#[derive(Debug, Deserialize)]
pub struct ItemSummary {
    /// The components of the item's path.
    #[serde(default)]
    pub path: Vec<String>,
    /// The kind of item.
    #[serde(default)]
    pub kind: ItemKind,
}

/// External crate metadata.
#[derive(Debug, Deserialize)]
pub struct ExternalCrate {
    pub name: String,
    #[serde(default)]
    pub html_root_url: Option<String>,
}

/// A single item in the rustdoc output.
#[derive(Debug, Deserialize)]
pub struct Item {
    /// Item ID.
    #[serde(default)]
    pub id: Option<Id>,
    /// Item name (None for impl blocks).
    #[serde(default)]
    pub name: Option<String>,
    /// Visibility.
    #[serde(default)]
    pub visibility: Visibility,
    /// Attributes as strings (e.g., "#[derive(Debug)]").
    #[serde(default)]
    pub attrs: Vec<String>,
    /// Deprecation information.
    #[serde(default)]
    pub deprecation: Option<Deprecation>,
    /// Documentation string.
    #[serde(default)]
    pub docs: Option<String>,
    /// Source span.
    #[serde(default)]
    pub span: Option<Span>,
    /// The item's inner content (what kind of item this is).
    #[serde(default)]
    pub inner: ItemEnum,
    /// Links within documentation.
    #[serde(default)]
    pub links: HashMap<String, Id>,
}

/// Source code span.
#[derive(Debug, Deserialize)]
pub struct Span {
    #[serde(default)]
    pub filename: String,
    #[serde(default)]
    pub begin: (usize, usize),
    #[serde(default)]
    pub end: (usize, usize),
}

/// Deprecation information.
#[derive(Debug, Deserialize)]
pub struct Deprecation {
    #[serde(default)]
    pub since: Option<String>,
    #[serde(default)]
    pub note: Option<String>,
}

/// Visibility of an item.
#[derive(Debug, Clone, Deserialize, Default)]
#[serde(rename_all = "snake_case")]
pub enum Visibility {
    #[default]
    Public,
    Default,
    Crate,
    Restricted(VisibilityRestricted),
}

/// Restricted visibility details.
#[derive(Debug, Clone, Deserialize)]
pub struct VisibilityRestricted {
    pub parent: Id,
    pub path: String,
}

/// The kind of item (used in ItemSummary).
#[derive(Debug, Clone, Deserialize, Default)]
#[serde(rename_all = "snake_case")]
pub enum ItemKind {
    #[default]
    Module,
    ExternCrate,
    Use,
    Struct,
    StructField,
    Union,
    Enum,
    Variant,
    Function,
    TypeAlias,
    Constant,
    Trait,
    TraitAlias,
    Impl,
    Static,
    ExternType,
    Macro,
    ProcMacro,
    ProcAttribute,
    ProcDerive,
    AssocConst,
    AssocType,
    Primitive,
    Keyword,
}

/// The inner content of an Item -- determines what kind of item it is.
///
/// Uses adjacently tagged representation: `{ "kind": "...", "inner": ... }`.
/// The `Unknown` variant catches any unrecognized `kind` values for forward
/// compatibility.
#[derive(Debug, Deserialize, Default)]
#[serde(tag = "kind", content = "inner")]
pub enum ItemEnum {
    #[serde(alias = "module")]
    Module {
        #[serde(default)]
        items: Vec<Id>,
        #[serde(default)]
        is_stripped: bool,
    },

    #[serde(alias = "struct")]
    Struct {
        #[serde(default)]
        kind: StructKind,
        #[serde(default)]
        generics: Generics,
        #[serde(default)]
        impls: Vec<Id>,
    },

    #[serde(alias = "union")]
    Union {
        #[serde(default)]
        generics: Generics,
        #[serde(default)]
        fields: Vec<Id>,
        #[serde(default)]
        fields_stripped: bool,
        #[serde(default)]
        impls: Vec<Id>,
    },

    #[serde(alias = "enum")]
    Enum {
        #[serde(default)]
        generics: Generics,
        #[serde(default)]
        variants: Vec<Id>,
        #[serde(default)]
        variants_stripped: bool,
        #[serde(default)]
        impls: Vec<Id>,
    },

    #[serde(alias = "variant")]
    Variant(VariantKind),

    #[serde(alias = "function")]
    Function {
        #[serde(default)]
        sig: FunctionSignature,
        #[serde(default)]
        generics: Generics,
        #[serde(default)]
        has_body: bool,
    },

    #[serde(alias = "trait")]
    Trait {
        #[serde(default)]
        generics: Generics,
        #[serde(default)]
        bounds: Vec<GenericBound>,
        #[serde(default)]
        items: Vec<Id>,
        #[serde(default)]
        implementations: Vec<Id>,
        #[serde(default)]
        is_auto: bool,
        #[serde(default)]
        is_unsafe: bool,
        #[serde(default)]
        is_object_safe: bool,
    },

    #[serde(alias = "impl")]
    Impl {
        #[serde(default)]
        generics: Generics,
        #[serde(rename = "trait")]
        #[serde(default)]
        trait_: Option<ResolvedPath>,
        #[serde(rename = "for")]
        for_: Type,
        #[serde(default)]
        items: Vec<Id>,
        #[serde(default)]
        is_unsafe: bool,
        #[serde(default)]
        is_negative: bool,
        #[serde(default)]
        is_synthetic: bool,
        #[serde(default)]
        blanket_impl: Option<Type>,
    },

    #[serde(alias = "use")]
    Use {
        #[serde(default)]
        source: String,
        #[serde(default)]
        name: Option<String>,
        #[serde(default)]
        id: Option<Id>,
        #[serde(default)]
        is_glob: bool,
    },

    #[serde(alias = "type_alias")]
    TypeAlias {
        #[serde(default)]
        generics: Generics,
        #[serde(rename = "type")]
        #[serde(default)]
        type_: Option<Type>,
    },

    #[serde(alias = "constant")]
    Constant {
        #[serde(rename = "type")]
        type_: Type,
        #[serde(rename = "const")]
        #[serde(default)]
        value: Option<String>,
    },

    #[serde(alias = "static")]
    Static {
        #[serde(rename = "type")]
        type_: Type,
        #[serde(default)]
        is_mutable: bool,
        #[serde(default)]
        value: Option<String>,
    },

    #[serde(alias = "struct_field")]
    StructField(Type),

    #[serde(alias = "macro")]
    Macro(String),

    #[serde(alias = "assoc_const")]
    AssocConst {
        #[serde(rename = "type")]
        type_: Type,
        #[serde(default)]
        value: Option<String>,
    },

    #[serde(alias = "assoc_type")]
    AssocType {
        #[serde(default)]
        generics: Generics,
        #[serde(default)]
        bounds: Vec<GenericBound>,
        #[serde(rename = "type")]
        #[serde(default)]
        type_: Option<Type>,
    },

    /// Catch-all for unrecognized item kinds (forward compatibility).
    #[default]
    #[serde(other)]
    Unknown,
}

/// Struct layout kind.
#[derive(Debug, Deserialize, Default)]
#[serde(tag = "kind", content = "fields")]
pub enum StructKind {
    #[default]
    #[serde(alias = "unit")]
    Unit,
    #[serde(alias = "tuple")]
    Tuple(Vec<Option<Id>>),
    #[serde(alias = "plain")]
    Plain {
        fields: Vec<Id>,
        #[serde(default)]
        fields_stripped: bool,
    },
}

/// Enum variant kind.
#[derive(Debug, Deserialize, Default)]
#[serde(tag = "kind")]
pub enum VariantKind {
    #[default]
    #[serde(alias = "plain")]
    Plain,
    #[serde(alias = "tuple")]
    Tuple(Vec<Option<Id>>),
    #[serde(alias = "struct")]
    Struct {
        fields: Vec<Id>,
        #[serde(default)]
        fields_stripped: bool,
    },
}

/// A resolved path reference to another item.
#[derive(Debug, Clone, Deserialize, Default)]
pub struct ResolvedPath {
    pub name: String,
    #[serde(default)]
    pub id: Option<Id>,
    #[serde(default)]
    pub args: Option<Box<GenericArgs>>,
}

/// A type reference in the rustdoc JSON.
///
/// Uses adjacently tagged representation: `{ "kind": "...", "inner": ... }`.
/// The `Unknown` variant catches any unrecognized type kinds.
#[derive(Debug, Clone, Deserialize, Default)]
#[serde(tag = "kind", content = "inner")]
pub enum Type {
    #[serde(alias = "resolved_path")]
    ResolvedPath(ResolvedPath),

    #[serde(alias = "primitive")]
    Primitive(String),

    #[serde(alias = "tuple")]
    Tuple(Vec<Type>),

    #[serde(alias = "slice")]
    Slice(Box<Type>),

    #[serde(alias = "array")]
    Array {
        #[serde(rename = "type")]
        type_: Box<Type>,
        len: String,
    },

    #[serde(alias = "raw_pointer")]
    RawPointer {
        #[serde(default)]
        is_mutable: bool,
        #[serde(rename = "type")]
        type_: Box<Type>,
    },

    #[serde(alias = "borrowed_ref")]
    BorrowedRef {
        #[serde(default)]
        lifetime: Option<String>,
        #[serde(default)]
        is_mutable: bool,
        #[serde(rename = "type")]
        type_: Box<Type>,
    },

    #[serde(alias = "function_pointer")]
    FunctionPointer(Box<FunctionPointer>),

    #[serde(alias = "qualified_path")]
    QualifiedPath {
        name: String,
        #[serde(default)]
        args: Option<Box<GenericArgs>>,
        self_type: Box<Type>,
        #[serde(rename = "trait")]
        #[serde(default)]
        trait_: Option<ResolvedPath>,
    },

    #[serde(alias = "impl_trait")]
    ImplTrait(Vec<GenericBound>),

    #[serde(alias = "dyn_trait")]
    DynTrait(DynTrait),

    #[serde(alias = "infer")]
    Infer,

    #[serde(alias = "generic")]
    Generic(String),

    /// Catch-all for unrecognized type kinds (forward compatibility).
    #[default]
    #[serde(other)]
    Unknown,
}

/// A function pointer type.
#[derive(Debug, Clone, Deserialize, Default)]
pub struct FunctionPointer {
    #[serde(default)]
    pub sig: FunctionSignature,
    #[serde(default)]
    pub generic_params: Vec<GenericParamDef>,
    #[serde(default)]
    pub header: FunctionHeader,
}

/// Function signature.
#[derive(Debug, Clone, Deserialize, Default)]
pub struct FunctionSignature {
    /// Parameter (name, type) pairs.
    #[serde(default)]
    pub inputs: Vec<(String, Type)>,
    /// Return type (None for -> ()).
    #[serde(default)]
    pub output: Option<Type>,
    #[serde(default)]
    pub is_c_variadic: bool,
}

/// Function header qualifiers.
#[derive(Debug, Clone, Deserialize, Default)]
pub struct FunctionHeader {
    #[serde(default)]
    pub is_const: bool,
    #[serde(default)]
    pub is_unsafe: bool,
    #[serde(default)]
    pub is_async: bool,
    #[serde(default)]
    pub abi: Option<String>,
}

/// Generics information.
#[derive(Debug, Clone, Deserialize, Default)]
pub struct Generics {
    #[serde(default)]
    pub params: Vec<GenericParamDef>,
    #[serde(default)]
    pub where_predicates: Vec<WherePredicate>,
}

/// A generic parameter definition.
#[derive(Debug, Clone, Deserialize)]
pub struct GenericParamDef {
    pub name: String,
    #[serde(default)]
    pub kind: GenericParamDefKind,
}

/// Kind of generic parameter.
#[derive(Debug, Clone, Deserialize, Default)]
#[serde(tag = "kind", content = "inner")]
pub enum GenericParamDefKind {
    #[serde(alias = "lifetime")]
    Lifetime {
        #[serde(default)]
        outlives: Vec<String>,
    },

    #[serde(alias = "type")]
    Type {
        #[serde(default)]
        bounds: Vec<GenericBound>,
        #[serde(default)]
        default: Option<Type>,
        #[serde(default)]
        is_synthetic: bool,
    },

    #[serde(alias = "const")]
    Const {
        #[serde(rename = "type")]
        type_: Type,
        #[serde(default)]
        default: Option<String>,
    },

    /// Catch-all for unrecognized generic parameter kinds.
    #[default]
    #[serde(other)]
    Unknown,
}

/// A generic bound on a type parameter.
#[derive(Debug, Clone, Deserialize)]
#[serde(tag = "kind", content = "inner")]
pub enum GenericBound {
    #[serde(alias = "trait_bound")]
    TraitBound {
        #[serde(rename = "trait")]
        trait_: ResolvedPath,
        #[serde(default)]
        modifier: TraitBoundModifier,
        #[serde(default)]
        generic_params: Vec<GenericParamDef>,
    },

    #[serde(alias = "outlives")]
    Outlives(String),

    #[serde(alias = "use")]
    Use(Vec<String>),
}

/// Trait bound modifier.
#[derive(Debug, Clone, Deserialize, Default)]
#[serde(rename_all = "snake_case")]
pub enum TraitBoundModifier {
    #[default]
    None,
    Maybe,
    MaybeConst,
}

/// Where predicate.
#[derive(Debug, Clone, Deserialize)]
#[serde(tag = "kind", content = "inner")]
pub enum WherePredicate {
    #[serde(alias = "bound_predicate")]
    BoundPredicate {
        #[serde(rename = "type")]
        type_: Type,
        #[serde(default)]
        bounds: Vec<GenericBound>,
        #[serde(default)]
        generic_params: Vec<GenericParamDef>,
    },

    #[serde(alias = "lifetime_predicate")]
    LifetimePredicate {
        lifetime: String,
        #[serde(default)]
        outlives: Vec<String>,
    },

    #[serde(alias = "eq_predicate")]
    EqPredicate { lhs: Type, rhs: Type },
}

/// Generic arguments.
#[derive(Debug, Clone, Deserialize)]
#[serde(tag = "kind", content = "inner")]
pub enum GenericArgs {
    #[serde(alias = "angle_bracketed")]
    AngleBracketed {
        #[serde(default)]
        args: Vec<GenericArg>,
        #[serde(default)]
        constraints: Vec<TypeBinding>,
    },

    #[serde(alias = "parenthesized")]
    Parenthesized {
        #[serde(default)]
        inputs: Vec<Type>,
        #[serde(default)]
        output: Option<Type>,
    },
}

/// A single generic argument.
#[derive(Debug, Clone, Deserialize)]
#[serde(tag = "kind", content = "inner")]
pub enum GenericArg {
    #[serde(alias = "lifetime")]
    Lifetime(String),

    #[serde(alias = "type")]
    Type(Type),

    #[serde(alias = "const")]
    Const(ConstantValue),

    #[serde(alias = "infer")]
    Infer,
}

/// A constant value.
#[derive(Debug, Clone, Deserialize)]
pub struct ConstantValue {
    #[serde(default)]
    pub value: Option<String>,
    #[serde(default)]
    pub is_literal: bool,
}

/// Type binding (e.g., `Iterator<Item = T>`).
#[derive(Debug, Clone, Deserialize)]
pub struct TypeBinding {
    pub name: String,
    #[serde(default)]
    pub args: Option<GenericArgs>,
    #[serde(default)]
    pub binding: TypeBindingKind,
}

/// Kind of type binding.
#[derive(Debug, Clone, Deserialize, Default)]
#[serde(tag = "kind", content = "inner")]
pub enum TypeBindingKind {
    #[serde(alias = "equality")]
    Equality(Type),

    #[serde(alias = "constraint")]
    Constraint(Vec<GenericBound>),

    /// Catch-all for unrecognized binding kinds.
    #[default]
    #[serde(other)]
    Unknown,
}

/// Dynamic trait object.
#[derive(Debug, Clone, Deserialize, Default)]
pub struct DynTrait {
    #[serde(default)]
    pub traits: Vec<PolyTrait>,
    #[serde(default)]
    pub lifetime: Option<String>,
}

/// A trait in a dyn trait object (may have higher-ranked lifetimes).
#[derive(Debug, Clone, Deserialize)]
pub struct PolyTrait {
    #[serde(rename = "trait")]
    pub trait_: ResolvedPath,
    #[serde(default)]
    pub generic_params: Vec<GenericParamDef>,
}
