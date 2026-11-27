/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect, useId, useRef, useState } from "react";
import { observer } from "mobx-react";
import useSWR from "swr";
import { Button } from "@makeplane/propel/components/button";
import { Icon } from "@makeplane/propel/components/icon";
import { AddOutline, WarningTriangleOutline } from "@makeplane/propel/icons";
// plane imports
import { Loader } from "@plane/blocks/skeleton";
import { setToast } from "@plane/blocks/toast";
import { EUserPermissions, EUserPermissionsLevel, PROJECT_ROUTING_RULES_KEY } from "@plane/constants";
import { useTranslation } from "@plane/i18n";
import type { TProjectRoutingRule, TProjectTeam } from "@plane/types";
// components
import { SettingsHeading } from "@/components/settings/heading";
// hooks
import { useUserPermissions } from "@/hooks/store/user";
// services
import { ProjectRoutingRuleService } from "@/services/project-routing-rule.service";
// local imports
import { AddRoutingRuleForm } from "./add-routing-rule-form";
import { routingRuleRowId } from "./helpers";
import { RoutingRuleRow } from "./routing-rule-row";

const projectRoutingRuleService = new ProjectRoutingRuleService();

const HIGHLIGHT_MS = 2400;

/** The first control of a rule's row that takes the focus: its switch, or its delete button. */
const focusRuleRow = (ruleId: string) =>
  document
    .getElementById(routingRuleRowId(ruleId))
    ?.querySelector<HTMLElement>("[role='switch']:not([aria-disabled='true']), button:not([disabled])")
    ?.focus();

type Props = {
  workspaceSlug: string;
  projectId: string;
  isAdmin: boolean;
  /** The attached teams, from the list above (same cache entry); `undefined` until loaded. */
  projectTeams: TProjectTeam[] | undefined;
};

