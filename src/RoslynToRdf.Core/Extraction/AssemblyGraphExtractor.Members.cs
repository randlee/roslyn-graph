using Microsoft.CodeAnalysis;
using RoslynToRdf.Core.Model;

namespace RoslynToRdf.Core.Extraction;

public sealed partial class AssemblyGraphExtractor
{
    private void ExtractMethod(string typeIri, IMethodSymbol method)
    {
        var methodIri = _iris.Member(method);
        LogVerbose($"    Method: {method.Name}");

        var methodClass = method.MethodKind switch
        {
            MethodKind.Constructor or MethodKind.StaticConstructor => DotNetOntology.Classes.Constructor,
            _ => DotNetOntology.Classes.Method
        };

        _emitter.EmitIri(methodIri, RdfType, Prop(DotNetOntology.Classes.Member));
        _emitter.EmitIri(methodIri, RdfType, Prop(methodClass));
        _emitter.EmitLiteral(methodIri, Prop(DotNetOntology.MemberProps.Name), method.Name);
        _emitter.EmitLiteral(methodIri, Prop(DotNetOntology.MemberProps.Accessibility), method.DeclaredAccessibility.ToString());
        _emitter.EmitLiteral(methodIri, Prop(DotNetOntology.MemberProps.MethodKind), method.MethodKind.ToString());
        _emitter.EmitBool(methodIri, Prop(DotNetOntology.MemberProps.IsStatic), method.IsStatic);
        _emitter.EmitBool(methodIri, Prop(DotNetOntology.MemberProps.IsAbstract), method.IsAbstract);
        _emitter.EmitBool(methodIri, Prop(DotNetOntology.MemberProps.IsVirtual), method.IsVirtual);
        _emitter.EmitBool(methodIri, Prop(DotNetOntology.MemberProps.IsOverride), method.IsOverride);
        _emitter.EmitBool(methodIri, Prop(DotNetOntology.MemberProps.IsSealed), method.IsSealed);
        _emitter.EmitBool(methodIri, Prop(DotNetOntology.MemberProps.IsExtern), method.IsExtern);
        _emitter.EmitBool(methodIri, Prop(DotNetOntology.MemberProps.IsAsync), method.IsAsync);
        _emitter.EmitBool(methodIri, Prop(DotNetOntology.MemberProps.IsExtensionMethod), method.IsExtensionMethod);
        _emitter.EmitBool(methodIri, Prop(DotNetOntology.MemberProps.IsPartialDefinition), method.IsPartialDefinition);
        _emitter.EmitBool(methodIri, Prop(DotNetOntology.MemberProps.IsReadOnly), method.IsReadOnly);

        _emitter.EmitIri(typeIri, Prop(DotNetOntology.TypeRels.HasMember), methodIri);
        _emitter.EmitIri(methodIri, Prop(DotNetOntology.MemberRels.MemberOf), typeIri);

        if (!method.ReturnsVoid)
        {
            var returnTypeIri = EnsureTypeEmitted(method.ReturnType);
            _emitter.EmitIri(methodIri, Prop(DotNetOntology.MemberRels.ReturnType), returnTypeIri);
        }

        foreach (var tp in method.TypeParameters)
            ExtractTypeParameter(methodIri, method, tp);

        foreach (var param in method.Parameters)
            ExtractParameter(methodIri, method, param);

        if (method.OverriddenMethod != null)
            _emitter.EmitIri(methodIri, Prop(DotNetOntology.MemberRels.OverridesMethod), _iris.Member(method.OverriddenMethod));

        foreach (var impl in method.ExplicitInterfaceImplementations)
            _emitter.EmitIri(methodIri, Prop(DotNetOntology.MemberRels.ExplicitInterfaceImpl), _iris.Member(impl));

        if (_options.IncludeAttributes)
        {
            int attrIndex = 0;
            foreach (var attr in method.GetAttributes())
                ExtractAttribute(methodIri, method, attr, attrIndex++);
            foreach (var attr in method.GetReturnTypeAttributes())
                ExtractAttribute($"{methodIri}/return", method, attr, attrIndex++);
        }

        if (_xmlDocParser != null)
        {
            if (_options.ExtractExceptions)
                foreach (var exType in _xmlDocParser.GetExceptionTypes(method))
                    _emitter.EmitIri(methodIri, Prop(DotNetOntology.TypeRels.Throws), EnsureTypeEmitted(exType));
            if (_options.ExtractSeeAlso)
                foreach (var related in _xmlDocParser.GetSeeAlsoReferences(method))
                    _emitter.EmitIri(methodIri, Prop(DotNetOntology.TypeRels.RelatedTo), 
                        related is ITypeSymbol t ? EnsureTypeEmitted(t) : _iris.Member(related));
        }
    }

