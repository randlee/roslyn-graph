use rust2rdf::model::iri::IriMinter;

const BASE: &str = "http://example.org/rust";

fn minter() -> IriMinter {
    IriMinter::new(BASE)
}

// --- Crate IRI ---

#[test]
fn crate_iri_basic() {
    let m = minter();
    assert_eq!(
        m.crate_iri("serde", "1.0.197"),
        "http://example.org/rust/crate/serde/1.0.197"
    );
}

#[test]
fn crate_iri_with_hyphen() {
    let m = minter();
    assert_eq!(
        m.crate_iri("my-crate", "0.1.0"),
        "http://example.org/rust/crate/my-crate/0.1.0"
    );
}

// --- Module IRI ---

#[test]
fn module_iri_simple() {
    let m = minter();
    assert_eq!(
        m.module_iri("serde", "1.0.0", "de"),
        "http://example.org/rust/module/serde/1.0.0/de"
    );
}

#[test]
fn module_iri_nested_path() {
    let m = minter();
    // Module paths use :: which gets percent-encoded
    let iri = m.module_iri("tokio", "1.37.0", "io::util::read_buf");
    assert!(iri.contains("io%3A%3Autil%3A%3Aread_buf"));
    assert_eq!(
        iri,
        "http://example.org/rust/module/tokio/1.37.0/io%3A%3Autil%3A%3Aread_buf"
    );
}

#[test]
fn module_iri_deeply_nested() {
    let m = minter();
    let iri = m.module_iri("std", "1.78.0", "collections::hash_map::entry");
    assert_eq!(
        iri,
        "http://example.org/rust/module/std/1.78.0/collections%3A%3Ahash_map%3A%3Aentry"
    );
}

// --- Type IRI ---

#[test]
fn type_iri_basic() {
    let m = minter();
    assert_eq!(
        m.type_iri("serde", "1.0.0", "Deserializer"),
        "http://example.org/rust/type/serde/1.0.0/Deserializer"
    );
}

#[test]
fn type_iri_with_generics() {
    let m = minter();
    // Generics contain < and > which must be percent-encoded
    let iri = m.type_iri("std", "1.78.0", "HashMap<K, V>");
    assert!(iri.contains("HashMap%3CK%2C%20V%3E"));
}

#[test]
fn type_iri_special_characters() {
    let m = minter();
    // Test angle brackets, spaces, colons
    let iri = m.type_iri("my_crate", "0.1.0", "Foo<Bar<Baz>>");
    assert!(iri.contains("Foo%3CBar%3CBaz%3E%3E"));
    assert!(!iri.contains('<'));
    assert!(!iri.contains('>'));
}

// --- Member IRI ---

#[test]
fn member_iri_without_signature() {
    let m = minter();
    let type_iri = m.type_iri("serde", "1.0.0", "Deserializer");
    let member = m.member_iri(&type_iri, "deserialize", "");
    assert_eq!(
        member,
        "http://example.org/rust/type/serde/1.0.0/Deserializer/member/deserialize"
    );
}

#[test]
fn member_iri_with_signature() {
    let m = minter();
    let type_iri = m.type_iri("mycrate", "0.1.0", "MyStruct");
    let member = m.member_iri(&type_iri, "process", "&self, input: &str");
    assert!(member.contains("/member/process("));
    assert!(member.contains("%26self"));
}

// --- Parameter IRI ---

#[test]
fn parameter_iri_ordinals() {
    let m = minter();
    let type_iri = m.type_iri("mycrate", "0.1.0", "MyStruct");
    let method_iri = m.member_iri(&type_iri, "run", "");
    assert_eq!(
        m.parameter_iri(&method_iri, 0),
        format!("{method_iri}/param/0")
    );
    assert_eq!(
        m.parameter_iri(&method_iri, 3),
        format!("{method_iri}/param/3")
    );
}

// --- Type parameter IRI ---

#[test]
fn type_parameter_iri() {
    let m = minter();
    let type_iri = m.type_iri("mycrate", "0.1.0", "Container");
    assert_eq!(
        m.type_parameter_iri(&type_iri, 0),
        format!("{type_iri}/typeparam/0")
    );
    assert_eq!(
        m.type_parameter_iri(&type_iri, 2),
        format!("{type_iri}/typeparam/2")
    );
}

// --- Variant IRI ---

#[test]
fn variant_iri_simple() {
    let m = minter();
    let enum_iri = m.type_iri("std", "1.78.0", "Option");
    let variant = m.variant_iri(&enum_iri, "Some");
    assert_eq!(
        variant,
        "http://example.org/rust/type/std/1.78.0/Option/variant/Some"
    );
}

#[test]
fn variant_iri_with_special_chars() {
    let m = minter();
    let enum_iri = m.type_iri("mycrate", "0.1.0", "MyEnum");
    // Variant names are typically identifiers, but test encoding anyway
    let variant = m.variant_iri(&enum_iri, "Variant(i32)");
    assert!(variant.contains("Variant%28i32%29"));
}

