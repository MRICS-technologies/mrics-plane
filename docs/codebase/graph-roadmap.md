# Graph and Documentation Roadmap

This roadmap defines the four-layer hierarchy for Plane codebase documentation, the scopes it will cover, and the rules for producing graph-backed documentation. Everything below is **Planned** except the URL Routing Pilot, which is the only **Completed** graph.

Tracked-file counts are verified at base commit `743effede0380d7b9f64043cfd7c4295b89f16cd` (5,332 total tracked files). Counts describe scope only — they do not describe behavior, and no feature behavior should be inferred from them.

## Hierarchy

The documentation program is organized into four layers, from broadest to most focused:

1. **Repository architecture map** — a single graph of the whole repository.
2. **Application graphs** — one graph per application under `apps/`.
3. **Package graphs** — one graph per principal package under `packages/`.
4. **Domain deep dives** — focused graphs for cross-cutting domains that span applications and packages.

## Repository architecture map

Status: `Planned`.

A whole-repository graph covering all 5,332 tracked files. This is the foundation for whole-codebase coverage and is not yet generated.

## Application graphs

Status: `Planned`.

| Application | Tracked files |
| --- | --- |
| `apps/api/` | 733 |
| `apps/web/` | 2,366 |
| `apps/admin/` | 128 |
| `apps/space/` | 213 |
| `apps/live/` | 56 |
| `apps/proxy/` | 4 |

## Package graphs

Status: `Planned`.

| Package | Tracked files |
| --- | --- |
| `packages/i18n/` | 553 |
| `packages/propel/` | 397 |
| `packages/editor/` | 238 |
| `packages/ui/` | 135 |
| `packages/types/` | 124 |
| `packages/utils/` | 97 |
| `packages/constants/` | 64 |
| `packages/services/` | 59 |
| `packages/shared-state/` | 21 |

## Domain deep dives

Status: `Planned`.

Deep dives target bounded, cross-cutting domains and are scoped as they are prioritized. The URL Routing Pilot is the first example of this layer; additional dives (for example, the GitHub integration) are planned.

## Completed

### URL Routing Pilot

The only completed graph. Scope: the URL-routing subsystem under `apps/api/plane/app/urls/`.

| Metric | Value |
| --- | --- |
| File nodes | 22 |
| Class nodes | 1 |
| Total nodes | 23 |
| Edges | 23 |
| Layers | 2 |
| Guided-tour steps | 3 |

Artifact: [`apps/api/plane/app/urls/.ua/knowledge-graph.json`](../../apps/api/plane/app/urls/.ua/knowledge-graph.json)

The pilot is a bounded subsystem graph. It is not a whole-codebase graph.

## Rules

### Execution rule

Generate bounded graphs, review the artifact, validate it, commit only durable graph files, and then write or refresh the linked prose documentation.

### Accuracy rule

Never claim whole-codebase coverage until the repository architecture map and every planned component scope are generated and reviewed.
