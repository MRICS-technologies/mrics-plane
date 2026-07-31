# Checkpoint — Dynamic GitHub Integration

**Date:** 2026-07-30
**Primary worktree:** `/tmp/plane-wt-github`
**Primary branch:** `feat/github-integration-native`
**Backend implementation worktree:** `/tmp/plane-wt-github-backend`
**Backend branch:** `feat/github-integration-native-backend`
**Canonical specification:** `.hermes/plans/2026-07-29_172918-dynamic-github-integration-prd.md`

## Status

No change has been committed, pushed, or deployed. The primary worktree has no tracked source changes; its `.hermes/` directory is intentionally untracked for planning/checkpoint artifacts.

The backend worktree contains an **unintegrated P1 implementation** for secure instance-level GitHub App configuration. It is deliberately not accepted yet because an independent security review found blockers.

## Completed discovery and locked decisions

- The implementation stays native to Plane/Django: **no sidecar**, no new runtime, and no new package.
- Existing integration points to adapt:
  - `apps/api/plane/services/github/client.py`
  - `apps/api/plane/db/models/integration/github_sync.py`
  - `apps/api/plane/app/{views,serializers,urls}/github_sync.py`
  - instance configuration encryption/admin primitives under `apps/api/plane/license/`
  - existing issue sidebar GitHub panel under `apps/web/core/.../github-panel/`
- Credentials must be server-side, encrypted at rest, write-only, and separate from legacy OAuth credentials.
- Workspace installations, repo/project mapping, webhooks, PR linking, and settings UI are sequenced after P1 acceptance.

## P1 implementation currently present only in the backend worktree

New/modified files:

- `apps/api/plane/license/api/serializers/github_app.py` (new)
- `apps/api/plane/license/api/views/github_app.py` (new)
- `apps/api/plane/license/api/views/configuration.py`
- `apps/api/plane/license/api/views/__init__.py`
- `apps/api/plane/license/urls.py`
- `apps/api/plane/tests/contract/api/test_github_app_configuration.py` (new)

Implemented behavior:

- Instance-admin-only `GET/PATCH/DELETE /api/instances/github-app/`
- Local-only `POST /api/instances/github-app/test/`
- Write-only encrypted storage for the private key, webhook secret, and client secret.
- Generic configuration `GET/PATCH` excludes `GITHUB_APP_*` records to prevent the legacy decrypting serializer from disclosing GitHub App secrets.
- Legacy OAuth keys `GITHUB_CLIENT_ID` and `GITHUB_CLIENT_SECRET` are explicitly rejected by the GitHub App endpoint.
- Contract tests cover authorization, response non-disclosure, OAuth isolation, secret rotation, delete, and malformed configuration.

## Verification status

Passed:

- Python compilation for changed Python files.
- `git diff --check`.
- Static source assertions for write-only fields, generic configuration isolation, and OAuth-key collision guards.

Blocked:

- Focused pytest could not run: the backend worktree has no executable pytest environment and the project test setup requires Redis. No Docker/Compose route was available.

## Independent review blockers — must be remediated before integration

1. **API-token request logs:** redact or omit request bodies for `/api/instances/github-app/` before `APITokenLogMiddleware` queues them; otherwise submitted secrets could be persisted under `X-Api-Key`, including failed requests.
2. **Soft delete:** hard-delete GitHub App configuration records, or atomically revive them, so DELETE does not retain ciphertext and later PATCH can reconfigure the app.
3. **JWT test semantics:** remove decode-without-signature-verification or verify against a derived public key. Describe it as a local signer/key sanity check until actual GitHub validation is introduced.
4. **Required tests:** API-token log redaction, no retained ciphertext after delete, delete→reconfigure, and meaningful local JWT behavior.
5. **Fingerprint refinement:** avoid deterministic truncated SHA-256 secret fingerprints; use status/timestamps or a server-keyed HMAC if needed.

## Next plan

1. Fix agent orchestration/capture: Herdr remains the default. Use a Herdr shell pane to run noninteractive Claude when the interactive agent state machine is idle/blocked; retain capture only as fallback with an explicit higher turn limit.
2. Sonnet remediation-only slice for the five P1 blockers; no workspace models, UI, migration, or webhook work in that run.
3. Independent blocker-only Codex review.
4. Provision/identify a Redis-capable pytest environment and run P1 tests.
5. Integrate P1 only after review/test acceptance.
6. Then sequence: workspace installation/repo/project mapping migration → dynamic GitHub App JWT/installation-token cache client → workspace admin APIs → frontend settings/repo picker → signed webhooks/PR links → final integrated security and test review.

## Guardrails

- No credentials in source, logs, tests, API responses, Git, or chat.
- No commit, push, deploy, Coolify change, new dependency, or sidecar without explicit approval after verification.
- Sonnet implements; Codex independently reviews; Dahab is the integration and verification gate.

## Orchestration remediation — verified 2026-07-30

- **Herdr remains the default cockpit.** Herdr `0.7.5` server is healthy and its interactive-agent lifecycle path is not relied upon when an agent is idle/blocked or `agent_prompt_stalled` occurs.
- **Proven fallback within Herdr:** create a Herdr shell pane and use `herdr pane run` to launch native noninteractive Claude Code (`claude --print ...`). A real smoke test in workspace `wF` returned a standalone `HERDR_CLAUDE_SHELL_OK` line; matching was performed with an anchored regex to avoid falsely matching the echoed command.
- **Capture wrapper retired:** `/opt/data/bin/claude-code-capture` was deleted at the user's direction after the Herdr shell-pane pattern proved reliable. It is no longer a fallback execution path.
- **Execution rule:** use Herdr shell panes to manage Claude Code directly, with raw `claude --print`, an explicit turn limit, durable file-backed logs, and a standalone completion/exit marker.
- **Freebuff:** version `0.0.129` is available but remains TUI-only with no headless execution mode. Use only for fully specified low-risk/repetitive slices in an isolated Herdr pane, never for security-sensitive GitHub configuration or architectural work.

