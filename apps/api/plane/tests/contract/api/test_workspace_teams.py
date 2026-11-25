# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Contract tests for workspace teams and their repository per project.

GET/POST     /api/workspaces/<slug>/teams/
PATCH/DELETE /api/workspaces/<slug>/teams/<team_id>/
POST         /api/workspaces/<slug>/teams/<team_id>/members/
DELETE       /api/workspaces/<slug>/teams/<team_id>/members/<member_id>/
GET          /api/workspaces/<slug>/projects/<project_id>/github/team-repositories/
PUT          /api/workspaces/<slug>/projects/<project_id>/github/team-repositories/<team_id>/

plus the team repository in branch creation and the mapping list.
None of these tests contact GitHub.
"""

import importlib
import uuid
from unittest.mock import patch

import pytest
from django.apps import apps as django_apps
from django.db import IntegrityError, connection, transaction
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from plane.db.models import (
    Issue,
    IssueAssignee,
    Project,
    ProjectMember,
    ProjectMemberInvite,
    ProjectTeam,
    ProjectUserProperty,
    Team,
    TeamMember,
    User,
    Workspace,
    WorkspaceMember,
)
from plane.db.models.integration.github_app import GithubAppInstallation, GithubEnabledRepository
from plane.db.mixins import SoftDeletionQuerySet
from plane.db.models.integration.github_sync import ProjectTeamRepository, RepoProjectMapping
from plane.license.models import InstanceConfiguration
from plane.license.utils.encryption import encrypt_data
from plane.services.github.installations import soft_delete_installations
from plane.services.github.team_repo import pick_branch_mapping
from plane.services.teams.project_sync import locked_teams


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


def _team(workspace, name, members=()):
    team = Team.objects.create(workspace=workspace, name=name)
    for member in members:
        TeamMember.objects.create(workspace=workspace, team=team, member=member)
    return team


def _project(workspace, name, identifier, admin, member):
    p = Project.objects.create(name=name, identifier=identifier, workspace=workspace, created_by=admin)
    ProjectMember.objects.create(workspace=workspace, project=p, member=admin, role=20, is_active=True)
    ProjectMember.objects.create(workspace=workspace, project=p, member=member, role=15, is_active=True)
    return p


def _mapping(project, repo, is_default=False):
    return RepoProjectMapping.objects.create(
        project=project,
        repository=repo,
        github_installation_id=repo.installation.installation_id,
        github_repo=repo.full_name,
        base_branch="main",
        is_default=is_default,
    )


def _link(project, team):
    """Attach without the membership sync (the team repository tests do not need it)."""
    return ProjectTeam.objects.get_or_create(project=project, team=team)[0]


def _override(project, team, mapping):
    # A team repository needs the team attached to the project.
    _link(project, team)
    return ProjectTeamRepository.objects.create(project=project, team=team, mapping=mapping)


def _mappings_url(project):
    return f"/api/workspaces/{project.workspace.slug}/projects/{project.id}/github/mappings/"


def _team_repos_url(project):
    return f"/api/workspaces/{project.workspace.slug}/projects/{project.id}/github/team-repositories/"


def _team_repo_url(project, team_id):
    return f"{_team_repos_url(project)}{team_id}/"


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
    return _project(workspace, "Teams Project", "TMP", create_user, member_user)


@pytest.fixture
def project_y(db, workspace, create_user, member_user):
    return _project(workspace, "Project Y", "PRY", create_user, member_user)


@pytest.fixture
def issue(project, create_user):
    return Issue.objects.create(
        name="Teams Issue", project=project, workspace=project.workspace, created_by=create_user
    )


@pytest.fixture
def issue_y(project_y, create_user):
    return Issue.objects.create(
        name="Y Issue", project=project_y, workspace=project_y.workspace, created_by=create_user
    )


@pytest.fixture
def mapping_a(project, repo_a):
    # The project default.
    return _mapping(project, repo_a, is_default=True)


@pytest.fixture
def mapping_b(project, repo_b):
    return _mapping(project, repo_b)


@pytest.fixture
def frontend(workspace, create_user):
    return _team(workspace, "Frontend", members=[create_user])


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
    def test_list_is_ordered_by_name(self, admin_client, workspace, member_user):
        _team(workspace, "Zeta")
        _team(workspace, "Alpha", members=[member_user])

        resp = admin_client.get(_teams_url(workspace.slug))

        assert resp.status_code == status.HTTP_200_OK
        assert [team["name"] for team in resp.data] == ["Alpha", "Zeta"]
        alpha = resp.data[0]
        assert set(alpha) == {"id", "name", "description", "member_ids", "project_ids", "created_at"}
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
    def test_description_is_at_most_2000_characters(self, admin_client, workspace):
        resp = admin_client.post(_teams_url(workspace.slug), {"name": "F", "description": "x" * 2001}, format="json")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert "description" in resp.data
        team = _team(workspace, "Frontend")
        resp = admin_client.patch(_team_url(workspace.slug, team.id), {"description": "x" * 2001}, format="json")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        resp = admin_client.patch(_team_url(workspace.slug, team.id), {"description": "x" * 2000}, format="json")
        assert resp.status_code == status.HTTP_200_OK

    @pytest.mark.django_db
    def test_patch_writes_only_the_fields_sent(self, admin_client, workspace):
        team = _team(workspace, "Frontend")

        with CaptureQueriesContext(connection) as ctx:
            resp = admin_client.patch(_team_url(workspace.slug, team.id), {"name": "Web"}, format="json")

        assert resp.status_code == status.HTTP_200_OK, resp.data
        (update,) = [q["sql"] for q in ctx.captured_queries if q["sql"].startswith('UPDATE "teams"')]
        assert '"name"' in update
        assert '"description"' not in update

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
    def test_team_has_no_workspace_wide_repository(self, admin_client, workspace, repo_b):
        # The repository is chosen per project now; the old field is ignored.
        resp = admin_client.post(
            _teams_url(workspace.slug), {"name": "Frontend", "default_repository_id": str(repo_b.id)}, format="json"
        )
        assert resp.status_code == status.HTTP_201_CREATED, resp.data
        assert "default_repository" not in resp.data
        resp = admin_client.patch(
            _team_url(workspace.slug, resp.data["id"]), {"default_repository_id": str(repo_b.id)}, format="json"
        )
        assert resp.status_code == status.HTTP_200_OK, resp.data
        assert "default_repository" not in resp.data
        assert not hasattr(Team, "default_repository")


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
    def test_deleting_a_team_hard_deletes_its_memberships_and_project_repositories(
        self, admin_client, workspace, member_user, project, project_y, repo_a, repo_b
    ):
        team = _team(workspace, "Frontend", members=[member_user])
        other = _team(workspace, "Backend")
        _override(project, team, _mapping(project, repo_b))
        _override(project_y, team, _mapping(project_y, repo_a))
        kept = _override(project_y, other, RepoProjectMapping.objects.get(project=project_y))

        with patch("plane.db.mixins.soft_delete_related_objects") as cascade:
            assert admin_client.delete(_team_url(workspace.slug, team.id)).status_code == 204

        # No soft-delete cascade: it would only re-touch the hard-deleted rows.
        cascade.delay.assert_not_called()
        assert Team.all_objects.get(pk=team.pk).deleted_at is not None
        assert not TeamMember.all_objects.filter(team=team).exists()
        assert not ProjectTeamRepository.all_objects.filter(team=team).exists()
        assert list(ProjectTeamRepository.all_objects.values_list("id", flat=True)) == [kept.id]
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
# Team repositories per project: GET list / PUT one team
# ============================================================================


@pytest.mark.contract
class TestProjectTeamRepositoryApi:
    @pytest.mark.django_db
    def test_list_returns_every_attached_team_with_its_repository_in_this_project(
        self, admin_client, workspace, project, project_y, repo_a, repo_b, mapping_a, mapping_b, create_user
    ):
        left = _user("left@plane.so")
        WorkspaceMember.objects.create(workspace=workspace, member=left, role=15, is_active=False)
        frontend = _team(workspace, "Frontend", members=[create_user, left])
        backend = _team(workspace, "Backend")
        gone = _team(workspace, "Gone")
        _link(project, gone)
        Team.objects.filter(pk=gone.pk).update(deleted_at=timezone.now())
        _team(workspace, "Not attached")
        _override(project, frontend, mapping_b)
        _link(project, backend)
        _override(project_y, backend, _mapping(project_y, repo_a, is_default=True))

        resp = admin_client.get(_team_repos_url(project))

        assert resp.status_code == status.HTTP_200_OK
        # Members who left the workspace are not counted; Backend's override is in another project.
        assert resp.data == [
            {"team": {"id": str(backend.id), "name": "Backend", "member_count": 0}, "mapping_id": None},
            {"team": {"id": str(frontend.id), "name": "Frontend", "member_count": 1}, "mapping_id": str(mapping_b.id)},
        ]

    @pytest.mark.django_db
    def test_list_takes_a_constant_number_of_queries(self, admin_client, workspace, project, mapping_a, mapping_b):
        _override(project, _team(workspace, "Frontend", members=[_user("f@plane.so")]), mapping_b)

        def count_queries():
            with CaptureQueriesContext(connection) as ctx:
                assert admin_client.get(_team_repos_url(project)).status_code == status.HTTP_200_OK
            return len(ctx)

        baseline = count_queries()
        for i in range(4):
            team = _team(workspace, f"Team {i}", members=[_user(f"m{i}@plane.so")])
            _override(project, team, mapping_a if i % 2 else mapping_b)
        assert count_queries() == baseline

    @pytest.mark.django_db
    def test_admin_sets_changes_and_clears_a_team_repository(
        self, admin_client, project, mapping_a, mapping_b, frontend
    ):
        _link(project, frontend)
        url = _team_repo_url(project, frontend.id)

        resp = admin_client.put(url, {"mapping_id": str(mapping_b.id)}, format="json")
        assert resp.status_code == status.HTTP_200_OK, resp.data
        assert resp.data == {
            "team": {"id": str(frontend.id), "name": "Frontend", "member_count": 1},
            "mapping_id": str(mapping_b.id),
        }
        row_id = ProjectTeamRepository.objects.get(project=project, team=frontend).id

        resp = admin_client.put(url, {"mapping_id": str(mapping_a.id)}, format="json")
        assert resp.status_code == status.HTTP_200_OK, resp.data
        assert resp.data["mapping_id"] == str(mapping_a.id)
        assert list(ProjectTeamRepository.all_objects.values_list("id", "mapping_id")) == [(row_id, mapping_a.id)]

        for _ in range(2):
            resp = admin_client.put(url, {"mapping_id": None}, format="json")
            assert resp.status_code == status.HTTP_200_OK, resp.data
            assert resp.data["mapping_id"] is None
            assert not ProjectTeamRepository.all_objects.exists()

    @pytest.mark.django_db
    def test_mapping_must_be_a_live_mapping_of_this_project(
        self,
        admin_client,
        workspace,
        project,
        project_y,
        repo_a,
        repo_c,
        mapping_b,
        other_workspace,
        other_installation,
        create_user,
        frontend,
    ):
        _override(project, frontend, mapping_b)
        other_project_mapping = _mapping(project_y, repo_c, is_default=True)
        foreign_project = Project.objects.create(
            name="Foreign", identifier="FRN", workspace=other_workspace, created_by=create_user
        )
        foreign_mapping = _mapping(foreign_project, _repo(other_installation, 2001, "other/web"), is_default=True)
        removed = _mapping(project, repo_a)
        RepoProjectMapping.objects.filter(pk=removed.pk).update(deleted_at=timezone.now())
        url = _team_repo_url(project, frontend.id)

        for mapping_id in (other_project_mapping.id, foreign_mapping.id, removed.id, uuid.uuid4()):
            resp = admin_client.put(url, {"mapping_id": str(mapping_id)}, format="json")
            assert resp.status_code == status.HTTP_400_BAD_REQUEST, mapping_id
            assert "mapping_id" in resp.data
        for body in ({}, {"mapping_id": "not-a-uuid"}):
            assert admin_client.put(url, body, format="json").status_code == status.HTTP_400_BAD_REQUEST, body

        # Nothing was written: the existing override is untouched.
        assert list(ProjectTeamRepository.all_objects.values_list("team_id", "mapping_id")) == [
            (frontend.id, mapping_b.id)
        ]

    @pytest.mark.django_db
    def test_unknown_deleted_or_foreign_team_is_404(self, admin_client, workspace, other_workspace, project, mapping_b):
        foreign = _team(other_workspace, "Foreign")
        gone = _team(workspace, "Gone")
        Team.objects.filter(pk=gone.pk).update(deleted_at=timezone.now())

        for team_id in (uuid.uuid4(), foreign.id, gone.id):
            resp = admin_client.put(_team_repo_url(project, team_id), {"mapping_id": str(mapping_b.id)}, format="json")
            assert resp.status_code == status.HTTP_404_NOT_FOUND, team_id
        assert not ProjectTeamRepository.all_objects.exists()

    @pytest.mark.django_db
    def test_members_read_and_only_admins_write(self, workspace, project, mapping_b, member_user, frontend):
        member = _client(member_user)
        assert member.get(_team_repos_url(project)).status_code == status.HTTP_200_OK
        resp = member.put(_team_repo_url(project, frontend.id), {"mapping_id": str(mapping_b.id)}, format="json")
        assert resp.status_code == status.HTTP_403_FORBIDDEN
        assert not ProjectTeamRepository.all_objects.exists()

        guest = _user("project-guest@plane.so")
        WorkspaceMember.objects.create(workspace=workspace, member=guest, role=15)
        ProjectMember.objects.create(workspace=workspace, project=project, member=guest, role=5, is_active=True)
        outsider = _user("outsider@plane.so")
        for user in (guest, outsider):
            assert _client(user).get(_team_repos_url(project)).status_code == status.HTTP_403_FORBIDDEN
            resp = _client(user).put(
                _team_repo_url(project, frontend.id), {"mapping_id": str(mapping_b.id)}, format="json"
            )
            assert resp.status_code == status.HTTP_403_FORBIDDEN
        assert not ProjectTeamRepository.all_objects.exists()

    @pytest.mark.django_db
    def test_teams_of_other_workspaces_are_not_listed(
        self, admin_client, other_workspace, other_installation, project, mapping_b, create_user, frontend
    ):
        foreign = _team(other_workspace, "Foreign")
        foreign_project = Project.objects.create(
            name="Foreign", identifier="FRN", workspace=other_workspace, created_by=create_user
        )
        _override(foreign_project, foreign, _mapping(foreign_project, _repo(other_installation, 2001, "acme/web")))
        _link(project, frontend)

        resp = admin_client.get(_team_repos_url(project))

        assert [row["team"]["name"] for row in resp.data] == ["Frontend"]

    @pytest.mark.django_db
    def test_only_attached_teams_have_a_repository(self, admin_client, workspace, project, mapping_b, frontend):
        url = _team_repo_url(project, frontend.id)
        assert admin_client.get(_team_repos_url(project)).data == []
        for mapping_id in (str(mapping_b.id), None):
            resp = admin_client.put(url, {"mapping_id": mapping_id}, format="json")
            assert resp.status_code == status.HTTP_400_BAD_REQUEST, mapping_id
            assert resp.data == {"team_id": ["Attach the team to this project first."]}
        assert not ProjectTeamRepository.all_objects.exists()

        _attach(admin_client, project, frontend)

        assert [row["team"]["name"] for row in admin_client.get(_team_repos_url(project)).data] == ["Frontend"]
        assert admin_client.put(url, {"mapping_id": str(mapping_b.id)}, format="json").status_code == 200

    @pytest.mark.django_db
    def test_db_allows_one_live_repository_per_project_team(self, project, mapping_a, mapping_b, frontend):
        _override(project, frontend, mapping_a)
        with pytest.raises(IntegrityError), transaction.atomic():
            _override(project, frontend, mapping_b)


# ============================================================================
# Branch creation: the team repository of the project before the project default
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
class TestBranchUsesTeamRepository:
    @pytest.fixture(autouse=True)
    def _setup(self, github_app, mapping_a, mapping_b):
        pass

    @pytest.mark.django_db
    def test_same_team_uses_a_different_repository_per_project(
        self, admin_client, project, project_y, issue, issue_y, repo_a, repo_c, mapping_b, frontend
    ):
        _mapping(project_y, repo_a, is_default=True)
        _override(project, frontend, mapping_b)
        _override(project_y, frontend, _mapping(project_y, repo_c))

        assert _create_branch(admin_client, project, issue) == "acme/web"
        assert _create_branch(admin_client, project_y, issue_y) == "acme/docs"
        # An explicit repository still wins.
        assert _create_branch(admin_client, project, issue, repo="acme/api") == "acme/api"
        assert _create_branch(admin_client, project_y, issue_y, repo="acme/api") == "acme/api"

    @pytest.mark.django_db
    def test_user_without_a_team_gets_the_project_default(self, admin_client, workspace, project, issue, mapping_b):
        _override(project, _team(workspace, "Frontend"), mapping_b)
        assert _create_branch(admin_client, project, issue) == "acme/api"

    @pytest.mark.django_db
    def test_team_without_a_repository_in_this_project_gets_the_project_default(
        self, admin_client, project, project_y, issue, repo_c, frontend
    ):
        _override(project_y, frontend, _mapping(project_y, repo_c, is_default=True))
        assert _create_branch(admin_client, project, issue) == "acme/api"

    @pytest.mark.django_db
    @pytest.mark.parametrize("break_it", ["delete_team", "remove_member", "remove_mapping", "clear_override"])
    def test_falls_back_to_the_project_default(
        self, break_it, admin_client, workspace, project, issue, mapping_b, create_user, frontend
    ):
        _override(project, frontend, mapping_b)
        assert _create_branch(admin_client, project, issue) == "acme/web"

        if break_it == "delete_team":
            assert admin_client.delete(_team_url(workspace.slug, frontend.id)).status_code == 204
        elif break_it == "remove_member":
            assert admin_client.delete(_member_url(workspace.slug, frontend.id, create_user.id)).status_code == 204
        elif break_it == "remove_mapping":
            assert admin_client.delete(f"{_mappings_url(project)}{mapping_b.id}/").status_code == 204
        else:
            resp = admin_client.put(_team_repo_url(project, frontend.id), {"mapping_id": None}, format="json")
            assert resp.status_code == 200

        assert _create_branch(admin_client, project, issue) == "acme/api"
        if break_it != "remove_member":
            assert ProjectTeamRepository.all_objects.count() == 0

    @pytest.mark.django_db
    def test_removing_a_mapping_keeps_other_projects_and_mappings(
        self, admin_client, workspace, project, project_y, repo_b, mapping_a, mapping_b, frontend
    ):
        backend = _team(workspace, "Backend")
        _override(project, frontend, mapping_b)
        kept = [_override(project, backend, mapping_a), _override(project_y, frontend, _mapping(project_y, repo_b))]

        assert admin_client.delete(f"{_mappings_url(project)}{mapping_b.id}/").status_code == 204

        assert set(ProjectTeamRepository.all_objects.values_list("id", flat=True)) == {row.id for row in kept}

    @pytest.mark.django_db
    def test_disconnecting_github_removes_the_team_repositories(
        self, admin_client, workspace, project, issue, installation, mapping_b, frontend
    ):
        _override(project, frontend, mapping_b)
        soft_delete_installations([installation])
        assert not ProjectTeamRepository.all_objects.exists()

        # Reconnected: the mappings are revived (as the create endpoint does);
        # the team repository is not.
        reconnected = GithubAppInstallation.objects.create(
            workspace=workspace, installation_id=77770001, account_login="acme", account_type="Organization"
        )
        for mapping in RepoProjectMapping.all_objects.filter(project=project):
            mapping.repository = _repo(reconnected, mapping.repository.github_repository_id, mapping.github_repo)
            mapping.deleted_at = None
            mapping.save()

        assert _create_branch(admin_client, project, issue) == "acme/api"
        mappings = admin_client.get(_mappings_url(project)).data
        assert [(m["is_my_team_default"], m["default_for_teams"]) for m in mappings] == [(False, [])] * 2

    @pytest.mark.django_db
    def test_override_left_on_a_removed_mapping_or_team_is_ignored(
        self, workspace, project, mapping_a, mapping_b, create_user, frontend
    ):
        # A cleanup path that missed the row must still fall back.
        _override(project, frontend, mapping_b)
        RepoProjectMapping.objects.filter(pk=mapping_b.pk).update(deleted_at=timezone.now())
        assert pick_branch_mapping(workspace.slug, project.id, create_user) == mapping_a

        RepoProjectMapping.all_objects.filter(pk=mapping_b.pk).update(deleted_at=None)
        assert pick_branch_mapping(workspace.slug, project.id, create_user) == mapping_b
        Team.objects.filter(pk=frontend.pk).update(deleted_at=timezone.now())
        assert pick_branch_mapping(workspace.slug, project.id, create_user) == mapping_a

    @pytest.mark.django_db
    def test_detaching_the_team_drops_its_repository(self, admin_client, project, issue, mapping_b, frontend):
        _override(project, frontend, mapping_b)
        assert _create_branch(admin_client, project, issue) == "acme/web"

        assert admin_client.delete(_project_team_url(project, frontend.id)).status_code == 200

        assert _create_branch(admin_client, project, issue) == "acme/api"
        assert not ProjectTeamRepository.all_objects.exists()

    @pytest.mark.django_db
    def test_override_of_a_team_not_attached_is_ignored(self, workspace, project, mapping_a, mapping_b, frontend):
        # A cleanup path that missed the row must still fall back.
        ProjectTeamRepository.objects.create(project=project, team=frontend, mapping=mapping_b)
        assert pick_branch_mapping(workspace.slug, project.id, frontend.team_members.get().member) == mapping_a

    @pytest.mark.django_db
    def test_override_on_a_legacy_mapping_works(self, admin_client, project, issue, mapping_b, frontend):
        # Legacy mappings have no enabled-repository FK; the override points at the mapping itself.
        RepoProjectMapping.objects.filter(pk=mapping_b.pk).update(repository=None, github_repo="ACME/Web")
        _override(project, frontend, mapping_b)
        assert _create_branch(admin_client, project, issue) == "ACME/Web"
        assert [m["is_my_team_default"] for m in admin_client.get(_mappings_url(project)).data] == [False, True]

    @pytest.mark.django_db
    @pytest.mark.parametrize(
        "row, field",
        [
            ("repository", "is_enabled"),
            ("repository", "deleted_at"),
            ("installation", "is_active"),
            ("installation", "deleted_at"),
        ],
    )
    def test_override_on_an_unusable_repository_falls_back(
        self, row, field, admin_client, project, issue, repo_b, mapping_b, frontend
    ):
        # Disabled on GitHub or its installation gone: the project default is used.
        _override(project, frontend, mapping_b)
        target = repo_b if row == "repository" else repo_b.installation
        rows = type(target).all_objects.filter(pk=target.pk)
        unusable, usable = (timezone.now(), None) if field == "deleted_at" else (False, True)

        def my_team_repos():
            return [m["github_repo"] for m in admin_client.get(_mappings_url(project)).data if m["is_my_team_default"]]

        rows.update(**{field: unusable})
        assert _create_branch(admin_client, project, issue) == "acme/api"
        assert my_team_repos() == []
        # Admins still see the saved choice.
        assert admin_client.get(_team_repos_url(project)).data[0]["mapping_id"] == str(mapping_b.id)

        rows.update(**{field: usable})
        assert _create_branch(admin_client, project, issue) == "acme/web"
        assert my_team_repos() == ["acme/web"]

    @pytest.mark.django_db
    def test_inactive_workspace_member_has_no_team_repository(
        self, workspace, project, mapping_a, mapping_b, member_user
    ):
        _override(project, _team(workspace, "Frontend", members=[member_user]), mapping_b)
        assert pick_branch_mapping(workspace.slug, project.id, member_user) == mapping_b

        WorkspaceMember.objects.filter(workspace=workspace, member=member_user).update(is_active=False)
        assert pick_branch_mapping(workspace.slug, project.id, member_user) == mapping_a


# ============================================================================
# Mapping list: team repository hints, per project
# ============================================================================


@pytest.mark.contract
class TestMappingListTeamHints:
    @pytest.mark.django_db
    def test_hints_mark_the_users_team_repository_of_this_project(
        self,
        admin_client,
        workspace,
        project,
        project_y,
        repo_a,
        repo_c,
        mapping_a,
        mapping_b,
        member_user,
        frontend,
    ):
        backend = _team(workspace, "Backend")
        web2 = _team(workspace, "Web 2")
        _team(workspace, "No Repo")
        _override(project, frontend, mapping_b)
        _override(project, backend, mapping_a)
        _override(project, web2, mapping_b)
        _mapping(project_y, repo_a, is_default=True)
        _override(project_y, frontend, _mapping(project_y, repo_c))

        data = {m["github_repo"]: m for m in admin_client.get(_mappings_url(project)).data}

        assert data["acme/web"]["is_my_team_default"] is True
        assert data["acme/api"]["is_my_team_default"] is False
        assert data["acme/web"]["default_for_teams"] == [
            {"id": str(frontend.id), "name": "Frontend"},
            {"id": str(web2.id), "name": "Web 2"},
        ]
        assert data["acme/api"]["default_for_teams"] == [{"id": str(backend.id), "name": "Backend"}]
        # Existing fields are untouched.
        assert data["acme/api"]["is_default"] is True
        assert data["acme/web"]["repository_detail"]["id"] == mapping_b.repository_id

        # The same team uses another repository in project Y.
        data_y = {m["github_repo"]: m for m in admin_client.get(_mappings_url(project_y)).data}
        assert data_y["acme/docs"]["is_my_team_default"] is True
        assert data_y["acme/docs"]["default_for_teams"] == [{"id": str(frontend.id), "name": "Frontend"}]
        assert data_y["acme/api"]["is_my_team_default"] is False
        assert data_y["acme/api"]["default_for_teams"] == []

        # A member without a team sees the hints but no "my team" repository.
        member_data = _client(member_user).get(_mappings_url(project)).data
        assert [m["is_my_team_default"] for m in member_data] == [False, False]

    @pytest.mark.django_db
    def test_hints_ignore_teams_of_other_workspaces(
        self, admin_client, other_workspace, other_installation, project, mapping_b, create_user
    ):
        foreign = _team(other_workspace, "Foreign", members=[create_user])
        foreign_project = Project.objects.create(
            name="Foreign", identifier="FRN", workspace=other_workspace, created_by=create_user
        )
        _override(foreign_project, foreign, _mapping(foreign_project, _repo(other_installation, 3001, "acme/web")))

        (mapping,) = admin_client.get(_mappings_url(project)).data

        assert mapping["default_for_teams"] == []
        assert mapping["is_my_team_default"] is False

    @pytest.mark.django_db
    def test_hints_take_a_constant_number_of_queries(
        self, admin_client, workspace, project, mapping_a, mapping_b, frontend
    ):
        _override(project, frontend, mapping_b)

        def count_queries():
            with CaptureQueriesContext(connection) as ctx:
                assert admin_client.get(_mappings_url(project)).status_code == status.HTTP_200_OK
            return len(ctx)

        baseline = count_queries()
        for i in range(5):
            _override(project, _team(workspace, f"Team {i}"), mapping_a if i % 2 else mapping_b)
        assert count_queries() == baseline


# ============================================================================
# Project teams: the link, the leader and the membership source
# ============================================================================


def _migration_0133():
    return importlib.import_module("plane.db.migrations.0133_project_team_leader_member_source")


@pytest.mark.contract
class TestProjectTeamSchema:
    @pytest.mark.django_db
    def test_db_allows_one_live_link_per_project_team(self, project, frontend):
        ProjectTeam.objects.create(project=project, team=frontend)
        with pytest.raises(IntegrityError), transaction.atomic():
            ProjectTeam.objects.create(project=project, team=frontend)

    @pytest.mark.django_db
    def test_backfill_links_the_teams_that_have_a_repository_in_a_project(
        self, workspace, project, project_y, mapping_a, mapping_b, repo_c, frontend
    ):
        backend = _team(workspace, "Backend")
        gone = _team(workspace, "Gone")
        stale = _team(workspace, "Stale")
        mapping_y = _mapping(project_y, repo_c, is_default=True)
        for proj, team, mapping in [
            (project, frontend, mapping_b),
            (project_y, frontend, mapping_y),
            (project, backend, mapping_a),
            (project, gone, mapping_a),
            (project, stale, mapping_a),
        ]:
            ProjectTeamRepository.objects.create(project=proj, team=team, mapping=mapping)
        Team.objects.filter(pk=gone.pk).update(deleted_at=timezone.now())
        ProjectTeamRepository.objects.filter(team=stale).update(deleted_at=timezone.now())
        existing = ProjectTeam.objects.create(project=project, team=backend)

        _migration_0133().backfill_project_teams(django_apps, None)
        _migration_0133().backfill_project_teams(django_apps, None)

        links = ProjectTeam.all_objects.values_list("project_id", "team_id", "workspace_id")
        assert sorted(links) == sorted(
            [
                (project.id, frontend.id, workspace.id),
                (project_y.id, frontend.id, workspace.id),
                (project.id, backend.id, workspace.id),
            ]
        )
        assert ProjectTeam.objects.get(project=project, team=backend).id == existing.id
        # No membership changes.
        assert not ProjectMember.objects.filter(source_team__isnull=False).exists()


def _project_teams_url(project):
    return f"/api/workspaces/{project.workspace.slug}/projects/{project.id}/teams/"


def _project_team_url(project, team_id):
    return f"{_project_teams_url(project)}{team_id}/"


def _ws_user(workspace, email, role=15):
    user = _user(email)
    WorkspaceMember.objects.create(workspace=workspace, member=user, role=role)
    return user


def _attach(client, project, team):
    resp = client.post(_project_teams_url(project), {"team_id": str(team.id)}, format="json")
    assert resp.status_code in (200, 201), resp.data
    return resp


def _membership(project, user):
    """(is_active, role, source_team_id) of the user's live project membership, or None."""
    return (
        ProjectMember.objects.filter(project=project, member=user)
        .values_list("is_active", "role", "source_team_id")
        .first()
    )


