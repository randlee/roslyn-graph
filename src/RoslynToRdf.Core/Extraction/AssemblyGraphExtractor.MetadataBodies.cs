using System.Collections.Immutable;
using System.Reflection.Emit;
using System.Reflection.Metadata;
using System.Reflection.Metadata.Ecma335;
using System.Reflection.PortableExecutable;
using Microsoft.CodeAnalysis;

namespace RoslynToRdf.Core.Extraction;

public sealed partial class AssemblyGraphExtractor
{
    private MetadataBodies? _metadataBodies;

    private void ExtractMetadataBodyDependencies(IMethodSymbol method, string ownerIri)
    {
        if (_peImagePath is null || _compilation is null || method.MetadataToken == 0)
            return;
        _metadataBodies ??= new MetadataBodies(this, _peImagePath, method.ContainingAssembly);
        _metadataBodies.Extract(method, ownerIri);
    }

    private void DisposeMetadataBodies()
    {
        _metadataBodies?.Dispose();
        _metadataBodies = null;
    }

    private sealed class MetadataBodies : ISignatureTypeProvider<BodyType, BodyContext>, IDisposable
    {
        private readonly AssemblyGraphExtractor _extractor;
        private readonly FileStream _stream;
        private readonly PEReader _pe;
        private readonly MetadataReader _reader;
        private readonly IAssemblySymbol _assembly;
        private readonly Dictionary<AssemblyReferenceHandle, IAssemblySymbol?> _assemblies = new();
        private readonly HashSet<(string Owner, MethodDefinitionHandle Method)> _visited = new();
        private static readonly Dictionary<ushort, OpCode> OpCodesByValue = typeof(OpCodes).GetFields()
            .Where(field => field.FieldType == typeof(OpCode))
            .Select(field => (OpCode)field.GetValue(null)!)
            .ToDictionary(opcode => unchecked((ushort)opcode.Value));

        public MetadataBodies(AssemblyGraphExtractor extractor, string path, IAssemblySymbol assembly)
        {
            _extractor = extractor;
            _assembly = assembly;
            _stream = File.OpenRead(path);
            try
            {
                _pe = new PEReader(_stream);
                _reader = _pe.GetMetadataReader();
                var definition = _reader.GetAssemblyDefinition();
                if (_reader.GetString(definition.Name) != assembly.Identity.Name
                    || definition.Version != assembly.Identity.Version)
                    throw new BadImageFormatException("Body image does not match the extracted assembly.");
            }
            catch
            {
                _stream.Dispose();
                throw;
            }
        }

        public void Dispose()
        {
            _pe.Dispose();
            _stream.Dispose();
        }

