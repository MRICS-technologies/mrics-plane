/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

export type TRoutingRuleTriggerType = "label" | "epic";

/** Why a rule doesn't fire; the first that applies wins, in this order. */
export type TRoutingRuleInactiveReason = "label_deleted" | "epic_deleted" | "team_detached" | "disabled";

/** "Label X → team T" or "epic Y → team T": matching work goes to the team's leader in this project. */
export type TProjectRoutingRule = {
  id: string;
  trigger_type: TRoutingRuleTriggerType;
  /** Set for a label rule. */
  label: { id: string; name: string; color: string } | null;
  /** Set for an epic rule: any work item of the project; only its direct children match. */
  epic: { id: string; name: string; sequence_id: number; project_identifier: string } | null;
  team: { id: string; name: string };
  /** The team's leader in this project; `null` when it has none or isn't attached. */
  leader_id: string | null;
  team_attached: boolean;
  enabled: boolean;
  /** Enabled, team attached and trigger live. */
  is_active: boolean;
  inactive_reason: TRoutingRuleInactiveReason | null;
  created_at: string;
};

export type TProjectRoutingRuleCreate =
  | { trigger_type: "label"; label_id: string; team_id: string }
  | { trigger_type: "epic"; epic_id: string; team_id: string };