def _ids(*users):
    return sorted(str(user.id) for user in users)


@pytest.mark.contract
class TestAttachTeam:
    @pytest.mark.django_db
    def test_members_join_with_their_workspace_role(
        self, admin_client, workspace, project, create_user, django_capture_on_commit_callbacks
    ):
        dev = _ws_user(workspace, "dev@plane.so", role=15)
        guest = _ws_user(workspace, "ws-guest@plane.so", role=5)
        boss = _ws_user(workspace, "boss@plane.so", role=20)
        squad = _team(workspace, "Squad", members=[dev, guest, boss])

        with (
            patch("plane.services.teams.project_sync.project_add_user_email") as email,
            django_capture_on_commit_callbacks(execute=True),
        ):
            resp = _attach(admin_client, project, squad)

        assert resp.status_code == status.HTTP_201_CREATED
        link = ProjectTeam.objects.get(project=project, team=squad)
        assert resp.data == {
            "id": str(link.id),
            "team": {"id": str(squad.id), "name": "Squad", "member_ids": resp.data["team"]["member_ids"]},
            "leader_id": None,
            "created_at": resp.data["created_at"],
            "added_member_ids": _ids(dev, guest, boss),
        }
        assert sorted(resp.data["team"]["member_ids"]) == _ids(dev, guest, boss)
        assert _membership(project, dev) == (True, 15, squad.id)
        assert _membership(project, guest) == (True, 5, squad.id)
        assert _membership(project, boss) == (True, 20, squad.id)
        assert ProjectUserProperty.objects.filter(project=project, user__in=[dev, guest, boss]).count() == 3
        # Plane's "added to project" email, once per new member, after commit.
        assert [call.args[2] for call in email.delay.call_args_list] == [create_user.id] * 3
        added_rows = {str(call.args[1]) for call in email.delay.call_args_list}
        assert added_rows == {
            str(pk)
            for pk in ProjectMember.objects.filter(project=project, source_team=squad).values_list("id", flat=True)
        }

    @pytest.mark.django_db
    def test_attaching_again_is_200_and_changes_nothing(self, admin_client, workspace, project):
        dev = _ws_user(workspace, "dev@plane.so")
        squad = _team(workspace, "Squad", members=[dev])
        _attach(admin_client, project, squad)

        resp = _attach(admin_client, project, squad)

        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["added_member_ids"] == []
        assert ProjectTeam.all_objects.filter(project=project, team=squad).count() == 1
        assert ProjectMember.all_objects.filter(project=project, member=dev).count() == 1
        assert ProjectUserProperty.all_objects.filter(project=project, user=dev).count() == 1

    @pytest.mark.django_db
    def test_existing_members_keep_their_role_and_stay_individual(
        self, admin_client, workspace, project, create_user, member_user
    ):
        project_guest = _ws_user(workspace, "pguest@plane.so", role=15)
        ProjectMember.objects.create(workspace=workspace, project=project, member=project_guest, role=5)
        squad = _team(workspace, "Squad", members=[create_user, member_user, project_guest])

        resp = _attach(admin_client, project, squad)

        assert resp.data["added_member_ids"] == []
        assert _membership(project, create_user) == (True, 20, None)
        assert _membership(project, member_user) == (True, 15, None)
        assert _membership(project, project_guest) == (True, 5, None)

    @pytest.mark.django_db
    def test_a_removed_member_is_reactivated_from_the_team(self, admin_client, workspace, project):
        dev = _ws_user(workspace, "dev@plane.so")
        ProjectMember.objects.create(workspace=workspace, project=project, member=dev, role=5, is_active=False)
        squad = _team(workspace, "Squad", members=[dev])

        resp = _attach(admin_client, project, squad)

        assert resp.data["added_member_ids"] == _ids(dev)
        assert _membership(project, dev) == (True, 15, squad.id)
        assert ProjectMember.all_objects.filter(project=project, member=dev).count() == 1
        assert ProjectUserProperty.objects.filter(project=project, user=dev).exists()

    @pytest.mark.django_db
    def test_members_who_left_the_workspace_are_not_added(self, admin_client, workspace, project):
        left = _user("left@plane.so")
        WorkspaceMember.objects.create(workspace=workspace, member=left, role=15, is_active=False)
        squad = _team(workspace, "Squad", members=[left])

        resp = _attach(admin_client, project, squad)

        assert resp.data["added_member_ids"] == []
        assert resp.data["team"]["member_ids"] == []
        assert _membership(project, left) is None

    @pytest.mark.django_db
    def test_unknown_foreign_or_deleted_team_is_404_and_bad_body_is_400(
        self, admin_client, workspace, other_workspace, project
    ):
        foreign = _team(other_workspace, "Foreign")
        gone = _team(workspace, "Gone")
        Team.objects.filter(pk=gone.pk).update(deleted_at=timezone.now())
        url = _project_teams_url(project)

        for team_id in (uuid.uuid4(), foreign.id, gone.id):
            assert admin_client.post(url, {"team_id": str(team_id)}, format="json").status_code == 404, team_id
        for body in ({}, {"team_id": "nope"}, {"team_id": None}):
            assert admin_client.post(url, body, format="json").status_code == 400, body
        assert not ProjectTeam.all_objects.exists()

    @pytest.mark.django_db
    def test_attach_takes_a_bounded_number_of_queries(
        self, admin_client, workspace, project, django_assert_max_num_queries
    ):
        squad = _team(workspace, "Squad", members=[_ws_user(workspace, f"dev{i}@plane.so") for i in range(10)])

        with django_assert_max_num_queries(20):
            resp = _attach(admin_client, project, squad)

        assert len(resp.data["added_member_ids"]) == 10


