using Microsoft.CodeAnalysis;
using RoslynToRdf.Core.Emitters;
using RoslynToRdf.Core.Extraction;

namespace RoslynToRdf.Tests;

public class PhaseCBodyFailureTests
{
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void BodyWriterFailurePropagatesAndReleasesImage(bool metadata)
    {
        var compilation = TestUtilities.CreateCompilation(
            "public class Target {} public class Root { public object Body() => new Target(); }");
        var (path, directory) = TestUtilities.EmitToTempAssembly(compilation);
        try
        {
            var emitter = new FailingBodyEmitter();
            var extractor = new AssemblyGraphExtractor(emitter);
            if (metadata)
            {
                var reference = MetadataReference.CreateFromFile(path);
                var consumer = TestUtilities.CreateCompilation("").AddReferences(reference);
                var assembly = (IAssemblySymbol)consumer.GetAssemblyOrModuleSymbol(reference)!;
                Assert.Throws<IOException>(() => extractor.Extract(consumer, assembly, path));
            }
            else
                Assert.Throws<IOException>(() => extractor.Extract(compilation, compilation.Assembly));
            Assert.True(emitter.AttemptedBodyWrite);
            using var exclusive = new FileStream(path, FileMode.Open, FileAccess.ReadWrite, FileShare.None);
        }
        finally
        {
            File.Delete(path);
            Directory.Delete(directory);
        }
    }

    private sealed class FailingBodyEmitter : ITriplesEmitter
    {
        private readonly TestEmitter _inner = new();
        public bool AttemptedBodyWrite { get; private set; }
        public long TripleCount => _inner.TripleCount;
        public void EmitIri(string subject, string predicate, string objectIri)
        {
            if (predicate.EndsWith("/usesType", StringComparison.Ordinal))
            {
                AttemptedBodyWrite = true;
                throw new IOException("Body output failed.");
            }
            _inner.EmitIri(subject, predicate, objectIri);
        }
        public void EmitLiteral(string subject, string predicate, string value) => _inner.EmitLiteral(subject, predicate, value);
        public void EmitTypedLiteral(string subject, string predicate, string value, string datatype) => _inner.EmitTypedLiteral(subject, predicate, value, datatype);
        public void EmitBool(string subject, string predicate, bool value) => _inner.EmitBool(subject, predicate, value);
        public void EmitInt(string subject, string predicate, int value) => _inner.EmitInt(subject, predicate, value);
        public void EmitLong(string subject, string predicate, long value) => _inner.EmitLong(subject, predicate, value);
        public void AddPrefix(string prefix, string iri) => _inner.AddPrefix(prefix, iri);
        public void Flush() => _inner.Flush();
        public void Dispose() => _inner.Dispose();
    }
}
