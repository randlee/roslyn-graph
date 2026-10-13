using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.CSharp.Syntax;

namespace RoslynToRdf.Core.Extraction;

/// <summary>
/// Finds unsafe contexts and operations in source declarations. Nested local functions and lambdas
/// are part of the containing graph method because the graph does not emit separate nodes for them.
/// </summary>
internal static class UnsafeMethodAnalyzer
{
    internal sealed record Fact(string Reason, string Location);

    public static bool HasUnsafeTypeModifier(INamedTypeSymbol type) => type.DeclaringSyntaxReferences
        .Select(reference => reference.GetSyntax())
        .OfType<TypeDeclarationSyntax>()
        .Any(declaration => declaration.Modifiers.Any(SyntaxKind.UnsafeKeyword));

    public static IReadOnlyList<Fact> Analyze(Compilation compilation, IMethodSymbol method, string? sourceRoot)
    {
        var facts = new HashSet<Fact>();
        foreach (var reference in method.DeclaringSyntaxReferences)
        {
            var declaration = reference.GetSyntax();
            var model = compilation.GetSemanticModel(declaration.SyntaxTree);

            if (HasUnsafeModifier(declaration))
                Add(facts, "UnsafeMethodModifier", declaration, sourceRoot);

            foreach (var node in declaration.DescendantNodesAndSelf())
            {
                switch (node)
                {
                    case UnsafeStatementSyntax:
                        Add(facts, "UnsafeBlock", node, sourceRoot);
                        break;
                    case PointerTypeSyntax:
                        Add(facts, "PointerType", node, sourceRoot);
                        break;
                    case FunctionPointerTypeSyntax:
                        Add(facts, "FunctionPointerType", node, sourceRoot);
                        break;
                    case FixedStatementSyntax:
                        Add(facts, "FixedStatement", node, sourceRoot);
                        break;
                    case StackAllocArrayCreationExpressionSyntax stackAlloc
                        when model.GetTypeInfo(stackAlloc).Type is IPointerTypeSymbol:
                        Add(facts, "PointerStackAlloc", node, sourceRoot);
                        break;
                    case MemberAccessExpressionSyntax memberAccess when memberAccess.IsKind(SyntaxKind.PointerMemberAccessExpression):
                        Add(facts, "PointerMemberAccess", node, sourceRoot);
                        break;
                    case PrefixUnaryExpressionSyntax unary when unary.IsKind(SyntaxKind.PointerIndirectionExpression):
                        Add(facts, "PointerDereference", node, sourceRoot);
                        break;
                    case PrefixUnaryExpressionSyntax unary when unary.IsKind(SyntaxKind.AddressOfExpression)
                        && model.GetTypeInfo(unary).Type is IPointerTypeSymbol:
                        Add(facts, "PointerAddressOf", node, sourceRoot);
                        break;
                }
            }
        }

        return facts.OrderBy(fact => fact.Reason, StringComparer.Ordinal)
            .ThenBy(fact => fact.Location, StringComparer.Ordinal).ToArray();
    }

    private static bool HasUnsafeModifier(SyntaxNode declaration) => declaration switch
    {
        BaseMethodDeclarationSyntax method => method.Modifiers.Any(SyntaxKind.UnsafeKeyword),
        LocalFunctionStatementSyntax localFunction => localFunction.Modifiers.Any(SyntaxKind.UnsafeKeyword),
        _ => false
    };

    private static void Add(HashSet<Fact> facts, string reason, SyntaxNode node, string? sourceRoot)
    {
        var span = node.GetLocation().GetLineSpan();
        var path = string.IsNullOrEmpty(span.Path) ? "<source>" : span.Path.Replace('\\', '/');
        if (sourceRoot is not null && Path.IsPathRooted(path) && path != "<source>")
            path = Path.GetRelativePath(sourceRoot, path).Replace('\\', '/');
        facts.Add(new Fact(reason, $"{path}:{span.StartLinePosition.Line + 1}:{span.StartLinePosition.Character + 1}"));
    }
}
