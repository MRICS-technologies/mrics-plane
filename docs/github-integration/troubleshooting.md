# Troubleshooting — GitHub integration

## Organization access

**Symptom:** the GitHub install dialog only shows your personal account — your
organizations are missing.

**Why:** organizations can restrict third-party application access. A GitHub
App created under a _personal_ account is not automatically allowed for an
organization with restrictions. Apps created under the organization itself are
always allowed for that organization.

**Fix (pick one):**

1. **Create the app under the organization** (recommended):
   - Instance admin → GitHub App → fill the **Organization** field before
     clicking _Create GitHub App_ → the app becomes organization-owned
   - Reconnect each workspace (recreating the app resets connections
     automatically)
2. **Approve the app in the organization:**
   - GitHub → Organization → **Settings → Third-party access** →
     allow this GitHub App (or relax the org policy)

The same org that owns the app can always install it. Other orgs may still need
approval under their own third-party access policy.

## Webhook deliveries

**Symptom:** PR events don't appear on issues, or link states are stale.

Check GitHub's side first: GitHub App settings → **Advanced → Recent
deliveries**:

- **No deliveries** → the app is not subscribed to `pull_request` / `push`, or
  the webhook URL is wrong (it must point to `/api/github/webhook/`)
- **Red / failed deliveries** → GitHub could not reach the endpoint; check
  network/firewall (the URL must be publicly reachable)
- **Green 2xx deliveries but no links** → the event arrived but did not
  correlate: the PR's head branch must match a linked branch name, or the PR
  title must contain the issue ID

## Reconnecting after the app was recreated

Recreating the GitHub App (new app id) **automatically resets** every
workspace: installations, enabled repositories, project mappings, and issue
links are cleaned up. Each workspace then simply **connects again**
(Workspace Settings → GitHub → Connect).

If you see a _"Remove project mappings before disconnecting"_ message on a
healthy installation, that is the safety guard: the confirm dialog explains it
removes the mappings too — confirm once and the disconnect proceeds.

## "Something went wrong" in the repository picker

Usually an orphaned installation (the app was reconfigured but the workspace
was not reconnected). Reconnect the workspace; the picker refreshes from
GitHub.

## Branch creation errors

| Message                                                    | Meaning                                                                       |
| ---------------------------------------------------------- | ----------------------------------------------------------------------------- |
| `No GitHub repository mapping configured for this project` | Attach a repo in Project Settings first                                       |
| `Branch already exists`                                    | The issue is already linked to that branch — reuse the link                   |
| `GitHub App is not configured`                             | The instance admin hasn't created the app yet                                 |
| `Link expired` page after connecting                       | The install state token was already used or too old — click **Connect** again |

## Still stuck?

Check the API container logs for `POST /api/github/webhook/` entries and
GitHub App → Advanced → Recent deliveries, then report both.
