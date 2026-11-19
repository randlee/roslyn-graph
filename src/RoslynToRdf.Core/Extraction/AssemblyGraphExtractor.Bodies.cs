using Microsoft.CodeAnalysis;
using RoslynToRdf.Core.Model;

namespace RoslynToRdf.Core.Extraction;

public sealed partial class AssemblyGraphExtractor
{
    private string? _peImagePath;
    private readonly HashSet<(string Owner, string Target)> _bodyTypeEdges = new();
    private readonly List<string> _bodyResolutionDiagnostics = new();
    public IReadOnlyList<string> BodyResolutionDiagnostics => _bodyResolutionDiagnostics.AsReadOnly();

    private void ReportBodyDiagnostic(string message)
    {
        if (!_bodyResolutionDiagnostics.Contains(message))
            _bodyResolutionDiagnostics.Add(message);
        LogVerbose(message);
    }

    private void ExtractBodyDependencies(ISymbol member, string ownerIri)
    {
        if (member.DeclaringSyntaxReferences.Length > 0)
        {
            ExtractSourceBodyDependencies(member, ownerIri);
            return;
        }

        if (_peImagePath == null)
            return;

        switch (member)
        {
            case IMethodSymbol method:
                ExtractMetadataBodyDependencies(method, ownerIri);
                break;
            case IPropertySymbol property:
                if (property.GetMethod != null)
                    ExtractMetadataBodyDependencies(property.GetMethod, ownerIri);
                if (property.SetMethod != null)
                    ExtractMetadataBodyDependencies(property.SetMethod, ownerIri);
                break;
            case IEventSymbol eventSymbol:
                if (eventSymbol.AddMethod != null)
                    ExtractMetadataBodyDependencies(eventSymbol.AddMethod, ownerIri);
                if (eventSymbol.RemoveMethod != null)
                    ExtractMetadataBodyDependencies(eventSymbol.RemoveMethod, ownerIri);
                if (eventSymbol.RaiseMethod != null)
                    ExtractMetadataBodyDependencies(eventSymbol.RaiseMethod, ownerIri);
                break;
        }
    }

    private void EmitBodyType(string ownerIri, ITypeSymbol? type)
    {
        if (type == null)
            return;

        var pending = new Stack<ITypeSymbol>();
        var visited = new HashSet<ISymbol>(SymbolEqualityComparer.Default);
        pending.Push(type);
        while (pending.TryPop(out var current))
        {
            if (!visited.Add(current))
                continue;

            switch (current)
            {
                case IArrayTypeSymbol array:
                    pending.Push(array.ElementType);
                    break;
                case IPointerTypeSymbol pointer:
                    pending.Push(pointer.PointedAtType);
                    break;
                case IFunctionPointerTypeSymbol pointer:
                    pending.Push(pointer.Signature.ReturnType);
                    foreach (var parameter in pointer.Signature.Parameters)
                        pending.Push(parameter.Type);
                    foreach (var convention in pointer.Signature.UnmanagedCallingConventionTypes)
                        pending.Push(convention);
                    break;
                case INamedTypeSymbol named when named.TypeKind != TypeKind.Error:
                    var targetIri = EnsureTypeEmitted(named);
                    if (_bodyTypeEdges.Add((ownerIri, targetIri)))
                        _emitter.EmitIri(ownerIri, Prop(DotNetOntology.MemberRels.UsesType), targetIri);
                    if (!SymbolEqualityComparer.Default.Equals(named, named.OriginalDefinition))
                        pending.Push(named.OriginalDefinition);
                    if (named.ContainingType != null)
                        pending.Push(named.ContainingType);
                    foreach (var argument in named.TypeArguments)
                        pending.Push(argument);
                    break;
                case IErrorTypeSymbol:
                    ReportBodyDiagnostic($"Unresolved body type for {ownerIri}: {current.ToDisplayString()}");
                    break;
            }
        }
    }

    private void EmitBodySymbol(string ownerIri, ISymbol? symbol)
    {
        if (symbol is ITypeSymbol type)
        {
            EmitBodyType(ownerIri, type);
            return;
        }

        EmitBodyType(ownerIri, symbol?.ContainingType);
        switch (symbol)
        {
            case IMethodSymbol method:
                if (!method.ReturnsVoid)
                    EmitBodyType(ownerIri, method.ReturnType);
                foreach (var argument in method.TypeArguments)
                    EmitBodyType(ownerIri, argument);
                foreach (var parameter in method.Parameters)
                    EmitBodyType(ownerIri, parameter.Type);
                break;
            case IPropertySymbol property:
                EmitBodyType(ownerIri, property.Type);
                foreach (var parameter in property.Parameters)
                    EmitBodyType(ownerIri, parameter.Type);
                break;
            case IFieldSymbol field:
                EmitBodyType(ownerIri, field.Type);
                break;
            case IEventSymbol eventSymbol:
                EmitBodyType(ownerIri, eventSymbol.Type);
                break;
            case ILocalSymbol local:
                EmitBodyType(ownerIri, local.Type);
                break;
            case IParameterSymbol parameter:
                EmitBodyType(ownerIri, parameter.Type);
                break;
        }
    }
}
