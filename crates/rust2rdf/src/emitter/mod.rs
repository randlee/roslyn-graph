pub mod ntriples;
pub mod turtle;

/// Trait for emitting RDF triples in different serialization formats.
/// Direct port of the .NET ITriplesEmitter interface.
pub trait TriplesEmitter {
    /// Emit a triple with an IRI object.
    fn emit_iri(&mut self, subject: &str, predicate: &str, object: &str);
    /// Emit a triple with a plain string literal object.
    fn emit_literal(&mut self, subject: &str, predicate: &str, value: &str);
    /// Emit a triple with a typed literal object.
    fn emit_typed_literal(&mut self, subject: &str, predicate: &str, value: &str, datatype: &str);
    /// Emit a triple with a boolean literal object.
    fn emit_bool(&mut self, subject: &str, predicate: &str, value: bool);
    /// Emit a triple with an integer literal object.
    fn emit_int(&mut self, subject: &str, predicate: &str, value: i64);
    /// Register a namespace prefix (used by Turtle format).
    fn add_prefix(&mut self, prefix: &str, iri: &str);
    /// Flush any buffered output.
    fn flush(&mut self) -> std::io::Result<()>;
    /// Return the number of triples emitted so far.
    fn triple_count(&self) -> u64;
}
