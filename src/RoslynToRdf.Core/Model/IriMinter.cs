using Microsoft.CodeAnalysis;
using System.Text;
using System.Text.RegularExpressions;

namespace RoslynToRdf.Core.Model;

/// <summary>
/// Generates consistent IRIs for .NET symbols in RDF graphs.
/// </summary>
public partial class IriMinter
{
    private readonly string _baseUri;

    public IriMinter(string baseUri = "http://dotnet.example/")
    {
        _baseUri = baseUri.TrimEnd('/');
    }

    public string BaseUri => _baseUri;
    public string OntologyPrefix => $"{_baseUri}/ontology/";

    /// <summary>
    /// IRI for an assembly.
    /// </summary>
    public string Assembly(IAssemblySymbol assembly)
    {
        var version = assembly.Identity.Version.ToString();
        return $"{_baseUri}/assembly/{Escape(assembly.Name)}/{Escape(version)}";
    }

    /// <summary>
    /// IRI for a namespace (global across assemblies).
    /// </summary>
    public string Namespace(INamespaceSymbol ns)
    {
        if (ns.IsGlobalNamespace)
            return $"{_baseUri}/namespace/_global_";
        return $"{_baseUri}/namespace/{Escape(ns.ToDisplayString())}";
    }

    /// <summary>
    /// IRI for a type, scoped to its containing assembly.
    /// </summary>
    public string Type(ITypeSymbol type)
    {
        var fullName = GetFullMetadataName(type);

        // Arrays and pointers have no containing assembly; scope them by their element's assembly so Foo[] and Foo*
        // from two assemblies, or two versions of one assembly, keep distinct identities.
        var asm = type.ContainingAssembly ?? ElementAssembly(type);
        if (asm is null)
        {
            // Special types like dynamic, void, function pointers, type-parameter arrays, etc.
            return $"{_baseUri}/type/_builtin_/{Escape(fullName)}";
        }

        var version = asm.Identity.Version.ToString();
        return $"{_baseUri}/type/{Escape(asm.Name)}/{Escape(version)}/{Escape(fullName)}";
    }

    /// <summary>
    /// IRI for a member (method, property, field, event).
    /// </summary>
    public string Member(ISymbol member)
    {
        var typeIri = Type(member.ContainingType);
        var sig = GetMemberSignature(member);
        return $"{typeIri}/member/{Escape(member.Name + sig)}";
    }

    /// <summary>
    /// IRI for a method parameter.
    /// </summary>
    public string Parameter(IMethodSymbol method, IParameterSymbol param)
    {
        var methodIri = Member(method);
        return $"{methodIri}/param/{param.Ordinal}";
    }

    /// <summary>
    /// IRI for a parameter owned by a method or an indexer property.
    /// </summary>
    public string Parameter(ISymbol owner, IParameterSymbol param)
    {
        var ownerIri = owner switch
        {
            IMethodSymbol method => Member(method),
            IPropertySymbol property => Member(property),
            _ => throw new ArgumentException($"Unexpected parameter owner type: {owner.GetType()}")
        };
        return $"{ownerIri}/param/{param.Ordinal}";
    }

    /// <summary>
    /// IRI for a type parameter.
    /// </summary>
    public string TypeParameter(ISymbol owner, ITypeParameterSymbol typeParam)
    {
        var ownerIri = owner switch
        {
            INamedTypeSymbol type => Type(type),
            IMethodSymbol method => Member(method),
            _ => throw new ArgumentException($"Unexpected owner type: {owner.GetType()}")
        };
        return $"{ownerIri}/typeparam/{typeParam.Ordinal}";
    }

    /// <summary>
    /// IRI for an attribute instance on a symbol.
    /// </summary>
    public string Attribute(ISymbol target, AttributeData attr, int index)
    {
        var targetIri = target switch
        {
            IAssemblySymbol asm => Assembly(asm),
            INamedTypeSymbol type => Type(type),
            IMethodSymbol method => Member(method),
            IPropertySymbol prop => Member(prop),
            IFieldSymbol field => Member(field),
            IEventSymbol evt => Member(evt),
            IParameterSymbol param => Parameter(param.ContainingSymbol, param),
            _ => throw new ArgumentException($"Unexpected target type: {target.GetType()}")
        };
        return Attribute(targetIri, index);
    }

    /// <summary>
    /// IRI for an attribute instance on an already minted target IRI.
    /// </summary>
    public string Attribute(string targetIri, int index)
    {
        var attributeIri = $"{targetIri}/attr/{index}";
        if (Uri.TryCreate(attributeIri, UriKind.Absolute, out var absoluteIri) && !absoluteIri.IsFile)
            return attributeIri;

        var baseUri = new Uri($"{_baseUri.TrimEnd('/')}/", UriKind.Absolute);
        return new Uri(baseUri, attributeIri.TrimStart('/')).AbsoluteUri;
    }

