# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""One-time state tokens for the GitHub App manifest/install browser round trips
(Coolify pattern). No model, no migration -- state lives in the cache only, is
single-use, and binds the caller-supplied identity so a completed or replayed
callback can never be reattached to a different admin/workspace/user."""

import hashlib
import secrets

from django.core.cache import cache
from django.utils import timezone

STATE_TTL_SECONDS = 900
_CACHE_PREFIX = "github:setup_state:"


def _cache_key(state):
    # Hash the state before using it as a cache key so the raw, sensitive
    # token value is never itself stored verbatim as a Redis key.
    return _CACHE_PREFIX + hashlib.sha256(state.encode()).hexdigest()


def issue(action, **binding):
    """Mint a single-use state token bound to `action` and the given claims
    (e.g. `user_id`, or `workspace_id`/`user_id`/`redirect`). `issued_at`
    anchors the fresh-install window check in the setup callback."""
    state = secrets.token_urlsafe(32)
    cache.set(
        _cache_key(state),
        {"action": action, "issued_at": timezone.now().isoformat(), **binding},
        STATE_TTL_SECONDS,
    )
    return state


def consume(state, expected_action):
    """Redeem a state token: returns the bound claims once, or None if the
    token is missing, expired, already consumed, or bound to a different
    action. A state bound to a different action is left untouched so it
    remains redeemable by the flow it was actually issued for; only a
    matching-action token is deleted, which is what makes replay impossible."""
    if not state:
        return None
    key = _cache_key(state)
    payload = cache.get(key)
    if not payload:
        return None
    if payload.get("action") != expected_action:
        return None
    cache.delete(key)
    return {k: v for k, v in payload.items() if k != "action"}
