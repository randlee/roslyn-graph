using System.Text;
using RoslynToRdf.Core.Emitters;

namespace RoslynToRdf.Tests;

public class EmittersTests
{
    [Fact]
    public void NTriplesEmitter_EscapesSpecialCharacters()
    {
        using var stream = new MemoryStream();
        using var emitter = new NTriplesEmitter(stream, leaveOpen: true);

        emitter.EmitLiteral("http://s", "http://p", "line1\n\"quoted\"");
        emitter.Flush();

        var text = Encoding.UTF8.GetString(stream.ToArray());
        Assert.Contains("line1\\n\\\"quoted\\\"", text);
    }

    [Fact]
    public void TurtleEmitter_WritesPrefixesOnce()
    {
        using var stream = new MemoryStream();
        using var emitter = new TurtleEmitter(stream, leaveOpen: true);

        emitter.AddPrefix("ex", "http://example/");
        emitter.EmitIri("http://s", "http://p", "http://o");
        emitter.EmitIri("http://s", "http://p2", "http://o2");
        emitter.Flush();

        var text = Encoding.UTF8.GetString(stream.ToArray());
        var prefixCount = text.Split("@prefix ex:", StringSplitOptions.None).Length - 1;
        Assert.Equal(1, prefixCount);
    }

    [Fact]
    public void TurtleEmitter_EmitsBooleanAsBareLiteral()
    {
        using var stream = new MemoryStream();
        using var emitter = new TurtleEmitter(stream, leaveOpen: true);

        emitter.EmitBool("http://s", "http://p", true);
        emitter.Flush();

        var text = Encoding.UTF8.GetString(stream.ToArray());
        Assert.Contains("> true .", text);
    }
}
