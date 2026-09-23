---
name: roslyn-graph-explore
description: Explore published Roslyn Graph/Oxigraph solution and view databases using ontology-aware SPARQL, bounded RDF extraction, and relationship visualizations. Use when asked to query a Roslyn Graph database, inspect types/interfaces/inheritance/members/dependencies, compare logical and physical versions, generate a graph payload, or render a Roslyn Graph visualization.
---

# Roslyn Graph Explore

Require a solution or view manifest/store path. Read its manifest first to identify membership, named graphs, source/package provenance, and whether a logical-type view is available.

Inspect ontology predicates used by the store when its schema version is uncertain. Treat physical assembly graphs as provenance truth. Use a logical view only when the requested analysis intentionally reconciles approved versions.

Build bounded SPARQL queries for interfaces and implementations, inheritance, members, dependencies, callers, attributes, assembly/package provenance, and physical-to-logical drill-down. Select distinct node and edge identities before constructing RDF for a viewer, because types can occur in multiple named graphs.

Export only the requested subgraph as Turtle or N-Quads, include physical provenance for every logical item, and render it through the viewer. Do not dump or visualize the entire database by default.