        public void Extract(IMethodSymbol symbol, string owner)
        {
            if (!SymbolEqualityComparer.Default.Equals(symbol.ContainingModule, _assembly.Modules.First()))
            {
                Unresolved($"multi-module body {symbol}");
                return;
            }
            var entity = MetadataTokens.EntityHandle(symbol.MetadataToken);
            if (entity.Kind != HandleKind.MethodDefinition)
                throw new BadImageFormatException("Expected an input-module method definition.");
            var root = (MethodDefinitionHandle)entity;
            if (IsGenerated(root))
                return;
            var pending = new Queue<(MethodDefinitionHandle Handle, BodyContext Context)>();
            pending.Enqueue((root, Context(symbol)));
            while (pending.TryDequeue(out var work))
            {
                if (!_visited.Add((owner, work.Handle)))
                    continue;
                var definition = _reader.GetMethodDefinition(work.Handle);
                EnqueueStateMachine(definition, pending, owner);
                if (definition.RelativeVirtualAddress == 0)
                    continue;
                var body = _pe.GetMethodBody(definition.RelativeVirtualAddress);
                if (!body.LocalSignature.IsNil)
                    Emit(owner, _reader.GetStandaloneSignature(body.LocalSignature)
                        .DecodeLocalSignature(this, work.Context));
                foreach (var region in body.ExceptionRegions)
                    if (region.Kind == ExceptionRegionKind.Catch)
                        Emit(owner, DecodeType(region.CatchType, work.Context));
                var il = body.GetILReader();
                while (il.RemainingBytes > 0)
                {
                    ushort value = il.ReadByte();
                    if (value == 0xfe)
                        value = (ushort)(0xfe00 | il.ReadByte());
                    if (!OpCodesByValue.TryGetValue(value, out var opcode))
                        throw new BadImageFormatException($"Unknown IL opcode 0x{value:x4}.");
                    switch (opcode.OperandType)
                    {
                        case OperandType.InlineType:
                        case OperandType.InlineTok:
                        case OperandType.InlineField:
                        case OperandType.InlineMethod:
                            var handle = MetadataTokens.EntityHandle(il.ReadInt32());
                            var target = EmitToken(owner, handle, work.Context);
                            if (!target.IsNil && IsGenerated(target)
                                && (opcode == OpCodes.Call || opcode == OpCodes.Callvirt
                                    || opcode == OpCodes.Newobj || opcode == OpCodes.Ldftn
                                    || opcode == OpCodes.Ldvirtftn))
                                pending.Enqueue((target, TokenContext(handle, work.Context)));
                            break;
                        case OperandType.InlineSig:
                            var signatureHandle = MetadataTokens.EntityHandle(il.ReadInt32());
                            if (signatureHandle.Kind != HandleKind.StandaloneSignature)
                                throw new BadImageFormatException("Invalid calli signature token.");
                            Emit(owner, _reader.GetStandaloneSignature((StandaloneSignatureHandle)signatureHandle)
                                .DecodeMethodSignature(this, work.Context));
                            break;
                        case OperandType.InlineSwitch:
                            var count = il.ReadInt32();
                            if (count < 0 || count > il.RemainingBytes / sizeof(int))
                                throw new BadImageFormatException("Invalid IL switch table.");
                            il.Offset += count * sizeof(int);
                            break;
                        default:
                            var width = opcode.OperandType switch
                            {
                                OperandType.InlineNone => 0,
                                OperandType.ShortInlineBrTarget or OperandType.ShortInlineI
                                    or OperandType.ShortInlineVar => 1,
                                OperandType.InlineVar => 2,
                                OperandType.InlineBrTarget or OperandType.InlineI
                                    or OperandType.ShortInlineR or OperandType.InlineString => 4,
                                OperandType.InlineI8 or OperandType.InlineR => 8,
                                _ => throw new BadImageFormatException($"Unsupported IL operand {opcode.OperandType}.")
                            };
                            if (width > il.RemainingBytes)
                                throw new BadImageFormatException("Truncated IL operand.");
                            il.Offset += width;
                            break;
                    }
                }
            }
        }

        private BodyContext Context(IMethodSymbol method) => new(
            TypeArguments(method.ContainingType), method.TypeArguments.Select(FromSymbol).ToImmutableArray());

        private ImmutableArray<BodyType> TypeArguments(INamedTypeSymbol type)
        {
            var outer = type.ContainingType is null ? ImmutableArray<BodyType>.Empty : TypeArguments(type.ContainingType);
            return outer.AddRange(type.TypeArguments.Select(FromSymbol));
        }

        private BodyContext TokenContext(EntityHandle handle, BodyContext caller)
        {
            if (handle.Kind == HandleKind.MethodSpecification)
            {
                var specification = _reader.GetMethodSpecification((MethodSpecificationHandle)handle);
                var basis = TokenContext(specification.Method, caller);
                return basis with { MethodArguments = specification.DecodeSignature(this, caller) };
            }
            if (handle.Kind == HandleKind.MemberReference)
            {
                var member = _reader.GetMemberReference((MemberReferenceHandle)handle);
                return new BodyContext(DecodeType(member.Parent, caller).Arguments, ImmutableArray<BodyType>.Empty);
            }
            if (handle.Kind == HandleKind.MethodDefinition)
            {
                var definition = _reader.GetMethodDefinition((MethodDefinitionHandle)handle);
                return new BodyContext(DecodeType(definition.GetDeclaringType(), caller).Arguments,
                    ImmutableArray<BodyType>.Empty);
            }
            return caller;
        }