    private void ExtractProperty(string typeIri, IPropertySymbol prop)
    {
        var propIri = _iris.Member(prop);
        LogVerbose($"    Property: {prop.Name}");

        _emitter.EmitIri(propIri, RdfType, Prop(DotNetOntology.Classes.Member));
        _emitter.EmitIri(propIri, RdfType, Prop(DotNetOntology.Classes.Property));
        _emitter.EmitLiteral(propIri, Prop(DotNetOntology.MemberProps.Name), prop.Name);
        _emitter.EmitLiteral(propIri, Prop(DotNetOntology.MemberProps.Accessibility), prop.DeclaredAccessibility.ToString());
        _emitter.EmitBool(propIri, Prop(DotNetOntology.MemberProps.IsStatic), prop.IsStatic);
        _emitter.EmitBool(propIri, Prop(DotNetOntology.MemberProps.IsAbstract), prop.IsAbstract);
        _emitter.EmitBool(propIri, Prop(DotNetOntology.MemberProps.IsVirtual), prop.IsVirtual);
        _emitter.EmitBool(propIri, Prop(DotNetOntology.MemberProps.IsOverride), prop.IsOverride);
        _emitter.EmitBool(propIri, Prop(DotNetOntology.MemberProps.IsSealed), prop.IsSealed);
        _emitter.EmitBool(propIri, Prop(DotNetOntology.MemberProps.IsRequired), prop.IsRequired);
        _emitter.EmitBool(propIri, Prop(DotNetOntology.MemberProps.HasGetter), prop.GetMethod != null);
        _emitter.EmitBool(propIri, Prop(DotNetOntology.MemberProps.HasSetter), prop.SetMethod != null);

        if (prop.GetMethod != null)
            _emitter.EmitLiteral(propIri, Prop(DotNetOntology.MemberProps.GetterAccessibility), prop.GetMethod.DeclaredAccessibility.ToString());
        if (prop.SetMethod != null)
        {
            _emitter.EmitLiteral(propIri, Prop(DotNetOntology.MemberProps.SetterAccessibility), prop.SetMethod.DeclaredAccessibility.ToString());
            _emitter.EmitBool(propIri, Prop(DotNetOntology.MemberProps.IsInitOnly), prop.SetMethod.IsInitOnly);
        }

        _emitter.EmitIri(typeIri, Prop(DotNetOntology.TypeRels.HasMember), propIri);
        _emitter.EmitIri(propIri, Prop(DotNetOntology.MemberRels.MemberOf), typeIri);
        _emitter.EmitIri(propIri, Prop(DotNetOntology.MemberRels.PropertyType), EnsureTypeEmitted(prop.Type));

        foreach (var param in prop.Parameters)
            ExtractParameter(propIri, null, param);

        if (prop.OverriddenProperty != null)
            _emitter.EmitIri(propIri, Prop(DotNetOntology.MemberRels.OverridesMethod), _iris.Member(prop.OverriddenProperty));

        foreach (var impl in prop.ExplicitInterfaceImplementations)
            _emitter.EmitIri(propIri, Prop(DotNetOntology.MemberRels.ExplicitInterfaceImpl), _iris.Member(impl));

        if (_options.IncludeAttributes)
        {
            int attrIndex = 0;
            foreach (var attr in prop.GetAttributes())
                ExtractAttribute(propIri, prop, attr, attrIndex++);
        }

        if (_xmlDocParser != null && _options.ExtractSeeAlso)
            foreach (var related in _xmlDocParser.GetSeeAlsoReferences(prop))
                _emitter.EmitIri(propIri, Prop(DotNetOntology.TypeRels.RelatedTo), 
                    related is ITypeSymbol t ? EnsureTypeEmitted(t) : _iris.Member(related));
    }

