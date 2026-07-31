# Dynamic GitHub Integration for MRICS Plane Fork — PRD & Technical Implementation Spec

> **For Hermes/Dahab:** This is a planning/specification artifact only. Do not implement from this document until Hijazi explicitly asks to proceed. When implementation starts, use `agent-orchestration-herdr-tmux`: Opus plans, Sonnet/Codex implement/review, Dahab integrates/verifies/deploys.

**Goal:** Replace the MRICS-specific static GitHub credential MVP with a reusable, product-like, self-hosted GitHub integration configured from Plane UI by instance/workspace admins.

**Repository:** `/tmp/plane-wt-github`
**Branch inspected:** `feat/github-integration-native`
**Commit inspected:** `60f38c2`
**Date:** 2026-07-29
**Mode:** PRD/spec only — no code, no commit, no deploy.

---

## 1. Executive Summary

The current native GitHub MVP added the useful product surface we want to keep: an issue-detail GitHub sidebar, branch creation, GitHub link records, and backend routes/services. However, its setup model is not reusable: it relies on instance-level environment variables such as `GITHUB_APP_ID`, `GITHUB_APP_PRIVATE_KEY`, `GITHUB_WEBHOOK_SECRET`, plus hardcoded installation IDs in project mappings.

Hijazi rejected that model correctly. A reusable Plane fork image must not require Dahab to manually create a GitHub developer app, inject secrets into Docker/Coolify, or hardcode MRICS installation IDs. The integration must behave like a real product capability: an authorized admin configures GitHub inside the Plane instance/workspace, connects a GitHub account/org, selects repositories, maps them to Plane projects, and then issue-level branch/PR automation works for that workspace.

The recommended direction is a native Plane implementation using the existing integration primitives where possible, not a sidecar. The first production-grade target should support one of two setup modes:

1. **Preferred long-term:** GitHub App setup/install flow exposed through Plane admin/workspace settings. If GitHub App Manifest flow is feasible for self-hosted callback URLs, use it. Otherwise support manually pasting app credentials into an admin-only write-only screen as an interim admin flow, not chat/env vars.
2. **Fallback first slice:** Fine-grained PAT/workspace token flow, only if GitHub App dynamic setup is too large for the next implementation window. This should be explicitly temporary and have a migration path to GitHub App installations.

The spec below assumes **GitHub App as the target architecture**, with a possible PAT compatibility bridge only as a scoped fallback.

---

## 2. Product Requirements

### 2.1 Problem

Current MVP problems:

- GitHub credentials are external static deploy-time configuration.
- Installation IDs are effectively trusted/hardcoded data rather than verified workspace configuration.
- Docker image is not reusable for future teams/instances without per-instance code/config manipulation.
- The old Plane OSS GitHub integration UI/services appear partly broken/dead and can confuse workspace admins.
- Secret handling is not productized: no UI setup, validation, rotation, masking, or audit trail.
- Webhook routing and branch creation must become tenant-aware and idempotent.

### 2.2 Goals

- Allow a Plane instance/workspace admin to configure GitHub from the UI.
- Allow workspace admins to connect/install GitHub orgs/accounts and select allowed repositories.
- Allow project admins/workspace admins to map Plane projects to selected GitHub repositories.
- Preserve the current issue sidebar GitHub panel concept.
- Let project members create/view GitHub branches/PR links only for authorized project mappings.
- Make branch creation idempotent and safe under retries/concurrency.
- Implement signed, tenant-aware, idempotent webhook processing.
- Store secrets securely; never expose private keys/webhook secrets/tokens after write.
- Keep the Plane fork native; do not introduce a new sidecar runtime.
- Support incremental, deployable phases so current MVP behavior can keep working while setup migrates.

### 2.3 Non-goals for first production slice

- Full two-way issue sync between GitHub issues and Plane issues.
- Automatic PR-merged-to-Plane-state transition, except as a later webhook extension point.
- Complex GitHub Enterprise Server support unless it falls out naturally from configurable API/base URLs.
- Multi-GitHub-App-per-workspace unless required by user workflow.
- Marketplace distribution of the Plane fork.
- A separate Node/Python sidecar service.
- Asking users for secrets in chat, Telegram, Obsidian, or deployment notes.

---

## 3. Personas and Permissions

### 3.1 Instance admin / god-mode admin

Can:

- Configure instance-level GitHub App credentials if using one app per Plane instance.
- Validate app credentials.
- Rotate private key/webhook secret.
- Disable/delete instance GitHub configuration.
- View masked status only, never raw secrets.
- See audit/status for webhook failures and setup errors.

Cannot:

- Use UI responses to retrieve stored secret values after write.

Likely permission check to verify during implementation:

- Existing Plane god-mode/admin primitives. Search for admin/god-mode routes and permission classes before implementation.

### 3.2 Workspace admin

Can:

- Start GitHub App installation flow for their workspace.
- Complete installation callback and attach installation to workspace.
- List repositories accessible to verified installation.
- Select/enable repositories for workspace use.
- Map repositories to Plane projects.
- Disable/reconnect workspace installation.

Cannot:

- Configure instance-level private key unless also instance admin.
- Enumerate repositories for installations not attached to the workspace.
- Bypass server-side permission checks by passing installation IDs manually.

### 3.3 Project admin / project member

Project admin can:

- Choose or update project mapping if workspace policy allows project-level mapping.

Project member can:

- View GitHub links for issues in projects they can access.
- Create branches only through an authorized project mapping.

Project member cannot:

- List all workspace GitHub installations.
- Change integration credentials/mappings.
- Create branches in unmapped/unauthorized repositories.

---

## 4. Recommended UX Flows

### 4.1 Instance setup flow — GitHub App configuration

Route/location to verify during implementation:

- Existing admin/god-mode settings area, or a new instance-admin settings page.
- Candidate frontend area: `apps/web/core` settings/admin routes; verify exact route structure before implementation.

Flow:

1. Instance admin opens **Admin Settings → Integrations → GitHub**.
2. UI shows one of these states:
   - Not configured.
   - Configured but unvalidated.
   - Configured and healthy.
   - Misconfigured/needs rotation.
3. Admin chooses setup method:
   - Preferred: create/register GitHub App using manifest/callback flow if feasible.
   - Manual admin fallback: paste App ID, private key, webhook secret, app slug/client ID if needed.
4. Backend validates credentials by generating an app JWT and calling GitHub app endpoint.
5. UI stores credentials through write-only endpoint.
6. Response returns only masked status:
   - app slug/name
   - app ID
   - configured timestamp
   - last validation status
   - secret fingerprints, not secret values

### 4.2 Workspace installation flow

1. Workspace admin opens **Workspace Settings → Integrations → GitHub**.
2. If instance app is missing, UI shows:
   - “GitHub is not configured for this Plane instance. Ask an instance admin.”
3. If configured, UI shows:
   - “Connect GitHub organization/account.”
4. Workspace admin clicks install/connect.
5. Backend creates signed state with workspace slug, user ID, nonce, expiry.
6. User is redirected to GitHub App install/authorize URL.
7. GitHub redirects to callback with `installation_id`, `setup_action`, `state`.
8. Backend validates state, verifies installation belongs to the configured app, persists workspace installation.
9. UI returns to workspace GitHub page showing installation status and repo picker.

### 4.3 Repository selection and project mapping

1. Workspace admin opens repo picker.
2. Backend lists repos from GitHub using installation token.
3. Admin selects allowed repositories for workspace.
4. Admin maps a Plane project to one allowed repository and optional defaults:
   - default base branch
   - branch prefix/template
   - whether branch creation is enabled
5. Issue sidebar uses project mapping automatically.

Important Opus correction:

- **Do not directly reuse** `apps/web/core/components/integration/github/select-repository.tsx` because it is coupled to the old dead endpoint `workspace-integrations/{id}/github-repositories/?page=N` through `projectService.getGithubRepositories()`.
- Build a new picker on the new endpoint:
  - `GET /api/workspaces/{slug}/github/repositories/`

