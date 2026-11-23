/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { Tooltip } from "@makeplane/propel/components/tooltip";
import { GitBranchOutline, GitPullRequestOutline } from "@makeplane/propel/icons";
import { useTranslation } from "@plane/i18n";
import type { TIssueGitLink } from "@plane/types";
import { cn } from "@plane/utils";
import { usePlatformOS } from "@/hooks/use-platform-os";

const STATE_BADGE_CLASSNAME: Record<TIssueGitLink["state"], string> = {
  open: "bg-success-subtle text-success-primary",
  merged: "bg-accent-subtle text-accent-primary",
  closed: "bg-danger-subtle text-danger-primary",
  unknown: "bg-layer-1 text-tertiary",
};

type Props = {
  link: TIssueGitLink;
  /** Show which repository the link belongs to (projects with several repositories). */
  showRepo?: boolean;
};

export const GitLinkItem = (props: Props) => {
  const { link, showRepo = false } = props;
  const { isMobile } = usePlatformOS();
  const { t } = useTranslation();
  const Icon = link.kind === "pr" ? GitPullRequestOutline : GitBranchOutline;
  const [repoOwner, repoName] = link.github_repo.split("/");
  const stateLabel =
    link.kind === "branch" ? t("work_item.github.link.state.linked") : t(`work_item.github.link.state.${link.state}`);

  return (
    <div className="group flex min-h-10 flex-shrink-0 items-center justify-between gap-3 rounded-sm border-[0.5px] border-subtle bg-surface-2 px-3 py-1.5 hover:bg-layer-1">
      <div className="flex min-w-0 flex-1 items-center gap-2.5">
        <Icon className="size-4 flex-shrink-0 text-tertiary group-hover:text-primary" />
        <div className="flex w-0 flex-1 flex-col">
          <Tooltip label={link.url} disabled={isMobile}>
            <a href={link.url} target="_blank" rel="noopener noreferrer" className="truncate text-body-xs-regular">
              {link.ref}
            </a>
          </Tooltip>
          {showRepo && (
            // The owner truncates first so the repository name, which tells
            // a project's repositories apart, stays visible.
            <span className="flex text-caption-sm-regular text-tertiary" title={link.github_repo}>
              <span className="truncate">{repoOwner}</span>
              <span className="max-w-full flex-shrink-0 truncate">/{repoName}</span>
            </span>
          )}
        </div>
      </div>
      <span
        className={cn(
          "flex-shrink-0 rounded-full px-2 py-0.5 text-caption-sm-regular capitalize",
          STATE_BADGE_CLASSNAME[link.state]
        )}
      >
        {stateLabel}
      </span>
    </div>
  );
};
