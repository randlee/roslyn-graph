// Builds the "Copy for Claude" payload: the types currently on the graph, their members, the edges between
// them, the filters applied in the explorer, and the provenance (store, query or graph definition) the page
// was generated from, so a chat can re-query the same store. Format documented in the roslyn-graph-explore
// skill: reference/selection-format.md.
(function (root, factory) {
    const api = factory();
    if (typeof module === 'object' && module.exports) {
        module.exports = api;
    }
    root.RoslynGraphSelection = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
    const FORMAT = 'roslyn-graph-selection/1';
    const MEMBER_ORDER = ['constructor', 'property', 'method', 'field', 'event'];

    function parameterList(graphData, parameterIris, typeName) {
        return (parameterIris || [])
            .map(iri => graphData.parameters.get(iri))
            .filter(p => p)
            .sort((a, b) => a.ordinal - b.ordinal)
            .map(p => `${typeName(p.parameterType)} ${p.name}`.trim())
            .join(', ');
    }

    function memberSignature(graphData, member, typeName) {
        const type = member.returnType ? typeName(member.returnType) : '';
        switch (member.kind) {
            case 'constructor':
                return `${member.name}(${parameterList(graphData, member.parameters, typeName)})`;
            case 'method':
                return `${type || 'void'} ${member.name}(${parameterList(graphData, member.parameters, typeName)})`;
            case 'event':
                return `event ${type} ${member.name}`.replace(/\s+/g, ' ').trim();
            default:
                return `${type} ${member.name}`.trim();
        }
    }

    function describeType(graphData, iri, typeName) {
        const type = graphData.types.get(iri);
        const namespace = type.namespace ? graphData.namespaces.get(type.namespace) : null;
        const members = (type.members || [])
            .map(m => graphData.members.get(m))
            .filter(m => m && m.name)
            .sort((a, b) => MEMBER_ORDER.indexOf(a.kind) - MEMBER_ORDER.indexOf(b.kind) || a.name.localeCompare(b.name))
            .map(m => ({ kind: m.kind, signature: memberSignature(graphData, m, typeName) }));
        return {
            fullName: type.fullName || type.name,
            name: type.name,
            kind: type.kind,
            namespace: namespace ? namespace.name : '',
            inherits: (type.inherits || []).map(typeName),
            implements: (type.implements || []).map(typeName),
            members,
            iri
        };
    }

    // options: {
    //   typeIris: IRIs to include (the drawn nodes, or one selected type),
    //   scope: 'graph' | 'type',
    //   context: provenance object embedded in the page (or null),
    //   view: { visibleNamespaces, hiddenNamespaces, search, selectedType },
    //   typeName: iri -> display name (the explorer's getTypeName)
    // }
    function build(graphData, options) {
        const typeName = options.typeName;
        const included = new Set(options.typeIris.filter(iri => graphData.types.has(iri)));
        const types = [...included]
            .map(iri => describeType(graphData, iri, typeName))
            .sort((a, b) => a.fullName.localeCompare(b.fullName));
        const edges = graphData.relationships
            .filter(r => included.has(r.from) && (included.has(r.to) || options.scope === 'type'))
            .map(r => ({ from: typeName(r.from), to: typeName(r.to), kind: r.type }))
            .sort((a, b) => (a.from + a.kind + a.to).localeCompare(b.from + b.kind + b.to));
        const memberCount = types.reduce((sum, t) => sum + t.members.length, 0);
        return {
            format: FORMAT,
            note: 'Copied from the Roslyn Graph explorer. Paste into a chat and ask Claude to deep-dive these types '
                + '(roslyn-graph-explore skill, deep-dive workflow); context.source identifies the store to query.',
            scope: options.scope,
            context: options.context || null,
            view: options.view || {},
            summary: { types: types.length, members: memberCount, edges: edges.length },
            types,
            edges
        };
    }

    function toText(selection) {
        return JSON.stringify(selection, null, 1);
    }

    return { FORMAT, build, memberSignature, toText };
});