@pytest.mark.contract
class TestDetachTeam:
    @pytest.mark.django_db
    def test_only_team_sourced_members_are_removed(
        self, admin_client, workspace, project, project_y, member_user, mapping_a, mapping_b, repo_c, create_bot_user
    ):
        dev = _ws_user(workspace, "dev@plane.so")
        promoted = _ws_user(workspace, "promoted@plane.so")
        boss = _ws_user(workspace, "boss@plane.so", role=20)
        WorkspaceMember.objects.create(workspace=workspace, member=create_bot_user, role=15)
        squad = _team(workspace, "Squad", members=[dev, promoted, boss, member_user, create_bot_user])
        _attach(admin_client, project, squad)
        ProjectMember.objects.filter(project=project, member=promoted).update(role=20)
        _override(project, squad, mapping_b)
        kept_override = _override(project_y, squad, _mapping(project_y, repo_c, is_default=True))

        resp = admin_client.delete(_project_team_url(project, squad.id))

        assert resp.status_code == status.HTTP_200_OK, resp.data
        assert resp.data == {
            "removed_member_ids": _ids(dev),
            "kept_member_ids": _ids(promoted, boss, member_user, create_bot_user),
        }
        assert _membership(project, dev) == (False, 15, None)
        # Promoted to project admin, workspace admin, individually added, bot: kept as individual members.
        assert _membership(project, promoted) == (True, 20, None)
        assert _membership(project, boss) == (True, 20, None)
        assert _membership(project, member_user) == (True, 15, None)
        assert _membership(project, create_bot_user)[0] is True
        assert not ProjectTeam.all_objects.filter(project=project).exists()
        assert list(ProjectTeamRepository.all_objects.values_list("id", flat=True)) == [kept_override.id]

    @pytest.mark.django_db
    def test_assignments_of_a_removed_member_are_kept(self, admin_client, workspace, project, issue):
        dev = _ws_user(workspace, "dev@plane.so")
        squad = _team(workspace, "Squad", members=[dev])
        _attach(admin_client, project, squad)
        IssueAssignee.objects.create(issue=issue, assignee=dev, project=project, workspace=workspace)

        assert admin_client.delete(_project_team_url(project, squad.id)).data["removed_member_ids"] == _ids(dev)

        assert IssueAssignee.objects.filter(issue=issue, assignee=dev).exists()

    @pytest.mark.django_db
    def test_detaching_a_team_that_is_not_attached_is_404(self, admin_client, workspace, other_workspace, project):
        squad = _team(workspace, "Squad")
        foreign = _team(other_workspace, "Foreign")
        for team_id in (squad.id, foreign.id, uuid.uuid4()):
            assert admin_client.delete(_project_team_url(project, team_id)).status_code == 404, team_id

    @pytest.mark.django_db
    def test_other_projects_keep_the_team(self, admin_client, workspace, project, project_y):
        dev = _ws_user(workspace, "dev@plane.so")
        squad = _team(workspace, "Squad", members=[dev])
        _attach(admin_client, project, squad)
        _attach(admin_client, project_y, squad)

        admin_client.delete(_project_team_url(project, squad.id))

        assert _membership(project, dev) == (False, 15, None)
        assert _membership(project_y, dev) == (True, 15, squad.id)


