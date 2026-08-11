# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import time
from urllib.parse import quote, urlencode, urlsplit

import jwt
from jwt.exceptions import PyJWTError
from django.http import HttpResponseRedirect
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .base import BaseAPIView
from plane.authentication.utils.host import base_host
from plane.license.api.permissions import InstanceAdminPermission
from plane.license.api.serializers.github_app import (
    ALLOWED_KEYS,
    GITHUB_APP_CATEGORY,
    SECRET_KEYS,
    GitHubAppConfigurationRequestSerializer,
    serialize_github_app_configuration,
)
from plane.license.models import InstanceConfiguration
from plane.license.utils.encryption import decrypt_data, encrypt_data
from plane.services.github.client import GitHubClient
from plane.services.github.credentials import DEFAULT_GITHUB_HTML_BASE_URL
from plane.services.github.setup_state import consume as consume_setup_state, issue as issue_setup_state
from plane.utils.cache import invalidate_cache

# GitHub App manifest defaults (Phase 1 scope only): branch creation, reading
# repo metadata, and reading PRs for link correlation. No `administration`,
# no PR/issue write access.
#
# NOTE (GitHub manifest rules): `installation` and `installation_repositories`
# MUST NOT be listed in default_events -- GitHub rejects the manifest with
# "Default events unsupported" and delivers those lifecycle events to every
# app automatically.
MANIFEST_DEFAULT_PERMISSIONS = {"contents": "write", "metadata": "read", "pull_requests": "read"}
MANIFEST_DEFAULT_EVENTS = ["pull_request", "push"]


def _write_github_app_configuration(values):
    """Persist validated `GITHUB_APP_*` values through the single write path
    so encryption, category, and soft-delete-revival stay consistent whether
    the caller is the manual PATCH form or the automated manifest callback."""
    for key, value in values.items():
        if key == "GITHUB_APP_ENABLED":
            value = "1" if value else "0"
        elif isinstance(value, str):
            value = value.strip() if key not in SECRET_KEYS else value

        # Use all_objects (not the soft-delete-filtered default manager) so a
        # reconfigure after DELETE recreates a working row instead of hitting
        # the unique constraint on a retained, soft-deleted record.
        configuration, _ = InstanceConfiguration.all_objects.get_or_create(
            key=key,
            defaults={
                "category": GITHUB_APP_CATEGORY,
                "is_encrypted": key in SECRET_KEYS,
            },
        )
        configuration.category = GITHUB_APP_CATEGORY
        configuration.is_encrypted = key in SECRET_KEYS
        configuration.value = encrypt_data(value) if key in SECRET_KEYS else value
        configuration.deleted_at = None
        configuration.save(update_fields=["category", "is_encrypted", "value", "deleted_at", "updated_at"])


def _is_github_app_already_configured():
    configuration = InstanceConfiguration.objects.filter(key="GITHUB_APP_ID").first()
    return bool(configuration and configuration.value)


class GitHubAppConfigurationEndpoint(BaseAPIView):
    """Instance-admin-only, write-only storage for GitHub App credentials."""

    permission_classes = [InstanceAdminPermission]

    def get(self, request):
        return Response(serialize_github_app_configuration(), status=status.HTTP_200_OK)

    @invalidate_cache(path="/api/instances/configurations/", user=False)
    @invalidate_cache(path="/api/instances/", user=False)
    def patch(self, request):
        serializer = GitHubAppConfigurationRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        _write_github_app_configuration(serializer.validated_data)
        return Response(serialize_github_app_configuration(), status=status.HTTP_200_OK)

    @invalidate_cache(path="/api/instances/configurations/", user=False)
    @invalidate_cache(path="/api/instances/", user=False)
    def delete(self, request):
        # Hard-delete: InstanceConfiguration.key is unique, and the default
        # manager only soft-deletes (sets deleted_at). Soft-deleted rows would
        # keep the key occupied and break a subsequent PATCH reconfiguration.
        InstanceConfiguration.all_objects.filter(key__in=ALLOWED_KEYS).delete()
        return Response(serialize_github_app_configuration(), status=status.HTTP_200_OK)


