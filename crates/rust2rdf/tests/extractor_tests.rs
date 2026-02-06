//! Integration tests for CrateExtractor against the fixture crate JSON.

use rust2rdf::emitter::ntriples::NTriplesEmitter;
use rust2rdf::emitter::TriplesEmitter;
use rust2rdf::extraction::extractor::{CrateExtractor, ExtractionOptions};
use rust2rdf::extraction::rustdoc_loader;
use rust2rdf::extraction::rustdoc_model::Crate;
use std::path::Path;

// ---------------------------------------------------------------------------
// Helper: load fixture and extract to NTriples string
// ---------------------------------------------------------------------------

fn fixture_path() -> std::path::PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/fixture_crate.json")
}

fn load_fixture() -> Crate {
    rustdoc_loader::load_json(&fixture_path()).expect("Failed to load fixture JSON")
}

fn extract_to_ntriples(opts: ExtractionOptions) -> String {
    let krate = load_fixture();
    let mut buf = Vec::new();
    {
        let mut emitter = NTriplesEmitter::new(&mut buf);
        let mut extractor = CrateExtractor::new(&mut emitter, &krate, opts);
        extractor.extract();
        emitter.flush().unwrap();
    }
    String::from_utf8(buf).expect("Invalid UTF-8 in NTriples output")
}

fn extract_default() -> String {
    extract_to_ntriples(ExtractionOptions::default())
}

/// Check that the output contains a triple `<subject> <predicate> <object> .`
fn has_iri_triple(output: &str, subject: &str, predicate: &str, object: &str) -> bool {
    let expected = format!("<{subject}> <{predicate}> <{object}> .");
    output.lines().any(|line| line.trim() == expected)
}

/// Check that the output contains a triple `<subject> <predicate> "value" .`
fn has_literal_triple(output: &str, subject: &str, predicate: &str, value: &str) -> bool {
    let expected = format!("<{subject}> <{predicate}> \"{value}\" .");
    output.lines().any(|line| line.trim() == expected)
}

/// Check that the output contains a triple with a boolean value
fn has_bool_triple(output: &str, subject: &str, predicate: &str, value: bool) -> bool {
    let val = if value { "true" } else { "false" };
    let expected = format!(
        "<{subject}> <{predicate}> \"{val}\"^^<http://www.w3.org/2001/XMLSchema#boolean> ."
    );
    output.lines().any(|line| line.trim() == expected)
}

/// Check that the output contains a triple with an integer value
fn has_int_triple(output: &str, subject: &str, predicate: &str, value: i64) -> bool {
    let expected = format!(
        "<{subject}> <{predicate}> \"{value}\"^^<http://www.w3.org/2001/XMLSchema#integer> ."
    );
    output.lines().any(|line| line.trim() == expected)
}

// Ontology IRIs
const RDF_TYPE: &str = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type";
const TG_NS: &str = "http://typegraph.example/ontology/";
const RT_NS: &str = "http://rust.example/ontology/";

fn tg(local: &str) -> String {
    format!("{TG_NS}{local}")
}
fn rt(local: &str) -> String {
    format!("{RT_NS}{local}")
}

// Base for test IRIs
const BASE: &str = "http://rust.example";

fn crate_iri() -> String {
    format!("{BASE}/crate/fixture_crate/0.1.0")
}

fn module_iri(path: &str) -> String {
    format!("{BASE}/module/fixture_crate/0.1.0/{path}")
}

fn type_iri(path: &str) -> String {
    format!("{BASE}/type/fixture_crate/0.1.0/{path}")
}

// ===========================================================================
// Tests: Crate node
// ===========================================================================

#[test]
fn crate_node_has_rdf_types() {
    let out = extract_default();
    assert!(
        has_iri_triple(&out, &crate_iri(), RDF_TYPE, &rt("Crate")),
        "Crate should be rt:Crate"
    );
    assert!(
        has_iri_triple(&out, &crate_iri(), RDF_TYPE, &tg("Assembly")),
        "Crate should also be tg:Assembly"
    );
}

#[test]
fn crate_node_has_name_and_version() {
    let out = extract_default();
    assert!(has_literal_triple(
        &out,
        &crate_iri(),
        &tg("name"),
        "fixture_crate"
    ));
    assert!(has_literal_triple(
        &out,
        &crate_iri(),
        &tg("version"),
        "0.1.0"
    ));
    assert!(has_literal_triple(
        &out,
        &crate_iri(),
        &tg("language"),
        "rust"
    ));
}