    private void ExtractField(string typeIri, IFieldSymbol field)
    {
        var fieldIri = _iris.Member(field);
        LogVerbose($"    Field: {field.Name}");

        _emitter.EmitIri(fieldIri, RdfType, Prop(DotNetOntology.Classes.Member));
        _emitter.EmitIri(fieldIri, RdfType, Prop(DotNetOntology.Classes.Field));
        _emitter.EmitLiteral(fieldIri, Prop(DotNetOntology.MemberProps.Name), field.Name);
        _emitter.EmitLiteral(fieldIri, Prop(DotNetOntology.MemberProps.Accessibility), field.DeclaredAccessibility.ToString());
        _emitter.EmitBool(fieldIri, Prop(DotNetOntology.MemberProps.IsStatic), field.IsStatic);
        _emitter.EmitBool(fieldIri, Prop(DotNetOntology.MemberProps.IsReadOnly), field.IsReadOnly);
        _emitter.EmitBool(fieldIri, Prop(DotNetOntology.MemberProps.IsConst), field.IsConst);
        _emitter.EmitBool(fieldIri, Prop(DotNetOntology.MemberProps.IsVolatile), field.IsVolatile);
        _emitter.EmitBool(fieldIri, Prop(DotNetOntology.MemberProps.IsRequired), field.IsRequired);

        if (field.HasConstantValue)
            _emitter.EmitLiteral(fieldIri, Prop(DotNetOntology.MemberProps.ConstValue), field.ConstantValue?.ToString() ?? "null");

        _emitter.EmitIri(typeIri, Prop(DotNetOntology.TypeRels.HasMember), fieldIri);
        _emitter.EmitIri(fieldIri, Prop(DotNetOntology.MemberRels.MemberOf), typeIri);
        _emitter.EmitIri(fieldIri, Prop(DotNetOntology.MemberRels.FieldType), EnsureTypeEmitted(field.Type));

        if (_options.IncludeAttributes)
        {
            int attrIndex = 0;
            foreach (var attr in field.GetAttributes())
                ExtractAttribute(fieldIri, field, attr, attrIndex++);
        }
    }

    private void ExtractEvent(string typeIri, IEventSymbol evt)
    {
        var evtIri = _iris.Member(evt);
        LogVerbose($"    Event: {evt.Name}");

        _emitter.EmitIri(evtIri, RdfType, Prop(DotNetOntology.Classes.Member));
        _emitter.EmitIri(evtIri, RdfType, Prop(DotNetOntology.Classes.Event));
        _emitter.EmitLiteral(evtIri, Prop(DotNetOntology.MemberProps.Name), evt.Name);
        _emitter.EmitLiteral(evtIri, Prop(DotNetOntology.MemberProps.Accessibility), evt.DeclaredAccessibility.ToString());
        _emitter.EmitBool(evtIri, Prop(DotNetOntology.MemberProps.IsStatic), evt.IsStatic);
        _emitter.EmitBool(evtIri, Prop(DotNetOntology.MemberProps.IsAbstract), evt.IsAbstract);
        _emitter.EmitBool(evtIri, Prop(DotNetOntology.MemberProps.IsVirtual), evt.IsVirtual);
        _emitter.EmitBool(evtIri, Prop(DotNetOntology.MemberProps.IsOverride), evt.IsOverride);
        _emitter.EmitBool(evtIri, Prop(DotNetOntology.MemberProps.IsSealed), evt.IsSealed);

        _emitter.EmitIri(typeIri, Prop(DotNetOntology.TypeRels.HasMember), evtIri);
        _emitter.EmitIri(evtIri, Prop(DotNetOntology.MemberRels.MemberOf), typeIri);
        _emitter.EmitIri(evtIri, Prop(DotNetOntology.MemberRels.EventType), EnsureTypeEmitted(evt.Type));

        if (evt.OverriddenEvent != null)
            _emitter.EmitIri(evtIri, Prop(DotNetOntology.MemberRels.OverridesMethod), _iris.Member(evt.OverriddenEvent));

        foreach (var impl in evt.ExplicitInterfaceImplementations)
            _emitter.EmitIri(evtIri, Prop(DotNetOntology.MemberRels.ExplicitInterfaceImpl), _iris.Member(impl));

        if (_options.IncludeAttributes)
        {
            int attrIndex = 0;
            foreach (var attr in evt.GetAttributes())
                ExtractAttribute(evtIri, evt, attr, attrIndex++);
        }
    }

