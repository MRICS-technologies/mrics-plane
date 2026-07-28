# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.urls import path

from plane.api.views import (
    ActiveTimerAPIEndpoint,
    StartTimerAPIEndpoint,
    StopTimerAPIEndpoint,
    WorkItemWorklogDetailAPIEndpoint,
    WorkItemWorklogListCreateAPIEndpoint,
    WorkItemStateDurationAPIEndpoint,
)


urlpatterns = [
    path(
        "workspaces/<str:slug>/active-timer/",
        ActiveTimerAPIEndpoint.as_view(http_method_names=["get"]),
        name="active-timer",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/work-items/<uuid:issue_id>/worklogs/",
        WorkItemWorklogListCreateAPIEndpoint.as_view(http_method_names=["get", "post"]),
        name="work-item-worklog-list",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/work-items/<uuid:issue_id>/worklogs/<uuid:pk>/",
        WorkItemWorklogDetailAPIEndpoint.as_view(http_method_names=["patch", "delete"]),
        name="work-item-worklog-detail",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/work-items/<uuid:issue_id>/state-durations/",
        WorkItemStateDurationAPIEndpoint.as_view(http_method_names=["get"]),
        name="work-item-state-durations",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/work-items/<uuid:issue_id>/timer/start/",
        StartTimerAPIEndpoint.as_view(http_method_names=["post"]),
        name="work-item-timer-start",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/work-items/<uuid:issue_id>/timer/stop/",
        StopTimerAPIEndpoint.as_view(http_method_names=["post"]),
        name="work-item-timer-stop",
    ),
]