#[test]
fn crate_has_external_dependencies() {
    let out = extract_default();
    // The fixture has external crates like "std", "core", "alloc"
    // They are emitted with their names
    assert!(
        out.contains(&rt("dependsOn")),
        "Should emit rt:dependsOn for external crates"
    );
    // Check for std dependency
    let std_iri = format!("{BASE}/crate/std/0.0.0");
    assert!(
        has_iri_triple(&out, &crate_iri(), &rt("dependsOn"), &std_iri),
        "Should depend on std"
    );
}

// ===========================================================================
// Tests: Module hierarchy
// ===========================================================================

#[test]
fn nested_module_emitted() {
    let out = extract_default();
    let nested = module_iri("fixture_crate%3A%3Anested");
    assert!(
        has_iri_triple(&out, &nested, RDF_TYPE, &rt("Module")),
        "nested module should be rt:Module"
    );
    assert!(
        has_iri_triple(&out, &nested, RDF_TYPE, &tg("Namespace")),
        "nested module should also be tg:Namespace"
    );
    assert!(has_literal_triple(&out, &nested, &tg("name"), "nested"));
}

#[test]
fn deeply_nested_module_emitted() {
    let out = extract_default();
    let deep = module_iri("fixture_crate%3A%3Anested%3A%3Adeep");
    assert!(
        has_iri_triple(&out, &deep, RDF_TYPE, &rt("Module")),
        "deeply nested module should be rt:Module"
    );
    assert!(has_literal_triple(&out, &deep, &tg("name"), "deep"));
}

#[test]
fn module_has_parent_namespace() {
    let out = extract_default();
    let deep = module_iri("fixture_crate%3A%3Anested%3A%3Adeep");
    let nested = module_iri("fixture_crate%3A%3Anested");
    assert!(
        has_iri_triple(&out, &deep, &tg("parentNamespace"), &nested),
        "deep module should have nested as parent namespace"
    );
}

#[test]
fn module_defined_in_assembly() {
    let out = extract_default();
    let nested = module_iri("fixture_crate%3A%3Anested");
    assert!(
        has_iri_triple(&out, &nested, &tg("definedInAssembly"), &crate_iri()),
        "Module should be defined in the crate assembly"
    );
}

// ===========================================================================
// Tests: Struct extraction
// ===========================================================================

#[test]
fn struct_basic_properties() {
    let out = extract_default();
    let my_struct = type_iri("fixture_crate%3A%3AMyStruct");
    assert!(has_iri_triple(&out, &my_struct, RDF_TYPE, &tg("Struct")));
    assert!(has_literal_triple(&out, &my_struct, &tg("name"), "MyStruct"));
    assert!(has_literal_triple(
        &out,
        &my_struct,
        &tg("fullName"),
        "fixture_crate::MyStruct"
    ));
    assert!(has_literal_triple(
        &out,
        &my_struct,
        &tg("accessibility"),
        "Public"
    ));
}

#[test]
fn struct_defined_in_assembly_and_namespace() {
    let out = extract_default();
    let my_struct = type_iri("fixture_crate%3A%3AMyStruct");
    let root_mod = module_iri("fixture_crate");
    assert!(has_iri_triple(
        &out,
        &my_struct,
        &tg("definedInAssembly"),
        &crate_iri()
    ));
    assert!(has_iri_triple(
        &out,
        &my_struct,
        &tg("inNamespace"),
        &root_mod
    ));
}

#[test]
fn struct_is_generic() {
    let out = extract_default();
    let my_struct = type_iri("fixture_crate%3A%3AMyStruct");
    assert!(
        has_bool_triple(&out, &my_struct, &tg("isGeneric"), true),
        "MyStruct<T> should be marked generic"
    );
}

