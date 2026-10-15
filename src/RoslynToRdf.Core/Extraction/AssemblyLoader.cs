using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using System.Reflection;
using System.Reflection.Metadata;
using System.Reflection.PortableExecutable;

namespace RoslynToRdf.Core.Extraction;

/// <summary>
/// Describes an assembly reference that could not be loaded during the latest load.
/// </summary>
public sealed record AssemblyReferenceDiagnostic(
    string AssemblyName, string? ReferencePath, string? ReferencedBy, string Reason);

/// <summary>
/// Loads assemblies and creates Roslyn Compilations for analysis.
/// </summary>
public sealed class AssemblyLoader
{
    private readonly List<string> _additionalReferencePaths = new();
    private readonly List<string> _searchDirectories = new();

    /// <summary>
    /// Unresolved or unreadable references from the latest load. Target assembly failures throw instead.
    /// </summary>
    public IReadOnlyList<AssemblyReferenceDiagnostic> ReferenceDiagnostics { get; private set; } =
        Array.Empty<AssemblyReferenceDiagnostic>();

    /// <summary>
    /// Add an assembly reference path. Missing or unreadable files are reported when loading.
    /// </summary>
    public void AddReferencePath(string path) => _additionalReferencePaths.Add(path);

    /// <summary>
    /// Add directories to search for referenced assemblies.
    /// </summary>
    public void AddSearchDirectory(string directory)
    {
        if (Directory.Exists(directory))
            _searchDirectories.Add(directory);
    }

    /// <summary>
    /// Load an assembly and create a Compilation for it, retaining reference failures as diagnostics.
    /// </summary>
    public (Compilation compilation, IAssemblySymbol assembly) LoadAssembly(string assemblyPath)
    {
        ReferenceDiagnostics = Array.Empty<AssemblyReferenceDiagnostic>();
        if (!File.Exists(assemblyPath))
            throw new FileNotFoundException($"Assembly not found: {assemblyPath}");

        var target = ReadAssembly(assemblyPath);
        var loaded = new Dictionary<string, LoadedAssembly>(StringComparer.OrdinalIgnoreCase)
        {
            [target.Identity.Name!] = target
        };
        var searchDirectories = new List<string>(_searchDirectories);
        searchDirectories.Add(Path.GetDirectoryName(target.Path)!);
        var diagnostics = new List<AssemblyReferenceDiagnostic>();

        foreach (var referencePath in _additionalReferencePaths.Distinct(StringComparer.OrdinalIgnoreCase))
        {
            try
            {
                var reference = ReadAssembly(referencePath);
                loaded.TryAdd(reference.Identity.Name!, reference);
                searchDirectories.Add(Path.GetDirectoryName(reference.Path)!);
            }
            catch (Exception exception) when (IsReferenceFailure(exception))
            {
                diagnostics.Add(new AssemblyReferenceDiagnostic(
                    Path.GetFileNameWithoutExtension(referencePath), referencePath, null, exception.Message));
            }
        }

        var runtimeDirectory = Path.GetDirectoryName(typeof(object).Assembly.Location);
        if (runtimeDirectory != null)
            searchDirectories.Add(runtimeDirectory);

        var pending = new Queue<LoadedAssembly>(loaded.Values);
        var unresolved = new Dictionary<string, (AssemblyName Identity, string ReferencedBy, AssemblyReferenceDiagnostic Diagnostic)>(
            StringComparer.OrdinalIgnoreCase);

        while (true)
        {
            while (pending.TryDequeue(out var assembly))
            {
                foreach (var dependency in assembly.Dependencies)
                {
                    if (loaded.ContainsKey(dependency.Name!))
                        continue;

                    var reference = ResolveReference(dependency, assembly.Path, searchDirectories, out var diagnostic);
                    if (reference == null)
                    {
                        unresolved[dependency.Name!] = (dependency, assembly.Path, diagnostic!);
                        continue;
                    }

                    loaded.Add(reference.Identity.Name!, reference);
                    searchDirectories.Add(Path.GetDirectoryName(reference.Path)!);
                    pending.Enqueue(reference);
                    unresolved.Remove(dependency.Name!);
                }
            }

            foreach (var entry in unresolved.ToArray())
            {
                if (loaded.ContainsKey(entry.Key))
                {
                    unresolved.Remove(entry.Key);
                    continue;
                }

                var reference = ResolveReference(entry.Value.Identity, entry.Value.ReferencedBy, searchDirectories, out var diagnostic);
                if (reference == null)
                {
                    unresolved[entry.Key] = (entry.Value.Identity, entry.Value.ReferencedBy, diagnostic!);
                    continue;
                }

                loaded.Add(reference.Identity.Name!, reference);
                searchDirectories.Add(Path.GetDirectoryName(reference.Path)!);
                pending.Enqueue(reference);
                unresolved.Remove(entry.Key);
            }

            if (pending.Count == 0)
                break;
        }

        diagnostics.AddRange(unresolved.Values.Select(entry => entry.Diagnostic));
        ReferenceDiagnostics = diagnostics.AsReadOnly();

        var compilation = CSharpCompilation.Create(
            "Analysis",
            references: loaded.Values.Select(assembly => assembly.Reference),
            options: new CSharpCompilationOptions(
                OutputKind.DynamicallyLinkedLibrary,
                metadataImportOptions: MetadataImportOptions.All));

        var assemblySymbol = compilation.GetAssemblyOrModuleSymbol(target.Reference) as IAssemblySymbol;
        if (assemblySymbol == null)
            throw new InvalidOperationException("Failed to load assembly symbol");

        return (compilation, assemblySymbol);
    }

