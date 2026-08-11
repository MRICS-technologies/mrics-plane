# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Contract tests for the native GitHub sync endpoints (Phase 3 MVP).

GET/POST   /api/workspaces/<slug>/projects/<project_id>/github/mappings/
DELETE     /api/workspaces/<slug>/projects/<project_id>/github/mappings/<pk>/
GET        /api/workspaces/<slug>/projects/<project_id>/issues/<issue_id>/git-links/
POST       /api/workspaces/<slug>/projects/<project_id>/issues/<issue_id>/github/create-branch/
POST       /api/github/webhook/

The webhook secret and app credentials used below are sourced from the P1
instance `InstanceConfiguration` (`GITHUB_APP_*` keys), not environment
variables -- see `plane.services.github.credentials`.
"""

import hashlib
import hmac
import json
from unittest.mock import patch

import pytest
from rest_framework import status

from plane.db.models import Issue, Project, ProjectMember, Workspace, WorkspaceMember
from plane.db.models.integration.github_sync import GithubWebhookDelivery, IssueGitLink, RepoProjectMapping
from plane.db.models.integration.github_app import GithubAppInstallation, GithubEnabledRepository
from plane.license.models import InstanceConfiguration
from plane.license.utils.encryption import encrypt_data


@pytest.fixture
def project(db, workspace, create_user):
    project = Project.objects.create(
        name="Test Project",
        identifier="TP",
        workspace=workspace,
        created_by=create_user,
    )
    ProjectMember.objects.create(
        workspace=workspace,
        project=project,
        member=create_user,
        role=20,
        is_active=True,
    )
    return project


@pytest.fixture
def issue(db, project, create_user):
    return Issue.objects.create(
        name="Test Issue",
        project=project,
        workspace=project.workspace,
        created_by=create_user,
    )


@pytest.fixture
def mapping(db, project):
    return RepoProjectMapping.objects.create(
        project=project,
        github_installation_id=123,
        github_repo="acme/widgets",
    )


def _mappings_url(slug, project_id):
    return f"/api/workspaces/{slug}/projects/{project_id}/github/mappings/"


def _create_branch_url(slug, project_id, issue_id):
    return f"/api/workspaces/{slug}/projects/{project_id}/issues/{issue_id}/github/create-branch/"


@pytest.mark.contract
class TestRepoProjectMappingAPI:
    @pytest.mark.django_db
    def test_list_and_create_mapping(self, session_client, workspace, project):
        # S2: must create native installation + enabled repository first.
        installation = GithubAppInstallation.objects.create(
            workspace=workspace,
            installation_id=42,
            account_login="acme",
        )
        enabled_repo = GithubEnabledRepository.objects.create(
            installation=installation,
            github_repository_id=1001,
            full_name="acme/widgets",
            is_enabled=True,
        )

        url = _mappings_url(workspace.slug, project.id)

        response = session_client.post(
            url,
            {"repository_id": str(enabled_repo.pk)},
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED, response.data

        response = session_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1


@pytest.mark.contract
class TestIssueCreateBranchAPI:
    @pytest.mark.django_db
    def test_create_branch_without_mapping_returns_422(self, session_client, workspace, project, issue):
        url = _create_branch_url(workspace.slug, project.id, issue.id)

        response = session_client.post(url, {"branch_name": "feature/TP-1-add-login"}, format="json")

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    @pytest.mark.django_db
    def test_create_branch_without_github_app_configured_returns_422(
        self, session_client, workspace, project, issue, mapping
    ):
        # Mapping exists, but no GITHUB_APP_* InstanceConfiguration has been
        # written -- the credentials bridge must report unconfigured rather
        # than falling back to any environment variable.
        url = _create_branch_url(workspace.slug, project.id, issue.id)

        response = session_client.post(url, {"branch_name": "feature/TP-1-add-login"}, format="json")

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert response.data["error"] == "GitHub App is not configured"

    @pytest.mark.django_db
    def test_create_branch_links_existing_github_branch_instead_of_409(
        self, session_client, workspace, project, issue, mapping
    ):
        # Phase16 gap: GitHub already has this branch (eg. created manually)
        # and Plane has no link for it yet -- the endpoint must link it to
        # the issue and succeed instead of dead-ending on a conflict.
        _configure_webhook_app()
        url = _create_branch_url(workspace.slug, project.id, issue.id)

        with (
            patch("plane.app.views.github_sync.GitHubClient.get_branch_sha", return_value="deadbeef"),
            patch("plane.app.views.github_sync.GitHubClient.create_branch") as mock_create,
        ):
            response = session_client.post(url, {"branch_name": "feature/TP-1-add-login"}, format="json")

        assert response.status_code == status.HTTP_200_OK, response.data
        assert response.data["linked_existing"] is True
        assert response.data["branch_name"] == "feature/TP-1-add-login"
        mock_create.assert_not_called()

        links = IssueGitLink.objects.filter(
            issue_id=issue.id, github_repo=mapping.github_repo, kind="branch", ref="feature/TP-1-add-login"
        )
        assert links.count() == 1
        assert links.first().state == "open"

    @pytest.mark.django_db
    def test_create_branch_request_is_idempotent(self, session_client, workspace, project, issue, mapping):
        # A repeated request for a branch this issue is already linked to
        # must succeed without creating a duplicate IssueGitLink or 409ing.
        _configure_webhook_app()
        url = _create_branch_url(workspace.slug, project.id, issue.id)
        create_result = {
            "branch_name": "feature/TP-1-add-login",
            "url": "https://github.example/acme/widgets/tree/feature/TP-1-add-login",
            "sha": "cafebabe",
        }

        with (
            patch("plane.app.views.github_sync.GitHubClient.get_branch_sha", return_value=None),
            patch("plane.app.views.github_sync.GitHubClient.create_branch", return_value=create_result),
        ):
            first = session_client.post(url, {"branch_name": "feature/TP-1-add-login"}, format="json")

        assert first.status_code == status.HTTP_201_CREATED, first.data
        assert first.data["linked_existing"] is False

        # The second call must not need to reach GitHub at all -- it is
        # answered purely from the already-live IssueGitLink.
        second = session_client.post(url, {"branch_name": "feature/TP-1-add-login"}, format="json")

        assert second.status_code == status.HTTP_200_OK, second.data
        assert second.data["linked_existing"] is True

        links = IssueGitLink.objects.filter(
            issue_id=issue.id, github_repo=mapping.github_repo, kind="branch", ref="feature/TP-1-add-login"
        )
        assert links.count() == 1

    @pytest.mark.django_db
    def test_create_branch_still_creates_a_new_branch_when_absent_on_github(
        self, session_client, workspace, project, issue, mapping
    ):
        # Regression: a genuinely new branch name must still be created via
        # the GitHub App exactly as before.
        _configure_webhook_app()
        url = _create_branch_url(workspace.slug, project.id, issue.id)
        create_result = {
            "branch_name": "feature/TP-2-new-thing",
            "url": "https://github.example/acme/widgets/tree/feature/TP-2-new-thing",
            "sha": "0123456789abcdef",
        }

        with (
            patch("plane.app.views.github_sync.GitHubClient.get_branch_sha", return_value=None),
            patch(
                "plane.app.views.github_sync.GitHubClient.create_branch", return_value=create_result
            ) as mock_create,
        ):
            response = session_client.post(url, {"branch_name": "feature/TP-2-new-thing"}, format="json")

        assert response.status_code == status.HTTP_201_CREATED, response.data
        assert response.data["linked_existing"] is False
        assert response.data["branch_name"] == "feature/TP-2-new-thing"
        assert response.data["sha"] == "0123456789abcdef"
        mock_create.assert_called_once_with("acme", "widgets", "feature/TP-2-new-thing", mapping.base_branch)

        links = IssueGitLink.objects.filter(
            issue_id=issue.id, github_repo=mapping.github_repo, kind="branch", ref="feature/TP-2-new-thing"
        )
        assert links.count() == 1

    @pytest.mark.django_db
    def test_create_branch_links_branch_already_linked_to_another_issue(
        self, session_client, workspace, project, issue, mapping, create_user
    ):
        # Option 3 (Phase 2): one GitHub branch may be intentionally linked to
        # several Plane issues -- linking a branch that another issue already
        # links must succeed (200, no GitHub create call), not 409, leaving
        # two independent live branch links behind.
        _configure_webhook_app()
        other_issue = Issue.objects.create(
            name="Other Issue", project=project, workspace=project.workspace, created_by=create_user
        )
        IssueGitLink.objects.create(
            workspace=project.workspace,
            project=project,
            issue=other_issue,
            github_repo=mapping.github_repo,
            kind="branch",
            ref="feature/shared-branch",
            url="https://github.example/acme/widgets/tree/feature/shared-branch",
            state="open",
            detected_via="manual",
        )

        url = _create_branch_url(workspace.slug, project.id, issue.id)
        with (
            patch("plane.app.views.github_sync.GitHubClient.get_branch_sha", return_value="deadbeef"),
            patch("plane.app.views.github_sync.GitHubClient.create_branch") as mock_create,
        ):
            response = session_client.post(url, {"branch_name": "feature/shared-branch"}, format="json")

        assert response.status_code == status.HTTP_200_OK, response.data
        assert response.data["linked_existing"] is True
        mock_create.assert_not_called()

        links = IssueGitLink.objects.filter(
            github_repo=mapping.github_repo, kind="branch", ref="feature/shared-branch"
        )
        assert links.count() == 2
        assert set(links.values_list("issue_id", flat=True)) == {issue.id, other_issue.id}


def _set_github_app_webhook_secret(secret):
    InstanceConfiguration.objects.update_or_create(
        key="GITHUB_APP_WEBHOOK_SECRET",
        defaults={"value": encrypt_data(secret), "category": "GITHUB_APP", "is_encrypted": True},
    )


@pytest.mark.contract
class TestGitHubWebhookAPI:
    WEBHOOK_URL = "/api/github/webhook/"

    @pytest.mark.django_db
    def test_webhook_invalid_signature_returns_401(self, api_client):
        _set_github_app_webhook_secret("test-webhook-secret")

        response = api_client.post(
            self.WEBHOOK_URL,
            data=json.dumps({"action": "opened"}),
            content_type="application/json",
            HTTP_X_HUB_SIGNATURE_256="sha256=bogus",
            HTTP_X_GITHUB_EVENT="pull_request",
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.django_db
    def test_webhook_valid_signature_returns_200(self, api_client):
        secret = "test-webhook-secret"
        _set_github_app_webhook_secret(secret)
        InstanceConfiguration.objects.update_or_create(
            key="GITHUB_APP_ID",
            defaults={"value": "123456", "category": "GITHUB_APP", "is_encrypted": False},
        )
        InstanceConfiguration.objects.update_or_create(
            key="GITHUB_APP_PRIVATE_KEY",
            defaults={
                "value": encrypt_data("fake-pem-private-key"),
                "category": "GITHUB_APP",
                "is_encrypted": True,
            },
        )

        body = json.dumps({"action": "opened"}).encode()
        signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

        response = api_client.post(
            self.WEBHOOK_URL,
            data=body,
            content_type="application/json",
            HTTP_X_HUB_SIGNATURE_256=signature,
            HTTP_X_GITHUB_EVENT="pull_request",
        )

        assert response.status_code == status.HTTP_200_OK

    @pytest.mark.django_db
    def test_webhook_without_github_app_configured_returns_401(self, api_client):
        # No GITHUB_APP_WEBHOOK_SECRET row at all -- must fail closed.
        body = json.dumps({"action": "opened"}).encode()
        signature = "sha256=" + hmac.new(b"any-secret", body, hashlib.sha256).hexdigest()

        response = api_client.post(
            self.WEBHOOK_URL,
            data=body,
            content_type="application/json",
            HTTP_X_HUB_SIGNATURE_256=signature,
            HTTP_X_GITHUB_EVENT="pull_request",
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.django_db
    def test_webhook_with_partial_app_configuration_returns_401(self, api_client):
        # A webhook secret with no app id/private key is not a usable GitHub
        # App -- must still fail closed rather than accept the signature.
        secret = "test-webhook-secret"
        _set_github_app_webhook_secret(secret)

        body = json.dumps({"action": "opened"}).encode()
        signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

        response = api_client.post(
            self.WEBHOOK_URL,
            data=body,
            content_type="application/json",
            HTTP_X_HUB_SIGNATURE_256=signature,
            HTTP_X_GITHUB_EVENT="pull_request",
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED



def _configure_webhook_app(secret="test-webhook-secret"):
    _set_github_app_webhook_secret(secret)
    InstanceConfiguration.objects.update_or_create(
        key="GITHUB_APP_ID",
        defaults={"value": "123456", "category": "GITHUB_APP", "is_encrypted": False},
    )
    InstanceConfiguration.objects.update_or_create(
        key="GITHUB_APP_PRIVATE_KEY",
        defaults={
            "value": encrypt_data("fake-pem-private-key"),
            "category": "GITHUB_APP",
            "is_encrypted": True,
        },
    )
    return secret


def _pull_request_payload(
    installation,
    repository,
    number=17,
    title="TP-1 implement webhook",
    head="feature/TP-1-webhook",
    action="opened",
    merged=False,
    updated_at="2026-07-31T00:00:00Z",
):
    return {
        "action": action,
        "installation": {"id": installation.installation_id},
        "repository": {"id": repository.github_repository_id, "full_name": repository.full_name},
        "pull_request": {
            "number": number,
            "title": title,
            "head": {"ref": head},
            "html_url": f"https://github.example/{repository.full_name}/pull/{number}",
            "merged": merged,
            "updated_at": updated_at,
        },
    }


def _post_signed_webhook(api_client, payload, secret, delivery_id):
    body = json.dumps(payload).encode()
    signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return api_client.post(
        TestGitHubWebhookAPI.WEBHOOK_URL,
        data=body,
        content_type="application/json",
        HTTP_X_HUB_SIGNATURE_256=signature,
        HTTP_X_GITHUB_EVENT="pull_request",
        HTTP_X_GITHUB_DELIVERY=delivery_id,
    )


@pytest.fixture
def webhook_context(db, workspace, project, issue):
    issue.sequence_id = 1
    issue.save(update_fields=["sequence_id"])
    installation = GithubAppInstallation.objects.create(
        workspace=workspace, installation_id=92001, account_login="acme"
    )
    repository = GithubEnabledRepository.objects.create(
        installation=installation,
        github_repository_id=93001,
        full_name="acme/widgets",
        is_enabled=True,
    )
    RepoProjectMapping.objects.create(
        workspace=workspace,
        project=project,
        repository=repository,
        github_installation_id=installation.installation_id,
        github_repo=repository.full_name,
    )
    return installation, repository


@pytest.mark.contract
class TestGitHubPullRequestWebhookContract:
    @pytest.mark.django_db
    def test_raw_signature_and_body_limit(self, api_client, webhook_context):
        installation, repository = webhook_context
        secret = _configure_webhook_app()
        response = _post_signed_webhook(
            api_client,
            _pull_request_payload(installation, repository, title="no issue key"),
            secret,
            "delivery-raw-signature",
        )
        assert response.status_code == status.HTTP_200_OK
        assert GithubWebhookDelivery.objects.filter(delivery_id="delivery-raw-signature").count() == 1

        # This must return before calling the HMAC/configuration path or JSON parser.
        response = api_client.post(
            TestGitHubWebhookAPI.WEBHOOK_URL,
            data=b"x" * (1024 * 1024 + 1),
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_413_REQUEST_ENTITY_TOO_LARGE

    @pytest.mark.django_db
    def test_duplicate_delivery_is_acknowledged_without_reprocessing(self, api_client, webhook_context):
        installation, repository = webhook_context
        secret = _configure_webhook_app()
        payload = _pull_request_payload(installation, repository)
        response = _post_signed_webhook(api_client, payload, secret, "delivery-duplicate")
        assert response.status_code == status.HTTP_200_OK
        link = IssueGitLink.objects.get(kind="pr", github_repo=repository.full_name, pr_number=17)
        assert link.state == "open"

        payload["action"] = "closed"
        payload["pull_request"]["merged"] = True
        response = _post_signed_webhook(api_client, payload, secret, "delivery-duplicate")
        assert response.status_code == status.HTTP_200_OK
        link.refresh_from_db()
        assert link.state == "open"
        assert GithubWebhookDelivery.objects.filter(delivery_id="delivery-duplicate").count() == 1

    @pytest.mark.django_db
    def test_inactive_or_wrong_repository_does_not_link(self, api_client, webhook_context):
        installation, repository = webhook_context
        secret = _configure_webhook_app()
        installation.is_active = False
        installation.save(update_fields=["is_active"])
        response = _post_signed_webhook(
            api_client, _pull_request_payload(installation, repository), secret, "delivery-inactive"
        )
        assert response.status_code == status.HTTP_200_OK
        assert not IssueGitLink.objects.filter(kind="pr").exists()

        installation.is_active = True
        installation.save(update_fields=["is_active"])
        payload = _pull_request_payload(installation, repository, number=18)
        payload["repository"]["id"] = repository.github_repository_id + 1
        response = _post_signed_webhook(api_client, payload, secret, "delivery-wrong-repo")
        assert response.status_code == status.HTTP_200_OK
        assert not IssueGitLink.objects.filter(kind="pr").exists()

    @pytest.mark.django_db
    def test_branch_match_wins_and_events_are_idempotent_and_ordered(self, api_client, webhook_context, project, issue):
        installation, repository = webhook_context
        secret = _configure_webhook_app()
        branch_issue = Issue.objects.create(
            name="Branch Issue",
            project=project,
            workspace=project.workspace,
            created_by=issue.created_by,
            sequence_id=2,
        )
        IssueGitLink.objects.create(
            workspace=project.workspace,
            project=project,
            issue=branch_issue,
            github_repo=repository.full_name,
            kind="branch",
            ref="feature/linked-branch",
            url="https://github.example/acme/widgets/tree/feature/linked-branch",
            state="open",
            detected_via="manual",
        )
        payload = _pull_request_payload(
            installation,
            repository,
            title="TP-1 title fallback must lose",
            head="feature/linked-branch",
            updated_at="2026-07-31T01:00:00Z",
        )
        assert _post_signed_webhook(api_client, payload, secret, "delivery-open").status_code == status.HTTP_200_OK
        link = IssueGitLink.objects.get(kind="pr", github_repo=repository.full_name, pr_number=17)
        assert link.issue_id == branch_issue.id
        assert link.detected_via == "branch"
        assert link.state == "open"

        payload.update(action="closed")
        payload["pull_request"].update(merged=True, updated_at="2026-07-31T02:00:00Z")
        assert _post_signed_webhook(api_client, payload, secret, "delivery-merged").status_code == status.HTTP_200_OK
        link.refresh_from_db()
        assert link.state == "merged"

        payload["pull_request"].update(merged=False, updated_at="2026-07-31T00:30:00Z")
        assert _post_signed_webhook(api_client, payload, secret, "delivery-stale").status_code == status.HTTP_200_OK
        link.refresh_from_db()
        assert link.state == "merged"

        payload.update(action="reopened")
        payload["pull_request"].update(merged=False, updated_at="2026-07-31T03:00:00Z")
        assert _post_signed_webhook(api_client, payload, secret, "delivery-reopened").status_code == status.HTTP_200_OK
        link.refresh_from_db()
        assert link.state == "open"

    @pytest.mark.django_db
    def test_webhook_shared_branch_fans_out_pr_link_to_every_linked_issue(
        self, api_client, webhook_context, project, issue, create_user
    ):
        # Option 3 (Phase 2): a PR opened from a branch shared by multiple
        # issues must attach to ALL of them, not just the first/newest match.
        installation, repository = webhook_context
        secret = _configure_webhook_app()
        second_issue = Issue.objects.create(
            name="Second Issue",
            project=project,
            workspace=project.workspace,
            created_by=create_user,
            sequence_id=2,
        )
        for target_issue in (issue, second_issue):
            IssueGitLink.objects.create(
                workspace=project.workspace,
                project=project,
                issue=target_issue,
                github_repo=repository.full_name,
                kind="branch",
                ref="feature/shared-branch",
                url="https://github.example/acme/widgets/tree/feature/shared-branch",
                state="open",
                detected_via="manual",
            )

        payload = _pull_request_payload(
            installation, repository, number=55, title="no key here", head="feature/shared-branch"
        )
        response = _post_signed_webhook(api_client, payload, secret, "delivery-shared-open")
        assert response.status_code == status.HTTP_200_OK

        links = IssueGitLink.objects.filter(kind="pr", github_repo=repository.full_name, pr_number=55)
        assert links.count() == 2
        assert set(links.values_list("issue_id", flat=True)) == {issue.id, second_issue.id}
        assert all(link.state == "open" and link.detected_via == "branch" for link in links)

        # A later delivery for the same PR must update every linked issue's
        # row, not just one of them, and must not create duplicates.
        payload.update(action="closed")
        payload["pull_request"].update(merged=True, updated_at="2026-07-31T05:00:00Z")
        response = _post_signed_webhook(api_client, payload, secret, "delivery-shared-closed")
        assert response.status_code == status.HTTP_200_OK

        links = IssueGitLink.objects.filter(kind="pr", github_repo=repository.full_name, pr_number=55)
        assert links.count() == 2
        assert all(link.state == "merged" for link in links)

        # GitHub retrying the exact same delivery must be a pure no-op.
        replay = _post_signed_webhook(api_client, payload, secret, "delivery-shared-closed")
        assert replay.status_code == status.HTTP_200_OK
        links = IssueGitLink.objects.filter(kind="pr", github_repo=repository.full_name, pr_number=55)
        assert links.count() == 2
        assert all(link.state == "merged" for link in links)

    @pytest.mark.django_db
    def test_issue_key_no_match_and_cross_workspace_mapping_are_safe(self, api_client, webhook_context, create_user):
        installation, repository = webhook_context
        secret = _configure_webhook_app()
        payload = _pull_request_payload(
            installation, repository, title="TP-999 only outside issue", head="release/no-key", number=19
        )
        assert _post_signed_webhook(api_client, payload, secret, "delivery-no-match").status_code == status.HTTP_200_OK
        assert not IssueGitLink.objects.filter(kind="pr").exists()

        second_workspace = Workspace.objects.create(
            name="Other Workspace", slug="other-webhook-workspace", owner=create_user
        )
        WorkspaceMember.objects.create(workspace=second_workspace, member=create_user, role=20)
        second_project = Project.objects.create(
            name="Other Project", identifier="TP", workspace=second_workspace, created_by=create_user
        )
        second_issue = Issue.objects.create(
            name="Other Issue",
            project=second_project,
            workspace=second_workspace,
            created_by=create_user,
            sequence_id=999,
        )
        RepoProjectMapping.objects.create(
            workspace=second_workspace,
            project=second_project,
            repository=repository,
            github_installation_id=installation.installation_id,
            github_repo=repository.full_name,
        )
        assert (
            _post_signed_webhook(api_client, payload, secret, "delivery-cross-workspace").status_code
            == status.HTTP_200_OK
        )
        assert not IssueGitLink.objects.filter(kind="pr", issue=second_issue).exists()


    @pytest.mark.django_db
    def test_existing_pr_updates_without_a_current_issue_key(self, api_client, webhook_context):
        installation, repository = webhook_context
        secret = _configure_webhook_app()
        payload = _pull_request_payload(installation, repository, number=20, title="TP-1 initial")
        assert (
            _post_signed_webhook(api_client, payload, secret, "delivery-existing-open").status_code
            == status.HTTP_200_OK
        )
        payload.update(action="closed")
        payload["pull_request"].update(
            title="release housekeeping",
            head={"ref": "release/no-key"},
            merged=False,
            updated_at="2026-07-31T03:00:00Z",
        )
        assert (
            _post_signed_webhook(api_client, payload, secret, "delivery-existing-close").status_code
            == status.HTTP_200_OK
        )
        link = IssueGitLink.objects.get(kind="pr", github_repo=repository.full_name, pr_number=20)
        assert link.state == "closed"
        assert link.ref == "release/no-key"

        synchronize = _pull_request_payload(
            installation, repository, number=22, title="TP-1 synchronize", action="synchronize"
        )
        assert (
            _post_signed_webhook(api_client, synchronize, secret, "delivery-sync-initial").status_code
            == status.HTTP_200_OK
        )
        assert IssueGitLink.objects.get(kind="pr", github_repo=repository.full_name, pr_number=22).state == "open"

    @pytest.mark.django_db
    def test_pr_identity_is_scoped_to_workspace(self, api_client, webhook_context, create_user):
        installation, repository = webhook_context
        secret = _configure_webhook_app()
        second_workspace = Workspace.objects.create(
            name="Separate Workspace", slug="separate-webhook-workspace", owner=create_user
        )
        WorkspaceMember.objects.create(workspace=second_workspace, member=create_user, role=20)
        second_project = Project.objects.create(
            name="Separate Project", identifier="ZZ", workspace=second_workspace, created_by=create_user
        )
        second_issue = Issue.objects.create(
            name="Separate Issue",
            project=second_project,
            workspace=second_workspace,
            created_by=create_user,
            sequence_id=1,
        )
        IssueGitLink.objects.create(
            workspace=second_workspace,
            project=second_project,
            issue=second_issue,
            github_repo=repository.full_name,
            kind="pr",
            ref="old-ref",
            url="https://github.example/acme/widgets/pull/21",
            state="open",
            pr_number=21,
            detected_via="title",
        )
        payload = _pull_request_payload(installation, repository, number=21, title="TP-1 current workspace")
        assert (
            _post_signed_webhook(api_client, payload, secret, "delivery-workspace-scoped").status_code
            == status.HTTP_200_OK
        )
        current_link = IssueGitLink.objects.get(
            workspace=installation.workspace, kind="pr", github_repo=repository.full_name, pr_number=21
        )
        assert current_link.issue.workspace_id == installation.workspace_id
        foreign_link = IssueGitLink.objects.get(workspace=second_workspace, kind="pr", pr_number=21)
        assert foreign_link.issue_id == second_issue.id


# ---------------------------------------------------------------------------
# P1 1.6: installation / installation_repositories webhook lifecycle events
# ---------------------------------------------------------------------------


def _post_signed_webhook_event(api_client, payload, secret, delivery_id, event):
    body = json.dumps(payload).encode()
    signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return api_client.post(
        TestGitHubWebhookAPI.WEBHOOK_URL,
        data=body,
        content_type="application/json",
        HTTP_X_HUB_SIGNATURE_256=signature,
        HTTP_X_GITHUB_EVENT=event,
        HTTP_X_GITHUB_DELIVERY=delivery_id,
    )


@pytest.mark.contract
class TestGitHubInstallationLifecycleWebhook:
    @pytest.mark.django_db
    def test_unknown_event_is_a_200_noop(self, api_client, webhook_context):
        secret = _configure_webhook_app()
        response = _post_signed_webhook_event(
            api_client, {"action": "whatever"}, secret, "delivery-unknown-event", "star"
        )
        assert response.status_code == status.HTTP_200_OK
        assert GithubWebhookDelivery.objects.filter(delivery_id="delivery-unknown-event", event="star").exists()

    @pytest.mark.django_db
    def test_installation_created_is_a_noop_and_never_attaches_a_workspace(self, api_client, webhook_context):
        installation, _repository = webhook_context
        secret = _configure_webhook_app()
        payload = {"action": "created", "installation": {"id": installation.installation_id + 1}}
        response = _post_signed_webhook_event(api_client, payload, secret, "delivery-install-created", "installation")
        assert response.status_code == status.HTTP_200_OK
        assert not GithubAppInstallation.objects.filter(installation_id=installation.installation_id + 1).exists()

    @pytest.mark.django_db
    def test_installation_deleted_flips_is_active_and_frees_the_installation_id(self, api_client, webhook_context):
        # N6: "deleted" must soft-delete (not just is_active=False) so the
        # unique installation_id claim is freed -- otherwise a reinstall of
        # the same account can never attach a fresh row (coordinates with I3).
        installation, _repository = webhook_context
        secret = _configure_webhook_app()
        payload = {"action": "deleted", "installation": {"id": installation.installation_id}}
        with patch("plane.db.mixins.soft_delete_related_objects.delay"):
            response = _post_signed_webhook_event(
                api_client, payload, secret, "delivery-install-deleted", "installation"
            )
        assert response.status_code == status.HTTP_200_OK
        # The default `objects` manager filters out soft-deleted rows, so a
        # plain refresh_from_db() would raise DoesNotExist -- go through
        # all_objects instead.
        installation = GithubAppInstallation.all_objects.get(pk=installation.pk)
        assert installation.is_active is False
        assert installation.suspended_at is not None
        assert installation.deleted_at is not None

    @pytest.mark.django_db
    def test_installation_suspend_and_unsuspend_flip_is_active(self, api_client, webhook_context):
        installation, _repository = webhook_context
        secret = _configure_webhook_app()

        suspend_payload = {"action": "suspend", "installation": {"id": installation.installation_id}}
        response = _post_signed_webhook_event(
            api_client, suspend_payload, secret, "delivery-install-suspend", "installation"
        )
        assert response.status_code == status.HTTP_200_OK
        installation.refresh_from_db()
        assert installation.is_active is False
        assert installation.suspended_at is not None

        unsuspend_payload = {"action": "unsuspend", "installation": {"id": installation.installation_id}}
        response = _post_signed_webhook_event(
            api_client, unsuspend_payload, secret, "delivery-install-unsuspend", "installation"
        )
        assert response.status_code == status.HTTP_200_OK
        installation.refresh_from_db()
        assert installation.is_active is True
        assert installation.suspended_at is None

    @pytest.mark.django_db
    def test_installation_repositories_removed_disables_repo_and_leaves_mapping_intact(
        self, api_client, webhook_context, project
    ):
        installation, repository = webhook_context
        secret = _configure_webhook_app()
        payload = {
            "action": "removed",
            "installation": {"id": installation.installation_id},
            "repositories_removed": [{"id": repository.github_repository_id, "full_name": repository.full_name}],
        }
        response = _post_signed_webhook_event(
            api_client, payload, secret, "delivery-repo-removed", "installation_repositories"
        )
        assert response.status_code == status.HTTP_200_OK
        repository.refresh_from_db()
        assert repository.is_enabled is False
        assert RepoProjectMapping.objects.filter(project=project, repository=repository).exists()

    @pytest.mark.django_db
    def test_installation_repositories_added_is_a_noop(self, api_client, webhook_context):
        installation, repository = webhook_context
        secret = _configure_webhook_app()
        payload = {
            "action": "added",
            "installation": {"id": installation.installation_id},
            "repositories_added": [{"id": repository.github_repository_id, "full_name": repository.full_name}],
        }
        response = _post_signed_webhook_event(
            api_client, payload, secret, "delivery-repo-added", "installation_repositories"
        )
        assert response.status_code == status.HTTP_200_OK
        repository.refresh_from_db()
        assert repository.is_enabled is True
