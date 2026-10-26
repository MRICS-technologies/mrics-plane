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


@pytest.fixture
def other_user(db):
    from plane.db.models import User

    return User.objects.create(email="closer@example.com", username="closer", first_name="Close", last_name="R")


def _state_activity(issue, actor, old_state, new_state, at):
    from plane.db.models import IssueActivity

    return IssueActivity.objects.create(
        issue=issue,
        project=issue.project,
        workspace=issue.workspace,
        actor=actor,
        verb="updated",
        field="state",
        old_value=old_state.name if old_state else None,
        new_value=new_state.name,
        old_identifier=old_state.id if old_state else None,
        new_identifier=new_state.id,
        epoch=at.timestamp(),
    )


@pytest.mark.django_db
def test_session_stays_with_starter_when_another_user_closes_it(issue, states, create_user, other_user):
    started_at = timezone.now() - timedelta(hours=3)
    sync_auto_state_worklog(
        issue=issue,
        user_id=create_user.id,
        old_state_id=states["todo"].id,
        new_state_id=states["started"].id,
        transition_at=started_at,
    )
    sync_auto_state_worklog(
        issue=issue,
        user_id=other_user.id,
        old_state_id=states["started"].id,
        new_state_id=states["done"].id,
        transition_at=timezone.now(),
    )

    worklog = WorkItemWorklog.objects.get(issue=issue, source=WorkItemWorklog.Source.AUTO_STATE)
    assert worklog.logged_by_id == create_user.id
    assert worklog.stopped_at is not None


@pytest.mark.django_db
def test_recovered_session_is_attributed_to_starter_not_closer(issue, states, create_user, other_user):
    entered_at = timezone.now() - timedelta(minutes=40)
    _state_activity(issue, create_user, states["todo"], states["started"], entered_at)

    sync_auto_state_worklog(
        issue=issue,
        user_id=other_user.id,
        old_state_id=states["started"].id,
        new_state_id=states["done"].id,
        transition_at=timezone.now(),
    )

    worklog = WorkItemWorklog.objects.get(issue=issue, source=WorkItemWorklog.Source.AUTO_STATE)
    assert worklog.logged_by_id == create_user.id
    assert abs((worklog.started_at - entered_at).total_seconds()) < 1


@pytest.mark.django_db
def test_fix_command_reattributes_closed_sessions(issue, states, create_user, other_user, tmp_path):
    from io import StringIO

    from django.core.management import call_command

    entered_at = timezone.now() - timedelta(hours=5)
    _state_activity(issue, create_user, states["todo"], states["started"], entered_at)
    worklog = WorkItemWorklog.objects.create(
        workspace=issue.workspace,
        project=issue.project,
        issue=issue,
        logged_by=other_user,
        date=timezone.localdate(),
        duration=Decimal("5"),
        source=WorkItemWorklog.Source.AUTO_STATE,
        started_at=entered_at,
        stopped_at=timezone.now(),
    )

    out = StringIO()
    call_command("fix_auto_state_worklog_owners", stdout=out)
    worklog.refresh_from_db()
    assert worklog.logged_by_id == other_user.id
    assert "1 to re-attribute" in out.getvalue()

    backup = tmp_path / "rollback.csv"
    call_command("fix_auto_state_worklog_owners", "--apply", "--backup-csv", str(backup), stdout=StringIO())
    worklog.refresh_from_db()
    assert worklog.logged_by_id == create_user.id
    assert str(worklog.id) in backup.read_text()

    out = StringIO()
    call_command("fix_auto_state_worklog_owners", "--apply", "--backup-csv", str(backup), stdout=out)
    assert "0 to re-attribute" in out.getvalue()


