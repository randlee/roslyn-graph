(function (root, factory) {
    const api = factory();
    if (typeof module === 'object' && module.exports) {
        module.exports = api;
    }
    root.RdfGraphParser = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
    async function parse(text, N3) {
        if (!N3 || !N3.Parser) {
            throw new Error('The RDF parser could not be loaded. Check the network connection and reload the page.');
        }

        const graphData = {
            types: new Map(),
            namespaces: new Map(),
            relationships: [],
            members: new Map(),
            parameters: new Map()
        };
        const dtOntology = 'http://dotnet.example/ontology/';
        const rdfType = 'http://www.w3.org/1999/02/22-rdf-syntax-ns#type';
        const parser = new N3.Parser();
        const quads = [];

        await new Promise((resolve, reject) => {
            parser.parse(text, (error, quad) => {
                if (error) {
                    reject(error);
                } else if (quad) {
                    quads.push(quad);
                } else {
                    resolve();
                }
            });
        });

        // Turtle does not guarantee that rdf:type is serialized before other properties.
        for (const { subject, predicate, object } of quads) {
            if (subject.termType !== 'NamedNode' || predicate.value !== rdfType || object.termType !== 'NamedNode') continue;

            const subjectIri = subject.value;
            const typeName = object.value.replace(dtOntology, '');
            if (['Class', 'Interface', 'Struct', 'Enum'].includes(typeName)) {
                if (!graphData.types.has(subjectIri)) {
                    graphData.types.set(subjectIri, {
                        iri: subjectIri,
                        kind: typeName.toLowerCase(),
                        name: '',
                        namespace: '',
                        members: [],
                        inherits: [],
                        implements: []
                    });
                }
                graphData.types.get(subjectIri).kind = typeName.toLowerCase();
            }

            if (['Method', 'Property', 'Field', 'Event', 'Constructor'].includes(typeName)) {
                if (!graphData.members.has(subjectIri)) {
                    graphData.members.set(subjectIri, {
                        iri: subjectIri,
                        kind: typeName.toLowerCase(),
                        name: '',
                        returnType: '',
                        parameters: []
                    });
                }
                graphData.members.get(subjectIri).kind = typeName.toLowerCase();
            }

            if (typeName === 'Parameter' && !graphData.parameters.has(subjectIri)) {
                graphData.parameters.set(subjectIri, {
                    iri: subjectIri,
                    name: '',
                    parameterType: '',
                    ordinal: 0
                });
            }
        }

        for (const { subject, predicate, object } of quads) {
            if (subject.termType !== 'NamedNode' || predicate.value !== dtOntology + 'inNamespace' || object.termType !== 'NamedNode') continue;

            const subjectIri = subject.value;
            const namespaceIri = object.value;
            if (graphData.types.has(subjectIri)) {
                graphData.types.get(subjectIri).namespace = namespaceIri;
                if (!graphData.namespaces.has(namespaceIri)) {
                    graphData.namespaces.set(namespaceIri, { iri: namespaceIri, name: '', types: [] });
                }
                graphData.namespaces.get(namespaceIri).types.push(subjectIri);
            }
        }

        for (const { subject, predicate, object } of quads) {
            if (subject.termType !== 'NamedNode') continue;

            const subjectIri = subject.value;
            const predicateIri = predicate.value;
            const objectIri = object.termType === 'NamedNode' ? object.value : null;
            const objectLiteral = object.termType === 'Literal' ? object.value : null;

            if (predicateIri === dtOntology + 'name' && objectLiteral !== null) {
                if (graphData.types.has(subjectIri)) graphData.types.get(subjectIri).name = objectLiteral;
                if (graphData.members.has(subjectIri)) graphData.members.get(subjectIri).name = objectLiteral;
                if (graphData.parameters.has(subjectIri)) graphData.parameters.get(subjectIri).name = objectLiteral;
                if (graphData.namespaces.has(subjectIri)) graphData.namespaces.get(subjectIri).name = objectLiteral;
            } else if (predicateIri === dtOntology + 'returnType' && objectIri && graphData.members.has(subjectIri)) {
                graphData.members.get(subjectIri).returnType = objectIri;
            } else if (predicateIri === dtOntology + 'parameterType' && objectIri && graphData.parameters.has(subjectIri)) {
                graphData.parameters.get(subjectIri).parameterType = objectIri;
            } else if (predicateIri === dtOntology + 'ordinal' && objectLiteral !== null && graphData.parameters.has(subjectIri)) {
                graphData.parameters.get(subjectIri).ordinal = parseInt(objectLiteral, 10);
            } else if (predicateIri === dtOntology + 'hasParameter' && objectIri && graphData.members.has(subjectIri)) {
                graphData.members.get(subjectIri).parameters.push(objectIri);
            } else if (predicateIri === dtOntology + 'inherits' && objectIri && graphData.types.has(subjectIri)) {
                graphData.types.get(subjectIri).inherits.push(objectIri);
                graphData.relationships.push({ from: subjectIri, to: objectIri, type: 'inherits' });
            } else if (predicateIri === dtOntology + 'implements' && objectIri && graphData.types.has(subjectIri)) {
                graphData.types.get(subjectIri).implements.push(objectIri);
                graphData.relationships.push({ from: subjectIri, to: objectIri, type: 'implements' });
            } else if (predicateIri === dtOntology + 'hasMember' && objectIri && graphData.types.has(subjectIri)) {
                graphData.types.get(subjectIri).members.push(objectIri);
            }
        }

        return graphData;
    }

    return { parse };
});
