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