class GitHubAppConfigurationTestEndpoint(BaseAPIView):
    """Validate the stored app key by constructing a local signed JWT only."""

    permission_classes = [InstanceAdminPermission]

    def post(self, request):
        configurations = {
            configuration.key: configuration
            for configuration in InstanceConfiguration.objects.filter(
                key__in={"GITHUB_APP_ID", "GITHUB_APP_PRIVATE_KEY"}
            )
        }
        app_id = configurations.get("GITHUB_APP_ID")
        private_key = configurations.get("GITHUB_APP_PRIVATE_KEY")
        if not app_id or not app_id.value or not private_key or not private_key.value:
            return Response(
                {"error": "GitHub App ID and private key must be configured before testing."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        private_key_value = decrypt_data(private_key.value)
        if not private_key_value:
            return Response(
                {"error": "GitHub App configuration is invalid."},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        now = int(time.time())
        payload = {"iat": now - 60, "exp": now + 540, "iss": app_id.value}
        try:
            # Signing successfully with RS256 is itself the proof that the
            # stored value is a usable RSA private key. This only proves local
            # signing capability -- it does not contact GitHub or validate the
            # app credentials remotely.
            jwt.encode(payload, private_key_value, algorithm="RS256")
        except (PyJWTError, TypeError, ValueError):
            return Response(
                {"error": "GitHub App configuration is invalid."},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        return Response(
            {"valid": True, "configuration": serialize_github_app_configuration()},
            status=status.HTTP_200_OK,
        )


class GitHubAppManifestEndpoint(BaseAPIView):
    """Instance-admin-only: build the one-time GitHub App manifest + state for
    the "Automated setup" flow (Coolify pattern). Never contacts GitHub -- the
    browser POSTs the manifest straight to GitHub via a hidden auto-submit form."""

    permission_classes = [InstanceAdminPermission]

    def post(self, request):
        if _is_github_app_already_configured():
            return Response(
                {"error": "already_configured", "detail": "A GitHub App is already configured on this instance."},
                status=status.HTTP_403_FORBIDDEN,
            )

        public_base_url = (request.data.get("public_base_url") or "").strip()
        base_url = public_base_url.rstrip("/") if public_base_url else request.build_absolute_uri("/").rstrip("/")
        html_base_url = (request.data.get("html_base_url") or DEFAULT_GITHUB_HTML_BASE_URL).rstrip("/")
        organization = (request.data.get("organization") or "").strip()

        state = issue_setup_state("manifest", user_id=str(request.user.id))
        hostname = urlsplit(base_url).hostname or "instance"

        manifest = {
            "name": f"Plane ({hostname})"[:34],
            "url": base_url,
            "hook_attributes": {"url": f"{base_url}/api/github/webhook/"},
            "redirect_url": f"{base_url}/api/instances/github-app/manifest/callback/",
            "setup_url": f"{base_url}/api/github/setup/",
            "setup_on_update": True,
            "public": False,
            "request_oauth_on_install": False,
            "default_permissions": MANIFEST_DEFAULT_PERMISSIONS,
            "default_events": MANIFEST_DEFAULT_EVENTS,
        }
        post_url = (
            f"{html_base_url}/organizations/{quote(organization)}/settings/apps/new"
            if organization
            else f"{html_base_url}/settings/apps/new"
        )

        return Response({"manifest": manifest, "post_url": post_url, "state": state}, status=status.HTTP_200_OK)


class GitHubAppManifestCallbackEndpoint(BaseAPIView):
    """`AllowAny` + state-gated: GitHub redirects the admin's browser here with
    a one-time `code` after the manifest is submitted. State validation must
    fully gate this endpoint since it is otherwise unauthenticated."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def _redirect_to_admin(self, request, github_app_status):
        admin_url = (base_host(request=request, is_admin=True) or "").rstrip("/")
        if not admin_url:
            # No usable host header (tests / misconfigured proxy): stay
            # relative so the browser remains on the admin app.
            return HttpResponseRedirect(f"/github-app/?{urlencode({'github_app': github_app_status})}")
        return HttpResponseRedirect(f"{admin_url}/github-app/?{urlencode({'github_app': github_app_status})}")

    def get(self, request):
        state = request.query_params.get("state", "")
        code = request.query_params.get("code", "")

        # State is checked, and burned, before any GitHub call or persistence.
        # N4: every failure here redirects to the admin app, never a raw JSON
        # body -- this endpoint is only ever reached via a GitHub browser
        # redirect, so JSON would render as an unstyled error page.
        claim = consume_setup_state(state, "manifest")
        if not claim:
            return self._redirect_to_admin(request, "invalid_state")

        if _is_github_app_already_configured():
            return self._redirect_to_admin(request, "already_configured")

        if not code:
            return self._redirect_to_admin(request, "missing_code")

        try:
            data = GitHubClient.convert_manifest(code)
        except Exception:
            return self._redirect_to_admin(request, "conversion_failed")

        if not data.get("id") or not data.get("pem"):
            return self._redirect_to_admin(request, "conversion_failed")

        _write_github_app_configuration(
            {
                "GITHUB_APP_ID": str(data.get("id")),
                "GITHUB_APP_SLUG": data.get("slug") or "",
                "GITHUB_APP_CLIENT_ID": data.get("client_id") or "",
                "GITHUB_APP_CLIENT_SECRET": data.get("client_secret") or "",
                "GITHUB_APP_PRIVATE_KEY": data.get("pem") or "",
                "GITHUB_APP_WEBHOOK_SECRET": data.get("webhook_secret") or "",
                "GITHUB_APP_ENABLED": True,
            }
        )

        return self._redirect_to_admin(request, "connected")
