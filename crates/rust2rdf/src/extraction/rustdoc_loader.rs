//! Load and deserialize rustdoc JSON output.

use std::path::Path;
use std::process::Command;
use super::rustdoc_model::Crate;

/// Errors that can occur during loading.
#[derive(Debug)]
pub enum LoadError {
    Io(std::io::Error),
    Json(serde_json::Error),
    RustdocFailed(String),
    CrateNameNotFound,
    OutputNotFound(String),
}

impl std::fmt::Display for LoadError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            LoadError::Io(e) => write!(f, "IO error: {e}"),
            LoadError::Json(e) => write!(f, "JSON parse error: {e}"),
            LoadError::RustdocFailed(msg) => write!(f, "rustdoc failed: {msg}"),
            LoadError::CrateNameNotFound => write!(f, "could not determine crate name from Cargo.toml"),
            LoadError::OutputNotFound(path) => write!(f, "rustdoc JSON output not found at: {path}"),
        }
    }
}

impl std::error::Error for LoadError {}

impl From<std::io::Error> for LoadError {
    fn from(e: std::io::Error) -> Self { LoadError::Io(e) }
}

impl From<serde_json::Error> for LoadError {
    fn from(e: serde_json::Error) -> Self { LoadError::Json(e) }
}

/// Load a rustdoc JSON file from disk.
pub fn load_json(path: &Path) -> Result<Crate, LoadError> {
    let content = std::fs::read_to_string(path)?;
    let krate: Crate = serde_json::from_str(&content)?;
    Ok(krate)
}

/// Run `cargo +nightly rustdoc` on a crate directory and load the result.
pub fn load_crate(crate_dir: &Path) -> Result<Crate, LoadError> {
    // Determine crate name from Cargo.toml
    let cargo_toml_path = crate_dir.join("Cargo.toml");
    let cargo_toml = std::fs::read_to_string(&cargo_toml_path)?;
    let crate_name = extract_crate_name(&cargo_toml)
        .ok_or(LoadError::CrateNameNotFound)?;

    // Run cargo rustdoc
    let output = Command::new("cargo")
        .args(["+nightly", "rustdoc", "--", "-Z", "unstable-options", "--output-format", "json"])
        .current_dir(crate_dir)
        .output()?;

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        return Err(LoadError::RustdocFailed(stderr.to_string()));
    }

    // Find the JSON output
    let json_name = crate_name.replace('-', "_");
    let json_path = crate_dir.join(format!("target/doc/{json_name}.json"));

    if !json_path.exists() {
        return Err(LoadError::OutputNotFound(json_path.display().to_string()));
    }

    load_json(&json_path)
}

/// Extract crate name from Cargo.toml content (simple parser).
fn extract_crate_name(content: &str) -> Option<String> {
    for line in content.lines() {
        let line = line.trim();
        if line.starts_with("name") {
            if let Some(value) = line.split('=').nth(1) {
                let name = value.trim().trim_matches('"').trim_matches('\'');
                return Some(name.to_string());
            }
        }
    }
    None
}

/// Extract crate version from Cargo.toml content.
pub fn extract_crate_version(content: &str) -> Option<String> {
    let mut in_package = false;
    for line in content.lines() {
        let line = line.trim();
        if line == "[package]" {
            in_package = true;
            continue;
        }
        if line.starts_with('[') && line != "[package]" {
            in_package = false;
            continue;
        }
        if in_package && line.starts_with("version") {
            if let Some(value) = line.split('=').nth(1) {
                let version = value.trim().trim_matches('"').trim_matches('\'');
                return Some(version.to_string());
            }
        }
    }
    None
}
