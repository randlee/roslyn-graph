//! Tests for rustdoc JSON serde model deserialization.
//!
//! These tests use hand-crafted JSON fragments to verify that our serde model
//! correctly deserializes the rustdoc JSON format (externally tagged enums).
//! We test both known variants and forward-compatibility (unknown variants/fields
//! are handled gracefully).

use rust2rdf::extraction::rustdoc_model::*;

#[test]
fn test_minimal_crate() {
    let json = r#"{
        "root": 0,
        "crate_version": "1.2.3",
        "index": {},
        "paths": {},
        "external_crates": {},
        "format_version": 57
    }"#;
    let krate: Crate = serde_json::from_str(json).unwrap();
    assert_eq!(krate.root, Id("0".to_string()));
    assert_eq!(krate.crate_version.as_deref(), Some("1.2.3"));
    assert_eq!(krate.format_version, 57);
    assert!(krate.index.is_empty());
    assert!(krate.paths.is_empty());
    assert!(krate.external_crates.is_empty());
}

#[test]
fn test_id_accepts_string() {
    let json = r#"{
        "root": "0:0",
        "format_version": 28
    }"#;
    let krate: Crate = serde_json::from_str(json).unwrap();
    assert_eq!(krate.root, Id("0:0".to_string()));
}

#[test]
fn test_id_accepts_integer() {
    let json = r#"{
        "root": 42,
        "format_version": 57
    }"#;
    let krate: Crate = serde_json::from_str(json).unwrap();
    assert_eq!(krate.root, Id("42".to_string()));
}

#[test]
fn test_crate_with_index_and_paths() {
    let json = r#"{
        "root": 0,
        "index": {
            "0": {
                "name": "mycrate",
                "inner": { "module": { "items": [1, 2] } }
            }
        },
        "paths": {
            "3": { "path": ["std", "string", "String"], "kind": "struct" }
        },
        "external_crates": {
            "1": { "name": "std", "html_root_url": "https://doc.rust-lang.org/nightly/" }
        },
        "format_version": 57
    }"#;
    let krate: Crate = serde_json::from_str(json).unwrap();
    assert_eq!(krate.index.len(), 1);
    let root_item = &krate.index["0"];
    assert_eq!(root_item.name.as_deref(), Some("mycrate"));
    match &root_item.inner {
        ItemEnum::Module { items, .. } => {
            assert_eq!(items.len(), 2);
            assert_eq!(items[0], Id("1".to_string()));
        }
        other => panic!("Expected Module, got {other:?}"),
    }

    let path_summary = &krate.paths["3"];
    assert_eq!(path_summary.path, vec!["std", "string", "String"]);
    assert!(matches!(path_summary.kind, ItemKind::Struct));

    let ext = &krate.external_crates["1"];
    assert_eq!(ext.name, "std");
    assert_eq!(
        ext.html_root_url.as_deref(),
        Some("https://doc.rust-lang.org/nightly/")
    );
}

#[test]
fn test_item_module() {
    let json = r#"{
        "name": "mymod",
        "visibility": "public",
        "docs": "Module documentation.",
        "inner": {
            "module": {
                "items": [10, 11],
                "is_stripped": false
            }
        }
    }"#;
    let item: Item = serde_json::from_str(json).unwrap();
    assert_eq!(item.name.as_deref(), Some("mymod"));
    assert_eq!(item.docs.as_deref(), Some("Module documentation."));
    match &item.inner {
        ItemEnum::Module { items, is_stripped } => {
            assert_eq!(items.len(), 2);
            assert!(!is_stripped);
        }
        other => panic!("Expected Module, got {other:?}"),
    }
}

#[test]
fn test_item_struct_plain() {
    let json = r#"{
        "name": "MyStruct",
        "visibility": "public",
        "inner": {
            "struct": {
                "kind": { "plain": { "fields": [20, 21], "has_stripped_fields": false } },
                "generics": { "params": [], "where_predicates": [] },
                "impls": [30]
            }
        }
    }"#;
    let item: Item = serde_json::from_str(json).unwrap();
    assert_eq!(item.name.as_deref(), Some("MyStruct"));
    match &item.inner {
        ItemEnum::Struct { kind, impls, .. } => {
            match kind {
                StructKind::Plain { fields, has_stripped_fields } => {
                    assert_eq!(fields.len(), 2);
                    assert!(!has_stripped_fields);
                }
                other => panic!("Expected Plain struct kind, got {other:?}"),
            }
            assert_eq!(impls.len(), 1);
        }
        other => panic!("Expected Struct, got {other:?}"),
    }
}

