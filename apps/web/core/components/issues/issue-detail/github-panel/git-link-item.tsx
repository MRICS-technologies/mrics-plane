/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { GitBranch, GitPullRequest } from "lucide-react";
import { useTranslation } from "@plane/i18n";
import { Tooltip } from "@plane/propel/tooltip";
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
};

export const GitLinkItem = (props: Props) => {
  const { link } = props;
  const { isMobile } = usePlatformOS();
  const { t } = useTranslation();
  const Icon = link.kind === "pr" ? GitPullRequest : GitBranch;
  const stateLabel =
    link.kind === "branch" ? t("work_item.github.link.state.linked") : t(`work_item.github.link.state.${link.state}`);

  return (
    <div className="group flex h-10 flex-shrink-0 items-center justify-between gap-3 rounded-sm border-[0.5px] border-subtle bg-surface-2 px-3 hover:bg-layer-1">
      <div className="flex min-w-0 flex-1 items-center gap-2.5">
        <Icon className="size-4 flex-shrink-0 text-tertiary group-hover:text-primary" />
        <Tooltip tooltipContent={link.url} isMobile={isMobile}>
          <a
            href={link.url}
            target="_blank"
            rel="noopener noreferrer"
            className="w-0 flex-1 truncate text-body-xs-regular"
          >
            {link.ref}
          </a>
        </Tooltip>
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
