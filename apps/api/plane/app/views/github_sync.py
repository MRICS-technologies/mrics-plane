# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Python imports
import hashlib
import hmac
import logging

# Third party imports
from django.db import IntegrityError, transaction
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

# Module imports
from .base import BaseAPIView, BaseViewSet
from plane.app.permissions import ROLE, allow_permission
from plane.app.serializers.github_sync import (
    GithubAppInstallationSerializer,
    GithubEnabledRepositorySerializer,
    IssueGitLinkSerializer,
    RepoProjectMappingSerializer,
)
from plane.db.models import Project, Workspace
from plane.db.models.integration.github_sync import IssueGitLink, RepoProjectMapping
from plane.db.models.integration.github_app import GithubAppInstallation, GithubEnabledRepository
from plane.services.github.client import GitHubClient
from plane.services.github.credentials import get_github_app_credentials

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# S1: RepoProjectMappingViewSet (hardened for S2)
# ---------------------------------------------------------------------------


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
        try:
            project = Project.objects.get(workspace__slug=slug, pk=project_id)
        except Project.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        serializer = self.serializer_class(data=request.data, context={"project": project})
        serializer.is_valid(raise_exception=True)

        # Check: project already has a live mapping? Return 409.
        if RepoProjectMapping.objects.filter(project=project).exists():
            return Response(
                {"error": "This project already has a configured repository mapping."},
                status=status.HTTP_409_CONFLICT,
            )

        try:
            with transaction.atomic():
                serializer.save(workspace=project.workspace, project=project)
        except IntegrityError:
            return Response(
                {"error": "A mapping conflict occurred (duplicate or constraint violation)."},
                status=status.HTTP_409_CONFLICT,
            )

        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @allow_permission([ROLE.ADMIN])
    def destroy(self, request, slug, project_id, pk):
        try:
            mapping = self.get_queryset().get(pk=pk)
        except RepoProjectMapping.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        mapping.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# S1: IssueGitLinkViewSet (unchanged)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# S1: IssueCreateBranchEndpoint (unchanged)
# ---------------------------------------------------------------------------


class IssueCreateBranchEndpoint(BaseAPIView):
    @allow_permission([ROLE.ADMIN, ROLE.MEMBER])
    def post(self, request, slug, project_id, issue_id):
        branch_name = request.data.get("branch_name")
        if not branch_name:
            return Response({"error": "branch_name is required"}, status=status.HTTP_400_BAD_REQUEST)

        repo = request.data.get("repo")
        mapping_qs = RepoProjectMapping.objects.filter(workspace__slug=slug, project_id=project_id)
        mapping = mapping_qs.filter(github_repo=repo).first() if repo else mapping_qs.filter(is_default=True).first()
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
            return Response({"error": "GitHub App is not configured"}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)

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
            return Response({"error": "GitHub App is not configured"}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)

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


# ---------------------------------------------------------------------------
# S1: GitHubWebhookView (unchanged)
# ---------------------------------------------------------------------------


