/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import useSWR from "swr";
import { Button } from "@makeplane/propel/components/button";
import { WarningTriangleOutline } from "@makeplane/propel/icons";
// plane imports
import { EmptyStateCompact } from "@plane/blocks/empty-state";
import { Loader } from "@plane/blocks/skeleton";
import { setToast } from "@plane/blocks/toast";
import { PROJECT_TEAMS_KEY, WORKSPACE_TEAMS_KEY } from "@plane/constants";
import { useTranslation } from "@plane/i18n";
import type { TProjectTeam, TWorkspaceTeam } from "@plane/types";
// components
import { SettingsHeading } from "@/components/settings/heading";
// hooks
import { useMember } from "@/hooks/store/use-member";
// services
import { ProjectTeamService } from "@/services/project-team.service";
import { WorkspaceTeamService } from "@/services/workspace-team.service";
// local imports
import { ADD_TEAM_TRIGGER_ID, AddTeamSelect } from "./add-team-select";
import { ProjectTeamListItem, projectTeamErrorMessage } from "./team-list-item";

const projectTeamService = new ProjectTeamService();
const workspaceTeamService = new WorkspaceTeamService();

type Props = {
  workspaceSlug: string;
  projectId: string;
  isAdmin: boolean;
};

export function ProjectTeamsPanel(props: Props) {
  const { workspaceSlug, projectId, isAdmin } = props;
  const { t } = useTranslation();
  const {
    project: { fetchProjectMembers },
  } = useMember();

  const {
    data: projectTeams,
    error,
    isLoading,
    mutate,
  } = useSWR(PROJECT_TEAMS_KEY(workspaceSlug, projectId), () => projectTeamService.list(workspaceSlug, projectId));
  // Same cache entry as Workspace settings → Teams; only admins attach teams.
  const { data: workspaceTeams } = useSWR(isAdmin ? WORKSPACE_TEAMS_KEY(workspaceSlug) : null, () =>
    workspaceTeamService.list(workspaceSlug)
  );
  const attachedTeamIds = new Set((projectTeams ?? []).map((projectTeam) => projectTeam.team.id));

  // Replaces the members rather than merging, so members a removal took out drop from the store.
  const refreshProjectMembers = () => fetchProjectMembers(workspaceSlug, projectId, true).catch(() => undefined);

  const handleAttach = async (team: TWorkspaceTeam) => {
    try {
      const { added_member_ids: added } = await projectTeamService.attach(workspaceSlug, projectId, team.id);
      await Promise.all([mutate(), refreshProjectMembers()]);
      setToast({
        type: "success",
        title: t("project_settings.teams.toasts.attached", { team: team.name }),
        message: t("project_settings.teams.toasts.members_added", { count: added.length }),
      });
    } catch (attachError) {
      setToast({
        type: "error",
        title: t("common.error.label"),
        message: projectTeamErrorMessage(
          attachError,
          t("project_settings.teams.errors.attach_failed"),
          t("project_settings.teams.errors.forbidden")
        ),
      });
    }
  };

  const handleUpdated = (updated: TProjectTeam) =>
    mutate((current) => current?.map((projectTeam) => (projectTeam.id === updated.id ? updated : projectTeam)), {
      revalidate: false,
    });

  const handleRefresh = () => Promise.all([mutate(), refreshProjectMembers()]);

  // The removed row held the focus: hand it to Add team, the way back to that team.
  const handleRemoved = () => window.setTimeout(() => document.getElementById(ADD_TEAM_TRIGGER_ID)?.focus());

  const addTeamSelect = isAdmin ? (
    <AddTeamSelect
      workspaceSlug={workspaceSlug}
      workspaceTeams={workspaceTeams}
      attachedTeamIds={attachedTeamIds}
      onAttach={(team) => void handleAttach(team)}
    />
  ) : undefined;

  return (
    <div className="flex flex-col gap-4">
      <SettingsHeading
        title={t("project_settings.teams.label")}
        description={t("project_settings.teams.description")}
        control={projectTeams?.length ? addTeamSelect : undefined}
      />

      {isLoading ? (
        <Loader className="flex flex-col gap-2">
          <Loader.Item height="72px" />
          <Loader.Item height="72px" />
        </Loader>
      ) : error ? (
        <div className="flex flex-col items-center gap-3 rounded-md border border-subtle py-10 text-center">
          <span className="grid size-11 place-items-center text-tertiary">
            <WarningTriangleOutline className="size-8" />
          </span>
          <div>
            <h6 className="text-14 font-medium">{t("common.something_went_wrong")}</h6>
            <p className="text-13 text-tertiary">{t("project_settings.teams.errors.load_failed")}</p>
          </div>
          <Button variant="ghost" size="sm" stretch="auto" label={t("common.retry")} onClick={() => void mutate()} />
        </div>
      ) : !projectTeams?.length ? (
        <EmptyStateCompact
          assetKey="members"
          title={t("project_settings.teams.empty.title")}
          description={t(
            isAdmin ? "project_settings.teams.empty.description_admin" : "project_settings.teams.empty.description"
          )}
          align="start"
          rootClassName="py-10"
          customButton={addTeamSelect}
        />
      ) : (
        <div className="flex flex-col">
          {projectTeams.map((projectTeam) => (
            <ProjectTeamListItem
              key={projectTeam.id}
              workspaceSlug={workspaceSlug}
              projectId={projectId}
              projectTeam={projectTeam}
              isAdmin={isAdmin}
              onUpdated={handleUpdated}
              onRefresh={handleRefresh}
              onRemoved={handleRemoved}
            />
          ))}
        </div>
      )}
    </div>
  );
}