    /// <summary>
    /// Gets the full metadata name for a type, handling nested types and generics.
    /// </summary>
    private static string GetFullMetadataName(ITypeSymbol type, bool forMemberSignature = false)
    {
        if (type is IArrayTypeSymbol arrayType)
        {
            var suffix = arrayType.IsSZArray ? "[]"
                : arrayType.Rank == 1 ? "[*]"
                : $"[{new string(',', arrayType.Rank - 1)}]";
            return $"{GetFullMetadataName(arrayType.ElementType, forMemberSignature)}{suffix}";
        }

        if (type is IPointerTypeSymbol pointerType)
        {
            return $"{GetFullMetadataName(pointerType.PointedAtType, forMemberSignature)}*";
        }

        if (type is IFunctionPointerTypeSymbol functionPointer)
        {
            return GetFunctionPointerMetadataName(functionPointer, forMemberSignature);
        }

        if (type is ITypeParameterSymbol typeParam)
        {
            if (forMemberSignature)
            {
                if (typeParam.DeclaringMethod != null)
                    return $"``{typeParam.Ordinal}";

                var ordinal = typeParam.Ordinal;
                var containingType = typeParam.DeclaringType?.ContainingType;
                while (containingType != null)
                {
                    ordinal += containingType.Arity;
                    containingType = containingType.ContainingType;
                }
                return $"`{ordinal}";
            }

            // Include the declaring type or method to make type parameters unique
            var ownerPart = typeParam.DeclaringType != null
                ? GetFullMetadataName(typeParam.DeclaringType)
                : typeParam.DeclaringMethod?.ToDisplayString() ?? "";
            return $"T:{ownerPart}.{typeParam.Name}";
        }

        if (type is not INamedTypeSymbol namedType)
        {
            return type.ToDisplayString();
        }

        var sb = new StringBuilder();

        // Handle containing types (nested types)
        var containingTypes = new Stack<INamedTypeSymbol>();
        var current = namedType.ContainingType;
        while (current != null)
        {
            containingTypes.Push(current);
            current = current.ContainingType;
        }

        // Namespace
        var containingNamespace = namedType.ContainingNamespace;
        if (containingNamespace is { IsGlobalNamespace: false })
        {
            sb.Append(containingNamespace.ToDisplayString());
            sb.Append('.');
        }

        // Containing types
        foreach (var containing in containingTypes)
        {
            sb.Append(containing.Name);
            AppendTypeParameters(sb, containing, forMemberSignature);
            sb.Append('+');
        }

        // Type name
        sb.Append(namedType.Name);
        AppendTypeParameters(sb, namedType, forMemberSignature);

        return sb.ToString();
    }

    // Function-pointer types have no containing assembly of their own.  A metadata name alone is therefore not a
    // sufficient key: two referenced assemblies can each define the same constituent name.  Member signatures keep
    // their established ordinal-form keys; standalone function-pointer type keys include recursively bound identity.
    private static string GetFunctionPointerMetadataName(IFunctionPointerTypeSymbol pointer, bool forMemberSignature)
    {
        var signature = pointer.Signature;
        var constituent = forMemberSignature
            ? (Func<ITypeSymbol, string>)(type => GetFullMetadataName(type, true))
            : GetBoundConstituentIdentity;
        var conventions = string.Join(",", signature.UnmanagedCallingConventionTypes.Select(convention => constituent(convention)));
        var parameters = string.Join(",", signature.Parameters
            .Select(parameter => $"{parameter.RefKind}:{constituent(parameter.Type)}"));
        var returnType = constituent(signature.ReturnType);
        return $"delegate*{signature.CallingConvention}[{conventions}]({parameters})~{signature.RefKind}:{returnType}";
    }

    private static string GetBoundConstituentIdentity(ITypeSymbol type)
    {
        return type switch
        {
            IArrayTypeSymbol array => GetBoundConstituentIdentity(array.ElementType)
                + (array.IsSZArray ? "[]" : array.Rank == 1 ? "[*]" : $"[{new string(',', array.Rank - 1)}]"),
            IPointerTypeSymbol pointer => GetBoundConstituentIdentity(pointer.PointedAtType) + "*",
            IFunctionPointerTypeSymbol functionPointer => GetFunctionPointerMetadataName(functionPointer, false),
            ITypeParameterSymbol parameter => GetFullMetadataName(parameter),
            INamedTypeSymbol named => GetBoundNamedTypeIdentity(named),
            _ => GetFullMetadataName(type),
        };
    }

    private static string GetBoundNamedTypeIdentity(INamedTypeSymbol type)
    {
        var assembly = type.ContainingAssembly;
        var assemblyIdentity = assembly is null
            ? "_builtin_"
            : $"{assembly.Identity.Name},{assembly.Identity.Version}";
        return $"{assemblyIdentity}:{GetBoundNamedTypeName(type)}";
    }

