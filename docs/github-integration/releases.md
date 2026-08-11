# Releases — GitHub integration

This log tracks every shipped round of the MRICS GitHub integration. Each entry
maps to a merge on `mrics/dev` and an immutable image tag (`mrics-vX.Y.Z`).

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
