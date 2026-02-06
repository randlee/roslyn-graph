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

    #region NTriplesEmitter Tests

    [Fact]
    public void NTriplesEmitter_EmptyString_HandlesCorrectly()
    {
        using var stream = new MemoryStream();
        using var emitter = new NTriplesEmitter(stream, leaveOpen: true);

        emitter.EmitLiteral("http://s", "http://p", "");
        emitter.Flush();

        var text = Encoding.UTF8.GetString(stream.ToArray());
        Assert.Contains("<http://s> <http://p> \"\" .", text);
    }

    [Fact]
    public void NTriplesEmitter_AllEscapeSequences_Escaped()
    {
        using var stream = new MemoryStream();
        using var emitter = new NTriplesEmitter(stream, leaveOpen: true);

        emitter.EmitLiteral("http://s", "http://p", "\\back\n\"quote\"\rtab\t");
        emitter.Flush();

        var text = Encoding.UTF8.GetString(stream.ToArray());
        Assert.Contains("\\\\back\\n\\\"quote\\\"\\rtab\\t", text);
    }

    [Fact]
    public void NTriplesEmitter_ControlCharacters_EscapedAsUnicode()
    {
        using var stream = new MemoryStream();
        using var emitter = new NTriplesEmitter(stream, leaveOpen: true);

        emitter.EmitLiteral("http://s", "http://p", "\u0001\u0002\u001F");
        emitter.Flush();

        var text = Encoding.UTF8.GetString(stream.ToArray());
        Assert.Contains("\\u0001\\u0002\\u001F", text);
    }

    [Fact]
    public void NTriplesEmitter_UnicodeCharacters_PreservedCorrectly()
    {
        using var stream = new MemoryStream();
        using var emitter = new NTriplesEmitter(stream, leaveOpen: true);

        emitter.EmitLiteral("http://s", "http://p", "Hello 世界 🌍");
        emitter.Flush();

        var text = Encoding.UTF8.GetString(stream.ToArray());
        Assert.Contains("Hello 世界 🌍", text);
    }

    [Fact]
    public void NTriplesEmitter_RTLText_PreservedCorrectly()
    {
        using var stream = new MemoryStream();
        using var emitter = new NTriplesEmitter(stream, leaveOpen: true);

        emitter.EmitLiteral("http://s", "http://p", "مرحبا שלום");
        emitter.Flush();

        var text = Encoding.UTF8.GetString(stream.ToArray());
        Assert.Contains("مرحبا שלום", text);
    }

    [Fact]
    public void NTriplesEmitter_VeryLongURI_HandledCorrectly()
    {
        using var stream = new MemoryStream();
        using var emitter = new NTriplesEmitter(stream, leaveOpen: true);

        var longUri = "http://example.com/" + new string('a', 10000);
        emitter.EmitIri("http://s", "http://p", longUri);
        emitter.Flush();

        var text = Encoding.UTF8.GetString(stream.ToArray());
        Assert.Contains(longUri, text);
    }

    [Fact]
    public void NTriplesEmitter_VeryLongLiteral_HandledCorrectly()
    {
        using var stream = new MemoryStream();
        using var emitter = new NTriplesEmitter(stream, leaveOpen: true);

        var longText = new string('x', 50000);
        emitter.EmitLiteral("http://s", "http://p", longText);
        emitter.Flush();

        var text = Encoding.UTF8.GetString(stream.ToArray());
        Assert.Contains(longText, text);
    }

    [Fact]
    public void NTriplesEmitter_NestedQuotes_EscapedCorrectly()
    {
        using var stream = new MemoryStream();
        using var emitter = new NTriplesEmitter(stream, leaveOpen: true);

        emitter.EmitLiteral("http://s", "http://p", "\"outer \"inner\" outer\"");
        emitter.Flush();

        var text = Encoding.UTF8.GetString(stream.ToArray());
        Assert.Contains("\\\"outer \\\"inner\\\" outer\\\"", text);
    }

    [Fact]
    public void NTriplesEmitter_MultipleBackslashes_EscapedCorrectly()
    {
        using var stream = new MemoryStream();
        using var emitter = new NTriplesEmitter(stream, leaveOpen: true);

        emitter.EmitLiteral("http://s", "http://p", "\\\\\\");
        emitter.Flush();

        var text = Encoding.UTF8.GetString(stream.ToArray());
        Assert.Contains("\\\\\\\\\\\\", text);
    }

    [Fact]
    public void NTriplesEmitter_TypedLiteral_FormatsCorrectly()
    {
        using var stream = new MemoryStream();
        using var emitter = new NTriplesEmitter(stream, leaveOpen: true);

        emitter.EmitTypedLiteral("http://s", "http://p", "42", "http://www.w3.org/2001/XMLSchema#integer");
        emitter.Flush();

        var text = Encoding.UTF8.GetString(stream.ToArray());
        Assert.Contains("\"42\"^^<http://www.w3.org/2001/XMLSchema#integer>", text);
    }

    [Fact]
    public void NTriplesEmitter_BoolTrue_FormatsAsTypedLiteral()
    {
        using var stream = new MemoryStream();
        using var emitter = new NTriplesEmitter(stream, leaveOpen: true);

        emitter.EmitBool("http://s", "http://p", true);
        emitter.Flush();

        var text = Encoding.UTF8.GetString(stream.ToArray());
        Assert.Contains("\"true\"^^<http://www.w3.org/2001/XMLSchema#boolean>", text);
    }

    [Fact]
    public void NTriplesEmitter_BoolFalse_FormatsAsTypedLiteral()
    {
        using var stream = new MemoryStream();
        using var emitter = new NTriplesEmitter(stream, leaveOpen: true);

        emitter.EmitBool("http://s", "http://p", false);
        emitter.Flush();

        var text = Encoding.UTF8.GetString(stream.ToArray());
        Assert.Contains("\"false\"^^<http://www.w3.org/2001/XMLSchema#boolean>", text);
    }

    [Fact]
    public void NTriplesEmitter_IntegerValues_FormatsCorrectly()
    {
        using var stream = new MemoryStream();
        using var emitter = new NTriplesEmitter(stream, leaveOpen: true);

        emitter.EmitInt("http://s", "http://p", 0);
        emitter.EmitInt("http://s", "http://p", -42);
        emitter.EmitInt("http://s", "http://p", int.MaxValue);
        emitter.EmitInt("http://s", "http://p", int.MinValue);
        emitter.Flush();

        var text = Encoding.UTF8.GetString(stream.ToArray());
        Assert.Contains("\"0\"^^<http://www.w3.org/2001/XMLSchema#integer>", text);
        Assert.Contains("\"-42\"^^<http://www.w3.org/2001/XMLSchema#integer>", text);
        Assert.Contains($"\"{int.MaxValue}\"^^<http://www.w3.org/2001/XMLSchema#integer>", text);
        Assert.Contains($"\"{int.MinValue}\"^^<http://www.w3.org/2001/XMLSchema#integer>", text);
    }

    [Fact]
    public void NTriplesEmitter_LongValues_FormatsCorrectly()
    {
        using var stream = new MemoryStream();
        using var emitter = new NTriplesEmitter(stream, leaveOpen: true);

        emitter.EmitLong("http://s", "http://p", long.MaxValue);
        emitter.EmitLong("http://s", "http://p", long.MinValue);
        emitter.Flush();

        var text = Encoding.UTF8.GetString(stream.ToArray());
        Assert.Contains($"\"{long.MaxValue}\"^^<http://www.w3.org/2001/XMLSchema#long>", text);
        Assert.Contains($"\"{long.MinValue}\"^^<http://www.w3.org/2001/XMLSchema#long>", text);
    }

    [Fact]
    public void NTriplesEmitter_AddPrefix_WritesComment()
    {
        using var stream = new MemoryStream();
        using var emitter = new NTriplesEmitter(stream, leaveOpen: true);

        emitter.AddPrefix("ex", "http://example.com/");
        emitter.Flush();

        var text = Encoding.UTF8.GetString(stream.ToArray());
        Assert.Contains("# @prefix ex: <http://example.com/> .", text);
    }

    [Fact]
    public void NTriplesEmitter_TripleCount_TracksCorrectly()
    {
        using var stream = new MemoryStream();
        using var emitter = new NTriplesEmitter(stream, leaveOpen: true);

        Assert.Equal(0, emitter.TripleCount);

        emitter.EmitIri("http://s", "http://p", "http://o");
        Assert.Equal(1, emitter.TripleCount);

        emitter.EmitLiteral("http://s", "http://p", "value");
        Assert.Equal(2, emitter.TripleCount);

        emitter.EmitTypedLiteral("http://s", "http://p", "value", "http://type");
        Assert.Equal(3, emitter.TripleCount);

        emitter.EmitBool("http://s", "http://p", true);
        Assert.Equal(4, emitter.TripleCount);

        emitter.EmitInt("http://s", "http://p", 42);
        Assert.Equal(5, emitter.TripleCount);

        emitter.EmitLong("http://s", "http://p", 42L);
        Assert.Equal(6, emitter.TripleCount);
    }

    [Fact]
    public void NTriplesEmitter_MixedContent_EndsWithNewline()
    {
        using var stream = new MemoryStream();
        using var emitter = new NTriplesEmitter(stream, leaveOpen: true);

        emitter.EmitIri("http://s", "http://p", "http://o");
        emitter.Flush();

        var text = Encoding.UTF8.GetString(stream.ToArray());
        Assert.EndsWith(".\n", text.Replace("\r\n", "\n"));
    }

    #endregion

    #region TurtleEmitter Tests

    [Fact]
    public void TurtleEmitter_EmptyString_HandlesCorrectly()
    {
        using var stream = new MemoryStream();
        using var emitter = new TurtleEmitter(stream, leaveOpen: true);

        emitter.EmitLiteral("http://s", "http://p", "");
        emitter.Flush();

        var text = Encoding.UTF8.GetString(stream.ToArray());
        Assert.Contains("<http://s> <http://p> \"\" .", text);
    }

    [Fact]
    public void TurtleEmitter_AllEscapeSequences_Escaped()
    {
        using var stream = new MemoryStream();
        using var emitter = new TurtleEmitter(stream, leaveOpen: true);

        emitter.EmitLiteral("http://s", "http://p", "\\back\n\"quote\"\rtab\t");
        emitter.Flush();

        var text = Encoding.UTF8.GetString(stream.ToArray());
        Assert.Contains("\\\\back\\n\\\"quote\\\"\\rtab\\t", text);
    }

    [Fact]
    public void TurtleEmitter_ControlCharacters_EscapedAsUnicode()
    {
        using var stream = new MemoryStream();
        using var emitter = new TurtleEmitter(stream, leaveOpen: true);

        emitter.EmitLiteral("http://s", "http://p", "\u0001\u0002\u001F");
        emitter.Flush();

        var text = Encoding.UTF8.GetString(stream.ToArray());
        Assert.Contains("\\u0001\\u0002\\u001F", text);
    }

    [Fact]
    public void TurtleEmitter_UnicodeCharacters_PreservedCorrectly()
    {
        using var stream = new MemoryStream();
        using var emitter = new TurtleEmitter(stream, leaveOpen: true);

        emitter.EmitLiteral("http://s", "http://p", "Hello 世界 🌍");
        emitter.Flush();

        var text = Encoding.UTF8.GetString(stream.ToArray());
        Assert.Contains("Hello 世界 🌍", text);
    }

    [Fact]
    public void TurtleEmitter_RTLText_PreservedCorrectly()
    {
        using var stream = new MemoryStream();
        using var emitter = new TurtleEmitter(stream, leaveOpen: true);

        emitter.EmitLiteral("http://s", "http://p", "مرحبا שלום");
        emitter.Flush();

        var text = Encoding.UTF8.GetString(stream.ToArray());
        Assert.Contains("مرحبا שלום", text);
    }

    [Fact]
    public void TurtleEmitter_VeryLongURI_HandledCorrectly()
    {
        using var stream = new MemoryStream();
        using var emitter = new TurtleEmitter(stream, leaveOpen: true);

        var longUri = "http://example.com/" + new string('a', 10000);
        emitter.EmitIri("http://s", "http://p", longUri);
        emitter.Flush();

        var text = Encoding.UTF8.GetString(stream.ToArray());
        Assert.Contains(longUri, text);
    }

    [Fact]
    public void TurtleEmitter_VeryLongLiteral_HandledCorrectly()
    {
        using var stream = new MemoryStream();
        using var emitter = new TurtleEmitter(stream, leaveOpen: true);

        var longText = new string('x', 50000);
        emitter.EmitLiteral("http://s", "http://p", longText);
        emitter.Flush();

        var text = Encoding.UTF8.GetString(stream.ToArray());
        Assert.Contains(longText, text);
    }

    [Fact]
    public void TurtleEmitter_NestedQuotes_EscapedCorrectly()
    {
        using var stream = new MemoryStream();
        using var emitter = new TurtleEmitter(stream, leaveOpen: true);

        emitter.EmitLiteral("http://s", "http://p", "\"outer \"inner\" outer\"");
        emitter.Flush();

        var text = Encoding.UTF8.GetString(stream.ToArray());
        Assert.Contains("\\\"outer \\\"inner\\\" outer\\\"", text);
    }

    [Fact]
    public void TurtleEmitter_MultipleBackslashes_EscapedCorrectly()
    {
        using var stream = new MemoryStream();
        using var emitter = new TurtleEmitter(stream, leaveOpen: true);

        emitter.EmitLiteral("http://s", "http://p", "\\\\\\");
        emitter.Flush();

        var text = Encoding.UTF8.GetString(stream.ToArray());
        Assert.Contains("\\\\\\\\\\\\", text);
    }

    [Fact]
    public void TurtleEmitter_TypedLiteral_FormatsCorrectly()
    {
        using var stream = new MemoryStream();
        using var emitter = new TurtleEmitter(stream, leaveOpen: true);

        emitter.EmitTypedLiteral("http://s", "http://p", "42", "http://www.w3.org/2001/XMLSchema#integer");
        emitter.Flush();

        var text = Encoding.UTF8.GetString(stream.ToArray());
        Assert.Contains("\"42\"^^<http://www.w3.org/2001/XMLSchema#integer>", text);
    }

    [Fact]
    public void TurtleEmitter_BoolFalse_FormatsAsBareLiteral()
    {
        using var stream = new MemoryStream();
        using var emitter = new TurtleEmitter(stream, leaveOpen: true);

        emitter.EmitBool("http://s", "http://p", false);
        emitter.Flush();

        var text = Encoding.UTF8.GetString(stream.ToArray());
        Assert.Contains("> false .", text);
    }

    [Fact]
    public void TurtleEmitter_IntegerValues_FormatsAsBareLiterals()
    {
        using var stream = new MemoryStream();
        using var emitter = new TurtleEmitter(stream, leaveOpen: true);

        emitter.EmitInt("http://s", "http://p", 0);
        emitter.EmitInt("http://s", "http://p2", -42);
        emitter.EmitInt("http://s", "http://p3", int.MaxValue);
        emitter.EmitInt("http://s", "http://p4", int.MinValue);
        emitter.Flush();

        var text = Encoding.UTF8.GetString(stream.ToArray());
        Assert.Contains("> 0 .", text);
        Assert.Contains("> -42 .", text);
        Assert.Contains($"> {int.MaxValue} .", text);
        Assert.Contains($"> {int.MinValue} .", text);
    }

    [Fact]
    public void TurtleEmitter_LongValues_FormatsAsTypedLiterals()
    {
        using var stream = new MemoryStream();
        using var emitter = new TurtleEmitter(stream, leaveOpen: true);

        emitter.EmitLong("http://s", "http://p", long.MaxValue);
        emitter.EmitLong("http://s", "http://p2", long.MinValue);
        emitter.Flush();

        var text = Encoding.UTF8.GetString(stream.ToArray());
        Assert.Contains($"\"{long.MaxValue}\"^^<http://www.w3.org/2001/XMLSchema#long>", text);
        Assert.Contains($"\"{long.MinValue}\"^^<http://www.w3.org/2001/XMLSchema#long>", text);
    }

    [Fact]
    public void TurtleEmitter_MultiplePrefixes_AllWrittenOnce()
    {
        using var stream = new MemoryStream();
        using var emitter = new TurtleEmitter(stream, leaveOpen: true);

        emitter.AddPrefix("ex", "http://example.com/");
        emitter.AddPrefix("rdf", "http://www.w3.org/1999/02/22-rdf-syntax-ns#");
        emitter.AddPrefix("rdfs", "http://www.w3.org/2000/01/rdf-schema#");
        emitter.EmitIri("http://s", "http://p", "http://o");
        emitter.Flush();

        var text = Encoding.UTF8.GetString(stream.ToArray());
        Assert.Contains("@prefix ex:", text);
        Assert.Contains("@prefix rdf:", text);
        Assert.Contains("@prefix rdfs:", text);

        // Verify each prefix appears exactly once
        var exCount = text.Split("@prefix ex:", StringSplitOptions.None).Length - 1;
        var rdfCount = text.Split("@prefix rdf:", StringSplitOptions.None).Length - 1;
        var rdfsCount = text.Split("@prefix rdfs:", StringSplitOptions.None).Length - 1;

        Assert.Equal(1, exCount);
        Assert.Equal(1, rdfCount);
        Assert.Equal(1, rdfsCount);
    }

    [Fact]
    public void TurtleEmitter_PrefixesAddedAfterEmit_NotWritten()
    {
        using var stream = new MemoryStream();
        using var emitter = new TurtleEmitter(stream, leaveOpen: true);

        emitter.EmitIri("http://s", "http://p", "http://o");
        emitter.AddPrefix("ex", "http://example.com/");
        emitter.Flush();

        var text = Encoding.UTF8.GetString(stream.ToArray());
        Assert.DoesNotContain("@prefix", text);
    }

    [Fact]
    public void TurtleEmitter_NoPrefixes_NoBlankLineAtStart()
    {
        using var stream = new MemoryStream();
        using var emitter = new TurtleEmitter(stream, leaveOpen: true);

        emitter.EmitIri("http://s", "http://p", "http://o");
        emitter.Flush();

        var text = Encoding.UTF8.GetString(stream.ToArray());
        Assert.DoesNotContain("@prefix", text);
        Assert.StartsWith("<http://s>", text);
    }

    [Fact]
    public void TurtleEmitter_WithPrefixes_BlankLineSeparatesPrefixesFromTriples()
    {
        using var stream = new MemoryStream();
        using var emitter = new TurtleEmitter(stream, leaveOpen: true);

        emitter.AddPrefix("ex", "http://example.com/");
        emitter.EmitIri("http://s", "http://p", "http://o");
        emitter.Flush();

        var text = Encoding.UTF8.GetString(stream.ToArray());
        var normalized = text.Replace("\r\n", "\n");
        Assert.Contains(".\n\n<http://s>", normalized);
    }

    [Fact]
    public void TurtleEmitter_TripleCount_TracksCorrectly()
    {
        using var stream = new MemoryStream();
        using var emitter = new TurtleEmitter(stream, leaveOpen: true);

        Assert.Equal(0, emitter.TripleCount);

        emitter.EmitIri("http://s", "http://p", "http://o");
        Assert.Equal(1, emitter.TripleCount);

        emitter.EmitLiteral("http://s", "http://p", "value");
        Assert.Equal(2, emitter.TripleCount);

        emitter.EmitTypedLiteral("http://s", "http://p", "value", "http://type");
        Assert.Equal(3, emitter.TripleCount);

        emitter.EmitBool("http://s", "http://p", true);
        Assert.Equal(4, emitter.TripleCount);

        emitter.EmitInt("http://s", "http://p", 42);
        Assert.Equal(5, emitter.TripleCount);

        emitter.EmitLong("http://s", "http://p", 42L);
        Assert.Equal(6, emitter.TripleCount);
    }

    [Fact]
    public void TurtleEmitter_MixedContent_EndsWithNewline()
    {
        using var stream = new MemoryStream();
        using var emitter = new TurtleEmitter(stream, leaveOpen: true);

        emitter.EmitIri("http://s", "http://p", "http://o");
        emitter.Flush();

        var text = Encoding.UTF8.GetString(stream.ToArray());
        Assert.EndsWith(".\n", text.Replace("\r\n", "\n"));
    }

    [Fact]
    public void TurtleEmitter_OverwriteSamePrefix_UsesLatestValue()
    {
        using var stream = new MemoryStream();
        using var emitter = new TurtleEmitter(stream, leaveOpen: true);

        emitter.AddPrefix("ex", "http://example.com/");
        emitter.AddPrefix("ex", "http://example.org/");
        emitter.EmitIri("http://s", "http://p", "http://o");
        emitter.Flush();

        var text = Encoding.UTF8.GetString(stream.ToArray());
        Assert.Contains("@prefix ex: <http://example.org/>", text);
        Assert.DoesNotContain("http://example.com/", text);
    }

    #endregion

    #region Cross-Emitter Comparison Tests

    [Fact]
    public void BothEmitters_EmitSameTriples_SameTripleCount()
    {
        using var ntStream = new MemoryStream();
        using var ntEmitter = new NTriplesEmitter(ntStream, leaveOpen: true);

        using var ttlStream = new MemoryStream();
        using var ttlEmitter = new TurtleEmitter(ttlStream, leaveOpen: true);

        // Emit same triples to both
        ntEmitter.EmitIri("http://s", "http://p", "http://o");
        ttlEmitter.EmitIri("http://s", "http://p", "http://o");

        ntEmitter.EmitLiteral("http://s", "http://p", "value");
        ttlEmitter.EmitLiteral("http://s", "http://p", "value");

        ntEmitter.EmitBool("http://s", "http://p", true);
        ttlEmitter.EmitBool("http://s", "http://p", true);

        Assert.Equal(ntEmitter.TripleCount, ttlEmitter.TripleCount);
    }

    [Fact]
    public void BothEmitters_EscapeIdentically_SpecialCharacters()
    {
        using var ntStream = new MemoryStream();
        using var ntEmitter = new NTriplesEmitter(ntStream, leaveOpen: true);

        using var ttlStream = new MemoryStream();
        using var ttlEmitter = new TurtleEmitter(ttlStream, leaveOpen: true);

        var testString = "test\n\"quote\"\ttab\\back\rreturn";

        ntEmitter.EmitLiteral("http://s", "http://p", testString);
        ttlEmitter.EmitLiteral("http://s", "http://p", testString);

        ntEmitter.Flush();
        ttlEmitter.Flush();

        var ntText = Encoding.UTF8.GetString(ntStream.ToArray());
        var ttlText = Encoding.UTF8.GetString(ttlStream.ToArray());

        // Both should have identical escaping
        Assert.Contains("test\\n\\\"quote\\\"\\ttab\\\\back\\rreturn", ntText);
        Assert.Contains("test\\n\\\"quote\\\"\\ttab\\\\back\\rreturn", ttlText);
    }

    [Fact]
    public void BothEmitters_HandleUnicode_Identically()
    {
        using var ntStream = new MemoryStream();
        using var ntEmitter = new NTriplesEmitter(ntStream, leaveOpen: true);

        using var ttlStream = new MemoryStream();
        using var ttlEmitter = new TurtleEmitter(ttlStream, leaveOpen: true);

        var unicodeString = "Emoji: 🎉 CJK: 你好 Math: ∑∫√";

        ntEmitter.EmitLiteral("http://s", "http://p", unicodeString);
        ttlEmitter.EmitLiteral("http://s", "http://p", unicodeString);

        ntEmitter.Flush();
        ttlEmitter.Flush();

        var ntText = Encoding.UTF8.GetString(ntStream.ToArray());
        var ttlText = Encoding.UTF8.GetString(ttlStream.ToArray());

        Assert.Contains(unicodeString, ntText);
        Assert.Contains(unicodeString, ttlText);
    }

    #endregion
}
