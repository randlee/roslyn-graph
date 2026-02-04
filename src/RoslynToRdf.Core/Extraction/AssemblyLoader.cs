using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using System.Reflection;
using System.Reflection.Metadata;
using System.Reflection.PortableExecutable;

namespace RoslynToRdf.Core.Extraction;

/// <summary>
/// Loads assemblies and creates Roslyn Compilations for analysis.
/// </summary>
public sealed class AssemblyLoader
{
    private readonly List<string> _additionalReferencePaths = new();
    private readonly List<string> _searchDirectories = new();

    /// <summary>
    /// Add additional assembly reference paths.
    /// </summary>
    public void AddReferencePath(string path)
    {
        if (File.Exists(path))
            _additionalReferencePaths.Add(path);
    }

    /// <summary>
    /// Add directories to search for referenced assemblies.
    /// </summary>
    public void AddSearchDirectory(string directory)
    {
        if (Directory.Exists(directory))
            _searchDirectories.Add(directory);
    }

    /// <summary>
    /// Load an assembly and create a Compilation for it.
    /// </summary>
    public (Compilation compilation, IAssemblySymbol assembly) LoadAssembly(string assemblyPath)
    {
        if (!File.Exists(assemblyPath))
            throw new FileNotFoundException($"Assembly not found: {assemblyPath}");

        var assemblyDirectory = Path.GetDirectoryName(assemblyPath)!;
        _searchDirectories.Add(assemblyDirectory);

        // Add common runtime directories
        var runtimeDir = Path.GetDirectoryName(typeof(object).Assembly.Location);
        if (runtimeDir != null)
            _searchDirectories.Add(runtimeDir);

        // Load the target assembly
        var targetRef = MetadataReference.CreateFromFile(assemblyPath);

        // Collect all references
        var references = new List<MetadataReference> { targetRef };
        var processedAssemblies = new HashSet<string>(StringComparer.OrdinalIgnoreCase)
        {
            Path.GetFileName(assemblyPath)
        };

        // Load direct references from the assembly
        LoadReferences(assemblyPath, references, processedAssemblies);

        // Add additional reference paths
        foreach (var refPath in _additionalReferencePaths)
        {
            if (!processedAssemblies.Contains(Path.GetFileName(refPath)))
            {
                references.Add(MetadataReference.CreateFromFile(refPath));
                processedAssemblies.Add(Path.GetFileName(refPath));
            }
        }

        // Create compilation
        var compilation = CSharpCompilation.Create(
            "Analysis",
            references: references,
            options: new CSharpCompilationOptions(OutputKind.DynamicallyLinkedLibrary));

        // Find the target assembly symbol
        var assemblySymbol = compilation.GetAssemblyOrModuleSymbol(targetRef) as IAssemblySymbol;
        if (assemblySymbol == null)
            throw new InvalidOperationException("Failed to load assembly symbol");

        return (compilation, assemblySymbol);
    }

    /// <summary>
    /// Load referenced assemblies recursively.
    /// </summary>
    private void LoadReferences(
        string assemblyPath, 
        List<MetadataReference> references, 
        HashSet<string> processedAssemblies)
    {
        var referencedAssemblies = GetReferencedAssemblies(assemblyPath);

        foreach (var refName in referencedAssemblies)
        {
            if (processedAssemblies.Contains(refName.Name + ".dll"))
                continue;

            processedAssemblies.Add(refName.Name + ".dll");

            var refPath = ResolveAssemblyPath(refName);
            if (refPath != null && File.Exists(refPath))
            {
                try
                {
                    references.Add(MetadataReference.CreateFromFile(refPath));
                    // Recursively load references
                    LoadReferences(refPath, references, processedAssemblies);
                }
                catch
                {
                    // Skip assemblies that can't be loaded
                }
            }
        }
    }

    /// <summary>
    /// Get the assembly references from an assembly file.
    /// </summary>
    private static IEnumerable<AssemblyName> GetReferencedAssemblies(string assemblyPath)
    {
        using var stream = File.OpenRead(assemblyPath);
        using var peReader = new PEReader(stream);

        if (!peReader.HasMetadata)
            yield break;

        var metadataReader = peReader.GetMetadataReader();

        foreach (var refHandle in metadataReader.AssemblyReferences)
        {
            var reference = metadataReader.GetAssemblyReference(refHandle);
            var name = metadataReader.GetString(reference.Name);
            var version = reference.Version;
            var culture = metadataReader.GetString(reference.Culture);
            var publicKeyToken = metadataReader.GetBlobBytes(reference.PublicKeyOrToken);

            var assemblyName = new AssemblyName
            {
                Name = name,
                Version = version,
                CultureName = string.IsNullOrEmpty(culture) ? null : culture
            };

            if (publicKeyToken.Length > 0)
                assemblyName.SetPublicKeyToken(publicKeyToken);

            yield return assemblyName;
        }
    }

    /// <summary>
    /// Resolve an assembly path from its name.
    /// </summary>
    private string? ResolveAssemblyPath(AssemblyName assemblyName)
    {
        var dllName = assemblyName.Name + ".dll";

        // Search in configured directories
        foreach (var dir in _searchDirectories)
        {
            var path = Path.Combine(dir, dllName);
            if (File.Exists(path))
                return path;
        }

        // Try to resolve from runtime
        try
        {
            var assembly = Assembly.Load(assemblyName);
            if (!string.IsNullOrEmpty(assembly.Location))
                return assembly.Location;
        }
        catch
        {
            // Ignore resolution failures
        }

        return null;
    }
}