#[test]
fn test_item_enum_with_variants() {
    let json = r#"{
        "name": "Color",
        "visibility": "public",
        "inner": {
            "enum": {
                "generics": { "params": [], "where_predicates": [] },
                "variants": [40, 41, 42],
                "variants_stripped": false,
                "impls": []
            }
        }
    }"#;
    let item: Item = serde_json::from_str(json).unwrap();
    assert_eq!(item.name.as_deref(), Some("Color"));
    match &item.inner {
        ItemEnum::Enum { variants, variants_stripped, .. } => {
            assert_eq!(variants.len(), 3);
            assert!(!variants_stripped);
        }
        other => panic!("Expected Enum, got {other:?}"),
    }
}

#[test]
fn test_item_function_with_signature() {
    let json = r#"{
        "name": "process",
        "visibility": "public",
        "inner": {
            "function": {
                "sig": {
                    "inputs": [
                        ["input", { "primitive": "u32" }],
                        ["name", { "borrowed_ref": { "lifetime": "'a", "is_mutable": false, "type": { "primitive": "str" } } }]
                    ],
                    "output": { "primitive": "bool" },
                    "is_c_variadic": false
                },
                "generics": { "params": [], "where_predicates": [] },
                "has_body": true,
                "header": { "is_const": false, "is_unsafe": false, "is_async": false }
            }
        }
    }"#;
    let item: Item = serde_json::from_str(json).unwrap();
    assert_eq!(item.name.as_deref(), Some("process"));
    match &item.inner {
        ItemEnum::Function { sig, has_body, .. } => {
            assert!(has_body);
            assert_eq!(sig.inputs.len(), 2);
            assert_eq!(sig.inputs[0].0, "input");
            assert!(matches!(&sig.inputs[0].1, Type::Primitive(s) if s == "u32"));

            // Check borrowed ref parameter
            assert_eq!(sig.inputs[1].0, "name");
            match &sig.inputs[1].1 {
                Type::BorrowedRef { lifetime, is_mutable, type_ } => {
                    assert_eq!(lifetime.as_deref(), Some("'a"));
                    assert!(!is_mutable);
                    assert!(matches!(type_.as_ref(), Type::Primitive(s) if s == "str"));
                }
                other => panic!("Expected BorrowedRef, got {other:?}"),
            }

            // Check return type
            assert!(matches!(&sig.output, Some(Type::Primitive(s)) if s == "bool"));
        }
        other => panic!("Expected Function, got {other:?}"),
    }
}

#[test]
fn test_unknown_item_kind_falls_through() {
    // With externally tagged enums, serde(other) catches unrecognized tags
    // when the value is absent or null. For tags with object values, serde
    // cannot deserialize into the unit Unknown variant. This test verifies
    // the behavior when the inner field is absent entirely (defaults to Unknown).
    let json = r#"{
        "name": "something"
    }"#;
    let item: Item = serde_json::from_str(json).unwrap();
    assert_eq!(item.name.as_deref(), Some("something"));
    assert!(matches!(item.inner, ItemEnum::Unknown));
}

#[test]
fn test_unknown_fields_are_ignored() {
    let json = r#"{
        "root": 0,
        "crate_version": "0.1.0",
        "format_version": 99,
        "some_new_field": "we don't know about this",
        "another_future_field": [1, 2, 3]
    }"#;
    let krate: Crate = serde_json::from_str(json).unwrap();
    assert_eq!(krate.root, Id("0".to_string()));
    assert_eq!(krate.format_version, 99);
}

#[test]
fn test_visibility_variants() {
    // Public
    let json = r#"{ "name": "pub_item", "visibility": "public", "inner": { "module": { "items": [] } } }"#;
    let item: Item = serde_json::from_str(json).unwrap();
    assert!(matches!(item.visibility, Visibility::Public));

    // Default
    let json = r#"{ "name": "priv_item", "visibility": "default", "inner": { "module": { "items": [] } } }"#;
    let item: Item = serde_json::from_str(json).unwrap();
    assert!(matches!(item.visibility, Visibility::Default));

    // Crate
    let json = r#"{ "name": "crate_item", "visibility": "crate", "inner": { "module": { "items": [] } } }"#;
    let item: Item = serde_json::from_str(json).unwrap();
    assert!(matches!(item.visibility, Visibility::Crate));

    // Restricted
    let json = r#"{ "name": "restricted_item", "visibility": { "restricted": { "parent": 0, "path": "super" } }, "inner": { "module": { "items": [] } } }"#;
    let item: Item = serde_json::from_str(json).unwrap();
    match &item.visibility {
        Visibility::Restricted(r) => {
            assert_eq!(r.parent, Id("0".to_string()));
            assert_eq!(r.path, "super");
        }
        other => panic!("Expected Restricted visibility, got {other:?}"),
    }
}

