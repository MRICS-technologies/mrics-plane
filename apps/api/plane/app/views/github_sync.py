# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Python imports
import hashlib
import hmac
import logging
import re
from datetime import timedelta
from urllib.parse import urlencode

# Third party imports
import requests
from django.db import IntegrityError, transaction
from django.http import HttpResponseRedirect
from django.utils import timezone
from django.utils.dateparse import parse_datetime
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
from plane.authentication.utils.host import base_host
from plane.db.models import Issue, Project, Workspace
from plane.db.models.integration.github_sync import GithubWebhookDelivery, IssueGitLink, RepoProjectMapping
from plane.db.models.integration.github_app import GithubAppInstallation, GithubEnabledRepository
from plane.services.github.client import GitHubClient
from plane.services.github.credentials import get_github_app_credentials
from plane.services.github.setup_state import (
    consume as consume_setup_state,
    issue as issue_setup_state,
    STATE_TTL_SECONDS,
)

logger = logging.getLogger(__name__)

# GitHub caps a delivery at ~25MB, but this endpoint only ever needs a
# `pull_request` event payload -- reject anything past 1 MiB before HMAC or
# JSON work touches it.
MAX_WEBHOOK_BODY_BYTES = 1024 * 1024

# pull_request.action values this slice understands; anything else (edited,
# labeled, assigned, ...) is acknowledged with no state change.
_OPEN_ACTIONS = {"opened", "reopened"}
_CLOSE_ACTIONS = {"closed"}
_SYNC_ACTIONS = {"synchronize"}

