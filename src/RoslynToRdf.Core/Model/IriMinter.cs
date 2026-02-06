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
    public string OntologyPrefix => "http://typegraph.example/ontology/";
    public string DotNetOntologyPrefix => $"{_baseUri}/ontology/";

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
        
        if (type.ContainingAssembly is null)
        {
            // Special types like dynamic, void, etc.
            return $"{_baseUri}/type/_builtin_/{Escape(fullName)}";
        }

        var asm = type.ContainingAssembly;
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
        return $"{typeIri}/member/{Escape(member.Name)}{sig}";
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
            IParameterSymbol param => Parameter((IMethodSymbol)param.ContainingSymbol, param),
            _ => throw new ArgumentException($"Unexpected target type: {target.GetType()}")
        };
        return $"{targetIri}/attr/{index}";
    }

    /// <summary>
    /// Gets the full metadata name for a type, handling nested types and generics.
    /// </summary>
    private static string GetFullMetadataName(ITypeSymbol type)
    {
        if (type is IArrayTypeSymbol arrayType)
        {
            return $"{GetFullMetadataName(arrayType.ElementType)}[]";
        }

        if (type is IPointerTypeSymbol pointerType)
        {
            return $"{GetFullMetadataName(pointerType.PointedAtType)}*";
        }

        if (type is ITypeParameterSymbol typeParam)
        {
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
        if (!namedType.ContainingNamespace.IsGlobalNamespace)
        {
            sb.Append(namedType.ContainingNamespace.ToDisplayString());
            sb.Append('.');
        }

        // Containing types
        foreach (var containing in containingTypes)
        {
            sb.Append(containing.Name);
            AppendTypeParameters(sb, containing);
            sb.Append('+');
        }

        // Type name
        sb.Append(namedType.Name);
        AppendTypeParameters(sb, namedType);

        return sb.ToString();
    }

    private static void AppendTypeParameters(StringBuilder sb, INamedTypeSymbol type)
    {
        if (type.TypeParameters.Length == 0 && type.TypeArguments.Length == 0)
            return;

        sb.Append('`');
        sb.Append(type.TypeParameters.Length > 0 ? type.TypeParameters.Length : type.TypeArguments.Length);

        // If this is a constructed generic, include the type arguments
        if (type.TypeArguments.Length > 0 && !type.TypeArguments.All(t => t is ITypeParameterSymbol))
        {
            sb.Append('[');
            for (int i = 0; i < type.TypeArguments.Length; i++)
            {
                if (i > 0) sb.Append(',');
                sb.Append(GetFullMetadataName(type.TypeArguments[i]));
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

                sb.Append(GetFullMetadataName(param.Type));
            }
            sb.Append(')');
            return sb.ToString();
        }

        if (member is IPropertySymbol prop && prop.IsIndexer)
        {
            var sb = new StringBuilder();
            sb.Append('[');
            for (int i = 0; i < prop.Parameters.Length; i++)
            {
                if (i > 0) sb.Append(',');
                sb.Append(GetFullMetadataName(prop.Parameters[i].Type));
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
