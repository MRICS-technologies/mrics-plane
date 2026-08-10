# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Python imports
import time

# Third party imports
import jwt
import requests
from django.core.cache import cache

from plane.services.github.credentials import (
    DEFAULT_GITHUB_API_BASE_URL,
    DEFAULT_GITHUB_HTML_BASE_URL,
    get_github_app_credentials,
)

# Cached below the GitHub-issued lifetime (app JWT: 10 min, installation
# token: 1 hour) so a client never presents an expired credential, and
# shared via django.core.cache (Redis) across web + Celery workers so
# concurrent calls don't each mint their own token.
APP_JWT_CACHE_TTL = 540
INSTALLATION_TOKEN_CACHE_TTL = 3000

# `GET /installation/repositories` is paginated at 100/page; this is a hard
# safety cap on runaway pagination, not an expected real-world ceiling.
MAX_INSTALLATION_REPOSITORY_PAGES = 100


def _app_jwt_cache_key(app_id):
    return f"github:app_jwt:{app_id}"


def _installation_token_cache_key(installation_id):
    return f"github:installation_token:{installation_id}"


class GitHubClient:
    """Thin wrapper around the GitHub App / REST API used for branch automation."""

    def __init__(
        self,
        app_id,
        private_key,
        installation_id,
        github_base_url=DEFAULT_GITHUB_API_BASE_URL,
        html_base_url=DEFAULT_GITHUB_HTML_BASE_URL,
    ):
        self.app_id = app_id
        self.private_key = private_key
        self.installation_id = installation_id
        self.github_base_url = github_base_url or DEFAULT_GITHUB_API_BASE_URL
        self.html_base_url = html_base_url or DEFAULT_GITHUB_HTML_BASE_URL

    @classmethod
    def for_installation(cls, installation_id):
        """Build a client from the P1 instance GitHub App configuration
        (the source of truth), for a given GitHub App installation id."""
        credentials = get_github_app_credentials()
        return cls(
            credentials.app_id,
            credentials.private_key,
            installation_id,
            credentials.github_base_url,
            credentials.html_base_url,
        )

    @classmethod
    def convert_manifest(cls, code, github_base_url=DEFAULT_GITHUB_API_BASE_URL):
        """Exchange a GitHub App manifest flow `code` for the app's credentials.
        Unauthenticated: the one-time `code` itself is the secret."""
        response = requests.post(
            f"{github_base_url}/app-manifests/{code}/conversions",
            headers={"Accept": "application/vnd.github+json"},
            timeout=10,
        )
        response.raise_for_status()
        return response.json()

    def _app_jwt(self):
        if not self.app_id or not self.private_key:
            # ponytail: MVP stub, full GitHub App auth wired up when the app is provisioned
            raise NotImplementedError("GitHub App is not configured (missing app id/private key)")

        cache_key = _app_jwt_cache_key(self.app_id)
        token = cache.get(cache_key)
        if token:
            return token

        now = int(time.time())
        payload = {"iat": now - 60, "exp": now + APP_JWT_CACHE_TTL, "iss": self.app_id}
        token = jwt.encode(payload, self.private_key, algorithm="RS256")
        cache.set(cache_key, token, APP_JWT_CACHE_TTL)
        return token

    def _app_headers(self):
        return {
            "Authorization": f"Bearer {self._app_jwt()}",
            "Accept": "application/vnd.github+json",
        }

    def get_installation(self, installation_id):
        """`GET /app/installations/{id}` -- used to verify that a GitHub-supplied
        installation id actually belongs to this app before trusting it."""
        response = requests.get(
            f"{self.github_base_url}/app/installations/{installation_id}",
            headers=self._app_headers(),
            timeout=10,
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()

    def get_installation_token(self):
        if not self.installation_id:
            raise NotImplementedError("GitHub App installation is not configured")

        cache_key = _installation_token_cache_key(self.installation_id)
        token = cache.get(cache_key)
        if token:
            return token

        response = requests.post(
            f"{self.github_base_url}/app/installations/{self.installation_id}/access_tokens",
            headers=self._app_headers(),
            timeout=10,
        )
        response.raise_for_status()
        token = response.json()["token"]
        cache.set(cache_key, token, INSTALLATION_TOKEN_CACHE_TTL)
        return token

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.get_installation_token()}",
            "Accept": "application/vnd.github+json",
        }

    def _request(self, method, url, **kwargs):
        """Issue an installation-token-authenticated request, retrying exactly
        once (after invalidating the cached token) on a 401."""
        kwargs.setdefault("timeout", 10)
        response = requests.request(method, url, headers=self._headers(), **kwargs)
        if response.status_code == 401:
            cache.delete(_installation_token_cache_key(self.installation_id))
            response = requests.request(method, url, headers=self._headers(), **kwargs)
        return response

    def list_installation_repositories(self):
        """`GET /installation/repositories`, paginated at 100/page."""
        repositories = []
        for page in range(1, MAX_INSTALLATION_REPOSITORY_PAGES + 1):
            response = self._request(
                "GET",
                f"{self.github_base_url}/installation/repositories",
                params={"per_page": 100, "page": page},
            )
            response.raise_for_status()
            page_repositories = response.json().get("repositories", [])
            repositories.extend(page_repositories)
            if len(page_repositories) < 100:
                break
        return repositories

    def get_branch_sha(self, owner, repo, branch):
        response = self._request("GET", f"{self.github_base_url}/repos/{owner}/{repo}/git/ref/heads/{branch}")
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()["object"]["sha"]

    def create_branch(self, owner, repo, branch_name, base_branch):
        base_sha = self.get_branch_sha(owner, repo, base_branch)
        if not base_sha:
            raise ValueError(f"Base branch '{base_branch}' not found in {owner}/{repo}")

        response = self._request(
            "POST",
            f"{self.github_base_url}/repos/{owner}/{repo}/git/refs",
            json={"ref": f"refs/heads/{branch_name}", "sha": base_sha},
        )
        response.raise_for_status()
        data = response.json()
        return {
            "branch_name": branch_name,
            "url": f"{self.html_base_url}/{owner}/{repo}/tree/{branch_name}",
            "sha": data["object"]["sha"],
        }
