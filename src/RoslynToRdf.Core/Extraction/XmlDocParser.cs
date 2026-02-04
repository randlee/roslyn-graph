using System.Xml;
using System.Xml.Linq;
using Microsoft.CodeAnalysis;

namespace RoslynToRdf.Core.Extraction;

/// <summary>
/// Parses XML documentation comments to extract exception and seealso references.
/// </summary>
public sealed class XmlDocParser
{
    private readonly Compilation _compilation;

    public XmlDocParser(Compilation compilation)
    {
        _compilation = compilation;
    }

    /// <summary>
    /// Extracts exception types from &lt;exception cref="..."&gt; elements.
    /// </summary>
    public IEnumerable<ITypeSymbol> GetExceptionTypes(ISymbol symbol)
    {
        var xml = symbol.GetDocumentationCommentXml();
        if (string.IsNullOrWhiteSpace(xml))
            yield break;

        XDocument? doc;
        try
        {
            doc = XDocument.Parse(xml);
        }
        catch (XmlException)
        {
            yield break;
        }

        var exceptionElements = doc.Descendants("exception");
        foreach (var elem in exceptionElements)
        {
            var cref = elem.Attribute("cref")?.Value;
            if (string.IsNullOrEmpty(cref))
                continue;

            var resolved = ResolveCref(cref);
            if (resolved is ITypeSymbol type)
                yield return type;
        }
    }

    /// <summary>
    /// Extracts related types from &lt;seealso cref="..."&gt; elements.
    /// </summary>
    public IEnumerable<ISymbol> GetSeeAlsoReferences(ISymbol symbol)
    {
        var xml = symbol.GetDocumentationCommentXml();
        if (string.IsNullOrWhiteSpace(xml))
            yield break;

        XDocument? doc;
        try
        {
            doc = XDocument.Parse(xml);
        }
        catch (XmlException)
        {
            yield break;
        }

        var seealsoElements = doc.Descendants("seealso");
        foreach (var elem in seealsoElements)
        {
            var cref = elem.Attribute("cref")?.Value;
            if (string.IsNullOrEmpty(cref))
                continue;

            var resolved = ResolveCref(cref);
            if (resolved != null)
                yield return resolved;
        }
    }

    /// <summary>
    /// Resolves a cref string to a symbol.
    /// Cref format: "T:Namespace.TypeName", "M:Namespace.TypeName.Method", etc.
    /// </summary>
    private ISymbol? ResolveCref(string cref)
    {
        if (string.IsNullOrEmpty(cref))
            return null;

        // Strip the prefix if present (T:, M:, P:, F:, E:, N:, !)
        var colonIndex = cref.IndexOf(':');
        string prefix;
        string name;

        if (colonIndex > 0 && colonIndex < 3)
        {
            prefix = cref[..colonIndex];
            name = cref[(colonIndex + 1)..];
        }
        else
        {
            // No prefix, try to resolve as-is
            prefix = "";
            name = cref;
        }

        // Handle error reference prefix (!)
        if (prefix == "!")
            return null;

        return prefix switch
        {
            "T" => ResolveType(name),
            "M" => ResolveMethod(name),
            "P" => ResolveProperty(name),
            "F" => ResolveField(name),
            "E" => ResolveEvent(name),
            "N" => null, // Namespaces aren't symbols we track as relationships
            "" => ResolveType(name) ?? ResolveMember(name),
            _ => null
        };
    }

    private ITypeSymbol? ResolveType(string name)
    {
        // Handle generic type parameters in name: System.Collections.Generic.List`1
        return _compilation.GetTypeByMetadataName(name);
    }

    private ISymbol? ResolveMethod(string name)
    {
        // Method names include parameters: Namespace.Type.Method(System.String,System.Int32)
        var parenIndex = name.IndexOf('(');
        string memberPath;
        string[]? paramTypes = null;

        if (parenIndex > 0)
        {
            memberPath = name[..parenIndex];
            var paramsPart = name[(parenIndex + 1)..].TrimEnd(')');
            if (!string.IsNullOrEmpty(paramsPart))
            {
                paramTypes = ParseParameterTypes(paramsPart);
            }
            else
            {
                paramTypes = Array.Empty<string>();
            }
        }
        else
        {
            memberPath = name;
        }

        return ResolveMemberOnType(memberPath, paramTypes);
    }

    private ISymbol? ResolveProperty(string name)
    {
        return ResolveMemberOnType(name, null);
    }

    private ISymbol? ResolveField(string name)
    {
        return ResolveMemberOnType(name, null);
    }

    private ISymbol? ResolveEvent(string name)
    {
        return ResolveMemberOnType(name, null);
    }

    private ISymbol? ResolveMember(string name)
    {
        return ResolveMemberOnType(name, null);
    }

    private ISymbol? ResolveMemberOnType(string memberPath, string[]? paramTypes)
    {
        // Split into type name and member name
        var lastDot = memberPath.LastIndexOf('.');
        if (lastDot < 0)
            return null;

        var typeName = memberPath[..lastDot];
        var memberName = memberPath[(lastDot + 1)..];

        // Handle explicit interface implementations: Type.Interface#Method
        memberName = memberName.Replace('#', '.');

        var type = ResolveType(typeName);
        if (type == null)
            return null;

        var members = type.GetMembers(memberName);
        if (members.Length == 0)
            return null;

        if (members.Length == 1 || paramTypes == null)
            return members[0];

        // Match by parameter types for overloaded methods
        foreach (var member in members)
        {
            if (member is IMethodSymbol method && MatchesParameters(method, paramTypes))
                return method;
        }

        return members[0]; // Fallback to first match
    }

    private static string[] ParseParameterTypes(string paramsPart)
    {
        // Simple parsing - doesn't handle all edge cases like nested generics
        var types = new List<string>();
        var depth = 0;
        var start = 0;

        for (int i = 0; i < paramsPart.Length; i++)
        {
            var c = paramsPart[i];
            switch (c)
            {
                case '{':
                case '<':
                case '[':
                    depth++;
                    break;
                case '}':
                case '>':
                case ']':
                    depth--;
                    break;
                case ',':
                    if (depth == 0)
                    {
                        types.Add(paramsPart[start..i].Trim());
                        start = i + 1;
                    }
                    break;
            }
        }

        if (start < paramsPart.Length)
            types.Add(paramsPart[start..].Trim());

        return types.ToArray();
    }

    private bool MatchesParameters(IMethodSymbol method, string[] paramTypes)
    {
        if (method.Parameters.Length != paramTypes.Length)
            return false;

        for (int i = 0; i < paramTypes.Length; i++)
        {
            var expectedType = paramTypes[i];
            var actualType = method.Parameters[i].Type;

            // Simple matching - compare display strings
            var actualName = actualType.ToDisplayString(SymbolDisplayFormat.FullyQualifiedFormat)
                .Replace("global::", "");

            if (!expectedType.Equals(actualName, StringComparison.Ordinal) &&
                !expectedType.Equals(actualType.MetadataName, StringComparison.Ordinal))
            {
                return false;
            }
        }

        return true;
    }
}
