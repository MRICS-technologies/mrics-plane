# Pull request linking

The webhook feature keeps Plane issue Git links synchronized with the pull request that relates to them. It creates or updates PR links; it does **not** change Plane workflow state yet.

## Event flow

```text
GitHub pull_request delivery
  → POST /api/github/webhook/
  → verify signature over raw body
  → verify delivery id, installation, enabled repository, and mapping
  → resolve the Plane issue(s)
  → create or update PR links
```

## Supported lifecycle events

| GitHub action                 | Plane link state |
| ----------------------------- | ---------------- |
| `opened`                      | `open`           |
| `reopened`                    | `open`           |
| `synchronize`                 | `open`           |
| `closed` with `merged: false` | `closed`         |
| `closed` with `merged: true`  | `merged`         |

Unsupported actions are acknowledged without modifying a link. This keeps the initial scope narrow and predictable.

## How Plane resolves the issue

Plane uses the following order:

1. **Existing PR links** — later events update every existing link for the same workspace/repository/PR number, even if a key is no longer present in the PR title or branch.
2. **Existing branch links** — the PR head branch is matched to every live branch link for mapped projects. A shared branch can resolve to multiple Plane issues; the PR fans out to all of them.
3. **Issue key fallback** — when no branch link exists, Plane searches the PR title and head branch for an issue key using the mapped project identifier, for example `TP-123`.

If the fallback issue-key search is ambiguous or no mapped issue is found, Plane does nothing. It will not guess and attach the PR to an unrelated issue.

## Expected developer workflow

1. Create or select one or more Plane work items, for example `TP-123` and `TP-124`.
2. Use the Plane branch create/link action where possible. It records the branch link and gives the webhook the strongest correlation signal.
3. If one branch covers multiple work items, link that same branch from each relevant issue before opening the PR.
4. If creating a branch manually, include the issue key in the branch name, for example `feature/muhammed-tp-123-webhook-linking`.
5. Include the key in the PR title as a fallback, for example `TP-123: link webhook deliveries`.
6. Open, update, close, reopen, or merge the PR normally.

## Link guarantees

- A GitHub PR number is unique per issue inside its Plane workspace and repository context, so the same GitHub PR can appear on every issue linked to a shared branch.
- Repeated delivery IDs are acknowledged without duplicate side effects.
- Older or timestamp-less events cannot regress a newer link state.
- Soft-deleted historical links can be restored safely.
- A PR that belongs to a disabled installation, disabled repository, or unmapped project is not linked.

## Not included yet

The following remain future work:

- Moving a Plane issue to Review, In Progress, or Done from PR activity.
- Multi-PR completion policies.
- Automatic timer changes on PR merge.
- Commit-message fallback matching.