### 4.4 Issue sidebar flow

Keep the existing current MVP concept:

- `apps/web/core/components/issues/issue-detail/github-panel/`
- `apps/web/core/services/github-sync.service.ts`

States:

- Loading GitHub links.
- Project has no GitHub mapping.
- User lacks permission to create branch.
- Repository inaccessible/disconnected.
- Existing branch/PR links shown.
- Create branch button enabled.
- Branch creation in progress.
- Branch already exists/link reused.
- GitHub permission/rate-limit/not-found error with clear message.

---

## 5. Current Repo Surface and Decisions

### 5.1 Current MVP files to preserve/adapt

Backend:

- `apps/api/plane/db/models/integration/github_sync.py`
- `apps/api/plane/app/views/github_sync.py`
- `apps/api/plane/app/serializers/github_sync.py`
- `apps/api/plane/app/urls/github_sync.py`
- `apps/api/plane/services/github/client.py`

Frontend:

- `apps/web/core/services/github-sync.service.ts`
- `apps/web/core/components/issues/issue-detail/github-panel/github-panel.tsx`
- `apps/web/core/components/issues/issue-detail/github-panel/create-branch-button.tsx`
- `apps/web/core/components/issues/issue-detail/github-panel/git-link-item.tsx`
- `apps/web/core/components/issues/issue-detail/sidebar.tsx`

Decision:

- Preserve the issue sidebar user experience.
- Replace any static-env/hardcoded installation lookup underneath it with dynamic workspace/project mapping.

### 5.2 Existing Plane integration primitives to inspect/reuse

Backend:

- `apps/api/plane/db/models/integration/base.py`
- `apps/api/plane/db/models/integration/github.py`

Frontend/services:

- `apps/web/core/services/app_installation.service.ts`
- `apps/web/core/services/integrations/github.service.ts`
- `apps/web/core/components/project/integration-card.tsx`
- `apps/web/core/components/integration/github/select-repository.tsx`
- `apps/web/core/services/project/project.service.ts`

Decision:

- Reuse `Integration`/`WorkspaceIntegration` concepts if they fit Plane’s current architecture.
- Do **not** keep dead old GitHub endpoints alive just for component reuse.
- Document and prune/redirect old dead frontend services in a dedicated phase.

### 5.3 Dead/legacy frontend surface to prune or replace

Confirmed by Opus note:

- `apps/web/core/components/integration/github/select-repository.tsx`
  - Coupled to old endpoint shape.
- `apps/web/core/components/project/integration-card.tsx`
  - Calls `projectService.getProjectGithubRepository()` and `syncGithubRepository()`; these appear to 404.
- `apps/web/core/services/project/project.service.ts`
  - Contains dead GitHub repository/sync methods tied to old workspace integration endpoints.
- `apps/web/core/services/integrations/github.service.ts`
  - Contains `listAllRepositories` and importer endpoints that appear dead.

Decision:

- Phase 3 must create a new authoritative GitHub setup service and repo picker.
- Phase 8 must remove or redirect legacy/dead GitHub methods/pages to prevent duplicate broken flows.

---

## 6. Target Data Model

Exact existing model fields must be verified during implementation, but the target ownership model should be:

### D1. Instance GitHub app configuration

Purpose: store app-level credentials/config for the Plane instance.

Likely options:

- Reuse `Integration` or `WorkspaceIntegration.config` only if it supports instance-level secret storage safely.
- Otherwise add a dedicated model under integration models.

Candidate model name:

- `GithubAppConfig`

Fields:

- `id`
- `app_id`
- `app_slug` / `app_name`
- `client_id` if needed for manifest/OAuth flow
- `private_key_encrypted`
- `webhook_secret_encrypted`
- `github_base_url` default `https://api.github.com`
- `html_base_url` default `https://github.com`
- `is_enabled`
- `last_validated_at`
- `last_validation_error_code`
- `created_by`
- `updated_by`
- timestamps

Rules:

- Never serialize `private_key_encrypted` or `webhook_secret_encrypted`.
- Read responses return masked/fingerprint metadata only.
- Rotation writes replace only the target secret.

### D2. Workspace GitHub installation

Purpose: attach a verified GitHub App installation to a Plane workspace.

Candidate model name:

- `GithubWorkspaceInstallation`

Fields:

- `workspace`
- `app_config`
- `installation_id`
- `account_login`
- `account_type` (`Organization`/`User`)
- `account_avatar_url`
- `permissions_snapshot`
- `repository_selection` (`all`/`selected`)
- `is_active`
- `last_synced_at`
- `last_error_code`
- timestamps

Constraints:

- Unique active `(workspace, installation_id)`.
- Never trust `installation_id` passed from client without verifying against GitHub/app and workspace callback state.

### D3. Workspace allowed repositories

Purpose: cache/list repos enabled for a workspace.

Candidate model name:

- Reuse existing `GithubRepository` if it already represents GitHub repos.
- Otherwise add/adapt `GithubRepository` to include workspace installation tenancy.

Fields:

- `workspace_installation`
- `github_repository_id`
- `owner`
- `name`
- `full_name`
- `private`
- `default_branch`
- `html_url`
- `is_enabled`
- `last_seen_at`

Constraints:

- Unique `(workspace_installation, github_repository_id)`.

### D4. Project-to-repository mapping

Current MVP appears to have a project mapping model such as `RepoProjectMapping`.

Decision:

- Keep/adapt it if it already stores `workspace`, `project`, repo identity, installation ID, base branch.
- Rename or migrate to a clearer model only if current naming/shape blocks long-term use.

Target fields:

- `workspace`
- `project`
- `repository`
- `base_branch`
- `branch_prefix` / `branch_template`
- `is_enabled`
- timestamps

Constraints:

- Unique active mapping per project unless multi-repo-per-project is explicitly required later.
- Project mapping must belong to same workspace as repository installation.

### D5. Issue Git links

Current MVP appears to have `IssueGitLink`.

Decision:

- Preserve existing issue link records and migrate only fields necessary for dynamic mapping.
- Existing links must remain visible even if integration is temporarily disabled.

Target fields:

- `workspace`
- `project`
- `issue`
- `repository`
- `branch_name`
- `branch_ref`
- `branch_url`
- `pull_request_number` nullable
- `pull_request_url` nullable
- `github_node_id`/`github_id` nullable
- `status` (`branch_created`, `pr_open`, `pr_merged`, `closed`, etc.)
- `idempotency_key` or deterministic uniqueness fields
- timestamps

Constraints:

- Unique `(issue, repository, branch_name)`.
- Optional unique idempotency key per `(workspace, issue, repository, action)`.

### D6. Webhook deliveries

Add if not already present.

Candidate model:

- `GithubWebhookDelivery`

Fields:

- `delivery_id`
- `event`
- `installation_id`
- `repository_id`
- `workspace_installation` nullable until resolved
- `status`
- `received_at`
- `processed_at`
- `error_code`

Constraints:

- Unique `delivery_id` for idempotency/replay protection.

---

## 7. API Contract

Prefix to align with existing custom MVP routes during implementation. Recommended new namespace:

`/api/workspaces/{workspace_slug}/github/`

Exact URL include path must be verified in:

- `apps/api/plane/app/urls/github_sync.py`
- broader API URL registration files.

### 7.1 Instance app config endpoints

These may live outside workspace scope if Plane has instance-admin APIs. If not, gate under a god-mode workspace/admin route.

#### `GET /api/admin/integrations/github/app/`

Permission: instance admin.

Response:

```json
{
  "configured": true,
  "enabled": true,
  "app_id": "123456",
  "app_slug": "mrics-plane",
  "github_base_url": "https://api.github.com",
  "last_validated_at": "2026-07-29T17:00:00Z",
  "last_validation_status": "ok",
  "private_key_fingerprint": "sha256:abcd...",
  "webhook_secret_fingerprint": "sha256:efgh..."
}
```

