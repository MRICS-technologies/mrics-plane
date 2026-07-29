# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.test import override_settings
from django.utils import timezone
from rest_framework import status

from plane.db.models import Issue, Project, ProjectMember, State, WorkItemWorklog
from plane.db.models.state import StateGroup


@pytest.fixture
def project(db, workspace, create_user):
    project = Project.objects.create(
        name="Auto State Contract Project",
        identifier="ASC",
        workspace=workspace,
        created_by=create_user,
    )
    ProjectMember.objects.create(project=project, member=create_user, role=20, is_active=True)
    return project


@pytest.fixture
def states(db, workspace, project):
    todo = State.objects.create(
        name="Todo",
        color="#60646C",
        sequence=10000,
        project=project,
        workspace=workspace,
        group=StateGroup.UNSTARTED.value,
        default=True,
    )
    started = State.objects.create(
        name="In Progress",
        color="#F59E0B",
        sequence=20000,
        project=project,
        workspace=workspace,
        group=StateGroup.STARTED.value,
    )
    done = State.objects.create(
        name="Done",
        color="#46A758",
        sequence=30000,
        project=project,
        workspace=workspace,
        group=StateGroup.COMPLETED.value,
    )
    return {"todo": todo, "started": started, "done": done}


@pytest.fixture
def issue(db, workspace, project, states, create_user):
    return Issue.objects.create(
        name="Auto state contract issue",
        workspace=workspace,
        project=project,
        state=states["started"],
        created_by=create_user,
    )


def state_duration_url(workspace, project, issue):
    return (
        f"/api/v1/workspaces/{workspace.slug}/projects/{project.id}/"
        f"work-items/{issue.id}/state-durations/"
    )


def app_state_duration_url(workspace, project, issue):
    return (
        f"/api/workspaces/{workspace.slug}/projects/{project.id}/"
        f"issues/{issue.id}/state-durations/"
    )


def worklog_detail_url(workspace, project, issue, worklog):
    return (
        f"/api/v1/workspaces/{workspace.slug}/projects/{project.id}/"
        f"work-items/{issue.id}/worklogs/{worklog.id}/"
    )


@pytest.mark.contract
class TestAutoStateDurationContract:
    @pytest.mark.django_db
    def test_todo_issue_has_zero_duration_and_no_sessions(
        self, api_key_client, workspace, project, issue, states
    ):
        issue.state = states["todo"]
        issue.save(update_fields=["state"])

        response = api_key_client.get(state_duration_url(workspace, project, issue))

        assert response.status_code == status.HTTP_200_OK
        assert response.data["completed_started_seconds"] == 0.0
        assert response.data["active_started_seconds"] == 0.0
        assert response.data["total_started_seconds"] == 0.0
        assert response.data["sessions"] == []

    @pytest.mark.django_db
    def test_app_route_rejects_unauthenticated_request(
        self, api_client, workspace, project, issue
    ):
        response = api_client.get(app_state_duration_url(workspace, project, issue))

        assert response.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)

    @pytest.mark.django_db
    def test_issue_view_reopens_tracking_for_a_second_progress_cycle(
        self, api_key_client, workspace, project, issue, states
    ):
        issue.state = states["todo"]
        issue.save(update_fields=["state"])
        issue_url = (
            f"/api/v1/workspaces/{workspace.slug}/projects/{project.id}/"
            f"work-items/{issue.id}/"
        )

        with (
            override_settings(APP_BASE_URL="http://testserver"),
            patch("plane.api.views.issue.issue_activity.delay"),
            patch("plane.api.views.issue.model_activity.delay"),
        ):
            for state_name in ("started", "done", "started"):
                response = api_key_client.patch(
                    issue_url, {"state": str(states[state_name].id)}, format="json"
                )
                assert response.status_code == status.HTTP_200_OK

        worklogs = WorkItemWorklog.objects.filter(
            issue=issue, source=WorkItemWorklog.Source.AUTO_STATE
        ).order_by("started_at")
        assert worklogs.count() == 2
        assert worklogs[0].stopped_at is not None
        assert worklogs[1].stopped_at is None

    @pytest.mark.django_db
    def test_summary_separates_completed_and_active_time(
        self, api_key_client, workspace, project, issue, create_user
    ):
        now = timezone.now()
        completed_started_at = now - timedelta(minutes=20)
        completed_stopped_at = now - timedelta(minutes=5)
        active_started_at = completed_stopped_at

        WorkItemWorklog.objects.create(
            workspace=workspace,
            project=project,
            issue=issue,
            logged_by=create_user,
            date=timezone.localdate(completed_stopped_at),
            duration=Decimal("0.2500"),
            source=WorkItemWorklog.Source.AUTO_STATE,
            started_at=completed_started_at,
            stopped_at=completed_stopped_at,
        )
        WorkItemWorklog.objects.create(
            workspace=workspace,
            project=project,
            issue=issue,
            logged_by=create_user,
            date=timezone.localdate(active_started_at),
            duration=Decimal("0.0001"),
            source=WorkItemWorklog.Source.AUTO_STATE,
            started_at=active_started_at,
            stopped_at=None,
        )

        with patch("plane.api.views.time_tracking.timezone.now", return_value=now):
            response = api_key_client.get(state_duration_url(workspace, project, issue))

        assert response.status_code == status.HTTP_200_OK
        assert response.data["completed_started_seconds"] == pytest.approx(900.0)
        assert response.data["active_started_seconds"] == pytest.approx(300.0)
        assert response.data["total_started_seconds"] == pytest.approx(1200.0)
        assert response.data["current_state"]["group"] == StateGroup.STARTED.value
        assert len(response.data["sessions"]) == 1
        assert response.data["sessions"][0]["source"] == WorkItemWorklog.Source.AUTO_STATE

    @pytest.mark.django_db
    def test_app_route_accepts_browser_session_auth(
        self, api_client, workspace, project, issue, create_user
    ):
        api_client.force_login(create_user)

        response = api_client.get(app_state_duration_url(workspace, project, issue))

        assert response.status_code == status.HTTP_200_OK
        assert response.data["issue"] == str(issue.id)

    @pytest.mark.django_db
    def test_auto_state_worklog_cannot_be_edited(
        self, api_key_client, workspace, project, issue, create_user
    ):
        now = timezone.now()
        worklog = WorkItemWorklog.objects.create(
            workspace=workspace,
            project=project,
            issue=issue,
            logged_by=create_user,
            date=timezone.localdate(now),
            duration=Decimal("0.2500"),
            source=WorkItemWorklog.Source.AUTO_STATE,
            started_at=now - timedelta(minutes=15),
            stopped_at=now,
        )

        response = api_key_client.patch(
            worklog_detail_url(workspace, project, issue, worklog),
            {"duration": "2.0000"},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        worklog.refresh_from_db()
        assert worklog.duration == Decimal("0.2500")

    @pytest.mark.django_db
    def test_auto_state_worklog_cannot_be_deleted(
        self, api_key_client, workspace, project, issue, create_user
    ):
        now = timezone.now()
        worklog = WorkItemWorklog.objects.create(
            workspace=workspace,
            project=project,
            issue=issue,
            logged_by=create_user,
            date=timezone.localdate(now),
            duration=Decimal("0.2500"),
            source=WorkItemWorklog.Source.AUTO_STATE,
            started_at=now - timedelta(minutes=15),
            stopped_at=now,
        )

        response = api_key_client.delete(worklog_detail_url(workspace, project, issue, worklog))

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert WorkItemWorklog.objects.filter(pk=worklog.id).exists()