    private static LoadedAssembly ReadAssembly(string path)
    {
        var fullPath = Path.GetFullPath(path);
        var identity = AssemblyName.GetAssemblyName(fullPath);
        var dependencies = GetReferencedAssemblies(fullPath).ToArray();
        return new LoadedAssembly(fullPath, identity, MetadataReference.CreateFromFile(fullPath), dependencies);
    }

    private static LoadedAssembly? ResolveReference(
        AssemblyName identity, string referencedBy, List<string> searchDirectories,
        out AssemblyReferenceDiagnostic? diagnostic)
    {
        diagnostic = null;
        foreach (var path in ResolveAssemblyPaths(identity, searchDirectories).Distinct(StringComparer.OrdinalIgnoreCase))
        {
            try
            {
                var reference = ReadAssembly(path);
                if (string.Equals(reference.Identity.Name, identity.Name, StringComparison.OrdinalIgnoreCase))
                    return reference;

                diagnostic = new AssemblyReferenceDiagnostic(identity.FullName, path, referencedBy,
                    $"File contains assembly '{reference.Identity.Name}' instead of '{identity.Name}'.");
            }
            catch (Exception exception) when (IsReferenceFailure(exception))
            {
                diagnostic = new AssemblyReferenceDiagnostic(identity.FullName, path, referencedBy, exception.Message);
            }
        }

        diagnostic ??= new AssemblyReferenceDiagnostic(identity.FullName, null, referencedBy, "No matching assembly was found.");
        return null;
    }

    private static bool IsReferenceFailure(Exception exception) =>
        exception is IOException or UnauthorizedAccessException or BadImageFormatException or ArgumentException or NotSupportedException;

    private static IEnumerable<AssemblyName> GetReferencedAssemblies(string assemblyPath)
    {
        using var stream = File.OpenRead(assemblyPath);
        using var peReader = new PEReader(stream);
        var metadataReader = peReader.GetMetadataReader();

        foreach (var refHandle in metadataReader.AssemblyReferences)
        {
            var reference = metadataReader.GetAssemblyReference(refHandle);
            var name = metadataReader.GetString(reference.Name);
            var culture = metadataReader.GetString(reference.Culture);
            var publicKeyToken = metadataReader.GetBlobBytes(reference.PublicKeyOrToken);
            var assemblyName = new AssemblyName
            {
                Name = name,
                Version = reference.Version,
                CultureName = string.IsNullOrEmpty(culture) ? null : culture
            };
            if (publicKeyToken.Length > 0)
                assemblyName.SetPublicKeyToken(publicKeyToken);
            yield return assemblyName;
        }
    }

    private static IEnumerable<string> ResolveAssemblyPaths(AssemblyName assemblyName, List<string> searchDirectories)
    {
        foreach (var directory in searchDirectories.Distinct(StringComparer.OrdinalIgnoreCase))
        {
            var path = Path.Combine(directory, assemblyName.Name + ".dll");
            if (File.Exists(path))
                yield return path;
        }

        string? runtimePath = null;
        try
        {
            var assembly = Assembly.Load(assemblyName);
            if (!string.IsNullOrEmpty(assembly.Location))
                runtimePath = assembly.Location;
        }
        catch (Exception exception) when (IsReferenceFailure(exception))
        {
        }

        if (runtimePath != null)
            yield return runtimePath;
    }

    private sealed record LoadedAssembly(
        string Path, AssemblyName Identity, PortableExecutableReference Reference, AssemblyName[] Dependencies);
}
