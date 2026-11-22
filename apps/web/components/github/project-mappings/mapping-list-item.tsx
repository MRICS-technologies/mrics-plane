/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { XCircle } from "lucide-react";
// plane imports
import { useTranslation } from "@plane/i18n";
import type { TRepoProjectMapping } from "@plane/types";
// local imports
import { DeleteMappingModal } from "./delete-mapping-modal";

type Props = {
  mapping: TRepoProjectMapping;
  onDelete: (mapping: TRepoProjectMapping) => Promise<void>;
};

export function MappingListItem(props: Props) {
  const { mapping, onDelete } = props;
  const { t } = useTranslation();
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);

  const repoLabel = mapping.repository_detail?.full_name ?? mapping.github_repo;

  return (
    <div className="flex items-center justify-between border-b border-subtle py-3">
      <DeleteMappingModal
        isOpen={isDeleteModalOpen}
        onClose={() => setIsDeleteModalOpen(false)}
        onDelete={() => onDelete(mapping)}
        mappingLabel={repoLabel}
      />
      <div className="flex flex-col gap-0.5">
        <span className="text-13 font-medium">{repoLabel}</span>
        <span className="text-11 text-tertiary">
          {t("project_settings.github.mapping.base_branch", { branch: mapping.base_branch ?? "—" })}
          {mapping.repo_label ? ` · ${t("project_settings.github.mapping.label", { label: mapping.repo_label })}` : ""}
        </span>
      </div>
      <button
        type="button"
        onClick={() => setIsDeleteModalOpen(true)}
        aria-label={t("project_settings.github.mapping.remove_aria_label", { repo: repoLabel })}
        className="grid place-items-center text-danger-primary"
      >
        <XCircle className="h-4 w-4" />
      </button>
    </div>
  );
}
