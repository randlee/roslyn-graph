using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.FlowAnalysis;
using Microsoft.CodeAnalysis.Operations;
using CSharp = Microsoft.CodeAnalysis.CSharp;
using CSharpSyntax = Microsoft.CodeAnalysis.CSharp.Syntax;
using VisualBasic = Microsoft.CodeAnalysis.VisualBasic;
using VisualBasicSyntax = Microsoft.CodeAnalysis.VisualBasic.Syntax;

namespace RoslynToRdf.Core.Extraction;

public sealed partial class AssemblyGraphExtractor
{
    private readonly HashSet<(SyntaxTree Tree, int Start, int Length, string Owner)> _sourceBodyRoots = new();

    private void ExtractSourceBodyDependencies(ISymbol member, string ownerIri)
    {
        if (_compilation == null)
            return;
        var symbols = new List<ISymbol> { member };
        if (member is IMethodSymbol method)
        {
            symbols.AddRange(method.Parameters);
            if (method.PartialImplementationPart != null)
                symbols.Add(method.PartialImplementationPart);
        }
        if (member is IPropertySymbol property)
        {
            if (property.GetMethod != null) symbols.Add(property.GetMethod);
            if (property.SetMethod != null) symbols.Add(property.SetMethod);
        }
        if (member is IEventSymbol eventSymbol)
        {
            if (eventSymbol.AddMethod != null) symbols.Add(eventSymbol.AddMethod);
            if (eventSymbol.RemoveMethod != null) symbols.Add(eventSymbol.RemoveMethod);
            if (eventSymbol.RaiseMethod != null) symbols.Add(eventSymbol.RaiseMethod);
        }
        foreach (var symbol in symbols)
        foreach (var reference in symbol.DeclaringSyntaxReferences)
        {
            var root = reference.GetSyntax();
            if (root.Parent is VisualBasicSyntax.MethodBlockBaseSyntax or VisualBasicSyntax.PropertyBlockSyntax
                or VisualBasicSyntax.EventBlockSyntax)
                root = root.Parent;
            if (root is VisualBasicSyntax.ModifiedIdentifierSyntax
                && root.Parent is VisualBasicSyntax.VariableDeclaratorSyntax declarator)
                root = declarator;
            if (!_sourceBodyRoots.Add((root.SyntaxTree, root.SpanStart, root.Span.Length, ownerIri)))
                continue;
            var model = _compilation.GetSemanticModel(root.SyntaxTree);
            var visited = new HashSet<IOperation>(ReferenceEqualityComparer.Instance);
            var controlFlowRoots = new HashSet<IOperation>(ReferenceEqualityComparer.Instance);
            var pending = new Stack<SyntaxNode>();
            if (root is CSharpSyntax.TypeDeclarationSyntax typeDeclaration)
            {
                if (typeDeclaration.ParameterList != null) pending.Push(typeDeclaration.ParameterList);
                if (typeDeclaration.BaseList != null) pending.Push(typeDeclaration.BaseList);
            }
            else
                pending.Push(root);
            while (pending.TryPop(out var node))
            {
                if (node is CSharpSyntax.AttributeSyntax or VisualBasicSyntax.AttributeSyntax)
                    continue;
                foreach (var child in node.ChildNodes())
                    pending.Push(child);
                var operation = model.GetOperation(node);
                if (operation != null)
                {
                    VisitSourceOperations(operation, ownerIri, model, visited);
                    while (operation.Parent != null)
                        operation = operation.Parent;
                    controlFlowRoots.Add(operation);
                }
                CollectSelectedSourceMembers(node, model, ownerIri);
            }
            foreach (var operation in controlFlowRoots)
                CollectSourceControlFlow(operation, model, ownerIri, visited);
        }
    }

