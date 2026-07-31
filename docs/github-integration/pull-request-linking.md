# Pull request linking

The webhook feature keeps a Plane issue’s Git links synchronized with the pull request that relates to it. It creates or updates a PR link; it does **not** change the Plane issue’s workflow state.

## Event flow

```text
GitHub pull_request delivery
  → POST /api/github/webhook/
  → verify signature over raw body
  → verify delivery id, installation, enabled repository, and mapping
  → resolve the Plane issue
  → create or update one PR link
```

## Supported lifecycle events

| GitHub action | Plane link state |
| --- | --- |
| `opened` | `open` |
| `reopened` | `open` |
| `synchronize` | `open` |
| `closed` with `merged: false` | `closed` |
| `closed` with `merged: true` | `merged` |

Unsupported actions are acknowledged without modifying a link. This keeps the initial scope narrow and predictable.

## How Plane resolves the issue

Plane uses the following order and creates a link only when it gets one unambiguous result:

1. **Existing PR link** — later events update the existing link even if a key is no longer present in the PR title or branch.
2. **Existing Plane-created branch link** — the PR head branch is matched to an existing branch link for one mapped project.
3. **Issue key** — Plane searches the PR title and head branch for an issue key using the mapped project identifier, for example `TP-123`.

If multiple mappings match or no mapped issue is found, Plane does nothing. It will not guess and attach the PR to an unrelated issue.

## Expected developer workflow

1. Create or select a Plane work item, for example `TP-123`.
2. Use the Plane branch-creation action where possible. It records the branch link and gives the webhook the strongest correlation signal.
3. If creating a branch manually, include the issue key in the branch name, for example `feature/TP-123-webhook-linking`.
4. Include the key in the PR title as a fallback, for example `TP-123: link webhook deliveries`.
5. Open, update, close, reopen, or merge the PR normally.

## Link guarantees

- A GitHub PR number is unique only inside its Plane workspace and repository context.
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