#[test]
fn struct_fields_emitted() {
    let out = extract_default();
    let my_struct = type_iri("fixture_crate%3A%3AMyStruct");

    // Check field member
    let field_iri = format!("{my_struct}/member/field");
    assert!(
        has_iri_triple(&out, &field_iri, RDF_TYPE, &tg("Field")),
        "field should be tg:Field"
    );
    assert!(has_literal_triple(&out, &field_iri, &tg("name"), "field"));
    assert!(has_iri_triple(
        &out,
        &my_struct,
        &tg("hasMember"),
        &field_iri
    ));

    // Check count field
    let count_iri = format!("{my_struct}/member/count");
    assert!(has_iri_triple(&out, &count_iri, RDF_TYPE, &tg("Field")));
    assert!(has_literal_triple(&out, &count_iri, &tg("name"), "count"));
    // count: usize should have a field type pointing to primitive usize
    let usize_iri = format!("{BASE}/type/_primitive_/usize");
    assert!(
        has_iri_triple(&out, &count_iri, &tg("fieldType"), &usize_iri),
        "count field should have usize type"
    );
}

#[test]
fn struct_field_visibility() {
    let out = extract_default();
    let my_struct = type_iri("fixture_crate%3A%3AMyStruct");
    let field_iri = format!("{my_struct}/member/field");
    assert!(has_literal_triple(
        &out,
        &field_iri,
        &tg("accessibility"),
        "Public"
    ));
}

#[test]
fn unit_struct_no_fields() {
    let out = extract_default();
    // Deep is a unit struct in nested::deep
    let deep_struct = type_iri("fixture_crate%3A%3Anested%3A%3Adeep%3A%3ADeep");
    assert!(has_iri_triple(
        &out,
        &deep_struct,
        RDF_TYPE,
        &tg("Struct")
    ));
    assert!(has_literal_triple(
        &out,
        &deep_struct,
        &tg("name"),
        "Deep"
    ));
}

// ===========================================================================
// Tests: Enum extraction
// ===========================================================================

#[test]
fn enum_basic_properties() {
    let out = extract_default();
    let my_enum = type_iri("fixture_crate%3A%3AMyEnum");
    assert!(has_iri_triple(&out, &my_enum, RDF_TYPE, &tg("Enum")));
    assert!(has_literal_triple(&out, &my_enum, &tg("name"), "MyEnum"));
    assert!(has_literal_triple(
        &out,
        &my_enum,
        &tg("accessibility"),
        "Public"
    ));
}

#[test]
fn enum_variants_emitted() {
    let out = extract_default();
    let my_enum = type_iri("fixture_crate%3A%3AMyEnum");

    // Plain variant
    let plain = format!("{my_enum}/variant/Plain");
    assert!(has_iri_triple(
        &out,
        &plain,
        RDF_TYPE,
        &rt("EnumVariant")
    ));
    assert!(has_literal_triple(&out, &plain, &tg("name"), "Plain"));
    assert!(has_iri_triple(
        &out,
        &my_enum,
        &rt("hasVariant"),
        &plain
    ));
    assert!(has_literal_triple(
        &out,
        &plain,
        &rt("variantKind"),
        "plain"
    ));

    // Tuple variant
    let tuple = format!("{my_enum}/variant/Tuple");
    assert!(has_iri_triple(
        &out,
        &tuple,
        RDF_TYPE,
        &rt("EnumVariant")
    ));
    assert!(has_literal_triple(
        &out,
        &tuple,
        &rt("variantKind"),
        "tuple"
    ));

    // Struct variant
    let struct_v = format!("{my_enum}/variant/Struct");
    assert!(has_iri_triple(
        &out,
        &struct_v,
        RDF_TYPE,
        &rt("EnumVariant")
    ));
    assert!(has_literal_triple(
        &out,
        &struct_v,
        &rt("variantKind"),
        "struct"
    ));
}

#[test]
fn enum_variant_fields() {
    let out = extract_default();
    let my_enum = type_iri("fixture_crate%3A%3AMyEnum");

    // Struct variant { x: f64, y: f64 }
    let struct_v = format!("{my_enum}/variant/Struct");
    let x_field = format!("{struct_v}/member/x");
    let y_field = format!("{struct_v}/member/y");

    assert!(
        has_iri_triple(&out, &struct_v, &rt("variantField"), &x_field),
        "Struct variant should have x field"
    );
    assert!(
        has_iri_triple(&out, &struct_v, &rt("variantField"), &y_field),
        "Struct variant should have y field"
    );
    assert!(has_iri_triple(&out, &x_field, RDF_TYPE, &tg("Field")));

    // x should have f64 type
    let f64_iri = format!("{BASE}/type/_primitive_/f64");
    assert!(has_iri_triple(&out, &x_field, &tg("fieldType"), &f64_iri));
}

