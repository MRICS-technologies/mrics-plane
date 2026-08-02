# Plane Codebase Documentation

Navigation-first documentation for the Plane repository (the MRICS fork), backed by version-controlled Understand Anything knowledge graphs. The goal of this program is **maintainable, incremental codebase documentation**: each graph is a bounded, reviewable artifact that captures the architecture, components, and relationships of a specific scope, and the prose pages here link to those graphs and stay in sync with them.

## Scope and status

| Area | Status |
| --- | --- |
| Repository architecture landscape (root graph) | **Completed** — [`../../.ua/knowledge-graph.json`](../../.ua/knowledge-graph.json) |
| URL-routing pilot (domain graph) | **Completed** — [`../../apps/api/plane/app/urls/.ua/knowledge-graph.json`](../../apps/api/plane/app/urls/.ua/knowledge-graph.json) |
| Per-application and per-package component graphs | **Planned** — see the [graph roadmap](./graph-roadmap.md) |
| Prose documentation | Source-backed, incremental — pages below are written from manifests, entry points, and configuration only |

The root graph is a **top-level architecture landscape**: it records workspace/application boundaries, the five applications, the shared packages, and infrastructure/coordination boundaries. It does **not** contain component-level detail; the URL-routing graph under `apps/api/plane/app/urls/.ua/` is the authoritative source for that subsystem. The [`meta.json`](../../.ua/meta.json) for the root graph states this scope explicitly.

## Documentation map

| Page | What it covers |
| --- | --- |
| [Architecture map](./architecture.md) | Monorepo/workspace topology: apps, packages, operational and config boundaries, and what each graph level represents. |
| [Applications](./applications.md) | One source-backed subsection each for API, web, admin, space, live, and proxy. |
| [Backend (API)](./backend.md) | Django project entry points, URL-routing topology, app boundaries, the URL-routing pilot and its graph, and safe extension/testing guidance. |
| [Frontend](./frontend.md) | Web, admin, space, and live composition; how the frontend apps relate; shared package roles; development navigation. |
| [Packages](./packages.md) | Table of every tracked workspace package manifest under `packages/*/package.json` with declared name and role. |
| [Domains and integrations](./domains-and-integrations.md) | Documented cross-cutting domains and integrations, including pointers to the GitHub integration docs. |
| [Operations](./operations.md) | Developer/CI/container/deployment configuration map: compose files, root scripts, `deployments/`, `.github/`. |
| [Testing and contributing](./testing-and-contributing.md) | Workspace/test/lint/format navigation based on root scripts and CONTRIBUTING; how to validate docs and graphs. |
| [Maintenance](./maintenance.md) | Graph update policy, durable vs transient `.ua` files, evidence rules, review checklist, and the completeness definition. |
| [Graph and documentation roadmap](./graph-roadmap.md) | The four-layer graph hierarchy, planned scopes, and the rules for generating, reviewing, and committing graphs. |

## Graph artifacts

| Graph | Scope | Location |
| --- | --- | --- |
| Repository architecture landscape | Top-level monorepo/workspace boundaries | [`../../.ua/knowledge-graph.json`](../../.ua/knowledge-graph.json) |
| URL Routing Pilot | The 22-file URL-routing subsystem under `apps/api/plane/app/urls/` (23 nodes, 23 edges, 2 layers, 3 guided-tour steps) | [`../../apps/api/plane/app/urls/.ua/knowledge-graph.json`](../../apps/api/plane/app/urls/.ua/knowledge-graph.json) |

## Related documentation

- [Graph and documentation roadmap](./graph-roadmap.md) — hierarchy, scopes, generation/review rules.
- [GitHub integration](../github-integration/README.md) — the MRICS native GitHub App integration (operator setup, security boundaries, dev acceptance, rollback). This is a feature documentation set, separate from the codebase-understanding pages here.

## How this stays current

- **Graph artifacts are version-controlled.** Durable graph outputs (`knowledge-graph.json`, `meta.json`, and related files under each `.ua/` directory) are tracked in Git and travel with the code they describe (see [`../../.gitignore`](../../.gitignore), which ignores only `.ua/intermediate/`, `.ua/tmp/`, and `.ua/.trash-*/`).
- **Prose is source-backed.** Every technical assertion in these pages carries an explicit source path (manifest, entry point, or configuration file) or is marked `Not yet documented` / `Planned deep dive`.
- **Changes require review and validation.** See [Maintenance](./maintenance.md) for the checklist applied to every documentation or graph change.
