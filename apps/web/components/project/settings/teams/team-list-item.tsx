/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { observer } from "mobx-react";
import { Avatar } from "@makeplane/propel/components/avatar";
import { AvatarGroup } from "@makeplane/propel/components/avatar-group";
import { Button } from "@makeplane/propel/components/button";
// plane imports
import { ConfirmDialog } from "@plane/blocks/dialog";
import { setToast } from "@plane/blocks/toast";
import { useTranslation } from "@plane/i18n";
import type { TApiError, TProjectTeam } from "@plane/types";
import { getFileURL } from "@plane/utils";
// components
import { MemberSelect } from "@/components/dropdowns/member/member-select";
// hooks
import { useMember } from "@/hooks/store/use-member";
// services
import { ProjectTeamService } from "@/services/project-team.service";

const projectTeamService = new ProjectTeamService();

const MAX_AVATARS = 4;

/** Message of the toast for a failed write: the API's own field message when it sends one. */
export const projectTeamErrorMessage = (error: unknown, fallback: string, forbidden: string) => {
  const { status, data } = (error ?? {}) as TApiError;
  if (status === 403) return forbidden;
  const fieldErrors = data && Object.values(data)[0];
  const first = Array.isArray(fieldErrors) ? fieldErrors[0] : undefined;
  return status === 400 && typeof first === "string" ? first : fallback;
};

type Props = {
  workspaceSlug: string;
  projectId: string;
  projectTeam: TProjectTeam;
  isAdmin: boolean;
  /** The row the API returned after a leader change. */
  onUpdated: (projectTeam: TProjectTeam) => Promise<unknown>;
  /** Re-fetches the list and the project members. */
  onRefresh: () => Promise<unknown>;
  /** Called once the team is removed and the list re-fetched (this row is gone). */
  onRemoved: () => void;
};

