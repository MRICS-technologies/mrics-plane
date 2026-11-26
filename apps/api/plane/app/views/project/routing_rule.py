# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Django imports
from django.db import IntegrityError, transaction
from django.db.models import Exists, OuterRef
from django.utils import timezone

# Third party imports
from rest_framework import serializers, status
from rest_framework.response import Response

# Module imports
from plane.app.permissions import ROLE, allow_permission
from plane.app.serializers.team import active_team_members
from plane.db.models import Issue, Label, ProjectRoutingRule, ProjectTeam
from plane.services.teams.project_sync import locked_teams
from ..base import BaseAPIView

TRIGGER_FIELDS = {"label": "label_id", "epic": "epic_id"}
ENABLE_ERRORS = {
    "label_deleted": "The label was deleted.",
    "epic_deleted": "The epic was deleted or archived.",
    "team_detached": "Attach the team to this project first.",
}


class RoutingRuleCreateSerializer(serializers.Serializer):
    trigger_type = serializers.ChoiceField(choices=ProjectRoutingRule.TriggerType.choices)
    label_id = serializers.UUIDField(required=False, allow_null=True)
    epic_id = serializers.UUIDField(required=False, allow_null=True)
    team_id = serializers.UUIDField()

    def validate(self, attrs):
        field = TRIGGER_FIELDS[attrs["trigger_type"]]
        errors = {}
        if not attrs.get(field):
            errors[field] = ["This field is required."]
        for other in TRIGGER_FIELDS.values():
            if other != field and attrs.get(other):
                errors[other] = [f'Not allowed for trigger_type "{attrs["trigger_type"]}".']
        if errors:
            raise serializers.ValidationError(errors)
        return attrs


class RoutingRuleUpdateSerializer(serializers.Serializer):
    enabled = serializers.BooleanField()

    def validate(self, attrs):
        extra = sorted(set(self.initial_data) - {"enabled"})
        if extra:
            raise serializers.ValidationError({key: ["This field can't be changed."] for key in extra})
        return attrs


def _rules(slug, project_id):
    # all_objects: Plane's soft-delete cascade (deletion_task) also soft-deletes
    # the rules of a deleted label or epic; they stay listed, inactive.
    return ProjectRoutingRule.all_objects.filter(workspace__slug=slug, project_id=project_id).select_related(
        "team", "label", "epic__project"
    )


def _leaders(project_id):
    """{team id: leader id or None} for the teams attached to the project. A
    leader no longer among the team's active members reads as none, as on the
    project teams list."""
    rows = (
        ProjectTeam.objects.filter(project_id=project_id, team__deleted_at__isnull=True)
        .annotate(
            listed=Exists(active_team_members().filter(team_id=OuterRef("team_id"), member_id=OuterRef("leader_id")))
        )
        .values_list("team_id", "leader_id", "listed")
    )
    return {team_id: leader_id if listed else None for team_id, leader_id, listed in rows}


def _inactive_reason(rule, leaders):
    if rule.label_id and rule.label.deleted_at:
        return "label_deleted"
    if rule.epic_id and (rule.epic.deleted_at or rule.epic.archived_at):
        return "epic_deleted"
    if rule.team_id not in leaders:
        return "team_detached"
    if not rule.enabled:
        return "disabled"
    return None


def _serialize(rule, leaders):
    reason = _inactive_reason(rule, leaders)
    return {
        "id": str(rule.id),
        "trigger_type": rule.trigger_type,
        "label": {"id": str(rule.label_id), "name": rule.label.name, "color": rule.label.color}
        if rule.label_id
        else None,
        "epic": {
            "id": str(rule.epic_id),
            "name": rule.epic.name,
            "sequence_id": rule.epic.sequence_id,
            "project_identifier": rule.epic.project.identifier,
        }
        if rule.epic_id
        else None,
        "team": {"id": str(rule.team_id), "name": rule.team.name},
        "leader_id": str(leaders[rule.team_id]) if leaders.get(rule.team_id) else None,
        "team_attached": rule.team_id in leaders,
        "enabled": rule.enabled,
        "is_active": reason is None,
        "inactive_reason": reason,
        "created_at": rule.created_at,
    }


