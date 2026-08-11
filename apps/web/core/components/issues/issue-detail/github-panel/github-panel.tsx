/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
import useSWR from "swr";
import { Github } from "lucide-react";
import { GITHUB_ISSUE_GIT_LINKS_KEY, GITHUB_PROJECT_MAPPINGS_KEY } from "@plane/constants";
import { useTranslation } from "@plane/i18n";
import { useIssueDetail } from "@/hooks/store/use-issue-detail";
import { useProject } from "@/hooks/store/use-project";
import { GithubSyncService } from "@/services/github-sync.service";
import { CreateBranchButton } from "./create-branch-button";
import { GitLinkItem } from "./git-link-item";

const githubSyncService = new GithubSyncService();

const slugify = (value: string) =>
  value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");

type Props = {
  workspaceSlug: string;
  projectId: string;
  issueId: string;
  disabled?: boolean;
};

export const GitHubPanel = observer(function GitHubPanel(props: Props) {
  const { workspaceSlug, projectId, issueId, disabled } = props;
  const { t } = useTranslation();
  const { getProjectIdentifierById } = useProject();
  const {
    issue: { getIssueById },
  } = useIssueDetail();

  const issue = getIssueById(issueId);
  const projectIdentifier = getProjectIdentifierById(projectId);
  const issueIdentifier = projectIdentifier && issue?.sequence_id ? `${projectIdentifier}-${issue.sequence_id}` : "";

  const { data: mappings, isLoading: isMappingsLoading } = useSWR(
    workspaceSlug && projectId ? GITHUB_PROJECT_MAPPINGS_KEY(workspaceSlug, projectId) : null,
    workspaceSlug && projectId ? () => githubSyncService.getMappings(workspaceSlug, projectId) : null
  );

  const {
    data: gitLinks,
    isLoading: isGitLinksLoading,
    mutate: mutateGitLinks,
  } = useSWR(
    workspaceSlug && projectId && issueId ? GITHUB_ISSUE_GIT_LINKS_KEY(workspaceSlug, projectId, issueId) : null,
    workspaceSlug && projectId && issueId
      ? () => githubSyncService.getGitLinks(workspaceSlug, projectId, issueId)
      : null
  );

  const suggestedBranchName = `feature/${slugify(`${issueIdentifier}-${issue?.name ?? ""}`)}`;

  const isLoading = isMappingsLoading || isGitLinksLoading;
  const hasMapping = Boolean(mappings && mappings.length > 0);
  const hasGitLinks = Boolean(gitLinks && gitLinks.length > 0);

  // Hijazi's call for Phase 1 1.5c: an unmapped project hides branch
  // creation entirely (no hint, no disabled state) rather than nudging --
  // the nudge lives in project settings instead. If there is nothing to
  // show and nothing actionable, the panel renders nothing. N10: don't know
  // which case this is until loading finishes, so render nothing (not a
  // header + skeleton) while loading rather than flashing the header on
  // every open of an unmapped project's work item.
  if (isLoading) return null;
  if (!hasGitLinks && (!hasMapping || disabled)) return null;

  return (
    <div className="border-t border-subtle-1 pt-2.5">
      <h6 className="flex items-center gap-1.5 text-body-xs-medium">
        <Github className="size-3.5" />
        {t("work_item.github.label")}
      </h6>
      <div className="mt-2 space-y-2">
        {hasGitLinks && (
          <div className="space-y-1.5">
            {gitLinks?.map((link) => (
              <GitLinkItem key={link.id} link={link} />
            ))}
          </div>
        )}

        {hasMapping && !disabled && (
          <CreateBranchButton
            workspaceSlug={workspaceSlug}
            projectId={projectId}
            issueId={issueId}
            suggestedBranchName={suggestedBranchName}
            mappings={mappings ?? []}
            onCreated={() => mutateGitLinks()}
          />
        )}
      </div>
    </div>
  );
});