Never return raw secrets.

#### `PUT /api/admin/integrations/github/app/`

Permission: instance admin.

Request:

```json
{
  "app_id": "123456",
  "private_key": "-----BEGIN PRIVATE KEY-----...",
  "webhook_secret": "...",
  "github_base_url": "https://api.github.com",
  "html_base_url": "https://github.com",
  "enabled": true
}
```

Response: masked config object.

Errors:

- `400` malformed key.
- `403` not instance admin.
- `422` GitHub validation failed.

#### `POST /api/admin/integrations/github/app/validate/`

Permission: instance admin.

Validates stored config by creating app JWT and calling GitHub.

#### `POST /api/admin/integrations/github/app/rotate-secret/`

Permission: instance admin.

Request:

```json
{
  "secret_type": "private_key",
  "value": "-----BEGIN PRIVATE KEY-----..."
}
```

or

```json
{
  "secret_type": "webhook_secret",
  "value": "new-secret"
}
```

### 7.2 Workspace installation endpoints

#### `GET /api/workspaces/{slug}/github/status/`

Permission: workspace member can read limited project-facing status; workspace admin gets full setup status.

Response for admin:

```json
{
  "instance_configured": true,
  "installation": {
    "id": "uuid",
    "installation_id": 12345678,
    "account_login": "MRICS-technologies",
    "account_type": "Organization",
    "is_active": true,
    "repository_selection": "selected",
    "last_synced_at": "2026-07-29T17:00:00Z"
  },
  "webhook_health": {
    "last_delivery_at": "2026-07-29T17:05:00Z",
    "last_error_code": null
  }
}
```

#### `POST /api/workspaces/{slug}/github/install-url/`

Permission: workspace admin.

Creates signed state and returns install URL.

Response:

```json
{
  "install_url": "https://github.com/apps/<app-slug>/installations/new?state=...",
  "state_expires_at": "2026-07-29T17:15:00Z"
}
```

#### `GET /api/integrations/github/callback/`

Permission: public callback, but validates signed state.

Query:

- `installation_id`
- `setup_action`
- `state`

Behavior:

- Validate state signature/expiry/user/workspace.
- Verify installation belongs to configured GitHub App.
- Persist/update workspace installation.
- Redirect to workspace GitHub settings page with success/error code.

#### `DELETE /api/workspaces/{slug}/github/installation/{id}/`

Permission: workspace admin.

Disables installation/mappings. Does not delete historical issue links by default.

### 7.3 Repository endpoints

#### `GET /api/workspaces/{slug}/github/repositories/`

Permission: workspace admin for full list. Project members should not use this endpoint unless a narrowed project scope is added.

Query:

- `page`
- `per_page`
- `search`
- `enabled`

Response:

```json
{
  "results": [
    {
      "id": "uuid",
      "github_repository_id": 123,
      "full_name": "MRICS-technologies/mrics-plane",
      "owner": "MRICS-technologies",
      "name": "mrics-plane",
      "private": true,
      "default_branch": "mrics/dev",
      "html_url": "https://github.com/MRICS-technologies/mrics-plane",
      "is_enabled": true
    }
  ],
  "next_cursor": null
}
```

#### `POST /api/workspaces/{slug}/github/repositories/sync/`

Permission: workspace admin.

Fetches repos from GitHub installation and updates local cache.

#### `PATCH /api/workspaces/{slug}/github/repositories/{repo_id}/`

Permission: workspace admin.

Enable/disable repo for workspace.

### 7.4 Project mapping endpoints

#### `GET /api/workspaces/{slug}/projects/{project_id}/github/mapping/`

Permission: project member can read limited mapping status; project admin/workspace admin can see editable config.

#### `PUT /api/workspaces/{slug}/projects/{project_id}/github/mapping/`

Permission: workspace admin or project admin if allowed.

Request:

```json
{
  "repository_id": "uuid",
  "base_branch": "main",
  "branch_prefix": "plane",
  "enabled": true
}
```

Errors:

- `403` user lacks project/workspace admin role.
- `404` repo not in workspace installation.
- `409` project already mapped and multi-repo not supported.
- `422` invalid branch/template.

### 7.5 Issue link/branch endpoints

Current MVP endpoints may already exist in `github_sync.py`; adapt them rather than duplicating if possible.

#### `GET /api/workspaces/{slug}/projects/{project_id}/issues/{issue_id}/github/links/`

Permission: project member.

Response:

```json
{
  "mapping_status": "configured",
  "can_create_branch": true,
  "links": [
    {
      "id": "uuid",
      "type": "branch",
      "repository_full_name": "MRICS-technologies/mrics-plane",
      "branch_name": "plane/MRP-123-add-github-setup",
      "url": "https://github.com/MRICS-technologies/mrics-plane/tree/plane/MRP-123-add-github-setup",
      "status": "branch_created"
    }
  ]
}
```

#### `POST /api/workspaces/{slug}/projects/{project_id}/issues/{issue_id}/github/branches/`

Permission: project member with issue access and mapping enabled.

Request:

```json
{
  "repository_id": "uuid",
  "base_branch": "main",
  "branch_name": "optional-custom-name",
  "idempotency_key": "client-generated-or-server-derived"
}
```

Behavior:

- Derive branch name if absent.
- Check existing link first.
- Verify repository belongs to project mapping.
- Use installation token for repo.
- Create ref from base branch SHA.
- Persist link.
- Return existing link on duplicate retry.

Errors:

- `403` no access.
- `404` issue/project/repo/base branch not found.
- `409` branch collision not owned by this issue.
- `422` invalid branch name.
- `502` GitHub unavailable.

### 7.6 Webhook endpoint

#### `POST /api/integrations/github/webhook/`

Permission: public endpoint with signature verification.

Headers:

- `X-GitHub-Event`
- `X-GitHub-Delivery`
- `X-Hub-Signature-256`

Rules:

1. Read raw request body bytes.
2. Validate HMAC SHA-256 using configured webhook secret before parsing JSON.
3. Constant-time compare signature.
4. Deduplicate `X-GitHub-Delivery`.
5. Parse event and resolve installation/repository to workspace installation.
6. Reject unknown/disabled installation.
7. Store delivery and enqueue/process event.
8. Return fast 2xx for accepted duplicate/known deliveries, 4xx for invalid signature.

---

## 8. Security Design

### 8.1 Secret storage

Requirements:

- Store private keys, webhook secrets, and PATs encrypted at rest.
- Never serialize raw secrets in API responses.
- Never log raw secrets or GitHub Authorization headers.
- Use write-only update endpoints.
- Expose only fingerprint/masked metadata.
- Support rotation independently for private key and webhook secret.
- On deletion, securely remove stored secret values and disable dependent installations.

Implementation detail to verify:

- Plane may already have secret/encrypted field utilities. Reuse existing patterns if present. If not, implement with the project’s established Django settings secret/key management rather than adding a new dependency unless necessary.

### 8.2 Permission enforcement

All enforcement must be server-side.

Do not trust:

- Installation IDs from client.
- Repository IDs from client without workspace-installation verification.
- UI visibility as authorization.

### 8.3 Audit logging

Add or reuse audit event system for:

- Instance GitHub app configured/validated/rotated/deleted.
- Workspace installation connected/disconnected.
- Repositories enabled/disabled.
- Project mapping created/updated/deleted.
- Webhook invalid signature/unknown installation/replayed delivery.
- Branch creation success/failure.

Audit payloads must be redacted.

---

## 9. Branch Creation Design

### 9.1 Branch name derivation

Default pattern:

```text
{prefix}/{issue_identifier}-{slugified_issue_title}
```

Example:

```text
plane/MRP-123-dynamic-github-setup
```

Rules:

- Lowercase unless project convention requires otherwise.
- Replace invalid Git ref characters.
- Collapse repeated separators.
- Max length guard.
- Avoid trailing `.`, `.lock`, `/`, or invalid ref segments.

