/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

export type TWorkspaceTeam = {
  id: string;
  name: string;
  description: string;
  default_repository: { id: string; full_name: string } | null;
  member_ids: string[];
  created_at: string;
};

export type TWorkspaceTeamPayload = {
  name?: string;
  description?: string;
  default_repository_id?: string | null;
};