@pytest.mark.contract
class TestListProjectTeams:
    @pytest.mark.django_db
    def test_list_is_ordered_by_team_name_and_hides_members_who_left(
        self, admin_client, workspace, project, project_y, create_user
    ):
        dev = _ws_user(workspace, "dev@plane.so")
        left = _ws_user(workspace, "left@plane.so")
        zeta = _team(workspace, "Zeta", members=[dev, left])
        alpha = _team(workspace, "Alpha", members=[create_user])
        _attach(admin_client, project, zeta)
        _attach(admin_client, project, alpha)
        _team(workspace, "Not attached")
        ProjectTeam.objects.filter(project=project, team=zeta).update(leader=left)
        WorkspaceMember.objects.filter(workspace=workspace, member=left).update(is_active=False)

        resp = admin_client.get(_project_teams_url(project))

        assert resp.status_code == status.HTTP_200_OK
        assert [(row["team"]["name"], row["team"]["member_ids"], row["leader_id"]) for row in resp.data] == [
            ("Alpha", _ids(create_user), None),
            ("Zeta", _ids(dev), None),
        ]
        assert set(resp.data[0]) == {"id", "team", "leader_id", "created_at"}
        assert admin_client.get(_project_teams_url(project_y)).data == []

    @pytest.mark.django_db
    def test_list_takes_a_constant_number_of_queries(self, admin_client, workspace, project):
        _attach(admin_client, project, _team(workspace, "Squad", members=[_ws_user(workspace, "dev@plane.so")]))

        def count_queries():
            with CaptureQueriesContext(connection) as ctx:
                assert admin_client.get(_project_teams_url(project)).status_code == status.HTTP_200_OK
            return len(ctx)

        baseline = count_queries()
        for i in range(4):
            team = _team(workspace, f"Team {i}", members=[_ws_user(workspace, f"m{i}@plane.so")])
            ProjectTeam.objects.create(project=project, team=team, leader=team.team_members.get().member)
        assert count_queries() == baseline