    private void ExtractParameter(string memberIri, IMethodSymbol? method, IParameterSymbol param)
    {
        var paramIri = method != null ? _iris.Parameter(method, param) : $"{memberIri}/param/{param.Ordinal}";

        _emitter.EmitIri(paramIri, RdfType, Prop(DotNetOntology.Classes.Parameter));
        _emitter.EmitLiteral(paramIri, Prop(DotNetOntology.ParamProps.Name), param.Name);
        _emitter.EmitInt(paramIri, Prop(DotNetOntology.ParamProps.Ordinal), param.Ordinal);
        _emitter.EmitBool(paramIri, Prop(DotNetOntology.ParamProps.IsOptional), param.IsOptional);
        _emitter.EmitBool(paramIri, Prop(DotNetOntology.ParamProps.IsParams), param.IsParams);
        _emitter.EmitBool(paramIri, Prop(DotNetOntology.ParamProps.IsThis), param.IsThis);
        _emitter.EmitBool(paramIri, Prop(DotNetOntology.ParamProps.IsDiscard), param.IsDiscard);
        _emitter.EmitLiteral(paramIri, Prop(DotNetOntology.ParamProps.RefKind), param.RefKind.ToString());
        _emitter.EmitBool(paramIri, Prop(DotNetOntology.ParamProps.HasExplicitDefaultValue), param.HasExplicitDefaultValue);

        if (param.HasExplicitDefaultValue)
            _emitter.EmitLiteral(paramIri, Prop(DotNetOntology.ParamProps.DefaultValue), param.ExplicitDefaultValue?.ToString() ?? "null");

        _emitter.EmitIri(memberIri, Prop(DotNetOntology.MemberRels.HasParameter), paramIri);
        _emitter.EmitIri(paramIri, Prop(DotNetOntology.ParamRels.ParameterOf), memberIri);
        _emitter.EmitIri(paramIri, Prop(DotNetOntology.ParamRels.ParameterType), EnsureTypeEmitted(param.Type));

        if (_options.IncludeAttributes)
        {
            int attrIndex = 0;
            foreach (var attr in param.GetAttributes())
                ExtractAttribute(paramIri, param, attr, attrIndex++);
        }
    }

    private void ExtractAttribute(string targetIri, ISymbol target, AttributeData attr, int index)
    {
        if (attr.AttributeClass == null) return;

        var attrIri = _iris.Attribute(target, attr, index);
        _emitter.EmitIri(attrIri, RdfType, Prop(DotNetOntology.Classes.Attribute));
        _emitter.EmitIri(targetIri, Prop(DotNetOntology.TypeRels.HasAttribute), attrIri);
        _emitter.EmitIri(attrIri, Prop(DotNetOntology.AttrRels.AttributeOf), targetIri);
        _emitter.EmitIri(attrIri, Prop(DotNetOntology.AttrRels.AttributeType), EnsureTypeEmitted(attr.AttributeClass));

        if (attr.ConstructorArguments.Length > 0)
            _emitter.EmitLiteral(attrIri, Prop(DotNetOntology.AttrProps.ConstructorArguments), 
                string.Join(", ", attr.ConstructorArguments.Select(FormatTypedConstant)));

        if (attr.NamedArguments.Length > 0)
            _emitter.EmitLiteral(attrIri, Prop(DotNetOntology.AttrProps.NamedArguments), 
                string.Join(", ", attr.NamedArguments.Select(kv => $"{kv.Key}={FormatTypedConstant(kv.Value)}")));
    }

    private static string FormatTypedConstant(TypedConstant tc)
    {
        if (tc.IsNull) return "null";
        if (tc.Kind == TypedConstantKind.Array)
            return $"[{string.Join(", ", tc.Values.Select(FormatTypedConstant))}]";
        if (tc.Kind == TypedConstantKind.Type && tc.Value is ITypeSymbol typeValue)
            return $"typeof({typeValue.ToDisplayString()})";
        if (tc.Value is string s) return $"\"{s}\"";
        return tc.Value?.ToString() ?? "null";
    }
}