class GitHubWebhookView(BaseAPIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def _verify_signature(self, request):
        try:
            credentials = get_github_app_credentials()
        except Exception:
            return False

        if not credentials or not credentials.webhook_secret:
            # ponytail: fail closed -- an unconfigured/undecryptable P1 app
            # configuration must reject the webhook, never 500 it.
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


# ---------------------------------------------------------------------------
# S2: Workspace Installation Endpoint
# ---------------------------------------------------------------------------


class WorkspaceInstallationEndpoint(BaseAPIView):
    @allow_permission([ROLE.ADMIN, ROLE.MEMBER], level="WORKSPACE")
    def get(self, request, slug):
        installation = GithubAppInstallation.objects.filter(workspace__slug=slug).first()
        if not installation:
            return Response(None, status=status.HTTP_200_OK)
        serializer = GithubAppInstallationSerializer(installation)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @allow_permission([ROLE.ADMIN], level="WORKSPACE")
    def post(self, request, slug):
        workspace = Workspace.objects.get(slug=slug)
        serializer = GithubAppInstallationSerializer(data=request.data, context={"workspace": workspace})
        if not serializer.is_valid():
            errors = serializer.errors
            if any(getattr(item, "code", None) == "conflict" for details in errors.values() for item in details):
                return Response(errors, status=status.HTTP_409_CONFLICT)
            return Response(errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Serialise installation creation per workspace. The pre-validation guard
            # above gives fast feedback, while this locked re-check closes the
            # concurrent-POST window without broadening S2 with a migration.
            with transaction.atomic():
                workspace = Workspace.objects.select_for_update().get(pk=workspace.pk)
                if GithubAppInstallation.objects.filter(workspace=workspace).exists():
                    return Response(
                        {"installation_id": "This workspace already has an active installation."},
                        status=status.HTTP_409_CONFLICT,
                    )
                serializer.save(workspace=workspace)
        except IntegrityError:
            return Response(
                {"installation_id": "This installation_id is already claimed by another workspace."},
                status=status.HTTP_409_CONFLICT,
            )

        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @allow_permission([ROLE.ADMIN], level="WORKSPACE")
    def delete(self, request, slug):
        installation = GithubAppInstallation.objects.filter(workspace__slug=slug).first()
        if not installation:
            return Response(status=status.HTTP_404_NOT_FOUND)
        if RepoProjectMapping.objects.filter(repository__installation=installation).exists():
            return Response(
                {"error": "Remove project mappings before disconnecting this GitHub installation."},
                status=status.HTTP_409_CONFLICT,
            )
        installation.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# S2: Workspace Repositories Endpoints
# ---------------------------------------------------------------------------


class WorkspaceRepositoriesEndpoint(BaseAPIView):
    @allow_permission([ROLE.ADMIN, ROLE.MEMBER], level="WORKSPACE")
    def get(self, request, slug):
        installation = self._get_installation(slug)
        if not installation:
            return Response([], status=status.HTTP_200_OK)
        qs = GithubEnabledRepository.objects.filter(installation=installation)
        enabled_param = request.query_params.get("enabled")
        if enabled_param is not None:
            enabled_value = enabled_param.lower()
            if enabled_value not in {"true", "false"}:
                return Response(
                    {"enabled": "enabled must be true or false."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            qs = qs.filter(is_enabled=enabled_value == "true")
        serializer = GithubEnabledRepositorySerializer(qs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @allow_permission([ROLE.ADMIN], level="WORKSPACE")
    def post(self, request, slug):
        installation = self._get_installation(slug)
        if not installation:
            return Response(
                {"error": "No active GitHub installation for this workspace."},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        serializer = GithubEnabledRepositorySerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        try:
            with transaction.atomic():
                installation = GithubAppInstallation.objects.select_for_update().get(pk=installation.pk)
                if GithubEnabledRepository.objects.filter(
                    installation=installation,
                    full_name=serializer.validated_data["full_name"],
                ).exists():
                    return Response(
                        {"full_name": "This repository is already enabled for this installation."},
                        status=status.HTTP_409_CONFLICT,
                    )
                serializer.save(installation=installation)
        except IntegrityError:
            return Response(
                {"github_repository_id": "This repository is already enabled for this installation."},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @staticmethod
    def _get_installation(slug):
        return GithubAppInstallation.objects.filter(workspace__slug=slug, is_active=True).first()


class WorkspaceRepositoryDetailEndpoint(BaseAPIView):
    @allow_permission([ROLE.ADMIN], level="WORKSPACE")
    def patch(self, request, slug, repo_id):
        installation = WorkspaceRepositoriesEndpoint._get_installation(slug)
        if not installation:
            return Response(status=status.HTTP_404_NOT_FOUND)
        try:
            repo = GithubEnabledRepository.objects.get(pk=repo_id, installation=installation)
        except GithubEnabledRepository.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        # Only allow is_enabled and full_name to be patched.
        allowed_keys = {"is_enabled", "full_name"}
        unsupported_keys = set(request.data).difference(allowed_keys)
        if unsupported_keys:
            return Response(
                {"error": "Only is_enabled and full_name can be updated."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        allowed = {key: request.data[key] for key in allowed_keys if key in request.data}
        if not allowed:
            return Response(
                {"error": "Provide is_enabled or full_name to update this repository."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = GithubEnabledRepositorySerializer(repo, data=allowed, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        if (
            "full_name" in serializer.validated_data
            and GithubEnabledRepository.objects.filter(
                installation=installation,
                full_name=serializer.validated_data["full_name"],
            )
            .exclude(pk=repo.pk)
            .exists()
        ):
            return Response(
                {"full_name": "This repository is already enabled for this installation."},
                status=status.HTTP_409_CONFLICT,
            )
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)

    @allow_permission([ROLE.ADMIN], level="WORKSPACE")
    def delete(self, request, slug, repo_id):
        installation = WorkspaceRepositoriesEndpoint._get_installation(slug)
        if not installation:
            return Response(status=status.HTTP_404_NOT_FOUND)
        try:
            repo = GithubEnabledRepository.objects.get(pk=repo_id, installation=installation)
        except GithubEnabledRepository.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        if RepoProjectMapping.objects.filter(repository=repo).exists():
            return Response(
                {"error": "Remove project mappings before deleting this GitHub repository."},
                status=status.HTTP_409_CONFLICT,
            )
        repo.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
