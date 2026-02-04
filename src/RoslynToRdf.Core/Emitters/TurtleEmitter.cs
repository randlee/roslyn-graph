using System.Text;
using RoslynToRdf.Core.Model;

namespace RoslynToRdf.Core.Emitters;

/// <summary>
/// Emits RDF triples in Turtle format (.ttl).
/// Turtle is more human-readable than N-Triples but equivalent.
/// </summary>
public sealed class TurtleEmitter : ITriplesEmitter
{
    private readonly StreamWriter _writer;
    private readonly Dictionary<string, string> _prefixes = new();
    private long _tripleCount;
    private bool _prefixesWritten;

    public TurtleEmitter(string filePath)
    {
        _writer = new StreamWriter(filePath, false, new UTF8Encoding(false))
        {
            AutoFlush = false
        };
    }

    public TurtleEmitter(Stream stream, bool leaveOpen = false)
    {
        _writer = new StreamWriter(stream, new UTF8Encoding(false), leaveOpen: leaveOpen)
        {
            AutoFlush = false
        };
    }

    public long TripleCount => _tripleCount;

    public void AddPrefix(string prefix, string iri)
    {
        _prefixes[prefix] = iri;
    }

    private void EnsurePrefixesWritten()
    {
        if (_prefixesWritten) return;
        _prefixesWritten = true;

        foreach (var (prefix, iri) in _prefixes)
        {
            _writer.WriteLine($"@prefix {prefix}: <{iri}> .");
        }

        if (_prefixes.Count > 0)
            _writer.WriteLine();
    }

    public void EmitIri(string subject, string predicate, string objectIri)
    {
        EnsurePrefixesWritten();
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
        EnsurePrefixesWritten();
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
        EnsurePrefixesWritten();
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
        EnsurePrefixesWritten();
        _writer.Write('<');
        _writer.Write(subject);
        _writer.Write("> <");
        _writer.Write(predicate);
        _writer.Write("> ");
        _writer.Write(value ? "true" : "false");
        _writer.WriteLine(" .");
        _tripleCount++;
    }

    public void EmitInt(string subject, string predicate, int value)
    {
        EnsurePrefixesWritten();
        _writer.Write('<');
        _writer.Write(subject);
        _writer.Write("> <");
        _writer.Write(predicate);
        _writer.Write("> ");
        _writer.Write(value);
        _writer.WriteLine(" .");
        _tripleCount++;
    }

    public void EmitLong(string subject, string predicate, long value)
    {
        EmitTypedLiteral(subject, predicate, value.ToString(), DotNetOntology.Xsd + "long");
    }

    public void Flush()
    {
        _writer.Flush();
    }

    public void Dispose()
    {
        _writer.Dispose();
    }

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
