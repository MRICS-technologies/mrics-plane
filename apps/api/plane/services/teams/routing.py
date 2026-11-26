# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Routing rules: a work item that gains a label, or is put directly under an
epic (its parent), gets the project leader of the rule's team as an assignee.

apply_routing_rules() is the only place that evaluates them. Every work item
write path calls it inside its transaction, after it has written its own
labels, parent and assignees (no signals: Plane bulk-creates IssueLabel rows).
Not retroactive: creating or enabling a rule changes no existing work item.
"""

import json
import uuid
from collections import defaultdict
from functools import partial

from django.contrib.auth.hashers import make_password
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from plane.db.models import IssueActivity, IssueAssignee, ProjectMember, ProjectRoutingRule, ProjectTeam, User
from plane.db.models.user import BotTypeEnum

BOT_USERNAME = "routing_rule_bot"


def get_routing_bot():
    """The instance-wide actor of routing rule changes. It is in no workspace
    and can't sign in (a bot, with an unusable password)."""
    # get_or_create retries the read when a concurrent create wins. Keyed on
    # the username, which users can't choose; the email is unguessable because
    # sign-up doesn't verify emails, so a fixed one could be taken first.
    return User.objects.get_or_create(
        username=BOT_USERNAME,
        defaults={
            "email": f"routing-rule-bot-{uuid.uuid4().hex}@plane.invalid",
            "display_name": "Routing rule",
            "first_name": "Routing rule",
            "is_bot": True,
            "bot_type": BotTypeEnum.ROUTING_RULE,
            "password": make_password(None),
            "is_password_autoset": True,
        },
    )[0]


def _trigger(rule):
    return f'label "{rule.label.name}"' if rule.label_id else f'epic "{rule.epic.name}"'


def apply_routing_rules(changes):
    """changes: (issue, added label ids, new parent id or None) per work item.

    Each enabled rule of the work item's project whose label was added, or
    whose epic is the new parent, adds its team's leader in that project as an
    assignee, once, unless already assigned. Assignees are never removed. A
    rule that can't assign anyone (team not attached, no leader, leader not an
    active project member with role >= Member) leaves a "routing_rule" activity
    on the work item instead. A handful of queries per call."""
    changes = [
        (issue, {str(label_id) for label_id in label_ids or ()}, parent_id and str(parent_id))
        for issue, label_ids, parent_id in changes
        if label_ids or parent_id
    ]
    if not changes:
        return
    label_ids = set().union(*(added for _, added, _ in changes))
    parent_ids = {parent_id for _, _, parent_id in changes if parent_id}
    # Deleted labels and deleted or archived epics don't route.
    rules = (
        ProjectRoutingRule.objects.filter(project_id__in={issue.project_id for issue, _, _ in changes}, enabled=True)
        .filter(
            Q(label_id__in=label_ids, label__deleted_at__isnull=True)
            | Q(epic_id__in=parent_ids, epic__deleted_at__isnull=True, epic__archived_at__isnull=True)
        )
        .select_related("team", "label", "epic")
    )
    matches = [
        (issue, rule)
        for rule in rules
        for issue, added, parent_id in changes
        if rule.project_id == issue.project_id
        and (str(rule.label_id) in added if rule.label_id else str(rule.epic_id) == parent_id)
    ]
    if not matches:
        return

    project_ids = {rule.project_id for _, rule in matches}
    leaders = {
        (project_id, team_id): leader_id
        for project_id, team_id, leader_id in ProjectTeam.objects.filter(
            project_id__in=project_ids, team_id__in={rule.team_id for _, rule in matches}
        ).values_list("project_id", "team_id", "leader_id")
    }
    # Plane's own rule for assignees (IssueCreateSerializer.validate).
    assignable = set(
        ProjectMember.objects.filter(
            project_id__in=project_ids,
            member_id__in={leader_id for leader_id in leaders.values() if leader_id},
            is_active=True,
            role__gte=15,
        ).values_list("project_id", "member_id")
    )
    # Read after the caller's own assignee write, so only the leaders are reported.
    before = defaultdict(set)
    for issue_id, assignee_id in IssueAssignee.objects.filter(
        issue_id__in={issue.id for issue, _ in matches}
    ).values_list("issue_id", "assignee_id"):
        before[issue_id].add(assignee_id)

    added = defaultdict(list)
    notes = []
    for issue, rule in matches:
        key = (rule.project_id, rule.team_id)
        leader_id = leaders.get(key)
        if key not in leaders:
            reason = "team is not attached to the project"
        elif not leader_id:
            reason = "team has no leader"
        elif (rule.project_id, leader_id) not in assignable:
            reason = "leader can't be assigned (not an active project member)"
        else:
            if leader_id not in before[issue.id] and leader_id not in added.get(issue, ()):
                added[issue].append(leader_id)
            continue
        notes.append((issue, f"routing rule matched ({_trigger(rule)} → team {rule.team.name}), {reason}"))
    if not added and not notes:
        return

    bot = get_routing_bot()
    epoch = int(timezone.now().timestamp())
    IssueAssignee.objects.bulk_create(
        [
            IssueAssignee(
                issue_id=issue.id,
                assignee_id=leader_id,
                project_id=issue.project_id,
                workspace_id=issue.workspace_id,
                created_by=bot,
                updated_by=bot,
            )
            for issue, leader_ids in added.items()
            for leader_id in leader_ids
        ],
        ignore_conflicts=True,
    )
    IssueActivity.objects.bulk_create(
        [
            IssueActivity(
                issue_id=issue.id,
                project_id=issue.project_id,
                workspace_id=issue.workspace_id,
                actor=bot,
                verb="updated",
                field="routing_rule",
                comment=comment,
                epoch=epoch,
            )
            for issue, comment in notes
        ]
    )

    # Imported here: the task module imports plane.app.serializers, which calls us.
    from plane.bgtasks.issue_activities_task import issue_activity

    for issue, leader_ids in added.items():
        current = [str(assignee_id) for assignee_id in before[issue.id]]
        # Plane's "added assignee" activity and notification, by the bot. No issue
        # webhook: those come from model_activity, which only views send.
        # No origin, like issue_automation_task: the request's own activity sets it.
        transaction.on_commit(
            partial(
                issue_activity.delay,
                type="issue.activity.updated",
                requested_data=json.dumps({"assignee_ids": current + [str(leader_id) for leader_id in leader_ids]}),
                current_instance=json.dumps({"assignee_ids": current}),
                actor_id=str(bot.id),
                issue_id=str(issue.id),
                project_id=str(issue.project_id),
                epoch=epoch,
                notification=True,
                # The bot does not subscribe to the work item.
                subscriber=False,
            )
        )