    private void VisitSourceOperations(IOperation root, string ownerIri, SemanticModel model, HashSet<IOperation> visited)
    {
        var pending = new Stack<IOperation>();
        pending.Push(root);
        while (pending.TryPop(out var operation))
        {
            if (!visited.Add(operation))
                continue;
            EmitBodyType(ownerIri, operation.Type);
            foreach (var child in operation.ChildOperations)
                pending.Push(child);
            switch (operation)
            {
                case IObjectCreationOperation creation: EmitBodySymbol(ownerIri, creation.Constructor); break;
                case IVariableDeclaratorOperation variable: EmitBodyType(ownerIri, variable.Symbol.Type); break;
                case IInvocationOperation invocation:
                    EmitBodySymbol(ownerIri, invocation.TargetMethod);
                    if (invocation.IsImplicit && invocation.TargetMethod.Name == "DisposeAsync")
                        CollectImplicitAwait(invocation.TargetMethod, invocation.Syntax, model, ownerIri);
                    break;
                case IMethodReferenceOperation method: EmitBodySymbol(ownerIri, method.Method); break;
                case IFieldReferenceOperation field: EmitBodySymbol(ownerIri, field.Field); break;
                case IPropertyReferenceOperation property: EmitBodySymbol(ownerIri, property.Property); break;
                case IEventReferenceOperation eventReference: EmitBodySymbol(ownerIri, eventReference.Event); break;
                case IConversionOperation conversion: EmitBodySymbol(ownerIri, conversion.OperatorMethod); break;
                case IBinaryOperation binary: EmitBodySymbol(ownerIri, binary.OperatorMethod); break;
                case IUnaryOperation unary: EmitBodySymbol(ownerIri, unary.OperatorMethod); break;
                case IIncrementOrDecrementOperation increment: EmitBodySymbol(ownerIri, increment.OperatorMethod); break;
                case ICompoundAssignmentOperation assignment: EmitBodySymbol(ownerIri, assignment.OperatorMethod); break;
                case ITypeOfOperation typeOf: EmitBodyType(ownerIri, typeOf.TypeOperand); break;
                case ISizeOfOperation sizeOf: EmitBodyType(ownerIri, sizeOf.TypeOperand); break;
                case IIsTypeOperation isType: EmitBodyType(ownerIri, isType.TypeOperand); break;
                case ITypePatternOperation pattern: EmitBodyType(ownerIri, pattern.MatchedType); break;
                case IDeclarationPatternOperation declaration: EmitBodyType(ownerIri, declaration.MatchedType); break;
                case IRecursivePatternOperation recursive:
                    EmitBodyType(ownerIri, recursive.MatchedType);
                    EmitBodySymbol(ownerIri, recursive.DeconstructSymbol);
                    break;
                case ICatchClauseOperation catchClause: EmitBodyType(ownerIri, catchClause.ExceptionType); break;
                case INameOfOperation nameOf:
                    EmitBodySymbol(ownerIri, model.GetSymbolInfo(nameOf.Argument.Syntax).Symbol);
                    foreach (var namedMember in model.GetMemberGroup(nameOf.Argument.Syntax))
                        EmitBodySymbol(ownerIri, namedMember);
                    break;
            }
        }
    }

    private void CollectSelectedSourceMembers(SyntaxNode node, SemanticModel model, string ownerIri)
    {
        CSharp.DeconstructionInfo? deconstruction = node switch
        {
            CSharpSyntax.AssignmentExpressionSyntax assignment => CSharp.CSharpExtensions.GetDeconstructionInfo(model, assignment),
            CSharpSyntax.ForEachVariableStatementSyntax variable => CSharp.CSharpExtensions.GetDeconstructionInfo(model, variable),
            _ => null
        };
        if (deconstruction.HasValue)
        {
            var pending = new Stack<CSharp.DeconstructionInfo>();
            pending.Push(deconstruction.Value);
            while (pending.TryPop(out var current))
            {
                EmitBodySymbol(ownerIri, current.Method);
                if (!current.Nested.IsDefaultOrEmpty)
                    foreach (var nested in current.Nested)
                        pending.Push(nested);
            }
        }
        if (node is CSharpSyntax.CommonForEachStatementSyntax forEach)
        {
            var info = CSharp.CSharpExtensions.GetForEachStatementInfo(model, forEach);
            EmitBodySymbol(ownerIri, info.GetEnumeratorMethod);
            EmitBodySymbol(ownerIri, info.MoveNextMethod);
            EmitBodySymbol(ownerIri, info.CurrentProperty);
            EmitBodySymbol(ownerIri, info.DisposeMethod);
            EmitBodyType(ownerIri, info.ElementType);
            EmitBodySymbol(ownerIri, info.CurrentConversion.MethodSymbol);
            EmitBodySymbol(ownerIri, info.ElementConversion.MethodSymbol);
            if (info.IsAsynchronous)
            {
                CollectImplicitAwait(info.MoveNextMethod, node, model, ownerIri);
                CollectImplicitAwait(info.DisposeMethod, node, model, ownerIri);
            }
        }
        else if (node is VisualBasicSyntax.ForEachBlockSyntax visualBasicForEach)
        {
            var info = VisualBasic.VisualBasicExtensions.GetForEachStatementInfo(model, visualBasicForEach);
            EmitBodySymbol(ownerIri, info.GetEnumeratorMethod);
            EmitBodySymbol(ownerIri, info.MoveNextMethod);
            EmitBodySymbol(ownerIri, info.CurrentProperty);
            EmitBodySymbol(ownerIri, info.DisposeMethod);
            EmitBodyType(ownerIri, info.ElementType);
            EmitBodySymbol(ownerIri, info.CurrentConversion.MethodSymbol);
            EmitBodySymbol(ownerIri, info.ElementConversion.MethodSymbol);
        }
        else if (node is CSharpSyntax.AwaitExpressionSyntax awaitExpression)
        {
            var info = CSharp.CSharpExtensions.GetAwaitExpressionInfo(model, awaitExpression);
            EmitBodySymbol(ownerIri, info.GetAwaiterMethod);
            EmitBodySymbol(ownerIri, info.IsCompletedProperty);
            EmitBodySymbol(ownerIri, info.GetResultMethod);
        }
        else if (node is VisualBasicSyntax.AwaitExpressionSyntax visualBasicAwait)
        {
            var info = VisualBasic.VisualBasicExtensions.GetAwaitExpressionInfo(model, visualBasicAwait);
            EmitBodySymbol(ownerIri, info.GetAwaiterMethod);
            EmitBodySymbol(ownerIri, info.IsCompletedProperty);
            EmitBodySymbol(ownerIri, info.GetResultMethod);
        }
    }

