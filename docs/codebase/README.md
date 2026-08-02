# Plane Codebase Understanding

The goal of this documentation program is **maintainable, incremental codebase documentation backed by versioned Understand Anything graphs**. Instead of a single explanation of the whole repository that drifts out of date, each graph is a bounded, reviewable artifact that captures the architecture, components, and relationships of a specific scope. The prose in this section links to those graphs and stays in sync with them.

## Documentation map

| Artifact | Status | Link |
| --- | --- | --- |
| Architecture Map | Planned | [roadmap](./graph-roadmap.md#repository-architecture-map) |
| Application Graphs | Planned | [roadmap](./graph-roadmap.md#application-graphs) |
| Package Graphs | Planned | [roadmap](./graph-roadmap.md#package-graphs) |
| Domain Deep Dives | Planned | [roadmap](./graph-roadmap.md#domain-deep-dives) |
| URL Routing Pilot | Completed | [knowledge graph](../../apps/api/plane/app/urls/.ua/knowledge-graph.json) |

The [URL Routing Pilot](../../apps/api/plane/app/urls/.ua/knowledge-graph.json) is the first completed graph in this program. Its **23 nodes** cover only the **22-file URL-routing subsystem** under `apps/api/plane/app/urls/` — they do not cover the full repository.

See the [graph and documentation roadmap](./graph-roadmap.md) for the four-layer hierarchy, the verified scopes of each application and package, and the rules for generating, reviewing, validating, and committing new graphs.

## How this stays current

- **Graph artifacts are version-controlled.** Durable graph outputs (`knowledge-graph.json`, `meta.json`, and related files under each `.ua/` directory) are tracked in Git and travel with the code they describe.
- **Transient scratch data is ignored.** Intermediate and temporary analysis output (`.ua/intermediate/`, `.ua/tmp/`, `.ua/.trash-*/`) is git-ignored and never committed.
- **Changes require review and validation before merge.** Every new or refreshed graph is reviewed and validated as part of the change, and the linked prose documentation is written or refreshed in the same change.