export const ProjectTeamListItem = observer(function ProjectTeamListItem(props: Props) {
  const { workspaceSlug, projectId, projectTeam, isAdmin, onUpdated, onRefresh, onRemoved } = props;
  const { team, leader_id: leaderId } = projectTeam;
  const { t, currentLocale } = useTranslation();
  const {
    workspace: { getWorkspaceMemberDetails },
  } = useMember();
  const [isRemoveOpen, setIsRemoveOpen] = useState(false);
  const [isRemoving, setIsRemoving] = useState(false);

  const members = team.member_ids.flatMap((memberId) => getWorkspaceMemberDetails(memberId)?.member ?? []);
  // The API sends the ids in no particular order; sorted, the avatars keep their places between renders.
  // In place on purpose: `members` is a fresh array (and `toSorted` is past this app's ES2022 lib).
  members.sort((a, b) => a.display_name.localeCompare(b.display_name, currentLocale));
  const leaderName = leaderId ? getWorkspaceMemberDetails(leaderId)?.member.display_name : undefined;
  const forbidden = t("project_settings.teams.errors.forbidden");

  const handleLeaderChange = async (memberId: string) => {
    // The "No leader" row reports an empty id.
    const nextLeaderId = memberId || null;
    if (nextLeaderId === leaderId) return;
    try {
      const updated = await projectTeamService.updateLeader(workspaceSlug, projectId, team.id, nextLeaderId);
      await onUpdated(updated);
      setToast({
        type: "success",
        title: t("common.success"),
        message: nextLeaderId
          ? t("project_settings.teams.toasts.leader_set", {
              name: getWorkspaceMemberDetails(nextLeaderId)?.member.display_name ?? "",
              team: team.name,
            })
          : t("project_settings.teams.toasts.leader_cleared", { team: team.name }),
      });
    } catch (error) {
      setToast({
        type: "error",
        title: t("common.error.label"),
        message: projectTeamErrorMessage(error, t("project_settings.teams.errors.leader_failed"), forbidden),
      });
      // A 400 usually means the team changed meanwhile (the picked member left it).
      void onRefresh();
    }
  };

  const handleRemove = async () => {
    setIsRemoving(true);
    try {
      const { removed_member_ids: removed, kept_member_ids: kept } = await projectTeamService.detach(
        workspaceSlug,
        projectId,
        team.id
      );
      setToast({
        type: "success",
        title: t("project_settings.teams.toasts.removed", { team: team.name }),
        message: t("project_settings.teams.toasts.members_removed", { removed: removed.length, kept: kept.length }),
      });
      // The row, and this dialog with it, unmount once the list is refreshed.
      await onRefresh();
      onRemoved();
    } catch (error) {
      setToast({
        type: "error",
        title: t("common.error.label"),
        message: projectTeamErrorMessage(error, t("project_settings.teams.errors.remove_failed"), forbidden),
      });
      setIsRemoving(false);
      setIsRemoveOpen(false);
    }
  };

  return (
    <div
      className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3 border-b border-subtle py-4"
      data-testid="project-team"
    >
      {isAdmin && (
        <ConfirmDialog
          isOpen={isRemoveOpen}
          handleClose={() => setIsRemoveOpen(false)}
          handleSubmit={handleRemove}
          isSubmitting={isRemoving}
          primaryButtonText={{
            default: t("project_settings.teams.remove_modal.confirm"),
            loading: t("project_settings.teams.remove_modal.confirming"),
          }}
          title={t("project_settings.teams.remove_modal.title", { team: team.name })}
          content={t("project_settings.teams.remove_modal.content", { team: team.name })}
        />
      )}

      <div className="flex min-w-0 flex-1 basis-full items-center gap-4 sm:basis-48">
        <div className="flex min-w-0 flex-col gap-0.5">
          <span className="truncate text-14 font-medium">{team.name}</span>
          <span className="text-11 text-tertiary">
            {t("workspace_settings.settings.teams.member_count", { count: team.member_ids.length })}
          </span>
        </div>
        {members.length > 0 && (
          <AvatarGroup
            size="sm"
            max={MAX_AVATARS}
            label={members.map((member) => member.display_name).join(", ")}
            overflowTooltip={
              members
                .slice(MAX_AVATARS)
                .map((member) => member.display_name)
                .join(", ") || undefined
            }
          >
            {members.map((member) => (
              <Avatar
                key={member.id}
                alt={member.display_name}
                fallback={member.display_name?.[0]?.toUpperCase()}
                src={getFileURL(member.avatar_url)}
                tooltip
              />
            ))}
          </AvatarGroup>
        )}
      </div>

      {/* Below `sm` the group takes the full width; long labels wrap Remove to its own line. */}
      <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-2 max-sm:w-full">
        <div className="flex min-w-0 flex-1 items-center gap-2 sm:flex-none">
          <span className="shrink-0 text-11 font-medium text-tertiary">{t("project_settings.teams.leader")}</span>
          {isAdmin ? (
            <div className="min-w-0 flex-1 sm:w-44 sm:flex-none">
              <MemberSelect
                testId="project-team-leader"
                value={leaderId}
                onChange={(memberId) => void handleLeaderChange(memberId)}
                memberIds={team.member_ids}
                clearable
                clearLabel={t("project_settings.teams.no_leader")}
                placeholder={t("project_settings.teams.no_leader")}
                tooltip={{
                  heading: t("project_settings.teams.leader_of", { team: team.name }),
                  emptyContent: t("project_settings.teams.no_leader"),
                }}
                disabled={team.member_ids.length === 0}
                variant="select-md"
              />
            </div>
          ) : (
            <span className="min-w-0 truncate text-13">{leaderName ?? t("project_settings.teams.no_leader")}</span>
          )}
        </div>
        {isAdmin && (
          <Button
            variant="ghost"
            size="xs"
            stretch="auto"
            label={t("project_settings.teams.remove")}
            aria-label={t("project_settings.teams.remove_aria_label", { team: team.name })}
            onClick={() => setIsRemoveOpen(true)}
          />
        )}
      </div>
    </div>
  );
});
