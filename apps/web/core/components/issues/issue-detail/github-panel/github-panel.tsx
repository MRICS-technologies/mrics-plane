/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
import useSWR from "swr";
import { Github } from "lucide-react";
import { Loader } from "@plane/ui";
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
};

export const GitHubPanel = observer(function GitHubPanel(props: Props) {
  const { workspaceSlug, projectId, issueId } = props;
  const { getProjectIdentifierById } = useProject();
  const {
    issue: { getIssueById },
  } = useIssueDetail();

  const issue = getIssueById(issueId);
  const projectIdentifier = getProjectIdentifierById(projectId);
  const issueIdentifier = projectIdentifier && issue?.sequence_id ? `${projectIdentifier}-${issue.sequence_id}` : "";

  const { data: mappings, isLoading: isMappingsLoading } = useSWR(
    workspaceSlug && projectId ? `GITHUB_MAPPINGS_${workspaceSlug}_${projectId}` : null,
    workspaceSlug && projectId ? () => githubSyncService.getMappings(workspaceSlug, projectId) : null
  );

  const {
    data: gitLinks,
    isLoading: isGitLinksLoading,
    mutate: mutateGitLinks,
  } = useSWR(
    workspaceSlug && projectId && issueId ? `GITHUB_GIT_LINKS_${workspaceSlug}_${projectId}_${issueId}` : null,
    workspaceSlug && projectId && issueId
      ? () => githubSyncService.getGitLinks(workspaceSlug, projectId, issueId)
      : null
  );

  const suggestedBranchName = `feature/${slugify(`${issueIdentifier}-${issue?.name ?? ""}`)}`;

  const isLoading = isMappingsLoading || isGitLinksLoading;

  return (
    <div>
      <h6 className="flex items-center gap-1.5 text-body-xs-medium">
        <Github className="size-3.5" />
        GitHub
      </h6>
      <div className="mt-2 space-y-2">
        {isLoading ? (
          <Loader className="space-y-2">
            <Loader.Item height="30px" />
          </Loader>
        ) : (
          <>
            {gitLinks && gitLinks.length > 0 && (
              <div className="space-y-1.5">
                {gitLinks.map((link) => (
                  <GitLinkItem key={link.id} link={link} />
                ))}
              </div>
            )}

            {mappings && mappings.length > 0 ? (
              <CreateBranchButton
                workspaceSlug={workspaceSlug}
                projectId={projectId}
                issueId={issueId}
                suggestedBranchName={suggestedBranchName}
                mappings={mappings}
                onCreated={() => mutateGitLinks()}
              />
            ) : (
              <span className="text-body-xs-regular text-tertiary">No GitHub repository configured</span>
            )}
          </>
        )}
      </div>
    </div>
  );
});
