/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { Badge } from "@makeplane/propel/components/badge";
import { Button } from "@makeplane/propel/components/button";
import { CloseCircleOutline } from "@makeplane/propel/icons";
// plane imports
import { setToast } from "@plane/blocks/toast";
import { useTranslation } from "@plane/i18n";
import type { TRepoProjectMapping } from "@plane/types";
// local imports
import { DeleteMappingModal } from "./delete-mapping-modal";

type Props = {
  mapping: TRepoProjectMapping;
  onSetDefault: (mapping: TRepoProjectMapping) => Promise<void>;
  onDelete: (mapping: TRepoProjectMapping) => Promise<void>;
};

export function MappingListItem(props: Props) {
  const { mapping, onSetDefault, onDelete } = props;
  const { t } = useTranslation();
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
  const [isSettingDefault, setIsSettingDefault] = useState(false);

  const repoLabel = mapping.repository_detail?.full_name ?? mapping.github_repo;

  const handleSetDefault = async () => {
    setIsSettingDefault(true);
    try {
      await onSetDefault(mapping);
    } catch {
      setToast({
        type: "error",
        title: t("common.error"),
        message: t("project_settings.github.mapping.errors.set_default_failed"),
      });
    } finally {
      setIsSettingDefault(false);
    }
  };

  return (
    <div className="flex items-center justify-between gap-3 border-b border-subtle py-3">
      <DeleteMappingModal
        isOpen={isDeleteModalOpen}
        onClose={() => setIsDeleteModalOpen(false)}
        onDelete={() => onDelete(mapping)}
        mappingLabel={repoLabel}
        isDefault={mapping.is_default}
      />
      <div className="flex min-w-0 flex-col gap-0.5">
        <div className="flex items-center gap-2">
          <span className="truncate text-13 font-medium">{repoLabel}</span>
          {mapping.is_default && <Badge size="xs" variant="neutral" label={t("common.default")} />}
        </div>
        <span className="text-11 text-tertiary">
          {t("project_settings.github.mapping.base_branch", { branch: mapping.base_branch ?? "—" })}
          {mapping.repo_label ? ` · ${t("project_settings.github.mapping.label", { label: mapping.repo_label })}` : ""}
        </span>
      </div>
      <div className="flex flex-shrink-0 items-center gap-2">
        {!mapping.is_default && (
          <Button
            variant="ghost"
            size="xs"
            stretch="auto"
            label={t("project_settings.github.mapping.set_default")}
            onClick={() => void handleSetDefault()}
            loading={isSettingDefault}
          />
        )}
        <button
          type="button"
          onClick={() => setIsDeleteModalOpen(true)}
          aria-label={t("project_settings.github.mapping.remove_aria_label", { repo: repoLabel })}
          className="grid place-items-center text-danger-primary"
        >
          <CloseCircleOutline className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}
