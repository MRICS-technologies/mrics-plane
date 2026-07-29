# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from datetime import date, datetime, timedelta
from datetime import timezone as dt_timezone
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
    cancelled = State.objects.create(
        name="Cancelled",
        color="#DC2626",
        sequence=40000,
        project=project,
        workspace=workspace,
        group=StateGroup.CANCELLED.value,
    )
    return {"todo": todo, "started": started, "done": done, "cancelled": cancelled}


def contributor_analytics_url(workspace, project):
    return f"/api/workspaces/{workspace.slug}/contributor-analytics/?project_ids={project.id}"


def contributor_analytics_range_url(workspace, project, start_date, end_date):
    return (
        f"/api/workspaces/{workspace.slug}/contributor-analytics/"
        f"?project_ids={project.id}&start_date={start_date}&end_date={end_date}"
    )


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

        # A cancelled, assigned issue must not inflate assigned/eligible counts or
        # the completion-rate denominator.
        cancelled_issue = Issue.objects.create(
            name="Cancelled work",
            workspace=workspace,
            project=project,
            state=states["cancelled"],
        )
        IssueAssignee.objects.create(
            issue=cancelled_issue,
            assignee=create_user,
            project=project,
            workspace=workspace,
        )

        api_client.force_authenticate(user=create_user)
        with patch("plane.app.views.analytic.project_analytics.timezone.now", return_value=now):
            response = api_client.get(contributor_analytics_url(workspace, project))

        assert response.status_code == status.HTTP_200_OK, response.data
        assert response.data["attribution"] == {
            "task_counts": "current_assignees",
            "time": "worklog_owner",
            "scope": "all_time",
            "start_date": None,
            "end_date": None,
            "task_basis": "issue_created_at",
            "time_basis": "worklog_date_or_session_overlap",
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

    def test_date_range_filters_task_and_time_totals(
        self,
        api_client,
        workspace,
        project,
        states,
        create_user,
        second_member,
    ):
        # Range under test is inclusive 2024-01-10..2024-01-12, i.e. the window
        # [2024-01-10T00:00Z, 2024-01-13T00:00Z) once day-after-end is applied.
        frozen_now = datetime(2024, 1, 11, tzinfo=dt_timezone.utc)

        completed_in_range = Issue.objects.create(
            name="Completed in range", workspace=workspace, project=project, state=states["done"]
        )
        Issue.objects.filter(pk=completed_in_range.pk).update(
            created_at=datetime(2024, 1, 11, 12, tzinfo=dt_timezone.utc)
        )
        started_in_range = Issue.objects.create(
            name="Started in range", workspace=workspace, project=project, state=states["started"]
        )
        Issue.objects.filter(pk=started_in_range.pk).update(
            created_at=datetime(2024, 1, 12, 8, tzinfo=dt_timezone.utc)
        )
        unstarted_in_range = Issue.objects.create(
            name="Unstarted in range", workspace=workspace, project=project, state=states["todo"]
        )
        Issue.objects.filter(pk=unstarted_in_range.pk).update(
            created_at=datetime(2024, 1, 10, 0, 30, tzinfo=dt_timezone.utc)
        )
        completed_out_of_range = Issue.objects.create(
            name="Completed before range", workspace=workspace, project=project, state=states["done"]
        )
        Issue.objects.filter(pk=completed_out_of_range.pk).update(
            created_at=datetime(2024, 1, 5, 12, tzinfo=dt_timezone.utc)
        )
        started_out_of_range = Issue.objects.create(
            name="Started after range", workspace=workspace, project=project, state=states["started"]
        )
        Issue.objects.filter(pk=started_out_of_range.pk).update(
            created_at=datetime(2024, 1, 13, 1, tzinfo=dt_timezone.utc)
        )

        for issue in (
            completed_in_range,
            started_in_range,
            unstarted_in_range,
            completed_out_of_range,
            started_out_of_range,
        ):
            IssueAssignee.objects.create(issue=issue, assignee=create_user, project=project, workspace=workspace)
        IssueAssignee.objects.create(
            issue=started_in_range, assignee=second_member, project=project, workspace=workspace
        )

        # Manual/timer/import worklogs: only in-range `date` values should count.
        WorkItemWorklog.objects.create(
            issue=completed_in_range,
            logged_by=create_user,
            project=project,
            workspace=workspace,
            date=date(2024, 1, 11),
            duration=Decimal("1.0000"),
            source=WorkItemWorklog.Source.MANUAL,
        )
        WorkItemWorklog.objects.create(
            issue=completed_out_of_range,
            logged_by=create_user,
            project=project,
            workspace=workspace,
            date=date(2024, 1, 5),
            duration=Decimal("2.0000"),
            source=WorkItemWorklog.Source.TIMER,
        )
        WorkItemWorklog.objects.create(
            issue=started_out_of_range,
            logged_by=create_user,
            project=project,
            workspace=workspace,
            date=date(2024, 1, 13),
            duration=Decimal("5.0000"),
            source=WorkItemWorklog.Source.MANUAL,
        )
        WorkItemWorklog.objects.create(
            issue=started_in_range,
            logged_by=second_member,
            project=project,
            workspace=workspace,
            date=date(2024, 1, 12),
            duration=Decimal("0.5000"),
            source=WorkItemWorklog.Source.IMPORT,
        )

        # Completed auto session crossing the start boundary: only window_start
        # -> stopped_at (2h) should count.
        WorkItemWorklog.objects.create(
            issue=started_in_range,
            logged_by=create_user,
            project=project,
            workspace=workspace,
            date=date(2024, 1, 10),
            duration=Decimal("0.0001"),
            source=WorkItemWorklog.Source.AUTO_STATE,
            started_at=datetime(2024, 1, 9, 20, tzinfo=dt_timezone.utc),
            stopped_at=datetime(2024, 1, 10, 2, tzinfo=dt_timezone.utc),
        )
        # Open auto session started before the range, still running at the frozen
        # `now` inside the range: only window_start -> now (24h) should count.
        WorkItemWorklog.objects.create(
            issue=started_in_range,
            logged_by=second_member,
            project=project,
            workspace=workspace,
            date=date(2024, 1, 9),
            duration=Decimal("0.0001"),
            source=WorkItemWorklog.Source.AUTO_STATE,
            started_at=datetime(2024, 1, 9, tzinfo=dt_timezone.utc),
            stopped_at=None,
        )

        api_client.force_authenticate(user=create_user)
        with patch("plane.app.views.analytic.project_analytics.timezone.now", return_value=frozen_now):
            response = api_client.get(
                contributor_analytics_range_url(workspace, project, "2024-01-10", "2024-01-12")
            )

        assert response.status_code == status.HTTP_200_OK, response.data
        assert response.data["attribution"] == {
            "task_counts": "current_assignees",
            "time": "worklog_owner",
            "scope": "date_range",
            "start_date": "2024-01-10",
            "end_date": "2024-01-12",
            "task_basis": "issue_created_at",
            "time_basis": "worklog_date_or_session_overlap",
        }
        assert response.data["summary"] == {
            "project_count": 1,
            "member_count": 2,
            "total_work_items": 3,
            "completed_work_items": 1,
            "started_work_items": 1,
            "auto_tracked_seconds": 7200 + 86400,
            "logged_work_seconds": 3600 + 1800,
            "total_tracked_seconds": 7200 + 86400 + 3600 + 1800,
        }

        contributors = {row["member_id"]: row for row in response.data["contributors"]}
        primary = contributors[str(create_user.id)]
        assert primary["assigned_work_items"] == 3
        assert primary["completed_work_items"] == 1
        assert primary["started_work_items"] == 1
        assert primary["completion_rate"] == round(1 / 3 * 100, 1)
        assert primary["auto_tracked_seconds"] == 7200
        assert primary["logged_work_seconds"] == 3600
        assert primary["total_tracked_seconds"] == 10800
        assert primary["auto_sessions"] == 1
        assert primary["logged_worklogs"] == 1

        secondary = contributors[str(second_member.id)]
        assert secondary["assigned_work_items"] == 1
        assert secondary["completed_work_items"] == 0
        assert secondary["started_work_items"] == 1
        assert secondary["completion_rate"] == 0.0
        assert secondary["auto_tracked_seconds"] == 86400
        assert secondary["logged_work_seconds"] == 1800
        assert secondary["total_tracked_seconds"] == 88200
        assert secondary["auto_sessions"] == 1
        assert secondary["logged_worklogs"] == 1

    @pytest.mark.parametrize(
        "query_suffix",
        [
            "start_date=2024-01-10",  # missing end_date
            "end_date=2024-01-10",  # missing start_date
            "start_date=2024-13-40&end_date=2024-01-10",  # malformed start_date
            "start_date=2024-01-10&end_date=not-a-date",  # malformed end_date
            "start_date=2024-01-12&end_date=2024-01-10",  # reversed range
        ],
    )
    def test_date_range_validation_errors(
        self,
        api_client,
        workspace,
        project,
        states,
        create_user,
        query_suffix,
    ):
        api_client.force_authenticate(user=create_user)
        url = f"/api/workspaces/{workspace.slug}/contributor-analytics/?project_ids={project.id}&{query_suffix}"
        response = api_client.get(url)

        assert response.status_code == status.HTTP_400_BAD_REQUEST, response.data
        assert "error" in response.data
