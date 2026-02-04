namespace RoslynToRdf.Core.Model;

/// <summary>
/// RDF vocabulary constants for the .NET type ontology.
/// </summary>
public static class DotNetOntology
{
    public const string Prefix = "dt";
    
    // Standard prefixes
    public const string Rdf = "http://www.w3.org/1999/02/22-rdf-syntax-ns#";
    public const string Rdfs = "http://www.w3.org/2000/01/rdf-schema#";
    public const string Xsd = "http://www.w3.org/2001/XMLSchema#";

    // Classes
    public static class Classes
    {
        public const string Assembly = "Assembly";
        public const string Namespace = "Namespace";
        public const string Type = "Type";
        public const string Class = "Class";
        public const string Struct = "Struct";
        public const string Interface = "Interface";
        public const string Enum = "Enum";
        public const string Delegate = "Delegate";
        public const string Record = "Record";
        public const string Member = "Member";
        public const string Method = "Method";
        public const string Constructor = "Constructor";
        public const string Property = "Property";
        public const string Field = "Field";
        public const string Event = "Event";
        public const string Parameter = "Parameter";
        public const string TypeParameter = "TypeParameter";
        public const string Attribute = "Attribute";
    }

    // Type properties
    public static class TypeProps
    {
        public const string Name = "name";
        public const string FullName = "fullName";
        public const string TypeKind = "typeKind";
        public const string Accessibility = "accessibility";
        public const string IsAbstract = "isAbstract";
        public const string IsSealed = "isSealed";
        public const string IsStatic = "isStatic";
        public const string IsGeneric = "isGeneric";
        public const string IsValueType = "isValueType";
        public const string IsRecord = "isRecord";
        public const string IsRefLikeType = "isRefLikeType";
        public const string IsReadOnly = "isReadOnly";
        public const string IsUnmanagedType = "isUnmanagedType";
        public const string SpecialType = "specialType";
        public const string EnumUnderlyingType = "enumUnderlyingType";
    }

    // Type relationships
    public static class TypeRels
    {
        public const string DefinedInAssembly = "definedInAssembly";
        public const string InNamespace = "inNamespace";
        public const string Inherits = "inherits";
        public const string Implements = "implements";
        public const string NestedIn = "nestedIn";
        public const string HasMember = "hasMember";
        public const string HasTypeParameter = "hasTypeParameter";
        public const string HasAttribute = "hasAttribute";
        public const string GenericDefinition = "genericDefinition";
        public const string TypeArgument = "typeArgument";
        public const string ArrayElementType = "arrayElementType";
        public const string PointerElementType = "pointerElementType";
        public const string Throws = "throws";
        public const string RelatedTo = "relatedTo";
    }

    // Member properties
    public static class MemberProps
    {
        public const string Name = "name";
        public const string Accessibility = "accessibility";
        public const string IsStatic = "isStatic";
        public const string IsAbstract = "isAbstract";
        public const string IsVirtual = "isVirtual";
        public const string IsOverride = "isOverride";
        public const string IsSealed = "isSealed";
        public const string IsExtern = "isExtern";
        public const string IsAsync = "isAsync";
        public const string IsReadOnly = "isReadOnly";
        public const string IsConst = "isConst";
        public const string IsVolatile = "isVolatile";
        public const string IsRequired = "isRequired";
        public const string IsInitOnly = "isInitOnly";
        public const string HasGetter = "hasGetter";
        public const string HasSetter = "hasSetter";
        public const string GetterAccessibility = "getterAccessibility";
        public const string SetterAccessibility = "setterAccessibility";
        public const string ConstValue = "constValue";
        public const string IsExtensionMethod = "isExtensionMethod";
        public const string IsPartialDefinition = "isPartialDefinition";
        public const string MethodKind = "methodKind";
    }

    // Member relationships
    public static class MemberRels
    {
        public const string MemberOf = "memberOf";
        public const string ReturnType = "returnType";
        public const string PropertyType = "propertyType";
        public const string FieldType = "fieldType";
        public const string EventType = "eventType";
        public const string HasParameter = "hasParameter";
        public const string HasTypeParameter = "hasTypeParameter";
        public const string OverridesMethod = "overridesMethod";
        public const string ExplicitInterfaceImpl = "explicitInterfaceImplementation";
    }

    // Parameter properties
    public static class ParamProps
    {
        public const string Name = "name";
        public const string Ordinal = "ordinal";
        public const string IsOptional = "isOptional";
        public const string IsParams = "isParams";
        public const string IsThis = "isThis";
        public const string IsDiscard = "isDiscard";
        public const string RefKind = "refKind";
        public const string DefaultValue = "defaultValue";
        public const string HasExplicitDefaultValue = "hasExplicitDefaultValue";
    }

    // Parameter relationships
    public static class ParamRels
    {
        public const string ParameterType = "parameterType";
        public const string ParameterOf = "parameterOf";
    }

    // Type parameter properties
    public static class TypeParamProps
    {
        public const string Name = "name";
        public const string Ordinal = "ordinal";
        public const string Variance = "variance";
        public const string HasReferenceTypeConstraint = "hasReferenceTypeConstraint";
        public const string HasValueTypeConstraint = "hasValueTypeConstraint";
        public const string HasUnmanagedTypeConstraint = "hasUnmanagedTypeConstraint";
        public const string HasNotNullConstraint = "hasNotNullConstraint";
        public const string HasConstructorConstraint = "hasConstructorConstraint";
    }

    // Type parameter relationships
    public static class TypeParamRels
    {
        public const string TypeParameterOf = "typeParameterOf";
        public const string ConstrainedToType = "constrainedToType";
    }

    // Attribute properties and relationships
    public static class AttrProps
    {
        public const string AttributeClass = "attributeClass";
        public const string ConstructorArguments = "constructorArguments";
        public const string NamedArguments = "namedArguments";
    }

    public static class AttrRels
    {
        public const string AttributeOf = "attributeOf";
        public const string AttributeType = "attributeType";
    }

    // Assembly properties
    public static class AsmProps
    {
        public const string Name = "name";
        public const string Version = "version";
        public const string Culture = "culture";
        public const string PublicKeyToken = "publicKeyToken";
        public const string IsInteractive = "isInteractive";
    }

    // Namespace properties
    public static class NsProps
    {
        public const string Name = "name";
        public const string FullName = "fullName";
    }

    public static class NsRels
    {
        public const string ParentNamespace = "parentNamespace";
        public const string ContainsType = "containsType";
    }
}