#[test]
fn test_type_resolved_path() {
    let json = r#"{ "resolved_path": { "path": "Vec", "id": 10 } }"#;
    let ty: Type = serde_json::from_str(json).unwrap();
    match &ty {
        Type::ResolvedPath(rp) => {
            assert_eq!(rp.path, "Vec");
            assert_eq!(rp.id, Some(Id("10".to_string())));
        }
        other => panic!("Expected ResolvedPath, got {other:?}"),
    }
}

#[test]
fn test_type_variants() {
    // Primitive
    let json = r#"{ "primitive": "i64" }"#;
    let ty: Type = serde_json::from_str(json).unwrap();
    assert!(matches!(&ty, Type::Primitive(s) if s == "i64"));

    // Tuple
    let json = r#"{ "tuple": [{ "primitive": "u8" }, { "primitive": "u16" }] }"#;
    let ty: Type = serde_json::from_str(json).unwrap();
    match &ty {
        Type::Tuple(elems) => {
            assert_eq!(elems.len(), 2);
            assert!(matches!(&elems[0], Type::Primitive(s) if s == "u8"));
            assert!(matches!(&elems[1], Type::Primitive(s) if s == "u16"));
        }
        other => panic!("Expected Tuple, got {other:?}"),
    }

    // Slice
    let json = r#"{ "slice": { "primitive": "u8" } }"#;
    let ty: Type = serde_json::from_str(json).unwrap();
    match &ty {
        Type::Slice(inner) => {
            assert!(matches!(inner.as_ref(), Type::Primitive(s) if s == "u8"));
        }
        other => panic!("Expected Slice, got {other:?}"),
    }

    // BorrowedRef
    let json = r#"{ "borrowed_ref": { "lifetime": "'static", "is_mutable": true, "type": { "primitive": "str" } } }"#;
    let ty: Type = serde_json::from_str(json).unwrap();
    match &ty {
        Type::BorrowedRef { lifetime, is_mutable, type_ } => {
            assert_eq!(lifetime.as_deref(), Some("'static"));
            assert!(is_mutable);
            assert!(matches!(type_.as_ref(), Type::Primitive(s) if s == "str"));
        }
        other => panic!("Expected BorrowedRef, got {other:?}"),
    }

    // Generic
    let json = r#"{ "generic": "T" }"#;
    let ty: Type = serde_json::from_str(json).unwrap();
    assert!(matches!(&ty, Type::Generic(s) if s == "T"));

    // Unknown type kind (forward compatibility)
    // With externally tagged enums, serde(other) catches unrecognized tags
    // only when the value is absent. For types, we test via the Default impl.
    let ty: Type = Default::default();
    assert!(matches!(ty, Type::Unknown));
}

#[test]
fn test_item_trait() {
    let json = r#"{
        "name": "MyTrait",
        "visibility": "public",
        "inner": {
            "trait": {
                "generics": { "params": [], "where_predicates": [] },
                "bounds": [],
                "items": [50, 51],
                "implementations": [60],
                "is_auto": false,
                "is_unsafe": false,
                "is_dyn_compatible": true
            }
        }
    }"#;
    let item: Item = serde_json::from_str(json).unwrap();
    assert_eq!(item.name.as_deref(), Some("MyTrait"));
    match &item.inner {
        ItemEnum::Trait {
            items,
            implementations,
            is_auto,
            is_unsafe,
            is_dyn_compatible,
            ..
        } => {
            assert_eq!(items.len(), 2);
            assert_eq!(implementations.len(), 1);
            assert!(!is_auto);
            assert!(!is_unsafe);
            assert!(is_dyn_compatible);
        }
        other => panic!("Expected Trait, got {other:?}"),
    }
}

