/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { API_BASE_URL } from "@plane/constants";
import { APIService } from "@/services/api.service";

export type TRepoProjectMappingRepositoryDetail = {
  id: string;
  github_repository_id: number;
  full_name: string;
  is_enabled: boolean;
};

export type TRepoProjectMapping = {
  id: string;
  github_repo: string;
  base_branch: string | null;
  is_default: boolean;
  repo_label: string | null;
  repository_detail: TRepoProjectMappingRepositoryDetail | null;
  created_at: string;
  updated_at: string;
};

export type TCreateMappingPayload = {
  repository_id: string;
  base_branch?: string;
  repo_label?: string;
};

export type TApiError = {
  status?: number;
  data?: Record<string, unknown>;
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

export type TGithubInstallation = {
  id: string;
  installation_id: number;
  account_login: string;
  account_type: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

export type TGithubEnabledRepository = {
  id: string;
  github_repository_id: number;
  full_name: string;
  is_enabled: boolean;
  created_at: string;
  updated_at: string;
};

export class GithubSyncService extends APIService {
  constructor() {
    super(API_BASE_URL);
  }

  async getInstallation(workspaceSlug: string): Promise<TGithubInstallation | null> {
    return this.get(`/api/workspaces/${workspaceSlug}/github/installation/`)
      .then((response) => response?.data)
      .catch((error) => {
        throw { status: error?.response?.status, data: error?.response?.data } as TApiError;
      });
  }

  async createInstallation(
    workspaceSlug: string,
    data: { installation_id: number; account_login: string; account_type?: string }
  ): Promise<TGithubInstallation> {
    return this.post(`/api/workspaces/${workspaceSlug}/github/installation/`, data)
      .then((response) => response?.data)
      .catch((error) => {
        throw { status: error?.response?.status, data: error?.response?.data } as TApiError;
      });
  }

  async deleteInstallation(workspaceSlug: string): Promise<void> {
    return this.delete(`/api/workspaces/${workspaceSlug}/github/installation/`)
      .then((response) => response?.data)
      .catch((error) => {
        throw { status: error?.response?.status, data: error?.response?.data } as TApiError;
      });
  }

  async getRepositories(workspaceSlug: string): Promise<TGithubEnabledRepository[]> {
    return this.get(`/api/workspaces/${workspaceSlug}/github/repositories/`)
      .then((response) => response?.data)
      .catch((error) => {
        throw { status: error?.response?.status, data: error?.response?.data } as TApiError;
      });
  }

  async createRepository(
    workspaceSlug: string,
    data: { github_repository_id: number; full_name: string }
  ): Promise<TGithubEnabledRepository> {
    return this.post(`/api/workspaces/${workspaceSlug}/github/repositories/`, data)
      .then((response) => response?.data)
      .catch((error) => {
        throw { status: error?.response?.status, data: error?.response?.data } as TApiError;
      });
  }

  async updateRepository(
    workspaceSlug: string,
    repoId: string,
    data: Partial<Pick<TGithubEnabledRepository, "is_enabled" | "full_name">>
  ): Promise<TGithubEnabledRepository> {
    return this.patch(`/api/workspaces/${workspaceSlug}/github/repositories/${repoId}/`, data)
      .then((response) => response?.data)
      .catch((error) => {
        throw { status: error?.response?.status, data: error?.response?.data } as TApiError;
      });
  }

  async deleteRepository(workspaceSlug: string, repoId: string): Promise<void> {
    return this.delete(`/api/workspaces/${workspaceSlug}/github/repositories/${repoId}/`)
      .then((response) => response?.data)
      .catch((error) => {
        throw { status: error?.response?.status, data: error?.response?.data } as TApiError;
      });
  }

  async getMappings(workspaceSlug: string, projectId: string): Promise<TRepoProjectMapping[]> {
    return this.get(`/api/workspaces/${workspaceSlug}/projects/${projectId}/github/mappings/`)
      .then((response) => response?.data)
      .catch((error) => {
        throw { status: error?.response?.status, data: error?.response?.data } as TApiError;
      });
  }

  async createMapping(
    workspaceSlug: string,
    projectId: string,
    data: TCreateMappingPayload
  ): Promise<TRepoProjectMapping> {
    return this.post(`/api/workspaces/${workspaceSlug}/projects/${projectId}/github/mappings/`, data)
      .then((response) => response?.data)
      .catch((error) => {
        throw { status: error?.response?.status, data: error?.response?.data } as TApiError;
      });
  }

  async deleteMapping(workspaceSlug: string, projectId: string, mappingId: string): Promise<void> {
    return this.delete(`/api/workspaces/${workspaceSlug}/projects/${projectId}/github/mappings/${mappingId}/`)
      .then((response) => response?.data)
      .catch((error) => {
        throw { status: error?.response?.status, data: error?.response?.data } as TApiError;
      });
  }

  async getGitLinks(workspaceSlug: string, projectId: string, issueId: string): Promise<TIssueGitLink[]> {
    return this.get(`/api/workspaces/${workspaceSlug}/projects/${projectId}/issues/${issueId}/git-links/`)
      .then((response) => response?.data)
      .catch((error) => {
        throw { status: error?.response?.status, data: error?.response?.data } as TApiError;
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
        throw { status: error?.response?.status, data: error?.response?.data } as TApiError;
      });
  }
}
