# Getting started — GitHub integration

Four steps, no credentials ever typed. The whole setup is designed to feel like
"it just works": the app is created for you, the repos are discovered for you,
and the mappings are a checkbox list.

## 1. Create the GitHub App (one click, instance-level)

1. Log in to the **instance admin** (`/god-mode/`)
2. Open **GitHub App** from the sidebar (`/god-mode/github-app/`)
3. Click **Create GitHub App**
4. GitHub opens (make sure you are logged in to GitHub in that browser):
   - **Optional:** fill the **Organization** field _before_ clicking create to
     create the app under a GitHub organization instead of your personal
     account — this matters when the org restricts third-party app installs
     (see [Troubleshooting](troubleshooting.md#organization-access))
   - Approve the manifest → the app is created and configured automatically

The app is an _identity_: it has no repositories of its own. Workspaces connect
to it in the next step.

> **Recreating the app** resets every workspace connection automatically
> (repos, mappings, and links are cleaned up). This is intentional — after a
> reconfig, each workspace simply connects again.

## 2. Connect a workspace (one per workspace)

1. In the app, open **Workspace Settings → GitHub**
2. Click **Connect GitHub**
3. GitHub asks which account to install the app for — pick the **organization
   or account** whose repositories you want (organizations only appear when the
   app is allowed for them; see Troubleshooting)
4. Grant the repositories → back in Plane, the connection is live

One installation per workspace — a workspace cannot stack two connections.

## 3. Enable repositories

The workspace GitHub panel lists the granted repositories **live from GitHub**
(no IDs to type). Check the ones this workspace wants to use.

## 4. Attach repositories to projects

1. Open **Project Settings → GitHub** (or the _Attach GitHub repo (recommended)_
   prompt on a project without one)
2. Pick from the workspace's enabled repositories
3. Set the **base branch** (used when creating branches) and which mapping is
   the project **default** (used by the issue panel when multiple repos map to
   the same project)

Rules that are enforced:

- A project can map **multiple** repositories — exactly **one** is the default
- The **same** repository can be mapped into **many** projects
- A repository cannot be mapped **twice** into the same project

## Done — where the magic happens

Open any issue → the **GitHub panel** shows:

- **Create branch** (or link an existing branch) — see [Usage](usage.md)
- Any linked branch/PR with their current state

Next step: [Usage](usage.md).
