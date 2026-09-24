const assert = require('node:assert/strict');
const test = require('node:test');
const N3 = require('n3');
const { parse } = require('./rdf-graph-parser');
const selection = require('./graph-selection');

const turtle = `
@prefix dt: <http://dotnet.example/ontology/> .
@prefix ex: <http://example.test/> .
ex:ICamera a dt:Interface ; dt:name "ICamera" ; dt:fullName "Contoso.Camera.ICamera" .
ex:ITaker a dt:Interface ; dt:name "ITaker" ; dt:fullName "Contoso.Camera.ITaker<T>" .
ex:Id a dt:Struct ; dt:name "CameraId" ; dt:fullName "Contoso.Camera.CameraId" .
`;

const source = {
    manifest: 'F:\\.roslyn-graph\\views\\abc\\manifest.json', store: 'F:\\.roslyn-graph\\views\\abc\\store.oxigraph',
    kind: 'view', artifactId: 'abc', collection: 'app_current'
};

test('a graph page copies its types, store and graph definition, nothing else', async () => {
    const graph = await parse(turtle, N3);
    const context = {
        format: 'roslyn-graph-context/1', generator: 'graph', source,
        definition: { path: 'F:\\ws\\.roslyn-graph\\graphs\\camera.graph.toml', title: 'Camera', text: 'schema_version = 1 …' },
        result: { types: 3 }
    };
    const copied = selection.build(graph, { typeIris: [...graph.types.keys()], context });
    assert.deepEqual(copied, {
        format: 'roslyn-graph-selection/2',
        store: source.manifest,
        collection: 'app_current',
        query: { kind: 'graph', title: 'Camera', definition: 'F:\\ws\\.roslyn-graph\\graphs\\camera.graph.toml' },
        types: ['Contoso.Camera.CameraId', 'Contoso.Camera.ICamera', 'Contoso.Camera.ITaker<T>']
    });
    assert.doesNotThrow(() => JSON.parse(selection.toText(copied)));
});

test('an export points at its query file and parameters; an inline query carries its text', () => {
    const fromFile = selection.queryReference({ generator: 'export', source,
        query: { file: 'q\\implementers.rq', params: ['INTERFACE=Contoso.ICamera'], text: 'CONSTRUCT …', logical: true } });
    assert.deepEqual(fromFile, { kind: 'export', file: 'q\\implementers.rq', params: ['INTERFACE=Contoso.ICamera'], logical: true });
    const inline = selection.queryReference({ generator: 'export', source, query: { file: null, params: [], text: 'CONSTRUCT { } WHERE { }' } });
    assert.deepEqual(inline, { kind: 'export', text: 'CONSTRUCT { } WHERE { }' });
});

test('one selected type; a hand-loaded file has no store', async () => {
    const graph = await parse(turtle, N3);
    const copied = selection.build(graph, { typeIris: ['http://example.test/ICamera'], context: { generator: 'file', fileName: 'x.nt' } });
    assert.deepEqual(copied, { format: 'roslyn-graph-selection/2', query: { kind: 'file', fileName: 'x.nt' }, types: ['Contoso.Camera.ICamera'] });
});
