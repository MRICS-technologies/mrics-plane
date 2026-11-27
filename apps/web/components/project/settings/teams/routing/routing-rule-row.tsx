/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useId, useRef, useState } from "react";
import { observer } from "mobx-react";
import { Icon } from "@makeplane/propel/components/icon";
import { IconButton } from "@makeplane/propel/components/icon-button";
import { Switch } from "@makeplane/propel/components/switch";
import { Tooltip } from "@makeplane/propel/components/tooltip";
import { DeleteOutline, WarningTriangleOutline } from "@makeplane/propel/icons";
// plane imports
import { ConfirmDialog } from "@plane/blocks/dialog";
import { setToast } from "@plane/blocks/toast";
import { useTranslation } from "@plane/i18n";
import type { TApiError, TProjectRoutingRule, TRoutingRuleInactiveReason } from "@plane/types";
import { cn } from "@plane/utils";
// hooks
import { useMember } from "@/hooks/store/use-member";
// services
import { ProjectRoutingRuleService } from "@/services/project-routing-rule.service";
// local imports
import { routingRuleErrorMessage, routingRuleRowId, routingRuleSummary } from "./helpers";

const projectRoutingRuleService = new ProjectRoutingRuleService();

/** Reasons a rule can't be turned on; `disabled` is just the switch being off. */
const BLOCKING_REASONS: Partial<Record<TRoutingRuleInactiveReason, string>> = {
  label_deleted: "project_settings.teams.routing.inactive.label_deleted",
  epic_deleted: "project_settings.teams.routing.inactive.epic_deleted",
  team_detached: "project_settings.teams.routing.inactive.team_detached",
};

type Props = {
  workspaceSlug: string;
  projectId: string;
  rule: TProjectRoutingRule;
  isAdmin: boolean;
  /** Briefly marks the row: just added, or the one a duplicate pointed at. */
  isHighlighted: boolean;
  /** The row the API returned after a toggle. */
  onUpdated: (rule: TProjectRoutingRule) => Promise<unknown>;
  /** Re-fetches the list. */
  onRefresh: () => Promise<unknown>;
  /** Drops the row once the rule is gone, then moves the focus on. */
  onDeleted: (ruleId: string) => Promise<unknown>;
};