### 9.2 Idempotency

Server should derive a deterministic idempotency key if client does not provide one:

```text
workspace_id:project_id:issue_id:repository_id:create_branch
```

On duplicate request:

- If a link exists and branch exists on GitHub, return existing link.
- If link exists but branch missing, either repair/recreate or return a clear recoverable error based on policy.
- If branch exists but no link and name matches deterministic issue branch, attach link after verification.
- If branch exists but belongs to unknown/manual source, return `409` collision and suggest alternate name.

### 9.3 GitHub error mapping

- GitHub `401`: installation token invalid/reconnect required.
- GitHub `403`: insufficient app permissions or rate limit.
- GitHub `404`: repo/base branch not found or inaccessible.
- GitHub `409`: ref already exists/race condition.
- GitHub `422`: invalid ref name/request.
- Network/5xx: `502` with retry-safe message.

---

## 10. Webhook Event Design

First supported events:

- `installation`
- `installation_repositories`
- `repository` if useful for renamed/deleted repos
- `pull_request`
- `push` optional for branch existence updates

First production behavior:

- Installation added/removed: update workspace installation status only when it can be associated safely.
- Repository added/removed: sync workspace repository cache.
- PR opened/synchronized/closed/merged: attach/update PR links if branch/repo matches an existing `IssueGitLink`.

Later behavior:

- PR merged can optionally transition Plane issue state if project policy maps PR merged to a state.

---

## 11. Backward Compatibility and Migration

### 11.1 Keep current sidebar alive

The current `github-sync.service.ts` and issue sidebar panel are the live MVP surface. Do not break them while adding admin/workspace setup.

### 11.2 Migrate static env behavior

Phase migration:

1. Add dynamic config models/endpoints without removing env fallback.
2. If env vars exist, surface them as “legacy configured” status to instance admin only.
3. Add migration/management path to convert existing hardcoded project mappings into dynamic workspace installation mappings.
4. Once dynamic setup is verified, remove or deprecate env fallback.

### 11.3 Preserve existing links

Existing `IssueGitLink` records remain visible even if:

- Workspace installation is disabled.
- Repo mapping is changed.
- Dynamic config is not yet migrated.

They should be marked read-only/unavailable for new branch creation if integration is disconnected.

---

## 12. Frontend Plan

### 12.1 New authoritative service

Create or adapt:

- `apps/web/core/services/github-sync.service.ts` for issue sidebar operations.
- New setup service, likely:
  - `apps/web/core/services/github-integration.service.ts`
  - or extend `github-sync.service.ts` if project conventions prefer one service.

The service should own:

- instance/workspace status
- install URL
- repo listing/sync
- project mapping CRUD
- branch creation

Avoid the dead old endpoint shape.

### 12.2 Settings pages/components

Likely create/modify, exact route paths to verify:

- Workspace settings GitHub integration page.
- Instance/god-mode GitHub settings page.
- Repository picker component built on `GET /api/workspaces/{slug}/github/repositories/`.
- Project mapping form.

Do not directly reuse old `select-repository.tsx` unless rewritten against the new service.

### 12.3 Issue sidebar states

Modify:

- `apps/web/core/components/issues/issue-detail/github-panel/github-panel.tsx`
- `apps/web/core/components/issues/issue-detail/github-panel/create-branch-button.tsx`
- `apps/web/core/components/issues/issue-detail/github-panel/git-link-item.tsx`

Required states:

- loading
- configured
- unmapped project
- disconnected installation
- permission denied
- create branch disabled
- branch creating
- branch exists/reused
- GitHub error/retry

---

## 13. Implementation Phases

### Phase 0 — Freeze contracts and inspect exact Plane primitives

Owner: Dahab + Opus/Codex read-only.

Tasks:

1. Verify admin/god-mode permission classes and settings route locations.
2. Verify existing integration models:
   - `apps/api/plane/db/models/integration/base.py`
   - `apps/api/plane/db/models/integration/github.py`
3. Verify existing custom MVP model fields:
   - `apps/api/plane/db/models/integration/github_sync.py`
4. Decide final model names and whether to reuse existing `GithubRepository` / `GithubRepositorySync`.
5. Write frozen API contract file before parallel implementation.

### Phase 1 — Backend data model + secret handling

Likely files:

- `apps/api/plane/db/models/integration/github_sync.py`
- New migration under the appropriate Django migrations package.
- Existing model exports/imports for integration models.

Tasks:

1. Add instance app config model or extend existing integration config.
2. Add workspace installation model.
3. Add/adjust repository cache model.
4. Add/adjust project mapping model.
5. Add webhook delivery/idempotency model.
6. Add encrypted secret field usage.
7. Add uniqueness constraints.
8. Add migrations.

### Phase 2 — Backend GitHub client refactor

Likely file:

- `apps/api/plane/services/github/client.py`

Tasks:

1. Replace env-only config loading with injected app config/workspace installation.
2. Add app JWT generation from stored private key.
3. Add installation token creation.
4. Add repo listing.
5. Add branch/ref creation with error mapping.
6. Add validation method for app config.
7. Ensure logs redact auth/secrets.

### Phase 3 — Backend API endpoints

Likely files:

- `apps/api/plane/app/views/github_sync.py`
- `apps/api/plane/app/serializers/github_sync.py`
- `apps/api/plane/app/urls/github_sync.py`
- Parent URL registration if required.

Tasks:

1. Add instance app config/status/validate endpoints.
2. Add workspace status endpoint.
3. Add install URL endpoint.
4. Add callback endpoint with state validation.
5. Add repository list/sync/enable endpoints.
6. Add project mapping endpoints.
7. Adapt issue links/branch endpoints to dynamic mapping.
8. Add webhook endpoint.
9. Add server-side permission checks for each endpoint.

### Phase 4 — Frontend setup UX

Likely files:

- New GitHub integration service under `apps/web/core/services/`.
- Workspace settings integration route/components; verify exact location.
- Instance/god-mode settings route/components; verify exact location.

Tasks:

1. Add status page.
2. Add instance admin config form with write-only secret fields.
3. Add workspace connect/install CTA.
4. Add callback success/error handling page or query handling.
5. Add repository picker using the new endpoint.
6. Add project mapping form.

### Phase 5 — Issue sidebar adaptation

Likely files:

- `apps/web/core/services/github-sync.service.ts`
- `apps/web/core/components/issues/issue-detail/github-panel/github-panel.tsx`
- `apps/web/core/components/issues/issue-detail/github-panel/create-branch-button.tsx`
- `apps/web/core/components/issues/issue-detail/github-panel/git-link-item.tsx`

Tasks:

1. Fetch mapping-aware issue GitHub status.
2. Show setup/unmapped/permission states.
3. Use new branch creation endpoint shape.
4. Display existing links independent of current installation health.

### Phase 6 — Webhook processing

Likely files:

- `apps/api/plane/app/views/github_sync.py` or dedicated webhook view file.
- `apps/api/plane/services/github/` if service module split is warranted.
- Tests.

Tasks:

1. Raw body signature verification.
2. Delivery dedupe.
3. Installation/repository routing.
4. Repository cache update events.
5. PR link update events.
6. Redacted audit/status recording.

### Phase 7 — Migration/legacy cleanup

Files to prune/redirect deliberately:

- `apps/web/core/components/integration/github/select-repository.tsx`
- `apps/web/core/components/project/integration-card.tsx`
- `apps/web/core/services/project/project.service.ts`
- `apps/web/core/services/integrations/github.service.ts`

Tasks:

1. Identify all old GitHub integration routes/callers.
2. Redirect settings entry points to the new GitHub setup page.
3. Remove dead service methods or mark them deprecated behind no-call paths.
4. Ensure no UI exposes broken old workspace integration flow.

### Phase 8 — Verification and dev deploy

Tasks:

