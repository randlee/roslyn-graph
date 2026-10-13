using System.Text;
using RoslynToRdf.Cli;

namespace RoslynToRdf.Tests;

public class CliIntegrationTests
{
    [Fact]
    public async Task Cli_TurtleOutput_WritesFileWithPrefixes()
    {
        var source = @"
namespace Sample;
public class C { public int X => 1; }
";

        var compilation = TestUtilities.CreateCompilation(source, "CliTurtle");
        var (assemblyPath, dir) = TestUtilities.EmitToTempAssembly(compilation);

        var outputPath = Path.Combine(dir, "out.ttl");
        var args = new[]
        {
            assemblyPath,
            "-o", outputPath,
            "-f", "turtle",
            "-b", "http://test.example/",
            "-q"
        };

        var result = await RunCliAsync(args);

        Assert.Equal(0, result.ExitCode);
        Assert.True(File.Exists(outputPath));

        var text = await File.ReadAllTextAsync(outputPath);
        Assert.Contains("@prefix dt: <http://test.example/ontology/>", text);
        Assert.Contains("http://test.example/assembly/", text);
        Assert.True(string.IsNullOrWhiteSpace(result.Stdout));
    }

    [Fact]
    public async Task Cli_NTriplesOutput_WritesFile()
    {
        var source = @"
namespace Sample;
public class C { public int X => 1; }
";

        var compilation = TestUtilities.CreateCompilation(source, "CliNTriples");
        var (assemblyPath, dir) = TestUtilities.EmitToTempAssembly(compilation);

        var outputPath = Path.Combine(dir, "out.nt");
        var args = new[]
        {
            assemblyPath,
            "-o", outputPath,
            "-f", "ntriples",
            "-b", "http://test.example/",
            "-q"
        };

        var result = await RunCliAsync(args);

        Assert.Equal(0, result.ExitCode);
        Assert.True(File.Exists(outputPath));

        var text = await File.ReadAllTextAsync(outputPath);
        Assert.Contains("<http://test.example/assembly/", text);
    }

    [Fact]
    public async Task Cli_MultipleAssemblies_WritesOneCombinedGraph()
    {
        var firstCompilation = TestUtilities.CreateCompilation("namespace First; public class A { }", "CliFirst");
        var secondCompilation = TestUtilities.CreateCompilation("namespace Second; public class B { }", "CliSecond");
        var (firstAssemblyPath, firstDirectory) = TestUtilities.EmitToTempAssembly(firstCompilation);
        var (secondAssemblyPath, _) = TestUtilities.EmitToTempAssembly(secondCompilation);
        var outputPath = Path.Combine(firstDirectory, "combined.ttl");

        var result = await RunCliAsync([
            firstAssemblyPath,
            "--assembly", secondAssemblyPath,
            "--output", outputPath,
            "--format", "turtle",
            "--quiet"
        ]);

        Assert.Equal(0, result.ExitCode);
        var text = await File.ReadAllTextAsync(outputPath);
        Assert.Contains("assembly/CliFirst", text);
        Assert.Contains("assembly/CliSecond", text);
    }

    [Fact]
    public async Task Cli_MultipleAssemblies_RequiresExplicitOutputPath()
    {
        var firstCompilation = TestUtilities.CreateCompilation("namespace First; public class A { }", "CliFirst");
        var secondCompilation = TestUtilities.CreateCompilation("namespace Second; public class B { }", "CliSecond");
        var (firstAssemblyPath, _) = TestUtilities.EmitToTempAssembly(firstCompilation);
        var (secondAssemblyPath, _) = TestUtilities.EmitToTempAssembly(secondCompilation);

        var result = await RunCliAsync([
            firstAssemblyPath,
            "--assembly", secondAssemblyPath,
            "--quiet"
        ]);

        Assert.Equal(1, result.ExitCode);
        Assert.Contains("--output is required", result.Stderr);
    }

    [Fact]
    public async Task Cli_MissingAssembly_ReturnsError()
    {
        var missingPath = Path.Combine(Path.GetTempPath(), "missing_" + Guid.NewGuid() + ".dll");
        var args = new[] { missingPath };

        var result = await RunCliAsync(args);

        Assert.Equal(1, result.ExitCode);
        Assert.Contains("Assembly not found", result.Stderr);
    }

    private static async Task<(int ExitCode, string Stdout, string Stderr)> RunCliAsync(string[] args)
    {
        var originalOut = Console.Out;
        var originalErr = Console.Error;

        using var outWriter = new StringWriter(new StringBuilder());
        using var errWriter = new StringWriter(new StringBuilder());

        Console.SetOut(outWriter);
        Console.SetError(errWriter);

        try
        {
            var exitCode = await Program.Main(args);
            return (exitCode, outWriter.ToString(), errWriter.ToString());
        }
        finally
        {
            Console.SetOut(originalOut);
            Console.SetError(originalErr);
        }
    }
}
