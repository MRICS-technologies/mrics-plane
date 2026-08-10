/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { API_BASE_URL } from "@plane/constants";
import type {
  TApiError,
  TAvailableGithubRepository,
  TCreateBranchResponse,
  TCreateMappingPayload,
  TGithubEnabledRepository,
  TGithubInstallation,
  TIssueGitLink,
  TRepoProjectMapping,
  TWorkspaceGitHubInstallURLResponse,
} from "@plane/types";
import { APIService } from "@/services/api.service";

export type {
  TApiError,
  TAvailableGithubRepository,
  TCreateBranchResponse,
  TCreateMappingPayload,
  TGithubEnabledRepository,
  TGithubInstallation,
  TIssueGitLink,
  TRepoProjectMapping,
  TWorkspaceGitHubInstallURLResponse,
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

  /** Issues a one-time, workspace-bound state and the GitHub install URL that
   * carries it (Phase 1 1.4 one-click install). The caller should redirect
   * the browser to `install_url` -- nothing is persisted until GitHub
   * verifies the installation and calls back. */
  async getInstallURL(workspaceSlug: string, redirect?: string): Promise<TWorkspaceGitHubInstallURLResponse> {
    return this.post(`/api/workspaces/${workspaceSlug}/github/install-url/`, redirect ? { redirect } : {})
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

  /** Live view of every repository the installation can see on GitHub, merged
   * with this workspace's enabled-repository state (Phase 1 1.5 discovery). */
  async getAvailableRepositories(workspaceSlug: string): Promise<TAvailableGithubRepository[]> {
    return this.get(`/api/workspaces/${workspaceSlug}/github/available-repositories/`)
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

  /** Bulk enable/disable straight from the live discovery list. */
  async bulkUpdateRepositories(
    workspaceSlug: string,
    data: Array<{
      github_repository_id: number;
      full_name: string;
      is_enabled: boolean;
      private?: boolean;
      default_branch?: string;
      html_url?: string;
    }>
  ): Promise<TGithubEnabledRepository[]> {
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
