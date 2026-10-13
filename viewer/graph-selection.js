// Builds the "Copy for Claude" payload: the types on the graph plus a pointer to the database and the query
// that produced it, so a fresh chat can locate both and look everything else up itself. Format documented
// in the roslyn-graph-explore skill: reference/selection-format.md.
(function (root, factory) {
    const api = factory();
    if (typeof module === 'object' && module.exports) {
        module.exports = api;
    }
    root.RoslynGraphSelection = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
    const FORMAT = 'roslyn-graph-selection/2';

    // context: the provenance embedded in the page (roslyn-graph-context/1), or { generator: 'file', fileName }.
    function queryReference(context) {
        if (!context) return null;
        if (context.generator === 'graph' && context.definition) {
            return { kind: 'graph', title: context.definition.title, definition: context.definition.path };
        }
        if (context.generator === 'export' && context.query) {
            const reference = { kind: 'export' };
            if (context.query.file) reference.file = context.query.file;
            else reference.text = context.query.text; // inline query: nothing else to point to
            if (context.query.params && context.query.params.length) reference.params = context.query.params;
            if (context.query.logical) reference.logical = true;
            return reference;
        }
        if (context.generator === 'file') return { kind: 'file', fileName: context.fileName };
        return null;
    }

    // options: { typeIris: drawn nodes or the one selected type, context: page provenance or null }
    function build(graphData, options) {
        const context = options.context || null;
        const source = context && context.source;
        const types = options.typeIris
            .map(iri => graphData.types.get(iri))
            .filter(t => t)
            .map(t => t.fullName || t.name)
            .sort();
        const selection = { format: FORMAT };
        if (source) {
            selection.store = source.manifest;
            if (source.collection) selection.collection = source.collection;
        }
        const query = queryReference(context);
        if (query) selection.query = query;
        selection.types = [...new Set(types)];
        return selection;
    }

    function toText(selection) {
        return JSON.stringify(selection, null, 1);
    }

    return { FORMAT, build, queryReference, toText };
});
