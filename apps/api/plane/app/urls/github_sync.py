# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.urls import path

from plane.app.views import (
    RepoProjectMappingViewSet,
    IssueGitLinkViewSet,
    IssueCreateBranchEndpoint,
    GitHubWebhookView,
    WorkspaceInstallationEndpoint,
    WorkspaceRepositoriesEndpoint,
    WorkspaceRepositoryDetailEndpoint,
)

urlpatterns = [
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/github/mappings/",
        RepoProjectMappingViewSet.as_view({"get": "list", "post": "create"}),
        name="github-repo-project-mappings",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/github/mappings/<uuid:pk>/",
        RepoProjectMappingViewSet.as_view({"delete": "destroy"}),
        name="github-repo-project-mapping-detail",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/issues/<uuid:issue_id>/git-links/",
        IssueGitLinkViewSet.as_view({"get": "list"}),
        name="github-issue-git-links",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/issues/<uuid:issue_id>/github/create-branch/",
        IssueCreateBranchEndpoint.as_view(),
        name="github-issue-create-branch",
    ),
    path(
        "github/webhook/",
        GitHubWebhookView.as_view(),
        name="github-webhook",
    ),
    # S2: Workspace installation
    path(
        "workspaces/<str:slug>/github/installation/",
        WorkspaceInstallationEndpoint.as_view(),
        name="github-workspace-installation",
    ),
    # S2: Workspace repositories
    path(
        "workspaces/<str:slug>/github/repositories/",
        WorkspaceRepositoriesEndpoint.as_view(),
        name="github-workspace-repositories",
    ),
    path(
        "workspaces/<str:slug>/github/repositories/<uuid:repo_id>/",
        WorkspaceRepositoryDetailEndpoint.as_view(),
        name="github-workspace-repository-detail",
    ),
]
