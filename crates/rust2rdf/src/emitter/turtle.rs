use std::collections::HashMap;
use std::io::Write;
use super::TriplesEmitter;

/// Turtle format emitter with prefix support.
pub struct TurtleEmitter<W: Write> {
    writer: W,
    count: u64,
    prefixes: HashMap<String, String>,
    prefix_written: bool,
}

impl<W: Write> TurtleEmitter<W> {
    pub fn new(writer: W) -> Self {
        Self {
            writer,
            count: 0,
            prefixes: HashMap::new(),
            prefix_written: false,
        }
    }

    /// Write all registered prefixes (called before first triple).
    fn write_prefixes(&mut self) {
        if self.prefix_written {
            return;
        }
        self.prefix_written = true;
        // Sort for deterministic output
        let mut prefixes: Vec<_> = self.prefixes.iter().collect();
        prefixes.sort_by_key(|(k, _)| (*k).clone());
        for (prefix, iri) in prefixes {
            writeln!(self.writer, "@prefix {prefix}: <{iri}> .").unwrap();
        }
        if !self.prefixes.is_empty() {
            writeln!(self.writer).unwrap();
        }
    }

    /// Try to compact an IRI using registered prefixes.
    fn compact_iri(&self, iri: &str) -> String {
        // Find longest matching prefix
        let mut best: Option<(&str, &str)> = None;
        for (prefix, ns) in &self.prefixes {
            if iri.starts_with(ns.as_str())
                && best.is_none_or(|(_, prev_ns)| ns.len() > prev_ns.len())
            {
                best = Some((prefix.as_str(), ns.as_str()));
            }
        }
        if let Some((prefix, ns)) = best {
            let local = &iri[ns.len()..];
            // Only compact if local name is valid (alphanumeric + _)
            if !local.is_empty() && local.chars().all(|c| c.is_alphanumeric() || c == '_') {
                return format!("{prefix}:{local}");
            }
        }
        format!("<{iri}>")
    }

    fn escape_literal(s: &str) -> String {
        let mut out = String::with_capacity(s.len());
        for c in s.chars() {
            match c {
                '\\' => out.push_str("\\\\"),
                '"' => out.push_str("\\\""),
                '\n' => out.push_str("\\n"),
                '\r' => out.push_str("\\r"),
                '\t' => out.push_str("\\t"),
                _ => out.push(c),
            }
        }
        out
    }
}

impl<W: Write> TriplesEmitter for TurtleEmitter<W> {
    fn emit_iri(&mut self, subject: &str, predicate: &str, object: &str) {
        self.write_prefixes();
        let s = self.compact_iri(subject);
        let p = self.compact_iri(predicate);
        let o = self.compact_iri(object);
        writeln!(self.writer, "{s} {p} {o} .").unwrap();
        self.count += 1;
    }

    fn emit_literal(&mut self, subject: &str, predicate: &str, value: &str) {
        self.write_prefixes();
        let s = self.compact_iri(subject);
        let p = self.compact_iri(predicate);
        let escaped = Self::escape_literal(value);
        writeln!(self.writer, "{s} {p} \"{escaped}\" .").unwrap();
        self.count += 1;
    }

    fn emit_typed_literal(
        &mut self,
        subject: &str,
        predicate: &str,
        value: &str,
        datatype: &str,
    ) {
        self.write_prefixes();
        let s = self.compact_iri(subject);
        let p = self.compact_iri(predicate);
        let dt = self.compact_iri(datatype);
        let escaped = Self::escape_literal(value);
        writeln!(self.writer, "{s} {p} \"{escaped}\"^^{dt} .").unwrap();
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
        self.prefixes.insert(prefix.to_string(), iri.to_string());
    }

    fn flush(&mut self) -> std::io::Result<()> {
        self.writer.flush()
    }

    fn triple_count(&self) -> u64 {
        self.count
    }
}