        private MethodDefinitionHandle EmitToken(string owner, EntityHandle handle, BodyContext context)
        {
            switch (handle.Kind)
            {
                case HandleKind.TypeDefinition:
                case HandleKind.TypeReference:
                case HandleKind.TypeSpecification:
                    Emit(owner, DecodeType(handle, context));
                    return default;
                case HandleKind.MethodSpecification:
                    var specification = _reader.GetMethodSpecification((MethodSpecificationHandle)handle);
                    var arguments = specification.DecodeSignature(this, context);
                    Emit(owner, arguments);
                    return EmitToken(owner, specification.Method, context with { MethodArguments = arguments });
                case HandleKind.MethodDefinition:
                    var method = _reader.GetMethodDefinition((MethodDefinitionHandle)handle);
                    Emit(owner, DecodeType(method.GetDeclaringType(), context));
                    Emit(owner, method.DecodeSignature(this, context));
                    return (MethodDefinitionHandle)handle;
                case HandleKind.FieldDefinition:
                    var field = _reader.GetFieldDefinition((FieldDefinitionHandle)handle);
                    Emit(owner, DecodeType(field.GetDeclaringType(), context));
                    Emit(owner, field.DecodeSignature(this, context));
                    return default;
                case HandleKind.MemberReference:
                    var member = _reader.GetMemberReference((MemberReferenceHandle)handle);
                    var declaring = DecodeType(member.Parent, context);
                    Emit(owner, declaring);
                    var memberContext = context with { TypeArguments = declaring.Arguments };
                    if (member.GetKind() == MemberReferenceKind.Field)
                    {
                        Emit(owner, member.DecodeFieldSignature(this, memberContext));
                        return default;
                    }
                    var signature = member.DecodeMethodSignature(this, memberContext);
                    Emit(owner, signature);
                    return ResolveMethod(member, declaring, memberContext, signature);
                default:
                    throw new BadImageFormatException($"Unsupported body token kind {handle.Kind}.");
            }
        }

        private MethodDefinitionHandle ResolveMethod(MemberReference member, BodyType declaring, BodyContext context,
            MethodSignature<BodyType> signature)
        {
            if (declaring.Definition.IsNil)
                return default;
            var matches = new List<MethodDefinitionHandle>();
            foreach (var candidate in _reader.GetTypeDefinition(declaring.Definition).GetMethods())
            {
                var definition = _reader.GetMethodDefinition(candidate);
                if (!_reader.StringComparer.Equals(definition.Name, _reader.GetString(member.Name)))
                    continue;
                var candidateSignature = definition.DecodeSignature(this, context);
                if (candidateSignature.Header == signature.Header
                    && candidateSignature.GenericParameterCount == signature.GenericParameterCount
                    && EqualType(candidateSignature.ReturnType, signature.ReturnType)
                    && candidateSignature.ParameterTypes.Length == signature.ParameterTypes.Length
                    && candidateSignature.ParameterTypes.Zip(signature.ParameterTypes).All(pair => EqualType(pair.First, pair.Second)))
                    matches.Add(candidate);
            }
            if (matches.Count == 1)
                return matches[0];
            Unresolved($"input method reference {_reader.GetString(member.Name)} on {declaring.Named}");
            return default;
        }

        private static bool EqualType(BodyType left, BodyType right) => left.Key == right.Key;

        private bool IsGenerated(MethodDefinitionHandle handle)
        {
            var method = _reader.GetMethodDefinition(handle);
            if (HasAttribute(method.GetCustomAttributes(), "System.Runtime.CompilerServices.CompilerGeneratedAttribute"))
                return true;
            for (var type = method.GetDeclaringType(); !type.IsNil; type = _reader.GetTypeDefinition(type).GetDeclaringType())
                if (HasAttribute(_reader.GetTypeDefinition(type).GetCustomAttributes(),
                    "System.Runtime.CompilerServices.CompilerGeneratedAttribute"))
                    return true;
            return false;
        }

        private bool HasAttribute(CustomAttributeHandleCollection attributes, string name) =>
            attributes.Any(handle => AttributeName(_reader.GetCustomAttribute(handle)) == name);

        private string? AttributeName(CustomAttribute attribute)
        {
            var constructor = attribute.Constructor;
            var type = constructor.Kind switch
            {
                HandleKind.MethodDefinition => _reader.GetMethodDefinition((MethodDefinitionHandle)constructor).GetDeclaringType(),
                HandleKind.MemberReference => _reader.GetMemberReference((MemberReferenceHandle)constructor).Parent,
                _ => default
            };
            return MetadataName(type);
        }

