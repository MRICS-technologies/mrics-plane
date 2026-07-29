/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { API_BASE_URL } from "@plane/constants";
import { APIService } from "@/services/api.service";

export type TRepoProjectMapping = {
  id: string;
  github_repo: string;
  base_branch: string;
  is_default: boolean;
  repo_label: string;
};

export type TIssueGitLink = {
  id: string;
  kind: "branch" | "pr";
  ref: string;
  url: string;
  state: "open" | "merged" | "closed" | "unknown";
  detected_via: string;
  github_repo: string;
};

export type TCreateBranchResponse = {
  branch_name: string;
  url: string;
  sha: string;
};

export class GithubSyncService extends APIService {
  constructor() {
    super(API_BASE_URL);
  }

  async getMappings(workspaceSlug: string, projectId: string): Promise<TRepoProjectMapping[]> {
    return this.get(`/api/workspaces/${workspaceSlug}/projects/${projectId}/github/mappings/`)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response;
      });
  }

  async createMapping(
    workspaceSlug: string,
    projectId: string,
    data: Partial<TRepoProjectMapping>
  ): Promise<TRepoProjectMapping> {
    return this.post(`/api/workspaces/${workspaceSlug}/projects/${projectId}/github/mappings/`, data)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response;
      });
  }

  async deleteMapping(workspaceSlug: string, projectId: string, mappingId: string): Promise<void> {
    return this.delete(`/api/workspaces/${workspaceSlug}/projects/${projectId}/github/mappings/${mappingId}/`)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response;
      });
  }

  async getGitLinks(workspaceSlug: string, projectId: string, issueId: string): Promise<TIssueGitLink[]> {
    return this.get(`/api/workspaces/${workspaceSlug}/projects/${projectId}/issues/${issueId}/git-links/`)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response;
      });
  }

  async createBranch(
    workspaceSlug: string,
    projectId: string,
    issueId: string,
    data: { branch_name: string; repo?: string }
  ): Promise<TCreateBranchResponse> {
    return this.post(
      `/api/workspaces/${workspaceSlug}/projects/${projectId}/issues/${issueId}/github/create-branch/`,
      data
    )
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response;
      });
  }
}
