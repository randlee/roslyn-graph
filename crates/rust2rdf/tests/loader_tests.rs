use rust2rdf::extraction::rustdoc_loader;
use std::path::Path;

#[test]
fn load_fixture_json() {
    let fixture_path = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("tests/fixtures/fixture_crate.json");

    let krate = rustdoc_loader::load_json(&fixture_path)
        .expect("Failed to load fixture JSON");

    // Verify basic structure
    assert!(!krate.index.is_empty(), "Index should not be empty");
    assert!(krate.format_version > 0, "Format version should be set");
}

#[test]
fn fixture_has_expected_items() {
    let fixture_path = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("tests/fixtures/fixture_crate.json");

    let krate = rustdoc_loader::load_json(&fixture_path)
        .expect("Failed to load fixture JSON");

    // Check that expected items exist by name
    let names: Vec<String> = krate.index.values()
        .filter_map(|item| item.name.clone())
        .collect();

    assert!(names.contains(&"MyStruct".to_string()), "Should contain MyStruct");
    assert!(names.contains(&"MyEnum".to_string()), "Should contain MyEnum");
    assert!(names.contains(&"MyTrait".to_string()), "Should contain MyTrait");
    assert!(names.contains(&"fallible".to_string()), "Should contain fallible");
    assert!(names.contains(&"nested".to_string()), "Should contain nested module");
}

#[test]
fn extract_crate_version_works() {
    let toml = r#"
[package]
name = "my-crate"
version = "1.2.3"
edition = "2021"
"#;
    assert_eq!(
        rustdoc_loader::extract_crate_version(toml),
        Some("1.2.3".to_string())
    );
}

#[test]
fn extract_crate_version_missing() {
    let toml = r#"
[dependencies]
serde = "1"
"#;
    assert_eq!(rustdoc_loader::extract_crate_version(toml), None);
}

#[test]
fn load_nonexistent_file_gives_error() {
    let result = rustdoc_loader::load_json(Path::new("/nonexistent/file.json"));
    assert!(result.is_err());
}