        private void EnqueueStateMachine(MethodDefinition method,
            Queue<(MethodDefinitionHandle Handle, BodyContext Context)> pending, string owner)
        {
            foreach (var handle in method.GetCustomAttributes())
            {
                var attribute = _reader.GetCustomAttribute(handle);
                if (AttributeName(attribute) is not ("System.Runtime.CompilerServices.AsyncStateMachineAttribute"
                    or "System.Runtime.CompilerServices.IteratorStateMachineAttribute"
                    or "System.Runtime.CompilerServices.AsyncIteratorStateMachineAttribute"))
                    continue;
                var blob = _reader.GetBlobReader(attribute.Value);
                if (blob.ReadUInt16() != 1)
                    throw new BadImageFormatException("Invalid state-machine attribute.");
                var serialized = blob.ReadSerializedString();
                if (serialized is null)
                    throw new BadImageFormatException("Missing state-machine type.");
                var bracket = serialized.IndexOf('[');
                var comma = serialized.IndexOf(',');
                var end = bracket >= 0 ? bracket : comma >= 0 ? comma : serialized.Length;
                var typeName = serialized[..end];
                var matched = false;
                foreach (var typeHandle in _reader.TypeDefinitions)
                {
                    if (MetadataName(typeHandle) != typeName)
                        continue;
                    var bodyType = DecodeType(typeHandle, BodyContext.Empty);
                    Emit(owner, bodyType);
                    foreach (var candidate in _reader.GetTypeDefinition(typeHandle).GetMethods())
                    {
                        if (!_reader.StringComparer.Equals(_reader.GetMethodDefinition(candidate).Name, "MoveNext"))
                            continue;
                        pending.Enqueue((candidate, new BodyContext(bodyType.Arguments, ImmutableArray<BodyType>.Empty)));
                        matched = true;
                    }
                }
                if (!matched)
                    Unresolved($"state-machine body {serialized}");
            }
        }

        private string? MetadataName(EntityHandle handle)
        {
            if (handle.Kind == HandleKind.TypeDefinition)
            {
                var type = _reader.GetTypeDefinition((TypeDefinitionHandle)handle);
                var outer = type.GetDeclaringType();
                return outer.IsNil ? Qualify(type.Namespace, type.Name) : MetadataName(outer) + "+" + _reader.GetString(type.Name);
            }
            if (handle.Kind == HandleKind.TypeReference)
            {
                var type = _reader.GetTypeReference((TypeReferenceHandle)handle);
                return type.ResolutionScope.Kind == HandleKind.TypeReference
                    ? MetadataName(type.ResolutionScope) + "+" + _reader.GetString(type.Name) : Qualify(type.Namespace, type.Name);
            }
            return null;
        }

        private string Qualify(StringHandle space, StringHandle name) =>
            space.IsNil || _reader.GetString(space).Length == 0 ? _reader.GetString(name)
                : _reader.GetString(space) + "." + _reader.GetString(name);

        private BodyType DecodeType(EntityHandle handle, BodyContext context) => handle.Kind switch
        {
            HandleKind.TypeDefinition => GetTypeFromDefinition(_reader, (TypeDefinitionHandle)handle, 0),
            HandleKind.TypeReference => GetTypeFromReference(_reader, (TypeReferenceHandle)handle, 0),
            HandleKind.TypeSpecification => GetTypeFromSpecification(_reader, context, (TypeSpecificationHandle)handle, 0),
            _ => Missing($"type token {handle.Kind}")
        };

        public BodyType GetTypeFromDefinition(MetadataReader reader, TypeDefinitionHandle handle, byte rawTypeKind)
        {
            var name = MetadataName(handle)!;
            var symbol = _assembly.GetTypeByMetadataName(name);
            if (symbol is not null)
                return FromSymbol(symbol) with { Definition = handle };
            var definition = reader.GetTypeDefinition(handle);
            var arguments = definition.GetGenericParameters().Select(parameter =>
                BodyType.Empty with { Key = "!" + reader.GetGenericParameter(parameter).Index }).ToImmutableArray();
            return new BodyType(null, ImmutableArray<ITypeSymbol>.Empty, arguments, _assembly.Identity + ":" + name, handle);
        }

        public BodyType GetTypeFromReference(MetadataReader reader, TypeReferenceHandle handle, byte rawTypeKind)
        {
            var reference = reader.GetTypeReference(handle);
            var name = MetadataName(handle)!;
            IAssemblySymbol? assembly;
            switch (reference.ResolutionScope.Kind)
            {
                case HandleKind.AssemblyReference:
                    assembly = ResolveAssembly((AssemblyReferenceHandle)reference.ResolutionScope);
                    break;
                case HandleKind.ModuleDefinition:
                    assembly = _assembly;
                    break;
                case HandleKind.TypeReference:
                    var outer = GetTypeFromReference(reader, (TypeReferenceHandle)reference.ResolutionScope, 0).Named;
                    var nestedName = reader.GetString(reference.Name);
                    var symbol = outer?.GetTypeMembers().SingleOrDefault(type => type.MetadataName == nestedName);
                    return symbol is null ? Missing(name) : FromSymbol(symbol);
                default:
                    if (reference.ResolutionScope.IsNil)
                    {
                        var forwarded = _assembly.ResolveForwardedType(name);
                        return forwarded is null ? Missing($"forwarded {name}") : FromSymbol(forwarded);
                    }
                    return Missing($"{name} in unavailable scope {reference.ResolutionScope.Kind}");
            }
            var resolved = assembly?.GetTypeByMetadataName(name) ?? assembly?.ResolveForwardedType(name);
            return resolved is null ? Missing(name) : FromSymbol(resolved);
        }

