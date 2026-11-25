# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Guests must only see ``id``/``member``/``role`` from the member endpoints (WEB-10019 / SEC-122).

The views pass ``fields=("id", "member", "role")`` to ``WorkSpaceMemberSerializer``
(``fields = "__all__"``); ``DynamicBaseSerializer`` used to ignore it.
"""

import pytest
from rest_framework.test import APIClient

from plane.db.models import Project, ProjectMember, Team, WorkspaceMember
from plane.tests.factories import UserFactory

ALLOWED = {"id", "member", "role"}
NON_GUEST_WORKSPACE_FIELDS = ALLOWED | {"is_active", "created_at"}
PROJECT_LIST_FIELDS = ALLOWED | {"original_role", "created_at"}
# Members/admins also get the read-only team id behind a membership ("via <team>" tag).
NON_GUEST_PROJECT_LIST_FIELDS = PROJECT_LIST_FIELDS | {"source_team"}


@pytest.fixture
def guest_client(workspace, create_user):
    guest = UserFactory(username="guest-user")
    WorkspaceMember.objects.create(workspace=workspace, member=guest, role=5, is_active=True)
    project = Project.objects.create(name="P", identifier="PRJ", workspace=workspace, created_by=create_user)
    ProjectMember.objects.create(workspace=workspace, project=project, member=guest, role=5, is_active=True)
    client = APIClient()
    client.force_authenticate(user=guest)
    client.project = project
    return client


@pytest.mark.contract
@pytest.mark.django_db
class TestGuestMemberFields:
    def test_workspace_member_list(self, guest_client, workspace):
        response = guest_client.get(f"/api/workspaces/{workspace.slug}/members/")

        assert response.status_code == 200
        assert response.data
        for row in response.data:
            assert set(row) == ALLOWED

    def test_workspace_member_retrieve(self, guest_client, workspace):
        member = WorkspaceMember.objects.filter(workspace=workspace, role=20).first()

        response = guest_client.get(f"/api/workspaces/{workspace.slug}/members/{member.id}/")

        assert response.status_code == 200
        assert set(response.data) == ALLOWED

    def test_project_member_list(self, guest_client, workspace):
        response = guest_client.get(f"/api/workspaces/{workspace.slug}/projects/{guest_client.project.id}/members/")

        assert response.status_code == 200
        assert response.data
        for row in response.data:
            assert set(row) == PROJECT_LIST_FIELDS


@pytest.mark.contract
@pytest.mark.django_db
class TestNonGuestMemberFields:
    """The web app reads these keys; the allowlists must not drop them for members/admins."""

    def test_workspace_member_list_keeps_is_active_and_created_at(self, session_client, workspace):
        response = session_client.get(f"/api/workspaces/{workspace.slug}/members/")

        assert response.status_code == 200
        assert response.data
        for row in response.data:
            assert set(row) == NON_GUEST_WORKSPACE_FIELDS

    def test_workspace_member_retrieve_keeps_is_active_and_created_at(self, session_client, workspace):
        member = WorkspaceMember.objects.filter(workspace=workspace, role=20).first()

        response = session_client.get(f"/api/workspaces/{workspace.slug}/members/{member.id}/")

        assert response.status_code == 200
        assert set(response.data) == NON_GUEST_WORKSPACE_FIELDS

    def test_project_member_list_keeps_original_role_and_created_at(self, session_client, workspace, create_user):
        project = Project.objects.create(name="P2", identifier="PR2", workspace=workspace, created_by=create_user)
        ProjectMember.objects.create(workspace=workspace, project=project, member=create_user, role=20, is_active=True)

        response = session_client.get(f"/api/workspaces/{workspace.slug}/projects/{project.id}/members/")

        assert response.status_code == 200
        assert response.data
        for row in response.data:
            assert set(row) == NON_GUEST_PROJECT_LIST_FIELDS


@pytest.mark.contract
@pytest.mark.django_db
class TestProjectMemberListSourceTeam:
    """``source_team`` is the team id that added the member (null = added individually), read-only."""

    @pytest.fixture
    def project_with_team_member(self, workspace, create_user):
        project = Project.objects.create(name="P3", identifier="PR3", workspace=workspace, created_by=create_user)
        ProjectMember.objects.create(workspace=workspace, project=project, member=create_user, role=20, is_active=True)
        team = Team.objects.create(workspace=workspace, name="Backend")
        via_team = UserFactory(username="via-team")
        WorkspaceMember.objects.create(workspace=workspace, member=via_team, role=15, is_active=True)
        ProjectMember.objects.create(
            workspace=workspace, project=project, member=via_team, role=15, is_active=True, source_team=team
        )
        return project, team, via_team

    def _by_member(self, response):
        return {str(row["member"]): row for row in response.data}

    def test_admin_sees_team_id_or_null(self, session_client, workspace, create_user, project_with_team_member):
        project, team, via_team = project_with_team_member

        response = session_client.get(f"/api/workspaces/{workspace.slug}/projects/{project.id}/members/")

        assert response.status_code == 200
        rows = self._by_member(response)
        assert str(rows[str(via_team.id)]["source_team"]) == str(team.id)
        assert rows[str(create_user.id)]["source_team"] is None

    def test_member_role_sees_team_id(self, workspace, project_with_team_member):
        project, team, via_team = project_with_team_member
        client = APIClient()
        client.force_authenticate(user=via_team)

        response = client.get(f"/api/workspaces/{workspace.slug}/projects/{project.id}/members/")

        assert response.status_code == 200
        assert str(self._by_member(response)[str(via_team.id)]["source_team"]) == str(team.id)

    def test_guest_does_not_see_source_team(self, workspace, project_with_team_member):
        project, _team, _via_team = project_with_team_member
        guest = UserFactory(username="guest-p3")
        WorkspaceMember.objects.create(workspace=workspace, member=guest, role=5, is_active=True)
        ProjectMember.objects.create(workspace=workspace, project=project, member=guest, role=5, is_active=True)
        client = APIClient()
        client.force_authenticate(user=guest)

        response = client.get(f"/api/workspaces/{workspace.slug}/projects/{project.id}/members/")

        assert response.status_code == 200
        assert response.data
        for row in response.data:
            assert "source_team" not in row

    def test_source_team_is_read_only_on_member_update(self, session_client, workspace, project_with_team_member):
        project, team, via_team = project_with_team_member
        row = ProjectMember.objects.get(project=project, member=via_team)

        response = session_client.patch(
            f"/api/workspaces/{workspace.slug}/projects/{project.id}/members/{row.id}/",
            {"role": 15, "source_team": None},
            format="json",
        )

        assert response.status_code == 200
        row.refresh_from_db()
        assert row.source_team_id == team.id
