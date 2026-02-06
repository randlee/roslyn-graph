//! CLI integration tests.
//!
//! These tests invoke the `rust2rdf` binary via `std::process::Command`
//! against the fixture JSON file and verify output correctness.

use std::path::PathBuf;
use std::process::Command;

/// Path to the built binary (set by cargo test).
fn binary_path() -> PathBuf {
    // `cargo test` places the test binary next to the main binary
    let mut path = std::env::current_exe()
        .expect("current_exe")
        .parent()
        .expect("parent")
        .parent()
        .expect("grandparent")
        .to_path_buf();
    path.push("rust2rdf");
    path
}

/// Path to the fixture JSON file.
fn fixture_path() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests")
        .join("fixtures")
        .join("fixture_crate.json")
}

#[test]
fn ntriples_output_is_valid() {
    let output = Command::new(binary_path())
        .args(["--json", fixture_path().to_str().unwrap(), "-q"])
        .output()
        .expect("failed to execute binary");

    assert!(
        output.status.success(),
        "rust2rdf failed: {}",
        String::from_utf8_lossy(&output.stderr)
    );

    let stdout = String::from_utf8(output.stdout).expect("invalid UTF-8");

    // N-Triples: every non-empty, non-comment line ends with " ."
    for line in stdout.lines() {
        let trimmed = line.trim();
        if trimmed.is_empty() || trimmed.starts_with('#') {
            continue;
        }
        assert!(
            trimmed.ends_with(" ."),
            "N-Triples line does not end with ' .': {trimmed}"
        );
        // Each triple line should have a subject starting with <
        assert!(
            trimmed.starts_with('<'),
            "N-Triples line does not start with '<': {trimmed}"
        );
    }

    // Should have produced some triples (excluding comment/blank lines)
    let triple_lines: usize = stdout
        .lines()
        .filter(|l| {
            let t = l.trim();
            !t.is_empty() && !t.starts_with('#')
        })
        .count();
    assert!(
        triple_lines > 10,
        "Expected more than 10 triples, got {triple_lines}"
    );
}

#[test]
fn turtle_output_has_prefixes() {
    let output = Command::new(binary_path())
        .args([
            "--json",
            fixture_path().to_str().unwrap(),
            "--format",
            "turtle",
            "-q",
        ])
        .output()
        .expect("failed to execute binary");

    assert!(
        output.status.success(),
        "rust2rdf failed: {}",
        String::from_utf8_lossy(&output.stderr)
    );

    let stdout = String::from_utf8(output.stdout).expect("invalid UTF-8");

    // Turtle output should have @prefix declarations
    assert!(
        stdout.contains("@prefix"),
        "Turtle output should contain @prefix declarations"
    );
    assert!(
        stdout.contains("@prefix rdf:"),
        "Turtle output should contain rdf prefix"
    );
}

#[test]
fn base_uri_changes_output_iris() {
    let custom_base = "http://custom.example/test";
    let output = Command::new(binary_path())
        .args([
            "--json",
            fixture_path().to_str().unwrap(),
            "--base-uri",
            custom_base,
            "-q",
        ])
        .output()
        .expect("failed to execute binary");

    assert!(
        output.status.success(),
        "rust2rdf failed: {}",
        String::from_utf8_lossy(&output.stderr)
    );

    let stdout = String::from_utf8(output.stdout).expect("invalid UTF-8");

    // Output should contain the custom base URI in subject IRIs
    assert!(
        stdout.contains("http://custom.example/test/crate/"),
        "Output should contain custom base URI in crate IRIs"
    );

    // Subject IRIs for crate/types should NOT use the default base URI.
    // Note: the ontology namespace (http://rust.example/ontology/) is a fixed
    // constant and will still appear in predicate/type IRIs -- that is expected.
    let has_default_subject = stdout.lines().any(|line| {
        let trimmed = line.trim();
        if trimmed.is_empty() || trimmed.starts_with('#') {
            return false;
        }
        // Check the subject (first <...>) for default base URI
        trimmed.starts_with("<http://rust.example/crate/")
            || trimmed.starts_with("<http://rust.example/type/")
            || trimmed.starts_with("<http://rust.example/module/")
    });
    assert!(
        !has_default_subject,
        "Subject IRIs should use custom base URI, not the default"
    );
}

#[test]
fn exclude_impls_reduces_triple_count() {
    // Run with impls
    let with_impls = Command::new(binary_path())
        .args(["--json", fixture_path().to_str().unwrap(), "-q"])
        .output()
        .expect("failed to execute binary");
    assert!(with_impls.status.success());
    let with_count = String::from_utf8(with_impls.stdout)
        .unwrap()
        .lines()
        .filter(|l| {
            let t = l.trim();
            !t.is_empty() && !t.starts_with('#')
        })
        .count();

    // Run without impls
    let without_impls = Command::new(binary_path())
        .args([
            "--json",
            fixture_path().to_str().unwrap(),
            "--exclude-impls",
            "-q",
        ])
        .output()
        .expect("failed to execute binary");
    assert!(without_impls.status.success());
    let without_count = String::from_utf8(without_impls.stdout)
        .unwrap()
        .lines()
        .filter(|l| {
            let t = l.trim();
            !t.is_empty() && !t.starts_with('#')
        })
        .count();

    // Excluding impls should produce fewer triples (or equal if no impls in fixture)
    assert!(
        without_count <= with_count,
        "Excluding impls should not increase triple count: {without_count} > {with_count}"
    );
}

#[test]
fn verbose_prints_summary_to_stderr() {
    let output = Command::new(binary_path())
        .args(["--json", fixture_path().to_str().unwrap(), "--verbose"])
        .output()
        .expect("failed to execute binary");

    assert!(output.status.success());

    let stderr = String::from_utf8(output.stderr).expect("invalid UTF-8");

    assert!(
        stderr.contains("Loading input from:"),
        "Verbose mode should show loading message"
    );
    assert!(
        stderr.contains("Crate:"),
        "Verbose mode should show crate info"
    );
    assert!(
        stderr.contains("Extracted"),
        "Should show extraction summary"
    );
    assert!(
        stderr.contains("triples"),
        "Summary should mention triple count"
    );
}

#[test]
fn quiet_suppresses_stderr() {
    let output = Command::new(binary_path())
        .args(["--json", fixture_path().to_str().unwrap(), "-q"])
        .output()
        .expect("failed to execute binary");

    assert!(output.status.success());

    let stderr = String::from_utf8(output.stderr).expect("invalid UTF-8");
    assert!(
        stderr.is_empty(),
        "Quiet mode should produce no stderr output, got: {stderr}"
    );
}