// --- Impl IRI ---

#[test]
fn impl_iri_basic() {
    let m = minter();
    let iri = m.impl_iri("mycrate", "0.1.0", "impl-Display-for-MyStruct");
    assert_eq!(
        iri,
        "http://example.org/rust/impl/mycrate/0.1.0/impl-Display-for-MyStruct"
    );
}

// --- Lifetime IRI ---

#[test]
fn lifetime_iri_strips_tick() {
    let m = minter();
    let type_iri = m.type_iri("mycrate", "0.1.0", "Borrowed");
    let lt = m.lifetime_iri(&type_iri, "'a");
    assert!(lt.ends_with("/lifetime/a"));
    assert!(!lt.contains('\''));
}

#[test]
fn lifetime_iri_without_tick() {
    let m = minter();
    let type_iri = m.type_iri("mycrate", "0.1.0", "Borrowed");
    let lt = m.lifetime_iri(&type_iri, "static");
    assert!(lt.ends_with("/lifetime/static"));
}

// --- Primitive type IRI ---

#[test]
fn primitive_type_iris() {
    let m = minter();
    assert_eq!(
        m.primitive_type_iri("i32"),
        "http://example.org/rust/type/_primitive_/i32"
    );
    assert_eq!(
        m.primitive_type_iri("bool"),
        "http://example.org/rust/type/_primitive_/bool"
    );
    assert_eq!(
        m.primitive_type_iri("str"),
        "http://example.org/rust/type/_primitive_/str"
    );
    assert_eq!(
        m.primitive_type_iri("f64"),
        "http://example.org/rust/type/_primitive_/f64"
    );
}

// --- Tuple type IRI ---

#[test]
fn tuple_type_iri() {
    let m = minter();
    assert_eq!(
        m.tuple_type_iri(0),
        "http://example.org/rust/type/_tuple_/0"
    );
    assert_eq!(
        m.tuple_type_iri(2),
        "http://example.org/rust/type/_tuple_/2"
    );
    assert_eq!(
        m.tuple_type_iri(12),
        "http://example.org/rust/type/_tuple_/12"
    );
}

// --- Slice and array type IRIs ---

#[test]
fn slice_type_iri() {
    let m = minter();
    assert_eq!(
        m.slice_type_iri("u8"),
        "http://example.org/rust/type/_slice_/u8"
    );
}

#[test]
fn array_type_iri() {
    let m = minter();
    assert_eq!(
        m.array_type_iri("u8", "32"),
        "http://example.org/rust/type/_array_/u8/32"
    );
}

// --- Reference and raw pointer IRIs ---

#[test]
fn ref_type_iris() {
    let m = minter();
    assert_eq!(
        m.ref_type_iri("String", false),
        "http://example.org/rust/type/_ref_/String"
    );
    assert_eq!(
        m.ref_type_iri("String", true),
        "http://example.org/rust/type/_mut_/String"
    );
}

#[test]
fn raw_pointer_type_iris() {
    let m = minter();
    assert_eq!(
        m.raw_pointer_type_iri("u8", false),
        "http://example.org/rust/type/_ptr_const_/u8"
    );
    assert_eq!(
        m.raw_pointer_type_iri("u8", true),
        "http://example.org/rust/type/_ptr_mut_/u8"
    );
}

// --- Percent-encoding verification ---

#[test]
fn percent_encoding_special_characters() {
    let m = minter();
    // Space
    let iri = m.type_iri("c", "1.0.0", "has space");
    assert!(iri.contains("has%20space"));
    // Angle brackets
    let iri = m.type_iri("c", "1.0.0", "Vec<u8>");
    assert!(iri.contains("Vec%3Cu8%3E"));
    // Colons
    let iri = m.type_iri("c", "1.0.0", "std::io::Error");
    assert!(iri.contains("std%3A%3Aio%3A%3AError"));
    // Ampersand
    let iri = m.type_iri("c", "1.0.0", "&str");
    assert!(iri.contains("%26str"));
}

// --- Edge cases ---

#[test]
fn empty_string_inputs() {
    let m = minter();
    let iri = m.crate_iri("", "");
    assert_eq!(iri, "http://example.org/rust/crate//");
    let iri = m.module_iri("", "", "");
    assert_eq!(iri, "http://example.org/rust/module///");
}

#[test]
fn base_uri_trailing_slash_stripped() {
    let m = IriMinter::new("http://example.org/rust/");
    assert_eq!(m.base_uri(), "http://example.org/rust");
    assert_eq!(
        m.crate_iri("serde", "1.0.0"),
        "http://example.org/rust/crate/serde/1.0.0"
    );
}

#[test]
fn base_uri_multiple_trailing_slashes() {
    let m = IriMinter::new("http://example.org/rust///");
    assert_eq!(m.base_uri(), "http://example.org/rust");
}