        private IAssemblySymbol? ResolveAssembly(AssemblyReferenceHandle handle)
        {
            if (_assemblies.TryGetValue(handle, out var cached))
                return cached;
            var reference = _reader.GetAssemblyReference(handle);
            var identity = new AssemblyIdentity(_reader.GetString(reference.Name), reference.Version,
                reference.Culture.IsNil ? null : _reader.GetString(reference.Culture),
                _reader.GetBlobContent(reference.PublicKeyOrToken),
                (reference.Flags & System.Reflection.AssemblyFlags.PublicKey) != 0);
            var bound = _assembly.Modules.First().ReferencedAssemblies;
            var boundSymbols = _assembly.Modules.First().ReferencedAssemblySymbols;
            for (var index = 0; index < bound.Length; index++)
            {
                if (!bound[index].Equals(identity))
                    continue;
                _assemblies.Add(handle, boundSymbols[index]);
                return boundSymbols[index];
            }
            var candidates = _extractor._compilation!.References
                .Select(reference => _extractor._compilation.GetAssemblyOrModuleSymbol(reference))
                .OfType<IAssemblySymbol>().Concat(new[] { _extractor._compilation.Assembly })
                .Where(assembly => assembly.Identity.Equals(identity)).Distinct(SymbolEqualityComparer.Default)
                .Cast<IAssemblySymbol>().ToArray();
            var resolved = candidates.Length == 1 ? candidates[0] : null;
            if (resolved is null)
                Unresolved($"assembly {identity}");
            _assemblies.Add(handle, resolved);
            return resolved;
        }

        private BodyType FromSymbol(ITypeSymbol symbol)
        {
            if (symbol is ITypeParameterSymbol parameter)
                return BodyType.Empty with { Key = (parameter.TypeParameterKind == TypeParameterKind.Method ? "!!" : "!") + parameter.Ordinal };
            if (symbol is INamedTypeSymbol named)
            {
                var definition = SymbolEqualityComparer.Default.Equals(named.ContainingAssembly, _assembly)
                    && named.MetadataToken != 0
                    ? MetadataTokens.EntityHandle(named.MetadataToken) : default;
                return new BodyType(named, ImmutableArray.Create<ITypeSymbol>(named), TypeArguments(named),
                    named.ContainingAssembly.Identity + ":" + named.ToDisplayString(SymbolDisplayFormat.FullyQualifiedFormat),
                    definition.Kind == HandleKind.TypeDefinition ? (TypeDefinitionHandle)definition : default);
            }
            if (symbol is IArrayTypeSymbol array)
                return FromSymbol(array.ElementType);
            if (symbol is IPointerTypeSymbol pointer)
                return FromSymbol(pointer.PointedAtType);
            return new BodyType(null, ImmutableArray.Create(symbol), ImmutableArray<BodyType>.Empty);
        }

        private void Emit(string owner, BodyType type)
        {
            foreach (var symbol in type.Types)
                _extractor.EmitBodyType(owner, symbol);
        }

        private void Emit(string owner, IEnumerable<BodyType> types)
        {
            foreach (var type in types)
                Emit(owner, type);
        }

        private void Emit(string owner, MethodSignature<BodyType> signature)
        {
            Emit(owner, signature.ReturnType);
            Emit(owner, signature.ParameterTypes);
        }

        private void Unresolved(string detail) => _extractor.Log($"Unresolved metadata body dependency: {detail}");
        private BodyType Missing(string detail)
        {
            Unresolved(detail);
            return BodyType.Empty;
        }

