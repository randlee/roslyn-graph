const assert = require('node:assert/strict');
const test = require('node:test');
const N3 = require('n3');
const { parse } = require('./rdf-graph-parser');

const compactTurtle = `
@prefix dt: <http://dotnet.example/ontology/> .
@prefix ex: <http://example.test/> .

ex:IChild dt:name "IChild" ;
    a dt:Interface ;
    dt:implements ex:IBase ;
    dt:inNamespace ex:Sample .

ex:IBase dt:name "IBase" ;
    a dt:Interface ;
    dt:inNamespace ex:Sample .

ex:Sample dt:name "Sample" .
`;

test('parses compact Turtle even when names precede rdf:type', async () => {
    const graph = await parse(compactTurtle, N3);
    const child = graph.types.get('http://example.test/IChild');

    assert.equal(graph.types.size, 2);
    assert.equal(child.name, 'IChild');
    assert.equal(child.kind, 'interface');
    assert.equal(child.namespace, 'http://example.test/Sample');
    assert.deepEqual(child.implements, ['http://example.test/IBase']);
    assert.equal(graph.namespaces.get('http://example.test/Sample').name, 'Sample');
    assert.deepEqual(graph.relationships, [{
        from: 'http://example.test/IChild',
        to: 'http://example.test/IBase',
        type: 'implements'
    }]);
});

test('reports invalid RDF instead of producing a partial graph', async () => {
    await assert.rejects(() => parse('@prefix broken:', N3));
});

test('reads rg:references as a references relationship between types', async () => {
    const graph = await parse(`
@prefix dt: <http://dotnet.example/ontology/> .
@prefix rg: <http://roslyn-graph.example/ontology/> .
@prefix ex: <http://example.test/> .
ex:Service a dt:Class ; dt:name "Service" ; rg:references ex:Options .
ex:Options a dt:Class ; dt:name "Options" .
`, N3);
    assert.deepEqual(graph.relationships, [{
        from: 'http://example.test/Service',
        to: 'http://example.test/Options',
        type: 'references'
    }]);
});
