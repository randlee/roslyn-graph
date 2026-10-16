using System.Collections.Immutable;
using Microsoft.CodeAnalysis;

namespace RoslynToRdf.Tests;

internal sealed class AssemblyReferenceFixture : IDisposable
{
    public string DirectoryPath { get; } = Path.Combine(Path.GetTempPath(), "roslyn2rdf-tests", Guid.NewGuid().ToString("N"));
    public string TargetPath { get; }
    public string DependencyPath { get; }
    public string TransitivePath { get; }
    public string DependencyName => Path.GetFileNameWithoutExtension(DependencyPath);
    public string TransitiveName => Path.GetFileNameWithoutExtension(TransitivePath);

    public AssemblyReferenceFixture(bool referenceTransitiveDirectly = false, bool strongNamedDependency = false)
    {
        var suffix = Guid.NewGuid().ToString("N");
        var dependencyDirectory = Path.Combine(DirectoryPath, "dependencies");
        var targetDirectory = Path.Combine(DirectoryPath, "target");
        Directory.CreateDirectory(dependencyDirectory);
        Directory.CreateDirectory(targetDirectory);
        TransitivePath = Path.Combine(dependencyDirectory, "Transitive_" + suffix + ".dll");
        DependencyPath = Path.Combine(dependencyDirectory, "Dependency_" + suffix + ".dll");
        TargetPath = Path.Combine(targetDirectory, "Target_" + suffix + ".dll");

        Emit("namespace ReferenceFixture; public class Root { }", TransitivePath, []);
        ReplaceDependency("2.0.0.0", publicSign: strongNamedDependency);
        var targetSource = referenceTransitiveDirectly
            ? "namespace ReferenceFixture; public class Target : Base { public Root? Value { get; set; } }"
            : "namespace ReferenceFixture; public class Target : Base { }";
        Emit(targetSource, TargetPath, [DependencyPath, TransitivePath]);
    }

    public void ReplaceDependency(string version, string culture = "", bool publicSign = false)
    {
        var source = $$"""
            [assembly: System.Reflection.AssemblyVersion("{{version}}")]
            [assembly: System.Reflection.AssemblyCulture("{{culture}}")]
            namespace ReferenceFixture;
            public class Base : Root { }
            """;
        Emit(source, DependencyPath, [TransitivePath], publicSign);
    }

    private static void Emit(string source, string path, string[] references, bool publicSign = false)
    {
        var compilation = TestUtilities.CreateCompilation(source, Path.GetFileNameWithoutExtension(path))
            .AddReferences(references.Select(reference => MetadataReference.CreateFromFile(reference)));
        if (publicSign)
        {
            compilation = compilation.WithOptions(compilation.Options
                .WithCryptoPublicKey(typeof(object).Assembly.GetName().GetPublicKey()!.ToImmutableArray())
                .WithPublicSign(true));
        }
        var result = compilation.Emit(path);
        if (!result.Success)
            throw new InvalidOperationException(string.Join(Environment.NewLine, result.Diagnostics));
    }

    public void Dispose() => Directory.Delete(DirectoryPath, recursive: true);
}
