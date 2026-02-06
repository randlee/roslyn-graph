using Microsoft.CodeAnalysis;
using RoslynToRdf.Core.Emitters;
using RoslynToRdf.Core.Model;

namespace RoslynToRdf.Core.Extraction;

/// <summary>
/// Extracts a complete RDF graph from a .NET assembly using Roslyn.
/// </summary>
public sealed partial class AssemblyGraphExtractor
{
    private readonly IriMinter _iris;
    private readonly ITriplesEmitter _emitter;
    private readonly ExtractionOptions _options;
    private readonly HashSet<string> _emittedTypes = new();
    private readonly HashSet<string> _emittedNamespaces = new();
    private XmlDocParser? _xmlDocParser;
    private readonly Action<string>? _log;

    public AssemblyGraphExtractor(
        ITriplesEmitter emitter, 
        ExtractionOptions? options = null,
        Action<string>? log = null)
    {
        _options = options ?? new ExtractionOptions();
        _iris = new IriMinter(_options.BaseUri);
        _emitter = emitter;
        _log = log;

        // Add standard prefixes
        _emitter.AddPrefix("rdf", DotNetOntology.Rdf);
        _emitter.AddPrefix("rdfs", DotNetOntology.Rdfs);
        _emitter.AddPrefix("xsd", DotNetOntology.Xsd);
        _emitter.AddPrefix(DotNetOntology.Prefix, _iris.OntologyPrefix);
        _emitter.AddPrefix(DotNetOntology.DotNetPrefix, _iris.DotNetOntologyPrefix);
    }

    private string Prop(string name) => $"{_iris.OntologyPrefix}{name}";
    private string DotNetProp(string name) => $"{_iris.DotNetOntologyPrefix}{name}";
    private string RdfType => $"{DotNetOntology.Rdf}type";

    /// <summary>
    /// Extract the type graph from a compilation, focusing on a target assembly.
    /// </summary>
    public void Extract(Compilation compilation, IAssemblySymbol targetAssembly)
    {
        _xmlDocParser = new XmlDocParser(compilation);

        Log($"Extracting assembly: {targetAssembly.Name} v{targetAssembly.Identity.Version}");

        // Emit assembly node
        var asmIri = _iris.Assembly(targetAssembly);
        _emitter.EmitIri(asmIri, RdfType, Prop(DotNetOntology.Classes.Assembly));
        _emitter.EmitLiteral(asmIri, Prop(DotNetOntology.AsmProps.Name), targetAssembly.Name);
        _emitter.EmitLiteral(asmIri, Prop(DotNetOntology.AsmProps.Version), 
            targetAssembly.Identity.Version.ToString());
        
        if (!string.IsNullOrEmpty(targetAssembly.Identity.CultureName))
            _emitter.EmitLiteral(asmIri, DotNetProp(DotNetOntology.AsmProps.Culture),
                targetAssembly.Identity.CultureName);

        var publicKeyToken = targetAssembly.Identity.PublicKeyToken;
        if (publicKeyToken.Length > 0)
            _emitter.EmitLiteral(asmIri, DotNetProp(DotNetOntology.AsmProps.PublicKeyToken),
                BitConverter.ToString(publicKeyToken.ToArray()).Replace("-", "").ToLowerInvariant());

        _emitter.EmitBool(asmIri, DotNetProp(DotNetOntology.AsmProps.IsInteractive),
            targetAssembly.IsInteractive);

        _emitter.EmitLiteral(asmIri, _iris.OntologyPrefix + "language", "dotnet");

        // Walk all types in this assembly
        var typeCount = 0;
        foreach (var type in GetAllTypes(targetAssembly.GlobalNamespace))
        {
            if (ShouldIncludeType(type))
            {
                ExtractType(type, asmIri);
                typeCount++;
            }
        }

        Log($"Extracted {typeCount} types, {_emitter.TripleCount} triples");
    }

