/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useMemo, useState } from "react";
import { Search, TriangleAlert } from "lucide-react";
import useSWR, { mutate } from "swr";
// plane imports
import { GITHUB_AVAILABLE_REPOSITORIES_KEY, GITHUB_REPOSITORIES_KEY } from "@plane/constants";
import { useTranslation } from "@plane/i18n";
import { Button } from "@plane/propel/button";
import { EmptyStateCompact } from "@plane/propel/empty-state";
import { TOAST_TYPE, setToast } from "@plane/propel/toast";
import type { TAvailableGithubRepository, TGithubEnabledRepository } from "@plane/types";
import { Loader } from "@plane/ui";
// components
import { SettingsHeading } from "@/components/settings/heading";
// services
import { GithubSyncService } from "@/services/github-sync.service";
// local imports
import { AvailableRepositoryListItem } from "./available-repository-list-item";
import { RegisterRepositoryModal } from "./register-repository-modal";
import { RepositoryListItem } from "./repository-list-item";

const githubSyncService = new GithubSyncService();

type Props = {
  workspaceSlug: string;
  hasInstallation: boolean;
};

export function RepositoriesPanel(props: Props) {
  const { workspaceSlug, hasInstallation } = props;
  const { t } = useTranslation();
  const [search, setSearch] = useState("");
  const [pendingChanges, setPendingChanges] = useState<Record<number, boolean>>({});
  const [isSaving, setIsSaving] = useState(false);
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [isRetrying, setIsRetrying] = useState(false);

  const {
    data: availableRepositories,
    error: availableError,
    isLoading: isAvailableLoading,
    mutate: mutateAvailable,
  } = useSWR(
    hasInstallation ? GITHUB_AVAILABLE_REPOSITORIES_KEY(workspaceSlug) : null,
    hasInstallation ? () => githubSyncService.getAvailableRepositories(workspaceSlug) : null
  );

  const { data: enabledRepositories, mutate: mutateEnabled } = useSWR(
    hasInstallation ? GITHUB_REPOSITORIES_KEY(workspaceSlug) : null,
    hasInstallation ? () => githubSyncService.getRepositories(workspaceSlug) : null
  );

  const mergedRepositories = useMemo(
    () =>
      (availableRepositories ?? []).map((repository) => {
        const isEnabled = pendingChanges[repository.github_repository_id] ?? repository.is_enabled;
        return Object.assign({}, repository, { is_enabled: isEnabled });
      }),
    [availableRepositories, pendingChanges]
  );

  const filteredRepositories = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) return mergedRepositories;
    return mergedRepositories.filter((repository) => repository.full_name.toLowerCase().includes(query));
  }, [mergedRepositories, search]);

  const hasPendingChanges = Object.keys(pendingChanges).length > 0;

  const handleRetry = async () => {
    setIsRetrying(true);
    await mutateAvailable();
    setIsRetrying(false);
  };

  const handleToggle = (repository: TAvailableGithubRepository, isEnabled: boolean) => {
    setPendingChanges((prev) => ({ ...prev, [repository.github_repository_id]: isEnabled }));
  };

  const handleSave = async () => {
    const changedRepositories = mergedRepositories.filter(
      (repository) => repository.github_repository_id in pendingChanges
    );
    if (changedRepositories.length === 0) return;

    setIsSaving(true);
    try {
      const response = await githubSyncService.bulkUpdateRepositories(
        workspaceSlug,
        changedRepositories.map((repository) => ({
          github_repository_id: repository.github_repository_id,
          full_name: repository.full_name,
          is_enabled: repository.is_enabled,
          private: repository.private,
          default_branch: repository.default_branch,
          html_url: repository.html_url,
        }))
      );
      // N7: a 207 partial failure responds with `{ results, errors }`
      // instead of a plain array -- never assume `.length` is on the response.
      const updated = Array.isArray(response) ? response : response.results;
      const failedCount = Array.isArray(response) ? 0 : response.errors.length;
      setPendingChanges({});
      await Promise.all([mutateAvailable(), mutateEnabled()]);
      if (failedCount > 0) {
        setToast({
          type: TOAST_TYPE.ERROR,
          title: t("common.error"),
          message: t("workspace_settings.settings.github.repositories.save_failed"),
        });
      } else {
        setToast({
          type: TOAST_TYPE.SUCCESS,
          title: t("common.success"),
          message: t("workspace_settings.settings.github.repositories.save_success", { count: updated.length }),
        });
      }
    } catch (error) {
      // D6: surface the server's per-item message (e.g. "Remove the project
      // mapping before disabling this repository.") instead of the generic
      // "save failed" toast, especially for the common single-item case where
      // the 400 body carries `errors`.
      const serverErrors = (
        error as {
          data?: { errors?: Array<{ errors?: Record<string, string[]> }> };
        }
      )?.data?.errors;
      const firstMessage = serverErrors?.[0]?.errors ? Object.values(serverErrors[0].errors)[0]?.[0] : undefined;
      setToast({
        type: TOAST_TYPE.ERROR,
        title: t("common.error"),
        message: firstMessage ?? t("workspace_settings.settings.github.repositories.save_failed"),
      });
    } finally {
      setIsSaving(false);
    }
  };

  const handleAddManually = async (data: { github_repository_id: number; full_name: string }) => {
    const created = await githubSyncService.createRepository(workspaceSlug, data);
    mutate<TGithubEnabledRepository[]>(
      GITHUB_REPOSITORIES_KEY(workspaceSlug),
      (prev) => [created, ...(prev ?? [])],
      false
    );
    mutateAvailable();
    setToast({
      type: TOAST_TYPE.SUCCESS,
      title: t("common.success"),
      message: t("workspace_settings.settings.github.repositories.manual.success"),
    });
  };

  const handleManualToggle = async (repository: TGithubEnabledRepository, isEnabled: boolean) => {
    const updated = await githubSyncService.updateRepository(workspaceSlug, repository.id, { is_enabled: isEnabled });
    mutate<TGithubEnabledRepository[]>(
      GITHUB_REPOSITORIES_KEY(workspaceSlug),
      (prev) => (prev ?? []).map((repo) => (repo.id === updated.id ? updated : repo)),
      false
    );
  };

  const handleManualDelete = async (repository: TGithubEnabledRepository) => {
    await githubSyncService.deleteRepository(workspaceSlug, repository.id);
    mutate<TGithubEnabledRepository[]>(
      GITHUB_REPOSITORIES_KEY(workspaceSlug),
      (prev) => (prev ?? []).filter((repo) => repo.id !== repository.id),
      false
    );
  };

  return (
    <div className="flex flex-col gap-4">
      <RegisterRepositoryModal
        isOpen={isAddModalOpen}
        onClose={() => setIsAddModalOpen(false)}
        onRegister={handleAddManually}
      />

      <SettingsHeading
        title={t("workspace_settings.settings.github.repositories.title")}
        description={t("workspace_settings.settings.github.repositories.description")}
        control={
          hasPendingChanges ? (
            <Button variant="primary" size="sm" onClick={handleSave} loading={isSaving}>
              {t("common.save_changes")}
            </Button>
          ) : undefined
        }
      />

      {!hasInstallation ? (
        <EmptyStateCompact
          assetKey="link"
          title={t("workspace_settings.settings.github.repositories.empty.no_installation.title")}
          description={t("workspace_settings.settings.github.repositories.empty.no_installation.description")}
          align="start"
          rootClassName="py-10"
        />
      ) : isAvailableLoading ? (
        <Loader className="flex flex-col gap-2">
          <Loader.Item height="48px" />
          <Loader.Item height="48px" />
        </Loader>
      ) : availableError ? (
        <div className="flex flex-col gap-4">
          <div className="flex flex-col items-center gap-3 rounded-md border border-subtle py-10 text-center">
            <span className="grid size-11 place-items-center text-tertiary">
              <TriangleAlert className="size-8" />
            </span>
            <div>
              <h6 className="text-14 font-medium">{t("common.something_went_wrong")}</h6>
              <p className="text-13 text-tertiary">
                {t("workspace_settings.settings.github.repositories.errors.load_failed")}
              </p>
            </div>
            <Button variant="link" onClick={handleRetry} loading={isRetrying}>
              {t("workspace_settings.settings.github.retry")}
            </Button>
          </div>
          {enabledRepositories && enabledRepositories.length > 0 && (
            <div>
              <p className="pb-2 text-12 text-tertiary">
                {t("workspace_settings.settings.github.repositories.errors.fallback_list")}
              </p>
              {enabledRepositories.map((repository) => (
                <RepositoryListItem
                  key={repository.id}
                  repository={repository}
                  onToggle={handleManualToggle}
                  onDelete={handleManualDelete}
                />
              ))}
            </div>
          )}
        </div>
      ) : (availableRepositories ?? []).length > 0 ? (
        <div className="flex flex-col gap-3">
          <div className="relative">
            <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-tertiary" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={t("workspace_settings.settings.github.repositories.search_placeholder")}
              className="w-full rounded-sm border-[0.5px] border-subtle bg-surface-1 py-1.5 pr-3 pl-8 text-13 outline-none"
            />
          </div>
          {filteredRepositories.length > 0 ? (
            <div>
              {filteredRepositories.map((repository) => (
                <AvailableRepositoryListItem
                  key={repository.github_repository_id}
                  repository={repository}
                  isEnabled={repository.is_enabled}
                  onToggle={handleToggle}
                />
              ))}
            </div>
          ) : (
            <p className="py-6 text-center text-13 text-tertiary">
              {t("workspace_settings.settings.github.repositories.no_search_results")}
            </p>
          )}
        </div>
      ) : (
        <EmptyStateCompact
          assetKey="link"
          title={t("workspace_settings.settings.github.repositories.empty.no_repositories.title")}
          description={t("workspace_settings.settings.github.repositories.empty.no_repositories.description")}
          align="start"
          rootClassName="py-10"
        />
      )}

      <div>
        <Button variant="link" size="sm" onClick={() => setIsAddModalOpen(true)} disabled={!hasInstallation}>
          {t("workspace_settings.settings.github.repositories.manual.trigger")}
        </Button>
      </div>
    </div>
  );
}