    // Namespace.Outer`1[args]+Inner`1[args]: each level carries its own bound type arguments, so a nested type keeps
    // the constructed arguments of the types that contain it (Outer<Left>.Inner and Outer<Right>.Inner stay distinct).
    // Levels without constructed arguments produce the same text as the definition's metadata name.
    private static string GetBoundNamedTypeName(INamedTypeSymbol type)
    {
        var sb = new StringBuilder();
        if (type.ContainingType is { } containing)
            sb.Append(GetBoundNamedTypeName(containing)).Append('+');
        else if (type.ContainingNamespace is { IsGlobalNamespace: false } ns)
            sb.Append(ns.ToDisplayString()).Append('.');
        sb.Append(type.Name);
        if (type.Arity > 0)
        {
            sb.Append('`').Append(type.Arity);
            if (!type.IsUnboundGenericType && !type.TypeArguments.All(argument => argument is ITypeParameterSymbol))
                sb.Append('[').Append(string.Join(",", type.TypeArguments.Select(GetBoundConstituentIdentity))).Append(']');
        }
        return sb.ToString();
    }

    // The assembly that owns the type at the core of an array or pointer: a named type's assembly, or a type
    // parameter's owner assembly (Left's Owner<T>.T[] and Right's must not merge). Null for function pointers and
    // dynamic, which keep _builtin_.
    private static IAssemblySymbol? ElementAssembly(ITypeSymbol type) => type switch
    {
        IArrayTypeSymbol array => ElementAssembly(array.ElementType),
        IPointerTypeSymbol pointer => ElementAssembly(pointer.PointedAtType),
        INamedTypeSymbol named => named.ContainingAssembly,
        ITypeParameterSymbol parameter => parameter.ContainingAssembly,
        _ => null,
    };

    // A constructed type's IRI is scoped by its own assembly, so a type argument from that same assembly keeps the
    // established unqualified form (List`1[System.Int32]); an argument from any other assembly is qualified with its
    // assembly name and version, so List<Left.Arg> and List<Right.Arg> do not merge.
    private static string GetTypeArgumentIdentity(ITypeSymbol argument, IAssemblySymbol? context)
    {
        var name = GetFullMetadataName(argument);
        var assembly = argument.ContainingAssembly ?? ElementAssembly(argument);
        return assembly is null || SymbolEqualityComparer.Default.Equals(assembly, context)
            ? name
            : $"[{assembly.Identity.Name},{assembly.Identity.Version}]{name}";
    }

    private static void AppendTypeParameters(StringBuilder sb, INamedTypeSymbol type, bool forMemberSignature)
    {
        if (type.TypeParameters.Length == 0 && type.TypeArguments.Length == 0)
            return;

        sb.Append('`');
        sb.Append(type.TypeParameters.Length > 0 ? type.TypeParameters.Length : type.TypeArguments.Length);

        if (type.TypeArguments.Length > 0 && (forMemberSignature || !type.TypeArguments.All(t => t is ITypeParameterSymbol)))
        {
            sb.Append('[');
            for (int i = 0; i < type.TypeArguments.Length; i++)
            {
                if (i > 0) sb.Append(',');
                sb.Append(forMemberSignature
                    ? GetFullMetadataName(type.TypeArguments[i], true)
                    : GetTypeArgumentIdentity(type.TypeArguments[i], type.ContainingAssembly));
            }
            sb.Append(']');
        }
    }

    /// <summary>
    /// Gets a unique signature for a member to disambiguate overloads.
    /// </summary>
    private static string GetMemberSignature(ISymbol member)
    {
        if (member is IMethodSymbol method)
        {
            var sb = new StringBuilder();
            if (method.Arity > 0)
            {
                sb.Append("``");
                sb.Append(method.Arity);
            }
            sb.Append('(');
            for (int i = 0; i < method.Parameters.Length; i++)
            {
                if (i > 0) sb.Append(',');

                // Include ref/out/in modifiers
                var param = method.Parameters[i];
                if (param.RefKind == RefKind.Ref)
                    sb.Append("ref ");
                else if (param.RefKind == RefKind.Out)
                    sb.Append("out ");
                else if (param.RefKind == RefKind.In)
                    sb.Append("in ");

                sb.Append(GetFullMetadataName(param.Type, forMemberSignature: true));
            }
            sb.Append(')');
            if (method.MethodKind == MethodKind.Conversion)
            {
                sb.Append('~');
                sb.Append(GetFullMetadataName(method.ReturnType, forMemberSignature: true));
            }
            return sb.ToString();
        }

        if (member is IPropertySymbol prop && prop.IsIndexer)
        {
            var sb = new StringBuilder();
            sb.Append('[');
            for (int i = 0; i < prop.Parameters.Length; i++)
            {
                if (i > 0) sb.Append(',');
                sb.Append(GetFullMetadataName(prop.Parameters[i].Type, forMemberSignature: true));
            }
            sb.Append(']');
            return sb.ToString();
        }

        return string.Empty;
    }

    /// <summary>
    /// Escapes a string for use in an IRI.
    /// </summary>
    private static string Escape(string value)
    {
        // IRI-safe escaping: encode characters that aren't allowed in IRIs
        var sb = new StringBuilder();
        foreach (var c in value)
        {
            if (char.IsLetterOrDigit(c) || c == '-' || c == '_' || c == '.' || c == '~')
            {
                sb.Append(c);
            }
            else
            {
                // Percent-encode
                foreach (var b in Encoding.UTF8.GetBytes(c.ToString()))
                {
                    sb.Append('%');
                    sb.Append(b.ToString("X2"));
                }
            }
        }
        return sb.ToString();
    }
}
