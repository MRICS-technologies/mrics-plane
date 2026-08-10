# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import json
import uuid

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.core.cache import cache
from django.utils import timezone
from rest_framework import status

from plane.license.models import Instance, InstanceAdmin, InstanceConfiguration

GITHUB_APP_URL = "/api/instances/github-app/"
GITHUB_APP_TEST_URL = "/api/instances/github-app/test/"
CONFIGURATIONS_URL = "/api/instances/configurations/"


@pytest.fixture
def instance_admin_client(api_client, create_user):
    instance = Instance.objects.create(
        instance_name="GitHub App Test Instance",
        instance_id=str(uuid.uuid4()),
        current_version="1.0.0",
        domain="http://localhost:8000",
        last_checked_at=timezone.now(),
    )
    InstanceAdmin.objects.create(instance=instance, user=create_user, role=20)
    api_client.force_authenticate(user=create_user)
    cache.clear()
    return api_client


@pytest.fixture
def private_key():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()


def github_app_payload(private_key):
    return {
        "GITHUB_APP_ID": "123456",
        "GITHUB_APP_SLUG": "plane-test-app",
        "GITHUB_APP_PRIVATE_KEY": private_key,
        "GITHUB_APP_WEBHOOK_SECRET": "webhook-secret-for-test",
        "GITHUB_APP_CLIENT_ID": "client-id-for-test",
        "GITHUB_APP_CLIENT_SECRET": "client-secret-for-test",
        "GITHUB_APP_GITHUB_BASE_URL": "https://api.github.com",
        "GITHUB_APP_HTML_BASE_URL": "https://github.com",
        "GITHUB_APP_ENABLED": True,
    }


