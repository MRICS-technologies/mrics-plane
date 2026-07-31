# Administrator setup

This guide configures GitHub once at the instance level, then scopes its use through workspace installations and project mappings.

## Before you begin

You need:

- A public HTTPS URL that reaches the Plane API.
- A GitHub App owned by the intended organization or account, or permission to create one.
- A Plane **instance administrator** and a Plane **workspace administrator**.
- Permission to install the app on the repository that will be mapped.

> [!warning]
> Do not copy private keys, client secrets, or webhook secrets into this repository, browser console output, issue comments, or chat. Enter them directly through the approved GitHub and Plane admin forms.

## 1. Configure the GitHub App in Plane

Open Plane’s instance/God-mode GitHub App configuration. The matching backend resource is `/api/instances/github-app/`; secret inputs are write-only and normal responses must not return the raw values.

Provide the App identifiers and credentials requested by the form, plus the public webhook destination:

```text
<PLANE_PUBLIC_URL>/api/github/webhook/
```

For the current MRICS dev environment, this is:

```text
https://mrics-plane-dev.193.122.88.185.sslip.io/api/github/webhook/
```

Use the **Test** action in the instance configuration UI before moving on. A missing or unusable configuration must fail clearly; it must never downgrade webhook signature checks.

## 2. Configure the GitHub App in GitHub

In the GitHub App settings:

1. Set the webhook URL to the Plane API endpoint above.
2. Set the webhook secret to the same value saved in Plane’s GitHub App configuration.
3. Subscribe to the **Pull requests** event.
4. Install the app only on the repositories Plane should be allowed to use.

The current PR-linking slice handles `opened`, `reopened`, `synchronize`, and `closed` events (including merged PRs). Other pull-request actions are acknowledged without changing a Plane link.

## 3. Register the workspace installation

Open the workspace GitHub settings and register the GitHub App installation. Plane validates that the installation is active before it permits branch or PR-link operations.

The API resource is:

```text
/api/workspaces/<workspace-slug>/github/installation/
```

## 4. Enable repositories

Load the repositories accessible to the registered installation, then enable only the repositories that the workspace should use.

```text
/api/workspaces/<workspace-slug>/github/repositories/
```

A webhook from a repository that is not enabled is intentionally ignored. This prevents a valid GitHub event from affecting an unrelated Plane project.

## 5. Map each repository to one Plane project

From the project GitHub settings, map one enabled repository to the target Plane project.

```text
/api/workspaces/<workspace-slug>/projects/<project-id>/github/mappings/
```

Mappings are the authorization boundary for PR linking. A PR event without a current mapping does not create a Plane link.

## Setup checklist

- [ ] Plane instance GitHub App configuration passes its local test.
- [ ] GitHub App points at the right public Plane API endpoint.
- [ ] Pull requests event is enabled in GitHub.
- [ ] The installation is registered and active for the intended Plane workspace.
- [ ] The repository is enabled for that installation.
- [ ] The repository is mapped to the correct Plane project.
- [ ] The dev smoke test has been completed before any production decision.
