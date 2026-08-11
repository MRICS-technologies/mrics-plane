# Releases — GitHub integration

This log tracks every shipped round of the MRICS GitHub integration. Each entry
maps to a merge on `mrics/dev` and an immutable image tag (`mrics-vX.Y.Z`).

## v1.4.2.5 — creator-name branch suggestions (2026-08-11)

- **UX:** the issue panel's suggested branch name now includes the creator's
  first name when available, for example
  `feature/muhammed-alldev-92-payment-flow`.
- **Fallback:** if `first_name` is blank, Plane uses the first token of
  `display_name`; if no usable name exists, it keeps the previous
  `feature/<issue-key>-<slug>` format.
- **Images:** frontend
  `sha256:5e886e15433ff334e74f956917641219637f40cf49348602b767292a78279c65`.

## v1.4.2.4 — Phase 2 branch-linking foundation (2026-08-11)

- **Existing branch linking:** typing a branch that already exists on GitHub now
  links it to the Plane issue instead of returning a conflict.
- **Shared branches:** a single GitHub branch may intentionally be linked to
  multiple Plane issues.
- **PR fan-out:** pull-request webhooks from a shared branch create/update PR
  links for **every issue** linked to that branch.
- **Migration `0130`:** PR-link uniqueness is widened from
  `(workspace, repo, PR number)` to `(workspace, repo, PR number, issue)` so one
  GitHub PR can appear on multiple work items.
- **Images:** backend
  `sha256:4e675f35590186be7bd46b67192e451e56b6dc48a37d8d21352acd54b8eb0e94`,
  frontend
  `sha256:8b09f9d3a45ce92ce66f52579af8cce3420939938cbce7c21e65c8ed8ab7d50d`,
  admin
  `sha256:702dbcd0f123a5d8a176277cbe344e80c506987e0033d0d649211e7d3481ece9`.

## v1.4.2.1 — manifest events fix (2026-08-11)

- **Fix:** GitHub rejects manifests that declare `installation` /
  `installation_repositories` in `default_events` ("Default events
  unsupported"). The manifest now declares only `pull_request` + `push`; the
  lifecycle events are auto-delivered.
- **Fix:** `base_host()` no longer crashes when `WEB_URL`/`APP_BASE_URL` are
  unset (redirect building is now None-safe).
- **Images:** backend `738e0c53` (staging: `mrics-v1.4.2.1`).

## v1.4.2 — Phase 1: the reworked GitHub setup (2026-08-11)

The feature the user-facing docs describe. Root causes fixed from the original
implementation:

- **One-click GitHub App creation** via the manifest flow — no credentials
  typed (the old UI literally said _"This does not contact GitHub"_; everything
  was hand-typed: installation IDs, repo IDs).
- **Verified install callback** — reads the installation from GitHub before
  trusting it; installation must be _fresh_ (created inside the state token's
  lifetime) when no row exists.
- **Installation ownership enforced** (B1): a live installation belongs to
  exactly one workspace — cross-workspace rebinding returns a conflict.
- **Live repo discovery** — the picker lists repositories from GitHub; bulk
  saves validate each repo against GitHub's live list and report per-item
  errors.
- **Installation lifecycle webhooks** — suspend / delete / unsuspend /
  repositories events now update the connection state; soft-deletes are
  cascade-free (mappings and links survive disconnects).
- **Setup-state tokens** — single-use, hashed, cache-backed, expire after 15
  minutes.
- **Admin app now built as a MRICS image** (`mrics-plane-admin`) — the
  god-mode GitHub App page ships from the fork.
- **Migration `0129`** — additive only (discovery fields, all nullable).
- **CI gate fixed** — the GitHub App configuration test suite now runs on
  pull requests (it was push-only; it had never exercised PRs).

## v1.4.1 — upstream sync + time tracking (2026-08-10)

- Fork synced to upstream **Plane v1.4.1** (merge-node `0127`, drift-free
  migration state).
- **Work-log / time tracking** shipped: per-issue timers, state durations,
  analytics; duration display uses 24-hour calendar days (`Xd Zh`).
- The GitHub rework's foundation (models, webhook, branch endpoint) merged in
  this round.

## How releases work

Every round: branch → PR → CI (lint, types, builds, the GitHub configuration
test suite) → merge → immutable image builds (`dev-latest`) → manual tag
(`mrics-vX.Y.Z`) → staging redeploy (digest-pinned) → validation → production
cutover (digest swap, backup first, rollback artifacts retained).
