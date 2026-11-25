/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

/** A workspace team attached to a project, with its leader in that project. */
export type TProjectTeam = {
  id: string;
  team: { id: string; name: string; member_ids: string[] };
  leader_id: string | null;
  created_at: string;
};

export type TProjectTeamAttachResponse = TProjectTeam & {
  /** Members the attach added to the project, or reactivated. */
  added_member_ids: string[];
};

export type TProjectTeamDetachResponse = {
  removed_member_ids: string[];
  /** Members still in the project after the detach (admins, hand-added members). */
  kept_member_ids: string[];
};
