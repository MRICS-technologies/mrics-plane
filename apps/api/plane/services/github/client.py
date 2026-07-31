# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Python imports
import time

# Third party imports
import jwt
import requests

from plane.services.github.credentials import (
    DEFAULT_GITHUB_API_BASE_URL,
    DEFAULT_GITHUB_HTML_BASE_URL,
    get_github_app_credentials,
)


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

    def _app_jwt(self):
        if not self.app_id or not self.private_key:
            # ponytail: MVP stub, full GitHub App auth wired up when the app is provisioned
            raise NotImplementedError("GitHub App is not configured (missing app id/private key)")

        now = int(time.time())
        payload = {"iat": now - 60, "exp": now + 540, "iss": self.app_id}
        return jwt.encode(payload, self.private_key, algorithm="RS256")

    def get_installation_token(self):
        if not self.installation_id:
            raise NotImplementedError("GitHub App installation is not configured")

        response = requests.post(
            f"{self.github_base_url}/app/installations/{self.installation_id}/access_tokens",
            headers={
                "Authorization": f"Bearer {self._app_jwt()}",
                "Accept": "application/vnd.github+json",
            },
            timeout=10,
        )
        response.raise_for_status()
        return response.json()["token"]

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.get_installation_token()}",
            "Accept": "application/vnd.github+json",
        }

    def get_branch_sha(self, owner, repo, branch):
        response = requests.get(
            f"{self.github_base_url}/repos/{owner}/{repo}/git/ref/heads/{branch}",
            headers=self._headers(),
            timeout=10,
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()["object"]["sha"]

    def create_branch(self, owner, repo, branch_name, base_branch):
        base_sha = self.get_branch_sha(owner, repo, base_branch)
        if not base_sha:
            raise ValueError(f"Base branch '{base_branch}' not found in {owner}/{repo}")

        response = requests.post(
            f"{self.github_base_url}/repos/{owner}/{repo}/git/refs",
            headers=self._headers(),
            json={"ref": f"refs/heads/{branch_name}", "sha": base_sha},
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
        return {
            "branch_name": branch_name,
            "url": f"{self.html_base_url}/{owner}/{repo}/tree/{branch_name}",
            "sha": data["object"]["sha"],
        }