1. Backend unit/API tests.
2. Frontend typecheck/lint/build.
3. Local smoke against dev/staging where possible.
4. Deploy to Coolify dev only after user approval.
5. Curl probe dev Plane after deploy.

---

## 14. Test and Verification Plan

### Backend tests

Add tests for:

- Secret write returns masked response.
- Secret read never exposes raw value.
- App config validation success/failure.
- Non-admin cannot configure app.
- Workspace admin can start installation.
- Invalid/expired callback state rejected.
- Unknown installation rejected.
- Repository listing constrained to workspace installation.
- Project mapping cannot use repo from another workspace.
- Issue branch creation requires project access.
- Branch creation idempotency returns existing branch.
- Branch collision returns `409`.
- GitHub error mapping.
- Webhook invalid signature rejected before parsing.
- Webhook replay/delivery dedupe.
- Disabled installation rejects webhook processing.

### Frontend tests/checks

- Typecheck for new service/types.
- Settings page state rendering.
- Repo picker uses new endpoint, not old `workspace-integrations/{id}/github-repositories/`.
- Issue sidebar states.
- Permission-based disabled/hidden controls.
- No raw secret value appears in client state/logging.

### Integration smoke

Manual/dev smoke:

1. Instance admin configures GitHub App.
2. Workspace admin installs GitHub app.
3. Repo list loads.
4. Repo enabled and mapped to project.
5. Issue sidebar shows configured state.
6. Branch creation succeeds.
7. Repeated click/request returns same branch link.
8. PR webhook updates link/status.
9. Disable installation; existing links remain visible, new branch disabled.

---

## 15. Acceptance Criteria

- Docker image no longer requires MRICS-specific GitHub installation IDs or private keys to be baked into env for normal setup.
- Instance/workspace admin can configure/connect GitHub from UI.
- Secrets are write-only, encrypted, masked, and rotatable.
- Workspace repositories are discovered from verified GitHub installation tokens.
- Plane projects map only to repos available to the workspace installation.
- Issue sidebar supports mapped/unmapped/disconnected/permission states.
- Branch creation is idempotent and handles GitHub errors cleanly.
- Webhook verifies signature with raw body, dedupes deliveries, and routes by verified installation/repository.
- Old broken GitHub integration UI/services are removed, redirected, or clearly unreachable.
- Existing MVP links remain visible after migration.
- Backend tests and frontend build/typecheck pass.
- Dev deployment smoke passes before production consideration.

---

## 16. Risks and Tradeoffs

### GitHub App Manifest feasibility

GitHub App Manifest flow may be awkward for self-hosted instances with custom callback URLs. If too large, use admin manual GitHub App credential entry as first production slice, still inside UI and write-only.

### Secret encryption support

If Plane lacks a clean encrypted field utility, implementation must avoid adding a risky custom crypto abstraction. Prefer existing Django/Plane secret patterns or a minimal well-reviewed dependency only if necessary.

### Existing Plane integration primitives may be stale

Some old GitHub integration frontend paths appear dead. Reusing them blindly risks preserving broken endpoint shapes. Prefer new authoritative service/UX, then prune old surfaces.

### Migration complexity

Existing `RepoProjectMapping`/`IssueGitLink` data must not be lost. Add explicit migration tests before cleanup.

### Multi-workspace/multi-installation edge cases

One GitHub installation may be connected to multiple Plane workspaces, or one workspace may later need multiple installations. First slice can constrain the model, but constraints must be explicit.

---

## 17. Open Questions

1. Does MRICS need one GitHub App per Plane instance, or should each workspace be able to configure its own app?
2. Is GitHub Enterprise Server required soon?
3. Who exactly is “god-mode” in this Plane fork, and which permission class represents it?
4. Should project admins be able to map repos, or only workspace admins?
5. Should one Plane project support multiple repositories in first slice?
6. Should PR merged transition Plane issue state in v1, or stay later?
7. Which existing encrypted secret pattern should be used in Plane backend?
8. Should PAT fallback be implemented at all, or go directly to GitHub App credentials UI?

---

## 18. Herdr / Agent Execution Plan for Later Implementation

When Hijazi says to implement:

### Step A — Dahab prepares frozen contract

- Save API/data model contract to `/opt/data/tmp/plane-github-dynamic-contract.md`.
- Confirm exact permission classes/routes.
- Confirm final model reuse decisions.

### Step B — Opus 5 read-only final architecture check

Run through Herdr shell-pane noninteractive mode if Claude TUI onboarding remains unreliable.

Prompt:

- “Review this frozen contract and repo state. Do not edit. Find contradictions/gaps only.”

### Step C — Parallel implementation slices

Use worktrees if parallelizing.

1. **Backend model/migration slice**
   - Worker: Claude Sonnet 5.
   - Owns model/migration files only.
2. **Backend API/client slice**
   - Worker: Claude Sonnet 5 after model contract freezes.
   - Owns views/serializers/client/tests.
3. **Frontend setup UX slice**
   - Worker: Claude Sonnet 5 or Codex Terra.
   - Owns settings/service components only.
4. **Issue sidebar adaptation slice**
   - Worker: Codex Terra or Sonnet 5.
   - Owns sidebar/panel files only.
5. **Read-only review**
   - Worker: Codex Terra/Sol after diffs exist.
   - Use `danger-full-access` read-only prompt only if Codex `bwrap` sandbox blocks file reads; verify `git status` stays clean after.

### Step D — Dahab integrates/verifies

Dahab must:

- Inspect diffs.
- Resolve conflicts.
- Run backend/frontend tests.
- Verify no secrets in logs/API responses.
- Verify old GitHub UI dead paths are gone.
- Commit only after review.
- Deploy only after user approval.

---

## 19. Immediate Next Step Recommendation

Before coding, hold one short product decision:

**Recommended default:** implement GitHub App credentials UI + installation flow first, not PAT fallback.

Reason:

- It solves reusability properly.
- It avoids teaching customers a temporary PAT flow.
- It aligns with GitHub webhook/installation-token security model.

Only choose PAT fallback if the next implementation window must be significantly smaller and branch creation is the only urgent capability.

---

## 20. Opus 5 Late-Pass Amendments — Superseding Implementation Notes

The delayed Herdr Opus 5 full pass completed after the first saved version of this PRD. These amendments should be treated as **implementation-specific refinements** and supersede any more generic language above where they conflict.

### 20.1 Prefer existing Plane secret/config infrastructure over a new config model

Opus found that the central implementation does **not** need much new infrastructure. Before creating a dedicated `GithubAppConfig` table/model, the implementer should verify and preferably reuse:

- `InstanceConfiguration`
- existing Fernet encryption helpers
- `InstanceAdminPermission`
- existing `apps/admin` configuration form patterns
- existing Celery/bgtasks infrastructure

Concrete verification points before coding Phase 0:

1. `settings.SKIP_ENV_VAR` still defaults to `"1"` in `apps/api/plane/settings/common.py` — DB-over-env precedence matters for removing deploy-time GitHub secrets.
2. `InstanceConfigurationEndpoint.patch` still encrypts on write for `is_encrypted` keys in `apps/api/plane/license/api/views/configuration.py`.
3. `allow_permission` still accepts `level="WORKSPACE"` in `apps/api/plane/app/permissions/base.py`.

If these still hold, prefer storing GitHub App secrets as encrypted instance configuration keys instead of introducing a fresh secret-storage abstraction.

### 20.2 Use `GITHUB_APP_` names; do not collide with OAuth login keys

Use a strict `GITHUB_APP_` prefix for the self-hosted GitHub App configuration, for example:

- `GITHUB_APP_ID`
- `GITHUB_APP_SLUG`
- `GITHUB_APP_PRIVATE_KEY`
- `GITHUB_APP_WEBHOOK_SECRET`
- `GITHUB_APP_CLIENT_ID`
- `GITHUB_APP_CLIENT_SECRET`

Do **not** reuse `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET`; those are live OAuth-login keys in Plane and a naming collision would break sign-in.

