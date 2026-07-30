# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Python imports
import hashlib
import hmac
import logging

# Third party imports
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

# Module imports
from .base import BaseAPIView, BaseViewSet
from plane.app.permissions import ROLE, allow_permission
from plane.app.serializers.github_sync import (
    IssueGitLinkSerializer,
    RepoProjectMappingSerializer,
)
from plane.db.models import Project
from plane.db.models.integration.github_sync import IssueGitLink, RepoProjectMapping
from plane.services.github.client import GitHubClient
from plane.services.github.credentials import get_github_app_credentials

logger = logging.getLogger(__name__)


class RepoProjectMappingViewSet(BaseViewSet):
    model = RepoProjectMapping
    serializer_class = RepoProjectMappingSerializer

    def get_queryset(self):
        return RepoProjectMapping.objects.filter(
            workspace__slug=self.kwargs.get("slug"), project_id=self.kwargs.get("project_id")
        )

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER])
    def list(self, request, slug, project_id):
        serializer = self.serializer_class(self.get_queryset(), many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @allow_permission([ROLE.ADMIN])
    def create(self, request, slug, project_id):
        project = Project.objects.get(workspace__slug=slug, pk=project_id)
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(workspace=project.workspace, project=project)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @allow_permission([ROLE.ADMIN])
    def destroy(self, request, slug, project_id, pk):
        mapping = self.get_queryset().get(pk=pk)
        mapping.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class IssueGitLinkViewSet(BaseViewSet):
    model = IssueGitLink
    serializer_class = IssueGitLinkSerializer

    def get_queryset(self):
        return IssueGitLink.objects.filter(
            workspace__slug=self.kwargs.get("slug"),
            project_id=self.kwargs.get("project_id"),
            issue_id=self.kwargs.get("issue_id"),
        )

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER])
    def list(self, request, slug, project_id, issue_id):
        serializer = self.serializer_class(self.get_queryset(), many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class IssueCreateBranchEndpoint(BaseAPIView):
    @allow_permission([ROLE.ADMIN, ROLE.MEMBER])
    def post(self, request, slug, project_id, issue_id):
        branch_name = request.data.get("branch_name")
        if not branch_name:
            return Response({"error": "branch_name is required"}, status=status.HTTP_400_BAD_REQUEST)

        repo = request.data.get("repo")
        mapping_qs = RepoProjectMapping.objects.filter(workspace__slug=slug, project_id=project_id)
        mapping = (
            mapping_qs.filter(github_repo=repo).first()
            if repo
            else mapping_qs.filter(is_default=True).first()
        )
        if not mapping:
            return Response(
                {"error": "No GitHub repository mapping configured for this project"},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        if IssueGitLink.objects.filter(
            issue_id=issue_id,
            github_repo=mapping.github_repo,
            kind="branch",
            ref=branch_name,
        ).exists():
            return Response({"error": "Branch already exists"}, status=status.HTTP_409_CONFLICT)

        credentials = get_github_app_credentials()
        if not credentials:
            return Response(
                {"error": "GitHub App is not configured"}, status=status.HTTP_422_UNPROCESSABLE_ENTITY
            )

        owner, _, name = mapping.github_repo.partition("/")
        client = GitHubClient(
            credentials.app_id,
            credentials.private_key,
            mapping.github_installation_id,
            credentials.github_base_url,
            credentials.html_base_url,
        )
        try:
            if client.get_branch_sha(owner, name, branch_name):
                return Response({"error": "Branch already exists"}, status=status.HTTP_409_CONFLICT)
            result = client.create_branch(owner, name, branch_name, mapping.base_branch)
        except NotImplementedError:
            return Response(
                {"error": "GitHub App is not configured"}, status=status.HTTP_422_UNPROCESSABLE_ENTITY
            )

        git_link = IssueGitLink.objects.create(
            workspace=mapping.workspace,
            project=mapping.project,
            issue_id=issue_id,
            github_repo=mapping.github_repo,
            kind="branch",
            ref=result["branch_name"],
            url=result["url"],
            state="open",
            detected_via="manual",
        )
        serializer = IssueGitLinkSerializer(git_link)
        return Response(
            {"branch_name": result["branch_name"], "url": result["url"], "sha": result["sha"], **serializer.data},
            status=status.HTTP_201_CREATED,
        )


class GitHubWebhookView(BaseAPIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def _verify_signature(self, request):
        try:
            credentials = get_github_app_credentials()
        except Exception:
            # ponytail: fail closed -- an unconfigured/undecryptable P1 app
            # configuration must reject the webhook, never 500 it.
            return False

        if not credentials or not credentials.webhook_secret:
            return False

        secret = credentials.webhook_secret
        signature = request.headers.get("X-Hub-Signature-256", "")
        if not signature.startswith("sha256="):
            return False

        expected = "sha256=" + hmac.new(secret.encode(), request.body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

    def post(self, request):
        if not self._verify_signature(request):
            return Response({"error": "Invalid signature"}, status=status.HTTP_401_UNAUTHORIZED)

        event = request.headers.get("X-GitHub-Event", "")
        # ponytail: MVP just logs + acknowledges; full PR-state automation lands once
        # branch<->issue matching rules are decided
        logger.info("Received GitHub webhook event: %s", event)
        return Response(status=status.HTTP_200_OK)
