using System.Text;
using RoslynToRdf.Cli;

namespace RoslynToRdf.Tests;

public class CliIntegrationTests
{
    [Fact]
    public async Task Cli_StrictAliasMatchesLegacyMissingReferenceFailure()
    {
        using var fixture = new AssemblyReferenceFixture();
        foreach (var option in new[] { "--strict", "--fail-on-missing-references" })
        {
            var result = await RunCliAsync([
                fixture.TargetPath, "-o", Path.Combine(fixture.DirectoryPath, option[2..] + ".nt"), option
            ]);
            Assert.Equal(1, result.ExitCode);
            Assert.Contains(fixture.DependencyName, result.Stderr);
            Assert.DoesNotContain("Done.", result.Stdout);
        }
    }

    [Fact]
    public async Task Cli_UnwritableOutputIsFatalWithoutDone()
    {
        using var fixture = new AssemblyReferenceFixture();
        var result = await RunCliAsync([fixture.TargetPath, "-o", fixture.DirectoryPath]);
        Assert.Equal(1, result.ExitCode);
        Assert.Contains("Error:", result.Stderr);
        Assert.DoesNotContain("Done.", result.Stdout);
    }

    [Fact]
    public async Task Cli_UnresolvedSourceBodyWarnsEvenWhenQuiet()
    {
        using var fixture = new AssemblyReferenceFixture();
        var projectPath = Path.Combine(fixture.DirectoryPath, "Unresolved.csproj");
        await File.WriteAllTextAsync(projectPath, """
            <Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><TargetFramework>net8.0</TargetFramework></PropertyGroup></Project>
            """);
        await File.WriteAllTextAsync(Path.Combine(fixture.DirectoryPath, "Unresolved.cs"),
            "public class Inventory { public void Run() { MissingType value = null; } }");
        var result = await RunCliAsync([
            projectPath, "-o", Path.Combine(fixture.DirectoryPath, "unresolved.nt"), "--quiet"
        ]);
        Assert.Equal(0, result.ExitCode);
        Assert.Empty(result.Stdout);
        Assert.Contains("Warning: Unresolved body type", result.Stderr);
        Assert.Contains("MissingType", result.Stderr);
    }

    [Theory]
    [InlineData(null, false)]
    [InlineData("--exclude-attributes", false)]
    [InlineData("--include-attributes", true)]
    public async Task Cli_AttributesAreExplicitlyOptIn(string? option, bool expected)
    {
        var compilation = TestUtilities.CreateCompilation(
            "[System.Obsolete] public class Attributed { }", "PhaseCAttributes");
        var (assemblyPath, directory) = TestUtilities.EmitToTempAssembly(compilation);
        var outputPath = Path.ChangeExtension(assemblyPath, ".nt");
        try
        {
            var arguments = new List<string> { assemblyPath, "-o", outputPath, "--quiet" };
            if (option != null)
                arguments.Add(option);
            var result = await RunCliAsync(arguments.ToArray());
            Assert.Equal(0, result.ExitCode);
            var graph = await File.ReadAllTextAsync(outputPath);
            Assert.Equal(expected, graph.Contains("/ontology/hasAttribute>"));
        }
        finally
        {
            File.Delete(assemblyPath);
            File.Delete(outputPath);
            Directory.Delete(directory);
        }
    }

    [Fact]
    public async Task Cli_ConflictingAttributeOptionsFailBeforeOutput()
    {
        using var fixture = new AssemblyReferenceFixture();
        var outputPath = Path.Combine(fixture.DirectoryPath, "conflict.nt");
        var result = await RunCliAsync([
            fixture.TargetPath, "-o", outputPath, "--include-attributes", "--exclude-attributes"
        ]);
        Assert.Equal(1, result.ExitCode);
        Assert.Contains("cannot be combined", result.Stderr);
        Assert.False(File.Exists(outputPath));
    }

    [Theory]
    [InlineData("--strict")]
    [InlineData("--fail-on-missing-references")]
    public async Task Cli_StrictAliasesRejectVbSource(string option)
    {
        using var fixture = new AssemblyReferenceFixture();
        var projectPath = Path.Combine(fixture.DirectoryPath, "source.vbproj");
        var outputPath = Path.Combine(fixture.DirectoryPath, "source.nt");
        await File.WriteAllTextAsync(projectPath, "<Project />");
        var result = await RunCliAsync([projectPath, "-o", outputPath, option]);
        Assert.Equal(1, result.ExitCode);
        Assert.Contains("supported only for assembly", result.Stderr);
        Assert.False(File.Exists(outputPath));
    }

