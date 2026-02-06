use std::io::Write;
use super::TriplesEmitter;

/// N-Triples format emitter. Streams triples as `<s> <p> <o> .` lines.
pub struct NTriplesEmitter<W: Write> {
    writer: W,
    count: u64,
}

impl<W: Write> NTriplesEmitter<W> {
    pub fn new(writer: W) -> Self {
        Self { writer, count: 0 }
    }

    /// Escape a string for N-Triples literal (per RDF 1.1 N-Triples spec).
    fn escape_literal(s: &str) -> String {
        let mut out = String::with_capacity(s.len());
        for c in s.chars() {
            match c {
                '\\' => out.push_str("\\\\"),
                '"' => out.push_str("\\\""),
                '\n' => out.push_str("\\n"),
                '\r' => out.push_str("\\r"),
                '\t' => out.push_str("\\t"),
                c if (c as u32) < 0x20 => {
                    // Control chars: \uXXXX
                    out.push_str(&format!("\\u{:04X}", c as u32));
                }
                _ => out.push(c),
            }
        }
        out
    }
}

impl<W: Write> TriplesEmitter for NTriplesEmitter<W> {
    fn emit_iri(&mut self, subject: &str, predicate: &str, object: &str) {
        writeln!(self.writer, "<{subject}> <{predicate}> <{object}> .").unwrap();
        self.count += 1;
    }

    fn emit_literal(&mut self, subject: &str, predicate: &str, value: &str) {
        let escaped = Self::escape_literal(value);
        writeln!(self.writer, "<{subject}> <{predicate}> \"{escaped}\" .").unwrap();
        self.count += 1;
    }

    fn emit_typed_literal(
        &mut self,
        subject: &str,
        predicate: &str,
        value: &str,
        datatype: &str,
    ) {
        let escaped = Self::escape_literal(value);
        writeln!(
            self.writer,
            "<{subject}> <{predicate}> \"{escaped}\"^^<{datatype}> ."
        )
        .unwrap();
        self.count += 1;
    }

    fn emit_bool(&mut self, subject: &str, predicate: &str, value: bool) {
        let val = if value { "true" } else { "false" };
        self.emit_typed_literal(
            subject,
            predicate,
            val,
            "http://www.w3.org/2001/XMLSchema#boolean",
        );
    }

    fn emit_int(&mut self, subject: &str, predicate: &str, value: i64) {
        self.emit_typed_literal(
            subject,
            predicate,
            &value.to_string(),
            "http://www.w3.org/2001/XMLSchema#integer",
        );
    }

    fn add_prefix(&mut self, prefix: &str, iri: &str) {
        // N-Triples doesn't use prefixes, but emit as comment for readability
        writeln!(self.writer, "# @prefix {prefix}: <{iri}> .").unwrap();
    }

    fn flush(&mut self) -> std::io::Result<()> {
        self.writer.flush()
    }

    fn triple_count(&self) -> u64 {
        self.count
    }
}
