using System.Reflection;
using System.Text;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;

namespace RoslynToRdf.Tests;

internal static class TestUtilities
{
    public static CSharpCompilation CreateCompilation(
        string source,
        string assemblyName = "TestAssembly",
        bool allowUnsafe = false)
    {
        var parseOptions = new CSharpParseOptions(documentationMode: DocumentationMode.Diagnose);
        var tree = CSharpSyntaxTree.ParseText(source, parseOptions);

        return CSharpCompilation.Create(
            assemblyName,
            new[] { tree },
            GetDefaultReferences(),
            new CSharpCompilationOptions(OutputKind.DynamicallyLinkedLibrary, allowUnsafe: allowUnsafe));
    }

    public static (string assemblyPath, string directory) EmitToTempAssembly(CSharpCompilation compilation)
    {
        var dir = Path.Combine(Path.GetTempPath(), "roslyn2rdf-tests", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(dir);
        var assemblyPath = Path.Combine(dir, compilation.AssemblyName + ".dll");

        var emitResult = compilation.Emit(assemblyPath);
        if (!emitResult.Success)
        {
            var sb = new StringBuilder();
            foreach (var diag in emitResult.Diagnostics)
                sb.AppendLine(diag.ToString());
            throw new InvalidOperationException(sb.ToString());
        }

        return (assemblyPath, dir);
    }

    private static IEnumerable<MetadataReference> GetDefaultReferences()
    {
        // Use core assemblies that are available in the runtime
        var assemblies = new[]
        {
            typeof(object).Assembly,
            typeof(Console).Assembly,
            typeof(Enumerable).Assembly,
            typeof(Assembly).Assembly
        };

        foreach (var asm in assemblies.Distinct())
        {
            if (!string.IsNullOrEmpty(asm.Location))
                yield return MetadataReference.CreateFromFile(asm.Location);
        }
    }
}
