/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { TApiError, TProjectRoutingRule } from "@plane/types";

type TTranslate = (key: string, params?: Record<string, unknown>) => string;

/** The API's English texts the UI knows, by translation key. Any other text is shown as the server sent it. */
const KNOWN_SERVER_MESSAGES: Record<string, string> = {
  "Attach the team to this project first.": "project_settings.teams.routing.errors.team_not_attached",
  "The label was deleted.": "project_settings.teams.routing.errors.label_deleted",
  "The epic was deleted or archived.": "project_settings.teams.routing.errors.epic_deleted",
};

const translateServerMessage = (message: string, t: TTranslate) => {
  const key = KNOWN_SERVER_MESSAGES[message];
  return key ? t(key) : message;
};

/** Each field's first message of a 400, translated where known. Empty for any other error. */
export const routingRuleFieldErrors = (error: unknown, t: TTranslate): Record<string, string> => {
  const { status, data } = (error ?? {}) as TApiError;
  // A non-JSON 400 (a proxy's HTML page) arrives as a string.
  if (status !== 400 || !data || typeof data !== "object") return {};
  return Object.fromEntries(
    Object.entries(data).flatMap(([field, messages]) => {
      const first = Array.isArray(messages) ? messages[0] : messages;
      return typeof first === "string" ? [[field, translateServerMessage(first, t)]] : [];
    })
  );
};

/** Message of the toast for a failed write, as `projectTeamErrorMessage` does for teams. */
export const routingRuleErrorMessage = (error: unknown, t: TTranslate, fallback: string) => {
  const { status } = (error ?? {}) as TApiError;
  if (status === 403) return t("project_settings.teams.routing.errors.forbidden");
  if (status === 404) return t("project_settings.teams.routing.errors.not_found");
  return Object.values(routingRuleFieldErrors(error, t))[0] ?? fallback;
};

/** "Label Flutter" / "Epic MOB-12 Login flow": the trigger as plain text, for accessible names. */
export const routingRuleTriggerText = (rule: TProjectRoutingRule, t: TTranslate) =>
  rule.epic
    ? t("project_settings.teams.routing.rule_epic", {
        identifier: `${rule.epic.project_identifier}-${rule.epic.sequence_id}`,
        name: rule.epic.name,
      })
    : t("project_settings.teams.routing.rule_label", { name: rule.label?.name ?? "" });

/** "Label Flutter routes to Frontend": names the row's controls. */
export const routingRuleSummary = (rule: TProjectRoutingRule, t: TTranslate) =>
  t("project_settings.teams.routing.rule_summary", {
    trigger: routingRuleTriggerText(rule, t),
    team: rule.team.name,
  });

/** DOM id of a rule's row, for scrolling to it and moving the focus into it. */
export const routingRuleRowId = (ruleId: string) => `routing-rule-${ruleId}`;
