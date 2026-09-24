const assert = require('node:assert/strict');
const test = require('node:test');
const N3 = require('n3');
const { parse } = require('./rdf-graph-parser');
const selection = require('./graph-selection');

const turtle = `
@prefix dt: <http://dotnet.example/ontology/> .
@prefix rg: <http://roslyn-graph.example/ontology/> .
@prefix ex: <http://example.test/> .
ex:Ns dt:name "Contoso.Camera" .
ex:ICamera a dt:Interface ; dt:name "ICamera" ; dt:fullName "Contoso.Camera.ICamera" ; dt:inNamespace ex:Ns ;
    dt:implements ex:IDevice ; rg:references ex:Options ; dt:hasMember ex:Open, ex:Name, ex:Changed .
ex:IDevice a dt:Interface ; dt:name "IDevice" ; dt:fullName "Contoso.Camera.IDevice" ; dt:inNamespace ex:Ns .
ex:Options a dt:Class ; dt:name "Options" ; dt:fullName "Contoso.Camera.Options" ; dt:inNamespace ex:Ns .
ex:Open a dt:Method ; dt:name "Open" ; dt:returnType ex:Task ; dt:hasParameter ex:P0, ex:P1 .
ex:P0 a dt:Parameter ; dt:name "options" ; dt:ordinal 0 ; dt:parameterType ex:Options .
ex:P1 a dt:Parameter ; dt:name "timeout" ; dt:ordinal 1 ; dt:parameterType ex:Int .
ex:Name a dt:Property ; dt:name "Name" ; dt:propertyType ex:String .
ex:Changed a dt:Event ; dt:name "Changed" ; dt:eventType ex:Handler .
`;

// The explorer's getTypeName: graph types by name, others from the IRI tail.
function typeNameFor(graph) {
    return iri => (graph.types.get(iri) && graph.types.get(iri).name) || iri.split('/').pop();
}

test('builds a selection with signatures, edges, view and context', async () => {
    const graph = await parse(turtle, N3);
    const all = [...graph.types.keys()];
    const result = selection.build(graph, {
        typeIris: all, scope: 'graph',
        context: { generator: 'graph', source: { manifest: 'views/x/manifest.json' } },
        view: { visibleNamespaces: ['Contoso.Camera'], hiddenNamespaces: [], search: 'cam', selectedType: null },
        typeName: typeNameFor(graph)
    });
    assert.equal(result.format, 'roslyn-graph-selection/1');
    assert.deepEqual(result.summary, { types: 3, members: 3, edges: 2 });
    const camera = result.types.find(t => t.name === 'ICamera');
    assert.equal(camera.fullName, 'Contoso.Camera.ICamera');
    assert.equal(camera.namespace, 'Contoso.Camera');
    assert.deepEqual(camera.implements, ['IDevice']);
    assert.deepEqual(camera.members.map(m => m.signature), ['String Name', 'Task Open(Options options, Int timeout)', 'event Handler Changed']);
    assert.deepEqual(result.edges, [
        { from: 'ICamera', to: 'IDevice', kind: 'implements' },
        { from: 'ICamera', to: 'Options', kind: 'references' }
    ]);
    assert.equal(result.context.source.manifest, 'views/x/manifest.json');
    assert.equal(result.view.search, 'cam');
    assert.doesNotThrow(() => JSON.parse(selection.toText(result)));
});

test('type scope keeps edges to types outside the selection; graph scope drops them', async () => {
    const graph = await parse(turtle, N3);
    const camera = 'http://example.test/ICamera';
    const one = selection.build(graph, { typeIris: [camera], scope: 'type', typeName: typeNameFor(graph) });
    assert.equal(one.types.length, 1);
    assert.equal(one.edges.length, 2);
    const hidden = selection.build(graph, { typeIris: [camera], scope: 'graph', typeName: typeNameFor(graph) });
    assert.equal(hidden.edges.length, 0);
});
