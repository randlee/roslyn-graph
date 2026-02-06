//! Serde model for rustdoc JSON output format.
//!
//! These types match the rustdoc JSON schema (format version 35+).
//! We only model fields we need for extraction. Unknown fields are silently
//! ignored via serde defaults.
//!
//! Design notes:
//! - We use `#[serde(default)]` liberally for forward/backward compatibility.
//! - Enums use externally tagged representation (serde default), matching
//!   the rustdoc JSON format: `{ "struct": { ... } }`.
//! - Enums with `#[serde(other)]` place the Unknown variant last (serde requirement).
//! - We do NOT use `#[serde(deny_unknown_fields)]` -- unknown fields are ignored.
//! - The `Id` type accepts both string and integer JSON values for compatibility
//!   across rustdoc format versions.

use serde::Deserialize;
use std::collections::HashMap;

/// Newtype for rustdoc item IDs.
///
/// Handles both string IDs (older format versions) and integer IDs (format
/// version 35+) by using a custom deserializer.
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct Id(pub String);

impl<'de> Deserialize<'de> for Id {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: serde::Deserializer<'de>,
    {
        struct IdVisitor;

        impl<'de> serde::de::Visitor<'de> for IdVisitor {
            type Value = Id;

            fn expecting(&self, formatter: &mut std::fmt::Formatter) -> std::fmt::Result {
                formatter.write_str("a string or integer ID")
            }

            fn visit_str<E>(self, v: &str) -> Result<Id, E>
            where
                E: serde::de::Error,
            {
                Ok(Id(v.to_string()))
            }

            fn visit_string<E>(self, v: String) -> Result<Id, E>
            where
                E: serde::de::Error,
            {
                Ok(Id(v))
            }

            fn visit_u64<E>(self, v: u64) -> Result<Id, E>
            where
                E: serde::de::Error,
            {
                Ok(Id(v.to_string()))
            }

            fn visit_i64<E>(self, v: i64) -> Result<Id, E>
            where
                E: serde::de::Error,
            {
                Ok(Id(v.to_string()))
            }
        }

        deserializer.deserialize_any(IdVisitor)
    }
}

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
    /// Attributes (strings or structured objects depending on format version).
    #[serde(default)]
    pub attrs: Vec<serde_json::Value>,
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
/// Uses externally tagged representation (serde default): `{ "module": { ... } }`.
/// The `Unknown` variant catches any unrecognized tag values for forward
/// compatibility.
#[derive(Debug, Deserialize, Default)]
#[serde(rename_all = "snake_case")]
pub enum ItemEnum {
    Module {
        #[serde(default)]
        items: Vec<Id>,
        #[serde(default)]
        is_stripped: bool,
    },

    Struct {
        #[serde(default)]
        kind: StructKind,
        #[serde(default)]
        generics: Generics,
        #[serde(default)]
        impls: Vec<Id>,
    },

    Union {
        #[serde(default)]
        generics: Generics,
        #[serde(default)]
        fields: Vec<Id>,
        #[serde(default, alias = "fields_stripped")]
        has_stripped_fields: bool,
        #[serde(default)]
        impls: Vec<Id>,
    },

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

    Variant(VariantData),

    Function {
        #[serde(default)]
        sig: FunctionSignature,
        #[serde(default)]
        generics: Generics,
        #[serde(default)]
        has_body: bool,
        #[serde(default)]
        header: FunctionHeader,
    },

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
        #[serde(default, alias = "is_object_safe")]
        is_dyn_compatible: bool,
    },

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

    TypeAlias {
        #[serde(default)]
        generics: Generics,
        #[serde(rename = "type")]
        #[serde(default)]
        type_: Option<Type>,
    },

    Constant {
        #[serde(rename = "type")]
        type_: Type,
        #[serde(rename = "const")]
        #[serde(default)]
        const_: Option<ConstExpr>,
    },

    Static {
        #[serde(rename = "type")]
        type_: Type,
        #[serde(default)]
        is_mutable: bool,
        #[serde(default)]
        is_unsafe: bool,
        #[serde(default)]
        expr: Option<String>,
    },

    StructField(Type),

    Macro(String),

    AssocConst {
        #[serde(rename = "type")]
        type_: Type,
        #[serde(default)]
        value: Option<String>,
    },

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

/// A constant expression with value and type information.
#[derive(Debug, Clone, Deserialize, Default)]
pub struct ConstExpr {
    #[serde(default)]
    pub expr: Option<String>,
    #[serde(default)]
    pub value: Option<String>,
    #[serde(default)]
    pub is_literal: bool,
}

/// Struct layout kind.
///
/// Handles three formats:
/// - `"unit"` (string)
/// - `{ "tuple": [...] }` (externally tagged)
/// - `{ "plain": { "fields": [...], "has_stripped_fields": false } }` (externally tagged)
#[derive(Debug, Deserialize, Default)]
#[serde(rename_all = "snake_case")]
pub enum StructKind {
    #[default]
    Unit,
    Tuple(Vec<Option<Id>>),
    Plain {
        fields: Vec<Id>,
        #[serde(default, alias = "fields_stripped")]
        has_stripped_fields: bool,
    },
}

