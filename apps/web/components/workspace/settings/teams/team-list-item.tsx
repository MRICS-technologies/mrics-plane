/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { observer } from "mobx-react";
import { Avatar } from "@makeplane/propel/components/avatar";
import { Button } from "@makeplane/propel/components/button";
import { CloseCircleOutline } from "@makeplane/propel/icons";
// plane imports
import { ConfirmDialog } from "@plane/blocks/dialog";
import { Select } from "@plane/blocks/select";
import { setToast } from "@plane/blocks/toast";
import { useTranslation } from "@plane/i18n";
import type { TApiError, TWorkspaceTeam } from "@plane/types";
import { getFileURL } from "@plane/utils";
// components
import { MemberSelect } from "@/components/dropdowns/member/member-select";
// hooks
import { useMember } from "@/hooks/store/use-member";
// services
import { WorkspaceTeamService } from "@/services/workspace-team.service";
// local imports
import { TeamFormModal } from "./team-form-modal";

const workspaceTeamService = new WorkspaceTeamService();

export type TTeamRepositoryOption = { id: string; full_name: string };

/** i18n key of the toast for a failed team write. */
export const teamErrorKey = (error: unknown) => {
  const status = (error as TApiError)?.status;
  if (status === 409) return "workspace_settings.settings.teams.errors.duplicate_name";
  if (status === 403) return "workspace_settings.settings.teams.errors.forbidden";
  return "workspace_settings.settings.teams.errors.save_failed";
};

type Props = {
  workspaceSlug: string;
  team: TWorkspaceTeam;
  /** Every team of the workspace, to tell which team a picked member is moved from. */
  teams: TWorkspaceTeam[];
  /** Enabled repositories of the workspace's GitHub installation. */
  repositories: TTeamRepositoryOption[];
  isAdmin: boolean;
  onChange: () => Promise<unknown>;
};