@pytest.mark.contract
class TestProjectTeamPermissions:
    @pytest.mark.django_db
    def test_project_member_reads_but_cannot_write(self, admin_client, workspace, project, member_user):
        squad = _team(workspace, "Squad", members=[member_user])
        other = _team(workspace, "Other")
        _attach(admin_client, project, squad)
        client = _client(member_user)

        assert client.get(_project_teams_url(project)).status_code == status.HTTP_200_OK
        forbidden = [
            client.post(_project_teams_url(project), {"team_id": str(other.id)}, format="json"),
            client.patch(_project_team_url(project, squad.id), {"leader_id": str(member_user.id)}, format="json"),
            client.delete(_project_team_url(project, squad.id)),
        ]
        assert [resp.status_code for resp in forbidden] == [403] * 3
        assert list(ProjectTeam.objects.values_list("team_id", "leader_id")) == [(squad.id, None)]

    @pytest.mark.django_db
    def test_guests_outsiders_and_non_member_workspace_admins_are_403(self, admin_client, workspace, project):
        squad = _team(workspace, "Squad")
        guest = _ws_user(workspace, "pguest@plane.so", role=15)
        ProjectMember.objects.create(workspace=workspace, project=project, member=guest, role=5)
        outsider = _user("outsider@plane.so")
        # Plane's rule: a workspace admin needs a project membership too.
        boss = _ws_user(workspace, "boss@plane.so", role=20)

        for user in (guest, outsider, boss):
            client = _client(user)
            responses = [
                client.get(_project_teams_url(project)),
                client.post(_project_teams_url(project), {"team_id": str(squad.id)}, format="json"),
            ]
            assert [resp.status_code for resp in responses] == [403, 403], user.email
        assert not ProjectTeam.all_objects.exists()