# X-GitHub-Event values this view parses the body for; any other event is
# still recorded as a delivery (for dedup) but never JSON-decoded.
_HANDLED_EVENTS = {"pull_request", "installation", "installation_repositories"}
# GitHub's actual `installation.action` values are "suspend"/"unsuspend";
# the "suspended"/"unsuspended" spellings are accepted defensively.
_SUSPEND_ACTIONS = {"suspend", "suspended"}
_UNSUSPEND_ACTIONS = {"unsuspend", "unsuspended"}

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
# P4: GitHubWebhookView -- signed `pull_request` webhook -> IssueGitLink
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
        # Body size is checked first in this view; the route is also excluded
        # from API-token body logging so raw webhook data cannot be persisted.
        if len(request.body) > MAX_WEBHOOK_BODY_BYTES:
            return Response(status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
        if not self._verify_signature(request):
            return Response({"error": "Invalid signature"}, status=status.HTTP_401_UNAUTHORIZED)

        event = request.headers.get("X-GitHub-Event", "")
        delivery_id = request.headers.get("X-GitHub-Delivery", "")
        if not delivery_id:
            return Response(status=status.HTTP_200_OK)

        # Parse signed payloads before recording the delivery. A bad JSON body
        # must not poison GitHub's retry/dedup path.
        payload = request.data if event in _HANDLED_EVENTS else None
        installation_id = (payload.get("installation") or {}).get("id") if payload else None
        try:
            with transaction.atomic():
                GithubWebhookDelivery.objects.create(
                    delivery_id=delivery_id, event=event, installation_id=installation_id
                )
                if payload is not None:
                    if event == "pull_request":
                        self._process_pull_request(payload or {})
                    elif event == "installation":
                        self._process_installation(payload or {})
                    elif event == "installation_repositories":
                        self._process_installation_repositories(payload or {})
        except IntegrityError:
            # A live delivery id can be created only once. GitHub retries are
            # intentionally acknowledged without duplicating side effects.
            return Response(status=status.HTTP_200_OK)
        return Response(status=status.HTTP_200_OK)

    def _process_installation(self, payload):
        action = payload.get("action")
        installation_id = (payload.get("installation") or {}).get("id")
        if not installation_id:
            return

        if action == "created":
            # The verified /github/setup/ callback is the source of truth for
            # attaching a new installation to a workspace; this event carries
            # no trustworthy workspace binding of its own, so it is a no-op.
            return

        installation = GithubAppInstallation.objects.filter(installation_id=installation_id).first()
        if not installation:
            return

        if action == "deleted":
            installation.is_active = False
            installation.suspended_at = installation.suspended_at or timezone.now()
            installation.save(update_fields=["is_active", "suspended_at", "updated_at"])
        elif action in _SUSPEND_ACTIONS:
            installation.is_active = False
            installation.suspended_at = timezone.now()
            installation.save(update_fields=["is_active", "suspended_at", "updated_at"])
        elif action in _UNSUSPEND_ACTIONS:
            installation.is_active = True
            installation.suspended_at = None
            installation.save(update_fields=["is_active", "suspended_at", "updated_at"])

    def _process_installation_repositories(self, payload):
        if payload.get("action") != "removed":
            return
        installation_id = (payload.get("installation") or {}).get("id")
        if not installation_id:
            return
        installation = GithubAppInstallation.objects.filter(installation_id=installation_id).first()
        if not installation:
            return
        repo_ids = [repo.get("id") for repo in payload.get("repositories_removed") or [] if repo.get("id")]
        if not repo_ids:
            return
        GithubEnabledRepository.objects.filter(
            installation=installation, github_repository_id__in=repo_ids
        ).update(is_enabled=False, updated_at=timezone.now())

    def _process_pull_request(self, payload):
        installation_id = (payload.get("installation") or {}).get("id")
        repo_payload = payload.get("repository") or {}
        repo_github_id = repo_payload.get("id")
        repo_full_name = repo_payload.get("full_name")
        pr_payload = payload.get("pull_request") or {}
        pr_number = pr_payload.get("number")
        if not (installation_id and repo_github_id and repo_full_name and pr_number):
            return

        installation = GithubAppInstallation.objects.filter(installation_id=installation_id, is_active=True).first()
        if not installation:
            return
        enabled_repo = GithubEnabledRepository.objects.filter(
            installation=installation, github_repository_id=repo_github_id, is_enabled=True
        ).first()
        if not enabled_repo:
            return
        mappings = list(
            RepoProjectMapping.objects.filter(repository=enabled_repo, workspace=installation.workspace)
            .select_related("project")
            .order_by("project_id")
        )
        if not mappings:
            return

        # GitHub sends an object here. Treat a malformed signed payload as an
        # uncorrelatable event rather than allowing it to raise a 500.
        head_payload = pr_payload.get("head") or {}
        head_ref = head_payload.get("ref", "") if isinstance(head_payload, dict) else ""
        state = self._resolve_state(payload.get("action"), pr_payload.get("merged", False))
        updated_at = self._parse_datetime(pr_payload.get("updated_at"))

        # State updates must continue to work even if the title/head no longer
        # contains a key. The existing link is accepted only when it belongs to
        # this installation workspace and one of its current project mappings.
        mapped_project_ids = {mapping.project_id for mapping in mappings}
        existing = IssueGitLink.objects.filter(
            workspace=installation.workspace, kind="pr", github_repo=repo_full_name, pr_number=pr_number
        ).first()
        if existing:
            if existing.project_id not in mapped_project_ids:
                return
            self._upsert_pr_link(
                project=existing.project,
                issue=existing.issue,
                repo_full_name=repo_full_name,
                pr_number=pr_number,
                ref=head_ref,
                url=pr_payload.get("html_url", ""),
                state=state,
                updated_at=updated_at,
                detected_via=existing.detected_via,
            )
            return

        project, issue, detected_via = self._resolve_issue(
            mappings, repo_full_name, head_ref, pr_payload.get("title") or ""
        )
        if not issue:
            return
        self._upsert_pr_link(
            project=project,
            issue=issue,
            repo_full_name=repo_full_name,
            pr_number=pr_number,
            ref=head_ref,
            url=pr_payload.get("html_url", ""),
            state=state,
            updated_at=updated_at,
            detected_via=detected_via,
        )

    @staticmethod
    def _resolve_issue(mappings, repo_full_name, head_ref, title):
        branch_matches = []
        if head_ref:
            for mapping in mappings:
                branch_link = IssueGitLink.objects.filter(
                    project=mapping.project, github_repo=repo_full_name, kind="branch", ref=head_ref
                ).first()
                if branch_link:
                    branch_matches.append((mapping.project, branch_link.issue, "branch"))
        if len(branch_matches) == 1:
            return branch_matches[0]
        if len(branch_matches) > 1:
            return None, None, None

        issue_matches = []
        for mapping in mappings:
            pattern = re.compile(rf"\b{re.escape(mapping.project.identifier)}-(\d+)\b", re.IGNORECASE)
            for value in (title, head_ref):
                match = pattern.search(value or "")
                if match:
                    issue = Issue.objects.filter(project=mapping.project, sequence_id=int(match.group(1))).first()
                    if issue:
                        issue_matches.append((mapping.project, issue, "title"))
                        break
        return issue_matches[0] if len(issue_matches) == 1 else (None, None, None)

    @staticmethod
    def _resolve_state(action, merged):
        if action in _OPEN_ACTIONS:
            return "open"
        if action in _CLOSE_ACTIONS:
            return "merged" if merged else "closed"
        if action in _SYNC_ACTIONS:
            return "open"
        return None

    @staticmethod
    def _parse_datetime(value):
        return parse_datetime(value) if value else None

    @staticmethod
    def _upsert_pr_link(project, issue, repo_full_name, pr_number, ref, url, state, updated_at, detected_via):
        filters = {"workspace": project.workspace, "kind": "pr", "github_repo": repo_full_name, "pr_number": pr_number}
        existing = IssueGitLink.objects.select_for_update().filter(**filters).first()
        if existing:
            # Do not let an equal, absent, or older timestamp regress a known
            # state. GitHub timestamps are authoritative only when newer.
            if existing.github_updated_at and (not updated_at or updated_at <= existing.github_updated_at):
                return
            existing.ref = ref or existing.ref
            existing.url = url or existing.url
            if state:
                existing.state = state
            if updated_at:
                existing.github_updated_at = updated_at
            existing.save(update_fields=["ref", "url", "state", "github_updated_at", "updated_at"])
            return

        # Restore a soft-deleted matching PR instead of creating a duplicate
        # that the historic unique_together constraint would reject.
        deleted = (
            IssueGitLink.all_objects.select_for_update()
            .filter(**filters)
            .order_by("-updated_at")
            .first()
        )
        if deleted:
            deleted.deleted_at = None
            deleted.issue = issue
            deleted.project = project
            deleted.ref = ref
            deleted.url = url
            deleted.state = state or "unknown"
            deleted.github_updated_at = updated_at
            deleted.detected_via = detected_via
            deleted.save(
                update_fields=[
                    "deleted_at", "issue", "project", "ref", "url", "state", "github_updated_at", "detected_via",
                    "updated_at",
                ]
            )
            return

        try:
            with transaction.atomic():
                IssueGitLink.objects.create(
                    workspace=project.workspace,
                    project=project,
                    issue=issue,
                    github_repo=repo_full_name,
                    kind="pr",
                    ref=ref,
                    url=url,
                    state=state or "unknown",
                    pr_number=pr_number,
                    github_updated_at=updated_at,
                    detected_via=detected_via,
                )
        except IntegrityError:
            # A concurrent delivery created it first. Lock and apply this event
            # only if its timestamp is newer, instead of losing that update.
            existing = IssueGitLink.objects.select_for_update().filter(**filters).first()
            if existing and (
                not existing.github_updated_at or (updated_at and updated_at > existing.github_updated_at)
            ):
                existing.ref = ref or existing.ref
                existing.url = url or existing.url
                if state:
                    existing.state = state
                if updated_at:
                    existing.github_updated_at = updated_at
                existing.save(update_fields=["ref", "url", "state", "github_updated_at", "updated_at"])


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
# P1 1.4: One-click install (Coolify pattern) -- state-verified callback
# ---------------------------------------------------------------------------


class WorkspaceGitHubInstallURLEndpoint(BaseAPIView):
    """Issues a one-time, workspace-bound `state` and the GitHub install URL
    that carries it. The browser is sent straight to GitHub; nothing here
    trusts anything the client supplies beyond the workspace in the URL."""

    @allow_permission([ROLE.ADMIN], level="WORKSPACE")
    def post(self, request, slug):
        credentials = get_github_app_credentials()
        if not credentials or not credentials.app_slug:
            return Response(
                {"error": "GitHub App is not configured on this instance."},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        workspace = Workspace.objects.get(slug=slug)
        redirect = (request.data.get("redirect") or "").strip()
        state = issue_setup_state(
            "install", workspace_id=str(workspace.id), user_id=str(request.user.id), redirect=redirect
        )
        install_url = (
            f"{credentials.html_base_url}/apps/{credentials.app_slug}/installations/new"
            f"?{urlencode({'state': state})}"
        )
        return Response(
            {"install_url": install_url, "expires_at": timezone.now() + timedelta(seconds=STATE_TTL_SECONDS)},
            status=status.HTTP_200_OK,
        )


class GitHubSetupCallbackEndpoint(BaseAPIView):
    """`AllowAny` + state-gated: GitHub redirects the installer's browser here
    after `installations/new`. The installation is looked up and verified
    against our own app id via GitHub before anything is persisted -- the
    query-string `installation_id`/`setup_action` are never trusted as-is."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        claim = consume_setup_state(request.query_params.get("state", ""), "install")
        if not claim:
            return Response({"error": "invalid_state"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            installation_id = int(request.query_params.get("installation_id", ""))
        except (TypeError, ValueError):
            return Response({"error": "invalid_installation_id"}, status=status.HTTP_400_BAD_REQUEST)

        workspace = Workspace.objects.filter(pk=claim.get("workspace_id")).first()
        if not workspace:
            return Response({"error": "invalid_workspace"}, status=status.HTTP_400_BAD_REQUEST)

        credentials = get_github_app_credentials()
        if not credentials:
            return Response({"error": "not_configured"}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)

        try:
            installation_data = GitHubClient.for_installation(installation_id).get_installation(installation_id)
        except requests.RequestException:
            return Response({"error": "verification_failed"}, status=status.HTTP_502_BAD_GATEWAY)

        if not installation_data or str(installation_data.get("app_id")) != str(credentials.app_id):
            return Response({"error": "installation_mismatch"}, status=status.HTTP_400_BAD_REQUEST)

        self._upsert_installation(workspace, installation_id, installation_data)

        web_url = base_host(request=request, is_app=True).rstrip("/")
        redirect_url = f"{web_url}/{workspace.slug}/settings/github/?{urlencode({'github': 'connected'})}"
        return HttpResponseRedirect(redirect_url)

    @staticmethod
    def _upsert_installation(workspace, installation_id, installation_data):
        account = installation_data.get("account") or {}
        fields = {
            "workspace": workspace,
            "account_login": account.get("login", ""),
            "account_type": account.get("type", ""),
            "account_avatar_url": account.get("avatar_url", ""),
            "repository_selection": installation_data.get("repository_selection", ""),
            "is_active": True,
            "suspended_at": None,
            "deleted_at": None,
            "last_synced_at": timezone.now(),
        }
        with transaction.atomic():
            installation = (
                GithubAppInstallation.all_objects.select_for_update()
                .filter(installation_id=installation_id)
                .first()
            )
            if installation is None:
                try:
                    with transaction.atomic():
                        installation = GithubAppInstallation.objects.create(installation_id=installation_id, **fields)
                        return installation
                except IntegrityError:
                    installation = GithubAppInstallation.all_objects.select_for_update().get(
                        installation_id=installation_id
                    )
            for key, value in fields.items():
                setattr(installation, key, value)
            installation.save()
            return installation


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
        # The repo picker enables/disables many repositories in one save; the
        # panel's original single-object POST keeps working unchanged.
        if isinstance(request.data, list):
            return self._bulk_upsert(installation, request.data)
        return self._create_single(installation, request.data)

    @staticmethod
    def _create_single(installation, data):
        serializer = GithubEnabledRepositorySerializer(data=data)
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
    def _bulk_upsert(installation, items):
        results = []
        errors = []
        with transaction.atomic():
            installation = GithubAppInstallation.objects.select_for_update().get(pk=installation.pk)
            for index, item in enumerate(items):
                serializer = GithubEnabledRepositorySerializer(data=item)
                if not serializer.is_valid():
                    errors.append({"index": index, "errors": serializer.errors})
                    continue
                validated = serializer.validated_data
                repo, _ = GithubEnabledRepository.objects.update_or_create(
                    installation=installation,
                    github_repository_id=validated["github_repository_id"],
                    defaults={
                        "full_name": validated["full_name"],
                        "is_enabled": validated.get("is_enabled", True),
                        "private": validated.get("private", False),
                        "default_branch": validated.get("default_branch", ""),
                        "html_url": validated.get("html_url", ""),
                    },
                )
                results.append(GithubEnabledRepositorySerializer(repo).data)
        if errors:
            return Response(
                {"results": results, "errors": errors},
                status=status.HTTP_207_MULTI_STATUS if results else status.HTTP_400_BAD_REQUEST,
            )
        return Response(results, status=status.HTTP_200_OK)

    @staticmethod
    def _get_installation(slug):
        return GithubAppInstallation.objects.filter(workspace__slug=slug, is_active=True).first()


class WorkspaceAvailableRepositoriesEndpoint(BaseAPIView):
    """Live view of every repository the installation can see, merged with
    this workspace's `GithubEnabledRepository` state. No cache table -- the
    repo picker is opened rarely enough that a direct GitHub call is fine."""

    @allow_permission([ROLE.ADMIN], level="WORKSPACE")
    def get(self, request, slug):
        installation = WorkspaceRepositoriesEndpoint._get_installation(slug)
        if not installation:
            return Response(
                {"error": "No active GitHub installation for this workspace."},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        try:
            repositories = GitHubClient.for_installation(installation.installation_id).list_installation_repositories()
        except requests.RequestException:
            return Response(
                {"error": "github_unavailable", "detail": "Could not reach GitHub. Please retry."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        enabled_by_repo_id = {
            repo.github_repository_id: repo
            for repo in GithubEnabledRepository.objects.filter(installation=installation)
        }

        def _is_enabled(repo_id):
            enabled_row = enabled_by_repo_id.get(repo_id)
            return bool(enabled_row and enabled_row.is_enabled)

        data = [
            {
                "github_repository_id": repo.get("id"),
                "full_name": repo.get("full_name", ""),
                "private": bool(repo.get("private", False)),
                "default_branch": repo.get("default_branch", ""),
                "html_url": repo.get("html_url", ""),
                "is_enabled": _is_enabled(repo.get("id")),
            }
            for repo in repositories
        ]
        installation.last_synced_at = timezone.now()
        installation.save(update_fields=["last_synced_at", "updated_at"])
        return Response(data, status=status.HTTP_200_OK)


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