#[test]
fn enum_tuple_variant_fields() {
    let out = extract_default();
    let my_enum = type_iri("fixture_crate%3A%3AMyEnum");
    let tuple = format!("{my_enum}/variant/Tuple");

    // Tuple(i32, String) - fields named "0" and "1"
    let field_0 = format!("{tuple}/member/0");
    let field_1 = format!("{tuple}/member/1");

    assert!(
        has_iri_triple(&out, &tuple, &rt("variantField"), &field_0),
        "Tuple variant should have field 0"
    );
    assert!(
        has_iri_triple(&out, &tuple, &rt("variantField"), &field_1),
        "Tuple variant should have field 1"
    );

    // field 0 should be i32
    let i32_iri = format!("{BASE}/type/_primitive_/i32");
    assert!(has_iri_triple(
        &out,
        &field_0,
        &tg("fieldType"),
        &i32_iri
    ));
}

// ===========================================================================
// Tests: Trait extraction
// ===========================================================================

#[test]
fn trait_basic_properties() {
    let out = extract_default();
    let my_trait = type_iri("fixture_crate%3A%3AMyTrait");
    assert!(has_iri_triple(
        &out,
        &my_trait,
        RDF_TYPE,
        &tg("Interface")
    ));
    assert!(has_iri_triple(&out, &my_trait, RDF_TYPE, &rt("Trait")));
    assert!(has_literal_triple(
        &out,
        &my_trait,
        &tg("name"),
        "MyTrait"
    ));
    assert!(has_literal_triple(
        &out,
        &my_trait,
        &tg("accessibility"),
        "Public"
    ));
}

#[test]
fn trait_supertraits() {
    let out = extract_default();
    let my_trait = type_iri("fixture_crate%3A%3AMyTrait");

    // MyTrait: Send + Sync
    // These are in paths as core::marker::Send and core::marker::Sync
    let send_iri = type_iri("core%3A%3Amarker%3A%3ASend");
    let sync_iri = type_iri("core%3A%3Amarker%3A%3ASync");

    assert!(
        has_iri_triple(&out, &my_trait, &rt("superTrait"), &send_iri),
        "MyTrait should have Send as supertrait"
    );
    assert!(
        has_iri_triple(&out, &my_trait, &rt("superTrait"), &sync_iri),
        "MyTrait should have Sync as supertrait"
    );
}

#[test]
fn trait_methods_emitted() {
    let out = extract_default();
    let my_trait = type_iri("fixture_crate%3A%3AMyTrait");

    // required method
    let required = format!("{my_trait}/member/required");
    assert!(has_iri_triple(&out, &required, RDF_TYPE, &tg("Method")));
    assert!(has_literal_triple(
        &out,
        &required,
        &tg("name"),
        "required"
    ));
    assert!(has_iri_triple(
        &out,
        &my_trait,
        &tg("hasMember"),
        &required
    ));

    // provided method
    let provided = format!("{my_trait}/member/provided");
    assert!(has_iri_triple(&out, &provided, RDF_TYPE, &tg("Method")));
    assert!(has_literal_triple(
        &out,
        &provided,
        &tg("name"),
        "provided"
    ));
}

#[test]
fn trait_required_method_is_abstract() {
    let out = extract_default();
    let my_trait = type_iri("fixture_crate%3A%3AMyTrait");
    let required = format!("{my_trait}/member/required");
    // required method has has_body=false -> isAbstract=true
    assert!(
        has_bool_triple(&out, &required, &tg("isAbstract"), true),
        "Required method should be abstract"
    );
}

#[test]
fn trait_with_lifetime_parameter() {
    let out = extract_default();
    let with_lt = type_iri("fixture_crate%3A%3AWithLifetime");
    assert!(has_iri_triple(
        &out,
        &with_lt,
        RDF_TYPE,
        &tg("Interface")
    ));

    // Lifetime parameter 'a
    let lt_iri = format!("{with_lt}/lifetime/a");
    assert!(
        has_iri_triple(&out, &lt_iri, RDF_TYPE, &rt("Lifetime")),
        "WithLifetime should have a lifetime parameter"
    );
    assert!(has_iri_triple(
        &out,
        &with_lt,
        &rt("hasLifetime"),
        &lt_iri
    ));
}

