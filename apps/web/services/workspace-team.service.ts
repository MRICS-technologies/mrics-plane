/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { API_BASE_URL } from "@plane/constants";
import type { TApiError, TWorkspaceTeam, TWorkspaceTeamPayload } from "@plane/types";
import { APIService } from "@/services/api.service";

export class WorkspaceTeamService extends APIService {
  constructor() {
    super(API_BASE_URL);
  }

  private async unwrap<T>(call: Promise<{ data: T }>): Promise<T> {
    return call
      .then((response) => response?.data)
      .catch((error) => {
        throw { status: error?.response?.status, data: error?.response?.data } as TApiError;
      });
  }

  async list(workspaceSlug: string): Promise<TWorkspaceTeam[]> {
    return this.unwrap(this.get(`/api/workspaces/${workspaceSlug}/teams/`));
  }

  async create(workspaceSlug: string, data: TWorkspaceTeamPayload): Promise<TWorkspaceTeam> {
    return this.unwrap(this.post(`/api/workspaces/${workspaceSlug}/teams/`, data));
  }

  async update(workspaceSlug: string, teamId: string, data: TWorkspaceTeamPayload): Promise<TWorkspaceTeam> {
    return this.unwrap(this.patch(`/api/workspaces/${workspaceSlug}/teams/${teamId}/`, data));
  }

  async destroy(workspaceSlug: string, teamId: string): Promise<void> {
    return this.unwrap(this.delete(`/api/workspaces/${workspaceSlug}/teams/${teamId}/`));
  }

  /** Adds members to the team; members of another team are moved. */
  async addMembers(workspaceSlug: string, teamId: string, memberIds: string[]): Promise<TWorkspaceTeam> {
    return this.unwrap(
      this.post(`/api/workspaces/${workspaceSlug}/teams/${teamId}/members/`, { member_ids: memberIds })
    );
  }

  async removeMember(workspaceSlug: string, teamId: string, memberId: string): Promise<void> {
    return this.unwrap(this.delete(`/api/workspaces/${workspaceSlug}/teams/${teamId}/members/${memberId}/`));
  }
}
