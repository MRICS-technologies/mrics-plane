# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from datetime import datetime, timezone as dt_timezone
from decimal import Decimal, ROUND_HALF_UP

from django.apps import apps
from django.conf import settings
from django.db import models, transaction
from django.utils import timezone

from .issue import Issue, IssueActivity
from .project import ProjectBaseModel
from .state import State, StateGroup


class WorkItemWorklog(ProjectBaseModel):
    class Source(models.TextChoices):
        TIMER = "timer", "Timer"
        MANUAL = "manual", "Manual"
        IMPORT = "import", "Import"
        AUTO_STATE = "auto_state", "Auto (State)"

    issue = models.ForeignKey("db.Issue", on_delete=models.CASCADE, related_name="worklogs")
    logged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="work_item_worklogs",
    )
    date = models.DateField()
    duration = models.DecimalField(max_digits=12, decimal_places=4)
    description = models.TextField(blank=True, default="")
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.MANUAL)
    started_at = models.DateTimeField(null=True, blank=True)
    stopped_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "work_item_worklogs"
        ordering = ("-date", "-created_at")
        constraints = [
            models.UniqueConstraint(
                fields=["issue"],
                condition=models.Q(
                    source="auto_state",
                    stopped_at__isnull=True,
                    deleted_at__isnull=True,
                ),
                name="worklog_unique_open_auto_state_issue",
            )
        ]


class ActiveTimer(ProjectBaseModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="active_work_item_timers",
    )
    issue = models.ForeignKey("db.Issue", on_delete=models.CASCADE, related_name="active_timers")
    started_at = models.DateTimeField()
    last_warned_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "active_work_item_timers"
        constraints = [
            models.UniqueConstraint(
                fields=["user"],
                condition=models.Q(deleted_at__isnull=True),
                name="active_timer_unique_active_user",
            )
        ]


def seconds_to_hours(seconds):
    return (seconds / Decimal("3600")).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def worklog_duration_hours(started_at, stopped_at):
    seconds = Decimal(str((stopped_at - started_at).total_seconds()))
    duration = seconds_to_hours(seconds)
    return max(duration, Decimal("0.0001")) if duration >= Decimal("0") else duration


def activity_instant(activity):
    """Best available timestamp for an IssueActivity: its epoch, else created_at."""
    if activity.epoch is not None:
        return datetime.fromtimestamp(activity.epoch, tz=dt_timezone.utc)
    return activity.created_at


def state_entered_at(issue_id, state_id):
    """Timestamp the issue most recently moved into state_id, or None if never."""
    activity = (
        IssueActivity.objects.filter(issue_id=issue_id, field="state", new_identifier=state_id)
        .order_by("-epoch", "-created_at")
        .first()
    )
    return activity_instant(activity) if activity is not None else None


def started_group_entered_at(issue_id, *, fallback_to_issue_created=False):
    """Timestamp the current STARTED-group session began from existing state activity."""
    issue = Issue.objects.filter(pk=issue_id).only("id", "project_id", "created_at").first()
    if issue is None:
        return None

    started_state_ids = {
        str(state_id)
        for state_id in State.objects.filter(
            project_id=issue.project_id,
            group=StateGroup.STARTED.value,
        ).values_list("id", flat=True)
    }

    active_started_at = None
    has_state_activity = False
    activities = IssueActivity.objects.filter(issue_id=issue_id, field="state").order_by("epoch", "created_at")
    for activity in activities:
        has_state_activity = True
        old_started = str(activity.old_identifier) in started_state_ids if activity.old_identifier else False
        new_started = str(activity.new_identifier) in started_state_ids if activity.new_identifier else False
        if not old_started and new_started:
            active_started_at = activity_instant(activity)
        elif old_started and new_started:
            active_started_at = active_started_at or activity_instant(activity)
        elif old_started and not new_started:
            active_started_at = None

    if active_started_at is not None:
        return active_started_at
    if fallback_to_issue_created and not has_state_activity:
        return issue.created_at
    return None


def _is_started_state(project_id, state_id):
    if state_id is None:
        return False
    return State.objects.filter(pk=state_id, project_id=project_id, group=StateGroup.STARTED.value).exists()


def lock_issue_for_transition(issue_id):
    """Row-lock and return the fresh issue instance for a state transition.

    Call this first inside the same transaction.atomic() block that will persist
    the new state (before the serializer/save call), so concurrent transitions on
    the same issue serialize and the serializer saves a fresh locked instance.
    """
    return Issue.objects.select_for_update().get(pk=issue_id)


def auto_state_actor_id(issue, user_id=None):
    """Return a valid user id for automatic worklogs, or None if unavailable."""
    User = apps.get_model("db", "User")
    for candidate in (user_id, getattr(issue, "created_by_id", None)):
        if candidate and User.objects.filter(pk=candidate, is_active=True).exists():
            return candidate
    return None