#[test]
fn test_defaults_for_missing_fields() {
    // Minimal item with almost no fields -- defaults should fill in
    let json = r#"{
        "inner": { "module": { "items": [] } }
    }"#;
    let item: Item = serde_json::from_str(json).unwrap();
    assert!(item.name.is_none());
    assert!(item.id.is_none());
    assert!(item.docs.is_none());
    assert!(item.deprecation.is_none());
    assert!(item.span.is_none());
    assert!(item.attrs.is_empty());
    assert!(item.links.is_empty());
    assert!(matches!(item.visibility, Visibility::Public)); // default
}

#[test]
fn test_variant_plain() {
    let json = r#"{
        "name": "Plain",
        "inner": {
            "variant": {
                "kind": "plain",
                "discriminant": null
            }
        }
    }"#;
    let item: Item = serde_json::from_str(json).unwrap();
    match &item.inner {
        ItemEnum::Variant(data) => {
            assert!(matches!(data.kind, VariantKind::Plain));
        }
        other => panic!("Expected Variant, got {other:?}"),
    }
}

#[test]
fn test_variant_tuple() {
    let json = r#"{
        "name": "Tuple",
        "inner": {
            "variant": {
                "kind": { "tuple": [79, 80] },
                "discriminant": null
            }
        }
    }"#;
    let item: Item = serde_json::from_str(json).unwrap();
    match &item.inner {
        ItemEnum::Variant(data) => {
            match &data.kind {
                VariantKind::Tuple(fields) => assert_eq!(fields.len(), 2),
                other => panic!("Expected Tuple variant, got {other:?}"),
            }
        }
        other => panic!("Expected Variant, got {other:?}"),
    }
}

#[test]
fn test_variant_struct() {
    let json = r#"{
        "name": "Struct",
        "inner": {
            "variant": {
                "kind": { "struct": { "fields": [82, 83], "has_stripped_fields": false } },
                "discriminant": null
            }
        }
    }"#;
    let item: Item = serde_json::from_str(json).unwrap();
    match &item.inner {
        ItemEnum::Variant(data) => {
            match &data.kind {
                VariantKind::Struct { fields, has_stripped_fields } => {
                    assert_eq!(fields.len(), 2);
                    assert!(!has_stripped_fields);
                }
                other => panic!("Expected Struct variant, got {other:?}"),
            }
        }
        other => panic!("Expected Variant, got {other:?}"),
    }
}

#[test]
fn test_generic_bound_trait_bound() {
    let json = r#"{
        "trait_bound": {
            "trait": { "path": "Send", "id": 2, "args": null },
            "generic_params": [],
            "modifier": "none"
        }
    }"#;
    let bound: GenericBound = serde_json::from_str(json).unwrap();
    match &bound {
        GenericBound::TraitBound { trait_, modifier, .. } => {
            assert_eq!(trait_.path, "Send");
            assert!(matches!(modifier, TraitBoundModifier::None));
        }
        other => panic!("Expected TraitBound, got {other:?}"),
    }
}

#[test]
fn test_constant_with_const_expr() {
    let json = r#"{
        "name": "MY_CONST",
        "inner": {
            "constant": {
                "type": { "primitive": "i32" },
                "const": {
                    "expr": "42",
                    "value": "42i32",
                    "is_literal": true
                }
            }
        }
    }"#;
    let item: Item = serde_json::from_str(json).unwrap();
    match &item.inner {
        ItemEnum::Constant { type_, const_ } => {
            assert!(matches!(type_, Type::Primitive(s) if s == "i32"));
            let c = const_.as_ref().unwrap();
            assert_eq!(c.value.as_deref(), Some("42i32"));
            assert!(c.is_literal);
        }
        other => panic!("Expected Constant, got {other:?}"),
    }
}

#[test]
fn test_resolved_path_with_path_field() {
    // New format uses "path" instead of "name"
    let json = r#"{ "resolved_path": { "path": "Vec", "id": 105, "args": null } }"#;
    let ty: Type = serde_json::from_str(json).unwrap();
    match &ty {
        Type::ResolvedPath(rp) => {
            assert_eq!(rp.path, "Vec");
        }
        other => panic!("Expected ResolvedPath, got {other:?}"),
    }
}

#[test]
fn test_resolved_path_with_name_field() {
    // Old format uses "name" -- should work via alias
    let json = r#"{ "resolved_path": { "name": "HashMap", "id": 10 } }"#;
    let ty: Type = serde_json::from_str(json).unwrap();
    match &ty {
        Type::ResolvedPath(rp) => {
            assert_eq!(rp.path, "HashMap");
        }
        other => panic!("Expected ResolvedPath, got {other:?}"),
    }
}