    private bool ShouldIncludeType(INamedTypeSymbol type)
    {
        if (type.IsImplicitlyDeclared && !_options.IncludeCompilerGenerated)
            return false;

        return type.DeclaredAccessibility switch
        {
            Accessibility.Private => _options.IncludePrivate,
            Accessibility.Internal => _options.IncludeInternal,
            Accessibility.ProtectedAndInternal => _options.IncludeInternal,
            _ => true
        };
    }

    private bool ShouldIncludeMember(ISymbol member)
    {
        if (member.IsImplicitlyDeclared && !_options.IncludeCompilerGenerated)
            return false;

        return member.DeclaredAccessibility switch
        {
            Accessibility.Private => _options.IncludePrivate,
            Accessibility.Internal => _options.IncludeInternal,
            Accessibility.ProtectedAndInternal => _options.IncludeInternal,
            _ => true
        };
    }

    private IEnumerable<INamedTypeSymbol> GetAllTypes(INamespaceSymbol ns)
    {
        foreach (var type in ns.GetTypeMembers())
        {
            yield return type;
            foreach (var nested in GetNestedTypes(type))
                yield return nested;
        }

        foreach (var childNs in ns.GetNamespaceMembers())
        {
            foreach (var type in GetAllTypes(childNs))
                yield return type;
        }
    }

    private IEnumerable<INamedTypeSymbol> GetNestedTypes(INamedTypeSymbol type)
    {
        foreach (var nested in type.GetTypeMembers())
        {
            yield return nested;
            foreach (var deepNested in GetNestedTypes(nested))
                yield return deepNested;
        }
    }

