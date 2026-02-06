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

    #region Corner Cases

    [Fact]
    public void LoadAssembly_NonExistentFile_ThrowsFileNotFoundException()
    {
        var loader = new AssemblyLoader();
        var nonExistentPath = Path.Combine(Path.GetTempPath(), "NonExistent_" + Guid.NewGuid() + ".dll");

        var ex = Assert.Throws<FileNotFoundException>(() => loader.LoadAssembly(nonExistentPath));
        Assert.Contains("Assembly not found", ex.Message);
        Assert.Contains(nonExistentPath, ex.Message);
    }

    [Fact]
    public void LoadAssembly_EmptyAssembly_LoadsSuccessfully()
    {
        var source = @"
// Empty assembly with no types
";

        var compilation = TestUtilities.CreateCompilation(source, "EmptyAssembly");
        var (assemblyPath, _) = TestUtilities.EmitToTempAssembly(compilation);

        var loader = new AssemblyLoader();
        var (loadedCompilation, assemblySymbol) = loader.LoadAssembly(assemblyPath);

        Assert.NotNull(loadedCompilation);
        Assert.NotNull(assemblySymbol);
        Assert.Equal("EmptyAssembly", assemblySymbol.Name);
    }

    [Fact]
    public void LoadAssembly_CorruptedDll_ThrowsException()
    {
        var tempDir = Path.Combine(Path.GetTempPath(), "roslyn2rdf-tests", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempDir);
        var corruptedPath = Path.Combine(tempDir, "corrupted.dll");

        // Create a file with invalid PE format
        File.WriteAllText(corruptedPath, "This is not a valid DLL file");

        var loader = new AssemblyLoader();

        // Should throw when trying to create metadata reference
        Assert.ThrowsAny<Exception>(() => loader.LoadAssembly(corruptedPath));

        // Cleanup
        try { Directory.Delete(tempDir, true); } catch { }
    }

    [Fact]
    public void LoadAssembly_AssemblyWithNoReferences_LoadsSuccessfully()
    {
        var source = @"
namespace Isolated;

public class Simple
{
    public int GetValue() => 42;
}
";

        var compilation = TestUtilities.CreateCompilation(source, "NoRefsAssembly");
        var (assemblyPath, _) = TestUtilities.EmitToTempAssembly(compilation);

        var loader = new AssemblyLoader();
        var (loadedCompilation, assemblySymbol) = loader.LoadAssembly(assemblyPath);

        Assert.NotNull(loadedCompilation);
        Assert.NotNull(assemblySymbol);
        Assert.Equal("NoRefsAssembly", assemblySymbol.Name);
    }

    #endregion

    #region Reference Resolution

    [Fact]
    public void AddReferencePath_ValidFile_AddsReference()
    {
        var source = @"
namespace Test;
public class A { }
";

        var compilation = TestUtilities.CreateCompilation(source, "RefAssembly");
        var (refPath, _) = TestUtilities.EmitToTempAssembly(compilation);

        var loader = new AssemblyLoader();
        loader.AddReferencePath(refPath);

        // Load another assembly
        var mainSource = @"
namespace Main;
public class B { }
";
        var mainCompilation = TestUtilities.CreateCompilation(mainSource, "MainAssembly");
        var (mainPath, _) = TestUtilities.EmitToTempAssembly(mainCompilation);

        var (loadedCompilation, _) = loader.LoadAssembly(mainPath);

        // The reference should be included
        Assert.Contains(loadedCompilation.References, r =>
            r.Display != null && r.Display.Contains("RefAssembly"));
    }

    [Fact]
    public void AddReferencePath_NonExistentFile_DoesNotAddReference()
    {
        var loader = new AssemblyLoader();
        var nonExistentPath = Path.Combine(Path.GetTempPath(), "NonExistent_" + Guid.NewGuid() + ".dll");

        // Should not throw, just ignore
        loader.AddReferencePath(nonExistentPath);

        var source = @"
namespace Test;
public class C { }
";
        var compilation = TestUtilities.CreateCompilation(source, "TestAssembly");
        var (assemblyPath, _) = TestUtilities.EmitToTempAssembly(compilation);

        // Should load successfully even with invalid reference path
        var (loadedCompilation, assemblySymbol) = loader.LoadAssembly(assemblyPath);
        Assert.NotNull(loadedCompilation);
        Assert.NotNull(assemblySymbol);
    }

    [Fact]
    public void AddReferencePath_MultipleReferences_AddsAll()
    {
        var source1 = @"namespace Test1; public class A { }";
        var source2 = @"namespace Test2; public class B { }";
        var source3 = @"namespace Test3; public class C { }";

        var comp1 = TestUtilities.CreateCompilation(source1, "Ref1");
        var comp2 = TestUtilities.CreateCompilation(source2, "Ref2");
        var comp3 = TestUtilities.CreateCompilation(source3, "Ref3");

        var (ref1Path, _) = TestUtilities.EmitToTempAssembly(comp1);
        var (ref2Path, _) = TestUtilities.EmitToTempAssembly(comp2);
        var (ref3Path, _) = TestUtilities.EmitToTempAssembly(comp3);

        var loader = new AssemblyLoader();
        loader.AddReferencePath(ref1Path);
        loader.AddReferencePath(ref2Path);
        loader.AddReferencePath(ref3Path);

        var mainSource = @"namespace Main; public class Main { }";
        var mainComp = TestUtilities.CreateCompilation(mainSource, "MainAssembly");
        var (mainPath, _) = TestUtilities.EmitToTempAssembly(mainComp);

        var (loadedCompilation, _) = loader.LoadAssembly(mainPath);

        // All three references should be present
        var refDisplays = loadedCompilation.References.Select(r => r.Display ?? "").ToList();
        Assert.Contains(refDisplays, d => d.Contains("Ref1"));
        Assert.Contains(refDisplays, d => d.Contains("Ref2"));
        Assert.Contains(refDisplays, d => d.Contains("Ref3"));
    }

    [Fact]
    public void AddSearchDirectory_ValidDirectory_SearchesForReferences()
    {
        var searchDir = Path.Combine(Path.GetTempPath(), "roslyn2rdf-tests", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(searchDir);

        var refSource = @"namespace Ref; public class RefClass { }";
        var refComp = TestUtilities.CreateCompilation(refSource, "SearchedRef");
        var (_, refDir) = TestUtilities.EmitToTempAssembly(refComp);

        var loader = new AssemblyLoader();
        loader.AddSearchDirectory(refDir);

        var mainSource = @"namespace Main; public class Main { }";
        var mainComp = TestUtilities.CreateCompilation(mainSource, "MainWithSearch");
        var (mainPath, _) = TestUtilities.EmitToTempAssembly(mainComp);

        var (loadedCompilation, _) = loader.LoadAssembly(mainPath);

        Assert.NotNull(loadedCompilation);

        // Cleanup
        try { Directory.Delete(searchDir, true); } catch { }
    }

    [Fact]
    public void AddSearchDirectory_NonExistentDirectory_DoesNotThrow()
    {
        var loader = new AssemblyLoader();
        var nonExistentDir = Path.Combine(Path.GetTempPath(), "NonExistent_" + Guid.NewGuid());

        // Should not throw, just ignore
        loader.AddSearchDirectory(nonExistentDir);

        var source = @"namespace Test; public class C { }";
        var compilation = TestUtilities.CreateCompilation(source, "TestAssembly");
        var (assemblyPath, _) = TestUtilities.EmitToTempAssembly(compilation);

        // Should load successfully
        var (loadedCompilation, assemblySymbol) = loader.LoadAssembly(assemblyPath);
        Assert.NotNull(loadedCompilation);
        Assert.NotNull(assemblySymbol);
    }

    [Fact]
    public void AddSearchDirectory_MultipleDirectories_SearchesAll()
    {
        var dir1 = Path.Combine(Path.GetTempPath(), "roslyn2rdf-tests", Guid.NewGuid().ToString("N"));
        var dir2 = Path.Combine(Path.GetTempPath(), "roslyn2rdf-tests", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(dir1);
        Directory.CreateDirectory(dir2);

        var loader = new AssemblyLoader();
        loader.AddSearchDirectory(dir1);
        loader.AddSearchDirectory(dir2);

        var source = @"namespace Test; public class C { }";
        var compilation = TestUtilities.CreateCompilation(source, "MultiSearchTest");
        var (assemblyPath, _) = TestUtilities.EmitToTempAssembly(compilation);

        var (loadedCompilation, assemblySymbol) = loader.LoadAssembly(assemblyPath);

        Assert.NotNull(loadedCompilation);
        Assert.NotNull(assemblySymbol);

        // Cleanup
        try { Directory.Delete(dir1, true); } catch { }
        try { Directory.Delete(dir2, true); } catch { }
    }

    #endregion

    #region Error Conditions

    [Fact]
    public void LoadAssembly_WithMissingDependencies_LoadsWithoutDependency()
    {
        // Create a referenced assembly first
        var refSource = @"
namespace Referenced;
public class RefClass { public void Method() { } }
";
        var refComp = TestUtilities.CreateCompilation(refSource, "ReferencedAssembly");
        var (refPath, _) = TestUtilities.EmitToTempAssembly(refComp);

        // Create main assembly that references it
        var mainSource = @"
namespace Main;
public class MainClass
{
    public void UseRef(Referenced.RefClass r) => r.Method();
}
";
        var mainComp = TestUtilities.CreateCompilation(mainSource, "MainAssembly")
            .AddReferences(Microsoft.CodeAnalysis.MetadataReference.CreateFromFile(refPath));
        var (mainPath, mainDir) = TestUtilities.EmitToTempAssembly(mainComp);

        // Delete the referenced assembly to simulate missing dependency
        File.Delete(refPath);

        var loader = new AssemblyLoader();

        // Should still load the main assembly, just without the reference
        var (loadedCompilation, assemblySymbol) = loader.LoadAssembly(mainPath);

        Assert.NotNull(loadedCompilation);
        Assert.NotNull(assemblySymbol);
        Assert.Equal("MainAssembly", assemblySymbol.Name);
    }

    [Fact]
    public void LoadAssembly_DuplicateReferences_OnlyLoadsOnce()
    {
        var source = @"namespace Test; public class A { }";
        var compilation = TestUtilities.CreateCompilation(source, "DuplicateTest");
        var (assemblyPath, _) = TestUtilities.EmitToTempAssembly(compilation);

        var loader = new AssemblyLoader();

        // Add the same reference multiple times
        loader.AddReferencePath(assemblyPath);
        loader.AddReferencePath(assemblyPath);
        loader.AddReferencePath(assemblyPath);

        var (loadedCompilation, assemblySymbol) = loader.LoadAssembly(assemblyPath);

        Assert.NotNull(loadedCompilation);
        Assert.NotNull(assemblySymbol);

        // Count how many times the assembly appears in references
        var count = loadedCompilation.References.Count(r =>
            r.Display != null && r.Display.Contains("DuplicateTest"));

        // Should only appear once (the main assembly itself)
        Assert.Equal(1, count);
    }

    #endregion

    #region Edge Cases

    [Fact]
    public void LoadAssembly_WithRuntimeReferences_LoadsSuccessfully()
    {
        var source = @"
using System;

namespace Test;

public class WithSystemRefs
{
    public string GetString() => ""hello"".ToUpper();
}
";

        var compilation = TestUtilities.CreateCompilation(source, "SystemRefsTest");
        var (assemblyPath, _) = TestUtilities.EmitToTempAssembly(compilation);

        var loader = new AssemblyLoader();
        var (loadedCompilation, assemblySymbol) = loader.LoadAssembly(assemblyPath);

        Assert.NotNull(loadedCompilation);
        Assert.NotNull(assemblySymbol);
        Assert.Equal("SystemRefsTest", assemblySymbol.Name);

        // Should have multiple references including runtime assemblies
        Assert.True(loadedCompilation.References.Count() > 1);
    }

    [Fact]
    public void LoadAssembly_LargeNumberOfTypes_LoadsSuccessfully()
    {
        // Generate assembly with many types
        var sourceBuilder = new System.Text.StringBuilder();
        sourceBuilder.AppendLine("namespace Large;");

        for (int i = 0; i < 100; i++)
        {
            sourceBuilder.AppendLine($"public class Type{i} {{ public int Value{i} => {i}; }}");
        }

        var compilation = TestUtilities.CreateCompilation(sourceBuilder.ToString(), "LargeAssembly");
        var (assemblyPath, _) = TestUtilities.EmitToTempAssembly(compilation);

        var loader = new AssemblyLoader();
        var (loadedCompilation, assemblySymbol) = loader.LoadAssembly(assemblyPath);

        Assert.NotNull(loadedCompilation);
        Assert.NotNull(assemblySymbol);

        // Verify we can access types
        var type50 = loadedCompilation.GetTypeByMetadataName("Large.Type50");
        Assert.NotNull(type50);
    }

    [Fact]
    public void LoadAssembly_WithNestedTypes_LoadsCorrectly()
    {
        var source = @"
namespace Nested;

public class Outer
{
    public class Inner1
    {
        public class DeepInner { }
    }

    public class Inner2 { }
}
";

        var compilation = TestUtilities.CreateCompilation(source, "NestedTypes");
        var (assemblyPath, _) = TestUtilities.EmitToTempAssembly(compilation);

        var loader = new AssemblyLoader();
        var (loadedCompilation, assemblySymbol) = loader.LoadAssembly(assemblyPath);

        Assert.NotNull(loadedCompilation);
        Assert.NotNull(assemblySymbol);

        var outerType = loadedCompilation.GetTypeByMetadataName("Nested.Outer");
        Assert.NotNull(outerType);

        var inner1 = loadedCompilation.GetTypeByMetadataName("Nested.Outer+Inner1");
        Assert.NotNull(inner1);

        var deepInner = loadedCompilation.GetTypeByMetadataName("Nested.Outer+Inner1+DeepInner");
        Assert.NotNull(deepInner);
    }

    [Fact]
    public void LoadAssembly_WithGenerics_LoadsCorrectly()
    {
        var source = @"
namespace Generics;

public class Generic<T>
{
    public T Value { get; set; }
}

public class MultiGeneric<T1, T2>
{
    public T1 First { get; set; }
    public T2 Second { get; set; }
}
";

        var compilation = TestUtilities.CreateCompilation(source, "GenericTypes");
        var (assemblyPath, _) = TestUtilities.EmitToTempAssembly(compilation);

        var loader = new AssemblyLoader();
        var (loadedCompilation, assemblySymbol) = loader.LoadAssembly(assemblyPath);

        Assert.NotNull(loadedCompilation);
        Assert.NotNull(assemblySymbol);

        var genericType = loadedCompilation.GetTypeByMetadataName("Generics.Generic`1");
        Assert.NotNull(genericType);
        Assert.True(genericType.IsGenericType);

        var multiGeneric = loadedCompilation.GetTypeByMetadataName("Generics.MultiGeneric`2");
        Assert.NotNull(multiGeneric);
        Assert.Equal(2, multiGeneric.TypeParameters.Length);
    }

    [Fact]
    public void LoadAssembly_SameAssemblyTwice_ReturnsSameResult()
    {
        var source = @"namespace Test; public class C { }";
        var compilation = TestUtilities.CreateCompilation(source, "SameAssembly");
        var (assemblyPath, _) = TestUtilities.EmitToTempAssembly(compilation);

        var loader = new AssemblyLoader();
        var (comp1, asm1) = loader.LoadAssembly(assemblyPath);
        var (comp2, asm2) = loader.LoadAssembly(assemblyPath);

        Assert.NotNull(comp1);
        Assert.NotNull(comp2);
        Assert.NotNull(asm1);
        Assert.NotNull(asm2);

        Assert.Equal(asm1.Name, asm2.Name);
    }

    [Fact]
    public void LoadAssembly_WithAttributes_LoadsCorrectly()
    {
        var source = @"
using System;

namespace Attributes;

[Obsolete(""Old class"")]
public class AttributedClass
{
    [Obsolete(""Old method"")]
    public void OldMethod() { }
}
";

        var compilation = TestUtilities.CreateCompilation(source, "AttributedAssembly");
        var (assemblyPath, _) = TestUtilities.EmitToTempAssembly(compilation);

        var loader = new AssemblyLoader();
        var (loadedCompilation, assemblySymbol) = loader.LoadAssembly(assemblyPath);

        Assert.NotNull(loadedCompilation);
        Assert.NotNull(assemblySymbol);

        var type = loadedCompilation.GetTypeByMetadataName("Attributes.AttributedClass");
        Assert.NotNull(type);

        var attrs = type.GetAttributes();
        Assert.NotEmpty(attrs);
    }

    [Fact]
    public void LoadAssembly_WithInterfaces_LoadsCorrectly()
    {
        var source = @"
namespace Interfaces;

public interface IBase { }
public interface IDerived : IBase { }

public class Implementation : IDerived { }
";

        var compilation = TestUtilities.CreateCompilation(source, "InterfaceAssembly");
        var (assemblyPath, _) = TestUtilities.EmitToTempAssembly(compilation);

        var loader = new AssemblyLoader();
        var (loadedCompilation, assemblySymbol) = loader.LoadAssembly(assemblyPath);

        Assert.NotNull(loadedCompilation);
        Assert.NotNull(assemblySymbol);

        var impl = loadedCompilation.GetTypeByMetadataName("Interfaces.Implementation");
        Assert.NotNull(impl);

        var interfaces = impl.AllInterfaces;
        Assert.Contains(interfaces, i => i.Name == "IDerived");
        Assert.Contains(interfaces, i => i.Name == "IBase");
    }

    [Fact]
    public void LoadAssembly_WithAbstractClasses_LoadsCorrectly()
    {
        var source = @"
namespace Abstract;

public abstract class BaseClass
{
    public abstract void AbstractMethod();
    public virtual void VirtualMethod() { }
}

public class ConcreteClass : BaseClass
{
    public override void AbstractMethod() { }
}
";

        var compilation = TestUtilities.CreateCompilation(source, "AbstractAssembly");
        var (assemblyPath, _) = TestUtilities.EmitToTempAssembly(compilation);

        var loader = new AssemblyLoader();
        var (loadedCompilation, assemblySymbol) = loader.LoadAssembly(assemblyPath);

        Assert.NotNull(loadedCompilation);
        Assert.NotNull(assemblySymbol);

        var baseClass = loadedCompilation.GetTypeByMetadataName("Abstract.BaseClass");
        Assert.NotNull(baseClass);
        Assert.True(baseClass.IsAbstract);

        var concreteClass = loadedCompilation.GetTypeByMetadataName("Abstract.ConcreteClass");
        Assert.NotNull(concreteClass);
        Assert.False(concreteClass.IsAbstract);
    }

    #endregion

    #region Relative Path Resolution

    [Fact]
    public void LoadAssembly_ResolvesFromAssemblyDirectory()
    {
        // Create two assemblies in the same directory
        var dir = Path.Combine(Path.GetTempPath(), "roslyn2rdf-tests", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(dir);

        var ref1Source = @"namespace Ref1; public class RefClass1 { }";
        var ref1Comp = TestUtilities.CreateCompilation(ref1Source, "Ref1Assembly");
        var (ref1Path, _) = TestUtilities.EmitToTempAssembly(ref1Comp);

        // Move to common directory
        var ref1Target = Path.Combine(dir, "Ref1Assembly.dll");
        File.Move(ref1Path, ref1Target);

        var mainSource = @"namespace Main; public class Main { }";
        var mainComp = TestUtilities.CreateCompilation(mainSource, "MainInSameDir")
            .AddReferences(Microsoft.CodeAnalysis.MetadataReference.CreateFromFile(ref1Target));
        var (mainPath, _) = TestUtilities.EmitToTempAssembly(mainComp);

        var mainTarget = Path.Combine(dir, "MainInSameDir.dll");
        File.Move(mainPath, mainTarget);

        var loader = new AssemblyLoader();
        var (loadedCompilation, assemblySymbol) = loader.LoadAssembly(mainTarget);

        Assert.NotNull(loadedCompilation);
        Assert.NotNull(assemblySymbol);

        // Cleanup
        try { Directory.Delete(dir, true); } catch { }
    }

    #endregion

    #region Stress Tests

    [Fact]
    public void LoadAssembly_WithReferenceChain_LoadsSuccessfully()
    {
        // Create a chain: A -> B where both are in the same directory
        var dir = Path.Combine(Path.GetTempPath(), "roslyn2rdf-tests", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(dir);

        // Create assembly B first
        var sourceB = @"namespace B; public class ClassB { }";
        var compB = TestUtilities.CreateCompilation(sourceB, "AssemblyB");
        var (pathB, _) = TestUtilities.EmitToTempAssembly(compB);

        // Move B to common directory
        var targetPathB = Path.Combine(dir, "AssemblyB.dll");
        File.Copy(pathB, targetPathB, true);

        // Create assembly A that references B
        var sourceA = @"namespace A; public class ClassA { }";
        var compA = TestUtilities.CreateCompilation(sourceA, "AssemblyA")
            .AddReferences(Microsoft.CodeAnalysis.MetadataReference.CreateFromFile(targetPathB));
        var (pathA, _) = TestUtilities.EmitToTempAssembly(compA);

        // Move A to common directory
        var targetPathA = Path.Combine(dir, "AssemblyA.dll");
        File.Copy(pathA, targetPathA, true);

        var loader = new AssemblyLoader();
        var (loadedCompilation, assemblySymbol) = loader.LoadAssembly(targetPathA);

        Assert.NotNull(loadedCompilation);
        Assert.NotNull(assemblySymbol);
        Assert.Equal("AssemblyA", assemblySymbol.Name);

        // Verify that references were loaded
        Assert.True(loadedCompilation.References.Count() >= 1);

        // Cleanup
        try { Directory.Delete(dir, true); } catch { }
    }

    #endregion
}
