# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import time

import jwt
from jwt.exceptions import PyJWTError
from rest_framework import status
from rest_framework.response import Response

from .base import BaseAPIView
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
from plane.utils.cache import invalidate_cache


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

        for key, value in serializer.validated_data.items():
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