    private void ExtractType(INamedTypeSymbol type, string asmIri)
    {
        var typeIri = _iris.Type(type);
        
        if (!_emittedTypes.Add(typeIri))
            return; // Already emitted

        LogVerbose($"  Type: {type.ToDisplayString()}");

        // RDF type based on kind
        _emitter.EmitIri(typeIri, RdfType, Prop(DotNetOntology.Classes.Type));
        _emitter.EmitIri(typeIri, RdfType, Prop(GetTypeClass(type)));

        // Basic properties
        _emitter.EmitLiteral(typeIri, Prop(DotNetOntology.TypeProps.Name), type.Name);
        _emitter.EmitLiteral(typeIri, Prop(DotNetOntology.TypeProps.FullName), type.ToDisplayString());
        _emitter.EmitLiteral(typeIri, Prop(DotNetOntology.TypeProps.TypeKind), type.TypeKind.ToString());
        _emitter.EmitLiteral(typeIri, Prop(DotNetOntology.TypeProps.Accessibility), 
            type.DeclaredAccessibility.ToString());

        // Boolean flags
        _emitter.EmitBool(typeIri, Prop(DotNetOntology.TypeProps.IsAbstract), type.IsAbstract);
        _emitter.EmitBool(typeIri, Prop(DotNetOntology.TypeProps.IsSealed), type.IsSealed);
        _emitter.EmitBool(typeIri, Prop(DotNetOntology.TypeProps.IsStatic), type.IsStatic);
        _emitter.EmitBool(typeIri, Prop(DotNetOntology.TypeProps.IsGeneric), type.IsGenericType);
        _emitter.EmitBool(typeIri, Prop(DotNetOntology.TypeProps.IsValueType), type.IsValueType);
        _emitter.EmitBool(typeIri, Prop(DotNetOntology.TypeProps.IsRecord), type.IsRecord);
        _emitter.EmitBool(typeIri, DotNetProp(DotNetOntology.TypeProps.IsRefLikeType), type.IsRefLikeType);
        _emitter.EmitBool(typeIri, Prop(DotNetOntology.TypeProps.IsReadOnly), type.IsReadOnly);
        _emitter.EmitBool(typeIri, DotNetProp(DotNetOntology.TypeProps.IsUnmanagedType), type.IsUnmanagedType);

        if (type.SpecialType != SpecialType.None)
            _emitter.EmitLiteral(typeIri, DotNetProp(DotNetOntology.TypeProps.SpecialType),
                type.SpecialType.ToString());

        if (type.TypeKind == TypeKind.Enum && type.EnumUnderlyingType != null)
            _emitter.EmitIri(typeIri, DotNetProp(DotNetOntology.TypeProps.EnumUnderlyingType),
                EnsureTypeEmitted(type.EnumUnderlyingType));

        // Relationships
        _emitter.EmitIri(typeIri, Prop(DotNetOntology.TypeRels.DefinedInAssembly), asmIri);

        // Namespace
        if (!type.ContainingNamespace.IsGlobalNamespace)
        {
            var nsIri = EnsureNamespaceEmitted(type.ContainingNamespace);
            _emitter.EmitIri(typeIri, Prop(DotNetOntology.TypeRels.InNamespace), nsIri);
        }

        // Base type
        if (type.BaseType != null && type.BaseType.SpecialType != SpecialType.System_Object)
        {
            var baseIri = EnsureTypeEmitted(type.BaseType);
            _emitter.EmitIri(typeIri, Prop(DotNetOntology.TypeRels.Inherits), baseIri);
        }

        // Interfaces
        foreach (var iface in type.Interfaces)
        {
            var ifaceIri = EnsureTypeEmitted(iface);
            _emitter.EmitIri(typeIri, Prop(DotNetOntology.TypeRels.Implements), ifaceIri);
        }

        // Nested in
        if (type.ContainingType != null)
        {
            _emitter.EmitIri(typeIri, Prop(DotNetOntology.TypeRels.NestedIn), _iris.Type(type.ContainingType));
        }

        // Type parameters
        foreach (var tp in type.TypeParameters)
        {
            ExtractTypeParameter(typeIri, type, tp);
        }

        // Constructed generic: link to definition and type arguments
        if (type.IsGenericType && !type.IsUnboundGenericType && 
            type.OriginalDefinition != null && !SymbolEqualityComparer.Default.Equals(type, type.OriginalDefinition))
        {
            _emitter.EmitIri(typeIri, Prop(DotNetOntology.TypeRels.GenericDefinition), 
                _iris.Type(type.OriginalDefinition));
            
            for (int i = 0; i < type.TypeArguments.Length; i++)
            {
                var argIri = EnsureTypeEmitted(type.TypeArguments[i]);
                // Use a reified relationship to preserve order
                var argNodeIri = $"{typeIri}/typearg/{i}";
                _emitter.EmitIri(typeIri, Prop(DotNetOntology.TypeRels.TypeArgument), argNodeIri);
                _emitter.EmitInt(argNodeIri, Prop("index"), i);
                _emitter.EmitIri(argNodeIri, Prop("type"), argIri);
            }
        }

        // Attributes
        if (_options.IncludeAttributes)
        {
            int attrIndex = 0;
            foreach (var attr in type.GetAttributes())
            {
                ExtractAttribute(typeIri, type, attr, attrIndex++);
            }
        }

        // XML doc: exceptions and seealso
        if (_xmlDocParser != null)
        {
            if (_options.ExtractExceptions)
            {
                foreach (var exType in _xmlDocParser.GetExceptionTypes(type))
                {
                    var exIri = EnsureTypeEmitted(exType);
                    _emitter.EmitIri(typeIri, Prop(DotNetOntology.TypeRels.Throws), exIri);
                }
            }

            if (_options.ExtractSeeAlso)
            {
                foreach (var related in _xmlDocParser.GetSeeAlsoReferences(type))
                {
                    var relatedIri = related switch
                    {
                        ITypeSymbol t => EnsureTypeEmitted(t),
                        _ => _iris.Member(related)
                    };
                    _emitter.EmitIri(typeIri, Prop(DotNetOntology.TypeRels.RelatedTo), relatedIri);
                }
            }
        }

        // Members
        foreach (var member in type.GetMembers())
        {
            if (!ShouldIncludeMember(member))
                continue;

            switch (member)
            {
                case IMethodSymbol method when method.MethodKind == MethodKind.Ordinary ||
                                               method.MethodKind == MethodKind.Constructor ||
                                               method.MethodKind == MethodKind.StaticConstructor ||
                                               method.MethodKind == MethodKind.Destructor ||
                                               method.MethodKind == MethodKind.UserDefinedOperator ||
                                               method.MethodKind == MethodKind.Conversion:
                    ExtractMethod(typeIri, method);
                    break;
                case IPropertySymbol prop:
                    ExtractProperty(typeIri, prop);
                    break;
                case IFieldSymbol field:
                    ExtractField(typeIri, field);
                    break;
                case IEventSymbol evt:
                    ExtractEvent(typeIri, evt);
                    break;
            }
        }
    }