export const TeamListItem = observer(function TeamListItem(props: Props) {
  const { workspaceSlug, team, teams, repositories, isAdmin, onChange } = props;
  const { t } = useTranslation();
  const {
    workspace: { workspaceMemberIds, getWorkspaceMemberDetails },
  } = useMember();
  const [isRenameOpen, setIsRenameOpen] = useState(false);
  const [isDeleteOpen, setIsDeleteOpen] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [pendingMove, setPendingMove] = useState<{ memberId: string; from: TWorkspaceTeam } | null>(null);
  const [isMoving, setIsMoving] = useState(false);

  const memberName = (memberId: string) => getWorkspaceMemberDetails(memberId)?.member.display_name ?? "";
  const addableMemberIds = (workspaceMemberIds ?? []).filter(
    (memberId) => getWorkspaceMemberDetails(memberId)?.is_active !== false && !team.member_ids.includes(memberId)
  );
  const none: TTeamRepositoryOption = {
    id: "",
    full_name: t("workspace_settings.settings.teams.no_default_repository"),
  };
  const current = team.default_repository;
  // A default repository disabled since it was picked still shows as the value.
  const repositoryOptions = [
    none,
    ...repositories,
    ...(current && !repositories.some((repository) => repository.id === current.id) ? [current] : []),
  ];

  const run = async (write: () => Promise<unknown>) => {
    try {
      await write();
      await onChange();
    } catch (error) {
      setToast({ type: "error", title: t("common.error.label"), message: t(teamErrorKey(error)) });
      throw error;
    }
  };
  const runQuietly = (write: () => Promise<unknown>) => run(write).catch(() => undefined);

  const addMember = (memberId: string) =>
    runQuietly(() => workspaceTeamService.addMembers(workspaceSlug, team.id, [memberId]));

  const handlePickMember = (memberId: string) => {
    const from = teams.find((other) => other.id !== team.id && other.member_ids.includes(memberId));
    if (from) setPendingMove({ memberId, from });
    else void addMember(memberId);
  };

  const handleConfirmMove = async () => {
    if (!pendingMove) return;
    setIsMoving(true);
    await addMember(pendingMove.memberId);
    setIsMoving(false);
    setPendingMove(null);
  };

  const handleDelete = async () => {
    setIsDeleting(true);
    await runQuietly(() => workspaceTeamService.destroy(workspaceSlug, team.id));
    setIsDeleting(false);
    setIsDeleteOpen(false);
  };

  return (
    <div className="flex flex-col gap-3 border-b border-subtle py-4" data-testid="workspace-team">
      {isRenameOpen && (
        <TeamFormModal
          title={t("workspace_settings.settings.teams.form.rename_title")}
          submitLabel={t("workspace_settings.settings.teams.form.save")}
          initialName={team.name}
          onClose={() => setIsRenameOpen(false)}
          onSubmit={(name) => run(() => workspaceTeamService.update(workspaceSlug, team.id, { name }))}
        />
      )}
      <ConfirmDialog
        isOpen={isDeleteOpen}
        handleClose={() => setIsDeleteOpen(false)}
        handleSubmit={handleDelete}
        isSubmitting={isDeleting}
        primaryButtonText={{ default: t("common.delete"), loading: t("common.deleting") }}
        title={t("workspace_settings.settings.teams.delete_modal.title")}
        content={t("workspace_settings.settings.teams.delete_modal.content", { name: team.name })}
      />
      <ConfirmDialog
        isOpen={Boolean(pendingMove)}
        variant="warning"
        handleClose={() => setPendingMove(null)}
        handleSubmit={handleConfirmMove}
        isSubmitting={isMoving}
        primaryButtonText={{
          default: t("workspace_settings.settings.teams.move_modal.confirm"),
          loading: t("workspace_settings.settings.teams.move_modal.confirm"),
        }}
        title={t("workspace_settings.settings.teams.move_modal.title")}
        content={
          pendingMove
            ? t("workspace_settings.settings.teams.move_modal.content", {
                member: memberName(pendingMove.memberId),
                from: pendingMove.from.name,
                to: team.name,
              })
            : ""
        }
      />

      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-0.5">
          <span className="truncate text-14 font-medium">{team.name}</span>
          <span className="text-11 text-tertiary">
            {t("workspace_settings.settings.teams.member_count", { count: team.member_ids.length })}
          </span>
        </div>
        {isAdmin && (
          <div className="flex flex-shrink-0 items-center gap-2">
            <Button
              variant="ghost"
              size="xs"
              stretch="auto"
              label={t("workspace_settings.settings.teams.rename")}
              onClick={() => setIsRenameOpen(true)}
            />
            <Button
              variant="ghost"
              size="xs"
              stretch="auto"
              label={t("common.delete")}
              onClick={() => setIsDeleteOpen(true)}
            />
          </div>
        )}
      </div>

      <div className="flex flex-col gap-1.5">
        <span className="text-11 font-medium text-tertiary">
          {t("workspace_settings.settings.teams.default_repository")}
        </span>
        {isAdmin ? (
          <div className="flex flex-col gap-1">
            <div className="w-72 max-w-full">
              <Select<TTeamRepositoryOption>
                getValues={() => repositoryOptions}
                value={repositoryOptions.find((option) => option.id === (current?.id ?? "")) ?? none}
                onChange={(id) =>
                  void runQuietly(() =>
                    workspaceTeamService.update(workspaceSlug, team.id, { default_repository_id: id || null })
                  )
                }
                getOptionValue={(option) => option.id}
                getOptionLabel={(option) => option.full_name}
                disabled={repositories.length === 0 && !current}
                contentSizing="anchor"
              >
                <Select.Trigger<TTeamRepositoryOption> variant="select-md">
                  <Select.Value />
                </Select.Trigger>
              </Select>
            </div>
            {repositories.length === 0 && (
              <span className="text-11 text-tertiary">
                {t("workspace_settings.settings.teams.no_repositories_hint")}
              </span>
            )}
          </div>
        ) : (
          <span className="text-13">
            {current?.full_name ?? t("workspace_settings.settings.teams.no_default_repository")}
          </span>
        )}
      </div>

      <div className="flex flex-col gap-1.5">
        <span className="text-11 font-medium text-tertiary">{t("common.members")}</span>
        <div className="flex flex-wrap items-center gap-2">
          {team.member_ids.length === 0 && (
            <span className="text-13 text-tertiary">{t("workspace_settings.settings.teams.no_members")}</span>
          )}
          {team.member_ids.map((memberId) => {
            const member = getWorkspaceMemberDetails(memberId)?.member;
            if (!member) return null;
            return (
              <span
                key={memberId}
                className="flex items-center gap-1.5 rounded-sm border-[0.5px] border-subtle bg-surface-2 py-0.5 pr-1.5 pl-1 text-13"
              >
                <Avatar
                  alt={member.display_name}
                  fallback={member.display_name?.[0]?.toUpperCase()}
                  src={getFileURL(member.avatar_url)}
                  size="2xs"
                />
                {member.display_name}
                {isAdmin && (
                  <button
                    type="button"
                    onClick={() =>
                      void runQuietly(() => workspaceTeamService.removeMember(workspaceSlug, team.id, memberId))
                    }
                    aria-label={t("workspace_settings.settings.teams.remove_member_aria_label", {
                      name: member.display_name,
                    })}
                    className="grid place-items-center text-tertiary hover:text-primary"
                  >
                    <CloseCircleOutline className="size-3.5" />
                  </button>
                )}
              </span>
            );
          })}
          {isAdmin && addableMemberIds.length > 0 && (
            <MemberSelect
              value={null}
              onChange={handlePickMember}
              memberIds={addableMemberIds}
              placeholder={t("workspace_settings.settings.teams.add_member")}
              variant="pill-sm"
            />
          )}
        </div>
      </div>
    </div>
  );
});