def active_auto_state_worklog(issue_id):
    """Return the latest open automatic state worklog for an issue, if any."""
    return (
        WorkItemWorklog.objects.filter(
            issue_id=issue_id,
            source=WorkItemWorklog.Source.AUTO_STATE,
            stopped_at__isnull=True,
        )
        .order_by("-started_at", "-created_at")
        .first()
    )


def start_auto_state_worklog(*, issue, user_id, started_at):
    """Open an automatic state session when an issue enters STARTED."""
    user_id = auto_state_actor_id(issue, user_id)
    if user_id is None:
        return None
    if started_at is None:
        started_at = timezone.now()
    with transaction.atomic():
        Issue.objects.select_for_update().filter(pk=issue.id).exists()
        open_worklog = (
            WorkItemWorklog.objects.select_for_update()
            .filter(
                issue_id=issue.id,
                source=WorkItemWorklog.Source.AUTO_STATE,
                stopped_at__isnull=True,
            )
            .order_by("-started_at", "-created_at")
            .first()
        )
        if open_worklog is not None:
            return open_worklog
        return WorkItemWorklog.objects.create(
            workspace_id=issue.workspace_id,
            project_id=issue.project_id,
            issue_id=issue.id,
            logged_by_id=user_id,
            date=timezone.localdate(started_at),
            duration=Decimal("0.0001"),
            description="Auto tracking active from Started/In Progress state",
            source=WorkItemWorklog.Source.AUTO_STATE,
            started_at=started_at,
            stopped_at=None,
        )


def stop_auto_state_worklog(*, issue, user_id, stopped_at):
    """Close open automatic STARTED sessions when an issue leaves STARTED."""
    if stopped_at is None:
        stopped_at = timezone.now()
    with transaction.atomic():
        Issue.objects.select_for_update().filter(pk=issue.id).exists()
        open_worklogs = list(
            WorkItemWorklog.objects.select_for_update()
            .filter(
                issue_id=issue.id,
                source=WorkItemWorklog.Source.AUTO_STATE,
                stopped_at__isnull=True,
            )
            .order_by("started_at", "created_at")
        )
        if not open_worklogs:
            recovered_started_at = started_group_entered_at(issue.id, fallback_to_issue_created=True)
            fallback_user_id = auto_state_actor_id(issue, user_id)
            if fallback_user_id is None or recovered_started_at is None or stopped_at <= recovered_started_at:
                return None
            return WorkItemWorklog.objects.create(
                workspace_id=issue.workspace_id,
                project_id=issue.project_id,
                issue_id=issue.id,
                logged_by_id=fallback_user_id,
                date=timezone.localdate(stopped_at),
                duration=worklog_duration_hours(recovered_started_at, stopped_at),
                description="Auto tracked from Started/In Progress state changes",
                source=WorkItemWorklog.Source.AUTO_STATE,
                started_at=recovered_started_at,
                stopped_at=stopped_at,
            )

        closed_worklog = None
        for worklog in open_worklogs:
            if stopped_at <= worklog.started_at:
                continue
            actor_id = auto_state_actor_id(issue, user_id)
            if actor_id is not None:
                worklog.logged_by_id = actor_id
            worklog.stopped_at = stopped_at
            worklog.date = timezone.localdate(stopped_at)
            worklog.duration = worklog_duration_hours(worklog.started_at, stopped_at)
            worklog.description = "Auto tracked from Started/In Progress state changes"
            worklog.save(update_fields=["logged_by", "stopped_at", "date", "duration", "description", "updated_at"])
            closed_worklog = closed_worklog or worklog
        return closed_worklog


def sync_auto_state_worklog(*, issue, user_id, old_state_id, new_state_id, transition_at):
    """Synchronously mirror issue state transitions into automatic worklogs.

    This avoids relying on async activity ordering: moving into STARTED opens an
    auto session; moving out closes it; STARTED->STARTED leaves it running.
    """
    old_started = _is_started_state(issue.project_id, old_state_id)
    new_started = _is_started_state(issue.project_id, new_state_id)
    if old_started == new_started:
        return None
    if new_started:
        return start_auto_state_worklog(issue=issue, user_id=user_id, started_at=transition_at)
    return stop_auto_state_worklog(issue=issue, user_id=user_id, stopped_at=transition_at)


def create_auto_state_worklog(*, workspace_id, project_id, issue_id, user_id, started_at, stopped_at):
    """Backward-compatible direct creator for recovered completed sessions."""
    issue = Issue.objects.filter(pk=issue_id).only("id", "workspace_id", "project_id", "created_by_id").first()
    if issue is None or started_at is None or stopped_at is None or stopped_at <= started_at:
        return None
    user_id = auto_state_actor_id(issue, user_id)
    if user_id is None:
        return None
    return WorkItemWorklog.objects.create(
        workspace_id=workspace_id,
        project_id=project_id,
        issue_id=issue_id,
        logged_by_id=user_id,
        date=timezone.localdate(stopped_at),
        duration=worklog_duration_hours(started_at, stopped_at),
        description="Auto tracked from Started/In Progress state changes",
        source=WorkItemWorklog.Source.AUTO_STATE,
        started_at=started_at,
        stopped_at=stopped_at,
    )