    private void CollectImplicitAwait(IMethodSymbol? method, SyntaxNode syntax, SemanticModel model, string ownerIri)
    {
        if (method == null || syntax.Language != LanguageNames.CSharp)
            return;
        var statement = CSharp.SyntaxFactory.ExpressionStatement(CSharp.SyntaxFactory.AwaitExpression(
            CSharp.SyntaxFactory.DefaultExpression(CSharp.SyntaxFactory.ParseTypeName(
                method.ReturnType.ToDisplayString(SymbolDisplayFormat.FullyQualifiedFormat)))));
        if (!CSharp.CSharpExtensions.TryGetSpeculativeSemanticModel(model, syntax.SpanStart, statement, out var speculative))
        {
            var originalStatement = syntax.AncestorsAndSelf().OfType<CSharpSyntax.StatementSyntax>().FirstOrDefault();
            if (originalStatement == null)
            {
                ReportBodyDiagnostic($"Could not bind implicit await for {method.ToDisplayString()} in {ownerIri}");
                return;
            }
            var annotation = new SyntaxAnnotation();
            var replacement = statement.WithAdditionalAnnotations(annotation);
            var tree = syntax.SyntaxTree;
            var replacementTree = tree.WithRootAndOptions(tree.GetRoot().ReplaceNode(originalStatement, replacement), tree.Options);
            speculative = model.Compilation.ReplaceSyntaxTree(tree, replacementTree).GetSemanticModel(replacementTree);
            statement = (CSharpSyntax.ExpressionStatementSyntax)replacementTree.GetRoot().GetAnnotatedNodes(annotation).Single();
        }
        var info = CSharp.CSharpExtensions.GetAwaitExpressionInfo(speculative, (CSharpSyntax.AwaitExpressionSyntax)statement.Expression);
        if (info.GetAwaiterMethod == null)
            ReportBodyDiagnostic($"Could not resolve implicit awaiter for {method.ToDisplayString()} in {ownerIri}");
        EmitBodySymbol(ownerIri, info.GetAwaiterMethod);
        EmitBodySymbol(ownerIri, info.IsCompletedProperty);
        EmitBodySymbol(ownerIri, info.GetResultMethod);
    }

    private void CollectSourceControlFlow(IOperation operation, SemanticModel model, string ownerIri, HashSet<IOperation> visited)
    {
        ControlFlowGraph? graph = operation switch
        {
            IMethodBodyOperation method => ControlFlowGraph.Create(method),
            IConstructorBodyOperation constructor => ControlFlowGraph.Create(constructor),
            IBlockOperation block => ControlFlowGraph.Create(block),
            IFieldInitializerOperation field => ControlFlowGraph.Create(field),
            IPropertyInitializerOperation property => ControlFlowGraph.Create(property),
            IParameterInitializerOperation parameter => ControlFlowGraph.Create(parameter),
            _ => null
        };
        if (graph == null)
            return;
        var pending = new Queue<ControlFlowGraph>();
        var visitedGraphs = new HashSet<ControlFlowGraph>(ReferenceEqualityComparer.Instance);
        pending.Enqueue(graph);
        while (pending.TryDequeue(out var current))
        {
            if (!visitedGraphs.Add(current))
                continue;
            foreach (var local in current.LocalFunctions)
                pending.Enqueue(current.GetLocalFunctionControlFlowGraph(local));
            foreach (var block in current.Blocks)
            foreach (var body in block.Operations.Concat(block.BranchValue == null ? [] : new[] { block.BranchValue }))
            {
                VisitSourceOperations(body, ownerIri, model, visited);
                var operations = new Stack<IOperation>();
                operations.Push(body);
                while (operations.TryPop(out var child))
                {
                    if (child is IFlowAnonymousFunctionOperation anonymous)
                        pending.Enqueue(current.GetAnonymousFunctionControlFlowGraph(anonymous));
                    foreach (var descendant in child.ChildOperations)
                        operations.Push(descendant);
                }
            }
        }
    }
}