// ===========================================================================
// Tests: Function extraction
// ===========================================================================

#[test]
fn simple_function_parameters() {
    let out = extract_default();
    let root_mod = module_iri("fixture_crate");
    let simple_add = format!("{root_mod}/member/simple_add");

    assert!(has_iri_triple(
        &out,
        &simple_add,
        RDF_TYPE,
        &tg("Method")
    ));
    assert!(has_literal_triple(
        &out,
        &simple_add,
        &tg("name"),
        "simple_add"
    ));

    // Parameters: a: i32, b: i32
    let param_a = format!("{simple_add}/param/0");
    let param_b = format!("{simple_add}/param/1");

    assert!(has_iri_triple(
        &out,
        &param_a,
        RDF_TYPE,
        &tg("Parameter")
    ));
    assert!(has_literal_triple(&out, &param_a, &tg("name"), "a"));
    assert!(has_int_triple(&out, &param_a, &tg("ordinal"), 0));

    assert!(has_iri_triple(
        &out,
        &param_b,
        RDF_TYPE,
        &tg("Parameter")
    ));
    assert!(has_literal_triple(&out, &param_b, &tg("name"), "b"));
    assert!(has_int_triple(&out, &param_b, &tg("ordinal"), 1));

    // Parameter types
    let i32_iri = format!("{BASE}/type/_primitive_/i32");
    assert!(has_iri_triple(
        &out,
        &param_a,
        &tg("parameterType"),
        &i32_iri
    ));
    assert!(has_iri_triple(
        &out,
        &param_b,
        &tg("parameterType"),
        &i32_iri
    ));
}

#[test]
fn function_return_type() {
    let out = extract_default();
    let root_mod = module_iri("fixture_crate");
    let simple_add = format!("{root_mod}/member/simple_add");

    let i32_iri = format!("{BASE}/type/_primitive_/i32");
    assert!(
        has_iri_triple(&out, &simple_add, &tg("returnType"), &i32_iri),
        "simple_add should return i32"
    );
}

#[test]
fn function_parameter_of_relationship() {
    let out = extract_default();
    let root_mod = module_iri("fixture_crate");
    let simple_add = format!("{root_mod}/member/simple_add");
    let param_a = format!("{simple_add}/param/0");

    assert!(has_iri_triple(
        &out,
        &param_a,
        &tg("parameterOf"),
        &simple_add
    ));
    assert!(has_iri_triple(
        &out,
        &simple_add,
        &tg("hasParameter"),
        &param_a
    ));
}

#[test]
fn unsafe_function_marked() {
    let out = extract_default();
    let root_mod = module_iri("fixture_crate");
    let unsafe_fn = format!("{root_mod}/member/unsafe_fn");

    assert!(has_iri_triple(
        &out,
        &unsafe_fn,
        RDF_TYPE,
        &tg("Method")
    ));
    assert!(
        has_bool_triple(&out, &unsafe_fn, &rt("isUnsafe"), true),
        "unsafe_fn should be marked unsafe"
    );
}

// ===========================================================================
// Tests: Result error type extraction
// ===========================================================================

#[test]
fn result_error_type_extracted() {
    let out = extract_default();
    let root_mod = module_iri("fixture_crate");
    let fallible = format!("{root_mod}/member/fallible");

    assert!(has_iri_triple(
        &out,
        &fallible,
        RDF_TYPE,
        &tg("Method")
    ));

    // The error type of Result<String, std::io::Error> is std::io::Error
    // In paths, id=102 maps to std::io::error::Error
    let err_iri = type_iri("std%3A%3Aio%3A%3Aerror%3A%3AError");
    assert!(
        has_iri_triple(&out, &fallible, &rt("errorType"), &err_iri),
        "fallible should have errorType pointing to std::io::Error"
    );
}

#[test]
fn result_return_type_also_emitted() {
    let out = extract_default();
    let root_mod = module_iri("fixture_crate");
    let fallible = format!("{root_mod}/member/fallible");

    // Return type should be Result (via its path)
    // Result is core::result::Result in paths
    let result_iri = type_iri("core%3A%3Aresult%3A%3AResult");
    assert!(
        has_iri_triple(&out, &fallible, &tg("returnType"), &result_iri),
        "fallible should have returnType of Result"
    );
}

