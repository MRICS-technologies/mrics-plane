# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from rest_framework import serializers

from plane.db.models import ActiveTimer, WorkItemWorklog

from .base import BaseSerializer


class WorkItemWorklogSerializer(BaseSerializer):
    class Meta:
        model = WorkItemWorklog
        fields = [
            "id",
            "workspace",
            "project",
            "issue",
            "logged_by",
            "date",
            "duration",
            "description",
            "source",
            "started_at",
            "stopped_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "workspace",
            "project",
            "issue",
            "logged_by",
            "source",
            "started_at",
            "stopped_at",
            "created_at",
            "updated_at",
        ]

    def validate_duration(self, value):
        if value <= 0:
            raise serializers.ValidationError("Duration must be greater than zero.")
        return value


class ActiveTimerSerializer(BaseSerializer):
    class Meta:
        model = ActiveTimer
        fields = [
            "id",
            "user",
            "workspace",
            "project",
            "issue",
            "started_at",
            "last_warned_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields
