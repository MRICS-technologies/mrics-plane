# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Read-only bridge onto the P1 instance GitHub App configuration.

The instance-admin `GITHUB_APP_*` `InstanceConfiguration` rows (see
`plane.license.api.views.github_app`) are the single source of truth for the
GitHub client and sync/webhook views -- not environment variables. This
module never logs or returns raw credential values to a caller that didn't
already have them; on any absent or undecryptable configuration it returns
safe falsy values instead of raising.
"""

from dataclasses import dataclass, field

from plane.license.models import InstanceConfiguration
from plane.license.utils.encryption import decrypt_data

DEFAULT_GITHUB_API_BASE_URL = "https://api.github.com"
DEFAULT_GITHUB_HTML_BASE_URL = "https://github.com"

_SECRET_KEYS = {"GITHUB_APP_PRIVATE_KEY", "GITHUB_APP_WEBHOOK_SECRET", "GITHUB_APP_CLIENT_SECRET"}
_PUBLIC_KEYS = {
    "GITHUB_APP_ID",
    "GITHUB_APP_CLIENT_ID",
    "GITHUB_APP_GITHUB_BASE_URL",
    "GITHUB_APP_HTML_BASE_URL",
    "GITHUB_APP_ENABLED",
}
_ALL_KEYS = _SECRET_KEYS | _PUBLIC_KEYS


@dataclass(frozen=True)
class GitHubAppCredentials:
    app_id: str = ""
    # repr=False so an accidental log/print of this object can't leak a
    # secret through its default dataclass repr.
    private_key: str = field(default="", repr=False)
    webhook_secret: str = field(default="", repr=False)
    client_id: str = ""
    client_secret: str = field(default="", repr=False)
    github_base_url: str = DEFAULT_GITHUB_API_BASE_URL
    html_base_url: str = DEFAULT_GITHUB_HTML_BASE_URL
    enabled: bool = False

    def __bool__(self):
        """A usable app must have both an identity and a signing key."""
        return bool(self.app_id and self.private_key)


def get_github_app_credentials():
    """Return the configured `GitHubAppCredentials`, or an all-falsy instance
    if the GitHub App is not configured, partially configured, or a stored
    secret can no longer be decrypted (e.g. after a `SECRET_KEY` rotation).
    """
    configs = {c.key: c for c in InstanceConfiguration.objects.filter(key__in=_ALL_KEYS)}

    def public_value(key):
        config = configs.get(key)
        return config.value if config and config.value else ""

    def secret_value(key):
        config = configs.get(key)
        if not config or not config.value:
            return ""
        # decrypt_data already returns "" on any decryption failure.
        return decrypt_data(config.value)

    return GitHubAppCredentials(
        app_id=public_value("GITHUB_APP_ID"),
        private_key=secret_value("GITHUB_APP_PRIVATE_KEY"),
        webhook_secret=secret_value("GITHUB_APP_WEBHOOK_SECRET"),
        client_id=public_value("GITHUB_APP_CLIENT_ID"),
        client_secret=secret_value("GITHUB_APP_CLIENT_SECRET"),
        github_base_url=public_value("GITHUB_APP_GITHUB_BASE_URL") or DEFAULT_GITHUB_API_BASE_URL,
        html_base_url=public_value("GITHUB_APP_HTML_BASE_URL") or DEFAULT_GITHUB_HTML_BASE_URL,
        enabled=public_value("GITHUB_APP_ENABLED") == "1",
    )