    [Fact]
    public async Task Cli_VbProjectIncludesGenericAndBodyDependencies()
    {
        using var fixture = new AssemblyReferenceFixture();
        var projectPath = Path.Combine(fixture.DirectoryPath, "Inventory.vbproj");
        var outputPath = Path.Combine(fixture.DirectoryPath, "inventory.nt");
        await File.WriteAllTextAsync(projectPath, """
            <Project Sdk="Microsoft.NET.Sdk">
              <PropertyGroup>
                <TargetFramework>net8.0</TargetFramework>
                <RootNamespace></RootNamespace>
              </PropertyGroup>
            </Project>
            """);
        await File.WriteAllTextAsync(Path.Combine(fixture.DirectoryPath, "Inventory.vb"), """
            Public Class BodyOnly
            End Class
            Public Class Inventory(Of T)
                Public Function Make() As Object
                    Return New System.Collections.Generic.List(Of BodyOnly)()
                End Function
            End Class
            """);
        var restoreInfo = new System.Diagnostics.ProcessStartInfo("dotnet")
        {
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            CreateNoWindow = true,
            UseShellExecute = false
        };
        restoreInfo.ArgumentList.Add("restore");
        restoreInfo.ArgumentList.Add(projectPath);
        using var restore = System.Diagnostics.Process.Start(restoreInfo)!;
        var restoreOutput = restore.StandardOutput.ReadToEndAsync();
        var restoreError = restore.StandardError.ReadToEndAsync();
        await restore.WaitForExitAsync();
        Assert.True(restore.ExitCode == 0, await restoreOutput + await restoreError);
        var result = await RunCliAsync([projectPath, "-o", outputPath]);
        Assert.Equal(0, result.ExitCode);
        var graph = await File.ReadAllTextAsync(outputPath);
        Assert.True(graph.Contains("/ontology/usesType>"), result.Stdout + result.Stderr + graph);
        Assert.Contains("BodyOnly", graph);
        Assert.Contains("/ontology/hasTypeParameter>", graph);
    }

    [Theory]
    [InlineData("culture", false)]
    [InlineData("culture", true)]
    [InlineData("public-key", false)]
    [InlineData("public-key", true)]
    public async Task Cli_IncompatibleReferenceIdentityWarnsAndOnlyFailsWhenRequested(string mismatch, bool strict)
    {
        using var fixture = new AssemblyReferenceFixture(strongNamedDependency: mismatch == "public-key");
        fixture.ReplaceDependency("2.0.0.0", mismatch == "culture" ? "fr" : "");
        var outputPath = Path.Combine(fixture.DirectoryPath, "out.nt");
        var arguments = new List<string>
        {
            fixture.TargetPath, "--output", outputPath, "--quiet", "--reference", fixture.DependencyPath
        };
        if (strict)
            arguments.Add("--fail-on-missing-references");

        var result = await RunCliAsync(arguments.ToArray());

        Assert.Equal(strict ? 1 : 0, result.ExitCode);
        Assert.Empty(result.Stdout);
        Assert.Contains(fixture.DependencyName, result.Stderr);
        Assert.Contains(fixture.DependencyPath, result.Stderr);
        Assert.Contains("Roslyn could not bind", result.Stderr);
        Assert.Single(result.Stderr.Split(Environment.NewLine).Where(line => line.StartsWith("Warning: Assembly reference")));
        if (!strict)
            Assert.Contains("Warning: Unresolved metadata body dependency", result.Stderr);
        if (!strict)
            Assert.Contains("ReferenceFixture.Target", await File.ReadAllTextAsync(outputPath));
    }

    [Theory]
    [InlineData("1.0.0.0", false)]
    [InlineData("3.0.0.0", false)]
    [InlineData("3.0.0.0", true)]
    public async Task Cli_StrictModeAcceptsCompatibleVersionUnification(string version, bool strongNamed)
    {
        using var fixture = new AssemblyReferenceFixture(strongNamedDependency: strongNamed);
        fixture.ReplaceDependency(version, publicSign: strongNamed);
        var outputPath = Path.Combine(fixture.DirectoryPath, "out.nt");

        var result = await RunCliAsync([
            fixture.TargetPath, "--output", outputPath, "--quiet", "-r", fixture.DependencyPath,
            "--fail-on-missing-references"
        ]);

        Assert.Equal(0, result.ExitCode);
        Assert.Empty(result.Stdout);
        Assert.Empty(result.Stderr);
        Assert.Contains("ReferenceFixture.Base", await File.ReadAllTextAsync(outputPath));
    }