def _leader(project, team):
    return ProjectTeam.objects.values_list("leader_id", flat=True).get(project=project, team=team)


@pytest.mark.contract
class TestTeamMembershipSync:
    @pytest.mark.django_db
    def test_moving_a_member_follows_the_new_teams_projects(self, admin_client, workspace, project, project_y):
        dev = _ws_user(workspace, "dev@plane.so")
        t1 = _team(workspace, "T1", members=[dev])
        t2 = _team(workspace, "T2")
        nowhere = _team(workspace, "Nowhere")
        _attach(admin_client, project, t1)
        _attach(admin_client, project, t2)
        _attach(admin_client, project_y, t2)
        assert _membership(project, dev) == (True, 15, t1.id)

        resp = admin_client.post(_members_url(workspace.slug, t2.id), {"member_ids": [str(dev.id)]}, format="json")

        assert resp.status_code == status.HTTP_200_OK, resp.data
        assert _membership(project, dev) == (True, 15, t2.id)
        assert _membership(project_y, dev) == (True, 15, t2.id)

        admin_client.post(_members_url(workspace.slug, nowhere.id), {"member_ids": [str(dev.id)]}, format="json")

        assert _membership(project, dev) == (False, 15, None)
        assert _membership(project_y, dev) == (False, 15, None)

    @pytest.mark.django_db
    def test_a_new_member_joins_every_attached_project(self, admin_client, workspace, project, project_y):
        dev = _ws_user(workspace, "dev@plane.so")
        squad = _team(workspace, "Squad")
        _attach(admin_client, project, squad)

        admin_client.post(_members_url(workspace.slug, squad.id), {"member_ids": [str(dev.id)]}, format="json")

        assert _membership(project, dev) == (True, 15, squad.id)
        assert _membership(project_y, dev) is None

    @pytest.mark.django_db
    def test_a_removed_member_leaves_the_teams_projects(self, admin_client, workspace, project, project_y):
        dev = _ws_user(workspace, "dev@plane.so")
        promoted = _ws_user(workspace, "promoted@plane.so")
        squad = _team(workspace, "Squad", members=[dev, promoted])
        _attach(admin_client, project, squad)
        _attach(admin_client, project_y, squad)
        ProjectMember.objects.filter(project=project, member=promoted).update(role=20)

        for user in (dev, promoted):
            assert admin_client.delete(_member_url(workspace.slug, squad.id, user.id)).status_code == 204

        assert _membership(project, dev) == (False, 15, None)
        assert _membership(project_y, dev) == (False, 15, None)
        # A project admin stays, as an individual member.
        assert _membership(project, promoted) == (True, 20, None)
        assert _membership(project_y, promoted) == (False, 15, None)

    @pytest.mark.django_db
    def test_deleting_a_team_removes_its_members_from_its_projects(
        self, admin_client, workspace, project, project_y, member_user
    ):
        dev = _ws_user(workspace, "dev@plane.so")
        squad = _team(workspace, "Squad", members=[dev, member_user])
        _attach(admin_client, project, squad)
        _attach(admin_client, project_y, squad)

        assert admin_client.delete(_team_url(workspace.slug, squad.id)).status_code == 204

        assert _membership(project, dev) == (False, 15, None)
        assert _membership(project_y, dev) == (False, 15, None)
        assert _membership(project, member_user) == (True, 15, None)
        assert _membership(project_y, member_user) == (True, 15, None)
        assert not ProjectTeam.all_objects.filter(team=squad).exists()

    @pytest.mark.django_db
    def test_workspace_teams_list_their_projects(self, admin_client, workspace, project, project_y):
        squad = _team(workspace, "Squad")
        _team(workspace, "Idle")
        _attach(admin_client, project, squad)
        _attach(admin_client, project_y, squad)

        teams = {team["name"]: team for team in admin_client.get(_teams_url(workspace.slug)).data}

        assert sorted(teams["Squad"]["project_ids"]) == sorted([str(project.id), str(project_y.id)])
        assert teams["Idle"]["project_ids"] == []
        resp = admin_client.patch(_team_url(workspace.slug, squad.id), {"name": "Squad 2"}, format="json")
        assert sorted(resp.data["project_ids"]) == sorted([str(project.id), str(project_y.id)])


