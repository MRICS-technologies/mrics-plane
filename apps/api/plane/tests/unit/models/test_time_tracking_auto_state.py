# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from plane.db.models import Issue, Project, ProjectMember, State, WorkItemWorklog
from plane.db.models.state import StateGroup
from plane.db.models.time_tracking import sync_auto_state_worklog


@pytest.fixture
def project(db, workspace, create_user):
    project = Project.objects.create(
        name="Auto State Project",
        identifier="ASP",
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
    review = State.objects.create(
        name="Review",
        color="#F59E0B",
        sequence=30000,
        project=project,
        workspace=workspace,
        group=StateGroup.STARTED.value,
    )
    done = State.objects.create(
        name="Done",
        color="#46A758",
        sequence=40000,
        project=project,
        workspace=workspace,
        group=StateGroup.COMPLETED.value,
    )
    return {"todo": todo, "started": started, "review": review, "done": done}


@pytest.fixture
def issue(db, workspace, project, states, create_user):
    return Issue.objects.create(
        name="Auto state issue",
        workspace=workspace,
        project=project,
        state=states["todo"],
        created_by=create_user,
    )


@pytest.mark.django_db
def test_todo_to_started_opens_auto_state_session(issue, states, create_user):
    transition_at = timezone.now()

    sync_auto_state_worklog(
        issue=issue,
        user_id=create_user.id,
        old_state_id=states["todo"].id,
        new_state_id=states["started"].id,
        transition_at=transition_at,
    )

    worklog = WorkItemWorklog.objects.get(issue=issue, source=WorkItemWorklog.Source.AUTO_STATE)
    assert worklog.started_at == transition_at
    assert worklog.stopped_at is None
    assert worklog.duration > 0


@pytest.mark.django_db
def test_started_to_done_closes_auto_state_session(issue, states, create_user):
    started_at = timezone.now() - timedelta(minutes=30)
    stopped_at = timezone.now()
    sync_auto_state_worklog(
        issue=issue,
        user_id=create_user.id,
        old_state_id=states["todo"].id,
        new_state_id=states["started"].id,
        transition_at=started_at,
    )

    sync_auto_state_worklog(
        issue=issue,
        user_id=create_user.id,
        old_state_id=states["started"].id,
        new_state_id=states["done"].id,
        transition_at=stopped_at,
    )

    worklog = WorkItemWorklog.objects.get(issue=issue, source=WorkItemWorklog.Source.AUTO_STATE)
    assert worklog.started_at == started_at
    assert worklog.stopped_at == stopped_at
    assert worklog.duration >= Decimal("0.5")


@pytest.mark.django_db
def test_started_to_started_does_not_reset_session(issue, states, create_user):
    started_at = timezone.now() - timedelta(minutes=10)
    sync_auto_state_worklog(
        issue=issue,
        user_id=create_user.id,
        old_state_id=states["todo"].id,
        new_state_id=states["started"].id,
        transition_at=started_at,
    )

    sync_auto_state_worklog(
        issue=issue,
        user_id=create_user.id,
        old_state_id=states["started"].id,
        new_state_id=states["review"].id,
        transition_at=timezone.now(),
    )

    worklog = WorkItemWorklog.objects.get(issue=issue, source=WorkItemWorklog.Source.AUTO_STATE)
    assert worklog.started_at == started_at
    assert worklog.stopped_at is None
    assert WorkItemWorklog.objects.filter(issue=issue, source=WorkItemWorklog.Source.AUTO_STATE).count() == 1


@pytest.mark.django_db
def test_todo_to_done_does_not_create_auto_state_worklog(issue, states, create_user):
    sync_auto_state_worklog(
        issue=issue,
        user_id=create_user.id,
        old_state_id=states["todo"].id,
        new_state_id=states["done"].id,
        transition_at=timezone.now(),
    )

    assert not WorkItemWorklog.objects.filter(issue=issue, source=WorkItemWorklog.Source.AUTO_STATE).exists()

@pytest.mark.django_db
def test_issue_created_in_started_opens_auto_state_session(issue, states, create_user):
    transition_at = timezone.now()

    sync_auto_state_worklog(
        issue=issue,
        user_id=create_user.id,
        old_state_id=None,
        new_state_id=states["started"].id,
        transition_at=transition_at,
    )

    worklog = WorkItemWorklog.objects.get(issue=issue, source=WorkItemWorklog.Source.AUTO_STATE)
    assert worklog.started_at == transition_at
    assert worklog.stopped_at is None


@pytest.mark.django_db
def test_repeated_started_entry_keeps_one_open_session(issue, states, create_user):
    first_started_at = timezone.now() - timedelta(minutes=5)
    sync_auto_state_worklog(
        issue=issue,
        user_id=create_user.id,
        old_state_id=states["todo"].id,
        new_state_id=states["started"].id,
        transition_at=first_started_at,
    )

    sync_auto_state_worklog(
        issue=issue,
        user_id=create_user.id,
        old_state_id=states["todo"].id,
        new_state_id=states["started"].id,
        transition_at=timezone.now(),
    )

    worklogs = WorkItemWorklog.objects.filter(issue=issue, source=WorkItemWorklog.Source.AUTO_STATE)
    assert worklogs.count() == 1
    assert worklogs.get().started_at == first_started_at
    assert worklogs.get().stopped_at is None


@pytest.mark.django_db
def test_repeated_started_exit_does_not_create_duplicate_completed_session(issue, states, create_user):
    started_at = timezone.now() - timedelta(minutes=10)
    first_stopped_at = timezone.now() - timedelta(minutes=1)
    Issue.objects.filter(pk=issue.id).update(created_at=started_at - timedelta(minutes=1))
    issue.refresh_from_db(fields=["created_at"])

    sync_auto_state_worklog(
        issue=issue,
        user_id=create_user.id,
        old_state_id=states["todo"].id,
        new_state_id=states["started"].id,
        transition_at=started_at,
    )
    sync_auto_state_worklog(
        issue=issue,
        user_id=create_user.id,
        old_state_id=states["started"].id,
        new_state_id=states["done"].id,
        transition_at=first_stopped_at,
    )

    sync_auto_state_worklog(
        issue=issue,
        user_id=create_user.id,
        old_state_id=states["started"].id,
        new_state_id=states["done"].id,
        transition_at=timezone.now(),
    )

    worklogs = WorkItemWorklog.objects.filter(issue=issue, source=WorkItemWorklog.Source.AUTO_STATE)
    assert worklogs.count() == 1
    assert worklogs.get().started_at == started_at
    assert worklogs.get().stopped_at == first_stopped_at

@pytest.mark.django_db
def test_done_to_started_opens_a_new_session(issue, states, create_user):
    first_started_at = timezone.now() - timedelta(minutes=30)
    first_stopped_at = timezone.now() - timedelta(minutes=20)
    second_started_at = timezone.now() - timedelta(minutes=5)

    sync_auto_state_worklog(
        issue=issue,
        user_id=create_user.id,
        old_state_id=states["todo"].id,
        new_state_id=states["started"].id,
        transition_at=first_started_at,
    )
    sync_auto_state_worklog(
        issue=issue,
        user_id=create_user.id,
        old_state_id=states["started"].id,
        new_state_id=states["done"].id,
        transition_at=first_stopped_at,
    )
    sync_auto_state_worklog(
        issue=issue,
        user_id=create_user.id,
        old_state_id=states["done"].id,
        new_state_id=states["started"].id,
        transition_at=second_started_at,
    )

    worklogs = WorkItemWorklog.objects.filter(
        issue=issue, source=WorkItemWorklog.Source.AUTO_STATE
    ).order_by("started_at")
    assert worklogs.count() == 2
    assert worklogs[0].stopped_at == first_stopped_at
    assert worklogs[1].started_at == second_started_at
    assert worklogs[1].stopped_at is None


@pytest.mark.django_db
def test_stop_recovers_completed_session_when_open_worklog_is_missing(issue, states, create_user):
    entered_at = timezone.now() - timedelta(minutes=15)
    stopped_at = timezone.now()
    Issue.objects.filter(pk=issue.id).update(created_at=entered_at)
    issue.refresh_from_db(fields=["created_at"])

    sync_auto_state_worklog(
        issue=issue,
        user_id=create_user.id,
        old_state_id=states["started"].id,
        new_state_id=states["done"].id,
        transition_at=stopped_at,
    )

    worklog = WorkItemWorklog.objects.get(issue=issue, source=WorkItemWorklog.Source.AUTO_STATE)
    assert worklog.started_at == entered_at
    assert worklog.stopped_at == stopped_at
    assert worklog.duration >= Decimal("0.25")


@pytest.mark.django_db
def test_auto_state_actor_falls_back_to_issue_creator(issue, states, create_user):
    Issue.objects.filter(pk=issue.id).update(created_by=create_user)
    issue.refresh_from_db(fields=["created_by"])

    sync_auto_state_worklog(
        issue=issue,
        user_id=None,
        old_state_id=states["todo"].id,
        new_state_id=states["started"].id,
        transition_at=timezone.now(),
    )

    worklog = WorkItemWorklog.objects.get(issue=issue, source=WorkItemWorklog.Source.AUTO_STATE)
    assert worklog.logged_by_id == create_user.id
