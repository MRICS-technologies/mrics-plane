# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Contract tests for workspace teams and the team default GitHub repository.

GET/POST     /api/workspaces/<slug>/teams/
PATCH/DELETE /api/workspaces/<slug>/teams/<team_id>/
POST         /api/workspaces/<slug>/teams/<team_id>/members/
DELETE       /api/workspaces/<slug>/teams/<team_id>/members/<member_id>/

plus the team default repository in branch creation and the mapping list.
None of these tests contact GitHub.
"""

import uuid
from unittest.mock import patch

import pytest
from django.db import IntegrityError, connection, transaction
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from plane.db.models import (
    Issue,
    Project,
    ProjectMember,
    Team,
    TeamMember,
    User,
    Workspace,
    WorkspaceMember,
)
from plane.db.models.integration.github_app import GithubAppInstallation, GithubEnabledRepository
from plane.db.mixins import SoftDeletionQuerySet
from plane.db.models.integration.github_sync import RepoProjectMapping
from plane.license.models import InstanceConfiguration
from plane.license.utils.encryption import encrypt_data
from plane.services.github.installations import soft_delete_installations
from plane.services.github.team_repo import pick_branch_mapping


def _teams_url(slug):
    return f"/api/workspaces/{slug}/teams/"


def _team_url(slug, team_id):
    return f"/api/workspaces/{slug}/teams/{team_id}/"


def _members_url(slug, team_id):
    return f"/api/workspaces/{slug}/teams/{team_id}/members/"


def _member_url(slug, team_id, member_id):
    return f"/api/workspaces/{slug}/teams/{team_id}/members/{member_id}/"


def _client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _user(email):
    user = User.objects.create(email=email, username=email.split("@")[0], first_name=email.split("@")[0])
    user.set_password("test")
    user.save()
    return user


def _team(workspace, name, default_repository=None, members=()):
    team = Team.objects.create(workspace=workspace, name=name, default_repository=default_repository)
    for member in members:
        TeamMember.objects.create(workspace=workspace, team=team, member=member)
    return team


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def admin_client(session_client):
    return session_client


@pytest.fixture
def member_user(db, workspace):
    user = _user("member@plane.so")
    WorkspaceMember.objects.create(workspace=workspace, member=user, role=15)
    return user


@pytest.fixture
def guest_user(db, workspace):
    user = _user("guest@plane.so")
    WorkspaceMember.objects.create(workspace=workspace, member=user, role=5)
    return user


@pytest.fixture
def installation(db, workspace):
    return GithubAppInstallation.objects.create(
        workspace=workspace, installation_id=77770001, account_login="acme", account_type="Organization"
    )


def _repo(installation, github_id, full_name, is_enabled=True):
    return GithubEnabledRepository.objects.create(
        installation=installation, github_repository_id=github_id, full_name=full_name, is_enabled=is_enabled
    )


@pytest.fixture
def repo_a(installation):
    return _repo(installation, 1001, "acme/api")


@pytest.fixture
def repo_b(installation):
    return _repo(installation, 1002, "acme/web")


@pytest.fixture
def repo_c(installation):
    return _repo(installation, 1003, "acme/docs")


@pytest.fixture
def other_workspace(db, create_user):
    ws = Workspace.objects.create(name="Other Workspace", owner=create_user, slug="other-workspace")
    WorkspaceMember.objects.create(workspace=ws, member=create_user, role=20)
    return ws


@pytest.fixture
def other_installation(other_workspace):
    return GithubAppInstallation.objects.create(
        workspace=other_workspace, installation_id=77770002, account_login="other", account_type="Organization"
    )


@pytest.fixture
def project(db, workspace, create_user, member_user):
    p = Project.objects.create(name="Teams Project", identifier="TMP", workspace=workspace, created_by=create_user)
    ProjectMember.objects.create(workspace=workspace, project=p, member=create_user, role=20, is_active=True)
    ProjectMember.objects.create(workspace=workspace, project=p, member=member_user, role=15, is_active=True)
    return p


@pytest.fixture
def issue(project, create_user):
    return Issue.objects.create(
        name="Teams Issue", project=project, workspace=project.workspace, created_by=create_user
    )


@pytest.fixture
def mapping_a(project, repo_a):
    # The project default.
    return RepoProjectMapping.objects.create(
        project=project,
        repository=repo_a,
        github_installation_id=77770001,
        github_repo=repo_a.full_name,
        base_branch="main",
        is_default=True,
    )


@pytest.fixture
def mapping_b(project, repo_b):
    return RepoProjectMapping.objects.create(
        project=project,
        repository=repo_b,
        github_installation_id=77770001,
        github_repo=repo_b.full_name,
        base_branch="main",
        is_default=False,
    )


@pytest.fixture
def github_app(db):
    InstanceConfiguration.objects.update_or_create(
        key="GITHUB_APP_ID", defaults={"value": "123456", "category": "GITHUB_APP", "is_encrypted": False}
    )
    InstanceConfiguration.objects.update_or_create(
        key="GITHUB_APP_PRIVATE_KEY",
        defaults={"value": encrypt_data("fake-pem-private-key"), "category": "GITHUB_APP", "is_encrypted": True},
    )


# ============================================================================
# Team CRUD
# ============================================================================


@pytest.mark.contract
class TestTeamCrud:
    @pytest.mark.django_db
    def test_admin_creates_renames_and_deletes_a_team(self, admin_client, workspace):
        resp = admin_client.post(_teams_url(workspace.slug), {"name": "Frontend"}, format="json")
        assert resp.status_code == status.HTTP_201_CREATED, resp.data
        assert resp.data["name"] == "Frontend"
        assert resp.data["description"] == ""
        assert resp.data["default_repository"] is None
        assert resp.data["member_ids"] == []
        team_id = resp.data["id"]

        resp = admin_client.patch(
            _team_url(workspace.slug, team_id), {"name": "Web", "description": "UI"}, format="json"
        )
        assert resp.status_code == status.HTTP_200_OK, resp.data
        assert (resp.data["name"], resp.data["description"]) == ("Web", "UI")

        resp = admin_client.delete(_team_url(workspace.slug, team_id))
        assert resp.status_code == status.HTTP_204_NO_CONTENT
        assert admin_client.get(_teams_url(workspace.slug)).data == []
        assert Team.all_objects.get(pk=team_id).deleted_at is not None

    @pytest.mark.django_db
    def test_list_is_ordered_by_name(self, admin_client, workspace, repo_b, member_user):
        _team(workspace, "Zeta")
        _team(workspace, "Alpha", default_repository=repo_b, members=[member_user])

        resp = admin_client.get(_teams_url(workspace.slug))

        assert resp.status_code == status.HTTP_200_OK
        assert [team["name"] for team in resp.data] == ["Alpha", "Zeta"]
        alpha = resp.data[0]
        assert set(alpha) == {"id", "name", "description", "default_repository", "member_ids", "created_at"}
        assert alpha["default_repository"] == {"id": str(repo_b.id), "full_name": "acme/web"}
        assert alpha["member_ids"] == [str(member_user.id)]

    @pytest.mark.django_db
    def test_duplicate_live_name_is_rejected(self, admin_client, workspace):
        assert admin_client.post(_teams_url(workspace.slug), {"name": "Frontend"}, format="json").status_code == 201
        resp = admin_client.post(_teams_url(workspace.slug), {"name": "Frontend"}, format="json")
        assert resp.status_code == status.HTTP_409_CONFLICT

        backend = _team(workspace, "Backend")
        resp = admin_client.patch(_team_url(workspace.slug, backend.id), {"name": "Frontend"}, format="json")
        assert resp.status_code == status.HTTP_409_CONFLICT

        # A deleted team frees its name.
        frontend = Team.objects.get(workspace=workspace, name="Frontend")
        assert admin_client.delete(_team_url(workspace.slug, frontend.id)).status_code == 204
        assert admin_client.post(_teams_url(workspace.slug), {"name": "Frontend"}, format="json").status_code == 201

    @pytest.mark.django_db
    def test_name_is_required(self, admin_client, workspace):
        assert admin_client.post(_teams_url(workspace.slug), {}, format="json").status_code == 400
        assert admin_client.post(_teams_url(workspace.slug), {"name": "  "}, format="json").status_code == 400

    @pytest.mark.django_db
    def test_member_can_list_but_not_write(self, workspace, member_user, create_user):
        team = _team(workspace, "Frontend", members=[create_user])
        client = _client(member_user)

        assert client.get(_teams_url(workspace.slug)).status_code == status.HTTP_200_OK
        forbidden = [
            client.post(_teams_url(workspace.slug), {"name": "X"}, format="json"),
            client.patch(_team_url(workspace.slug, team.id), {"name": "X"}, format="json"),
            client.delete(_team_url(workspace.slug, team.id)),
            client.post(_members_url(workspace.slug, team.id), {"member_ids": [str(member_user.id)]}, format="json"),
            client.delete(_member_url(workspace.slug, team.id, create_user.id)),
        ]
        assert [resp.status_code for resp in forbidden] == [403] * 5
        assert TeamMember.objects.filter(team=team).count() == 1
        assert Team.objects.filter(workspace=workspace).count() == 1

    @pytest.mark.django_db
    def test_guest_and_outsider_cannot_list(self, workspace, guest_user):
        assert _client(guest_user).get(_teams_url(workspace.slug)).status_code == status.HTTP_403_FORBIDDEN
        outsider = _user("outsider@plane.so")
        assert _client(outsider).get(_teams_url(workspace.slug)).status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.django_db
    def test_default_repository_is_set_and_cleared(self, admin_client, workspace, repo_b):
        resp = admin_client.post(
            _teams_url(workspace.slug), {"name": "Frontend", "default_repository_id": str(repo_b.id)}, format="json"
        )
        assert resp.status_code == status.HTTP_201_CREATED, resp.data
        assert resp.data["default_repository"] == {"id": str(repo_b.id), "full_name": "acme/web"}

        resp = admin_client.patch(
            _team_url(workspace.slug, resp.data["id"]), {"default_repository_id": None}, format="json"
        )
        assert resp.status_code == status.HTTP_200_OK, resp.data
        assert resp.data["default_repository"] is None

    @pytest.mark.django_db
    def test_default_repository_must_be_an_enabled_repo_of_this_workspace(
        self, admin_client, workspace, installation, other_installation
    ):
        disabled = _repo(installation, 1009, "acme/old", is_enabled=False)
        foreign = _repo(other_installation, 2001, "other/web")
        for repo_id in (disabled.id, foreign.id, uuid.uuid4(), "not-a-uuid"):
            resp = admin_client.post(
                _teams_url(workspace.slug), {"name": "Frontend", "default_repository_id": str(repo_id)}, format="json"
            )
            assert resp.status_code == status.HTTP_400_BAD_REQUEST, repo_id
            assert "default_repository_id" in resp.data
        assert not Team.objects.filter(workspace=workspace).exists()

    @pytest.mark.django_db
    def test_default_repository_of_an_inactive_installation_is_rejected(self, admin_client, workspace, repo_b):
        GithubAppInstallation.objects.filter(pk=repo_b.installation_id).update(is_active=False)
        resp = admin_client.post(
            _teams_url(workspace.slug), {"name": "Frontend", "default_repository_id": str(repo_b.id)}, format="json"
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST


# ============================================================================
# Cross-workspace isolation
# ============================================================================


@pytest.mark.contract
class TestTeamCrossWorkspace:
    @pytest.mark.django_db
    def test_team_of_another_workspace_is_404(self, admin_client, workspace, other_workspace, create_user):
        foreign = _team(other_workspace, "Foreign", members=[create_user])

        assert admin_client.get(_teams_url(workspace.slug)).data == []
        responses = [
            admin_client.patch(_team_url(workspace.slug, foreign.id), {"name": "X"}, format="json"),
            admin_client.delete(_team_url(workspace.slug, foreign.id)),
            admin_client.post(
                _members_url(workspace.slug, foreign.id), {"member_ids": [str(create_user.id)]}, format="json"
            ),
            admin_client.delete(_member_url(workspace.slug, foreign.id, create_user.id)),
        ]
        assert [resp.status_code for resp in responses] == [404] * 4
        foreign.refresh_from_db()
        assert foreign.name == "Foreign" and foreign.deleted_at is None
        assert TeamMember.objects.filter(team=foreign).count() == 1

    @pytest.mark.django_db
    def test_adding_a_user_of_another_workspace_is_400_and_writes_nothing(
        self, admin_client, workspace, other_workspace, member_user
    ):
        team = _team(workspace, "Frontend")
        stranger = _user("stranger@plane.so")
        WorkspaceMember.objects.create(workspace=other_workspace, member=stranger, role=15)

        resp = admin_client.post(
            _members_url(workspace.slug, team.id),
            {"member_ids": [str(member_user.id), str(stranger.id)]},
            format="json",
        )

        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert resp.data["member_ids"] == [str(stranger.id)]
        assert not TeamMember.objects.filter(team=team).exists()

    @pytest.mark.django_db
    def test_adding_an_inactive_workspace_member_is_400(self, admin_client, workspace, member_user):
        WorkspaceMember.objects.filter(workspace=workspace, member=member_user).update(is_active=False)
        team = _team(workspace, "Frontend")

        resp = admin_client.post(
            _members_url(workspace.slug, team.id), {"member_ids": [str(member_user.id)]}, format="json"
        )

        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert resp.data["member_ids"] == [str(member_user.id)]


# ============================================================================
# Membership
# ============================================================================


@pytest.mark.contract
class TestTeamMembership:
    @pytest.mark.django_db
    def test_add_members_returns_the_team(self, admin_client, workspace, create_user, member_user):
        team = _team(workspace, "Frontend")

        resp = admin_client.post(
            _members_url(workspace.slug, team.id),
            {"member_ids": [str(create_user.id), str(member_user.id), str(member_user.id)]},
            format="json",
        )

        assert resp.status_code == status.HTTP_200_OK, resp.data
        assert resp.data["id"] == str(team.id)
        assert sorted(resp.data["member_ids"]) == sorted([str(create_user.id), str(member_user.id)])

    @pytest.mark.django_db
    def test_member_ids_must_be_a_non_empty_uuid_list(self, admin_client, workspace):
        team = _team(workspace, "Frontend")
        url = _members_url(workspace.slug, team.id)
        for body in ({}, {"member_ids": []}, {"member_ids": ["nope"]}, {"member_ids": "x"}):
            assert admin_client.post(url, body, format="json").status_code == status.HTTP_400_BAD_REQUEST, body

    @pytest.mark.django_db
    def test_adding_a_member_of_another_team_moves_them(self, admin_client, workspace, member_user):
        team_x = _team(workspace, "X", members=[member_user])
        team_y = _team(workspace, "Y")

        resp = admin_client.post(
            _members_url(workspace.slug, team_y.id), {"member_ids": [str(member_user.id)]}, format="json"
        )

        assert resp.status_code == status.HTTP_200_OK, resp.data
        rows = TeamMember.all_objects.filter(workspace=workspace, member=member_user)
        assert rows.count() == 1
        assert rows.get().team_id == team_y.id
        assert not TeamMember.objects.filter(team=team_x).exists()

    @pytest.mark.django_db
    def test_adding_a_member_already_in_the_team_is_a_noop(self, admin_client, workspace, member_user):
        team = _team(workspace, "Frontend", members=[member_user])
        row_id = TeamMember.objects.get(team=team).id

        resp = admin_client.post(
            _members_url(workspace.slug, team.id), {"member_ids": [str(member_user.id)]}, format="json"
        )

        assert resp.status_code == status.HTTP_200_OK
        assert list(TeamMember.all_objects.filter(member=member_user).values_list("id", flat=True)) == [row_id]

    @pytest.mark.django_db
    def test_member_added_concurrently_elsewhere_is_moved_not_a_500(self, admin_client, workspace, member_user):
        team_x = _team(workspace, "X")
        team_y = _team(workspace, "Y")
        real_get = SoftDeletionQuerySet.get

        def racing_get(queryset, *args, **kwargs):
            # Another request adds the member to X right after our lookup
            # misses, so our insert hits the one-team-per-member constraint.
            try:
                return real_get(queryset, *args, **kwargs)
            except TeamMember.DoesNotExist:
                TeamMember(workspace=workspace, team=team_x, member=member_user).save()
                raise

        with patch.object(SoftDeletionQuerySet, "get", racing_get):
            resp = admin_client.post(
                _members_url(workspace.slug, team_y.id), {"member_ids": [str(member_user.id)]}, format="json"
            )

        assert resp.status_code == status.HTTP_200_OK, resp.data
        assert resp.data["member_ids"] == [str(member_user.id)]
        assert TeamMember.all_objects.get(member=member_user).team_id == team_y.id

    @pytest.mark.django_db
    def test_member_ids_hide_members_who_left_the_workspace(self, admin_client, workspace, create_user, member_user):
        _team(workspace, "Frontend", members=[create_user, member_user])
        left = _user("left@plane.so")
        removed = _user("removed@plane.so")
        WorkspaceMember.objects.create(workspace=workspace, member=left, role=15, is_active=False)
        WorkspaceMember.objects.create(workspace=workspace, member=removed, role=15, deleted_at=timezone.now())
        _team(workspace, "Backend", members=[left, removed])

        def list_teams():
            with CaptureQueriesContext(connection) as ctx:
                resp = admin_client.get(_teams_url(workspace.slug))
            assert resp.status_code == status.HTTP_200_OK
            return {team["name"]: sorted(team["member_ids"]) for team in resp.data}, len(ctx)

        teams, queries = list_teams()
        assert teams == {"Backend": [], "Frontend": sorted([str(create_user.id), str(member_user.id)])}

        for i in range(3):
            _team(workspace, f"Team {i}", members=[_user(f"m{i}@plane.so")])
        assert list_teams()[1] == queries

    @pytest.mark.django_db
    def test_remove_member(self, admin_client, workspace, member_user):
        team = _team(workspace, "Frontend", members=[member_user])

        resp = admin_client.delete(_member_url(workspace.slug, team.id, member_user.id))
        assert resp.status_code == status.HTTP_204_NO_CONTENT
        assert not TeamMember.all_objects.filter(member=member_user).exists()

        resp = admin_client.delete(_member_url(workspace.slug, team.id, member_user.id))
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.django_db
    def test_deleting_a_team_hard_deletes_its_memberships(self, admin_client, workspace, member_user):
        team = _team(workspace, "Frontend", members=[member_user])
        other = _team(workspace, "Backend")

        with patch("plane.db.mixins.soft_delete_related_objects") as cascade:
            assert admin_client.delete(_team_url(workspace.slug, team.id)).status_code == 204

        # No soft-delete cascade: it would only re-touch the hard-deleted rows.
        cascade.delay.assert_not_called()
        assert Team.all_objects.get(pk=team.pk).deleted_at is not None
        assert not TeamMember.all_objects.filter(team=team).exists()
        resp = admin_client.post(
            _members_url(workspace.slug, other.id), {"member_ids": [str(member_user.id)]}, format="json"
        )
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["member_ids"] == [str(member_user.id)]

    @pytest.mark.django_db
    def test_db_allows_one_live_team_per_workspace_member(self, workspace, member_user):
        _team(workspace, "X", members=[member_user])
        team_y = _team(workspace, "Y")

        with pytest.raises(IntegrityError), transaction.atomic():
            TeamMember.objects.create(workspace=workspace, team=team_y, member=member_user)


# ============================================================================
# Branch creation: team default repository before the project default
# ============================================================================


def _create_branch(client, project, issue, **extra):
    """POST create-branch with GitHub mocked; returns the (owner, repo) the branch was created on."""
    url = f"/api/workspaces/{project.workspace.slug}/projects/{project.id}/issues/{issue.id}/github/create-branch/"
    result = {"branch_name": "feature/x", "url": "https://github.example/x", "sha": "abc123"}
    with (
        patch("plane.app.views.github_sync.GitHubClient.get_branch_sha", return_value=None),
        patch("plane.app.views.github_sync.GitHubClient.create_branch", return_value=result) as mock_create,
    ):
        resp = client.post(url, {"branch_name": "feature/x", **extra}, format="json")
    assert resp.status_code == status.HTTP_201_CREATED, resp.data
    owner, name = mock_create.call_args.args[:2]
    return f"{owner}/{name}"


@pytest.mark.contract
class TestBranchUsesTeamDefaultRepository:
    @pytest.fixture(autouse=True)
    def _setup(self, github_app, mapping_a, mapping_b):
        pass

    @pytest.mark.django_db
    def test_team_default_repo_wins_over_the_project_default(
        self, admin_client, workspace, project, issue, repo_b, create_user
    ):
        _team(workspace, "Frontend", default_repository=repo_b, members=[create_user])
        assert _create_branch(admin_client, project, issue) == "acme/web"

    @pytest.mark.django_db
    def test_explicit_repo_still_wins(self, admin_client, workspace, project, issue, repo_b, create_user):
        _team(workspace, "Frontend", default_repository=repo_b, members=[create_user])
        assert _create_branch(admin_client, project, issue, repo="acme/api") == "acme/api"

    @pytest.mark.django_db
    def test_team_repo_not_attached_to_the_project_falls_back(
        self, admin_client, workspace, project, issue, repo_c, create_user
    ):
        _team(workspace, "Docs", default_repository=repo_c, members=[create_user])
        assert _create_branch(admin_client, project, issue) == "acme/api"

    @pytest.mark.django_db
    def test_user_without_a_team_gets_the_project_default(self, admin_client, workspace, project, issue, repo_b):
        _team(workspace, "Frontend", default_repository=repo_b)
        assert _create_branch(admin_client, project, issue) == "acme/api"

    @pytest.mark.django_db
    @pytest.mark.parametrize(
        "break_it",
        ["delete_team", "remove_member", "disable_repo", "remove_mapping", "deactivate_installation"],
    )
    def test_falls_back_to_the_project_default(
        self, break_it, admin_client, workspace, project, issue, repo_b, mapping_b, create_user
    ):
        team = _team(workspace, "Frontend", default_repository=repo_b, members=[create_user])
        assert _create_branch(admin_client, project, issue) == "acme/web"

        if break_it == "delete_team":
            assert admin_client.delete(_team_url(workspace.slug, team.id)).status_code == 204
        elif break_it == "remove_member":
            assert admin_client.delete(_member_url(workspace.slug, team.id, create_user.id)).status_code == 204
        elif break_it == "disable_repo":
            GithubEnabledRepository.objects.filter(pk=repo_b.pk).update(is_enabled=False)
        elif break_it == "remove_mapping":
            mapping_url = f"/api/workspaces/{workspace.slug}/projects/{project.id}/github/mappings/{mapping_b.id}/"
            assert admin_client.delete(mapping_url).status_code == 204
        else:
            GithubAppInstallation.objects.filter(pk=repo_b.installation_id).update(is_active=False)

        assert _create_branch(admin_client, project, issue) == "acme/api"

    @pytest.mark.django_db
    @pytest.mark.parametrize("remove_repo", ["soft_delete_repo", "disconnect_installation"])
    def test_deleted_team_repo_falls_back_and_is_not_hinted(
        self, remove_repo, admin_client, workspace, project, issue, installation, repo_b, create_user
    ):
        team = _team(workspace, "Frontend", default_repository=repo_b, members=[create_user])
        if remove_repo == "soft_delete_repo":
            GithubEnabledRepository.objects.filter(pk=repo_b.pk).update(deleted_at=timezone.now())
        else:
            soft_delete_installations([installation])
            # Reconnected: the same GitHub repositories come back as new rows
            # and the mappings are revived (as the create endpoint does); the
            # team still points at the old, deleted acme/web row.
            reconnected = GithubAppInstallation.objects.create(
                workspace=workspace, installation_id=77770001, account_login="acme", account_type="Organization"
            )
            for mapping in RepoProjectMapping.all_objects.filter(project=project):
                mapping.repository = _repo(reconnected, mapping.repository.github_repository_id, mapping.github_repo)
                mapping.deleted_at = None
                mapping.save()
        assert Team.objects.get(pk=team.pk).default_repository_id == repo_b.id

        assert _create_branch(admin_client, project, issue) == "acme/api"
        mappings = admin_client.get(f"/api/workspaces/{workspace.slug}/projects/{project.id}/github/mappings/").data
        assert {m["github_repo"] for m in mappings} == {"acme/api", "acme/web"}
        assert [(m["is_my_team_default"], m["default_for_teams"]) for m in mappings] == [(False, [])] * 2

    @pytest.mark.django_db
    def test_legacy_mapping_matches_the_team_repo_by_name(
        self, admin_client, workspace, project, issue, repo_b, mapping_b, create_user
    ):
        RepoProjectMapping.objects.filter(pk=mapping_b.pk).update(repository=None, github_repo="ACME/Web")
        _team(workspace, "Frontend", default_repository=repo_b, members=[create_user])
        assert _create_branch(admin_client, project, issue) == "ACME/Web"

    @pytest.mark.django_db
    def test_inactive_workspace_member_has_no_team_default(self, workspace, project, repo_b, mapping_a, member_user):
        _team(workspace, "Frontend", default_repository=repo_b, members=[member_user])
        assert pick_branch_mapping(workspace.slug, project.id, member_user).github_repo == "acme/web"

        WorkspaceMember.objects.filter(workspace=workspace, member=member_user).update(is_active=False)
        assert pick_branch_mapping(workspace.slug, project.id, member_user) == mapping_a


# ============================================================================
# Mapping list: team default hints
# ============================================================================


@pytest.mark.contract
class TestMappingListTeamHints:
    @pytest.mark.django_db
    def test_hints_mark_the_users_team_repo_and_list_teams(
        self, admin_client, workspace, project, repo_a, repo_b, mapping_a, mapping_b, create_user, member_user
    ):
        _team(workspace, "Frontend", default_repository=repo_b, members=[create_user])
        backend = _team(workspace, "Backend", default_repository=repo_a)
        web2 = _team(workspace, "Web 2", default_repository=repo_b)
        _team(workspace, "No Repo")
        url = f"/api/workspaces/{workspace.slug}/projects/{project.id}/github/mappings/"

        data = {m["github_repo"]: m for m in admin_client.get(url).data}

        assert data["acme/web"]["is_my_team_default"] is True
        assert data["acme/api"]["is_my_team_default"] is False
        frontend = Team.objects.get(name="Frontend")
        assert data["acme/web"]["default_for_teams"] == [
            {"id": str(frontend.id), "name": "Frontend"},
            {"id": str(web2.id), "name": "Web 2"},
        ]
        assert data["acme/api"]["default_for_teams"] == [{"id": str(backend.id), "name": "Backend"}]
        # Existing fields are untouched.
        assert data["acme/api"]["is_default"] is True
        assert data["acme/web"]["repository_detail"]["id"] == repo_b.id

        # A member without a team sees the hints but no "my team" repository.
        member_data = _client(member_user).get(url).data
        assert [m["is_my_team_default"] for m in member_data] == [False, False]

    @pytest.mark.django_db
    def test_hints_ignore_teams_of_other_workspaces_and_unusable_repos(
        self, admin_client, workspace, other_workspace, other_installation, project, repo_b, mapping_b, create_user
    ):
        # A legacy mapping matches by name: a same-named repository of another
        # workspace must still not leak that workspace's teams.
        RepoProjectMapping.objects.filter(pk=mapping_b.pk).update(repository=None)
        foreign_repo = _repo(other_installation, 3001, "acme/web")
        _team(other_workspace, "Foreign", default_repository=foreign_repo, members=[create_user])
        disabled = _repo(repo_b.installation, 1010, "acme/web-old", is_enabled=False)
        _team(workspace, "Stale", default_repository=disabled)
        url = f"/api/workspaces/{workspace.slug}/projects/{project.id}/github/mappings/"

        (mapping,) = admin_client.get(url).data

        assert mapping["default_for_teams"] == []
        assert mapping["is_my_team_default"] is False

    @pytest.mark.django_db
    def test_hints_take_a_constant_number_of_queries(
        self, admin_client, workspace, project, repo_a, repo_b, mapping_a, mapping_b, create_user
    ):
        url = f"/api/workspaces/{workspace.slug}/projects/{project.id}/github/mappings/"
        _team(workspace, "Frontend", default_repository=repo_b, members=[create_user])

        def count_queries():
            with CaptureQueriesContext(connection) as ctx:
                assert admin_client.get(url).status_code == status.HTTP_200_OK
            return len(ctx)

        baseline = count_queries()
        for i in range(5):
            _team(workspace, f"Team {i}", default_repository=repo_a if i % 2 else repo_b)
        assert count_queries() == baseline
