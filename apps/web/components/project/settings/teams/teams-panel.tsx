/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useRef, useState } from "react";
import { runInAction } from "mobx";
import useSWR, { mutate as globalMutate } from "swr";
import { Button } from "@makeplane/propel/components/button";
import { WarningTriangleOutline } from "@makeplane/propel/icons";
// plane imports
import { EmptyStateCompact } from "@plane/blocks/empty-state";
import { Loader } from "@plane/blocks/skeleton";
import { setToast } from "@plane/blocks/toast";
import {
  GITHUB_PROJECT_TEAM_REPOSITORIES_KEY,
  PROJECT_ROUTING_RULES_KEY,
  PROJECT_TEAMS_KEY,
  WORKSPACE_TEAMS_KEY,
} from "@plane/constants";
import { useTranslation } from "@plane/i18n";
import type { TProjectTeam, TWorkspaceTeam } from "@plane/types";
// components
import { SettingsHeading } from "@/components/settings/heading";
// hooks
import { useMember } from "@/hooks/store/use-member";
import { useProject } from "@/hooks/store/use-project";
// services
import { ProjectTeamService } from "@/services/project-team.service";
import { WorkspaceTeamService } from "@/services/workspace-team.service";
// local imports
import { AddTeamSelect } from "./add-team-select";
import { RoutingRulesSection } from "./routing/routing-rules-section";
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
  const { projectMap } = useProject();
  // Teams whose attach request hasn't settled yet: kept out of Add team so they can't be attached twice.
  const [attachingTeamIds, setAttachingTeamIds] = useState<ReadonlySet<string>>(new Set());
  // Where the focus goes once a removed row (which held it) is gone.
  const addTeamRef = useRef<HTMLDivElement>(null);
  const retryRef = useRef<HTMLButtonElement>(null);

  const {
    data: projectTeams,
    error,
    isLoading,
    mutate,
  } = useSWR(PROJECT_TEAMS_KEY(workspaceSlug, projectId), () => projectTeamService.list(workspaceSlug, projectId));
  // Same cache entry as Workspace settings → Teams; only admins attach teams.
  const {
    data: workspaceTeams,
    error: workspaceTeamsError,
    isLoading: isWorkspaceTeamsLoading,
    mutate: mutateWorkspaceTeams,
  } = useSWR(isAdmin ? WORKSPACE_TEAMS_KEY(workspaceSlug) : null, () => workspaceTeamService.list(workspaceSlug));
  const unavailableTeamIds = new Set([
    ...(projectTeams ?? []).map((projectTeam) => projectTeam.team.id),
    ...attachingTeamIds,
  ]);

  // Replaces the members rather than merging, so members a removal took out drop from the store. The
  // project's own member ids (the avatars and count on its card) follow, as in Plane's add/remove flows.
  const refreshProjectMembers = () =>
    fetchProjectMembers(workspaceSlug, projectId, true)
      .then((members) =>
        runInAction(() => {
          const project = projectMap[projectId];
          if (project) project.members = members.map((member) => member.member);
        })
      )
      .catch(() => undefined);

  // A team's attachment and leader decide each routing rule's leader and whether it is active.
  const refreshRoutingRules = () => globalMutate(PROJECT_ROUTING_RULES_KEY(workspaceSlug, projectId));

  // A team joining or leaving changes the list, the project's members, the routing rules and the GitHub
  // team defaults (they list attached teams only). Those are cleared rather than only revalidated: their
  // panel isn't mounted here, and would otherwise show the old rows until its own re-fetch lands.
  const refreshAfterTeamChange = () =>
    Promise.all([
      mutate(),
      refreshProjectMembers(),
      refreshRoutingRules(),
      globalMutate(GITHUB_PROJECT_TEAM_REPOSITORIES_KEY(workspaceSlug, projectId), undefined),
    ]);

  const setAttaching = (teamId: string, isAttaching: boolean) =>
    setAttachingTeamIds((current) => {
      const next = new Set(current);
      if (isAttaching) next.add(teamId);
      else next.delete(teamId);
      return next;
    });

  const handleAttach = async (team: TWorkspaceTeam) => {
    setAttaching(team.id, true);
    try {
      const { added_member_ids: added } = await projectTeamService.attach(workspaceSlug, projectId, team.id);
      await refreshAfterTeamChange();
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
      // The team may be gone (404) or attached meanwhile: both lists decide what Add team offers.
      await Promise.all([mutate(), mutateWorkspaceTeams()]);
    } finally {
      setAttaching(team.id, false);
    }
  };

  const handleUpdated = (updated: TProjectTeam) =>
    Promise.all([
      mutate((current) => current?.map((projectTeam) => (projectTeam.id === updated.id ? updated : projectTeam)), {
        revalidate: false,
      }),
      refreshRoutingRules(),
    ]);

  const handleRefresh = () => Promise.all([mutate(), refreshProjectMembers(), refreshRoutingRules()]);

  const handleRemoved = async () => {
    await refreshAfterTeamChange();
    // The removed row held the focus: hand it to Add team, the way back to that team, or to Retry when
    // the list could not be re-fetched (the error block replaces Add team then).
    window.setTimeout(() =>
      (retryRef.current ?? addTeamRef.current?.querySelector<HTMLElement>("button, [role='combobox']"))?.focus()
    );
  };

  const addTeamSelect = isAdmin ? (
    <AddTeamSelect
      ref={addTeamRef}
      workspaceSlug={workspaceSlug}
      workspaceTeams={workspaceTeams}
      isLoading={isWorkspaceTeamsLoading}
      error={workspaceTeamsError}
      unavailableTeamIds={unavailableTeamIds}
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
          <Button
            ref={retryRef}
            variant="ghost"
            size="sm"
            stretch="auto"
            label={t("common.retry")}
            onClick={() => void mutate()}
          />
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

      <div className="mt-6">
        <RoutingRulesSection
          workspaceSlug={workspaceSlug}
          projectId={projectId}
          isAdmin={isAdmin}
          projectTeams={projectTeams}
        />
      </div>
    </div>
  );
}