Acceptance test addition: configuring the GitHub App must leave OAuth-login GitHub keys untouched.

### 20.3 Manifest flow should be first-class, with manual credential entry as fallback

Preferred admin flow:

- Plane admin creates a GitHub App through GitHub App Manifest conversion from the admin UI.
- Plane receives app ID/client credentials/private key/webhook secret through the browser↔Plane↔GitHub flow.
- User does not manually create the app, download a `.pem`, or transmit secrets through chat/deployment config.

Fallback flow:

- Manual credential entry remains a first-class fallback if manifest conversion fails or is not viable for a self-hosted deployment.
- Error copy should explicitly offer manual fallback on manifest conversion failure.

### 20.4 API namespace refinement

For instance-level app configuration, prefer an instance/admin namespace if it matches current Plane patterns:

- `GET /api/instances/github-app/`
- `PATCH /api/instances/github-app/`
- `DELETE /api/instances/github-app/`
- `POST /api/instances/github-app/test/`
- `POST /api/instances/github-app/manifest/`
- `GET /api/instances/github-app/manifest/callback/`

Workspace-scoped endpoints remain under the workspace GitHub namespace.

### 20.5 Installation token caching is required

The current MVP appears to mint installation tokens too frequently. Add a 50-minute cache keyed by installation ID, invalidated on GitHub `401`.

Acceptance criterion: branch creation should not mint a fresh installation token for every individual GitHub API call.

### 20.6 Branch/ref validation should be a first-class phase

Add a dedicated helper module, likely:

- `apps/api/plane/services/github/refs.py`

Required helpers:

- `validate_branch_name()`
- `validate_repo_full_name()`

Reject invalid refs before any GitHub API call. Table-driven denylist tests should include spaces, `..`, leading dash, `.lock`, `@`, double slash, `~^:?*[\\`, NUL, and overlong names.

### 20.7 Webhook body/signature details

The MVP already reads `request.body` correctly for HMAC verification. Keep this behavior and add regression coverage with `content_type="application/json"` so DRF/middleware body consumption does not break verification.

Webhook endpoint additions:

- fail closed if webhook secret missing
- size guard with `413`
- duplicate delivery returns `200` with no task dispatched
- unknown installation returns only after signature check
- unclaimed installation can be accepted/queued safely depending on install flow
- out-of-order PR events discarded by `last_event_at`

### 20.8 PR correlation and polling fallback

Add PR-related fields to `IssueGitLink` if missing:

- `external_id`
- `head_branch`
- `author_login`
- `last_event_at`

Correlation rules:

1. Exact head-branch match wins.
2. Issue/work-item identifier regex match is secondary.
3. Cross-workspace identifier collision must not link.
4. No match should not create an orphan row.

If webhooks are unreachable, polling fallback should converge PR state within one 15-minute poll cycle and show an unhealthy webhook banner.

### 20.9 Migration ratchet and backward compatibility

For the mapping migration, use a ratchet:

1. Add installation FK/repository fields while keeping legacy integer `github_installation_id`.
2. Backfill into `GithubInstallation`/equivalent rows per workspace.
3. Keep API responses exposing the legacy computed `github_installation_id` until the shipped panel and previous frontend bundle are proven compatible.
4. Drop the legacy column only in a later release.

Regression guard: the phase-0 frontend bundle should still be able to drive the phase-N API for mapping list, git-link list, and branch creation until the planned cleanup release.

### 20.10 Dead-code cleanup caveat

Before deleting `apps/web/core/components/project/integration-card.tsx`, verify whether the Slack path in that file is still live. If Slack still uses it, delete only the GitHub branch/logic rather than the whole file.

Still remove or rewrite old GitHub-specific paths after the new flow lands:

- old `select-repository.tsx` usage tied to `workspace-integrations/*/github-repositories`
- old GitHub importer components/services
- old `project.service.ts` GitHub methods
- orphaned constants/types such as `PROJECT_GITHUB_REPOSITORY`, `IGithubRepoInfo`, `IGithubServiceImportFormData`, `GithubRepositoriesResponse` if no longer referenced

### 20.11 Additional acceptance criteria from Opus

- A container with zero `GITHUB_*` env vars can be configured end-to-end through UI and create a branch.
- No API response contains private key, webhook secret, or client secret substrings at any permission level.
- Two workspaces can connect different GitHub organizations and see only their own repos.
- A webhook for installation X updates only the workspace that owns X.
- A user with admin in workspace A and no membership in workspace B gets `403` on every `/api/workspaces/B/github/*` endpoint.
- Upgrade from commit `60f38c2` with env vars and legacy mappings continues to create branches with zero configuration changes.
- After cleanup, grep for `workspace-integrations/*/github-repositories` returns nothing.

### 20.12 Revised implementation sequencing

Recommended phase ordering after Opus late pass:

1. **P0 — Existing config plumbing and frozen contract**: verify `InstanceConfiguration`, encryption, permissions, env precedence, endpoint names.
2. **P1/P2 — Instance GitHub App manifest/credentials + admin UI**: security-sensitive; Claude/Sonnet implementation with Opus/Codex review.
3. **P3/P4 — Workspace installations, repository listing, project mapping, migration ratchet**: can proceed in parallel with P1/P2 after P0 if the contract is frozen.
4. **P5 — Branch validation/error taxonomy/token caching**: table-driven and suitable for Codex implementation/review.
5. **P6/P7 — Webhook PR linking + polling fallback/health**: sequential, subtle, Claude/Sonnet implementation.
6. **P8 — Dead-code cleanup**: mechanical deletion after verifying Slack caveat and after the new flow is live.

---

## 21. OSS Benchmark Amendment — Coolify and Dokploy GitHub App Patterns

This section was added after reviewing open-source self-hosted products that implement GitHub integration, especially Coolify and Dokploy. The goal is to double-check the Phase 3.1 PRD against proven real-world patterns.

### 21.1 Sources inspected

Primary source trees inspected locally:

- Coolify: `coollabsio/coolify`, inspected commit `5711930`
- Dokploy: `Dokploy/dokploy`, inspected commit `5df820a`

Relevant Coolify files:

- `app/Models/GithubApp.php`
- `app/Livewire/Source/Github/Create.php`
- `app/Livewire/Source/Github/Change.php`
- `resources/views/livewire/source/github/change.blade.php`
- `app/Http/Controllers/Webhook/Github.php`
- `bootstrap/helpers/github.php`
- `app/Policies/GithubAppPolicy.php`
- `app/Http/Controllers/Api/GithubController.php`
- `tests/Feature/Security/GithubAppSetupCallbackTest.php`
- `tests/Feature/GithubWebhookTest.php`

Relevant Dokploy files:

- `packages/server/src/db/schema/github.ts`
- `apps/dokploy/pages/api/providers/github/setup.ts`
- `apps/dokploy/components/dashboard/settings/git/github/add-github-provider.tsx`
- `packages/server/src/utils/providers/github.ts`

### 21.2 Verdict: our PRD direction is validated

Both Coolify and Dokploy use the same broad product pattern this PRD recommends:

1. The self-hosted product stores a GitHub provider/App record in its own database.
2. The user/admin configures the GitHub connection from the product UI, not by baking secrets into Docker image env vars.
3. GitHub App Manifest flow is used to generate app credentials from a browser form posted to GitHub.
4. GitHub returns credentials to a callback endpoint; the product persists app ID/client credentials/private key/webhook secret.
5. Installation ID is captured separately after installing the app.
6. Repository and branch pickers use installation-authenticated GitHub API calls.
7. Webhooks are verified by HMAC and mapped back to the stored GitHub App / installation / resources.

So the PRD’s shift away from MRICS-specific env vars and toward in-product admin/workspace setup is not speculative; it matches the pattern used by comparable self-hosted open-source deployment tools.

### 21.3 Coolify pattern — what to copy conceptually

