/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect, useId, useRef, useState } from "react";
import { observer } from "mobx-react";
import { Banner } from "@makeplane/propel/components/banner";
import { Button } from "@makeplane/propel/components/button";
import { RadioGroupField, RadioGroupFieldOption } from "@makeplane/propel/components/radio-group-field";
import { FieldLabel } from "@makeplane/propel/elements/field";
// plane imports
import { Select } from "@plane/blocks/select";
import { setToast } from "@plane/blocks/toast";
import { useTranslation } from "@plane/i18n";
import type {
  IIssueLabel,
  ISearchIssueResponse,
  TApiError,
  TProjectRoutingRule,
  TProjectRoutingRuleCreate,
  TProjectTeam,
  TRoutingRuleTriggerType,
} from "@plane/types";
// hooks
import { useLabel } from "@/hooks/store/use-label";
import { useMember } from "@/hooks/store/use-member";
// services
import { ProjectService } from "@/services/project";
import { ProjectRoutingRuleService } from "@/services/project-routing-rule.service";
// local imports
import { routingRuleErrorMessage, routingRuleFieldErrors } from "./helpers";

const projectService = new ProjectService();
const projectRoutingRuleService = new ProjectRoutingRuleService();

const epicLabel = (epic: ISearchIssueResponse) => `${epic.project__identifier}-${epic.sequence_id} ${epic.name}`;

type Props = {
  workspaceSlug: string;
  projectId: string;
  /** The project's attached teams, the only ones a rule can send work to. */
  projectTeams: TProjectTeam[];
  onCancel: () => void;
  onCreated: (rule: TProjectRoutingRule) => void;
  /** A rule with the same trigger and team exists: the id the 409 named. */
  onDuplicate: (ruleId: string) => void;
};

