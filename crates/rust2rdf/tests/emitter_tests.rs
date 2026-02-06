use rust2rdf::emitter::ntriples::NTriplesEmitter;
use rust2rdf::emitter::turtle::TurtleEmitter;
use rust2rdf::emitter::TriplesEmitter;

// ---------------------------------------------------------------------------
// NTriples tests
// ---------------------------------------------------------------------------

#[test]
fn nt_basic_iri_triple() {
    let mut buf = Vec::new();
    let mut em = NTriplesEmitter::new(&mut buf);
    em.emit_iri(
        "http://example.org/s",
        "http://example.org/p",
        "http://example.org/o",
    );
    let out = String::from_utf8(buf).unwrap();
    assert_eq!(
        out,
        "<http://example.org/s> <http://example.org/p> <http://example.org/o> .\n"
    );
}

#[test]
fn nt_literal_triple() {
    let mut buf = Vec::new();
    let mut em = NTriplesEmitter::new(&mut buf);
    em.emit_literal(
        "http://example.org/s",
        "http://example.org/name",
        "hello world",
    );
    let out = String::from_utf8(buf).unwrap();
    assert_eq!(
        out,
        "<http://example.org/s> <http://example.org/name> \"hello world\" .\n"
    );
}

#[test]
fn nt_typed_literal() {
    let mut buf = Vec::new();
    let mut em = NTriplesEmitter::new(&mut buf);
    em.emit_typed_literal(
        "http://example.org/s",
        "http://example.org/p",
        "42",
        "http://www.w3.org/2001/XMLSchema#integer",
    );
    let out = String::from_utf8(buf).unwrap();
    assert_eq!(
        out,
        "<http://example.org/s> <http://example.org/p> \"42\"^^<http://www.w3.org/2001/XMLSchema#integer> .\n"
    );
}

#[test]
fn nt_bool_true() {
    let mut buf = Vec::new();
    let mut em = NTriplesEmitter::new(&mut buf);
    em.emit_bool("http://example.org/s", "http://example.org/flag", true);
    let out = String::from_utf8(buf).unwrap();
    assert!(out.contains("\"true\"^^<http://www.w3.org/2001/XMLSchema#boolean>"));
}

#[test]
fn nt_bool_false() {
    let mut buf = Vec::new();
    let mut em = NTriplesEmitter::new(&mut buf);
    em.emit_bool("http://example.org/s", "http://example.org/flag", false);
    let out = String::from_utf8(buf).unwrap();
    assert!(out.contains("\"false\"^^<http://www.w3.org/2001/XMLSchema#boolean>"));
}

#[test]
fn nt_int() {
    let mut buf = Vec::new();
    let mut em = NTriplesEmitter::new(&mut buf);
    em.emit_int("http://example.org/s", "http://example.org/count", -7);
    let out = String::from_utf8(buf).unwrap();
    assert!(out.contains("\"-7\"^^<http://www.w3.org/2001/XMLSchema#integer>"));
}

