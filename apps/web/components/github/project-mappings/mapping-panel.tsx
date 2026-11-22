/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { TriangleAlert } from "lucide-react";
import useSWR, { mutate } from "swr";
// plane imports
import { GITHUB_PROJECT_MAPPINGS_KEY, GITHUB_REPOSITORIES_KEY } from "@plane/constants";
import { useTranslation } from "@plane/i18n";
import { Button } from "@plane/propel/button";
import { EmptyStateCompact } from "@plane/propel/empty-state";
import type { TCreateMappingPayload, TRepoProjectMapping } from "@plane/types";
import { Loader } from "@plane/ui";
// components
import { SettingsHeading } from "@/components/settings/heading";
// services
import { GithubSyncService } from "@/services/github-sync.service";
// local imports
import { CreateMappingModal } from "./create-mapping-modal";
import { MappingListItem } from "./mapping-list-item";

const githubSyncService = new GithubSyncService();

type Props = {
  workspaceSlug: string;
  projectId: string;
};

export function MappingPanel(props: Props) {
  const { workspaceSlug, projectId } = props;
  const { t } = useTranslation();
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [isRetrying, setIsRetrying] = useState(false);

  const {
    data: mappings,
    error: mappingsError,
    isLoading,
    mutate: mutateMappings,
  } = useSWR(GITHUB_PROJECT_MAPPINGS_KEY(workspaceSlug, projectId), () =>
    githubSyncService.getMappings(workspaceSlug, projectId)
  );

  const {
    data: repositories,
    error: repositoriesError,
    isLoading: isRepositoriesLoading,
    mutate: mutateRepositories,
  } = useSWR(GITHUB_REPOSITORIES_KEY(workspaceSlug), () => githubSyncService.getRepositories(workspaceSlug));
  const enabledRepositories = (repositories ?? []).filter((repository) => repository.is_enabled);

  const hasMapping = Boolean(mappings && mappings.length > 0);
  const hasError = Boolean(mappingsError || repositoriesError);

  const handleRetry = async () => {
    setIsRetrying(true);
    await Promise.all([mutateMappings(), mutateRepositories()]);
    setIsRetrying(false);
  };

  const handleCreate = async (data: TCreateMappingPayload) => {
    const created = await githubSyncService.createMapping(workspaceSlug, projectId, data);
    mutate<TRepoProjectMapping[]>(
      GITHUB_PROJECT_MAPPINGS_KEY(workspaceSlug, projectId),
      (prev) => [created, ...(prev ?? [])],
      false
    );
  };

  const handleDelete = async (mapping: TRepoProjectMapping) => {
    await githubSyncService.deleteMapping(workspaceSlug, projectId, mapping.id);
    mutate<TRepoProjectMapping[]>(
      GITHUB_PROJECT_MAPPINGS_KEY(workspaceSlug, projectId),
      (prev) => (prev ?? []).filter((m) => m.id !== mapping.id),
      false
    );
  };

  return (
    <div className="flex flex-col gap-4">
      <CreateMappingModal
        isOpen={isAddModalOpen}
        onClose={() => setIsAddModalOpen(false)}
        onCreate={handleCreate}
        enabledRepositories={enabledRepositories}
      />

      <SettingsHeading
        title={t("project_settings.github.mapping.title")}
        description={t("project_settings.github.mapping.description")}
        control={
          !hasMapping ? (
            <Button
              variant="primary"
              size="sm"
              onClick={() => setIsAddModalOpen(true)}
              disabled={enabledRepositories.length === 0}
            >
              {t("project_settings.github.mapping.attach_button")}
            </Button>
          ) : undefined
        }
      />

      {isLoading || isRepositoriesLoading ? (
        <Loader className="flex flex-col gap-2">
          <Loader.Item height="48px" />
        </Loader>
      ) : hasError ? (
        <div className="flex flex-col items-center gap-3 rounded-md border border-subtle py-10 text-center">
          <span className="grid size-11 place-items-center text-tertiary">
            <TriangleAlert className="size-8" />
          </span>
          <div>
            <h6 className="text-14 font-medium">{t("common.something_went_wrong")}</h6>
            <p className="text-13 text-tertiary">{t("project_settings.github.mapping.errors.load_failed")}</p>
          </div>
          <Button variant="link" onClick={handleRetry} loading={isRetrying}>
            {t("workspace_settings.settings.github.retry")}
          </Button>
        </div>
      ) : hasMapping ? (
        <div>
          {mappings?.map((mapping) => (
            <MappingListItem key={mapping.id} mapping={mapping} onDelete={handleDelete} />
          ))}
        </div>
      ) : (
        <EmptyStateCompact
          assetKey="link"
          title={t("project_settings.github.mapping.empty.title")}
          description={
            enabledRepositories.length > 0
              ? t("project_settings.github.mapping.empty.description_ready")
              : t("project_settings.github.mapping.empty.description_no_repos")
          }
          actions={
            enabledRepositories.length > 0
              ? [{ label: t("project_settings.github.mapping.attach_button"), onClick: () => setIsAddModalOpen(true) }]
              : []
          }
          align="start"
          rootClassName="py-10"
        />
      )}
    </div>
  );
}
