/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
import useSWR from "swr";
// plane imports
import { EUserPermissions, EUserPermissionsLevel, PROJECT_TEAMS_KEY, WORKSPACE_TEAMS_KEY } from "@plane/constants";
import { useTranslation } from "@plane/i18n";
// hooks
import { useUserPermissions } from "@/hooks/store/user";
// services
import { ProjectTeamService } from "@/services/project-team.service";
import { WorkspaceTeamService } from "@/services/workspace-team.service";

const projectTeamService = new ProjectTeamService();
const workspaceTeamService = new WorkspaceTeamService();

// Stands in for the team name while the tag is translated, so only the name truncates.
const TEAM_SLOT = "\u0000";

type Props = {
  workspaceSlug: string;
  projectId: string;
  /** The member's `source_team`: the team whose sync added them to the project. */
  teamId: string;
};

/** "via <team>" next to a project member added by a team. Renders nothing when the name can't be found. */
export const ProjectMemberTeamTag = observer(function ProjectMemberTeamTag(props: Props) {
  const { workspaceSlug, projectId, teamId } = props;
  const { t } = useTranslation();
  const { allowPermissions } = useUserPermissions();
  // Guests get a 403 from both team lists (and no `source_team` in the members list either).
  const canReadProjectTeams = allowPermissions(
    [EUserPermissions.ADMIN, EUserPermissions.MEMBER],
    EUserPermissionsLevel.PROJECT,
    workspaceSlug,
    projectId
  );
  const canReadWorkspaceTeams = allowPermissions(
    [EUserPermissions.ADMIN, EUserPermissions.MEMBER],
    EUserPermissionsLevel.WORKSPACE,
    workspaceSlug
  );

  // Same cache entry as Project settings → Teams; every row shares the one request.
  const { data: projectTeams } = useSWR(canReadProjectTeams ? PROJECT_TEAMS_KEY(workspaceSlug, projectId) : null, () =>
    projectTeamService.list(workspaceSlug, projectId)
  );
  const attachedTeam = projectTeams?.find((projectTeam) => projectTeam.team.id === teamId)?.team;
  // A detached team can still be a member's source; the workspace list still knows its name.
  const { data: workspaceTeams } = useSWR(
    canReadWorkspaceTeams && projectTeams && !attachedTeam ? WORKSPACE_TEAMS_KEY(workspaceSlug) : null,
    () => workspaceTeamService.list(workspaceSlug)
  );
  const teamName = attachedTeam?.name ?? workspaceTeams?.find((team) => team.id === teamId)?.name;

  if (!teamName) return null;

  const [before, after = ""] = t("project_settings.teams.via_team", { team: TEAM_SLOT }).split(TEAM_SLOT);
  return (
    <span
      className="flex max-w-32 min-w-0 shrink-0 items-center rounded-xs bg-layer-1 px-2 py-0.5 text-11 text-tertiary"
      title={t("project_settings.teams.via_team", { team: teamName })}
      data-testid="project-member-team-tag"
    >
      <span className="shrink-0 whitespace-pre">{before}</span>
      <span className="min-w-0 truncate">{teamName}</span>
      <span className="shrink-0 whitespace-pre">{after}</span>
    </span>
  );
});
