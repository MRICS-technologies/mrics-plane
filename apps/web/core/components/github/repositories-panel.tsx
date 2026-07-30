/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { TriangleAlert } from "lucide-react";
import useSWR, { mutate } from "swr";
// plane imports
import { Button } from "@plane/propel/button";
import { EmptyStateCompact } from "@plane/propel/empty-state";
import { TOAST_TYPE, setToast } from "@plane/propel/toast";
import { Loader } from "@plane/ui";
// components
import { SettingsHeading } from "@/components/settings/heading";
// services
import { GithubSyncService, type TGithubEnabledRepository } from "@/services/github-sync.service";
// local imports
import { RegisterRepositoryModal } from "./register-repository-modal";
import { RepositoryListItem } from "./repository-list-item";
import { GITHUB_REPOSITORIES_KEY } from "./swr-keys";

const githubSyncService = new GithubSyncService();

type Props = {
  workspaceSlug: string;
  hasInstallation: boolean;
};

export function RepositoriesPanel(props: Props) {
  const { workspaceSlug, hasInstallation } = props;
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [isRetrying, setIsRetrying] = useState(false);

  const {
    data: repositories,
    error: repositoriesError,
    isLoading,
    mutate: mutateRepositories,
  } = useSWR(GITHUB_REPOSITORIES_KEY(workspaceSlug), () => githubSyncService.getRepositories(workspaceSlug));

  const handleRetry = async () => {
    setIsRetrying(true);
    await mutateRepositories();
    setIsRetrying(false);
  };

  const handleAdd = async (data: { github_repository_id: number; full_name: string }) => {
    const created = await githubSyncService.createRepository(workspaceSlug, data);
    mutate<TGithubEnabledRepository[]>(
      GITHUB_REPOSITORIES_KEY(workspaceSlug),
      (prev) => [created, ...(prev ?? [])],
      false
    );
    setToast({ type: TOAST_TYPE.SUCCESS, title: "Success!", message: "Repository added." });
  };

  const handleToggle = async (repository: TGithubEnabledRepository, isEnabled: boolean) => {
    const updated = await githubSyncService.updateRepository(workspaceSlug, repository.id, {
      is_enabled: isEnabled,
    });
    mutate<TGithubEnabledRepository[]>(
      GITHUB_REPOSITORIES_KEY(workspaceSlug),
      (prev) => (prev ?? []).map((repo) => (repo.id === updated.id ? updated : repo)),
      false
    );
  };

  const handleDelete = async (repository: TGithubEnabledRepository) => {
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
        onRegister={handleAdd}
      />

      <SettingsHeading
        title="Repositories"
        description="Repositories manually enabled for this workspace's GitHub installation."
        control={
          <Button variant="primary" size="sm" onClick={() => setIsAddModalOpen(true)} disabled={!hasInstallation}>
            Add repository
          </Button>
        }
      />

      {isLoading ? (
        <Loader className="flex flex-col gap-2">
          <Loader.Item height="48px" />
          <Loader.Item height="48px" />
        </Loader>
      ) : repositoriesError ? (
        <div className="flex flex-col items-center gap-3 rounded-md border border-subtle py-10 text-center">
          <span className="grid size-11 place-items-center text-tertiary">
            <TriangleAlert className="size-8" />
          </span>
          <div>
            <h6 className="text-14 font-medium">Something went wrong!</h6>
            <p className="text-13 text-tertiary">Repositories could not be loaded, please try again.</p>
          </div>
          <Button variant="link" onClick={handleRetry} loading={isRetrying}>
            Try again
          </Button>
        </div>
      ) : repositories && repositories.length > 0 ? (
        <div>
          {repositories.map((repository) => (
            <RepositoryListItem
              key={repository.id}
              repository={repository}
              onToggle={handleToggle}
              onDelete={handleDelete}
            />
          ))}
        </div>
      ) : (
        <EmptyStateCompact
          assetKey="link"
          title="No repositories enabled"
          description={
            hasInstallation
              ? "Add a repository by its GitHub repository ID and full name."
              : "Register a GitHub installation before adding repositories."
          }
          actions={hasInstallation ? [{ label: "Add repository", onClick: () => setIsAddModalOpen(true) }] : []}
          align="start"
          rootClassName="py-10"
        />
      )}
    </div>
  );
}
