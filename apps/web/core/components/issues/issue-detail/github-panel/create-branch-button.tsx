/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useRef, useState } from "react";
import { observer } from "mobx-react";
import { GitBranch } from "lucide-react";
import { useOutsideClickDetector } from "@plane/hooks";
import { useTranslation } from "@plane/i18n";
import { Button } from "@plane/propel/button";
import { TOAST_TYPE, setToast } from "@plane/propel/toast";
import type { TRepoProjectMapping } from "@plane/types";
import { Input } from "@plane/ui";
import { GithubSyncService } from "@/services/github-sync.service";

const githubSyncService = new GithubSyncService();

type Props = {
  workspaceSlug: string;
  projectId: string;
  issueId: string;
  suggestedBranchName: string;
  mappings: TRepoProjectMapping[];
  onCreated: () => void;
};

export const CreateBranchButton = observer(function CreateBranchButton(props: Props) {
  const { workspaceSlug, projectId, issueId, suggestedBranchName, mappings, onCreated } = props;
  const { t } = useTranslation();
  const [isOpen, setIsOpen] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [branchName, setBranchName] = useState(suggestedBranchName);
  const [repo, setRepo] = useState(mappings.find((mapping) => mapping.is_default)?.github_repo ?? "");
  const containerRef = useRef<HTMLDivElement>(null);

  useOutsideClickDetector(containerRef, () => setIsOpen(false));

  const handleCreate = async () => {
    if (!branchName.trim()) return;
    setIsCreating(true);
    try {
      await githubSyncService.createBranch(workspaceSlug, projectId, issueId, {
        branch_name: branchName.trim(),
        repo: repo || undefined,
      });
      setToast({
        type: TOAST_TYPE.SUCCESS,
        title: t("common.success"),
        message: t("work_item.github.create_branch.success", { branch: branchName.trim() }),
      });
      setIsOpen(false);
      onCreated();
    } catch (error: any) {
      const status = error?.status;
      const message =
        status === 409
          ? t("work_item.github.create_branch.errors.conflict")
          : status === 422
            ? t("work_item.github.create_branch.errors.not_configured")
            : (error?.data?.error ?? t("work_item.github.create_branch.errors.failed"));
      setToast({ type: TOAST_TYPE.ERROR, title: t("common.error"), message });
    } finally {
      setIsCreating(false);
    }
  };

  if (!isOpen)
    return (
      <Button variant="secondary" size="sm" prependIcon={<GitBranch />} onClick={() => setIsOpen(true)}>
        {t("work_item.github.create_branch.trigger")}
      </Button>
    );

  return (
    <div ref={containerRef} className="flex flex-col gap-2 rounded-sm border-[0.5px] border-subtle bg-surface-2 p-2">
      <Input
        type="text"
        value={branchName}
        onChange={(e) => setBranchName(e.target.value)}
        placeholder={t("work_item.github.create_branch.placeholder")}
        className="w-full text-body-xs-regular"
      />
      {mappings.length > 1 && (
        <select
          value={repo}
          onChange={(e) => setRepo(e.target.value)}
          className="w-full rounded-sm border-[0.5px] border-subtle bg-surface-1 px-2 py-1 text-body-xs-regular"
        >
          {mappings.map((mapping) => (
            <option key={mapping.id} value={mapping.github_repo}>
              {mapping.repo_label || mapping.github_repo}
            </option>
          ))}
        </select>
      )}
      <div className="flex items-center justify-end gap-2">
        <Button variant="secondary" size="sm" onClick={() => setIsOpen(false)} disabled={isCreating}>
          {t("common.cancel")}
        </Button>
        <Button variant="primary" size="sm" onClick={handleCreate} loading={isCreating} disabled={!branchName.trim()}>
          {t("common.create")}
        </Button>
      </div>
    </div>
  );
});
