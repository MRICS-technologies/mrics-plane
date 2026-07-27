# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from decimal import Decimal, ROUND_HALF_UP

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response

from plane.api.serializers import ActiveTimerSerializer, WorkItemWorklogSerializer
from plane.app.permissions import ProjectLitePermission, WorkspaceViewerPermission
from plane.db.models import ActiveTimer, Issue, ProjectMember, WorkItemWorklog, WorkspaceMember
from plane.db.models.project import ROLE

from .base import BaseAPIView


def _timer_duration(started_at, stopped_at):
    seconds = Decimal(str((stopped_at - started_at).total_seconds()))
    duration = (seconds / Decimal("3600")).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    return max(duration, Decimal("0.0001")) if duration >= Decimal("0") else duration


def _stop_timer(timer, stopped_at):
    worklog = WorkItemWorklog.objects.create(
        workspace_id=timer.workspace_id,
        project_id=timer.project_id,
        issue_id=timer.issue_id,
        logged_by_id=timer.user_id,
        date=timezone.localdate(stopped_at),
        duration=_timer_duration(timer.started_at, stopped_at),
        source=WorkItemWorklog.Source.TIMER,
        started_at=timer.started_at,
        stopped_at=stopped_at,
    )
    timer.delete(soft=False)
    return worklog


class WorkItemWorklogListCreateAPIEndpoint(BaseAPIView):
    permission_classes = [ProjectLitePermission]

    def get_queryset(self):
        return WorkItemWorklog.objects.filter(
            workspace__slug=self.kwargs["slug"],
            project_id=self.kwargs["project_id"],
            issue_id=self.kwargs["issue_id"],
        ).select_related("logged_by")

    def get(self, request, slug, project_id, issue_id):
        return Response(WorkItemWorklogSerializer(self.get_queryset(), many=True).data)

    def post(self, request, slug, project_id, issue_id):
        issue = Issue.objects.get(
            workspace__slug=slug,
            project_id=project_id,
            id=issue_id,
        )
        serializer = WorkItemWorklogSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(
            workspace_id=issue.workspace_id,
            project_id=project_id,
            issue_id=issue_id,
            logged_by=request.user,
            source=WorkItemWorklog.Source.MANUAL,
        )
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class WorkItemWorklogDetailAPIEndpoint(BaseAPIView):
    permission_classes = [ProjectLitePermission]

    def get_object(self):
        worklog = WorkItemWorklog.objects.get(
            workspace__slug=self.kwargs["slug"],
            project_id=self.kwargs["project_id"],
            issue_id=self.kwargs["issue_id"],
            id=self.kwargs["pk"],
        )
        if worklog.logged_by_id != self.request.user.id and not self._is_workspace_or_project_admin(worklog):
            self.permission_denied(self.request)
        return worklog

    def _is_workspace_or_project_admin(self, worklog):
        return (
            ProjectMember.objects.filter(
                project_id=worklog.project_id,
                member=self.request.user,
                role=ROLE.ADMIN.value,
                is_active=True,
            ).exists()
            or WorkspaceMember.objects.filter(
                workspace_id=worklog.workspace_id,
                member=self.request.user,
                role=ROLE.ADMIN.value,
                is_active=True,
            ).exists()
        )

    def patch(self, request, slug, project_id, issue_id, pk):
        serializer = WorkItemWorklogSerializer(self.get_object(), data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def delete(self, request, slug, project_id, issue_id, pk):
        self.get_object().delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ActiveTimerAPIEndpoint(BaseAPIView):
    permission_classes = [WorkspaceViewerPermission]

    def get(self, request, slug):
        timer = (
            ActiveTimer.objects.filter(user=request.user, workspace__slug=slug)
            .select_related("workspace", "project", "issue")
            .first()
        )
        if timer is None:
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response(ActiveTimerSerializer(timer).data)


class StartTimerAPIEndpoint(BaseAPIView):
    permission_classes = [ProjectLitePermission]

    @transaction.atomic
    def post(self, request, slug, project_id, issue_id):
        user = get_user_model().objects.select_for_update().get(id=request.user.id)
        issue = Issue.objects.get(
            workspace__slug=slug,
            project_id=project_id,
            id=issue_id,
        )
        stopped_worklog = None
        old_timer = ActiveTimer.objects.select_for_update().filter(user=user).first()
        if old_timer is not None:
            stopped_worklog = _stop_timer(old_timer, timezone.now())

        timer = ActiveTimer.objects.create(
            user=user,
            workspace_id=issue.workspace_id,
            project_id=project_id,
            issue_id=issue_id,
            started_at=timezone.now(),
        )
        response = {"timer": ActiveTimerSerializer(timer).data}
        if stopped_worklog is not None:
            response["stopped_worklog"] = WorkItemWorklogSerializer(stopped_worklog).data
        return Response(response, status=status.HTTP_201_CREATED)


class StopTimerAPIEndpoint(BaseAPIView):
    permission_classes = [ProjectLitePermission]

    @transaction.atomic
    def post(self, request, slug, project_id, issue_id):
        get_user_model().objects.select_for_update().get(id=request.user.id)
        timer = ActiveTimer.objects.select_for_update().filter(
            user=request.user,
            workspace__slug=slug,
            project_id=project_id,
            issue_id=issue_id,
        ).first()
        if timer is None:
            return Response(
                {"error": "No active timer exists for this work item."},
                status=status.HTTP_404_NOT_FOUND,
            )
        worklog = _stop_timer(timer, timezone.now())
        return Response(WorkItemWorklogSerializer(worklog).data, status=status.HTTP_201_CREATED)