        public BodyType GetTypeFromSpecification(MetadataReader reader, BodyContext genericContext,
            TypeSpecificationHandle handle, byte rawTypeKind) => reader.GetTypeSpecification(handle).DecodeSignature(this, genericContext);
        public BodyType GetArrayType(BodyType elementType, ArrayShape shape) => elementType with { Key = elementType.Key + "[" + shape.Rank + "]" };
        public BodyType GetByReferenceType(BodyType elementType) => elementType with { Key = elementType.Key + "&" };
        public BodyType GetPointerType(BodyType elementType) => elementType with { Key = elementType.Key + "*" };
        public BodyType GetSZArrayType(BodyType elementType) => elementType with { Key = elementType.Key + "[]" };
        public BodyType GetPinnedType(BodyType elementType) => elementType;
        public BodyType GetModifiedType(BodyType modifier, BodyType unmodifiedType, bool isRequired) =>
            unmodifiedType with { Types = unmodifiedType.Types.AddRange(modifier.Types),
                Key = unmodifiedType.Key + (isRequired ? "modreq(" : "modopt(") + modifier.Key + ")" };
        public BodyType GetGenericInstantiation(BodyType genericType, ImmutableArray<BodyType> typeArguments) =>
            new(genericType.Named, genericType.Types.AddRange(typeArguments.SelectMany(argument => argument.Types)), typeArguments,
                genericType.Key + "<" + string.Join(",", typeArguments.Select(argument => argument.Key)) + ">", genericType.Definition);
        public BodyType GetGenericMethodParameter(BodyContext genericContext, int index) =>
            index < genericContext.MethodArguments.Length ? genericContext.MethodArguments[index] : BodyType.Empty with { Key = "!!" + index };
        public BodyType GetGenericTypeParameter(BodyContext genericContext, int index) =>
            index < genericContext.TypeArguments.Length ? genericContext.TypeArguments[index] : BodyType.Empty with { Key = "!" + index };
        public BodyType GetFunctionPointerType(MethodSignature<BodyType> signature) =>
            new(null, signature.ReturnType.Types.AddRange(signature.ParameterTypes.SelectMany(parameter => parameter.Types)),
                ImmutableArray<BodyType>.Empty, "fnptr:" + signature.Header.RawValue + ":" + signature.ReturnType.Key
                    + "(" + string.Join(",", signature.ParameterTypes.Select(parameter => parameter.Key)) + ")");
        public BodyType GetPrimitiveType(PrimitiveTypeCode typeCode)
        {
            var special = typeCode switch
            {
                PrimitiveTypeCode.Void => SpecialType.System_Void,
                PrimitiveTypeCode.Boolean => SpecialType.System_Boolean,
                PrimitiveTypeCode.Char => SpecialType.System_Char,
                PrimitiveTypeCode.SByte => SpecialType.System_SByte,
                PrimitiveTypeCode.Byte => SpecialType.System_Byte,
                PrimitiveTypeCode.Int16 => SpecialType.System_Int16,
                PrimitiveTypeCode.UInt16 => SpecialType.System_UInt16,
                PrimitiveTypeCode.Int32 => SpecialType.System_Int32,
                PrimitiveTypeCode.UInt32 => SpecialType.System_UInt32,
                PrimitiveTypeCode.Int64 => SpecialType.System_Int64,
                PrimitiveTypeCode.UInt64 => SpecialType.System_UInt64,
                PrimitiveTypeCode.Single => SpecialType.System_Single,
                PrimitiveTypeCode.Double => SpecialType.System_Double,
                PrimitiveTypeCode.String => SpecialType.System_String,
                PrimitiveTypeCode.TypedReference => SpecialType.System_TypedReference,
                PrimitiveTypeCode.IntPtr => SpecialType.System_IntPtr,
                PrimitiveTypeCode.UIntPtr => SpecialType.System_UIntPtr,
                PrimitiveTypeCode.Object => SpecialType.System_Object,
                _ => throw new BadImageFormatException($"Unknown primitive type {typeCode}.")
            };
            return FromSymbol(_extractor._compilation!.GetSpecialType(special));
        }
    }

    private sealed record BodyType(INamedTypeSymbol? Named, ImmutableArray<ITypeSymbol> Types,
        ImmutableArray<BodyType> Arguments, string Key = "", TypeDefinitionHandle Definition = default)
    {
        public static BodyType Empty { get; } = new(null, ImmutableArray<ITypeSymbol>.Empty, ImmutableArray<BodyType>.Empty);
    }

    private sealed record BodyContext(ImmutableArray<BodyType> TypeArguments, ImmutableArray<BodyType> MethodArguments)
    {
        public static BodyContext Empty { get; } = new(ImmutableArray<BodyType>.Empty, ImmutableArray<BodyType>.Empty);
    }
}
