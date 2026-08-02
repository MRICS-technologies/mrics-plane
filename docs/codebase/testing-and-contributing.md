# Testing and Contributing

Package-manager/workspace, test, lint, and format navigation based only on root scripts, `CONTRIBUTING.md`, and repository configuration — plus how to validate documentation and graph changes.

## Setup

Prerequisites and onboarding are in [`CONTRIBUTING.md`](../../CONTRIBUTING.md): Docker, Node.js 20+, Python 3.8+, Postgres 14, Redis, and ~12 GB RAM. The one-shot setup is:

```bash
chmod +x setup.sh
./setup.sh            # creates .env files from .env.example, generates a Django SECRET_KEY, pnpm install
docker compose -f docker-compose-local.yml up   # backend dependencies + api
pnpm dev              # web :3000, admin :3001, space :3002, live :3000 (turbo run dev --concurrency=18)
```

Toolchain facts from root manifests:

- **Package manager**: pnpm `11.3.0` (`packageManager` in [`package.json`](../../package.json)); workspace defined in [`pnpm-workspace.yaml`](../../pnpm-workspace.yaml) (apps + packages, excluding `apps/api` and `apps/proxy`).
- **Node**: `>= 22.18.0` (root `engines`); also pinned by `.mise.toml` (`node = "22.18.0"`).
- **Task runner**: Turborepo ([`turbo.json`](../../turbo.json)) with tasks `build`, `dev`, `start`, `clean`, `check*`, `fix*`, `test`, `build-storybook`.

## Root scripts

From [`package.json`](../../package.json):

| Script | Runs | Purpose |
| --- | --- | --- |
| `pnpm dev` | `turbo run dev --concurrency=18` | Start all dev servers |
| `pnpm build` | `turbo run build` | Build all workspace packages/apps |
| `pnpm start` | `turbo run start` | Run production builds |
| `pnpm check` | `turbo run check` | `check:format` + `check:lint` + `check:types` |
| `pnpm check:format` | `turbo run check:format` | `oxfmt --check` per package |
| `pnpm check:lint` | `turbo run check:lint` | `oxlint` per package |
| `pnpm check:types` | `turbo run check:types` | `tsc --noEmit` (web/admin/space also run `react-router typegen`) |
| `pnpm fix` / `fix:format` / `fix:lint` | `turbo run fix*` | Auto-fix formatting and lint |
| `pnpm clean` | `turbo run clean && rm -rf .turbo .next node_modules dist` | Full workspace clean |
| `pnpm prepare` | `husky` | Install git hooks (pre-commit runs `pnpm lint-staged`) |

Target a single package/app: `pnpm turbo run <command> --filter=<package>` (e.g. `pnpm --filter=@plane/ui storybook`).

## Formatting and linting

- **oxfmt** for formatting (`.oxfmtrc.json` — print width 120, tab width 2, Tailwind class sorting via `packages/tailwind-config/index.css`).
- **oxlint** for linting (`.oxlintrc.json` — react, typescript, jsx-a11y, import, promise, unicorn, oxc plugins; correctness/suspicious/perf at warn).
- **Pre-commit**: `.husky/pre-commit` runs `pnpm lint-staged`, which formats and lints staged files (`package.json` `lint-staged` block) with `oxfmt` and `oxlint --fix --deny-warnings`.
- Apps ship per-app `check:*`/`fix:*` scripts with explicit `oxlint --max-warnings=<n>` budgets (e.g. web `11957`, admin `759`, space `676`, live `119` — see each `apps/*/package.json`).
- **API (Python)**: ruff, configured in [`apps/api/pyproject.toml`](../../apps/api/pyproject.toml) (E/F rules, isort, pydocstyle google convention, line-length 120); CI runs `ruff check --fix apps/api`.

## API tests (pytest / Django)

