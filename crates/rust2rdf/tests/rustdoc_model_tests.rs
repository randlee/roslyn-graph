//! Tests for rustdoc JSON serde model deserialization.
//!
//! These tests use hand-crafted JSON fragments to verify that our serde model
//! correctly deserializes the rustdoc JSON format. We test both known variants
//! and forward-compatibility (unknown variants/fields are handled gracefully).

use rust2rdf::extraction::rustdoc_model::*;

#[test]
fn test_minimal_crate() {
    let json = r#"{
        "root": "0:0",
        "crate_version": "1.2.3",
        "index": {},
        "paths": {},
        "external_crates": {},
        "format_version": 28
    }"#;
    let krate: Crate = serde_json::from_str(json).unwrap();
    assert_eq!(krate.root, Id("0:0".to_string()));
    assert_eq!(krate.crate_version.as_deref(), Some("1.2.3"));
    assert_eq!(krate.format_version, 28);
    assert!(krate.index.is_empty());
    assert!(krate.paths.is_empty());
    assert!(krate.external_crates.is_empty());
}

#[test]
fn test_crate_with_index_and_paths() {
    let json = r#"{
        "root": "0:0",
        "index": {
            "0:0": {
                "name": "mycrate",
                "inner": { "kind": "module", "inner": { "items": ["0:1", "0:2"] } }
            }
        },
        "paths": {
            "0:3": { "path": ["std", "string", "String"], "kind": "struct" }
        },
        "external_crates": {
            "1": { "name": "std", "html_root_url": "https://doc.rust-lang.org/nightly/" }
        },
        "format_version": 28
    }"#;
    let krate: Crate = serde_json::from_str(json).unwrap();
    assert_eq!(krate.index.len(), 1);
    let root_item = &krate.index["0:0"];
    assert_eq!(root_item.name.as_deref(), Some("mycrate"));
    match &root_item.inner {
        ItemEnum::Module { items, .. } => {
            assert_eq!(items.len(), 2);
            assert_eq!(items[0], Id("0:1".to_string()));
        }
        other => panic!("Expected Module, got {other:?}"),
    }

    let path_summary = &krate.paths["0:3"];
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
            "kind": "module",
            "inner": {
                "items": ["1:0", "1:1"],
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
            "kind": "struct",
            "inner": {
                "kind": { "kind": "plain", "fields": { "fields": ["2:0", "2:1"], "fields_stripped": false } },
                "generics": { "params": [], "where_predicates": [] },
                "impls": ["3:0"]
            }
        }
    }"#;
    let item: Item = serde_json::from_str(json).unwrap();
    assert_eq!(item.name.as_deref(), Some("MyStruct"));
    match &item.inner {
        ItemEnum::Struct { kind, impls, .. } => {
            match kind {
                StructKind::Plain { fields, fields_stripped } => {
                    assert_eq!(fields.len(), 2);
                    assert!(!fields_stripped);
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
            "kind": "enum",
            "inner": {
                "generics": { "params": [], "where_predicates": [] },
                "variants": ["4:0", "4:1", "4:2"],
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
            "kind": "function",
            "inner": {
                "sig": {
                    "inputs": [
                        ["input", { "kind": "primitive", "inner": "u32" }],
                        ["name", { "kind": "borrowed_ref", "inner": { "lifetime": "'a", "is_mutable": false, "type": { "kind": "primitive", "inner": "str" } } }]
                    ],
                    "output": { "kind": "primitive", "inner": "bool" },
                    "is_c_variadic": false
                },
                "generics": { "params": [], "where_predicates": [] },
                "has_body": true
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
    // When the kind is unrecognized, serde(other) catches it as Unknown.
    // Note: with adjacently tagged enums, the Unknown unit variant works
    // when the "inner" content field is absent.
    let json = r#"{
        "name": "something",
        "inner": {
            "kind": "future_item_kind_v99"
        }
    }"#;
    let item: Item = serde_json::from_str(json).unwrap();
    assert_eq!(item.name.as_deref(), Some("something"));
    assert!(matches!(item.inner, ItemEnum::Unknown));
}

#[test]
fn test_unknown_fields_are_ignored() {
    let json = r#"{
        "root": "0:0",
        "crate_version": "0.1.0",
        "format_version": 99,
        "some_new_field": "we don't know about this",
        "another_future_field": [1, 2, 3]
    }"#;
    let krate: Crate = serde_json::from_str(json).unwrap();
    assert_eq!(krate.root, Id("0:0".to_string()));
    assert_eq!(krate.format_version, 99);
}

#[test]
fn test_visibility_variants() {
    // Public
    let json = r#"{ "name": "pub_item", "visibility": "public", "inner": { "kind": "module", "inner": { "items": [] } } }"#;
    let item: Item = serde_json::from_str(json).unwrap();
    assert!(matches!(item.visibility, Visibility::Public));

    // Default
    let json = r#"{ "name": "priv_item", "visibility": "default", "inner": { "kind": "module", "inner": { "items": [] } } }"#;
    let item: Item = serde_json::from_str(json).unwrap();
    assert!(matches!(item.visibility, Visibility::Default));

    // Crate
    let json = r#"{ "name": "crate_item", "visibility": "crate", "inner": { "kind": "module", "inner": { "items": [] } } }"#;
    let item: Item = serde_json::from_str(json).unwrap();
    assert!(matches!(item.visibility, Visibility::Crate));

    // Restricted
    let json = r#"{ "name": "restricted_item", "visibility": { "restricted": { "parent": "0:0", "path": "super" } }, "inner": { "kind": "module", "inner": { "items": [] } } }"#;
    let item: Item = serde_json::from_str(json).unwrap();
    match &item.visibility {
        Visibility::Restricted(r) => {
            assert_eq!(r.parent, Id("0:0".to_string()));
            assert_eq!(r.path, "super");
        }
        other => panic!("Expected Restricted visibility, got {other:?}"),
    }
}

#[test]
fn test_type_resolved_path() {
    let json = r#"{ "kind": "resolved_path", "inner": { "name": "Vec", "id": "1:0" } }"#;
    let ty: Type = serde_json::from_str(json).unwrap();
    match &ty {
        Type::ResolvedPath(rp) => {
            assert_eq!(rp.name, "Vec");
            assert_eq!(rp.id, Some(Id("1:0".to_string())));
        }
        other => panic!("Expected ResolvedPath, got {other:?}"),
    }
}

#[test]
fn test_type_variants() {
    // Primitive
    let json = r#"{ "kind": "primitive", "inner": "i64" }"#;
    let ty: Type = serde_json::from_str(json).unwrap();
    assert!(matches!(&ty, Type::Primitive(s) if s == "i64"));

    // Tuple
    let json = r#"{ "kind": "tuple", "inner": [{ "kind": "primitive", "inner": "u8" }, { "kind": "primitive", "inner": "u16" }] }"#;
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
    let json = r#"{ "kind": "slice", "inner": { "kind": "primitive", "inner": "u8" } }"#;
    let ty: Type = serde_json::from_str(json).unwrap();
    match &ty {
        Type::Slice(inner) => {
            assert!(matches!(inner.as_ref(), Type::Primitive(s) if s == "u8"));
        }
        other => panic!("Expected Slice, got {other:?}"),
    }

    // BorrowedRef
    let json = r#"{ "kind": "borrowed_ref", "inner": { "lifetime": "'static", "is_mutable": true, "type": { "kind": "primitive", "inner": "str" } } }"#;
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
    let json = r#"{ "kind": "generic", "inner": "T" }"#;
    let ty: Type = serde_json::from_str(json).unwrap();
    assert!(matches!(&ty, Type::Generic(s) if s == "T"));

    // Unknown type kind (forward compatibility)
    // Note: with adjacently tagged enums, the Unknown unit variant works
    // when the "inner" content field is absent.
    let json = r#"{ "kind": "some_future_type" }"#;
    let ty: Type = serde_json::from_str(json).unwrap();
    assert!(matches!(ty, Type::Unknown));
}

#[test]
fn test_item_trait() {
    let json = r#"{
        "name": "MyTrait",
        "visibility": "public",
        "inner": {
            "kind": "trait",
            "inner": {
                "generics": { "params": [], "where_predicates": [] },
                "bounds": [],
                "items": ["5:0", "5:1"],
                "implementations": ["6:0"],
                "is_auto": false,
                "is_unsafe": false,
                "is_object_safe": true
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
            is_object_safe,
            ..
        } => {
            assert_eq!(items.len(), 2);
            assert_eq!(implementations.len(), 1);
            assert!(!is_auto);
            assert!(!is_unsafe);
            assert!(is_object_safe);
        }
        other => panic!("Expected Trait, got {other:?}"),
    }
}

#[test]
fn test_defaults_for_missing_fields() {
    // Minimal item with almost no fields -- defaults should fill in
    let json = r#"{
        "inner": { "kind": "module", "inner": { "items": [] } }
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
