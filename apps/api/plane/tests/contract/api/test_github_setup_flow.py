# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Contract tests for the Phase 1 GitHub App zero-typing setup flow:

- Instance manifest flow: POST/GET /api/instances/github-app/manifest/{,callback/}
- Workspace one-click install: POST /api/workspaces/<slug>/github/install-url/,
  GET /api/github/setup/
- Live repository discovery: GET /api/workspaces/<slug>/github/available-repositories/
- `GitHubClient` token caching / 401-retry-once / pagination cap

None of these tests contact GitHub -- every GitHub HTTP call is mocked.
"""

import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
import requests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.core.cache import cache
from django.db import IntegrityError
from django.utils import timezone
from rest_framework import status

from plane.db.models import Project, User, Workspace, WorkspaceMember
from plane.db.models.integration.github_app import GithubAppInstallation, GithubEnabledRepository
from plane.db.models.integration.github_sync import RepoProjectMapping
from plane.license.models import Instance, InstanceAdmin, InstanceConfiguration
from plane.license.utils.encryption import decrypt_data, encrypt_data
from plane.services.github import setup_state
from plane.services.github.client import GitHubClient

MANIFEST_URL = "/api/instances/github-app/manifest/"
MANIFEST_CALLBACK_URL = "/api/instances/github-app/manifest/callback/"
SETUP_CALLBACK_URL = "/api/github/setup/"


def _install_url(slug):
    return f"/api/workspaces/{slug}/github/install-url/"


def _available_repos_url(slug):
    return f"/api/workspaces/{slug}/github/available-repositories/"


def _repositories_url(slug):
    return f"/api/workspaces/{slug}/github/repositories/"


def _configure_app(app_id="555111", private_key_pem="fake-key", app_slug="plane-app"):
    InstanceConfiguration.objects.update_or_create(
        key="GITHUB_APP_ID", defaults={"value": app_id, "category": "GITHUB_APP", "is_encrypted": False}
    )
    InstanceConfiguration.objects.update_or_create(
        key="GITHUB_APP_SLUG", defaults={"value": app_slug, "category": "GITHUB_APP", "is_encrypted": False}
    )
    InstanceConfiguration.objects.update_or_create(
        key="GITHUB_APP_PRIVATE_KEY",
        defaults={"value": encrypt_data(private_key_pem), "category": "GITHUB_APP", "is_encrypted": True},
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def instance_admin_client(api_client, create_user):
    instance = Instance.objects.create(
        instance_name="GitHub Setup Test Instance",
        instance_id=str(uuid.uuid4()),
        current_version="1.0.0",
        domain="http://localhost:8000",
        last_checked_at=timezone.now(),
    )
    InstanceAdmin.objects.create(instance=instance, user=create_user, role=20)
    api_client.force_authenticate(user=create_user)
    cache.clear()
    return api_client


@pytest.fixture
def private_key():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()


@pytest.fixture
def second_workspace(db):
    """A workspace the primary `create_user` fixture is never a member of."""
    owner = User.objects.create(email="second-setup-owner@plane.so", username="second-setup-owner")
    owner.set_password("test")
    owner.save()
    ws = Workspace.objects.create(name="Second Setup Workspace", owner=owner, slug="second-setup-workspace")
    WorkspaceMember.objects.create(workspace=ws, member=owner, role=20)
    return ws


# ---------------------------------------------------------------------------
# Instance manifest endpoint
# ---------------------------------------------------------------------------


@pytest.mark.contract
class TestGitHubAppManifestEndpoint:
    @pytest.mark.django_db
    def test_non_admin_is_forbidden(self, api_client, create_user):
        Instance.objects.create(
            instance_name="Non Admin Instance",
            instance_id=str(uuid.uuid4()),
            current_version="1.0.0",
            domain="http://localhost:8000",
            last_checked_at=timezone.now(),
        )
        api_client.force_authenticate(user=create_user)
        resp = api_client.post(MANIFEST_URL, {}, format="json")
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.django_db
    def test_already_configured_returns_403(self, instance_admin_client):
        InstanceConfiguration.objects.create(key="GITHUB_APP_ID", value="123", category="GITHUB_APP")
        resp = instance_admin_client.post(MANIFEST_URL, {}, format="json")
        assert resp.status_code == status.HTTP_403_FORBIDDEN
        assert resp.data["error"] == "already_configured"

    @pytest.mark.django_db
    def test_returns_manifest_post_url_and_state(self, instance_admin_client):
        resp = instance_admin_client.post(MANIFEST_URL, {}, format="json")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["state"]
        assert resp.data["post_url"].endswith("/settings/apps/new")
        manifest = resp.data["manifest"]
        assert manifest["hook_attributes"]["url"].endswith("/api/github/webhook/")
        assert manifest["redirect_url"].endswith("/api/instances/github-app/manifest/callback/")
        assert manifest["setup_url"].endswith("/api/github/setup/")
        assert manifest["default_permissions"] == {
            "contents": "write",
            "metadata": "read",
            "pull_requests": "read",
        }
        # GitHub manifest rules: installation lifecycle events must NOT be
        # declared in default_events (auto-delivered; manifest rejected otherwise).
        assert set(manifest["default_events"]) == {
            "pull_request",
            "push",
        }

    @pytest.mark.django_db
    def test_organization_post_url_targets_org_apps_endpoint(self, instance_admin_client):
        resp = instance_admin_client.post(MANIFEST_URL, {"organization": "acme-corp"}, format="json")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["post_url"].endswith("/organizations/acme-corp/settings/apps/new")


# ---------------------------------------------------------------------------
# Instance manifest callback
# ---------------------------------------------------------------------------


@pytest.mark.contract
class TestGitHubAppManifestCallbackEndpoint:
    """N4: this endpoint is only ever reached via a GitHub browser redirect,
    so every failure -- like every success -- redirects to the admin app
    with a `?github_app=<status>` query param rather than returning raw JSON."""

    @pytest.mark.django_db
    def test_missing_state_redirects_with_invalid_state(self, api_client):
        resp = api_client.get(MANIFEST_CALLBACK_URL, {"code": "abc"})
        assert resp.status_code == status.HTTP_302_FOUND
        assert "github_app=invalid_state" in resp["Location"]

    @pytest.mark.django_db
    def test_forged_state_redirects_with_invalid_state(self, api_client):
        resp = api_client.get(MANIFEST_CALLBACK_URL, {"code": "abc", "state": "not-a-real-state"})
        assert resp.status_code == status.HTTP_302_FOUND
        assert "github_app=invalid_state" in resp["Location"]

    @pytest.mark.django_db
    def test_wrong_action_state_redirects_with_invalid_state(self, api_client, workspace, create_user):
        # A state minted for the *install* flow must not be redeemable here.
        state = setup_state.issue("install", workspace_id=str(workspace.id), user_id=str(create_user.id))
        resp = api_client.get(MANIFEST_CALLBACK_URL, {"code": "abc", "state": state})
        assert resp.status_code == status.HTTP_302_FOUND
        assert "github_app=invalid_state" in resp["Location"]

    @pytest.mark.django_db
    def test_replayed_state_redirects_with_invalid_state(self, api_client, create_user):
        state = setup_state.issue("manifest", user_id=str(create_user.id))
        conversion = {
            "id": 111222,
            "slug": "plane-app",
            "client_id": "cid",
            "client_secret": "csecret",
            "pem": "pem-data",
            "webhook_secret": "whsecret",
        }
        with patch("plane.license.api.views.github_app.GitHubClient.convert_manifest", return_value=conversion):
            first = api_client.get(MANIFEST_CALLBACK_URL, {"code": "abc", "state": state})
        assert first.status_code == status.HTTP_302_FOUND
        assert "github_app=connected" in first["Location"]

        second = api_client.get(MANIFEST_CALLBACK_URL, {"code": "abc", "state": state})
        assert second.status_code == status.HTTP_302_FOUND
        assert "github_app=invalid_state" in second["Location"]

    @pytest.mark.django_db
    def test_expired_state_redirects_with_invalid_state(self, api_client, create_user, monkeypatch):
        monkeypatch.setattr(setup_state, "STATE_TTL_SECONDS", 0)
        state = setup_state.issue("manifest", user_id=str(create_user.id))
        resp = api_client.get(MANIFEST_CALLBACK_URL, {"code": "abc", "state": state})
        assert resp.status_code == status.HTTP_302_FOUND
        assert "github_app=invalid_state" in resp["Location"]

    @pytest.mark.django_db
    def test_already_configured_redirects_with_already_configured(self, api_client, create_user):
        _configure_app()
        state = setup_state.issue("manifest", user_id=str(create_user.id))
        resp = api_client.get(MANIFEST_CALLBACK_URL, {"code": "abc", "state": state})
        assert resp.status_code == status.HTTP_302_FOUND
        assert "github_app=already_configured" in resp["Location"]

    @pytest.mark.django_db
    def test_missing_code_redirects_with_missing_code(self, api_client, create_user):
        state = setup_state.issue("manifest", user_id=str(create_user.id))
        resp = api_client.get(MANIFEST_CALLBACK_URL, {"state": state})
        assert resp.status_code == status.HTTP_302_FOUND
        assert "github_app=missing_code" in resp["Location"]

    @pytest.mark.django_db
    def test_successful_conversion_stores_encrypted_keys_and_hides_secrets(self, api_client, create_user):
        state = setup_state.issue("manifest", user_id=str(create_user.id))
        conversion = {
            "id": 909090,
            "slug": "plane-rework-app",
            "client_id": "client-id-value",
            "client_secret": "client-secret-value",
            "pem": "-----BEGIN FAKE PEM-----",
            "webhook_secret": "webhook-secret-value",
        }
        with patch("plane.license.api.views.github_app.GitHubClient.convert_manifest", return_value=conversion):
            resp = api_client.get(MANIFEST_CALLBACK_URL, {"code": "one-time-code", "state": state})

        assert resp.status_code == status.HTTP_302_FOUND
        assert "github_app=connected" in resp["Location"]
        response_body = resp.content.decode() + resp["Location"]
        for secret in (conversion["client_secret"], conversion["pem"], conversion["webhook_secret"]):
            assert secret not in response_body

        assert InstanceConfiguration.objects.get(key="GITHUB_APP_ID").value == "909090"
        assert InstanceConfiguration.objects.get(key="GITHUB_APP_SLUG").value == "plane-rework-app"
        stored_pem = InstanceConfiguration.objects.get(key="GITHUB_APP_PRIVATE_KEY")
        assert stored_pem.is_encrypted is True
        assert decrypt_data(stored_pem.value) == conversion["pem"]
        stored_webhook_secret = InstanceConfiguration.objects.get(key="GITHUB_APP_WEBHOOK_SECRET")
        assert decrypt_data(stored_webhook_secret.value) == conversion["webhook_secret"]

    @pytest.mark.django_db
    def test_conversion_failure_redirects_with_error_and_persists_nothing(self, api_client, create_user):
        state = setup_state.issue("manifest", user_id=str(create_user.id))
        with patch(
            "plane.license.api.views.github_app.GitHubClient.convert_manifest",
            side_effect=requests.HTTPError("boom"),
        ):
            resp = api_client.get(MANIFEST_CALLBACK_URL, {"code": "bad-code", "state": state})
        assert resp.status_code == status.HTTP_302_FOUND
        assert "github_app=conversion_failed" in resp["Location"]
        assert not InstanceConfiguration.objects.filter(key="GITHUB_APP_ID").exists()


# ---------------------------------------------------------------------------
# Workspace one-click install: install-url + setup callback
# ---------------------------------------------------------------------------


@pytest.mark.contract
class TestWorkspaceGitHubInstallURLEndpoint:
    @pytest.mark.django_db
    def test_returns_422_when_app_not_configured(self, session_client, workspace):
        resp = session_client.post(_install_url(workspace.slug), {}, format="json")
        assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    @pytest.mark.django_db
    def test_returns_install_url_with_state_and_expiry(self, session_client, workspace):
        _configure_app()
        resp = session_client.post(_install_url(workspace.slug), {}, format="json")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["install_url"].startswith("https://github.com/apps/plane-app/installations/new?state=")
        assert resp.data["expires_at"]

    @pytest.mark.django_db
    def test_non_member_gets_403(self, api_client, workspace):
        outsider = User.objects.create(email="outsider-install@plane.so", username="outsider-install")
        outsider.set_password("test")
        outsider.save()
        api_client.force_authenticate(user=outsider)
        resp = api_client.post(_install_url(workspace.slug), {}, format="json")
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.django_db
    def test_first_connect_issues_no_github_delete(self, session_client, workspace):
        # No soft-deleted row for this workspace yet -- a first-time Connect
        # must not touch GitHub's uninstall endpoint at all.
        _configure_app()
        with patch("plane.app.views.github_sync.GitHubClient.delete_installation") as mock_delete:
            resp = session_client.post(_install_url(workspace.slug), {}, format="json")
        assert resp.status_code == status.HTTP_200_OK
        mock_delete.assert_not_called()

    @pytest.mark.django_db
    def test_reconnect_uninstalls_stale_installation_before_redirect(self, session_client, workspace):
        # Re-connect (Coolify pattern): a prior Disconnect left a soft-deleted
        # row and the app still installed on GitHub. `installations/new` would
        # show the Configure page (no callback) unless the stale install is
        # uninstalled first -- so the install-url endpoint must fire the
        # DELETE before it ever returns the install URL.
        _configure_app()
        stale = GithubAppInstallation.objects.create(
            workspace=workspace, installation_id=9001, account_login="acme"
        )
        with patch("plane.db.mixins.soft_delete_related_objects.delay"):
            stale.delete()

        with patch("plane.app.views.github_sync.GitHubClient.delete_installation") as mock_delete:
            resp = session_client.post(_install_url(workspace.slug), {}, format="json")

        assert resp.status_code == status.HTTP_200_OK
        mock_delete.assert_called_once_with(9001)
        assert "install_url" in resp.data

    @pytest.mark.django_db
    def test_reconnect_proceeds_when_github_uninstall_fails(self, session_client, workspace):
        # The uninstall is best-effort -- the install may already be gone on
        # GitHub's side (404) or the call may fail outright. Either way the
        # endpoint must still return a fresh install URL.
        _configure_app()
        stale = GithubAppInstallation.objects.create(
            workspace=workspace, installation_id=9002, account_login="acme"
        )
        with patch("plane.db.mixins.soft_delete_related_objects.delay"):
            stale.delete()

        with patch(
            "plane.app.views.github_sync.GitHubClient.delete_installation",
            side_effect=requests.HTTPError("404 Client Error"),
        ):
            resp = session_client.post(_install_url(workspace.slug), {}, format="json")

        assert resp.status_code == status.HTTP_200_OK
        assert "install_url" in resp.data


def _fake_installation_payload(
    app_id, login="acme", account_type="Organization", repository_selection="all", created_at=None
):
    # Default: a "fresh" installation (created after any state token was
    # issued) so unrelated tests pass through the freshness window. Tests
    # exercising the window pass an explicit old timestamp.
    created_at = created_at or (timezone.now() + timedelta(hours=1)).isoformat()
    return {
        "app_id": int(app_id),
        "account": {"login": login, "type": account_type, "avatar_url": f"https://avatars.example/{login}.png"},
        "repository_selection": repository_selection,
        "created_at": created_at,
    }


@pytest.mark.contract
class TestGitHubSetupCallbackEndpoint:
    @pytest.mark.django_db
    def test_missing_state_returns_expired_page_before_any_github_call(self, api_client):
        # I2/D7: `setup_on_update` sends GitHub's browser here with no `state`
        # at all -- no workspace to redirect back to, so a self-contained
        # "link expired" page (not raw JSON, not an unread query param).
        with patch("plane.app.views.github_sync.GitHubClient.get_installation") as mock_get:
            resp = api_client.get(SETUP_CALLBACK_URL, {"installation_id": "123"})
        assert resp.status_code == status.HTTP_200_OK
        assert b"invalid or expired" in resp.content
        mock_get.assert_not_called()

    @pytest.mark.django_db
    def test_forged_state_returns_expired_page_before_any_github_call(self, api_client):
        with patch("plane.app.views.github_sync.GitHubClient.get_installation") as mock_get:
            resp = api_client.get(SETUP_CALLBACK_URL, {"installation_id": "123", "state": "forged"})
        assert resp.status_code == status.HTTP_200_OK
        assert b"invalid or expired" in resp.content
        mock_get.assert_not_called()

    @pytest.mark.django_db
    def test_replayed_state_redirects_to_the_app(self, api_client, workspace, create_user):
        _configure_app()
        state = setup_state.issue("install", workspace_id=str(workspace.id), user_id=str(create_user.id))
        with patch(
            "plane.app.views.github_sync.GitHubClient.get_installation",
            return_value=_fake_installation_payload("555111"),
        ):
            first = api_client.get(SETUP_CALLBACK_URL, {"installation_id": "1", "state": state})
        assert first.status_code == status.HTTP_302_FOUND
        assert "github=connected" in first["Location"]

        second = api_client.get(SETUP_CALLBACK_URL, {"installation_id": "1", "state": state})
        # D7: a burned/replayed state takes the same "link expired" path as a
        # missing one -- an HTML page, never a redirect the UI can't read.
        assert second.status_code == status.HTTP_200_OK
        assert b"invalid or expired" in second.content

    @pytest.mark.django_db
    def test_installation_app_id_mismatch_returns_400(self, api_client, workspace, create_user):
        _configure_app()
        state = setup_state.issue("install", workspace_id=str(workspace.id), user_id=str(create_user.id))
        with patch(
            "plane.app.views.github_sync.GitHubClient.get_installation",
            return_value=_fake_installation_payload("999999999"),
        ):
            resp = api_client.get(SETUP_CALLBACK_URL, {"installation_id": "1", "state": state})
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert not GithubAppInstallation.objects.filter(workspace=workspace).exists()

    @pytest.mark.django_db
    def test_github_verification_failure_returns_502(self, api_client, workspace, create_user):
        _configure_app()
        state = setup_state.issue("install", workspace_id=str(workspace.id), user_id=str(create_user.id))
        with patch(
            "plane.app.views.github_sync.GitHubClient.get_installation",
            side_effect=requests.ConnectionError("boom"),
        ):
            resp = api_client.get(SETUP_CALLBACK_URL, {"installation_id": "1", "state": state})
        assert resp.status_code == status.HTTP_502_BAD_GATEWAY

    @pytest.mark.django_db
    def test_state_can_only_attach_to_the_workspace_it_was_issued_for(
        self, api_client, workspace, second_workspace, create_user
    ):
        _configure_app()
        state = setup_state.issue("install", workspace_id=str(workspace.id), user_id=str(create_user.id))
        with patch(
            "plane.app.views.github_sync.GitHubClient.get_installation",
            return_value=_fake_installation_payload("555111"),
        ):
            resp = api_client.get(SETUP_CALLBACK_URL, {"installation_id": "42", "state": state})

        assert resp.status_code == status.HTTP_302_FOUND
        installation = GithubAppInstallation.objects.get(installation_id=42)
        assert installation.workspace_id == workspace.id
        assert installation.workspace_id != second_workspace.id
        assert f"/{workspace.slug}/settings/github/" in resp["Location"]
        assert "github=connected" in resp["Location"]

    @pytest.mark.django_db
    def test_soft_deleted_installation_is_revived_not_duplicated(
        self, api_client, workspace, second_workspace, create_user
    ):
        # This is the legitimate counterpart to the B1 regression below: the
        # model's own contract (see GithubAppInstallation's docstring) is that
        # a *soft-deleted* installation -- deleted_at is set, so it is no
        # longer "live" -- may be revived under a different workspace. Only a
        # still-live row is protected from being re-pointed (B1).
        _configure_app()
        existing = GithubAppInstallation.objects.create(
            workspace=second_workspace, installation_id=77, account_login="old-org"
        )
        with patch("plane.db.mixins.soft_delete_related_objects.delay"):
            existing.delete()

        state = setup_state.issue("install", workspace_id=str(workspace.id), user_id=str(create_user.id))
        with patch(
            "plane.app.views.github_sync.GitHubClient.get_installation",
            return_value=_fake_installation_payload("555111", login="new-org", repository_selection="selected"),
        ):
            resp = api_client.get(SETUP_CALLBACK_URL, {"installation_id": "77", "state": state})

        assert resp.status_code == status.HTTP_302_FOUND
        assert GithubAppInstallation.all_objects.filter(installation_id=77).count() == 1
        revived = GithubAppInstallation.all_objects.get(installation_id=77)
        assert revived.pk == existing.pk
        assert revived.deleted_at is None
        assert revived.workspace_id == workspace.id
        assert revived.account_login == "new-org"
        assert revived.repository_selection == "selected"

    @pytest.mark.django_db
    def test_active_installation_owned_by_another_workspace_cannot_be_rebound(
        self, api_client, workspace, second_workspace, create_user
    ):
        # B1 regression: the callback only verifies the installation's app_id
        # via GitHub -- it never proves the caller actually administers the
        # installation's account. Without this check, an attacker who is
        # admin of `workspace` could enumerate installation ids and steal a
        # live installation that already belongs to `second_workspace`.
        _configure_app()
        victim = GithubAppInstallation.objects.create(
            workspace=second_workspace, installation_id=88, account_login="victim-org"
        )
        state = setup_state.issue("install", workspace_id=str(workspace.id), user_id=str(create_user.id))
        with patch(
            "plane.app.views.github_sync.GitHubClient.get_installation",
            return_value=_fake_installation_payload("555111", login="attacker-org"),
        ):
            resp = api_client.get(SETUP_CALLBACK_URL, {"installation_id": "88", "state": state})

        # D4: the conflict must land on the settings page (which toasts
        # ?github=failed), never a raw JSON 409.
        assert resp.status_code == status.HTTP_302_FOUND
        assert "github=failed" in resp["Location"]
        victim.refresh_from_db()
        assert victim.workspace_id == second_workspace.id
        assert victim.account_login == "victim-org"
        assert victim.deleted_at is None

    @pytest.mark.django_db
    def test_pre_existing_unclaimed_installation_cannot_be_attached(
        self, api_client, workspace, create_user
    ):
        # B1 hardening (fresh-install window): with no row at all, only a
        # JUST-created installation may be attached. An installation that
        # predates the state token belongs to a different GitHub account that
        # never completed setup here -- attaching it would hand that account's
        # repos to this workspace.
        _configure_app()
        state = setup_state.issue("install", workspace_id=str(workspace.id), user_id=str(create_user.id))
        old_payload = _fake_installation_payload("555111")
        old_payload["created_at"] = (timezone.now() - timedelta(hours=1)).isoformat()
        with patch(
            "plane.app.views.github_sync.GitHubClient.get_installation",
            return_value=old_payload,
        ):
            resp = api_client.get(SETUP_CALLBACK_URL, {"installation_id": "909", "state": state})

        # D5: the stale case redirects to the settings page with a distinct
        # marker so the user gets the "uninstall and reconnect" recovery path.
        assert resp.status_code == status.HTTP_302_FOUND
        assert "github=stale" in resp["Location"]
        assert not GithubAppInstallation.all_objects.filter(installation_id=909).exists()

    @pytest.mark.django_db
    def test_freshly_created_installation_attaches_normally(
        self, api_client, workspace, create_user
    ):
        # Fresh-install window, happy path: an installation created after the
        # state token was issued attaches normally.
        _configure_app()
        state = setup_state.issue("install", workspace_id=str(workspace.id), user_id=str(create_user.id))
        fresh_payload = _fake_installation_payload("555111")
        fresh_payload["created_at"] = (timezone.now() + timedelta(minutes=5)).isoformat()
        with patch(
            "plane.app.views.github_sync.GitHubClient.get_installation",
            return_value=fresh_payload,
        ):
            resp = api_client.get(SETUP_CALLBACK_URL, {"installation_id": "910", "state": state})

        assert resp.status_code == status.HTTP_302_FOUND
        installation = GithubAppInstallation.objects.get(installation_id=910)
        assert installation.workspace_id == workspace.id

    @pytest.mark.django_db
    def test_new_installation_frees_the_workspaces_prior_live_installation(
        self, api_client, workspace, create_user
    ):
        # I3: a workspace must hold at most one live installation. A second,
        # different installation attached through the callback frees (soft
        # deletes) the workspace's prior live row rather than stacking rows.
        _configure_app()
        first_installation = GithubAppInstallation.objects.create(
            workspace=workspace, installation_id=101, account_login="first-org"
        )
        state = setup_state.issue("install", workspace_id=str(workspace.id), user_id=str(create_user.id))
        with patch(
            "plane.app.views.github_sync.GitHubClient.get_installation",
            return_value=_fake_installation_payload("555111", login="second-org"),
        ):
            resp = api_client.get(SETUP_CALLBACK_URL, {"installation_id": "202", "state": state})

        assert resp.status_code == status.HTTP_302_FOUND
        # `objects` filters out soft-deleted rows, so refresh_from_db() would
        # raise DoesNotExist here -- go through all_objects instead.
        first_installation = GithubAppInstallation.all_objects.get(pk=first_installation.pk)
        assert first_installation.deleted_at is not None
        new_installation = GithubAppInstallation.objects.get(installation_id=202)
        assert new_installation.workspace_id == workspace.id
        assert new_installation.account_login == "second-org"

    @pytest.mark.django_db
    def test_soft_deleted_own_row_revives_despite_old_created_at(
        self, api_client, workspace, create_user
    ):
        # D1 guard: reviving your OWN disconnected installation stays free
        # even though its GitHub created_at predates the state token (GitHub
        # reuses the installation id after an uninstall/reinstall).
        _configure_app()
        prior = GithubAppInstallation.objects.create(
            workspace=workspace, installation_id=303, account_login="acme"
        )
        GithubAppInstallation.all_objects.filter(pk=prior.pk).update(
            is_active=False, deleted_at=timezone.now()
        )
        state = setup_state.issue("install", workspace_id=str(workspace.id), user_id=str(create_user.id))
        old_payload = _fake_installation_payload("555111", login="acme")
        old_payload["created_at"] = (timezone.now() - timedelta(days=30)).isoformat()
        with patch(
            "plane.app.views.github_sync.GitHubClient.get_installation",
            return_value=old_payload,
        ):
            resp = api_client.get(SETUP_CALLBACK_URL, {"installation_id": "303", "state": state})

        assert resp.status_code == status.HTTP_302_FOUND
        revived = GithubAppInstallation.all_objects.get(pk=prior.pk)
        assert revived.workspace_id == workspace.id
        assert revived.deleted_at is None

    @pytest.mark.django_db
    def test_soft_deleted_foreign_row_still_requires_fresh_installation(
        self, api_client, workspace, second_workspace, create_user
    ):
        # D1: a soft-deleted row owned by ANOTHER workspace is still the B1
        # takeover state (Disconnect leaves the App installed on GitHub), so
        # the freshness window must apply -- old created_at => stale.
        _configure_app()
        victim = GithubAppInstallation.objects.create(
            workspace=second_workspace, installation_id=404, account_login="victim-org"
        )
        GithubAppInstallation.all_objects.filter(pk=victim.pk).update(
            is_active=False, deleted_at=timezone.now()
        )
        state = setup_state.issue("install", workspace_id=str(workspace.id), user_id=str(create_user.id))
        old_payload = _fake_installation_payload("555111", login="attacker-org")
        old_payload["created_at"] = (timezone.now() - timedelta(hours=1)).isoformat()
        with patch(
            "plane.app.views.github_sync.GitHubClient.get_installation",
            return_value=old_payload,
        ):
            resp = api_client.get(SETUP_CALLBACK_URL, {"installation_id": "404", "state": state})

        assert resp.status_code == status.HTTP_302_FOUND
        assert "github=stale" in resp["Location"]
        victim.refresh_from_db()
        assert victim.workspace_id == second_workspace.id

    @pytest.mark.django_db
    def test_integrity_error_race_redirects_claimed_not_overwrites(
        self, api_client, workspace, second_workspace, create_user
    ):
        # D2: if a live row appears between our select and create (concurrent
        # attach), the create fails with IntegrityError -- the loser must be
        # rejected, never fall through to the unconditional overwrite.
        # Start from NO row so the flow reaches create() (a pre-existing live
        # row would trip already_claimed first and never exercise the race).
        _configure_app()
        state = setup_state.issue("install", workspace_id=str(workspace.id), user_id=str(create_user.id))
        with (
            patch(
                "plane.app.views.github_sync.GitHubClient.get_installation",
                return_value=_fake_installation_payload("555111", login="attacker-org"),
            ),
            patch(
                "plane.app.views.github_sync.GithubAppInstallation.objects.create",
                side_effect=IntegrityError("duplicate key value violates unique constraint"),
            ),
        ):
            resp = api_client.get(SETUP_CALLBACK_URL, {"installation_id": "505", "state": state})

        assert resp.status_code == status.HTTP_302_FOUND
        assert "github=failed" in resp["Location"]
        # The race loser must not own the installation.
        assert not GithubAppInstallation.all_objects.filter(
            installation_id=505, workspace=workspace
        ).exists()

    @pytest.mark.django_db
    def test_disconnect_preserves_enabled_repos_and_mappings(
        self, session_client, workspace, create_user
    ):
        # D3: Disconnect soft-deletes the installation row WITHOUT the
        # SoftDeleteModel Celery cascade -- enabled repos must survive so the
        # workspace can reconnect. (Mapped repos can't be disconnected at all
        # -- the endpoint guards with a 409 -- so the survival proof is on
        # the enabled-repo layer.)
        _configure_app()
        installation = GithubAppInstallation.objects.create(
            workspace=workspace, installation_id=606, account_login="acme"
        )
        repo = GithubEnabledRepository.objects.create(
            installation=installation, github_repository_id=7001, full_name="acme/widgets"
        )

        resp = session_client.delete(f"/api/workspaces/{workspace.slug}/github/installation/")

        assert resp.status_code == status.HTTP_204_NO_CONTENT
        installation.refresh_from_db()
        assert installation.deleted_at is not None
        assert GithubEnabledRepository.objects.filter(pk=repo.pk).exists()


# ---------------------------------------------------------------------------
# Live repository discovery
# ---------------------------------------------------------------------------


@pytest.mark.contract
class TestWorkspaceAvailableRepositoriesEndpoint:
    @pytest.mark.django_db
    def test_no_active_installation_returns_422(self, session_client, workspace):
        resp = session_client.get(_available_repos_url(workspace.slug))
        assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    @pytest.mark.django_db
    def test_no_app_configuration_returns_422_not_500(self, session_client, workspace):
        # I1: an installation row can outlive its instance GitHub App
        # configuration (e.g. the app was removed). GitHubClient.for_installation
        # then builds a client with no app id/private key -- discovery must
        # 422, not 500 when that client tries to mint a JWT.
        GithubAppInstallation.objects.create(workspace=workspace, installation_id=606059, account_login="acme")
        resp = session_client.get(_available_repos_url(workspace.slug))
        assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    @pytest.mark.django_db
    def test_lists_live_repositories_merged_with_enabled_state(self, session_client, workspace):
        _configure_app()
        installation = GithubAppInstallation.objects.create(
            workspace=workspace, installation_id=606060, account_login="acme"
        )
        GithubEnabledRepository.objects.create(
            installation=installation, github_repository_id=1, full_name="acme/widgets", is_enabled=True
        )
        remote_repos = [
            {
                "id": 1,
                "full_name": "acme/widgets",
                "private": False,
                "default_branch": "main",
                "html_url": "https://github.com/acme/widgets",
            },
            {
                "id": 2,
                "full_name": "acme/gadgets",
                "private": True,
                "default_branch": "dev",
                "html_url": "https://github.com/acme/gadgets",
            },
        ]
        with patch(
            "plane.app.views.github_sync.GitHubClient.list_installation_repositories",
            return_value=remote_repos,
        ):
            resp = session_client.get(_available_repos_url(workspace.slug))

        assert resp.status_code == status.HTTP_200_OK
        by_id = {row["github_repository_id"]: row for row in resp.data}
        assert by_id[1]["is_enabled"] is True
        assert by_id[2]["is_enabled"] is False
        assert by_id[2]["default_branch"] == "dev"
        assert by_id[2]["private"] is True

    @pytest.mark.django_db
    def test_github_failure_returns_502_with_retry_hint(self, session_client, workspace):
        _configure_app()
        GithubAppInstallation.objects.create(workspace=workspace, installation_id=606061, account_login="acme")
        with patch(
            "plane.app.views.github_sync.GitHubClient.list_installation_repositories",
            side_effect=requests.HTTPError("boom"),
        ):
            resp = session_client.get(_available_repos_url(workspace.slug))
        assert resp.status_code == status.HTTP_502_BAD_GATEWAY
        assert "detail" in resp.data

    @pytest.mark.django_db
    def test_non_member_gets_403_on_other_workspace(self, session_client, workspace, second_workspace):
        GithubAppInstallation.objects.create(
            workspace=second_workspace, installation_id=606062, account_login="other"
        )
        resp = session_client.get(_available_repos_url(second_workspace.slug))
        assert resp.status_code == status.HTTP_403_FORBIDDEN


# ---------------------------------------------------------------------------
# Bulk repository save (I6/I7)
# ---------------------------------------------------------------------------


@pytest.mark.contract
class TestWorkspaceRepositoriesBulkUpsert:
    @pytest.fixture
    def installation(self, db, workspace):
        _configure_app()
        return GithubAppInstallation.objects.create(
            workspace=workspace, installation_id=707070, account_login="acme"
        )

    @pytest.fixture
    def project(self, db, workspace, create_user):
        return Project.objects.create(
            name="Bulk Save Project", identifier="BSP", workspace=workspace, created_by=create_user
        )

    def _live_repos(self):
        return [
            {"id": 1, "full_name": "acme/widgets", "private": False, "default_branch": "main", "html_url": "u1"},
            {"id": 2, "full_name": "acme/gadgets", "private": True, "default_branch": "dev", "html_url": "u2"},
        ]

    @pytest.mark.django_db
    def test_bulk_upsert_creates_and_returns_the_full_list(self, session_client, workspace, installation):
        payload = [
            {"github_repository_id": 1, "full_name": "acme/widgets", "is_enabled": True},
            {"github_repository_id": 2, "full_name": "acme/gadgets", "is_enabled": False},
        ]
        with patch(
            "plane.app.views.github_sync.GitHubClient.list_installation_repositories",
            return_value=self._live_repos(),
        ):
            resp = session_client.post(_repositories_url(workspace.slug), payload, format="json")

        assert resp.status_code == status.HTTP_200_OK, resp.data
        assert len(resp.data) == 2
        assert GithubEnabledRepository.objects.filter(installation=installation, is_enabled=True).count() == 1

    @pytest.mark.django_db
    def test_bulk_upsert_rejects_a_repository_not_on_the_installation(self, session_client, workspace, installation):
        # I7: the client-supplied github_repository_id/full_name must be
        # cross-checked against what GitHub actually reports for this
        # installation before it is trusted and written.
        payload = [
            {"github_repository_id": 1, "full_name": "acme/widgets", "is_enabled": True},
            {"github_repository_id": 999, "full_name": "someone-else/private-repo", "is_enabled": True},
        ]
        with patch(
            "plane.app.views.github_sync.GitHubClient.list_installation_repositories",
            return_value=self._live_repos(),
        ):
            resp = session_client.post(_repositories_url(workspace.slug), payload, format="json")

        assert resp.status_code == status.HTTP_207_MULTI_STATUS, resp.data
        assert len(resp.data["results"]) == 1
        assert len(resp.data["errors"]) == 1
        assert resp.data["errors"][0]["index"] == 1
        assert not GithubEnabledRepository.objects.filter(
            installation=installation, github_repository_id=999
        ).exists()

    @pytest.mark.django_db
    def test_bulk_upsert_cannot_disable_a_mapped_repository(
        self, session_client, workspace, installation, project
    ):
        # I6: disabling a mapped repository through the bulk save must not
        # silently succeed -- the mapping would keep working (branch creation
        # doesn't check is_enabled) while the repo vanished from the picker.
        repo = GithubEnabledRepository.objects.create(
            installation=installation, github_repository_id=1, full_name="acme/widgets", is_enabled=True
        )
        RepoProjectMapping.objects.create(
            workspace=workspace,
            project=project,
            repository=repo,
            github_installation_id=installation.installation_id,
            github_repo=repo.full_name,
        )
        payload = [{"github_repository_id": 1, "full_name": "acme/widgets", "is_enabled": False}]
        with patch(
            "plane.app.views.github_sync.GitHubClient.list_installation_repositories",
            return_value=self._live_repos(),
        ):
            resp = session_client.post(_repositories_url(workspace.slug), payload, format="json")

        assert resp.status_code == status.HTTP_400_BAD_REQUEST, resp.data
        assert resp.data["errors"][0]["index"] == 0
        repo.refresh_from_db()
        assert repo.is_enabled is True

    @pytest.mark.django_db
    def test_bulk_upsert_rejects_batches_over_the_cap(self, session_client, workspace, installation):
        payload = [
            {"github_repository_id": i, "full_name": f"acme/repo-{i}", "is_enabled": True} for i in range(1, 202)
        ]
        resp = session_client.post(_repositories_url(workspace.slug), payload, format="json")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert GithubEnabledRepository.objects.filter(installation=installation).count() == 0


# ---------------------------------------------------------------------------
# GitHubClient: token caching, 401 retry, pagination cap
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self._json_data = json_data or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"status {self.status_code}")

    def json(self):
        return self._json_data


@pytest.mark.contract
class TestGitHubClientCaching:
    @pytest.fixture(autouse=True)
    def _clear_cache(self):
        cache.clear()
        yield
        cache.clear()

    def _client(self, installation_id=555):
        return GitHubClient("app-id", "fake-private-key", installation_id, "https://api.github.example")

    @pytest.mark.django_db
    def test_installation_token_is_cached_across_calls(self):
        client = self._client()
        with (
            patch.object(GitHubClient, "_app_jwt", return_value="fake-jwt"),
            patch(
                "plane.services.github.client.requests.post",
                return_value=_FakeResponse(200, {"token": "installation-token-abc"}),
            ) as mock_post,
        ):
            for _ in range(3):
                assert client.get_installation_token() == "installation-token-abc"

        assert mock_post.call_count == 1

    @pytest.mark.django_db
    def test_401_invalidates_cached_token_and_retries_exactly_once(self):
        client = self._client()
        cache.set("github:installation_token:555", "stale-token", 3000)

        responses = [_FakeResponse(401), _FakeResponse(200, {"object": {"sha": "abc123"}})]
        with (
            patch.object(GitHubClient, "_app_jwt", return_value="fake-jwt"),
            patch("plane.services.github.client.requests.request", side_effect=responses) as mock_request,
            patch(
                "plane.services.github.client.requests.post",
                return_value=_FakeResponse(200, {"token": "fresh-token"}),
            ) as mock_post,
        ):
            sha = client.get_branch_sha("acme", "widgets", "main")

        assert sha == "abc123"
        assert mock_request.call_count == 2
        mock_post.assert_called_once()
        # The 401 invalidated the STALE token; the retry re-minted and cached
        # the fresh one (get_installation_token always caches).
        assert cache.get("github:installation_token:555") == "fresh-token"

    @pytest.mark.django_db
    def test_list_installation_repositories_pagination_cap_is_honoured(self):
        client = self._client()
        cache.set("github:installation_token:555", "cached-token", 3000)

        full_page = [{"id": i, "full_name": f"acme/repo-{i}"} for i in range(100)]
        with patch(
            "plane.services.github.client.requests.request",
            return_value=_FakeResponse(200, {"repositories": full_page}),
        ) as mock_request:
            repositories = client.list_installation_repositories()

        # Every page comes back full (100/100), so pagination must stop at the
        # hard cap rather than looping forever.
        assert mock_request.call_count == 100
        assert len(repositories) == 100 * 100