@pytest.mark.django_db
def test_fix_command_leaves_sessions_without_matching_state_change(issue, states, create_user, other_user, tmp_path):
    from io import StringIO

    from django.core.management import call_command

    _state_activity(issue, create_user, states["todo"], states["started"], timezone.now() - timedelta(days=2))
    worklog = WorkItemWorklog.objects.create(
        workspace=issue.workspace,
        project=issue.project,
        issue=issue,
        logged_by=other_user,
        date=timezone.localdate(),
        duration=Decimal("1"),
        source=WorkItemWorklog.Source.AUTO_STATE,
        started_at=timezone.now() - timedelta(hours=1),
        stopped_at=timezone.now(),
    )

    call_command(
        "fix_auto_state_worklog_owners", "--apply", "--backup-csv", str(tmp_path / "b.csv"), stdout=StringIO()
    )
    worklog.refresh_from_db()
    assert worklog.logged_by_id == other_user.id


def _closed_auto_worklog(issue, owner, started_at, stopped_at):
    return WorkItemWorklog.objects.create(
        workspace=issue.workspace,
        project=issue.project,
        issue=issue,
        logged_by=owner,
        date=timezone.localdate(),
        duration=Decimal("1"),
        source=WorkItemWorklog.Source.AUTO_STATE,
        started_at=started_at,
        stopped_at=stopped_at,
    )


@pytest.mark.django_db
def test_fix_command_ignores_entries_after_the_session_ended(issue, states, create_user, other_user, tmp_path):
    from io import StringIO

    from django.core.management import call_command

    started_at = timezone.now() - timedelta(hours=1)
    Issue.objects.filter(pk=issue.id).update(created_at=started_at - timedelta(days=1))
    worklog = _closed_auto_worklog(issue, other_user, started_at, started_at + timedelta(seconds=5))
    # Someone else re-enters In Progress after the session already stopped.
    _state_activity(issue, create_user, states["done"], states["started"], started_at + timedelta(seconds=10))

    call_command(
        "fix_auto_state_worklog_owners", "--apply", "--backup-csv", str(tmp_path / "b.csv"), stdout=StringIO()
    )
    worklog.refresh_from_db()
    assert worklog.logged_by_id == other_user.id


@pytest.mark.django_db
def test_fix_command_gives_created_in_progress_sessions_to_creator(issue, states, create_user, other_user, tmp_path):
    from io import StringIO

    from django.core.management import call_command

    issue.refresh_from_db(fields=["created_at"])
    worklog = _closed_auto_worklog(issue, other_user, issue.created_at, issue.created_at + timedelta(hours=2))

    call_command(
        "fix_auto_state_worklog_owners", "--apply", "--backup-csv", str(tmp_path / "b.csv"), stdout=StringIO()
    )
    worklog.refresh_from_db()
    assert worklog.logged_by_id == create_user.id


@pytest.mark.django_db
def test_fix_command_skips_ambiguous_starts(issue, states, create_user, other_user, tmp_path):
    from io import StringIO

    from django.core.management import call_command
    from plane.db.models import User

    third = User.objects.create(email="third@example.com", username="third", first_name="T", last_name="H")
    started_at = timezone.now() - timedelta(hours=1)
    Issue.objects.filter(pk=issue.id).update(created_at=started_at - timedelta(days=1))
    _state_activity(issue, create_user, states["todo"], states["started"], started_at)
    _state_activity(issue, third, states["todo"], states["started"], started_at + timedelta(seconds=3))
    worklog = _closed_auto_worklog(issue, other_user, started_at, started_at + timedelta(hours=1))

    out = StringIO()
    call_command(
        "fix_auto_state_worklog_owners", "--apply", "--backup-csv", str(tmp_path / "b.csv"), stdout=out
    )
    worklog.refresh_from_db()
    assert worklog.logged_by_id == other_user.id
    assert "ambiguous" in out.getvalue()


@pytest.mark.django_db
def test_fix_command_apply_requires_backup(issue, states, create_user, other_user):
    from io import StringIO

    from django.core.management import call_command
    from django.core.management.base import CommandError

    entered_at = timezone.now() - timedelta(hours=5)
    Issue.objects.filter(pk=issue.id).update(created_at=entered_at - timedelta(days=1))
    _state_activity(issue, create_user, states["todo"], states["started"], entered_at)
    _closed_auto_worklog(issue, other_user, entered_at, timezone.now())

    with pytest.raises(CommandError):
        call_command("fix_auto_state_worklog_owners", "--apply", stdout=StringIO())