    [Fact]
    public async Task Cli_StrictModeAcceptsRuntimeFacadeBindings()
    {
        var runtimeDirectory = Path.GetDirectoryName(typeof(object).Assembly.Location)!;
        var compilation = TestUtilities.CreateCompilation(
                "public class RuntimeFacade { public System.Collections.Generic.IEnumerable<int> Values => System.Linq.Enumerable.Empty<int>(); }",
                "RuntimeFacadeBindings")
            .AddReferences(Microsoft.CodeAnalysis.MetadataReference.CreateFromFile(Path.Combine(runtimeDirectory, "System.Runtime.dll")));
        var (assemblyPath, directory) = TestUtilities.EmitToTempAssembly(compilation);
        try
        {
            var outputPath = Path.Combine(directory, "out.nt");
            var result = await RunCliAsync([assemblyPath, "--output", outputPath, "--quiet", "--fail-on-missing-references"]);

            Assert.Equal(0, result.ExitCode);
            Assert.Empty(result.Stdout);
            Assert.Empty(result.Stderr);
            Assert.Contains("RuntimeFacade", await File.ReadAllTextAsync(outputPath));
        }
        finally
        {
            Directory.Delete(directory, recursive: true);
        }
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task Cli_MissingDependencyWarnsEvenWhenQuietAndOnlyFailsWhenRequested(bool strict)
    {
        using var fixture = new AssemblyReferenceFixture();
        var outputPath = Path.Combine(fixture.DirectoryPath, "out.nt");
        var arguments = new List<string> { fixture.TargetPath, "--output", outputPath, "--quiet" };
        if (strict)
            arguments.Add("--fail-on-missing-references");

        var result = await RunCliAsync(arguments.ToArray());

        Assert.Equal(strict ? 1 : 0, result.ExitCode);
        Assert.Empty(result.Stdout);
        Assert.Contains("Warning:", result.Stderr);
        Assert.Contains(fixture.DependencyName, result.Stderr);
        Assert.Contains(fixture.TargetPath, result.Stderr);
        Assert.Contains("--reference (-r)", result.Stderr);
        Assert.Contains("--search-dir (-s)", result.Stderr);
        Assert.Single(result.Stderr.Split(Environment.NewLine).Where(line => line.StartsWith("Warning: Assembly reference")));
        if (!strict)
            Assert.Contains("Warning: Unresolved metadata body dependency", result.Stderr);
        if (strict)
            Assert.Contains("--fail-on-missing-references", result.Stderr);
        else
            Assert.Contains("ReferenceFixture.Target", await File.ReadAllTextAsync(outputPath));
    }

    [Theory]
    [InlineData("missing", false)]
    [InlineData("missing", true)]
    [InlineData("corrupt", false)]
    [InlineData("corrupt", true)]
    [InlineData("locked", false)]
    [InlineData("locked", true)]
    public async Task Cli_InvalidExplicitReferenceWarnsAndOnlyFailsWhenRequested(string failure, bool strict)
    {
        using var fixture = new AssemblyReferenceFixture();
        var invalidPath = Path.Combine(fixture.DirectoryPath, "invalid.dll");
        if (failure != "missing")
            await File.WriteAllTextAsync(invalidPath, "invalid assembly");
        using var lockStream = failure == "locked" ? new FileStream(invalidPath, FileMode.Open, FileAccess.Read, FileShare.None) : null;
        var outputPath = Path.Combine(fixture.DirectoryPath, "out.nt");
        var arguments = new List<string>
        {
            fixture.TargetPath, "--output", outputPath, "--quiet",
            "-r", fixture.DependencyPath, "-r", invalidPath
        };
        if (strict)
            arguments.Add("--fail-on-missing-references");

        var result = await RunCliAsync(arguments.ToArray());

        Assert.Equal(strict ? 1 : 0, result.ExitCode);
        Assert.Empty(result.Stdout);
        Assert.Contains("Warning:", result.Stderr);
        Assert.Contains(invalidPath, result.Stderr);
        Assert.Contains("explicit --reference", result.Stderr);
        if (!strict)
            Assert.Contains("ReferenceFixture.Target", await File.ReadAllTextAsync(outputPath));
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task Cli_MissingTransitiveDependencyWarnsAndOnlyFailsWhenRequested(bool strict)
    {
        using var fixture = new AssemblyReferenceFixture();
        File.Delete(fixture.TransitivePath);
        var arguments = new List<string>
        {
            fixture.TargetPath, "--output", Path.Combine(fixture.DirectoryPath, "out.nt"), "--quiet",
            "--reference", fixture.DependencyPath
        };
        if (strict)
            arguments.Add("--fail-on-missing-references");

        var result = await RunCliAsync(arguments.ToArray());

        Assert.Equal(strict ? 1 : 0, result.ExitCode);
        Assert.Empty(result.Stdout);
        Assert.Contains(fixture.TransitiveName, result.Stderr);
        Assert.Contains(fixture.DependencyPath, result.Stderr);
        Assert.Single(result.Stderr.Split(Environment.NewLine).Where(line => line.StartsWith("Warning:")));
    }

    [Fact]
    public async Task Cli_StrictModeAcceptsExplicitRenamedDependencyAndItsTransitiveReference()
    {
        using var fixture = new AssemblyReferenceFixture();
        var renamedPath = Path.Combine(fixture.DirectoryPath, "dependencies", "renamed.dll");
        File.Move(fixture.DependencyPath, renamedPath);
        var outputPath = Path.Combine(fixture.DirectoryPath, "out.nt");

        var result = await RunCliAsync([
            fixture.TargetPath, "--output", outputPath, "--quiet", "-r", renamedPath,
            "--fail-on-missing-references"
        ]);

        Assert.Equal(0, result.ExitCode);
        Assert.Empty(result.Stdout);
        Assert.Empty(result.Stderr);
        Assert.Contains("ReferenceFixture.Base", await File.ReadAllTextAsync(outputPath));
    }

    [Fact]
    public async Task Cli_StrictModeRejectsSourceProjectsBeforeCreatingOutput()
    {
        using var fixture = new AssemblyReferenceFixture();
        var projectPath = Path.Combine(fixture.DirectoryPath, "source.csproj");
        await File.WriteAllTextAsync(projectPath, "<Project />");
        var outputPath = Path.Combine(fixture.DirectoryPath, "out.nt");

        var result = await RunCliAsync([
            projectPath, "--output", outputPath, "--quiet", "--fail-on-missing-references"
        ]);

        Assert.Equal(1, result.ExitCode);
        Assert.Empty(result.Stdout);
        Assert.Contains("only for assembly (.dll) inputs", result.Stderr);
        Assert.False(File.Exists(outputPath));
    }

    [Theory]
    [InlineData("missing", false)]
    [InlineData("missing", true)]
    [InlineData("corrupt", false)]
    [InlineData("corrupt", true)]
    public async Task Cli_InvalidTargetRemainsFatal(string failure, bool strict)
    {
        using var fixture = new AssemblyReferenceFixture();
        if (failure == "missing")
            File.Delete(fixture.TargetPath);
        else
            await File.WriteAllTextAsync(fixture.TargetPath, "invalid assembly");
        var arguments = new List<string> { fixture.TargetPath, "--quiet" };
        if (strict)
            arguments.Add("--fail-on-missing-references");

        var result = await RunCliAsync(arguments.ToArray());

        Assert.Equal(1, result.ExitCode);
        Assert.Empty(result.Stdout);
        Assert.NotEmpty(result.Stderr);
    }

    [Fact]
    public async Task Cli_SkillHelp_DoesNotInheritAssemblyArgument()
    {
        var result = await RunCliAsync(["skill", "--help"]);

        Assert.Equal(0, result.ExitCode);
        Assert.Contains("skill [options]", result.Stdout);
        Assert.Contains("--install", result.Stdout);
        Assert.DoesNotContain("<assembly>", result.Stdout);
        Assert.DoesNotContain("roslyn2rdf <assembly>", result.Stdout);
    }

    [Fact]
    public async Task Cli_SkillRejectsPositionalAssemblyArgument()
    {
        var result = await RunCliAsync(["skill", "not-an-assembly.dll"]);

        Assert.Equal(1, result.ExitCode);
        Assert.DoesNotContain("Assembly not found", result.Stderr);
    }

    [Theory]
    [InlineData(false, true)]
    [InlineData(true, true)]
    [InlineData(true, false)]
    public async Task Cli_EmittedAssembly_HonorsVisibilityFlags(bool includePrivate, bool includeInternal)
    {
        var source = """
            namespace Sample;
            public class Visibility
            {
                public void PublicMethod() { }
                private void PrivateMethod() { }
                private int PrivateField = 1;
                private int PrivateProperty => PrivateField;
                private class PrivateNested { public class PrivateDescendant { } }
                internal void InternalMethod() { }
                internal int InternalField;
                internal int InternalProperty => InternalField;
                internal class InternalNested { public class InternalDescendant { } }
            }
            internal class InternalType { }
            """;
        var compilation = TestUtilities.CreateCompilation(source, "CliVisibility");
        var (assemblyPath, directory) = TestUtilities.EmitToTempAssembly(compilation);
        var outputPath = Path.Combine(directory, "visibility.nt");
        var args = new List<string> { assemblyPath, "--output", outputPath, "--quiet" };
        if (includePrivate)
            args.Add("--include-private");
        if (!includeInternal)
            args.AddRange(["--include-internal", "false"]);

        var result = await RunCliAsync(args.ToArray());

        Assert.Equal(0, result.ExitCode);
        var graph = await File.ReadAllTextAsync(outputPath);
        Assert.Contains("\"PublicMethod\"", graph);
        foreach (var name in new[] { "PrivateMethod", "PrivateField", "PrivateProperty", "PrivateNested", "PrivateDescendant" })
            Assert.Equal(includePrivate, graph.Contains($"\"{name}\"", StringComparison.Ordinal));
        foreach (var name in new[] { "InternalMethod", "InternalField", "InternalProperty", "InternalNested", "InternalType", "InternalDescendant" })
            Assert.Equal(includeInternal, graph.Contains($"\"{name}\"", StringComparison.Ordinal));
    }

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

    [Fact]
    public async Task Cli_SourceProjectUsesExplicitMsbuildEvaluationContext()
    {
        var root = Path.Combine(Path.GetTempPath(), "RoslynToRdfContext_" + Guid.NewGuid().ToString("N"));
        var dependency = Path.Combine(root, "Dependency");
        Directory.CreateDirectory(dependency);
        try
        {
            await File.WriteAllTextAsync(Path.Combine(root, "Context.props"), """
                <Project>
                  <PropertyGroup Condition="'$(Configuration)' == 'Debug' and '$(TargetFramework)' == 'net8.0'">
                    <DefineConstants>$(DefineConstants);PROFILE_CONTEXT_LOADED</DefineConstants>
                  </PropertyGroup>
                  <ItemGroup Condition="'$(Configuration)' == 'Debug' and '$(TargetFramework)' == 'net8.0'">
                    <ProjectReference Include="$(SolutionDir)Dependency/Dependency.csproj" />
                  </ItemGroup>
                </Project>
                """);
            var projectPath = Path.Combine(root, "Main.csproj");
            await File.WriteAllTextAsync(projectPath, """
                <Project Sdk="Microsoft.NET.Sdk">
                  <Import Project="$(SolutionDir)Context.props" />
                  <PropertyGroup><TargetFramework>net8.0</TargetFramework></PropertyGroup>
                </Project>
                """);
            await File.WriteAllTextAsync(Path.Combine(root, "Main.cs"), """
                namespace Fixture;
                #if PROFILE_CONTEXT_LOADED
                public class ContextOnly { public DependencyType Dependency { get; set; } = new(); }
                #endif
                """);
            await File.WriteAllTextAsync(Path.Combine(dependency, "Dependency.csproj"), """
                <Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><TargetFramework>net8.0</TargetFramework></PropertyGroup></Project>
                """);
            await File.WriteAllTextAsync(Path.Combine(dependency, "Dependency.cs"), "namespace Fixture; public class DependencyType { }");

            var outputPath = Path.Combine(root, "graph.ttl");
            var result = await RunCliAsync([
                projectPath, "--output", outputPath, "--format", "turtle", "--quiet",
                "--solution-dir", root, "--configuration", "Debug", "--platform", "AnyCPU", "--target-framework", "net8.0"
            ]);

            Assert.Equal(0, result.ExitCode);
            var graph = await File.ReadAllTextAsync(outputPath);
            Assert.Contains("Fixture.ContextOnly", graph);
            Assert.Contains("Fixture.DependencyType", graph);
        }
        finally
        {
            Directory.Delete(root, recursive: true);
        }
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
