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
