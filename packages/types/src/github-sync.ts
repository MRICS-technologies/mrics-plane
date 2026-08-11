/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

export type TGithubInstallation = {
  id: string;
  installation_id: number;
  account_login: string;
  account_type: string;
  account_avatar_url: string;
  repository_selection: string;
  is_active: boolean;
  suspended_at: string | null;
  last_synced_at: string | null;
  created_at: string;
  updated_at: string;
};

export type TGithubEnabledRepository = {
  id: string;
  github_repository_id: number;
  full_name: string;
  is_enabled: boolean;
  private: boolean;
  default_branch: string;
  html_url: string;
  created_at: string;
  updated_at: string;
};

/** A repository visible to the installation on GitHub, merged with this
 * workspace's enabled-repository state. Returned by the live discovery
 * endpoint -- not persisted until enabled. */
export type TAvailableGithubRepository = {
  github_repository_id: number;
  full_name: string;
  private: boolean;
  default_branch: string;
  html_url: string;
  is_enabled: boolean;
};

export type TRepoProjectMappingRepositoryDetail = {
  id: string;
  github_repository_id: number;
  full_name: string;
  is_enabled: boolean;
  default_branch: string;
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
  /** Absent when the branch was already linked to the issue (idempotent replay). */
  sha?: string;
  /** True when an already-existing GitHub branch was linked instead of a new one being created. */
  linked_existing: boolean;
};

export type TWorkspaceGitHubInstallURLResponse = {
  install_url: string;
  expires_at: string;
};

export type TApiError = {
  status?: number;
  data?: Record<string, unknown>;
};