@pytest.mark.contract
class TestProjectTeamLeader:
    @pytest.fixture
    def squad(self, admin_client, workspace, project, project_y):
        team = _team(workspace, "Squad", members=[_ws_user(workspace, "a@plane.so"), _ws_user(workspace, "b@plane.so")])
        _attach(admin_client, project, team)
        _attach(admin_client, project_y, team)
        return team

    @staticmethod
    def _set(client, project, team, leader):
        return client.patch(
            _project_team_url(project, team.id), {"leader_id": str(leader.id) if leader else None}, format="json"
        )

    @pytest.mark.django_db
    def test_each_project_has_its_own_leader(self, admin_client, project, project_y, squad):
        a, b = User.objects.get(email="a@plane.so"), User.objects.get(email="b@plane.so")

        resp = self._set(admin_client, project, squad, a)
        assert resp.status_code == status.HTTP_200_OK, resp.data
        assert resp.data["leader_id"] == str(a.id)
        assert self._set(admin_client, project_y, squad, b).data["leader_id"] == str(b.id)

        assert admin_client.get(_project_teams_url(project)).data[0]["leader_id"] == str(a.id)
        assert admin_client.get(_project_teams_url(project_y)).data[0]["leader_id"] == str(b.id)

        resp = self._set(admin_client, project, squad, None)
        assert resp.status_code == status.HTTP_200_OK
        assert (_leader(project, squad), _leader(project_y, squad)) == (None, b.id)

    @pytest.mark.django_db
    def test_leader_must_be_a_member_of_the_team(
        self, admin_client, workspace, other_workspace, project, squad, member_user
    ):
        stranger = _user("stranger@plane.so")
        WorkspaceMember.objects.create(workspace=other_workspace, member=stranger, role=15)
        _team(other_workspace, "Foreign", members=[stranger])
        left = _ws_user(workspace, "left@plane.so")
        TeamMember.objects.create(workspace=workspace, team=squad, member=left)
        WorkspaceMember.objects.filter(workspace=workspace, member=left).update(is_active=False)

        for user in (member_user, stranger, left):
            resp = self._set(admin_client, project, squad, user)
            assert resp.status_code == status.HTTP_400_BAD_REQUEST, user.email
            assert "leader_id" in resp.data
        url = _project_team_url(project, squad.id)
        for body in ({}, {"leader_id": "nope"}):
            assert admin_client.patch(url, body, format="json").status_code == 400, body
        assert _leader(project, squad) is None

    @pytest.mark.django_db
    def test_team_not_attached_is_404(self, admin_client, workspace, other_workspace, project, create_user):
        idle = _team(workspace, "Idle", members=[create_user])
        foreign = _team(other_workspace, "Foreign", members=[create_user])
        for team in (idle, foreign):
            assert self._set(admin_client, project, team, create_user).status_code == 404, team.name

    @pytest.mark.django_db
    def test_leaving_the_team_clears_the_leader_of_its_projects(
        self, admin_client, workspace, project, project_y, squad
    ):
        a, b = User.objects.get(email="a@plane.so"), User.objects.get(email="b@plane.so")
        self._set(admin_client, project, squad, a)
        self._set(admin_client, project_y, squad, b)
        other = _team(workspace, "Other")
        _attach(admin_client, project, other)
        ProjectTeam.objects.filter(project=project, team=other).update(leader=a)

        assert admin_client.delete(_member_url(workspace.slug, squad.id, a.id)).status_code == 204
        assert (_leader(project, squad), _leader(project_y, squad)) == (None, b.id)
        # Only the team they left.
        assert _leader(project, other) == a.id

        admin_client.post(_members_url(workspace.slug, other.id), {"member_ids": [str(b.id)]}, format="json")
        assert _leader(project_y, squad) is None


