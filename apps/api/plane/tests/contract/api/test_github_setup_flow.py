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
from unittest.mock import patch

import pytest
import requests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.core.cache import cache
from django.utils import timezone
from rest_framework import status

from plane.db.models import User, Workspace, WorkspaceMember
from plane.db.models.integration.github_app import GithubAppInstallation, GithubEnabledRepository
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
        assert set(manifest["default_events"]) == {
            "pull_request",
            "push",
            "installation",
            "installation_repositories",
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
    @pytest.mark.django_db
    def test_missing_state_returns_400(self, api_client):
        resp = api_client.get(MANIFEST_CALLBACK_URL, {"code": "abc"})
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert resp.data["error"] == "invalid_state"

    @pytest.mark.django_db
    def test_forged_state_returns_400(self, api_client):
        resp = api_client.get(MANIFEST_CALLBACK_URL, {"code": "abc", "state": "not-a-real-state"})
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.django_db
    def test_wrong_action_state_returns_400(self, api_client, workspace, create_user):
        # A state minted for the *install* flow must not be redeemable here.
        state = setup_state.issue(
            "install", workspace_id=str(workspace.id), user_id=str(create_user.id), redirect=""
        )
        resp = api_client.get(MANIFEST_CALLBACK_URL, {"code": "abc", "state": state})
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.django_db
    def test_replayed_state_returns_400(self, api_client, create_user):
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

        second = api_client.get(MANIFEST_CALLBACK_URL, {"code": "abc", "state": state})
        assert second.status_code == status.HTTP_400_BAD_REQUEST
        assert second.data["error"] == "invalid_state"

    @pytest.mark.django_db
    def test_expired_state_returns_400(self, api_client, create_user, monkeypatch):
        monkeypatch.setattr(setup_state, "STATE_TTL_SECONDS", 0)
        state = setup_state.issue("manifest", user_id=str(create_user.id))
        resp = api_client.get(MANIFEST_CALLBACK_URL, {"code": "abc", "state": state})
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.django_db
    def test_already_configured_returns_403(self, api_client, create_user):
        _configure_app()
        state = setup_state.issue("manifest", user_id=str(create_user.id))
        resp = api_client.get(MANIFEST_CALLBACK_URL, {"code": "abc", "state": state})
        assert resp.status_code == status.HTTP_403_FORBIDDEN
        assert resp.data["error"] == "already_configured"

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


def _fake_installation_payload(app_id, login="acme", account_type="Organization", repository_selection="all"):
    return {
        "app_id": int(app_id),
        "account": {"login": login, "type": account_type, "avatar_url": f"https://avatars.example/{login}.png"},
        "repository_selection": repository_selection,
    }


@pytest.mark.contract
class TestGitHubSetupCallbackEndpoint:
    @pytest.mark.django_db
    def test_missing_state_returns_400_before_any_github_call(self, api_client):
        with patch("plane.app.views.github_sync.GitHubClient.get_installation") as mock_get:
            resp = api_client.get(SETUP_CALLBACK_URL, {"installation_id": "123"})
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        mock_get.assert_not_called()

    @pytest.mark.django_db
    def test_forged_state_returns_400_before_any_github_call(self, api_client):
        with patch("plane.app.views.github_sync.GitHubClient.get_installation") as mock_get:
            resp = api_client.get(SETUP_CALLBACK_URL, {"installation_id": "123", "state": "forged"})
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        mock_get.assert_not_called()

    @pytest.mark.django_db
    def test_replayed_state_returns_400(self, api_client, workspace, create_user):
        _configure_app()
        state = setup_state.issue(
            "install", workspace_id=str(workspace.id), user_id=str(create_user.id), redirect=""
        )
        with patch(
            "plane.app.views.github_sync.GitHubClient.get_installation",
            return_value=_fake_installation_payload("555111"),
        ):
            first = api_client.get(SETUP_CALLBACK_URL, {"installation_id": "1", "state": state})
        assert first.status_code == status.HTTP_302_FOUND

        second = api_client.get(SETUP_CALLBACK_URL, {"installation_id": "1", "state": state})
        assert second.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.django_db
    def test_installation_app_id_mismatch_returns_400(self, api_client, workspace, create_user):
        _configure_app()
        state = setup_state.issue(
            "install", workspace_id=str(workspace.id), user_id=str(create_user.id), redirect=""
        )
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
        state = setup_state.issue(
            "install", workspace_id=str(workspace.id), user_id=str(create_user.id), redirect=""
        )
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
        state = setup_state.issue(
            "install", workspace_id=str(workspace.id), user_id=str(create_user.id), redirect=""
        )
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
        _configure_app()
        existing = GithubAppInstallation.objects.create(
            workspace=second_workspace, installation_id=77, account_login="old-org"
        )
        with patch("plane.db.mixins.soft_delete_related_objects.delay"):
            existing.delete()

        state = setup_state.issue(
            "install", workspace_id=str(workspace.id), user_id=str(create_user.id), redirect=""
        )
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
    def test_lists_live_repositories_merged_with_enabled_state(self, session_client, workspace):
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
        with patch("plane.services.github.client.requests.request", side_effect=responses) as mock_request:
            sha = client.get_branch_sha("acme", "widgets", "main")

        assert sha == "abc123"
        assert mock_request.call_count == 2
        assert cache.get("github:installation_token:555") is None

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