Coolify is the stronger benchmark because it is self-hosted, open-source, multi-team, and deploys private GitHub repositories.

#### Data model

Coolify has a first-class `GithubApp` model with:

- team ownership: `team_id`
- app identity: `app_id`, `name`, `organization`
- install identity: `installation_id`
- GitHub endpoints: `api_url`, `html_url`
- secrets: `client_secret`, `webhook_secret`, private key via `private_key_id`
- scope flag: `is_system_wide`
- permission snapshots: `contents`, `metadata`, `pull_requests`, `administration`

Action for Plane:

- Our PRD should keep its split between instance-level GitHub App registration and workspace-level installation/repository/project mappings, but Coolify confirms that a dedicated provider/App record is a normal product object, not a deployment-time secret blob.

#### UI setup

Coolify’s UI offers two setup cards:

- **Automated Installation** — recommended; uses GitHub App Manifest.
- **Manual Installation** — advanced fallback for custom/GitHub Enterprise cases.

Coolify’s manifest form includes:

- `hook_attributes.url`
- `redirect_url`
- `setup_url`
- `setup_on_update: true`
- `request_oauth_on_install: false`
- `public: false`
- `default_permissions`
- `default_events`

Action for Plane:

- Keep exactly this UX hierarchy: “Automated / recommended” first, “Manual / advanced fallback” second.
- Add a “custom webhook endpoint” option for self-hosted instances behind Cloudflare Tunnel/reverse proxies where public callback URL differs from internal/base URL.

#### System-wide warning

Coolify supports `is_system_wide` but explicitly warns it is not recommended because any team can use that GitHub App to deploy from repositories. It recommends team-specific GitHub Apps for security/isolation.

Action for Plane:

- Our workspace-scoped connection design is validated.
- If an instance-wide app registration is reused across workspaces, the PRD must ensure installation/repository authorization is still workspace-isolated.
- Add UI warning if any “available to all workspaces” mode is ever exposed.

#### State/callback security

Coolify uses cached one-time state records keyed by SHA256 of random state:

- state payload includes `action`, `github_app_id`, `team_id`
- manifest callback consumes state with `Cache::pull`
- install callback separately consumes install state
- wrong action → rejected
- replayed state → rejected
- another team’s state → rejected
- unauthenticated callback → rejected before calling GitHub
- already configured app cannot be rebound by manifest callback
- installation ID is verified against GitHub `/app/installations/{installation_id}` before being persisted

Action for Plane:

- Add explicit `GithubSetupState` / cache-backed one-time state mechanism.
- State must bind: action, user/admin, workspace/instance, target GitHub connection/app, expiry, and redirect destination.
- State must be consumed atomically on first use.
- Installation callback must verify installation belongs to the configured app before persisting.

#### GitHub Enterprise support

Coolify derives API URL from HTML URL:

- `github.com` → `https://api.github.com`
- `*.ghe.com` → `https://api.<host>`
- GitHub Enterprise Server → `<origin>/api/v3`

It also tests manifest conversion and install verification against `*.ghe.com` data residency hosts.

Action for Plane:

- Add GitHub Enterprise URL derivation to Phase 3.1 or explicitly mark as Phase 3.2.
- At minimum, model fields should not assume only `github.com`; store `html_url` and `api_url`.

#### Webhook handling

Coolify normal webhook flow:

- reads `X-GitHub-Event`
- reads `X-GitHub-Hook-Installation-Target-Id`
- finds `GithubApp` by `app_id`
- fails if webhook secret missing
- verifies `X-Hub-Signature-256` against raw request body using HMAC SHA-256 and constant-time comparison
- handles `installation` / `installation_repositories` events as setup/permission events
- handles `push` and `pull_request`
- maps push/PR events to application records by repository id + source id + branch/base branch
- dispatches async jobs for PR handling

Action for Plane:

- Keep webhook secret fail-closed behavior.
- Resolve GitHub App by `X-GitHub-Hook-Installation-Target-Id` / app ID first, but do not mutate tenant data until signature passes.
- For Plane’s PR linking, map by installation/repository/project/branch, not only repo name.

#### Repository and branch listing

Coolify lists repositories by calling `/installation/repositories` with installation token, `per_page=100`, up to a safety cap of 100 pages. It lists branches through `/repos/{owner}/{repo}/branches` with retries/timeouts.

Action for Plane:

- Our repo picker endpoint should use installation token and pagination.
- Add a hard safety cap and clear stale-cache behavior.
- Add timeout/retry policy and preserve GitHub error messages only if safe.

#### Token generation

Coolify creates a GitHub App JWT, then exchanges it for an installation token. It currently appears to mint installation tokens directly per call through helper functions.

Action for Plane:

- Our PRD’s token-cache requirement is an improvement over Coolify: cache installation tokens until near expiry, invalidate on 401.

#### Sensitive fields

Coolify hides `client_secret` and `webhook_secret` on the model by default, but some API paths can reveal them when a `can_read_sensitive` request attribute is set. Private key is stored separately as a `PrivateKey` model.

Action for Plane:

- Keep the stricter PRD stance: secrets should be write-only/masked by default. Reveal only if we deliberately design an admin “show once / rotate” flow.
- Never return private key or webhook secret in normal API responses.

### 21.4 Dokploy pattern — validates manifest flow but is weaker on state binding

Dokploy also uses GitHub App Manifest:

- UI builds a manifest and posts to GitHub app creation URL.
- Callback calls `POST /app-manifests/{code}/conversions`.
- It stores app ID, client ID/secret, webhook secret, private key, installation ID.
- It uses Octokit `createAppAuth` for app/installation authentication.
- Repo picker uses `apps.listReposAccessibleToInstallation`.
- Branch picker uses `repos.listBranches`.

Important contrast:

- Dokploy state format is visibly string-based (`gh_init:<organizationId>:<userId>` / `gh_setup:<githubId>`) rather than a random one-time cache-bound state like Coolify.
- The callback checks authenticated user/org and permissions, but Coolify’s state strategy is stronger against replay, cross-action confusion, and tampering.

Action for Plane:

- Copy the manifest-flow shape from Dokploy/Coolify, but copy Coolify’s stronger one-time state model, not Dokploy’s plain encoded state string.

### 21.5 Additional PRD changes implied by OSS review

Add/keep these explicit requirements:

1. **Public URL / webhook endpoint selection**
   - Admin can choose detected instance URL or custom public webhook base URL.
   - Required for Cloudflare Tunnel, reverse proxy, sslip, and unusual self-hosted setups.

2. **GitHub Enterprise readiness**
   - Store both `html_url` and `api_url`.
   - Derive API URL from HTML URL.
   - Support `github.com`, `*.ghe.com`, and GHES `/api/v3`, or explicitly defer with compatible schema.

3. **One-time setup state**
   - Manifest and install callbacks use separate one-time state actions.
   - Wrong action, missing state, expired state, replayed state, unauthenticated callback, and wrong workspace/team are all rejected before any external mutation.

4. **Installation verification**
   - Before saving installation ID, call GitHub App API to verify the installation belongs to our app ID.

5. **Permission snapshot/health**
   - Store or display effective permissions: contents, metadata, pull requests, administration if needed.
   - Provide a “refetch permissions”/health check action.

6. **Resources using this connection**
   - Add a UI tab showing projects/resources currently using a GitHub connection before deletion.
   - Block delete while mappings/resources depend on it unless user first unmaps them.

7. **Team/workspace-specific default**
   - Default to workspace-specific connections.
   - If instance-wide/system-wide connection exists, warn and strictly enforce repository access boundaries.

8. **Repository picker pagination**
   - Use installation-token API, `per_page=100`, explicit max pages, timeout/retry, and sort/search.

9. **Webhook test matrix**
   - Add tests mirroring Coolify’s callback tests: auth required, invalid state rejected, configured app cannot be rebound, replay rejected, wrong action rejected, wrong team/workspace rejected, unknown setup action rejected, installation ID verified, GHES/GHE host respected.