export const AddRoutingRuleForm = observer(function AddRoutingRuleForm(props: Props) {
  const { workspaceSlug, projectId, projectTeams, onCancel, onCreated, onDuplicate } = props;
  const { t } = useTranslation();
  const { getProjectLabels, fetchProjectLabels } = useLabel();
  const {
    workspace: { getWorkspaceMemberDetails },
  } = useMember();
  const [triggerType, setTriggerType] = useState<TRoutingRuleTriggerType>("label");
  const [labelId, setLabelId] = useState<string | null>(null);
  const [epic, setEpic] = useState<ISearchIssueResponse | null>(null);
  const [teamId, setTeamId] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [isDuplicate, setIsDuplicate] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  // Two submits in one frame both see the old state; the ref stops the second POST.
  const isSubmittingRef = useRef(false);
  // Every work item the epic search returned: the infinite Select reports the picked id only.
  const searchedEpicsRef = useRef(new Map<string, ISearchIssueResponse>());
  const formRef = useRef<HTMLFormElement>(null);
  const formId = useId();
  const triggerPickerId = `${formId}-trigger`;
  const teamPickerId = `${formId}-team`;

  // Opening the form moves the focus to its first control, the checked trigger type. A tick later, so the
  // radio group's own focus tracking is in place and the first arrow key already moves the selection.
  useEffect(() => {
    const timer = window.setTimeout(() =>
      formRef.current?.querySelector<HTMLElement>("[role='radio'][aria-checked='true']")?.focus()
    );
    return () => window.clearTimeout(timer);
  }, []);

  const labels = getProjectLabels(projectId);
  // The store keeps the labels once loaded, so this asks once (unless a project page loaded them already).
  useEffect(() => {
    if (!labels) void fetchProjectLabels(workspaceSlug, projectId).catch(() => undefined);
  }, [labels, fetchProjectLabels, workspaceSlug, projectId]);

  const selectedLabel = labels?.find((label) => label.id === labelId) ?? null;
  const selectedTeam = projectTeams.find((projectTeam) => projectTeam.team.id === teamId) ?? null;
  const triggerError = triggerType === "label" ? fieldErrors.label_id : fieldErrors.epic_id;
  // A team detached meanwhile drops out of the list, and out of the selection with it.
  const canSubmit = !!selectedTeam && (triggerType === "label" ? !!selectedLabel : !!epic) && !isSubmitting;

  // Any change clears the server's verdict on the old values.
  const clearErrors = (...fields: string[]) => {
    setIsDuplicate(false);
    setFieldErrors((current) => {
      const next = { ...current };
      for (const field of fields) delete next[field];
      return next;
    });
  };

  const handleSubmit = async () => {
    if (!canSubmit || !selectedTeam || isSubmittingRef.current) return;
    const data: TProjectRoutingRuleCreate =
      triggerType === "label"
        ? { trigger_type: "label", label_id: selectedLabel?.id ?? "", team_id: selectedTeam.team.id }
        : { trigger_type: "epic", epic_id: epic?.id ?? "", team_id: selectedTeam.team.id };
    isSubmittingRef.current = true;
    setIsSubmitting(true);
    try {
      const rule = await projectRoutingRuleService.create(workspaceSlug, projectId, data);
      onCreated(rule);
    } catch (error) {
      const { status, data: body } = (error ?? {}) as TApiError;
      if (status === 409) {
        setIsDuplicate(true);
        const existingId = (body as { id?: unknown } | undefined)?.id;
        if (typeof existingId === "string") onDuplicate(existingId);
      } else {
        const errors = routingRuleFieldErrors(error, t);
        setFieldErrors(errors);
        // A 400 on a field the form shows sits next to that field; anything else gets a toast.
        if (!["trigger_type", "label_id", "epic_id", "team_id"].some((field) => field in errors))
          setToast({
            type: "error",
            title: t("common.error.label"),
            message: routingRuleErrorMessage(error, t, t("project_settings.teams.routing.errors.create_failed")),
          });
      }
      isSubmittingRef.current = false;
      setIsSubmitting(false);
    }
  };

  return (
    <form
      ref={formRef}
      className="flex flex-col gap-4 rounded-lg border border-subtle bg-layer-2 p-4"
      aria-label={t("project_settings.teams.routing.add_rule")}
      onSubmit={(event) => {
        event.preventDefault();
        void handleSubmit();
      }}
      onKeyDown={(event) => {
        // Escape closes the form, unless a picker's own dropdown took it first.
        if (event.key === "Escape" && !event.defaultPrevented && !isSubmitting) onCancel();
      }}
      data-testid="routing-rule-form"
    >
      <RadioGroupField<TRoutingRuleTriggerType>
        label={t("project_settings.teams.routing.form.trigger_type")}
        name="trigger_type"
        size="lg"
        density="compact"
        orientation="horizontal"
        value={triggerType}
        onValueChange={(value) => {
          setTriggerType(value);
          clearErrors("trigger_type", "label_id", "epic_id");
        }}
        error={fieldErrors.trigger_type}
      >
        <RadioGroupFieldOption value="label" label={t("project_settings.teams.routing.trigger.label")} />
        <RadioGroupFieldOption value="epic" label={t("project_settings.teams.routing.trigger.epic")} />
      </RadioGroupField>

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="flex min-w-0 flex-col gap-1.5">
          <FieldLabel size="lg" inset={false} htmlFor={triggerPickerId}>
            {t(
              triggerType === "label"
                ? "project_settings.teams.routing.trigger.label"
                : "project_settings.teams.routing.trigger.epic"
            )}
          </FieldLabel>
          {triggerType === "label" ? (
            <Select<IIssueLabel>
              getValues={() => labels ?? []}
              value={selectedLabel}
              onChange={(id) => {
                setLabelId(id);
                clearErrors("label_id");
              }}
              getOptionValue={(label) => label.id}
              getOptionLabel={(label) => label.name}
              getOptionIcon={(label) => (
                <span
                  className="size-2 shrink-0 rounded-full"
                  style={{ backgroundColor: label.color || "#000000" }}
                  aria-hidden="true"
                />
              )}
              placeholder={t("project_settings.teams.routing.form.select_label")}
              searchPlaceholder={t("project_settings.teams.routing.form.search_labels")}
              emptyMessage={t("project_settings.teams.routing.form.no_labels")}
              contentSizing="anchor"
            >
              <Select.Trigger<IIssueLabel> id={triggerPickerId} variant="select-lg" data-testid="routing-rule-label">
                <Select.Value />
              </Select.Trigger>
            </Select>
          ) : (
            <Select<ISearchIssueResponse>
              infinite
              getValues={async ({ search }) => {
                // The search leaves out archived work items, which an epic rule can't use.
                const results = await projectService.projectIssuesSearch(workspaceSlug, projectId, {
                  search: search ?? "",
                  workspace_search: false,
                });
                for (const item of results) searchedEpicsRef.current.set(item.id, item);
                return { results, next_page_results: false };
              }}
              value={epic}
              onChange={(id) => {
                setEpic(searchedEpicsRef.current.get(id) ?? null);
                clearErrors("epic_id");
              }}
              getOptionValue={(item) => item.id}
              getOptionLabel={epicLabel}
              placeholder={t("project_settings.teams.routing.form.select_epic")}
              searchPlaceholder={t("project_settings.teams.routing.form.search_epics")}
              emptyMessage={t("project_settings.teams.routing.form.no_epics")}
              contentSizing="anchor"
            >
              <Select.Trigger<ISearchIssueResponse>
                id={triggerPickerId}
                variant="select-lg"
                data-testid="routing-rule-epic"
              >
                <Select.Value />
              </Select.Trigger>
            </Select>
          )}
          {triggerError && (
            <span className="text-11 text-danger-primary" role="alert">
              {triggerError}
            </span>
          )}
        </div>

        <div className="flex min-w-0 flex-col gap-1.5">
          <FieldLabel size="lg" inset={false} htmlFor={teamPickerId}>
            {t("project_settings.teams.routing.form.team")}
          </FieldLabel>
          <Select<TProjectTeam>
            getValues={() => projectTeams}
            value={selectedTeam}
            onChange={(id) => {
              setTeamId(id);
              clearErrors("team_id");
            }}
            getOptionValue={(projectTeam) => projectTeam.team.id}
            getOptionLabel={(projectTeam) => projectTeam.team.name}
            getOptionTrailing={(projectTeam) => (
              <span className="text-11 text-tertiary">
                {projectTeam.leader_id
                  ? getWorkspaceMemberDetails(projectTeam.leader_id)?.member.display_name
                  : t("project_settings.teams.routing.no_leader")}
              </span>
            )}
            placeholder={t("project_settings.teams.routing.form.select_team")}
            searchPlaceholder={t("project_settings.teams.search_teams")}
            pinSelected={false}
            contentSizing="anchor"
          >
            <Select.Trigger<TProjectTeam> id={teamPickerId} variant="select-lg" data-testid="routing-rule-team">
              <Select.Value />
            </Select.Trigger>
          </Select>
          {fieldErrors.team_id && (
            <span className="text-11 text-danger-primary" role="alert">
              {fieldErrors.team_id}
            </span>
          )}
          {selectedTeam && !selectedTeam.leader_id && (
            <Banner
              placement="inline"
              variant="warning"
              size="sm"
              title={t("project_settings.teams.routing.form.no_leader_warning", { team: selectedTeam.team.name })}
              data-testid="routing-rule-no-leader-warning"
            />
          )}
        </div>
      </div>

      <div className="flex flex-col-reverse items-stretch gap-3 sm:flex-row sm:items-center sm:justify-end">
        {isDuplicate && (
          <p className="text-13 text-danger-primary sm:mr-auto" role="alert" data-testid="routing-rule-duplicate">
            {t("project_settings.teams.routing.form.duplicate")}
          </p>
        )}
        <div className="flex justify-end gap-2">
          <Button
            variant="secondary"
            size="md"
            stretch="auto"
            label={t("common.cancel")}
            onClick={onCancel}
            disabled={isSubmitting}
          />
          <Button
            variant="primary"
            size="md"
            stretch="auto"
            type="submit"
            loading={isSubmitting}
            disabled={!canSubmit}
            label={
              isSubmitting
                ? t("project_settings.teams.routing.form.submitting")
                : t("project_settings.teams.routing.form.submit")
            }
            data-testid="routing-rule-submit"
          />
        </div>
      </div>
    </form>
  );
});
