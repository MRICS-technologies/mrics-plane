# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Shared soft-delete for GitHub installations and everything under them.

Callers must pass a queryset/iterable of ``GithubAppInstallation`` -- never
call ``.delete()`` on these models: ``SoftDeleteModel.delete()`` dispatches
the ``soft_delete_related_objects`` Celery cascade (`plane/db/mixins.py:78`),
which is unrelated to and far broader than what disconnect/reset need. Every
row here is soft-deleted with a raw ``.update()`` instead.
"""

from django.db import transaction
from django.utils import timezone

from plane.db.models.integration.github_app import GithubAppInstallation, GithubEnabledRepository
from plane.db.models.integration.github_sync import IssueGitLink, RepoProjectMapping


def soft_delete_installations(installations, *, include_git_links: bool = False) -> dict:
    """Soft-delete `installations` plus their enabled repos and project
    mappings (and, if `include_git_links`, their issue git links).

    `installations` may be a `GithubAppInstallation` queryset or any plain
    iterable of instances (e.g. `[installation]`).

    Returns counts: `{"installations": n, "repositories": n, "mappings": n,
    "git_links": n}`.
    """
    now = timezone.now()

    with transaction.atomic():
        if hasattr(installations, "values_list"):
            inst_ids = list(installations.values_list("id", flat=True))
        else:
            inst_ids = [installation.id for installation in installations]
        if not inst_ids:
            return {"installations": 0, "repositories": 0, "mappings": 0, "git_links": 0}

        ws_ids = list(GithubAppInstallation.objects.filter(id__in=inst_ids).values_list("workspace_id", flat=True))
        repo_qs = GithubEnabledRepository.objects.filter(installation_id__in=inst_ids)
        repo_ids, repo_names = zip(*repo_qs.values_list("id", "full_name")) if repo_qs.exists() else ((), ())

        mapping_count = RepoProjectMapping.all_objects.filter(
            deleted_at__isnull=True, repository__installation_id__in=inst_ids
        ).update(deleted_at=now, updated_at=now)

        git_link_count = 0
        if include_git_links:
            git_link_count = IssueGitLink.all_objects.filter(
                deleted_at__isnull=True, workspace_id__in=ws_ids, github_repo__in=repo_names
            ).update(deleted_at=now, updated_at=now)

        GithubEnabledRepository.all_objects.filter(id__in=repo_ids).update(deleted_at=now, updated_at=now)
        GithubAppInstallation.all_objects.filter(id__in=inst_ids).update(
            is_active=False, deleted_at=now, updated_at=now
        )

        return {
            "installations": len(inst_ids),
            "repositories": len(repo_ids),
            "mappings": mapping_count,
            "git_links": git_link_count,
        }