export const RoutingRuleRow = observer(function RoutingRuleRow(props: Props) {
  const { workspaceSlug, projectId, rule, isAdmin, isHighlighted, onUpdated, onRefresh, onDeleted } = props;
  const { t } = useTranslation();
  const {
    workspace: { getWorkspaceMemberDetails },
  } = useMember();
  const [isSaving, setIsSaving] = useState(false);
  const [isDeleteOpen, setIsDeleteOpen] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const controlsRef = useRef<HTMLDivElement>(null);
  const reasonId = useId();

  const blockingReason = rule.inactive_reason ? BLOCKING_REASONS[rule.inactive_reason] : undefined;
  const summary = routingRuleSummary(rule, t);
  const leaderName = rule.leader_id ? getWorkspaceMemberDetails(rule.leader_id)?.member.display_name : undefined;
  const textTone = rule.is_active ? "text-primary" : "text-tertiary";

  const handleToggle = async (enabled: boolean) => {
    setIsSaving(true);
    try {
      const updated = await projectRoutingRuleService.setEnabled(workspaceSlug, projectId, rule.id, enabled);
      await onUpdated(updated);
      setToast({
        type: "success",
        title: t(
          enabled ? "project_settings.teams.routing.toasts.enabled" : "project_settings.teams.routing.toasts.disabled"
        ),
      });
    } catch (error) {
      setToast({
        type: "error",
        title: t("common.error.label"),
        message: routingRuleErrorMessage(error, t, t("project_settings.teams.routing.errors.update_failed")),
      });
      // A 400 means the team, label or epic changed meanwhile; show what the server has now.
      void onRefresh();
    } finally {
      setIsSaving(false);
      // Disabling the switch dropped the focus it had; give it back unless the user has moved on.
      window.setTimeout(() => {
        if (document.activeElement === document.body)
          controlsRef.current?.querySelector<HTMLElement>("[role='switch']:not([aria-disabled='true'])")?.focus();
      });
    }
  };

  const handleDelete = async () => {
    setIsDeleting(true);
    try {
      await projectRoutingRuleService.remove(workspaceSlug, projectId, rule.id);
      setToast({ type: "success", title: t("project_settings.teams.routing.toasts.deleted") });
    } catch (error) {
      if ((error as TApiError | undefined)?.status !== 404) {
        setToast({
          type: "error",
          title: t("common.error.label"),
          message: routingRuleErrorMessage(error, t, t("project_settings.teams.routing.errors.delete_failed")),
        });
        setIsDeleting(false);
        setIsDeleteOpen(false);
        void onRefresh();
        return;
      }
      // Another admin deleted it first: what the user asked for has happened.
      setToast({ type: "info", title: t("project_settings.teams.routing.toasts.already_deleted") });
    }
    // The row, and this dialog with it, unmount once the rule leaves the list.
    await onDeleted(rule.id);
  };

  const leader = leaderName ? (
    <span className={cn("min-w-0 truncate", textTone)}>
      {t("project_settings.teams.routing.leader_name", { name: leaderName })}
    </span>
  ) : rule.leader_id ? null : rule.is_active ? (
    <Tooltip label={t("project_settings.teams.routing.no_leader_hint")}>
      <span className="inline-flex min-w-0 items-center gap-1 text-warning-primary">
        <WarningTriangleOutline className="size-3.5 shrink-0" aria-hidden="true" />
        <span className="truncate">{t("project_settings.teams.routing.no_leader")}</span>
        <span className="sr-only">{t("project_settings.teams.routing.no_leader_hint")}</span>
      </span>
    </Tooltip>
  ) : (
    <span className="min-w-0 truncate text-tertiary">{t("project_settings.teams.routing.no_leader")}</span>
  );

  return (
    <li
      id={routingRuleRowId(rule.id)}
      className="relative isolate flex flex-col gap-1 border-b border-subtle py-3"
      data-testid="routing-rule"
    >
      {/* The highlight bleeds past the text through its ring, which (unlike a wider box) adds no scroll overflow. */}
      <span
        className={cn(
          "pointer-events-none absolute inset-x-0 inset-y-2 -z-10 rounded-xs bg-accent-subtle opacity-0 ring-8 ring-accent-subtle transition-opacity duration-700 motion-reduce:transition-none",
          { "opacity-100": isHighlighted }
        )}
        aria-hidden="true"
      />
      {isAdmin && (
        <ConfirmDialog
          isOpen={isDeleteOpen}
          handleClose={() => setIsDeleteOpen(false)}
          handleSubmit={handleDelete}
          isSubmitting={isDeleting}
          primaryButtonText={{
            default: t("project_settings.teams.routing.delete_modal.confirm"),
            loading: t("project_settings.teams.routing.delete_modal.confirming"),
          }}
          title={t("project_settings.teams.routing.delete_modal.title")}
          content={
            rule.epic
              ? t("project_settings.teams.routing.delete_modal.content_epic", {
                  epic: `${rule.epic.project_identifier}-${rule.epic.sequence_id} ${rule.epic.name}`,
                  team: rule.team.name,
                })
              : t("project_settings.teams.routing.delete_modal.content_label", {
                  label: rule.label?.name ?? "",
                  team: rule.team.name,
                })
          }
        />
      )}

      {/* Trigger → team, then the leader and the controls; below `sm` those two halves take a line each. */}
      <div className="flex flex-wrap items-center gap-x-2 gap-y-2 text-13">
        <div className={cn("flex min-w-0 items-center gap-2 max-sm:basis-full", textTone)}>
          <span className="shrink-0 text-tertiary">
            {t(
              rule.epic ? "project_settings.teams.routing.trigger.epic" : "project_settings.teams.routing.trigger.label"
            )}
          </span>
          {rule.epic ? (
            <span className="flex min-w-0 items-center gap-1.5">
              <span className="shrink-0 text-11 font-medium text-tertiary">
                {rule.epic.project_identifier}-{rule.epic.sequence_id}
              </span>
              <span className="max-w-60 min-w-0 truncate">{rule.epic.name}</span>
            </span>
          ) : (
            <span className="inline-flex max-w-40 min-w-0 shrink items-center gap-1.5 rounded-full border border-strong px-2 py-0.5 text-11">
              <span
                className="size-1.5 shrink-0 rounded-full"
                style={{ backgroundColor: rule.label?.color || "#000000" }}
                aria-hidden="true"
              />
              <span className="truncate font-medium">{rule.label?.name}</span>
            </span>
          )}
          <span className="shrink-0 text-tertiary" aria-hidden="true">
            →
          </span>
          <span className="sr-only">{t("project_settings.teams.routing.routes_to")}</span>
          <span className="min-w-0 truncate font-medium">{rule.team.name}</span>
        </div>

        <div className="flex min-w-0 flex-1 items-center gap-2">
          <span className="shrink-0 text-tertiary max-sm:hidden" aria-hidden="true">
            →
          </span>
          {leader}
          <div ref={controlsRef} className="ml-auto flex shrink-0 items-center gap-2 pl-2">
            {isAdmin ? (
              <>
                <Switch
                  size="sm"
                  checked={rule.enabled}
                  onCheckedChange={(checked) => void handleToggle(checked)}
                  disabled={isSaving || !!blockingReason}
                  aria-label={t("project_settings.teams.routing.toggle_aria_label", { rule: summary })}
                  aria-describedby={blockingReason ? reasonId : undefined}
                  data-testid="routing-rule-toggle"
                />
                <IconButton
                  variant="ghost"
                  size="sm"
                  icon={<Icon icon={DeleteOutline} />}
                  aria-label={t("project_settings.teams.routing.delete_aria_label", { rule: summary })}
                  onClick={() => setIsDeleteOpen(true)}
                  data-testid="routing-rule-delete"
                />
              </>
            ) : (
              <span className="text-11 font-medium text-tertiary">
                {t(
                  rule.enabled ? "project_settings.teams.routing.state.on" : "project_settings.teams.routing.state.off"
                )}
              </span>
            )}
          </div>
        </div>
      </div>

      {blockingReason && (
        <p id={reasonId} className="flex items-start gap-1.5 text-11 text-tertiary">
          <WarningTriangleOutline className="mt-px size-3 shrink-0 text-warning-primary" aria-hidden="true" />
          <span>{t(blockingReason)}</span>
        </p>
      )}
    </li>
  );
});
