# Packages

Every tracked workspace package manifest under `packages/*/package.json`, with its declared package name and a concise role based on the manifest, README, or source entry point. Roles that cannot be confirmed from these artifacts are marked explicitly.

## Package inventory

| Package path | Declared name | Role (source) |
| --- | --- | --- |
| [`packages/types/package.json`](../../packages/types/package.json) | `@plane/types` | Shared TypeScript types/interfaces; a foundational leaf package with no internal workspace dependencies (manifest `dependencies`; root graph). |
| [`packages/constants/package.json`](../../packages/constants/package.json) | `@plane/constants` | Shared constants; depends only on `@plane/types` (manifest). |
| [`packages/utils/package.json`](../../packages/utils/package.json) | `@plane/utils` | Helper functions; depends on `@plane/constants` and `@plane/types` (manifest). |
| [`packages/hooks/package.json`](../../packages/hooks/package.json) | `@plane/hooks` | React hooks shared internally; no `@plane/*` dependencies (manifest; description "React hooks that are shared across multiple apps internally"). |
| [`packages/services/package.json`](../../packages/services/package.json) | `@plane/services` | Axios-based API service layer used by web, admin, and space; depends on `@plane/constants` and `@plane/types` (manifest; root graph). |
| [`packages/shared-state/package.json`](../../packages/shared-state/package.json) | `@plane/shared-state` | MobX-based shared state (stores for workspace/user); depends on `@plane/constants`, `@plane/types`, `@plane/utils` (manifest; `src/store/`; root graph). |
| [`packages/i18n/package.json`](../../packages/i18n/package.json) | `@plane/i18n` | i18next internationalization; ships per-language `src/locales/<lang>/` JSON; no `@plane/*` dependencies; scripts `generate:types`, `sync:check` (manifest; `src/locales/`). |
| [`packages/propel/package.json`](../../packages/propel/package.json) | `@plane/propel` | Headless UI component library (Base UI primitives: menu, dialog, tooltip, combobox, calendar, table, avatar, icons, charts); depends on constants/hooks/types/utils; ships Storybook (manifest; `src/`; `.storybook/`; root graph). |
| [`packages/ui/package.json`](../../packages/ui/package.json) | `@plane/ui` | Shared UI component package (buttons, modals, dropdowns, avatars, toasts, typography); depends on constants/hooks/propel/types/utils; ships Storybook (manifest; `src/`; `.storybook/`; root graph). |
| [`packages/editor/package.json`](../../packages/editor/package.json) | `@plane/editor` | Core rich-text editor (Tiptap/ProseMirror) that powers Plane; used by web, space, and live; depends on constants/hooks/propel/types/ui/utils ([`Readme.md`](../../packages/editor/Readme.md); manifest; root graph). |
| [`packages/decorators/package.json`](../../packages/decorators/package.json) | `@plane/decorators` | Controller and route decorators for Express.js apps (`@Controller`, `@Get`, `@WebSocket`, …); used by `apps/live` ([`README.md`](../../packages/decorators/README.md); manifest). |
| [`packages/logger/package.json`](../../packages/logger/package.json) | `@plane/logger` | Winston logger + request-logger middleware; used by `apps/live` ([`README.md`](../../packages/logger/README.md); manifest). |
| [`packages/codemods/package.json`](../../packages/codemods/package.json) | `@plane/codemods` | jscodeshift codemods (`function-declaration`, `remove-directives`) with tests; role from `scripts` and [`instructions.md`](../../packages/codemods/instructions.md). |
| [`packages/typescript-config/package.json`](../../packages/typescript-config/package.json) | `@plane/typescript-config` | Shared TypeScript config presets (`base`, `react-library`, `nextjs`, `react-router`, `node-library` JSON files); consumed as devDependency by apps; no scripts/deps (directory contents). |
| [`packages/tailwind-config/package.json`](../../packages/tailwind-config/package.json) | `@plane/tailwind-config` | Shared Tailwind configuration/CSS (description "common tailwind configuration across monorepo"); referenced by `.oxfmtrc.json` (`stylesheet: packages/tailwind-config/index.css`); no scripts/deps. |

## Notes

- **Workspace scope**: `packages/*` are workspace members ([`pnpm-workspace.yaml`](../../pnpm-workspace.yaml)); apps depend on them via `"@plane/*": "workspace:*"`.
- **Dependency backbone** (from the root graph and manifests): leaf packages `@plane/types` (no deps), then `constants` → types; `utils` → constants + types; up through `propel`/`ui`/`editor`/`services`/`shared-state`/`i18n`.
- **Graph status**: the root graph covers the nine principal packages (`types`, `constants`, `utils`, `propel`, `ui`, `editor`, `services`, `shared-state`, `i18n`). `@plane/hooks`, `@plane/decorators`, `@plane/logger`, `@plane/codemods`, `@plane/typescript-config`, and `@plane/tailwind-config` are tracked workspace packages but are `Not yet documented` at graph level (planned per [graph-roadmap.md](./graph-roadmap.md#package-graphs)).
- **Insufficiently evidenced roles**: none of the manifests are ambiguous enough to mark unknown; every package has a declared description or a verifiable source entry point above. Where a description was absent from the manifest (e.g. `@plane/types`), the role is inferred from the source layout and the root graph, not from the manifest alone.

## Where to look next

- [Frontend](./frontend.md) — which apps consume which packages.
- [Architecture map](./architecture.md) — where packages sit in the layer model.
- [Graph roadmap](./graph-roadmap.md#package-graphs) — planned per-package graphs.
