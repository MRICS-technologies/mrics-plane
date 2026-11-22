/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { XCircle } from "lucide-react";
// plane imports
import { useTranslation } from "@plane/i18n";
import { TOAST_TYPE, setToast } from "@plane/propel/toast";
import type { TGithubEnabledRepository } from "@plane/types";
import { ToggleSwitch } from "@plane/ui";
// local imports
import { DeleteRepositoryModal } from "./delete-repository-modal";

type Props = {
  repository: TGithubEnabledRepository;
  onToggle: (repository: TGithubEnabledRepository, isEnabled: boolean) => Promise<void>;
  onDelete: (repository: TGithubEnabledRepository) => Promise<void>;
};

export function RepositoryListItem(props: Props) {
  const { repository, onToggle, onDelete } = props;
  const { t } = useTranslation();
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
  const [isToggling, setIsToggling] = useState(false);

  const handleToggle = async (value: boolean) => {
    setIsToggling(true);
    await onToggle(repository, value).catch(() => {
      setToast({
        type: TOAST_TYPE.ERROR,
        title: t("common.error"),
        message: t("workspace_settings.settings.github.repositories.update_failed"),
      });
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
        <span className="text-11 text-tertiary">
          {t("workspace_settings.settings.github.repositories.repository_id", {
            id: repository.github_repository_id,
          })}
        </span>
      </div>
      <div className="flex items-center gap-4">
        <ToggleSwitch value={repository.is_enabled} onChange={handleToggle} disabled={isToggling} />
        <button
          type="button"
          onClick={() => setIsDeleteModalOpen(true)}
          aria-label={t("workspace_settings.settings.github.repositories.remove_aria_label", {
            repo: repository.full_name,
          })}
          className="grid place-items-center text-danger-primary"
        >
          <XCircle className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}
