/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { Lock } from "lucide-react";
// plane imports
import { Checkbox } from "@plane/ui";
import type { TAvailableGithubRepository } from "@plane/types";

type Props = {
  repository: TAvailableGithubRepository;
  isEnabled: boolean;
  onToggle: (repository: TAvailableGithubRepository, isEnabled: boolean) => void;
};

export function AvailableRepositoryListItem(props: Props) {
  const { repository, isEnabled, onToggle } = props;
  const inputId = `github-available-repo-${repository.github_repository_id}`;

  return (
    <label
      htmlFor={inputId}
      className="flex cursor-pointer items-center justify-between gap-3 border-b border-subtle px-1 py-2.5 hover:bg-layer-1"
    >
      <div className="flex min-w-0 items-center gap-2.5">
        <Checkbox id={inputId} checked={isEnabled} onChange={(e) => onToggle(repository, e.target.checked)} />
        <div className="flex min-w-0 flex-col gap-0.5">
          <span className="truncate text-13 font-medium">{repository.full_name}</span>
          <span className="text-11 text-tertiary">{repository.default_branch}</span>
        </div>
      </div>
      {repository.private && (
        <span className="flex flex-shrink-0 items-center gap-1 rounded-xs bg-layer-1 px-2 py-0.5 text-11 text-tertiary">
          <Lock className="size-3" />
        </span>
      )}
    </label>
  );
}
