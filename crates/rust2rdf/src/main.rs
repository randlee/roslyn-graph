use std::fs::File;
use std::io::{self, BufWriter, Write};
use std::path::PathBuf;
use std::process;

use clap::Parser;

use rust2rdf::emitter::ntriples::NTriplesEmitter;
use rust2rdf::emitter::turtle::TurtleEmitter;
use rust2rdf::emitter::TriplesEmitter;
use rust2rdf::extraction::extractor::{CrateExtractor, ExtractionOptions};
use rust2rdf::extraction::rustdoc_loader::{load_crate, load_json};

/// Extract Rust crate type graphs to RDF format.
#[derive(Parser)]
#[command(name = "rust2rdf", version, about)]
struct Cli {
    /// Path to crate directory or rustdoc JSON file.
    input: PathBuf,

    /// Output file path [default: stdout].
    #[arg(short, long, value_name = "FILE")]
    output: Option<PathBuf>,

    /// Output format: ntriples, turtle.
    #[arg(short, long, value_name = "FORMAT", default_value = "ntriples")]
    format: String,

    /// Base URI for IRIs.
    #[arg(short, long, value_name = "URI", default_value = "http://rust.example/")]
    base_uri: String,

    /// Exclude impl blocks.
    #[arg(long)]
    exclude_impls: bool,

    /// Exclude attribute information.
    #[arg(long)]
    exclude_attributes: bool,

    /// Don't extract Result<T,E> error types.
    #[arg(long)]
    no_error_types: bool,

    /// Don't extract derive macros.
    #[arg(long)]
    no_derives: bool,

    /// Input is a pre-generated rustdoc JSON file.
    #[arg(long)]
    json: bool,

    /// Verbose output.
    #[arg(short, long)]
    verbose: bool,

    /// Quiet output.
    #[arg(short, long)]
    quiet: bool,
}

fn run(cli: Cli) -> Result<(), Box<dyn std::error::Error>> {
    // Load the crate data
    if cli.verbose {
        eprintln!("Loading input from: {}", cli.input.display());
    }

    let crate_data = if cli.json {
        load_json(&cli.input)?
    } else {
        load_crate(&cli.input)?
    };

    // Determine crate name and version from the loaded data
    let crate_name = crate_data
        .index
        .get(&crate_data.root.0)
        .and_then(|item| item.name.clone())
        .unwrap_or_else(|| "unknown".to_string());

    let crate_version = crate_data
        .crate_version
        .clone()
        .unwrap_or_else(|| "0.0.0".to_string());

    if cli.verbose {
        eprintln!("Crate: {crate_name} v{crate_version}");
    }

    // Build extraction options
    let options = ExtractionOptions {
        base_uri: cli.base_uri.clone(),
        include_impls: !cli.exclude_impls,
        include_attributes: !cli.exclude_attributes,
        extract_error_types: !cli.no_error_types,
        extract_derives: !cli.no_derives,
    };

    // Determine output writer
    let output_writer: Box<dyn Write> = match &cli.output {
        Some(path) => Box::new(BufWriter::new(File::create(path)?)),
        None => Box::new(BufWriter::new(io::stdout().lock())),
    };

    // Create emitter and run extraction
    let format = cli.format.to_lowercase();
    let triple_count = match format.as_str() {
        "ntriples" | "nt" => {
            let mut emitter = NTriplesEmitter::new(output_writer);
            let mut extractor = CrateExtractor::new(&mut emitter, &crate_data, options);
            extractor.extract();
            emitter.flush()?;
            emitter.triple_count()
        }
        "turtle" | "ttl" => {
            let mut emitter = TurtleEmitter::new(output_writer);
            let mut extractor = CrateExtractor::new(&mut emitter, &crate_data, options);
            extractor.extract();
            emitter.flush()?;
            emitter.triple_count()
        }
        _ => {
            return Err(format!("Unknown format: {format}. Use 'ntriples' or 'turtle'.").into());
        }
    };

    // Print summary to stderr (unless quiet)
    if !cli.quiet {
        eprintln!(
            "Extracted {triple_count} triples from {crate_name} v{crate_version}"
        );
    }

    Ok(())
}

fn main() {
    let cli = Cli::parse();
    if let Err(e) = run(cli) {
        eprintln!("Error: {e}");
        process::exit(1);
    }
}
