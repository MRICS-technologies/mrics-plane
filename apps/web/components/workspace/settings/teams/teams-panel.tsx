/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import useSWR from "swr";
import { Button } from "@makeplane/propel/components/button";
import { WarningTriangleOutline } from "@makeplane/propel/icons";
// plane imports
import { EmptyStateCompact } from "@plane/blocks/empty-state";
import { Loader } from "@plane/blocks/skeleton";
import { setToast } from "@plane/blocks/toast";
import { GITHUB_REPOSITORIES_KEY, WORKSPACE_TEAMS_KEY } from "@plane/constants";
import { useTranslation } from "@plane/i18n";
// components
import { SettingsHeading } from "@/components/settings/heading";
// services
import { GithubSyncService } from "@/services/github-sync.service";
import { WorkspaceTeamService } from "@/services/workspace-team.service";
// local imports
import { TeamFormModal } from "./team-form-modal";
import { TeamListItem, teamErrorKey } from "./team-list-item";

const githubSyncService = new GithubSyncService();
const workspaceTeamService = new WorkspaceTeamService();

type Props = {
  workspaceSlug: string;
  isAdmin: boolean;
};

export function TeamsPanel(props: Props) {
  const { workspaceSlug, isAdmin } = props;
  const { t } = useTranslation();
  const [isCreateOpen, setIsCreateOpen] = useState(false);

  const {
    data: teams,
    error,
    isLoading,
    mutate,
  } = useSWR(WORKSPACE_TEAMS_KEY(workspaceSlug), () => workspaceTeamService.list(workspaceSlug));
  // Same cache entry as the GitHub settings page; [] without an installation.
  const { data: repositories } = useSWR(GITHUB_REPOSITORIES_KEY(workspaceSlug), () =>
    githubSyncService.getRepositories(workspaceSlug)
  );
  const enabledRepositories = (repositories ?? []).filter((repository) => repository.is_enabled);

  const handleCreate = async (name: string) => {
    try {
      await workspaceTeamService.create(workspaceSlug, { name });
      await mutate();
    } catch (createError) {
      setToast({ type: "error", title: t("common.error.label"), message: t(teamErrorKey(createError)) });
      throw createError;
    }
  };

  return (
    <div className="flex flex-col gap-4">
      {isCreateOpen && (
        <TeamFormModal
          title={t("workspace_settings.settings.teams.form.create_title")}
          submitLabel={t("common.create")}
          onClose={() => setIsCreateOpen(false)}
          onSubmit={handleCreate}
        />
      )}

      <SettingsHeading
        title={t("workspace_settings.settings.teams.title")}
        description={t("workspace_settings.settings.teams.description")}
        control={
          isAdmin ? (
            <Button
              variant="primary"
              size="xs"
              stretch="auto"
              label={t("workspace_settings.settings.teams.create")}
              onClick={() => setIsCreateOpen(true)}
            />
          ) : undefined
        }
      />

      {isLoading ? (
        <Loader className="flex flex-col gap-2">
          <Loader.Item height="96px" />
          <Loader.Item height="96px" />
        </Loader>
      ) : error ? (
        <div className="flex flex-col items-center gap-3 rounded-md border border-subtle py-10 text-center">
          <span className="grid size-11 place-items-center text-tertiary">
            <WarningTriangleOutline className="size-8" />
          </span>
          <div>
            <h6 className="text-14 font-medium">{t("common.something_went_wrong")}</h6>
            <p className="text-13 text-tertiary">{t("workspace_settings.settings.teams.errors.load_failed")}</p>
          </div>
          <Button variant="ghost" size="sm" stretch="auto" label={t("common.retry")} onClick={() => void mutate()} />
        </div>
      ) : !teams?.length ? (
        <EmptyStateCompact
          assetKey="members"
          title={t("workspace_settings.settings.teams.empty.title")}
          description={t("workspace_settings.settings.teams.empty.description")}
          align="start"
          rootClassName="py-10"
        />
      ) : (
        <div className="flex flex-col">
          {teams.map((team) => (
            <TeamListItem
              key={team.id}
              workspaceSlug={workspaceSlug}
              team={team}
              teams={teams}
              repositories={enabledRepositories}
              isAdmin={isAdmin}
              onChange={() => mutate()}
            />
          ))}
        </div>
      )}
    </div>
  );
}