/// Variant data wrapper (contains kind and optional discriminant).
#[derive(Debug, Deserialize, Default)]
pub struct VariantData {
    #[serde(default)]
    pub kind: VariantKind,
    #[serde(default)]
    pub discriminant: Option<Discriminant>,
}

/// Discriminant value for enum variants.
#[derive(Debug, Clone, Deserialize)]
pub struct Discriminant {
    #[serde(default)]
    pub expr: Option<String>,
    #[serde(default)]
    pub value: Option<String>,
}

/// Enum variant kind.
///
/// Handles three formats:
/// - `"plain"` (string)
/// - `{ "tuple": [...] }` (externally tagged)
/// - `{ "struct": { "fields": [...], "has_stripped_fields": false } }` (externally tagged)
#[derive(Debug, Deserialize, Default)]
#[serde(rename_all = "snake_case")]
pub enum VariantKind {
    #[default]
    Plain,
    Tuple(Vec<Option<Id>>),
    Struct {
        fields: Vec<Id>,
        #[serde(default, alias = "fields_stripped")]
        has_stripped_fields: bool,
    },
}

/// A resolved path reference to another item.
#[derive(Debug, Clone, Deserialize, Default)]
pub struct ResolvedPath {
    /// The path string (e.g., "Vec", "std::io::Error").
    /// Field is named `path` in newer format versions, `name` in older ones.
    #[serde(alias = "name")]
    pub path: String,
    #[serde(default)]
    pub id: Option<Id>,
    #[serde(default)]
    pub args: Option<Box<GenericArgs>>,
}

/// A type reference in the rustdoc JSON.
///
/// Uses externally tagged representation: `{ "primitive": "i32" }`.
/// The `Unknown` variant catches any unrecognized type kinds.
#[derive(Debug, Clone, Deserialize, Default)]
#[serde(rename_all = "snake_case")]
pub enum Type {
    ResolvedPath(ResolvedPath),

    Primitive(String),

    Tuple(Vec<Type>),

    Slice(Box<Type>),

    Array {
        #[serde(rename = "type")]
        type_: Box<Type>,
        len: String,
    },

    RawPointer {
        #[serde(default)]
        is_mutable: bool,
        #[serde(rename = "type")]
        type_: Box<Type>,
    },

    BorrowedRef {
        #[serde(default)]
        lifetime: Option<String>,
        #[serde(default)]
        is_mutable: bool,
        #[serde(rename = "type")]
        type_: Box<Type>,
    },

    FunctionPointer(Box<FunctionPointer>),

    QualifiedPath {
        name: String,
        #[serde(default)]
        args: Option<Box<GenericArgs>>,
        self_type: Box<Type>,
        #[serde(rename = "trait")]
        #[serde(default)]
        trait_: Option<ResolvedPath>,
    },

    ImplTrait(Vec<GenericBound>),

    DynTrait(DynTrait),

    Infer,

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
#[serde(rename_all = "snake_case")]
pub enum GenericParamDefKind {
    Lifetime {
        #[serde(default)]
        outlives: Vec<String>,
    },

    Type {
        #[serde(default)]
        bounds: Vec<GenericBound>,
        #[serde(default)]
        default: Option<Type>,
        #[serde(default)]
        is_synthetic: bool,
    },

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
#[serde(rename_all = "snake_case")]
pub enum GenericBound {
    TraitBound {
        #[serde(rename = "trait")]
        trait_: ResolvedPath,
        #[serde(default)]
        modifier: TraitBoundModifier,
        #[serde(default)]
        generic_params: Vec<GenericParamDef>,
    },

    Outlives(String),

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
#[serde(rename_all = "snake_case")]
pub enum WherePredicate {
    BoundPredicate {
        #[serde(rename = "type")]
        type_: Type,
        #[serde(default)]
        bounds: Vec<GenericBound>,
        #[serde(default)]
        generic_params: Vec<GenericParamDef>,
    },

    LifetimePredicate {
        lifetime: String,
        #[serde(default)]
        outlives: Vec<String>,
    },

    EqPredicate { lhs: Type, rhs: Type },
}

/// Generic arguments.
#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum GenericArgs {
    AngleBracketed {
        #[serde(default)]
        args: Vec<GenericArg>,
        #[serde(default)]
        constraints: Vec<TypeBinding>,
    },

    Parenthesized {
        #[serde(default)]
        inputs: Vec<Type>,
        #[serde(default)]
        output: Option<Type>,
    },
}

/// A single generic argument.
#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum GenericArg {
    Lifetime(String),

    Type(Type),

    Const(ConstantValue),

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
#[serde(rename_all = "snake_case")]
pub enum TypeBindingKind {
    Equality(Type),

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
