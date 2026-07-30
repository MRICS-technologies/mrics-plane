/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { XCircle } from "lucide-react";
// plane imports
import { TOAST_TYPE, setToast } from "@plane/propel/toast";
import { ToggleSwitch } from "@plane/ui";
// services
import type { TGithubEnabledRepository } from "@/services/github-sync.service";
// local imports
import { DeleteRepositoryModal } from "./delete-repository-modal";

type Props = {
  repository: TGithubEnabledRepository;
  onToggle: (repository: TGithubEnabledRepository, isEnabled: boolean) => Promise<void>;
  onDelete: (repository: TGithubEnabledRepository) => Promise<void>;
};

export function RepositoryListItem(props: Props) {
  const { repository, onToggle, onDelete } = props;
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
  const [isToggling, setIsToggling] = useState(false);

  const handleToggle = async (value: boolean) => {
    setIsToggling(true);
    await onToggle(repository, value).catch(() => {
      setToast({ type: TOAST_TYPE.ERROR, title: "Error!", message: "This repository could not be updated." });
    });
    setIsToggling(false);
  };

  return (
    <div className="flex items-center justify-between border-b border-subtle py-3">
      <DeleteRepositoryModal
        isOpen={isDeleteModalOpen}
        onClose={() => setIsDeleteModalOpen(false)}
        onDelete={() => onDelete(repository)}
        repositoryName={repository.full_name}
      />
      <div className="flex flex-col gap-0.5">
        <span className="text-13 font-medium">{repository.full_name}</span>
        <span className="text-11 text-tertiary">Repository ID: {repository.github_repository_id}</span>
      </div>
      <div className="flex items-center gap-4">
        <ToggleSwitch value={repository.is_enabled} onChange={handleToggle} disabled={isToggling} />
        <button
          type="button"
          onClick={() => setIsDeleteModalOpen(true)}
          aria-label={`Remove ${repository.full_name}`}
          className="grid place-items-center text-danger-primary"
        >
          <XCircle className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}