10. **Secret response policy**

- Coolify proves masking is necessary; our spec should go stricter: secrets are never returned except in a deliberate, audited, highly privileged reveal/show-once flow.

### 21.6 Final OSS benchmark conclusion

The PRD is architecturally correct. Coolify and Dokploy both validate the core decision:

> a reusable self-hosted product should create/configure GitHub integration dynamically through the product UI using GitHub App Manifest and installation callbacks, then use stored app/installation credentials for repo listing, branch operations, and webhook handling.

The most important improvement from this benchmark is to make **Coolify-style one-time setup state + installation verification + custom public webhook URL + GitHub Enterprise URL derivation** explicit acceptance criteria before implementation starts.

---

## 22. Sub-Agent Review Reconciliation — Accepted Additions and Rejected Simplification

A follow-up independent sub-agent review broadly agreed with the PRD and the OSS benchmark, but introduced a few extra implementation details worth preserving. This section reconciles that review with the direct source inspection above.

### 22.1 Accepted additions

#### Dedicated private-key resource/fingerprint dedup

Coolify stores private keys separately and references them from `GithubApp` by ID/UUID. For Plane, the implementation should prefer one of these two approaches, in order:

1. Reuse or extend an existing Plane secret/private-key facility if one exists and is appropriate.
2. Otherwise create a narrow `GithubPrivateKey` model rather than putting PEM text inline on every GitHub connection record.

Recommended fields:

- `id`, `workspace` or `owned_by_instance` depending on final scope
- `name`
- `private_key_encrypted`
- `fingerprint`
- `key_type`
- `is_git_related`
- `created_by`, `updated_by`, timestamps

Validation requirements:

- Parse PEM using Python `cryptography.hazmat.primitives.serialization.load_pem_private_key` or equivalent.
- Derive public-key fingerprint.
- Reject duplicate fingerprints with a clear `409`/validation error.
- Serialize only masked/fingerprint metadata, never PEM material.

Rationale: this makes rotation, deduplication, reuse, and future GitLab/Bitbucket support cleaner than copying the same encrypted PEM field into every provider row.

#### Explicit token cache mechanics

Add these concrete cache rules to the `GitHubClient` implementation:

- App JWT cache key: `github:app_jwt:{app_config_id}`
- App JWT TTL: about 9 minutes; GitHub App JWT max lifetime is 10 minutes.
- Installation token cache key: `github:installation_token:{installation_id}`
- Installation token TTL: about 50 minutes; installation tokens typically expire after 60 minutes.
- Use Django cache so tokens are shared across web/Celery workers when Redis/cache backend is configured.
- Invalidate the relevant token cache on GitHub `401` and retry once with a fresh token.
- Never persist access tokens in the database unless a later requirement explicitly needs durable auditing; prefer cache-only tokens.

#### Repository cache TTL and webhook refresh

If the PRD includes a `GithubRepository` cache table, make the cache contract explicit:

- `last_synced_at` is required.
- Default TTL: 5 minutes for UI picker freshness.
- `installation_repositories` webhooks should enqueue a Celery refresh for the affected installation.
- Stale cache can be served with a visible refresh state only if GitHub is unreachable; otherwise refresh live.
- Repo picker must still support explicit manual refresh.

#### Installation suspension/revocation handling

Webhook handling must include `installation` events beyond only `created`/`deleted` happy paths:

- `suspended`: mark installation inactive/suspended, block branch/PR operations, show reconnect instructions.
- `unsuspended`: revalidate permissions and mark active if checks pass.
- `deleted`: mark inactive/revoked, clear repo cache availability, keep historical issue links read-only.
- `installation_repositories`: refresh repository cache and unmap removed repositories only after explicit safety checks.

#### Delete guard

Before deleting/disabling a GitHub app/installation/private key, return `409` if active dependent resources exist:

- repo/project mappings
- issue Git links
- scheduled sync jobs
- cached webhook state if relevant

Response should include dependency counts and links/names when safe. Do not cascade-delete silently.

#### Serializer-level secret stripping

Model-level hidden fields are not enough. Enforce secrecy at serializer/view layer:

- DRF secret inputs are `write_only=True`.
- `to_representation()` strips any raw encrypted/raw secret fields unconditionally.
- Normal responses return only booleans, timestamps, fingerprints, and masked labels.
- Any future reveal/show-once endpoint must be separately permissioned and audited.

### 22.2 Rejected or corrected sub-agent point

The sub-agent recommended making manual credential entry the primary Phase 1 path and deferring manifest/callback flow because it believed Coolify primarily follows a direct-credential-entry flow. Direct source inspection shows the benchmark is more nuanced:

- Coolify has a manual/advanced credential-entry path.
- Coolify also has an automated GitHub App setup path in the UI using a manifest/callback flow.
- Dokploy also uses GitHub App Manifest conversion.

Therefore, this PRD should **not** demote manifest setup as a product goal. The correct implementation stance is:

1. **Preferred UX:** automated GitHub App Manifest setup from the admin UI when the instance has a valid public callback/webhook URL.
2. **Required fallback:** manual credential entry for self-hosted instances with unreachable callbacks, pre-existing GitHub Apps, GitHub Enterprise quirks, or admin preference.
3. **Implementation sequencing option:** if engineering wants the smallest first working slice, manual entry can ship first internally, but the user-facing PRD must still treat automated manifest setup as the target/default UX.

### 22.3 Final reconciled guidance for implementers

Use this decision matrix:

| Situation                                             | Flow                                                   |
| ----------------------------------------------------- | ------------------------------------------------------ |
| Instance has public URL and admin wants easiest setup | Automated GitHub App Manifest flow                     |
| Instance is private/local/tunnel not yet configured   | Manual credential entry or custom public URL first     |
| Existing GitHub App already exists                    | Manual credential entry/import                         |
| GitHub Enterprise or unusual API host                 | Manual entry first; manifest if verified for that host |
| Development/test environment                          | Manual entry acceptable for P1 smoke                   |

This preserves Coolify/Dokploy’s proven product UX while still allowing a low-risk incremental implementation path.

---

## 23. Implementation and Dev Acceptance Record — 2026-07-31

The dynamic GitHub integration implementation described by this PRD is now merged into `mrics/dev` through [PR #3](https://github.com/MRICS-technologies/mrics-plane/pull/3), merge commit `67803a8d069bdaac269f098b76846d25367e54ac`.

### Delivered in this rollout

- Instance-level, write-only GitHub App configuration and workspace-scoped installations/repositories/mappings.
- Signed GitHub `pull_request` webhook handling that resolves a mapped Plane issue and creates or updates its PR link for `opened`, `reopened`, `closed`, `merged`, and `synchronize` events.
- Raw-body HMAC verification, fail-closed invalid-signature behavior, request-payload/signature log exclusion, payload limiting, required delivery IDs, transactional replay/delivery deduplication, tenant-scoped PR identity, stale-event protection, and soft-delete-safe restoration.
- Focused contract coverage, including malformed/no-match payload safety and logger protections.

### Verified evidence

- PostgreSQL/Redis contract tests passed on the feature branch after independent review corrections (84 tests).
- The exact merged `mrics/dev` SHA passed the same hosted PostgreSQL/Redis contract workflow: [run 30616470428](https://github.com/MRICS-technologies/mrics-plane/actions/runs/30616470428).
- Matching backend and frontend images were built successfully for the merge SHA and pulled by the Coolify dev service.
- Dev availability was verified: the frontend returned `200` and the protected Plane API returned the expected `401` without credentials.

### Explicit non-scope / remaining gate

- This rollout links and updates PR records; it does not yet automate Plane issue workflow-state transitions from PR actions.
- No production deployment occurred.
- Final dev acceptance still requires one real GitHub App Pull request webhook delivery against a configured, mapped repository. The GitHub webhook secret must be entered directly in the relevant admin UI and never stored in Git, this PRD, logs, or chat.
