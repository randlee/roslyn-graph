using System.Reflection;
using System.Reflection.Metadata;
using System.Reflection.Metadata.Ecma335;
using System.Reflection.PortableExecutable;
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

    public static CSharpCompilation CreateCompilationWithArrayShapes()
    {
        var metadata = new MetadataBuilder();
        metadata.AddModule(0, metadata.GetOrAddString("ArrayShapes.dll"), metadata.GetOrAddGuid(Guid.NewGuid()), default, default);
        metadata.AddAssembly(metadata.GetOrAddString("ArrayShapes"), new Version(1, 0, 0, 0), default, default, default, default);
        var coreName = typeof(object).Assembly.GetName();
        var coreReference = metadata.AddAssemblyReference(metadata.GetOrAddString(coreName.Name!), coreName.Version!,
            default, metadata.GetOrAddBlob(coreName.GetPublicKeyToken()!), default, default);
        var objectReference = metadata.AddTypeReference(coreReference, metadata.GetOrAddString("System"), metadata.GetOrAddString("Object"));
        metadata.AddTypeDefinition(TypeAttributes.NotPublic, default, metadata.GetOrAddString("<Module>"), default,
            MetadataTokens.FieldDefinitionHandle(1), MetadataTokens.MethodDefinitionHandle(1));
        metadata.AddTypeDefinition(TypeAttributes.Public, default, metadata.GetOrAddString("ArrayShapes"), objectReference,
            MetadataTokens.FieldDefinitionHandle(1), MetadataTokens.MethodDefinitionHandle(1));

        var vectorSignature = new BlobBuilder();
        new BlobEncoder(vectorSignature).FieldSignature().SZArray().Int32();
        metadata.AddFieldDefinition(FieldAttributes.Public, metadata.GetOrAddString("Vector"), metadata.GetOrAddBlob(vectorSignature));
        var variableSignature = new BlobBuilder();
        new BlobEncoder(variableSignature).FieldSignature().Array(element => element.Int32(), shape => shape.Shape(1, [], []));
        metadata.AddFieldDefinition(FieldAttributes.Public, metadata.GetOrAddString("Variable"), metadata.GetOrAddBlob(variableSignature));

        var pe = new ManagedPEBuilder(new PEHeaderBuilder(imageCharacteristics: Characteristics.ExecutableImage | Characteristics.Dll),
            new MetadataRootBuilder(metadata), new BlobBuilder());
        var image = new BlobBuilder();
        pe.Serialize(image);
        return CreateCompilation("").AddReferences(MetadataReference.CreateFromImage(image.ToImmutableArray()));
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
