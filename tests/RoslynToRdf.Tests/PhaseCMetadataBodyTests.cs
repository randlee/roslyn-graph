using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using RoslynToRdf.Core.Extraction;
using RoslynToRdf.Core.Model;

namespace RoslynToRdf.Tests;

public class PhaseCMetadataBodyTests
{
    [Theory]
    [InlineData(OptimizationLevel.Debug)]
    [InlineData(OptimizationLevel.Release)]
    public void MetadataBodies_KeepLexicalOwnersAndDoNotExpandOrdinaryCallees(OptimizationLevel optimization)
    {
        const string source = """
            using System;
            using System.Collections.Generic;
            using System.Threading.Tasks;
            public class DirectOnly {}
            public class LambdaOnly {}
            public class OtherLambdaOnly {}
            public class IteratorOnly {}
            public class AsyncOnly {}
            public class PrivateOnly {}
            public class CalleeOnly {}
            public class Decoy {}
            public class Inventory {
              public object Direct() => new DirectOnly();
              public Func<object> Lambda() => () => new LambdaOnly();
              public Func<object> OtherLambda() => () => new OtherLambdaOnly();
              public IEnumerable<object> Iterator() { yield return new IteratorOnly(); }
              public async Task<object> Async() { await Task.Yield(); return new AsyncOnly(); }
              private object Uncalled() => new PrivateOnly();
              public object Caller() => Callee();
              public object Callee() => new CalleeOnly();
            }
            """;
        var sourceCompilation = TestUtilities.CreateCompilation(source, "BodyInventory")
            .WithOptions(TestUtilities.CreateCompilation("").Options.WithOptimizationLevel(optimization));
        var (path, directory) = TestUtilities.EmitToTempAssembly(sourceCompilation);
        try
        {
            var reference = MetadataReference.CreateFromFile(path);
            var compilation = TestUtilities.CreateCompilation("")
                .WithOptions(TestUtilities.CreateCompilation("").Options.WithMetadataImportOptions(MetadataImportOptions.All))
                .AddReferences(reference);
            var assembly = (IAssemblySymbol)compilation.GetAssemblyOrModuleSymbol(reference)!;
            var emitter = new TestEmitter();
            var options = new ExtractionOptions { IncludePrivate = true, IncludeInternal = true };
            new AssemblyGraphExtractor(emitter, options).Extract(compilation, assembly, peImagePath: path);
            var minter = new IriMinter(options.BaseUri);
            var root = assembly.GetTypeByMetadataName("Inventory")!;
            foreach (var pair in new[] {
                ("Direct", "DirectOnly"), ("Lambda", "LambdaOnly"), ("OtherLambda", "OtherLambdaOnly"),
                ("Iterator", "IteratorOnly"), ("Async", "AsyncOnly"), ("Uncalled", "PrivateOnly") })
            {
                var owner = minter.Member(root.GetMembers(pair.Item1).OfType<IMethodSymbol>().Single());
                var target = minter.Type(assembly.GetTypeByMetadataName(pair.Item2)!);
                Assert.Contains(emitter.Triples, triple => triple.Subject == owner
                    && triple.Predicate == minter.OntologyPrefix + "usesType" && triple.Object == target);
            }
            foreach (var pair in new[] { ("Lambda", "OtherLambdaOnly"), ("OtherLambda", "LambdaOnly"),
                ("Caller", "CalleeOnly"), ("Direct", "Decoy") })
            {
                var owner = minter.Member(root.GetMembers(pair.Item1).OfType<IMethodSymbol>().Single());
                var target = minter.Type(assembly.GetTypeByMetadataName(pair.Item2)!);
                Assert.DoesNotContain(emitter.Triples, triple => triple.Subject == owner
                    && triple.Predicate == minter.OntologyPrefix + "usesType" && triple.Object == target);
            }
        }
        finally
        {
            Directory.Delete(directory, true);
        }
    }
}
