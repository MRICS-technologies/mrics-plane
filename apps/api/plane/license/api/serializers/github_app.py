# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import hashlib
import hmac

from django.conf import settings
from rest_framework import serializers

from plane.license.models import InstanceConfiguration
from plane.license.utils.encryption import decrypt_data

GITHUB_APP_CATEGORY = "GITHUB_APP"

# Secrets: encrypted at rest, never returned in plaintext/ciphertext (fingerprint only).
SECRET_KEYS = {
    "GITHUB_APP_PRIVATE_KEY",
    "GITHUB_APP_WEBHOOK_SECRET",
    "GITHUB_APP_CLIENT_SECRET",
}

# Public: safe to echo back as-is.
PUBLIC_KEYS = {
    "GITHUB_APP_ID",
    "GITHUB_APP_SLUG",
    "GITHUB_APP_CLIENT_ID",
    "GITHUB_APP_GITHUB_BASE_URL",
    "GITHUB_APP_HTML_BASE_URL",
    "GITHUB_APP_ENABLED",
}

ALLOWED_KEYS = SECRET_KEYS | PUBLIC_KEYS

# Belong to the "Login with GitHub" OAuth flow, not the GitHub App. Explicitly
# rejected so callers can't confuse the two credential sets.
OAUTH_LOGIN_KEYS = {"GITHUB_CLIENT_ID", "GITHUB_CLIENT_SECRET"}


def _fingerprint(plaintext):
    # Keyed to this instance's SECRET_KEY so the fingerprint can't be
    # precomputed or matched against a value from outside this Plane instance.
    return "hmac-sha256:" + hmac.new(settings.SECRET_KEY.encode(), plaintext.encode(), hashlib.sha256).hexdigest()[
        :16
    ]


def _timestamp(configuration):
    return configuration.updated_at.isoformat() if configuration else None


class GitHubAppConfigurationRequestSerializer(serializers.Serializer):
    GITHUB_APP_ID = serializers.CharField(required=False, allow_blank=False)
    GITHUB_APP_SLUG = serializers.CharField(required=False, allow_blank=False)
    GITHUB_APP_PRIVATE_KEY = serializers.CharField(
        required=False, allow_blank=False, trim_whitespace=False, write_only=True
    )
    GITHUB_APP_WEBHOOK_SECRET = serializers.CharField(required=False, allow_blank=False, write_only=True)
    GITHUB_APP_CLIENT_ID = serializers.CharField(required=False, allow_blank=False)
    GITHUB_APP_CLIENT_SECRET = serializers.CharField(required=False, allow_blank=False, write_only=True)
    GITHUB_APP_GITHUB_BASE_URL = serializers.CharField(required=False, allow_blank=False)
    GITHUB_APP_HTML_BASE_URL = serializers.CharField(required=False, allow_blank=False)
    GITHUB_APP_ENABLED = serializers.BooleanField(required=False)

    def validate(self, attrs):
        request_keys = set(self.initial_data.keys())
        unknown = request_keys - ALLOWED_KEYS
        oauth_login_keys = request_keys & OAUTH_LOGIN_KEYS
        if unknown or oauth_login_keys:
            disallowed = unknown | oauth_login_keys
            raise serializers.ValidationError(
                {"error": f"Unknown or disallowed configuration key(s): {', '.join(sorted(disallowed))}"}
            )
        empty_secrets = [key for key in SECRET_KEYS if key in attrs and not attrs[key].strip()]
        if empty_secrets:
            raise serializers.ValidationError({key: "A GitHub App secret cannot be empty." for key in empty_secrets})
        if not attrs:
            raise serializers.ValidationError({"error": "At least one GitHub App configuration value is required."})
        return attrs


def serialize_github_app_configuration():
    """Build the response body: flags/public values/timestamps and secret fingerprints only."""
    configs = {c.key: c for c in InstanceConfiguration.objects.filter(key__in=ALLOWED_KEYS)}

    def public_value(key):
        config = configs.get(key)
        return config.value if config and config.value else None

    def secret_meta(key):
        config = configs.get(key)
        if not config or not config.value:
            return {"configured": False, "fingerprint": None, "updated_at": None}
        plaintext = decrypt_data(config.value)
        if not plaintext:
            return {"configured": False, "fingerprint": None, "updated_at": None}
        return {
            "configured": True,
            "fingerprint": _fingerprint(plaintext),
            "updated_at": _timestamp(config),
        }

    latest_update = max((config.updated_at for config in configs.values()), default=None)
    has_app_identity = bool(public_value("GITHUB_APP_ID"))
    has_private_key = secret_meta("GITHUB_APP_PRIVATE_KEY")["configured"]

    return {
        "configured": has_app_identity and has_private_key,
        "enabled": public_value("GITHUB_APP_ENABLED") == "1",
        "app_id": public_value("GITHUB_APP_ID"),
        "app_slug": public_value("GITHUB_APP_SLUG"),
        "client_id": public_value("GITHUB_APP_CLIENT_ID"),
        "github_base_url": public_value("GITHUB_APP_GITHUB_BASE_URL"),
        "html_base_url": public_value("GITHUB_APP_HTML_BASE_URL"),
        "updated_at": latest_update.isoformat() if latest_update else None,
        "private_key": secret_meta("GITHUB_APP_PRIVATE_KEY"),
        "webhook_secret": secret_meta("GITHUB_APP_WEBHOOK_SECRET"),
        "client_secret": secret_meta("GITHUB_APP_CLIENT_SECRET"),
    }
