/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { AddOutline } from "@makeplane/propel/icons";
// plane imports
import { Select } from "@plane/blocks/select";
import { useTranslation } from "@plane/i18n";
import type { TWorkspaceTeam } from "@plane/types";
// components
import { InlineLinkText } from "@/components/settings/inline-link-text";

/** The Add team trigger, focused again when a removal takes its row (and its focus) away. */
export const ADD_TEAM_TRIGGER_ID = "project-teams-add-team";

type Props = {
  workspaceSlug: string;
  /** Every team of the workspace; `undefined` while loading. */
  workspaceTeams: TWorkspaceTeam[] | undefined;
  attachedTeamIds: Set<string>;
  onAttach: (team: TWorkspaceTeam) => void;
};

/** Picks a workspace team not attached yet; attaching is the selection itself. */
export function AddTeamSelect(props: Props) {
  const { workspaceSlug, workspaceTeams, attachedTeamIds, onAttach } = props;
  const { t } = useTranslation();

  const availableTeams = (workspaceTeams ?? []).filter((team) => !attachedTeamIds.has(team.id));
  const hasNoWorkspaceTeams = workspaceTeams?.length === 0;

  return (
    <div className="flex flex-col items-start gap-1.5">
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
          disabled={hasNoWorkspaceTeams}
          pinSelected={false}
          contentSizing="auto"
        >
          <Select.Trigger<TWorkspaceTeam>
            variant="select-md"
            id={ADD_TEAM_TRIGGER_ID}
            prependIcon={<AddOutline aria-hidden="true" />}
            isEmpty={false}
            data-testid="project-teams-add"
          >
            <Select.Value />
          </Select.Trigger>
        </Select>
      </div>
      {hasNoWorkspaceTeams && (
        <p className="text-11 text-tertiary">
          <InlineLinkText
            translate={(link) => t("project_settings.teams.no_workspace_teams", { link })}
            linkLabel={t("project_settings.teams.workspace_teams_link")}
            href={`/${workspaceSlug}/settings/teams/`}
          />
        </p>
      )}
    </div>
  );
}
