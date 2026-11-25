/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { API_BASE_URL } from "@plane/constants";
import type { TApiError, TProjectTeam, TProjectTeamAttachResponse, TProjectTeamDetachResponse } from "@plane/types";
import { APIService } from "@/services/api.service";

export class ProjectTeamService extends APIService {
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

  async list(workspaceSlug: string, projectId: string): Promise<TProjectTeam[]> {
    return this.unwrap(this.get(`/api/workspaces/${workspaceSlug}/projects/${projectId}/teams/`));
  }

  /** Attaches the team and adds its members to the project; attaching again re-runs the sync. */
  async attach(workspaceSlug: string, projectId: string, teamId: string): Promise<TProjectTeamAttachResponse> {
    return this.unwrap(this.post(`/api/workspaces/${workspaceSlug}/projects/${projectId}/teams/`, { team_id: teamId }));
  }

  /** Sets the team's leader in this project, or clears it with `null`. */
  async updateLeader(
    workspaceSlug: string,
    projectId: string,
    teamId: string,
    leaderId: string | null
  ): Promise<TProjectTeam> {
    return this.unwrap(
      this.patch(`/api/workspaces/${workspaceSlug}/projects/${projectId}/teams/${teamId}/`, { leader_id: leaderId })
    );
  }

  /** Detaches the team; members it added leave the project unless they are admins or were added by hand. */
  async detach(workspaceSlug: string, projectId: string, teamId: string): Promise<TProjectTeamDetachResponse> {
    return this.unwrap(this.delete(`/api/workspaces/${workspaceSlug}/projects/${projectId}/teams/${teamId}/`));
  }
}