- **Config**: [`apps/api/pytest.ini`](../../apps/api/pytest.ini) — `DJANGO_SETTINGS_MODULE=plane.settings.test`, `--reuse-db --nomigrations`, strict markers `unit`, `contract`, `smoke`, `slow`. Tests live in `apps/api/plane/tests/` (`unit/`, `contract/app/`, `contract/api/`, `smoke/`) with factories in `plane/tests/factories.py`.
- **Run via Docker** (recommended; isolated stack in [`docker-compose-test.yml`](../../docker-compose-test.yml)):

  ```bash
  # full suite
  docker compose -f docker-compose-test.yml up --build --abort-on-container-exit --exit-code-from api-tests
  # subset, e.g. unit only
  docker compose -f docker-compose-test.yml run --rm --build api-tests pytest -m unit
  # teardown
  docker compose -f docker-compose-test.yml down -v
  ```

- Full walkthrough: [`apps/api/tests/RUNNING_TESTS.md`](../../apps/api/tests/RUNNING_TESTS.md); conventions and fixtures: [`apps/api/plane/tests/TESTING_GUIDE.md`](../../apps/api/plane/tests/TESTING_GUIDE.md). There is also a legacy `apps/api/run_tests.sh` wrapper (delegates to `tests/run_tests.sh`).

## Frontend tests

- `apps/live` is the workspace member with a configured test runner: Vitest (`vitest run` / `--coverage`), config in [`apps/live/vitest.config.ts`](../../apps/live/vitest.config.ts).
- `packages/codemods` also has Vitest specs (`packages/codemods/vitest.config.ts`, scripts `test`, `function-declaration`, `remove-directives`).
- Other frontend apps/packages do not currently declare test scripts in their manifests (web/admin/space `package.json` scripts are dev/build/check/fix only). Adding unit tests to those packages is an open improvement; see the [GitHub integration developer guide](../github-integration/developer-guide.md) for the contract-test pattern used for backend endpoints.

## Validating documentation and graphs in a change

Any change that touches `docs/codebase/` or a `.ua/` graph artifact should be validated like this:

1. **Content rules** — every technical assertion must carry a source path or be marked `Not yet documented`/`Planned deep dive` (see [maintenance.md](./maintenance.md#evidence-rules)). Do not invent behavior, deployment state, or secrets.
2. **Links resolve** — relative Markdown links must resolve inside the repository. Key link targets: root graph `../../.ua/knowledge-graph.json`, URL pilot `../../apps/api/plane/app/urls/.ua/knowledge-graph.json`, and `../github-integration/README.md`. A quick check: `git diff --check` plus a manual pass over every `](./...)`/`](../...)` target.
3. **Formatting** — Markdown is covered by the lint-staged `oxfmt` formatter (`*.md` in the lint-staged globs in [`package.json`](../../package.json)). Run `pnpm fix:format` or `pnpm exec oxfmt .` on changed files.
4. **Graph artifacts** — regenerate/refresh any touched `.ua/` graph via the Understand Anything workflow (see [maintenance.md](./maintenance.md#graph-update-policy)), review the artifact, and commit only durable files (`knowledge-graph.json`, `meta.json`, `fingerprints.json`, `config.json`, `.understandignore`); transient dirs (`.ua/intermediate/`, `.ua/tmp/`, `.ua/.trash-*/`) are git-ignored.
5. **CI parity** — documentation-only changes do not trigger the app build/lint workflows (they are path-filtered to source dirs), but the `copyright-check` (addlicense on `.py`/`.ts`/`.tsx` — not Markdown) and `i18n-sync-check` do not apply to `docs/`. Run `git diff --check` before finishing.

## Where to look next

- [Operations](./operations.md) — compose stacks and CI pipelines behind these commands.
- [Backend (API)](./backend.md#extension--testing-guidance-grounded-in-repo-config) — backend extension/testing guidance.
- [Maintenance](./maintenance.md) — the review checklist for doc/graph changes.
