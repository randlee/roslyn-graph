using System.Text;
using RoslynToRdf.Core.Model;

namespace RoslynToRdf.Core.Emitters;

/// <summary>
/// Emits RDF triples in N-Triples format (.nt).
/// N-Triples is a simple line-based format ideal for bulk loading.
/// </summary>
public sealed class NTriplesEmitter : ITriplesEmitter
{
    private readonly StreamWriter _writer;
    private long _tripleCount;

    public NTriplesEmitter(string filePath)
    {
        _writer = new StreamWriter(filePath, false, new UTF8Encoding(false))
        {
            AutoFlush = false
        };
    }

    public NTriplesEmitter(Stream stream, bool leaveOpen = false)
    {
        _writer = new StreamWriter(stream, new UTF8Encoding(false), leaveOpen: leaveOpen)
        {
            AutoFlush = false
        };
    }

    public long TripleCount => _tripleCount;

    public void EmitIri(string subject, string predicate, string objectIri)
    {
        _writer.Write('<');
        _writer.Write(subject);
        _writer.Write("> <");
        _writer.Write(predicate);
        _writer.Write("> <");
        _writer.Write(objectIri);
        _writer.WriteLine("> .");
        _tripleCount++;
    }

    public void EmitLiteral(string subject, string predicate, string value)
    {
        _writer.Write('<');
        _writer.Write(subject);
        _writer.Write("> <");
        _writer.Write(predicate);
        _writer.Write("> \"");
        _writer.Write(EscapeString(value));
        _writer.WriteLine("\" .");
        _tripleCount++;
    }

    public void EmitTypedLiteral(string subject, string predicate, string value, string datatype)
    {
        _writer.Write('<');
        _writer.Write(subject);
        _writer.Write("> <");
        _writer.Write(predicate);
        _writer.Write("> \"");
        _writer.Write(EscapeString(value));
        _writer.Write("\"^^<");
        _writer.Write(datatype);
        _writer.WriteLine("> .");
        _tripleCount++;
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
        // N-Triples doesn't support prefixes, but we can emit a comment for documentation
        _writer.WriteLine($"# @prefix {prefix}: <{iri}> .");
    }

    public void Flush()
    {
        _writer.Flush();
    }

    public void Dispose()
    {
        _writer.Dispose();
    }

    /// <summary>
    /// Escape special characters for N-Triples string literals.
    /// </summary>
    private static string EscapeString(string value)
    {
        if (string.IsNullOrEmpty(value))
            return value;

        var sb = new StringBuilder(value.Length + 16);
        foreach (var c in value)
        {
            switch (c)
            {
                case '\\': sb.Append("\\\\"); break;
                case '"': sb.Append("\\\""); break;
                case '\n': sb.Append("\\n"); break;
                case '\r': sb.Append("\\r"); break;
                case '\t': sb.Append("\\t"); break;
                default:
                    if (c < 0x20)
                    {
                        sb.Append("\\u");
                        sb.Append(((int)c).ToString("X4"));
                    }
                    else
                    {
                        sb.Append(c);
                    }
                    break;
            }
        }
        return sb.ToString();
    }
}
