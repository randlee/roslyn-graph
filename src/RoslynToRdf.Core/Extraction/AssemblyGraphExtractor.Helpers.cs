using Microsoft.CodeAnalysis;
using RoslynToRdf.Core.Model;

namespace RoslynToRdf.Core.Extraction;

public sealed partial class AssemblyGraphExtractor
{
    private string EnsureTypeEmitted(ITypeSymbol type)
    {
        if (type is IArrayTypeSymbol arrayType)
            return EnsureArrayTypeEmitted(arrayType);

        if (type is IPointerTypeSymbol pointerType)
            return EnsurePointerTypeEmitted(pointerType);

        if (type is ITypeParameterSymbol)
            return _iris.Type(type);

        if (type is not INamedTypeSymbol namedType)
            return _iris.Type(type);

        var typeIri = _iris.Type(type);

        if (_emittedTypes.Contains(typeIri))
            return typeIri;

        if (!_options.IncludeExternalTypes)
        {
            _emittedTypes.Add(typeIri);
            return typeIri;
        }

        _emittedTypes.Add(typeIri);

        _emitter.EmitIri(typeIri, RdfType, Prop(DotNetOntology.Classes.Type));
        _emitter.EmitLiteral(typeIri, Prop(DotNetOntology.TypeProps.Name), namedType.Name);
        _emitter.EmitLiteral(typeIri, Prop(DotNetOntology.TypeProps.FullName), namedType.ToDisplayString());
        _emitter.EmitLiteral(typeIri, Prop(DotNetOntology.TypeProps.TypeKind), namedType.TypeKind.ToString());

        if (namedType.ContainingAssembly != null)
        {
            var asmIri = _iris.Assembly(namedType.ContainingAssembly);
            _emitter.EmitIri(typeIri, Prop(DotNetOntology.TypeRels.DefinedInAssembly), asmIri);
        }

        if (!namedType.ContainingNamespace.IsGlobalNamespace)
        {
            var nsIri = EnsureNamespaceEmitted(namedType.ContainingNamespace);
            _emitter.EmitIri(typeIri, Prop(DotNetOntology.TypeRels.InNamespace), nsIri);
        }

        if (namedType.IsGenericType && !namedType.IsUnboundGenericType && 
            namedType.OriginalDefinition != null && 
            !SymbolEqualityComparer.Default.Equals(namedType, namedType.OriginalDefinition))
        {
            var defIri = EnsureTypeEmitted(namedType.OriginalDefinition);
            _emitter.EmitIri(typeIri, Prop(DotNetOntology.TypeRels.GenericDefinition), defIri);

            for (int i = 0; i < namedType.TypeArguments.Length; i++)
            {
                var argIri = EnsureTypeEmitted(namedType.TypeArguments[i]);
                var argNodeIri = $"{typeIri}/typearg/{i}";
                _emitter.EmitIri(typeIri, Prop(DotNetOntology.TypeRels.TypeArgument), argNodeIri);
                _emitter.EmitInt(argNodeIri, Prop("index"), i);
                _emitter.EmitIri(argNodeIri, Prop("type"), argIri);
            }
        }

        return typeIri;
    }

    private string EnsureArrayTypeEmitted(IArrayTypeSymbol arrayType)
    {
        var typeIri = _iris.Type(arrayType);

        if (_emittedTypes.Contains(typeIri))
            return typeIri;

        _emittedTypes.Add(typeIri);

        _emitter.EmitIri(typeIri, RdfType, Prop(DotNetOntology.Classes.Type));
        _emitter.EmitLiteral(typeIri, Prop(DotNetOntology.TypeProps.Name), arrayType.ToDisplayString());
        _emitter.EmitLiteral(typeIri, Prop(DotNetOntology.TypeProps.TypeKind), "Array");
        _emitter.EmitInt(typeIri, Prop("arrayRank"), arrayType.Rank);

        var elementIri = EnsureTypeEmitted(arrayType.ElementType);
        _emitter.EmitIri(typeIri, Prop(DotNetOntology.TypeRels.ArrayElementType), elementIri);

        return typeIri;
    }

    private string EnsurePointerTypeEmitted(IPointerTypeSymbol pointerType)
    {
        var typeIri = _iris.Type(pointerType);

        if (_emittedTypes.Contains(typeIri))
            return typeIri;

        _emittedTypes.Add(typeIri);

        _emitter.EmitIri(typeIri, RdfType, Prop(DotNetOntology.Classes.Type));
        _emitter.EmitLiteral(typeIri, Prop(DotNetOntology.TypeProps.Name), pointerType.ToDisplayString());
        _emitter.EmitLiteral(typeIri, Prop(DotNetOntology.TypeProps.TypeKind), "Pointer");

        var pointedAtIri = EnsureTypeEmitted(pointerType.PointedAtType);
        _emitter.EmitIri(typeIri, Prop(DotNetOntology.TypeRels.PointerElementType), pointedAtIri);

        return typeIri;
    }

    private string EnsureNamespaceEmitted(INamespaceSymbol ns)
    {
        var nsIri = _iris.Namespace(ns);

        if (_emittedNamespaces.Contains(nsIri))
            return nsIri;

        _emittedNamespaces.Add(nsIri);

        _emitter.EmitIri(nsIri, RdfType, Prop(DotNetOntology.Classes.Namespace));
        _emitter.EmitLiteral(nsIri, Prop(DotNetOntology.NsProps.Name), ns.Name);
        _emitter.EmitLiteral(nsIri, Prop(DotNetOntology.NsProps.FullName), ns.ToDisplayString());

        if (ns.ContainingNamespace != null && !ns.ContainingNamespace.IsGlobalNamespace)
        {
            var parentIri = EnsureNamespaceEmitted(ns.ContainingNamespace);
            _emitter.EmitIri(nsIri, Prop(DotNetOntology.NsRels.ParentNamespace), parentIri);
        }

        return nsIri;
    }
}
