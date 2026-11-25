/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { Ref } from "react";
import { AddOutline } from "@makeplane/propel/icons";
// plane imports
import { Select } from "@plane/blocks/select";
import { useTranslation } from "@plane/i18n";
import type { TWorkspaceTeam } from "@plane/types";
// components
import { InlineLinkText } from "@/components/settings/inline-link-text";

type Props = {
  /** On the wrapper: the shared trigger takes no ref, and the panel focuses it after a removal. */
  ref?: Ref<HTMLDivElement>;
  workspaceSlug: string;
  /** Every team of the workspace; `undefined` while loading. */
  workspaceTeams: TWorkspaceTeam[] | undefined;
  /** Teams attached already, or being attached. */
  unavailableTeamIds: Set<string>;
  onAttach: (team: TWorkspaceTeam) => void;
};

/** Picks a workspace team not attached yet; attaching is the selection itself. */
export function AddTeamSelect(props: Props) {
  const { ref, workspaceSlug, workspaceTeams, unavailableTeamIds, onAttach } = props;
  const { t } = useTranslation();

  const availableTeams = (workspaceTeams ?? []).filter((team) => !unavailableTeamIds.has(team.id));
  const hasNoWorkspaceTeams = workspaceTeams?.length === 0;

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
          disabled={hasNoWorkspaceTeams}
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
