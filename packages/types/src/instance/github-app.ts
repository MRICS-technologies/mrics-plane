/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

export type TInstanceGitHubAppPublicConfigurationKeys =
  | "GITHUB_APP_ID"
  | "GITHUB_APP_SLUG"
  | "GITHUB_APP_CLIENT_ID"
  | "GITHUB_APP_GITHUB_BASE_URL"
  | "GITHUB_APP_HTML_BASE_URL"
  | "GITHUB_APP_ENABLED";

export type TInstanceGitHubAppSecretConfigurationKeys =
  | "GITHUB_APP_PRIVATE_KEY"
  | "GITHUB_APP_WEBHOOK_SECRET"
  | "GITHUB_APP_CLIENT_SECRET";

export type TInstanceGitHubAppConfigurationKeys =
  | TInstanceGitHubAppPublicConfigurationKeys
  | TInstanceGitHubAppSecretConfigurationKeys;

export type TInstanceGitHubAppSecretMeta = {
  configured: boolean;
  fingerprint: string | null;
  updated_at: string | null;
};

export type IInstanceGitHubAppConfiguration = {
  configured: boolean;
  enabled: boolean;
  app_id: string | null;
  app_slug: string | null;
  client_id: string | null;
  github_base_url: string | null;
  html_base_url: string | null;
  updated_at: string | null;
  private_key: TInstanceGitHubAppSecretMeta;
  webhook_secret: TInstanceGitHubAppSecretMeta;
  client_secret: TInstanceGitHubAppSecretMeta;
};

export type TInstanceGitHubAppTestResult = {
  valid: boolean;
  configuration: IInstanceGitHubAppConfiguration;
};

export type TInstanceGitHubAppPatchPayload = Partial<
  Record<Exclude<TInstanceGitHubAppConfigurationKeys, "GITHUB_APP_ENABLED">, string>
> & {
  GITHUB_APP_ENABLED?: boolean;
};