// ===========================================================================
// Tests: Derive macro extraction
// ===========================================================================

#[test]
fn derive_macros_extracted() {
    let out = extract_default();
    let derived = type_iri("fixture_crate%3A%3ADerived");

    assert!(has_iri_triple(&out, &derived, RDF_TYPE, &tg("Struct")));

    // Derived has #[derive(Debug, Clone, PartialEq)]
    assert!(
        has_literal_triple(&out, &derived, &rt("derives"), "Debug"),
        "Derived should have Debug derive"
    );
    assert!(
        has_literal_triple(&out, &derived, &rt("derives"), "Clone"),
        "Derived should have Clone derive"
    );
    assert!(
        has_literal_triple(&out, &derived, &rt("derives"), "PartialEq"),
        "Derived should have PartialEq derive"
    );
}

#[test]
fn derive_extraction_can_be_disabled() {
    let out = extract_to_ntriples(ExtractionOptions {
        extract_derives: false,
        ..ExtractionOptions::default()
    });
    let derived = type_iri("fixture_crate%3A%3ADerived");
    assert!(has_iri_triple(&out, &derived, RDF_TYPE, &tg("Struct")));
    // Should NOT have derive triples
    assert!(
        !has_literal_triple(&out, &derived, &rt("derives"), "Debug"),
        "Derives should not be extracted when disabled"
    );
}

// ===========================================================================
// Tests: Visibility mapping
// ===========================================================================

#[test]
fn public_visibility() {
    let out = extract_default();
    let my_struct = type_iri("fixture_crate%3A%3AMyStruct");
    assert!(has_literal_triple(
        &out,
        &my_struct,
        &tg("accessibility"),
        "Public"
    ));
}

#[test]
fn default_visibility_is_private() {
    let out = extract_default();
    let my_trait = type_iri("fixture_crate%3A%3AMyTrait");
    // Trait methods with default visibility should be "Private"
    let provided = format!("{my_trait}/member/provided");
    assert!(has_literal_triple(
        &out,
        &provided,
        &tg("accessibility"),
        "Private"
    ));
}

// ===========================================================================
// Tests: Constant and Static extraction
// ===========================================================================

#[test]
fn constant_extraction() {
    let out = extract_default();
    let root_mod = module_iri("fixture_crate");
    let my_const = format!("{root_mod}/member/MY_CONST");

    assert!(has_iri_triple(&out, &my_const, RDF_TYPE, &tg("Field")));
    assert!(has_iri_triple(
        &out,
        &my_const,
        RDF_TYPE,
        &rt("Constant")
    ));
    assert!(has_literal_triple(
        &out,
        &my_const,
        &tg("name"),
        "MY_CONST"
    ));
    assert!(has_bool_triple(&out, &my_const, &tg("isConst"), true));

    // Type should be i32
    let i32_iri = format!("{BASE}/type/_primitive_/i32");
    assert!(has_iri_triple(
        &out,
        &my_const,
        &tg("fieldType"),
        &i32_iri
    ));
}

#[test]
fn static_extraction() {
    let out = extract_default();
    let root_mod = module_iri("fixture_crate");
    let my_static = format!("{root_mod}/member/MY_STATIC");

    assert!(has_iri_triple(
        &out,
        &my_static,
        RDF_TYPE,
        &rt("Static")
    ));
    assert!(has_literal_triple(
        &out,
        &my_static,
        &tg("name"),
        "MY_STATIC"
    ));

    // Type should be &str (borrowed ref to str)
    let ref_str_iri = format!("{BASE}/type/_ref_/str");
    assert!(
        has_iri_triple(&out, &my_static, &tg("fieldType"), &ref_str_iri),
        "MY_STATIC should have type &str"
    );
}

// ===========================================================================
// Tests: TypeAlias extraction
// ===========================================================================