## P1 remediation update — 2026-07-30

The P1 security blockers have now been remediated in the backend worktree, still without a commit/push/deploy:

- API-token logs suppress both request and response bodies for the exact slashless GitHub App base path and all descendants; sibling routes remain unaffected.
- Tests cover success, validation failure, unauthorized/forbidden, the test subroute, the slashless path, a full middleware `__call__` invocation, and sibling non-overmatch.
- GitHub App DELETE uses hard deletion through `all_objects`; delete→reconfigure is covered.
- JWT “test” is strictly local signing, with insecure decode removed.
- Secret fingerprints use a server-keyed HMAC.

- **Passed:** an isolated Python 3.11 test environment (outside the repo) ran `plane/tests/unit/middleware/test_logger.py` with `REDIS_URL=redis://127.0.0.1:6379/0`: **15 passed**.
- **Still blocked:** the six GitHub App contract tests need PostgreSQL. Docker is installed but its daemon is unavailable; the SQLite fallback fails during Plane schema creation because Plane uses PostgreSQL-specific types (not because of the GitHub App implementation). No source changes, commit, push, or deploy occurred.

## Current verified state — 2026-07-30

This section supersedes the stale status statements above.

- P1 is accepted and tracked remotely. Secure GitHub App configuration was committed as `f870105` on `feat/github-integration-native`; the PostgreSQL/Redis contract CI workflow was committed as `379b161` and pushed. The backend checkpoint branch remains at `c371201`.
- GitHub Actions run `30534960866` for commit `c371201` completed successfully: https://github.com/MRICS-technologies/mrics-plane/actions/runs/30534960866. This is the first real PostgreSQL-backed execution of `plane/tests/contract/api/test_github_app_configuration.py`.
- Local focused logger regression remains green: `plane/tests/unit/middleware/test_logger.py` — **15 passed**. No deployment occurred.
- Docker diagnosis: the Hermes runtime is a container with Docker client tooling but neither `dockerd` nor `/var/run/docker.sock`. The host daemon was not changed. The chosen safe remediation is GitHub Actions PostgreSQL/Redis runners rather than granting this agent host-Docker control.

## Noninteractive Claude / Opus execution rule — verified 2026-07-30

- The Opus planner was not a dead CLI process: it was performing work while `claude --print` buffered final output, making its durable log appear empty. A full repeat completed and produced the Phase 2 design contract.
- Required Herdr-pane invocation shape: pass the prompt explicitly with `-p`, add `--verbose --output-format stream-json --include-partial-messages`, write to a durable log, set an explicit `--max-turns`, and print a separate exit marker. This exposes progress and makes genuine stalls distinguishable from buffered output.
- Do not recreate the retired capture wrapper.
- Codex read-only sandbox cannot run in this container because unprivileged bubblewrap namespaces are denied. Use direct noninteractive Claude in a Herdr pane for local read-only review unless the host sandbox policy is changed.

## Current next slice

- Phase 2 S1 is isolated in `/tmp/plane-wt-github-s1` on `feat/github-integration-native-s1`: native workspace installation/repository schema, a non-destructive mapping bridge, and P1 credential consumption. It is not integrated until independent review and PostgreSQL CI acceptance.

## Delivered and deployed update — 2026-07-31

This section supersedes the historical “unintegrated” and “next slice” status statements above.

### Delivered scope

- Dynamic, write-only instance GitHub App configuration, workspace installations, repository registration, and project/repository mappings are integrated on `mrics/dev`.
- Signed GitHub `pull_request` webhook handling now links and updates Plane issues. It handles `opened`, `reopened`, `closed`, `merged`, and `synchronize` link lifecycle events; this slice does **not** move issue workflow states.
- The webhook implementation verifies the raw request body HMAC before parsing, fails closed on invalid signatures, suppresses webhook payload/signature logging, limits payload size, requires `X-GitHub-Delivery` for side-effecting work, and applies transactional delivery deduplication.
- PR identity is tenant-scoped, link updates protect against stale events, and historical soft-deleted links can be restored without silently losing data.

### Integration and validation evidence

- Pull request: [#3](https://github.com/MRICS-technologies/mrics-plane/pull/3), merged to `mrics/dev` on 2026-07-31.
- Merge commit: `67803a8d069bdaac269f098b76846d25367e54ac`.
- Feature-branch PostgreSQL/Redis acceptance: 84 tests passed after the final review corrections.
- The same PostgreSQL/Redis contract workflow passed again on the merged `mrics/dev` SHA: [GitHub Actions run 30616470428](https://github.com/MRICS-technologies/mrics-plane/actions/runs/30616470428).
- Backend and frontend images for `67803a8` were built successfully, then the Coolify service `MRICS Plane Dev Fork` (`s3huh6v0kn54nhiz646wnb4j`) was restarted with a forced latest-image pull.
- Live dev probes succeeded: `/` returned `200`; `/api/v1/users/me/` returned the expected `401` authentication response.

### Remaining acceptance gate

No production environment was changed. The only outstanding validation is a real GitHub App delivery against dev: configure the dev GitHub App’s webhook URL and secret in GitHub, enable Pull request events, create a mapped-repository PR containing an issue key, and confirm the expected link/lifecycle updates in Plane. Do not place the webhook secret in source, documentation, logs, or chat.