    private string GetTypeClass(INamedTypeSymbol type)
    {
        if (type.IsRecord)
            return DotNetOntology.Classes.Record;

        return type.TypeKind switch
        {
            TypeKind.Class => DotNetOntology.Classes.Class,
            TypeKind.Struct => DotNetOntology.Classes.Struct,
            TypeKind.Interface => DotNetOntology.Classes.Interface,
            TypeKind.Enum => DotNetOntology.Classes.Enum,
            TypeKind.Delegate => DotNetOntology.Classes.Delegate,
            _ => DotNetOntology.Classes.Type
        };
    }

    private void ExtractTypeParameter(string ownerIri, ISymbol owner, ITypeParameterSymbol tp)
    {
        var tpIri = _iris.TypeParameter(owner, tp);

        _emitter.EmitIri(tpIri, RdfType, Prop(DotNetOntology.Classes.TypeParameter));
        _emitter.EmitLiteral(tpIri, Prop(DotNetOntology.TypeParamProps.Name), tp.Name);
        _emitter.EmitInt(tpIri, Prop(DotNetOntology.TypeParamProps.Ordinal), tp.Ordinal);
        _emitter.EmitLiteral(tpIri, Prop(DotNetOntology.TypeParamProps.Variance), tp.Variance.ToString());

        _emitter.EmitBool(tpIri, DotNetProp(DotNetOntology.TypeParamProps.HasReferenceTypeConstraint),
            tp.HasReferenceTypeConstraint);
        _emitter.EmitBool(tpIri, DotNetProp(DotNetOntology.TypeParamProps.HasValueTypeConstraint),
            tp.HasValueTypeConstraint);
        _emitter.EmitBool(tpIri, DotNetProp(DotNetOntology.TypeParamProps.HasUnmanagedTypeConstraint),
            tp.HasUnmanagedTypeConstraint);
        _emitter.EmitBool(tpIri, DotNetProp(DotNetOntology.TypeParamProps.HasNotNullConstraint),
            tp.HasNotNullConstraint);
        _emitter.EmitBool(tpIri, DotNetProp(DotNetOntology.TypeParamProps.HasConstructorConstraint),
            tp.HasConstructorConstraint);

        _emitter.EmitIri(ownerIri, Prop(DotNetOntology.TypeRels.HasTypeParameter), tpIri);
        _emitter.EmitIri(tpIri, Prop(DotNetOntology.TypeParamRels.TypeParameterOf), ownerIri);

        // Type constraints
        foreach (var constraint in tp.ConstraintTypes)
        {
            var constraintIri = EnsureTypeEmitted(constraint);
            _emitter.EmitIri(tpIri, Prop(DotNetOntology.TypeParamRels.ConstrainedToType), constraintIri);
        }
    }

    private void Log(string message)
    {
        if (_options.LogLevel >= LogLevel.Info)
            _log?.Invoke(message);
    }

    private void LogVerbose(string message)
    {
        if (_options.LogLevel >= LogLevel.Verbose)
            _log?.Invoke(message);
    }
}
