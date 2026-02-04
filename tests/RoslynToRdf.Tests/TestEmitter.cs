using RoslynToRdf.Core.Emitters;
using RoslynToRdf.Core.Model;

namespace RoslynToRdf.Tests;

internal sealed class TestEmitter : ITriplesEmitter
{
    public sealed record Triple(string Subject, string Predicate, string Object, bool IsIri, string? Datatype);

    private readonly List<Triple> _triples = new();
    private readonly Dictionary<string, string> _prefixes = new();

    public IReadOnlyList<Triple> Triples => _triples;
    public IReadOnlyDictionary<string, string> Prefixes => _prefixes;

    public long TripleCount => _triples.Count;

    public void EmitIri(string subject, string predicate, string objectIri)
    {
        _triples.Add(new Triple(subject, predicate, objectIri, true, null));
    }

    public void EmitLiteral(string subject, string predicate, string value)
    {
        _triples.Add(new Triple(subject, predicate, value, false, null));
    }

    public void EmitTypedLiteral(string subject, string predicate, string value, string datatype)
    {
        _triples.Add(new Triple(subject, predicate, value, false, datatype));
    }

    public void EmitBool(string subject, string predicate, bool value)
    {
        EmitTypedLiteral(subject, predicate, value ? "true" : "false", DotNetOntology.Xsd + "boolean");
    }

    public void EmitInt(string subject, string predicate, int value)
    {
        EmitTypedLiteral(subject, predicate, value.ToString(), DotNetOntology.Xsd + "integer");
    }

    public void EmitLong(string subject, string predicate, long value)
    {
        EmitTypedLiteral(subject, predicate, value.ToString(), DotNetOntology.Xsd + "long");
    }

    public void AddPrefix(string prefix, string iri)
    {
        _prefixes[prefix] = iri;
    }

    public void Flush()
    {
    }

    public void Dispose()
    {
    }
}
