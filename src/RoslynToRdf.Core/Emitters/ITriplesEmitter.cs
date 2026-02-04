namespace RoslynToRdf.Core.Emitters;

/// <summary>
/// Abstraction for emitting RDF triples.
/// </summary>
public interface ITriplesEmitter : IDisposable
{
    /// <summary>
    /// Emit a triple with an IRI object.
    /// </summary>
    void EmitIri(string subject, string predicate, string objectIri);

    /// <summary>
    /// Emit a triple with a string literal object.
    /// </summary>
    void EmitLiteral(string subject, string predicate, string value);

    /// <summary>
    /// Emit a triple with a typed literal object.
    /// </summary>
    void EmitTypedLiteral(string subject, string predicate, string value, string datatype);

    /// <summary>
    /// Emit a triple with a boolean literal.
    /// </summary>
    void EmitBool(string subject, string predicate, bool value);

    /// <summary>
    /// Emit a triple with an integer literal.
    /// </summary>
    void EmitInt(string subject, string predicate, int value);

    /// <summary>
    /// Emit a triple with a long literal.
    /// </summary>
    void EmitLong(string subject, string predicate, long value);

    /// <summary>
    /// Add a prefix declaration.
    /// </summary>
    void AddPrefix(string prefix, string iri);

    /// <summary>
    /// Flush any buffered output.
    /// </summary>
    void Flush();

    /// <summary>
    /// Total number of triples emitted.
    /// </summary>
    long TripleCount { get; }
}