#[test]
fn nt_escape_special_chars() {
    let mut buf = Vec::new();
    let mut em = NTriplesEmitter::new(&mut buf);
    em.emit_literal(
        "http://example.org/s",
        "http://example.org/p",
        "line1\nline2\ttab\\slash\"quote",
    );
    let out = String::from_utf8(buf).unwrap();
    assert!(out.contains(r#"\"#));
    assert!(out.contains("\\n"));
    assert!(out.contains("\\t"));
    assert!(out.contains("\\\\"));
    assert!(out.contains("\\\""));
}

#[test]
fn nt_escape_control_chars() {
    let mut buf = Vec::new();
    let mut em = NTriplesEmitter::new(&mut buf);
    // \x01 is a control char that should be escaped as \u0001
    em.emit_literal(
        "http://example.org/s",
        "http://example.org/p",
        "a\x01b",
    );
    let out = String::from_utf8(buf).unwrap();
    assert!(out.contains("\\u0001"), "Expected \\u0001 in: {out}");
}

#[test]
fn nt_escape_unicode_passthrough() {
    let mut buf = Vec::new();
    let mut em = NTriplesEmitter::new(&mut buf);
    // Non-ASCII characters above U+001F should pass through unchanged
    em.emit_literal(
        "http://example.org/s",
        "http://example.org/p",
        "cafe\u{0301}",
    );
    let out = String::from_utf8(buf).unwrap();
    assert!(
        out.contains("cafe\u{0301}"),
        "Unicode should pass through: {out}"
    );
}

#[test]
fn nt_prefix_as_comment() {
    let mut buf = Vec::new();
    let mut em = NTriplesEmitter::new(&mut buf);
    em.add_prefix("ex", "http://example.org/");
    let out = String::from_utf8(buf).unwrap();
    assert_eq!(out, "# @prefix ex: <http://example.org/> .\n");
}

#[test]
fn nt_triple_count() {
    let mut buf = Vec::new();
    let mut em = NTriplesEmitter::new(&mut buf);
    assert_eq!(em.triple_count(), 0);
    em.emit_iri(
        "http://example.org/s",
        "http://example.org/p",
        "http://example.org/o",
    );
    assert_eq!(em.triple_count(), 1);
    em.emit_literal("http://example.org/s", "http://example.org/p", "val");
    assert_eq!(em.triple_count(), 2);
    em.emit_bool("http://example.org/s", "http://example.org/p", true);
    assert_eq!(em.triple_count(), 3);
    em.emit_int("http://example.org/s", "http://example.org/p", 10);
    assert_eq!(em.triple_count(), 4);
}

#[test]
fn nt_flush() {
    let mut buf = Vec::new();
    let mut em = NTriplesEmitter::new(&mut buf);
    em.emit_iri(
        "http://example.org/s",
        "http://example.org/p",
        "http://example.org/o",
    );
    assert!(em.flush().is_ok());
}

// ---------------------------------------------------------------------------
// Turtle tests
// ---------------------------------------------------------------------------

#[test]
fn turtle_basic_iri_with_prefix() {
    let mut buf = Vec::new();
    let mut em = TurtleEmitter::new(&mut buf);
    em.add_prefix("ex", "http://example.org/");
    em.emit_iri(
        "http://example.org/s",
        "http://example.org/p",
        "http://example.org/o",
    );
    let out = String::from_utf8(buf).unwrap();
    assert!(out.contains("@prefix ex: <http://example.org/> ."));
    assert!(out.contains("ex:s ex:p ex:o ."));
}

#[test]
fn turtle_literal_with_prefix() {
    let mut buf = Vec::new();
    let mut em = TurtleEmitter::new(&mut buf);
    em.add_prefix("ex", "http://example.org/");
    em.emit_literal("http://example.org/s", "http://example.org/name", "Alice");
    let out = String::from_utf8(buf).unwrap();
    assert!(
        out.contains("ex:s ex:name \"Alice\" ."),
        "Expected compacted form: {out}"
    );
}

#[test]
fn turtle_typed_literal_with_prefix() {
    let mut buf = Vec::new();
    let mut em = TurtleEmitter::new(&mut buf);
    em.add_prefix("xsd", "http://www.w3.org/2001/XMLSchema#");
    em.add_prefix("ex", "http://example.org/");
    em.emit_typed_literal(
        "http://example.org/s",
        "http://example.org/p",
        "42",
        "http://www.w3.org/2001/XMLSchema#integer",
    );
    let out = String::from_utf8(buf).unwrap();
    assert!(
        out.contains("ex:s ex:p \"42\"^^xsd:integer ."),
        "Expected compacted typed literal: {out}"
    );
}

#[test]
fn turtle_bool() {
    let mut buf = Vec::new();
    let mut em = TurtleEmitter::new(&mut buf);
    em.add_prefix("xsd", "http://www.w3.org/2001/XMLSchema#");
    em.emit_bool("http://example.org/s", "http://example.org/p", true);
    let out = String::from_utf8(buf).unwrap();
    assert!(
        out.contains("\"true\"^^xsd:boolean"),
        "Expected compacted bool: {out}"
    );
}

#[test]
fn turtle_int() {
    let mut buf = Vec::new();
    let mut em = TurtleEmitter::new(&mut buf);
    em.add_prefix("xsd", "http://www.w3.org/2001/XMLSchema#");
    em.emit_int("http://example.org/s", "http://example.org/p", 99);
    let out = String::from_utf8(buf).unwrap();
    assert!(
        out.contains("\"99\"^^xsd:integer"),
        "Expected compacted int: {out}"
    );
}

#[test]
fn turtle_prefix_declaration_sorted() {
    let mut buf = Vec::new();
    let mut em = TurtleEmitter::new(&mut buf);
    em.add_prefix("z", "http://z.org/");
    em.add_prefix("a", "http://a.org/");
    em.add_prefix("m", "http://m.org/");
    em.emit_iri("http://a.org/s", "http://m.org/p", "http://z.org/o");
    let out = String::from_utf8(buf).unwrap();
    let a_pos = out.find("@prefix a:").expect("missing @prefix a:");
    let m_pos = out.find("@prefix m:").expect("missing @prefix m:");
    let z_pos = out.find("@prefix z:").expect("missing @prefix z:");
    assert!(
        a_pos < m_pos && m_pos < z_pos,
        "Prefixes not sorted: a@{a_pos} m@{m_pos} z@{z_pos}"
    );
}

#[test]
fn turtle_escape_special_chars() {
    let mut buf = Vec::new();
    let mut em = TurtleEmitter::new(&mut buf);
    em.emit_literal(
        "http://example.org/s",
        "http://example.org/p",
        "line\n\"end\\",
    );
    let out = String::from_utf8(buf).unwrap();
    assert!(out.contains("\\n"), "Expected escaped newline: {out}");
    assert!(out.contains("\\\""), "Expected escaped quote: {out}");
    assert!(out.contains("\\\\"), "Expected escaped backslash: {out}");
}

#[test]
fn turtle_non_compactable_iri() {
    let mut buf = Vec::new();
    let mut em = TurtleEmitter::new(&mut buf);
    em.add_prefix("ex", "http://example.org/");
    // IRI that doesn't match any prefix
    em.emit_iri(
        "http://other.org/s",
        "http://example.org/p",
        "http://other.org/o",
    );
    let out = String::from_utf8(buf).unwrap();
    assert!(
        out.contains("<http://other.org/s>"),
        "Non-matching IRI should stay full: {out}"
    );
    assert!(out.contains("ex:p"), "Matching IRI should compact: {out}");
}

#[test]
fn turtle_triple_count() {
    let mut buf = Vec::new();
    let mut em = TurtleEmitter::new(&mut buf);
    assert_eq!(em.triple_count(), 0);
    em.emit_iri(
        "http://example.org/s",
        "http://example.org/p",
        "http://example.org/o",
    );
    em.emit_literal("http://example.org/s", "http://example.org/p", "v");
    em.emit_bool("http://example.org/s", "http://example.org/p", false);
    em.emit_int("http://example.org/s", "http://example.org/p", 1);
    assert_eq!(em.triple_count(), 4);
}

#[test]
fn turtle_no_prefix_uses_full_iri() {
    let mut buf = Vec::new();
    let mut em = TurtleEmitter::new(&mut buf);
    // No prefixes added — should use full IRIs in angle brackets
    em.emit_iri(
        "http://example.org/s",
        "http://example.org/p",
        "http://example.org/o",
    );
    let out = String::from_utf8(buf).unwrap();
    assert_eq!(
        out,
        "<http://example.org/s> <http://example.org/p> <http://example.org/o> .\n"
    );
}

#[test]
fn turtle_local_name_with_special_chars_not_compacted() {
    let mut buf = Vec::new();
    let mut em = TurtleEmitter::new(&mut buf);
    em.add_prefix("ex", "http://example.org/");
    // IRI whose local part has a dot — should NOT compact
    em.emit_iri(
        "http://example.org/foo.bar",
        "http://example.org/p",
        "http://example.org/o",
    );
    let out = String::from_utf8(buf).unwrap();
    assert!(
        out.contains("<http://example.org/foo.bar>"),
        "IRI with '.' should not compact: {out}"
    );
}

#[test]
fn turtle_flush() {
    let mut buf = Vec::new();
    let mut em = TurtleEmitter::new(&mut buf);
    em.emit_iri(
        "http://example.org/s",
        "http://example.org/p",
        "http://example.org/o",
    );
    assert!(em.flush().is_ok());
}
