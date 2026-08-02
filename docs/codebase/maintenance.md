# Maintenance

How the codebase documentation and its Understand Anything graphs stay current: the graph update policy, what is durable vs transient in `.ua/` directories, evidence rules for prose, the review checklist, and the definition of "complete documentation".

## Graph update policy

The documentation program is graph-first: prose links to version-controlled graphs and stays in sync with them. The policy (also summarized in [graph-roadmap.md](./graph-roadmap.md#rules)):

1. **Generate bounded graphs.** Each graph covers a clearly scoped subsystem — a repository landscape, an application, a package, or a domain deep dive. Scope comes from the [roadmap](./graph-roadmap.md) hierarchy.
2. **Review the artifact.** The graph JSON is a reviewable deliverable: check node/edge accuracy against the source it describes before committing.
3. **Validate it.** Confirm the graph's metrics (node/edge/layer/tour counts) and that paths resolve to real files. The existing completed graphs are the format reference: root landscape ([`../../.ua/knowledge-graph.json`](../../.ua/knowledge-graph.json)) and the URL Routing Pilot ([`../../apps/api/plane/app/urls/.ua/knowledge-graph.json`](../../apps/api/plane/app/urls/.ua/knowledge-graph.json)).
4. **Commit only durable files.** See the next section.
5. **Write or refresh linked prose in the same change.** A graph without its navigation page is not "done" (see completeness below).

When source changes invalidate a committed graph (e.g. the URL-routing subsystem gains a module), refresh the graph and its prose in the same change rather than letting them drift.

## Durable vs transient `.ua` files

Each analyzed scope keeps its artifacts under a `.ua/` directory:

- **Durable (committed)**: `knowledge-graph.json`, `meta.json`, `fingerprints.json`, `config.json`, `.understandignore`. These are tracked in Git — `git ls-files` shows `.ua/knowledge-graph.json`, `.ua/meta.json`, `.ua/fingerprints.json`, `.ua/config.json`, `.ua/.understandignore`, and the same set under `apps/api/plane/app/urls/.ua/`.
- **Transient (ignored)**: intermediate and temporary analysis output. Root [`.gitignore`](../../.gitignore) ignores `**/.ua/intermediate/`, `**/.ua/tmp/`, and `**/.ua/.trash-*/`. These are never committed.
- The URL pilot's `meta.json` records the analyzed-at timestamp and git commit hash, and the root `meta.json` additionally states the graph's scope ("top-level repository architecture landscape… does NOT replace scoped application/domain graphs"). Keep `meta.json` accurate when refreshing a graph.

## Evidence rules

Prose in `docs/codebase/` is source-backed:

- Every technical assertion carries an explicit source path in surrounding text, or is directly observable from a referenced manifest/config (e.g. `apps/web/package.json`, `docker-compose.yml`, `plane/urls.py`).
- **Never** turn assumptions into facts. Use `Not yet documented` / `Planned deep dive` / `Planned` where evidence is missing (see [domains-and-integrations.md](./domains-and-integrations.md) and [backend.md](./backend.md) for examples).
- **Never** include secrets, endpoint credentials, personal data, raw environment values, or unverified production information. This repo's docs must remain safe to read by any contributor.
- Prefer source paths over paraphrases: a claim like "web is served by nginx on 3000" must cite `Dockerfile.web`/`nginx.conf`, as in [applications.md](./applications.md).
- Do not duplicate feature docs: GitHub integration details live in [../github-integration/](../github-integration/) and are linked, not restated ([domains-and-integrations.md](./domains-and-integrations.md)).

## Review checklist

Apply to every change touching `docs/codebase/` or a `.ua/` graph artifact:

- [ ] Scope statement updated where needed ([README.md](./README.md) status table).
- [ ] All technical claims carry source paths; unknowns are marked.
- [ ] Relative links resolve (root graph `../../.ua/knowledge-graph.json`, URL pilot `../../apps/api/plane/app/urls/.ua/knowledge-graph.json`, sibling pages, `../github-integration/README.md`).
- [ ] No secrets, env values, or unverified production state.
- [ ] No duplication of the GitHub integration pages.
- [ ] Only durable `.ua/` files staged; transient dirs ignored.
- [ ] `git diff --check` passes; formatting consistent with `oxfmt` (Markdown is in the lint-staged globs).
- [ ] Graph refreshes accompanied by matching prose updates in the same change.

## Documentation completeness definition

"Complete documentation" does **not** mean every line of code has an explanation. A system area is complete when:

- it has a maintained navigation page in this set (linked from [README.md](./README.md)), and
- it has a planned or completed graph status recorded in the [roadmap](./graph-roadmap.md), and
- its page states its scope, links its graph (if completed), and marks unknown areas.

Per the roadmap's accuracy rule: never claim whole-codebase coverage until the repository architecture map and every planned component scope are generated and reviewed.

## Current completeness snapshot

| Area | Navigation page | Graph status |
| --- | --- | --- |
| Repository architecture landscape | [architecture.md](./architecture.md) | Completed (root graph) |
| URL routing subsystem | [backend.md](./backend.md#the-url-routing-pilot) | Completed (URL Routing Pilot) |
| Applications (api/web/admin/space/live/proxy) | [applications.md](./applications.md) | Planned per-app graphs |
| Frontend composition | [frontend.md](./frontend.md) | Planned |
| Packages | [packages.md](./packages.md) | Root graph covers 9 principal packages; 6 more tracked packages un-graphed |
| Domains & integrations | [domains-and-integrations.md](./domains-and-integrations.md) | Deep dives planned |
| Operations | [operations.md](./operations.md) | n/a (config map) |
| Testing & contributing | [testing-and-contributing.md](./testing-and-contributing.md) | n/a (config map) |

## Where to look next

- [README.md](./README.md) — index and scope/status.
- [Graph roadmap](./graph-roadmap.md) — planned graphs and generation rules.
- [Testing and contributing](./testing-and-contributing.md#validating-documentation-and-graphs-in-a-change) — the validation workflow.
