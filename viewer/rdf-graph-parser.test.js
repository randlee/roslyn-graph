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

test('reads member types from returnType, propertyType, fieldType and eventType', async () => {
    const graph = await parse(`
@prefix dt: <http://dotnet.example/ontology/> .
@prefix ex: <http://example.test/> .
ex:T a dt:Interface ; dt:name "IThing" ; dt:hasMember ex:M, ex:P, ex:F, ex:E .
ex:M a dt:Method ; dt:name "Run" ; dt:returnType ex:Result ; dt:hasParameter ex:M0 .
ex:M0 a dt:Parameter ; dt:name "count" ; dt:ordinal 0 ; dt:parameterType ex:Int .
ex:P a dt:Property ; dt:name "Name" ; dt:propertyType ex:String .
ex:F a dt:Field ; dt:name "value" ; dt:fieldType ex:Int .
ex:E a dt:Event ; dt:name "Changed" ; dt:eventType ex:Handler .
`, N3);
    const type = graph.types.get('http://example.test/T');
    assert.equal(type.members.length, 4);
    assert.equal(graph.members.get('http://example.test/M').returnType, 'http://example.test/Result');
    assert.equal(graph.members.get('http://example.test/P').returnType, 'http://example.test/String');
    assert.equal(graph.members.get('http://example.test/F').returnType, 'http://example.test/Int');
    assert.equal(graph.members.get('http://example.test/E').returnType, 'http://example.test/Handler');
    assert.deepEqual(graph.members.get('http://example.test/M').parameters, ['http://example.test/M0']);
    assert.equal(graph.parameters.get('http://example.test/M0').ordinal, 0);
});