#[test]
fn type_alias_extraction() {
    let out = extract_default();
    let string_vec = type_iri("fixture_crate%3A%3AStringVec");

    assert!(has_iri_triple(
        &out,
        &string_vec,
        RDF_TYPE,
        &rt("TypeAlias")
    ));
    assert!(has_literal_triple(
        &out,
        &string_vec,
        &tg("name"),
        "StringVec"
    ));
    assert!(has_literal_triple(
        &out,
        &string_vec,
        &tg("accessibility"),
        "Public"
    ));

    // Target type: Vec<String> => resolves to alloc::vec::Vec in paths
    let vec_iri = type_iri("alloc%3A%3Avec%3A%3AVec");
    assert!(
        has_iri_triple(&out, &string_vec, &tg("relatedTo"), &vec_iri),
        "StringVec should relate to Vec"
    );
}

// ===========================================================================
// Tests: Union extraction
// ===========================================================================

#[test]
fn union_extraction() {
    let out = extract_default();
    let my_union = type_iri("fixture_crate%3A%3AMyUnion");

    assert!(has_iri_triple(&out, &my_union, RDF_TYPE, &rt("Union")));
    assert!(has_literal_triple(
        &out,
        &my_union,
        &tg("name"),
        "MyUnion"
    ));
    assert!(has_literal_triple(
        &out,
        &my_union,
        &tg("accessibility"),
        "Public"
    ));
}

#[test]
fn union_fields() {
    let out = extract_default();
    let my_union = type_iri("fixture_crate%3A%3AMyUnion");

    let int_val = format!("{my_union}/member/int_val");
    let float_val = format!("{my_union}/member/float_val");

    assert!(has_iri_triple(&out, &int_val, RDF_TYPE, &tg("Field")));
    assert!(has_iri_triple(&out, &float_val, RDF_TYPE, &tg("Field")));

    let i32_iri = format!("{BASE}/type/_primitive_/i32");
    let f32_iri = format!("{BASE}/type/_primitive_/f32");
    assert!(has_iri_triple(
        &out,
        &int_val,
        &tg("fieldType"),
        &i32_iri
    ));
    assert!(has_iri_triple(
        &out,
        &float_val,
        &tg("fieldType"),
        &f32_iri
    ));
}

// ===========================================================================
// Tests: Impl block processing
// ===========================================================================

#[test]
fn trait_impl_emitted() {
    let out = extract_default();
    let my_struct = type_iri("fixture_crate%3A%3AMyStruct");
    let my_trait = type_iri("fixture_crate%3A%3AMyTrait");

    // MyStruct implements MyTrait
    // The paths entry for MyTrait (id=77) maps to fixture_crate::MyTrait
    // Since MyTrait is in our index and paths, the path lookup should give us
    // the correct IRI.
    // Check that the paths entry for 77 exists
    assert!(
        has_iri_triple(&out, &my_struct, &tg("implements"), &my_trait),
        "MyStruct should implement MyTrait"
    );
}

#[test]
fn trait_impl_node_properties() {
    let out = extract_default();
    // The trait impl for MyTrait on MyStruct has id "76"
    let impl_iri = format!("{BASE}/impl/fixture_crate/0.1.0/76");
    assert!(
        has_iri_triple(&out, &impl_iri, RDF_TYPE, &rt("TraitImpl")),
        "Impl 76 should be a TraitImpl"
    );

    let my_struct = type_iri("fixture_crate%3A%3AMyStruct");
    assert!(has_iri_triple(
        &out,
        &impl_iri,
        &rt("implFor"),
        &my_struct
    ));
}

// ===========================================================================
// Tests: Generics extraction
// ===========================================================================

#[test]
fn type_parameter_extracted() {
    let out = extract_default();
    let my_struct = type_iri("fixture_crate%3A%3AMyStruct");

    // MyStruct has type parameter T at ordinal 0
    let tp_iri = format!("{my_struct}/typeparam/0");
    assert!(has_iri_triple(
        &out,
        &tp_iri,
        RDF_TYPE,
        &tg("TypeParameter")
    ));
    assert!(has_literal_triple(&out, &tp_iri, &tg("name"), "T"));
    assert!(has_int_triple(&out, &tp_iri, &tg("ordinal"), 0));
    assert!(has_iri_triple(
        &out,
        &my_struct,
        &tg("hasTypeParameter"),
        &tp_iri
    ));
    assert!(has_iri_triple(
        &out,
        &tp_iri,
        &tg("typeParameterOf"),
        &my_struct
    ));
}