/** Project settings → Teams → Routing: rules that send labelled or epic work to a team's leader. */
export const RoutingRulesSection = observer(function RoutingRulesSection(props: Props) {
  const { workspaceSlug, projectId, isAdmin, projectTeams } = props;
  const { t } = useTranslation();
  const { allowPermissions } = useUserPermissions();
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [highlightedRuleId, setHighlightedRuleId] = useState<string | null>(null);
  const highlightTimerRef = useRef<number | undefined>(undefined);
  const addRuleRef = useRef<HTMLButtonElement>(null);
  const retryRef = useRef<HTMLButtonElement>(null);
  const hintId = useId();

  // Guests get a 403 (and can't open this tab); don't ask for them.
  const canRead = allowPermissions(
    [EUserPermissions.ADMIN, EUserPermissions.MEMBER],
    EUserPermissionsLevel.PROJECT,
    workspaceSlug,
    projectId
  );
  const {
    data: rules,
    error,
    isLoading,
    mutate,
  } = useSWR(canRead ? PROJECT_ROUTING_RULES_KEY(workspaceSlug, projectId) : null, () =>
    projectRoutingRuleService.list(workspaceSlug, projectId)
  );

  useEffect(() => () => window.clearTimeout(highlightTimerRef.current), []);

  if (!canRead) return null;

  const hasNoTeams = projectTeams?.length === 0;

  const highlight = (ruleId: string) => {
    setHighlightedRuleId(ruleId);
    window.clearTimeout(highlightTimerRef.current);
    highlightTimerRef.current = window.setTimeout(() => setHighlightedRuleId(null), HIGHLIGHT_MS);
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    window.setTimeout(() =>
      document
        .getElementById(routingRuleRowId(ruleId))
        ?.scrollIntoView({ block: "nearest", behavior: reduceMotion ? "auto" : "smooth" })
    );
  };

  const openForm = () => setIsFormOpen(true);

  const closeForm = () => {
    setIsFormOpen(false);
    window.setTimeout(() => addRuleRef.current?.focus());
  };

  const handleCreated = (rule: TProjectRoutingRule) => {
    void mutate((current) => [...(current ?? []), rule], { revalidate: false });
    setIsFormOpen(false);
    setToast({ type: "success", title: t("project_settings.teams.routing.toasts.created") });
    highlight(rule.id);
    // The form held the focus; the new rule's switch is where the user goes next.
    window.setTimeout(() => {
      if (!document.getElementById(routingRuleRowId(rule.id))) return addRuleRef.current?.focus();
      focusRuleRow(rule.id);
    });
  };

  const handleDuplicate = async (ruleId: string) => {
    // Another admin may have added it after the list loaded: load it before pointing at it.
    if (!rules?.some((rule) => rule.id === ruleId)) await mutate();
    highlight(ruleId);
  };

  const handleUpdated = (updated: TProjectRoutingRule) =>
    mutate((current) => current?.map((rule) => (rule.id === updated.id ? updated : rule)), { revalidate: false });

  const handleDeleted = async (ruleId: string) => {
    const index = rules?.findIndex((rule) => rule.id === ruleId) ?? -1;
    const nextRuleId = index >= 0 ? rules?.[index + 1]?.id : undefined;
    await mutate((current) => current?.filter((rule) => rule.id !== ruleId), { revalidate: false });
    // The deleted row held the focus: hand it to the next rule, or to Add rule after the last one (Retry when
    // the list failed to load meanwhile).
    window.setTimeout(() => {
      if (nextRuleId && document.getElementById(routingRuleRowId(nextRuleId))) focusRuleRow(nextRuleId);
      else (retryRef.current ?? addRuleRef.current)?.focus();
    });
  };

  const handleRefresh = () => mutate();

  return (
    <section className="flex flex-col gap-4" data-testid="routing-rules">
      <SettingsHeading
        variant="h4"
        title={t("project_settings.teams.routing.label")}
        description={t("project_settings.teams.routing.description")}
      />

      {isLoading ? (
        <Loader className="flex flex-col gap-2">
          <Loader.Item height="44px" />
          <Loader.Item height="44px" />
        </Loader>
      ) : error ? (
        <div className="flex flex-col items-center gap-3 rounded-md border border-subtle py-8 text-center">
          <span className="grid size-11 place-items-center text-tertiary">
            <WarningTriangleOutline className="size-8" />
          </span>
          <div>
            <h6 className="text-14 font-medium">{t("common.something_went_wrong")}</h6>
            <p className="text-13 text-tertiary">{t("project_settings.teams.routing.errors.load_failed")}</p>
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
      ) : (
        <>
          {!!rules?.length && (
            <ul className="flex flex-col" aria-label={t("project_settings.teams.routing.label")}>
              {rules.map((rule) => (
                <RoutingRuleRow
                  key={rule.id}
                  workspaceSlug={workspaceSlug}
                  projectId={projectId}
                  rule={rule}
                  isAdmin={isAdmin}
                  isHighlighted={highlightedRuleId === rule.id}
                  onUpdated={handleUpdated}
                  onRefresh={handleRefresh}
                  onDeleted={handleDeleted}
                />
              ))}
            </ul>
          )}

          {isAdmin &&
            (isFormOpen && projectTeams?.length ? (
              <AddRoutingRuleForm
                workspaceSlug={workspaceSlug}
                projectId={projectId}
                projectTeams={projectTeams}
                onCancel={closeForm}
                onCreated={handleCreated}
                onDuplicate={(ruleId) => void handleDuplicate(ruleId)}
              />
            ) : (
              <div className="flex flex-col items-start gap-1.5">
                <Button
                  ref={addRuleRef}
                  variant="secondary"
                  size="md"
                  stretch="auto"
                  icon={<Icon icon={AddOutline} />}
                  label={t("project_settings.teams.routing.add_rule")}
                  onClick={openForm}
                  disabled={!projectTeams?.length}
                  aria-describedby={hasNoTeams ? hintId : undefined}
                  data-testid="routing-rules-add"
                />
                {hasNoTeams && (
                  <p id={hintId} className="text-11 text-tertiary">
                    {t("project_settings.teams.routing.attach_team_first")}
                  </p>
                )}
              </div>
            ))}
        </>
      )}
    </section>
  );
});