def _plane_add_url(project):
    return f"/api/workspaces/{project.workspace.slug}/projects/{project.id}/members/"


@pytest.mark.contract
class TestIndividualAddClearsTheTeamSource:
    @pytest.fixture
    def dev(self, workspace):
        return _ws_user(workspace, "dev@plane.so")

    @pytest.fixture
    def squad(self, workspace, dev):
        return _team(workspace, "Squad", members=[dev])

    @pytest.mark.django_db
    def test_a_member_added_back_by_hand_survives_the_team(self, admin_client, project, dev, squad):
        _attach(admin_client, project, squad)
        admin_client.delete(_project_team_url(project, squad.id))
        assert _membership(project, dev) == (False, 15, None)

        resp = admin_client.post(
            _plane_add_url(project), {"members": [{"member_id": str(dev.id), "role": 15}]}, format="json"
        )
        assert resp.status_code == status.HTTP_201_CREATED, resp.data
        assert _membership(project, dev) == (True, 15, None)

        _attach(admin_client, project, squad)
        assert _membership(project, dev) == (True, 15, None)
        resp = admin_client.delete(_project_team_url(project, squad.id))
        assert resp.data == {"removed_member_ids": [], "kept_member_ids": _ids(dev)}
        assert _membership(project, dev) == (True, 15, None)

    @pytest.mark.django_db
    def test_a_team_member_added_by_hand_becomes_individual(self, admin_client, project, dev, squad):
        _attach(admin_client, project, squad)
        assert _membership(project, dev) == (True, 15, squad.id)

        admin_client.post(_plane_add_url(project), {"members": [{"member_id": str(dev.id), "role": 15}]}, format="json")

        assert _membership(project, dev) == (True, 15, None)
        admin_client.delete(_project_team_url(project, squad.id))
        assert _membership(project, dev) == (True, 15, None)

    @pytest.mark.django_db
    def test_joining_the_project_clears_the_source(self, workspace, project, dev, squad):
        # Removed by hand while the team was attached: inactive, source kept.
        ProjectMember.objects.create(
            workspace=workspace, project=project, member=dev, is_active=False, source_team=squad
        )

        resp = _client(dev).post(
            f"/api/users/me/workspaces/{workspace.slug}/projects/invitations/",
            {"project_ids": [str(project.id)]},
            format="json",
        )

        assert resp.status_code == status.HTTP_201_CREATED, resp.data
        assert _membership(project, dev) == (True, 15, None)

    @pytest.mark.django_db
    def test_accepting_an_invite_clears_the_source(self, workspace, project, dev, squad):
        ProjectMember.objects.create(
            workspace=workspace, project=project, member=dev, is_active=False, source_team=squad
        )
        invite = ProjectMemberInvite.objects.create(project=project, email=dev.email, token="t0k3n", role=15)

        resp = _client(dev).post(
            f"/api/workspaces/{workspace.slug}/projects/{project.id}/join/{invite.id}/",
            {"token": "t0k3n", "accepted": True},
            format="json",
        )

        assert resp.status_code == status.HTTP_200_OK, resp.data
        assert _membership(project, dev) == (True, 15, None)


@pytest.mark.contract
class TestSourceTeamGuards:
    @pytest.mark.django_db
    def test_the_member_patch_cannot_set_the_source(self, admin_client, project, member_user, frontend):
        row = ProjectMember.objects.get(project=project, member=member_user)

        resp = admin_client.patch(
            f"{_plane_add_url(project)}{row.id}/", {"source_team": str(frontend.id)}, format="json"
        )

        assert resp.status_code == status.HTTP_200_OK, resp.data
        assert _membership(project, member_user) == (True, 15, None)


@pytest.mark.contract
class TestSourceTeamGuards:
    @pytest.mark.django_db
    def test_the_member_patch_cannot_set_the_source(self, admin_client, project, member_user, frontend):
        row = ProjectMember.objects.get(project=project, member=member_user)

        resp = admin_client.patch(
            f"{_plane_add_url(project)}{row.id}/", {"source_team": str(frontend.id)}, format="json"
        )

        assert resp.status_code == status.HTTP_200_OK, resp.data
        assert _membership(project, member_user) == (True, 15, None)

    @pytest.mark.django_db
    def test_a_member_moved_to_an_unlocked_team_meanwhile_is_409(self, admin_client, workspace, project):
        dev = _ws_user(workspace, "dev@plane.so")
        _team(workspace, "T1", members=[dev])
        t2 = _team(workspace, "T2")
        t3 = _team(workspace, "T3")
        _attach(admin_client, project, t2)

        def moved_before_the_locks(slug):
            # A concurrent request moves dev from T1 to T3 after T1 was read.
            TeamMember.objects.filter(member=dev).update(team=t3)
            return locked_teams(slug)

        with patch("plane.app.views.workspace.team.locked_teams", moved_before_the_locks):
            resp = admin_client.post(_members_url(workspace.slug, t2.id), {"member_ids": [str(dev.id)]}, format="json")

        assert resp.status_code == status.HTTP_409_CONFLICT
        assert resp.data == {"member_ids": ["Team membership changed, try again."]}
        assert TeamMember.objects.get(member=dev).team_id == t3.id
        assert _membership(project, dev) is None