#[test]
fn type_parameter_trait_bound() {
    let out = extract_default();
    let my_struct = type_iri("fixture_crate%3A%3AMyStruct");
    let tp_iri = format!("{my_struct}/typeparam/0");

    // T: Clone -- Clone is in paths as core::clone::Clone
    let clone_iri = type_iri("core%3A%3Aclone%3A%3AClone");
    assert!(
        has_iri_triple(&out, &tp_iri, &rt("traitBound"), &clone_iri),
        "T should have Clone as trait bound"
    );
}

// ===========================================================================
// Tests: Nested struct (inner module types)
// ===========================================================================

#[test]
fn nested_struct_in_module() {
    let out = extract_default();
    let inner = type_iri("fixture_crate%3A%3Anested%3A%3AInner");
    assert!(has_iri_triple(&out, &inner, RDF_TYPE, &tg("Struct")));
    assert!(has_literal_triple(&out, &inner, &tg("name"), "Inner"));

    // Should be in the nested module namespace
    let nested_mod = module_iri("fixture_crate%3A%3Anested");
    assert!(has_iri_triple(
        &out,
        &inner,
        &tg("inNamespace"),
        &nested_mod
    ));
}

// ===========================================================================
// Tests: Triple count and extraction options
// ===========================================================================

#[test]
fn extraction_produces_nonzero_triples() {
    let krate = load_fixture();
    let mut buf = Vec::new();
    let count;
    {
        let mut emitter = NTriplesEmitter::new(&mut buf);
        let mut extractor =
            CrateExtractor::new(&mut emitter, &krate, ExtractionOptions::default());
        extractor.extract();
        count = emitter.triple_count();
        emitter.flush().unwrap();
    }
    assert!(count > 100, "Should produce many triples, got {count}");
}

#[test]
fn impls_can_be_disabled() {
    let with = extract_to_ntriples(ExtractionOptions {
        include_impls: true,
        ..ExtractionOptions::default()
    });
    let without = extract_to_ntriples(ExtractionOptions {
        include_impls: false,
        ..ExtractionOptions::default()
    });

    // With impls enabled we should have more triples
    let with_count = with.lines().count();
    let without_count = without.lines().count();
    assert!(
        with_count > without_count,
        "Impls should produce more triples: with={with_count}, without={without_count}"
    );
}

#[test]
fn error_type_extraction_can_be_disabled() {
    let out = extract_to_ntriples(ExtractionOptions {
        extract_error_types: false,
        ..ExtractionOptions::default()
    });
    // Should not contain errorType triples
    assert!(
        !out.contains(&rt("errorType")),
        "errorType should not appear when disabled"
    );
}

#[test]
fn custom_base_uri() {
    let out = extract_to_ntriples(ExtractionOptions {
        base_uri: "http://custom.example".to_string(),
        ..ExtractionOptions::default()
    });
    assert!(
        out.contains("http://custom.example/crate/fixture_crate/0.1.0"),
        "Custom base URI should be used in output"
    );
}

// ===========================================================================
// Tests: member_of relationship
// ===========================================================================

#[test]
fn function_member_of_module() {
    let out = extract_default();
    let root_mod = module_iri("fixture_crate");
    let simple_add = format!("{root_mod}/member/simple_add");

    assert!(has_iri_triple(
        &out,
        &simple_add,
        &tg("memberOf"),
        &root_mod
    ));
    assert!(has_iri_triple(
        &out,
        &root_mod,
        &tg("hasMember"),
        &simple_add
    ));
}

#[test]
fn constant_member_of_module() {
    let out = extract_default();
    let root_mod = module_iri("fixture_crate");
    let my_const = format!("{root_mod}/member/MY_CONST");

    assert!(has_iri_triple(
        &out,
        &my_const,
        &tg("memberOf"),
        &root_mod
    ));
}

// ===========================================================================
// Tests: full_name for functions
// ===========================================================================

#[test]
fn function_has_full_name() {
    let out = extract_default();
    let root_mod = module_iri("fixture_crate");
    let simple_add = format!("{root_mod}/member/simple_add");

    assert!(has_literal_triple(
        &out,
        &simple_add,
        &tg("fullName"),
        "fixture_crate::simple_add"
    ));
}
