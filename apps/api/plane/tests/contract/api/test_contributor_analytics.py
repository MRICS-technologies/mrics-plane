# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.utils import timezone
from rest_framework import status

from plane.db.models import (
    Issue,
    IssueAssignee,
    Project,
    ProjectMember,
    State,
    User,
    WorkItemWorklog,
)
from plane.db.models.state import StateGroup


@pytest.fixture
def project(db, workspace, create_user):
    project = Project.objects.create(
        name="Contributor Analytics Project",
        identifier="CAP",
        workspace=workspace,
        created_by=create_user,
    )
    ProjectMember.objects.create(project=project, member=create_user, role=20, is_active=True)
    return project


@pytest.fixture
def second_member(db, workspace, project):
    user = User.objects.create(
        email="second-contributor@plane.so",
        username="second-contributor",
        display_name="Second Contributor",
        is_active=True,
    )
    ProjectMember.objects.create(project=project, member=user, role=15, is_active=True)
    return user


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


def contributor_analytics_url(workspace, project):
    return f"/api/workspaces/{workspace.slug}/contributor-analytics/?project_ids={project.id}"


@pytest.mark.contract
@pytest.mark.django_db
class TestContributorAnalytics:
    def test_reports_task_and_time_totals_per_project_member(
        self,
        api_client,
        workspace,
        project,
        states,
        create_user,
        second_member,
    ):
        now = timezone.now()
        completed_issue = Issue.objects.create(
            name="Completed work",
            workspace=workspace,
            project=project,
            state=states["done"],
        )
        started_issue = Issue.objects.create(
            name="Active work",
            workspace=workspace,
            project=project,
            state=states["started"],
        )
        IssueAssignee.objects.create(
            issue=completed_issue,
            assignee=create_user,
            project=project,
            workspace=workspace,
        )
        IssueAssignee.objects.create(
            issue=started_issue,
            assignee=create_user,
            project=project,
            workspace=workspace,
        )
        IssueAssignee.objects.create(
            issue=started_issue,
            assignee=second_member,
            project=project,
            workspace=workspace,
        )

        WorkItemWorklog.objects.create(
            issue=completed_issue,
            logged_by=create_user,
            project=project,
            workspace=workspace,
            date=now.date(),
            duration=Decimal("1.5000"),
            source=WorkItemWorklog.Source.AUTO_STATE,
            started_at=now - timedelta(hours=2),
            stopped_at=now - timedelta(minutes=30),
        )
        WorkItemWorklog.objects.create(
            issue=started_issue,
            logged_by=create_user,
            project=project,
            workspace=workspace,
            date=now.date(),
            duration=Decimal("0.0001"),
            source=WorkItemWorklog.Source.AUTO_STATE,
            started_at=now - timedelta(minutes=30),
            stopped_at=None,
        )
        WorkItemWorklog.objects.create(
            issue=completed_issue,
            logged_by=create_user,
            project=project,
            workspace=workspace,
            date=now.date(),
            duration=Decimal("0.2500"),
            source=WorkItemWorklog.Source.MANUAL,
        )
        WorkItemWorklog.objects.create(
            issue=started_issue,
            logged_by=create_user,
            project=project,
            workspace=workspace,
            date=now.date(),
            duration=Decimal("0.5000"),
            source=WorkItemWorklog.Source.TIMER,
        )
        WorkItemWorklog.objects.create(
            issue=started_issue,
            logged_by=second_member,
            project=project,
            workspace=workspace,
            date=now.date(),
            duration=Decimal("1.0000"),
            source=WorkItemWorklog.Source.IMPORT,
        )

        api_client.force_authenticate(user=create_user)
        with patch("plane.app.views.analytic.project_analytics.timezone.now", return_value=now):
            response = api_client.get(contributor_analytics_url(workspace, project))

        assert response.status_code == status.HTTP_200_OK
        assert response.data["attribution"] == {
            "task_counts": "current_assignees",
            "time": "worklog_owner",
            "scope": "all_time",
        }
        assert response.data["summary"] == {
            "project_count": 1,
            "member_count": 2,
            "total_work_items": 2,
            "completed_work_items": 1,
            "started_work_items": 1,
            "auto_tracked_seconds": 7200,
            "logged_work_seconds": 6300,
            "total_tracked_seconds": 13500,
        }

        contributors = {row["member_id"]: row for row in response.data["contributors"]}
        primary = contributors[str(create_user.id)]
        assert primary["assigned_work_items"] == 2
        assert primary["completed_work_items"] == 1
        assert primary["started_work_items"] == 1
        assert primary["completion_rate"] == 50.0
        assert primary["auto_tracked_seconds"] == 7200
        assert primary["logged_work_seconds"] == 2700
        assert primary["total_tracked_seconds"] == 9900
        assert primary["auto_sessions"] == 2
        assert primary["logged_worklogs"] == 2

        secondary = contributors[str(second_member.id)]
        assert secondary["assigned_work_items"] == 1
        assert secondary["completed_work_items"] == 0
        assert secondary["started_work_items"] == 1
        assert secondary["completion_rate"] == 0.0
        assert secondary["auto_tracked_seconds"] == 0
        assert secondary["logged_work_seconds"] == 3600
        assert secondary["total_tracked_seconds"] == 3600
        assert secondary["logged_worklogs"] == 1
