using Microsoft.CodeAnalysis;
using RoslynToRdf.Core.Extraction;

namespace RoslynToRdf.Tests;

public class AssemblyLoaderTests
{
    [Fact]
    public void LoadAssembly_LoadsCompilationAndAssemblySymbol()
    {
        var source = @"
namespace Sample;
public class C { public int X => 1; }
";

        var compilation = TestUtilities.CreateCompilation(source, "LoaderTest");
        var (assemblyPath, _) = TestUtilities.EmitToTempAssembly(compilation);

        var loader = new AssemblyLoader();
        var (loadedCompilation, assemblySymbol) = loader.LoadAssembly(assemblyPath);

        Assert.NotNull(loadedCompilation);
        Assert.NotNull(assemblySymbol);
        Assert.Equal("LoaderTest", assemblySymbol.Name);

        var type = loadedCompilation.GetTypeByMetadataName("Sample.C");
        Assert.NotNull(type);
    }
}
