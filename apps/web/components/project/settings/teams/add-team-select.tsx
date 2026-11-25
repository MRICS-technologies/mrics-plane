/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { Ref } from "react";
import { observer } from "mobx-react";
import { AddOutline } from "@makeplane/propel/icons";
// plane imports
import { Select } from "@plane/blocks/select";
import { EUserPermissions, EUserPermissionsLevel } from "@plane/constants";
import { useTranslation } from "@plane/i18n";
import type { TWorkspaceTeam } from "@plane/types";
// components
import { InlineLinkText } from "@/components/settings/inline-link-text";
// hooks
import { useUserPermissions } from "@/hooks/store/user";

type Props = {
  /** On the wrapper: the shared trigger takes no ref, and the panel focuses it after a removal. */
  ref?: Ref<HTMLDivElement>;
  workspaceSlug: string;
  /** Every team of the workspace; `undefined` while loading, or when loading failed. */
  workspaceTeams: TWorkspaceTeam[] | undefined;
  isLoading: boolean;
  /** Set when the workspace teams could not be loaded. */
  error: unknown;
  /** Teams attached already, or being attached. */
  unavailableTeamIds: Set<string>;
  onAttach: (team: TWorkspaceTeam) => void;
};

/** Picks a workspace team not attached yet; attaching is the selection itself. */
export const AddTeamSelect = observer(function AddTeamSelect(props: Props) {
  const { ref, workspaceSlug, workspaceTeams, isLoading, error, unavailableTeamIds, onAttach } = props;
  const { t } = useTranslation();
  const { allowPermissions } = useUserPermissions();

  const availableTeams = (workspaceTeams ?? []).filter((team) => !unavailableTeamIds.has(team.id));
  const hasNoWorkspaceTeams = workspaceTeams?.length === 0;
  // A failed refresh keeps the teams already loaded; only a list that never arrived blocks Add team.
  const hasLoadFailed = !!error && !workspaceTeams;
  // Only workspace admins can create teams, so only they are sent to Workspace settings → Teams.
  const isWorkspaceAdmin = allowPermissions([EUserPermissions.ADMIN], EUserPermissionsLevel.WORKSPACE, workspaceSlug);

  return (
    <div ref={ref} className="flex flex-col items-start gap-1.5">
      <div className="w-48 max-w-full">
        <Select<TWorkspaceTeam>
          getValues={() => availableTeams}
          value={null}
          onChange={(teamId) => {
            const team = availableTeams.find((option) => option.id === teamId);
            if (team) onAttach(team);
          }}
          getOptionValue={(team) => team.id}
          getOptionLabel={(team) => team.name}
          getOptionTrailing={(team) => (
            <span className="text-11 text-tertiary">
              {t("workspace_settings.settings.teams.member_count", { count: team.member_ids.length })}
            </span>
          )}
          placeholder={t("project_settings.teams.add_team")}
          searchPlaceholder={t("project_settings.teams.search_teams")}
          emptyMessage={t("project_settings.teams.all_attached")}
          disabled={isLoading || hasLoadFailed || hasNoWorkspaceTeams}
          pinSelected={false}
          contentSizing="auto"
        >
          <Select.Trigger<TWorkspaceTeam>
            variant="select-md"
            prependIcon={<AddOutline aria-hidden="true" />}
            isEmpty={false}
            data-testid="project-teams-add"
          >
            <Select.Value />
          </Select.Trigger>
        </Select>
      </div>
      {hasLoadFailed ? (
        <p className="text-11 text-tertiary">{t("project_settings.teams.errors.workspace_teams_load_failed")}</p>
      ) : (
        hasNoWorkspaceTeams && (
          <p className="text-11 text-tertiary">
            {isWorkspaceAdmin ? (
              <InlineLinkText
                translate={(link) => t("project_settings.teams.no_workspace_teams", { link })}
                linkLabel={t("project_settings.teams.workspace_teams_link")}
                href={`/${workspaceSlug}/settings/teams/`}
              />
            ) : (
              t("project_settings.teams.no_workspace_teams_ask_admin")
            )}
          </p>
        )
      )}
    </div>
  );
});