@pytest.mark.contract
class TestGitHubAppConfigurationAPI:
    @pytest.mark.django_db
    def test_admin_write_read_and_local_test_do_not_disclose_secrets(self, instance_admin_client, private_key):
        payload = github_app_payload(private_key)
        response = instance_admin_client.patch(GITHUB_APP_URL, payload, format="json")

        assert response.status_code == status.HTTP_200_OK
        ciphertext = InstanceConfiguration.objects.get(key="GITHUB_APP_PRIVATE_KEY").value
        assert InstanceConfiguration.objects.get(key="GITHUB_APP_PRIVATE_KEY").is_encrypted is True
        for response_body in (response.content.decode(),):
            assert private_key not in response_body
            assert payload["GITHUB_APP_WEBHOOK_SECRET"] not in response_body
            assert payload["GITHUB_APP_CLIENT_SECRET"] not in response_body
            assert ciphertext not in response_body
        assert response.data["private_key"]["configured"] is True
        assert response.data["private_key"]["fingerprint"].startswith("hmac-sha256:")

        for url, method in ((GITHUB_APP_URL, "get"), (GITHUB_APP_TEST_URL, "post")):
            response = getattr(instance_admin_client, method)(url, format="json")
            assert response.status_code == status.HTTP_200_OK
            response_body = response.content.decode()
            assert private_key not in response_body
            assert payload["GITHUB_APP_WEBHOOK_SECRET"] not in response_body
            assert payload["GITHUB_APP_CLIENT_SECRET"] not in response_body
            assert ciphertext not in response_body
        assert response.data["valid"] is True

    @pytest.mark.django_db
    def test_non_admin_is_forbidden(self, api_client, create_user):
        instance = Instance.objects.create(
            instance_name="GitHub App Test Instance",
            instance_id=str(uuid.uuid4()),
            current_version="1.0.0",
            domain="http://localhost:8000",
            last_checked_at=timezone.now(),
        )
        assert instance
        api_client.force_authenticate(user=create_user)

        assert api_client.get(GITHUB_APP_URL).status_code == status.HTTP_403_FORBIDDEN
        assert api_client.patch(GITHUB_APP_URL, {"GITHUB_APP_ID": "123456"}, format="json").status_code == (
            status.HTTP_403_FORBIDDEN
        )
        assert api_client.post(GITHUB_APP_TEST_URL, format="json").status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.django_db
    def test_generic_configuration_never_reads_or_writes_app_records_and_oauth_is_untouched(
        self, instance_admin_client, private_key
    ):
        InstanceConfiguration.objects.create(
            key="GITHUB_CLIENT_SECRET",
            value="oauth-login-secret",
            category="AUTHENTICATION",
            is_encrypted=True,
        )
        instance_admin_client.patch(GITHUB_APP_URL, github_app_payload(private_key), format="json")
        original_webhook = InstanceConfiguration.objects.get(key="GITHUB_APP_WEBHOOK_SECRET").value

        response = instance_admin_client.get(CONFIGURATIONS_URL)
        assert response.status_code == status.HTTP_200_OK
        assert all(not item["key"].startswith("GITHUB_APP_") for item in response.data)

        response = instance_admin_client.patch(
            CONFIGURATIONS_URL,
            {"GITHUB_APP_WEBHOOK_SECRET": "attempted-generic-overwrite"},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data == []
        assert InstanceConfiguration.objects.get(key="GITHUB_APP_WEBHOOK_SECRET").value == original_webhook

        response = instance_admin_client.patch(
            GITHUB_APP_URL,
            {"GITHUB_CLIENT_SECRET": "attempted-oauth-overwrite"},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "attempted-oauth-overwrite" not in response.content.decode()
        assert InstanceConfiguration.objects.get(key="GITHUB_CLIENT_SECRET").value == "oauth-login-secret"

    @pytest.mark.django_db
    def test_partial_update_preserves_secrets_and_delete_only_removes_app_records(
        self, instance_admin_client, private_key
    ):
        InstanceConfiguration.objects.create(
            key="GITHUB_CLIENT_ID",
            value="oauth-login-client-id",
            category="AUTHENTICATION",
        )
        instance_admin_client.patch(GITHUB_APP_URL, github_app_payload(private_key), format="json")
        response = instance_admin_client.patch(GITHUB_APP_URL, {"GITHUB_APP_SLUG": "rotated-slug"}, format="json")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["app_slug"] == "rotated-slug"
        assert response.data["private_key"]["configured"] is True
        assert response.data["webhook_secret"]["configured"] is True
        assert response.data["client_secret"]["configured"] is True

        response = instance_admin_client.patch(GITHUB_APP_URL, {"GITHUB_APP_WEBHOOK_SECRET": ""}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

        response = instance_admin_client.delete(GITHUB_APP_URL)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["configured"] is False
        assert response.data["enabled"] is False
        assert not InstanceConfiguration.objects.filter(key__startswith="GITHUB_APP_").exists()
        assert InstanceConfiguration.objects.get(key="GITHUB_CLIENT_ID").value == "oauth-login-client-id"

    @pytest.mark.django_db
    def test_delete_hard_deletes_and_reconfigure_after_delete_succeeds(self, instance_admin_client, private_key):
        payload = github_app_payload(private_key)
        instance_admin_client.patch(GITHUB_APP_URL, payload, format="json")
        ciphertext = InstanceConfiguration.all_objects.get(key="GITHUB_APP_PRIVATE_KEY").value

        response = instance_admin_client.delete(GITHUB_APP_URL)
        assert response.status_code == status.HTTP_200_OK

        # Hard delete: no row survives, even through the manager that would
        # still see a merely soft-deleted (deleted_at set) record.
        assert not InstanceConfiguration.all_objects.filter(key__startswith="GITHUB_APP_").exists()
        assert not InstanceConfiguration.all_objects.filter(value=ciphertext).exists()

        # Reconfiguring after delete must recreate a working config rather than
        # colliding with a retained record on the unique `key` constraint.
        response = instance_admin_client.patch(GITHUB_APP_URL, payload, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["configured"] is True
        assert InstanceConfiguration.objects.get(key="GITHUB_APP_PRIVATE_KEY").value != ciphertext

    @pytest.mark.django_db
    def test_missing_or_malformed_configuration_fails_without_disclosing_secret(self, instance_admin_client):
        response = instance_admin_client.post(GITHUB_APP_TEST_URL, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

        malformed_private_key = "not-a-private-key"
        response = instance_admin_client.patch(
            GITHUB_APP_URL,
            {"GITHUB_APP_ID": "123456", "GITHUB_APP_PRIVATE_KEY": malformed_private_key},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        response = instance_admin_client.post(GITHUB_APP_TEST_URL, format="json")
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert malformed_private_key not in response.content.decode()

        response = instance_admin_client.patch(GITHUB_APP_URL, {"unexpected": "value"}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "value" not in json.dumps(response.data)

    @pytest.mark.django_db
    def test_app_slug_round_trips_through_the_credentials_bridge(self, instance_admin_client, private_key):
        # P1 1.1: GITHUB_APP_SLUG must reach plane.services.github.credentials
        # (the install URL {html_base}/apps/{slug}/installations/new needs it)
        # not just the license serializer response.
        from plane.services.github.credentials import get_github_app_credentials

        payload = github_app_payload(private_key)
        response = instance_admin_client.patch(GITHUB_APP_URL, payload, format="json")
        assert response.status_code == status.HTTP_200_OK

        response = instance_admin_client.get(GITHUB_APP_URL)
        assert response.data["app_slug"] == payload["GITHUB_APP_SLUG"]

        credentials = get_github_app_credentials()
        assert credentials.app_slug == payload["GITHUB_APP_SLUG"]
