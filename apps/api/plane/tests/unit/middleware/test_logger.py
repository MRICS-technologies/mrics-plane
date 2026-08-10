# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""
Unit tests for APITokenLogMiddleware.

Covers the credential-hygiene guarantees of the external API request logger:
- the raw API key is never persisted (a non-reversible hash is stored instead)
- sensitive request headers are redacted before being logged
"""

import hashlib
import hmac
from unittest.mock import Mock, patch

import pytest
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.http import HttpResponse
from django.test import RequestFactory

from plane.middleware.logger import APITokenLogMiddleware


@pytest.fixture
def request_factory():
    return RequestFactory()


@pytest.fixture
def middleware():
    return APITokenLogMiddleware(Mock(return_value=HttpResponse(b"{}")))


@pytest.mark.unit
class TestAPITokenLogMiddleware:
    API_KEY = "plane_api_supersecretvalue"
    AUTHORIZATION = "Bearer secret-bearer-token"
    COOKIE = "sessionid=secret-session-value"

    def _captured_log_data(self, middleware, request_factory):
        request = request_factory.get(
            "/api/v1/workspaces/",
            HTTP_X_API_KEY=self.API_KEY,
            HTTP_AUTHORIZATION=self.AUTHORIZATION,
            HTTP_COOKIE=self.COOKIE,
        )
        request.user = AnonymousUser()
        response = HttpResponse(b"{}")
        with patch("plane.middleware.logger.process_logs") as process_logs:
            middleware.process_request(request, response, request_body=b"")
            assert process_logs.delay.called
            return process_logs.delay.call_args.kwargs["log_data"]

    def test_token_identifier_is_hashed_not_plaintext(self, middleware, request_factory):
        log_data = self._captured_log_data(middleware, request_factory)

        expected_hash = hmac.new(
            settings.SECRET_KEY.encode(), self.API_KEY.encode(), hashlib.sha256
        ).hexdigest()
        assert log_data["token_identifier"] == expected_hash
        assert self.API_KEY not in log_data["token_identifier"]

    def test_sensitive_headers_are_redacted(self, middleware, request_factory):
        log_data = self._captured_log_data(middleware, request_factory)

        # None of the sensitive header values may appear in the logged headers.
        assert self.API_KEY not in log_data["headers"]
        assert self.AUTHORIZATION not in log_data["headers"]
        assert self.COOKIE not in log_data["headers"]
        assert "[REDACTED]" in log_data["headers"]

    def test_no_log_without_api_key(self, middleware, request_factory):
        request = request_factory.get("/api/v1/workspaces/")
        request.user = AnonymousUser()
        with patch("plane.middleware.logger.process_logs") as process_logs:
            middleware.process_request(request, HttpResponse(b"{}"), request_body=b"")
            assert not process_logs.delay.called


@pytest.mark.unit
class TestAPITokenLogMiddlewareGitHubAppBodyExclusion:
    """
    GitHub App configuration requests/responses can carry a private key,
    webhook secret, or client secret in the body. That body must never reach
    process_logs.delay, regardless of the outcome of the request.
    """

    API_KEY = "plane_api_supersecretvalue"
    SENTINEL = "sentinel-private-key-webhook-client-secret-value"

    def _call(self, middleware, request_factory, path, method="patch", status_code=200):
        request = getattr(request_factory, method)(path, HTTP_X_API_KEY=self.API_KEY)
        request.user = AnonymousUser()
        response = HttpResponse(self.SENTINEL.encode(), status=status_code)
        with patch("plane.middleware.logger.process_logs") as process_logs:
            # request_body is read once by __call__ and handed to process_request;
            # simulate that here rather than round-tripping through RequestFactory.
            middleware.process_request(request, response, request_body=self.SENTINEL.encode())
            assert process_logs.delay.called
            return process_logs.delay.call_args.kwargs["log_data"]

    @pytest.mark.parametrize(
        ("path", "method", "status_code"),
        [
            ("/api/instances/github-app/", "patch", 200),  # success
            ("/api/instances/github-app/", "patch", 400),  # failed validation
            ("/api/instances/github-app/", "get", 403),  # forbidden
            ("/api/instances/github-app/", "delete", 401),  # unauthorized
            ("/api/instances/github-app/test/", "post", 422),  # subroute / test endpoint
            ("/api/instances/github-app", "patch", 200),  # slashless base path, success
            ("/api/instances/github-app", "patch", 400),  # slashless base path, failed validation
            ("/api/instances/github-app", "get", 403),  # slashless base path, forbidden
            ("/api/instances/github-app", "delete", 401),  # slashless base path, unauthorized
        ],
    )
    def test_github_app_body_never_queued(self, middleware, request_factory, path, method, status_code):
        log_data = self._call(middleware, request_factory, path, method=method, status_code=status_code)

        assert log_data["body"] is None
        assert log_data["response_body"] is None
        assert self.SENTINEL not in str(log_data)

    def test_github_app_body_excluded_via_full_middleware_call(self, request_factory):
        """
        Exercises __call__ (not just the process_request helper) so the
        exclusion is proven against the same code path Django actually runs,
        including the slashless request that CommonMiddleware would otherwise
        redirect/reject before this middleware finishes.
        """
        get_response = Mock(return_value=HttpResponse(self.SENTINEL.encode(), status=400))
        middleware = APITokenLogMiddleware(get_response)
        request = request_factory.patch(
            "/api/instances/github-app", HTTP_X_API_KEY=self.API_KEY, data=self.SENTINEL, content_type="text/plain"
        )
        request.user = AnonymousUser()
        with patch("plane.middleware.logger.process_logs") as process_logs:
            middleware(request)
            assert process_logs.delay.called
            log_data = process_logs.delay.call_args.kwargs["log_data"]

        assert log_data["body"] is None
        assert log_data["response_body"] is None
        assert self.SENTINEL not in str(log_data)

    def test_sibling_route_is_not_overmatched(self, middleware, request_factory):
        """
        A route that merely starts with the same characters (but is a
        different resource) must not be swept into the exclusion.
        """
        log_data = self._call(
            middleware, request_factory, "/api/instances/github-app-foo/", method="patch", status_code=200
        )

        assert log_data["body"] == self.SENTINEL
        assert log_data["response_body"] == self.SENTINEL

    def test_non_github_app_route_body_logging_is_unaffected(self, middleware, request_factory):
        log_data = self._call(middleware, request_factory, "/api/v1/workspaces/", method="patch", status_code=200)

        assert log_data["body"] == self.SENTINEL
        assert log_data["response_body"] == self.SENTINEL


    @pytest.mark.parametrize("path", ["/api/github/webhook", "/api/github/webhook/"])
    def test_public_github_webhook_body_and_signature_never_queued(self, middleware, request_factory, path):
        request = request_factory.post(
            path,
            data=self.SENTINEL,
            content_type="application/json",
            HTTP_X_API_KEY=self.API_KEY,
            HTTP_X_HUB_SIGNATURE_256="sha256=signature-must-not-be-persisted",
        )
        request.user = AnonymousUser()
        with patch("plane.middleware.logger.process_logs") as process_logs:
            middleware.process_request(
                request, HttpResponse(self.SENTINEL.encode()), request_body=self.SENTINEL.encode()
            )
            log_data = process_logs.delay.call_args.kwargs["log_data"]

        assert log_data["body"] is None
        assert log_data["response_body"] is None
        assert self.SENTINEL not in str(log_data)
        assert "signature-must-not-be-persisted" not in log_data["headers"]