class ProjectRoutingRuleEndpoint(BaseAPIView):
    @allow_permission([ROLE.ADMIN, ROLE.MEMBER])
    def get(self, request, slug, project_id):
        leaders = _leaders(project_id)
        return Response([_serialize(rule, leaders) for rule in _rules(slug, project_id).order_by("created_at")])

    @allow_permission([ROLE.ADMIN])
    def post(self, request, slug, project_id):
        serializer = RoutingRuleCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        trigger = {"label_id": data.get("label_id"), "epic_id": data.get("epic_id")}
        errors = {}
        if trigger["label_id"] and not Label.objects.filter(project_id=project_id, pk=trigger["label_id"]).exists():
            errors["label_id"] = ["Must be a label of this project."]
        if (
            trigger["epic_id"]
            and not Issue.objects.filter(
                project_id=project_id, pk=trigger["epic_id"], archived_at__isnull=True
            ).exists()
        ):
            errors["epic_id"] = ["Must be a work item of this project."]
        try:
            with transaction.atomic():
                # The team lock orders this with a concurrent detach or team
                # delete, which disable the team's rules.
                team = locked_teams(slug).filter(pk=data["team_id"]).first()
                if not team:
                    errors["team_id"] = ["Must be a team of this workspace."]
                elif not ProjectTeam.objects.filter(project_id=project_id, team=team).exists():
                    errors["team_id"] = ["Attach the team to this project first."]
                if errors:
                    return Response(errors, status=status.HTTP_400_BAD_REQUEST)
                rule = ProjectRoutingRule.objects.create(
                    project_id=project_id, team=team, trigger_type=data["trigger_type"], **trigger
                )
        except IntegrityError:
            existing = ProjectRoutingRule.objects.filter(
                project_id=project_id, team_id=data["team_id"], **trigger
            ).first()
            if not existing:
                raise
            return Response(
                {"detail": "This rule already exists.", "id": str(existing.id)}, status=status.HTTP_409_CONFLICT
            )
        return Response(
            _serialize(_rules(slug, project_id).get(pk=rule.pk), _leaders(project_id)), status=status.HTTP_201_CREATED
        )


class ProjectRoutingRuleDetailEndpoint(BaseAPIView):
    @allow_permission([ROLE.ADMIN])
    def patch(self, request, slug, project_id, rule_id):
        serializer = RoutingRuleUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        enabled = serializer.validated_data["enabled"]
        with transaction.atomic():
            rule = _rules(slug, project_id).filter(pk=rule_id).first()
            if not rule:
                return Response(status=status.HTTP_404_NOT_FOUND)
            if enabled:
                # Lock the team, as on create: orders this with a concurrent detach.
                locked_teams(slug).filter(pk=rule.team_id).first()
            leaders = _leaders(project_id)
            reason = _inactive_reason(rule, leaders)
            if enabled and reason not in (None, "disabled"):
                return Response({"enabled": [ENABLE_ERRORS[reason]]}, status=status.HTTP_400_BAD_REQUEST)
            ProjectRoutingRule.all_objects.filter(pk=rule.pk).update(
                enabled=enabled, updated_at=timezone.now(), updated_by=request.user
            )
            rule.enabled = enabled
            return Response(_serialize(rule, leaders))

    @allow_permission([ROLE.ADMIN])
    def delete(self, request, slug, project_id, rule_id):
        deleted, _ = ProjectRoutingRule.all_objects.filter(
            workspace__slug=slug, project_id=project_id, pk=rule_id
        ).delete()
        return Response(status=status.HTTP_204_NO_CONTENT if deleted else status.HTTP_404_NOT_FOUND)
