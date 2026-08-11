/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { TriangleAlert } from "lucide-react";
import useSWR, { mutate } from "swr";
// plane imports
import { GITHUB_INSTALLATION_KEY, GITHUB_REPOSITORIES_KEY, GITHUB_AVAILABLE_REPOSITORIES_KEY } from "@plane/constants";
import { useTranslation } from "@plane/i18n";
import { Button } from "@plane/propel/button";
import { EmptyStateCompact } from "@plane/propel/empty-state";
import { TOAST_TYPE, setToast } from "@plane/propel/toast";
import { Avatar, Loader } from "@plane/ui";
// components
import { SettingsHeading } from "@/components/settings/heading";
// services
import { GithubSyncService } from "@/services/github-sync.service";
// local imports
import { DisconnectInstallationModal } from "./disconnect-installation-modal";
import { RegisterInstallationModal } from "./register-installation-modal";

const githubSyncService = new GithubSyncService();

type Props = {
  workspaceSlug: string;
};

export function InstallationPanel(props: Props) {
  const { workspaceSlug } = props;
  const { t } = useTranslation();
  const [isRegisterModalOpen, setIsRegisterModalOpen] = useState(false);
  const [isDisconnectModalOpen, setIsDisconnectModalOpen] = useState(false);
  const [isRetrying, setIsRetrying] = useState(false);
  const [isConnecting, setIsConnecting] = useState(false);

  const {
    data: installation,
    error: installationError,
    isLoading,
    mutate: mutateInstallation,
  } = useSWR(GITHUB_INSTALLATION_KEY(workspaceSlug), () => githubSyncService.getInstallation(workspaceSlug));

  const handleRetry = async () => {
    setIsRetrying(true);
    await mutateInstallation();
    setIsRetrying(false);
  };

  const handleConnect = async () => {
    setIsConnecting(true);
    try {
      const { install_url } = await githubSyncService.getInstallURL(workspaceSlug);
      window.location.assign(install_url);
    } catch (error) {
      const typedError = error as { status?: number };
      setToast({
        type: TOAST_TYPE.ERROR,
        title: t("common.error"),
        message:
          typedError?.status === 422
            ? t("workspace_settings.settings.github.installation.errors.not_configured")
            : t("workspace_settings.settings.github.installation.errors.connect_failed"),
      });
      setIsConnecting(false);
    }
  };

  const handleRegister = async (data: { installation_id: number; account_login: string; account_type?: string }) => {
    const created = await githubSyncService.createInstallation(workspaceSlug, data);
    mutate(GITHUB_INSTALLATION_KEY(workspaceSlug), created, false);
    setToast({
      type: TOAST_TYPE.SUCCESS,
      title: t("common.success"),
      message: t("workspace_settings.settings.github.installation.manual.success"),
    });
  };

  const handleDisconnect = async (force?: boolean) => {
    await githubSyncService.deleteInstallation(workspaceSlug, force);
    mutate(GITHUB_INSTALLATION_KEY(workspaceSlug), null, false);
    mutate(GITHUB_REPOSITORIES_KEY(workspaceSlug), [], false);
    mutate(GITHUB_AVAILABLE_REPOSITORIES_KEY(workspaceSlug));
  };

  return (
    <div className="flex flex-col gap-4">
      <RegisterInstallationModal
        isOpen={isRegisterModalOpen}
        onClose={() => setIsRegisterModalOpen(false)}
        onRegister={handleRegister}
      />
      <DisconnectInstallationModal
        isOpen={isDisconnectModalOpen}
        onClose={() => setIsDisconnectModalOpen(false)}
        onDisconnect={handleDisconnect}
      />

      <SettingsHeading
        title={t("workspace_settings.settings.github.installation.title")}
        description={t("workspace_settings.settings.github.installation.description")}
      />

      {isLoading ? (
        <Loader>
          <Loader.Item height="72px" />
        </Loader>
      ) : installationError ? (
        <div className="flex flex-col items-center gap-3 rounded-md border border-subtle py-10 text-center">
          <span className="grid size-11 place-items-center text-tertiary">
            <TriangleAlert className="size-8" />
          </span>
          <div>
            <h6 className="text-14 font-medium">{t("common.something_went_wrong")}</h6>
            <p className="text-13 text-tertiary">
              {t("workspace_settings.settings.github.installation.errors.load_failed")}
            </p>
          </div>
          <Button variant="link" onClick={handleRetry} loading={isRetrying}>
            {t("workspace_settings.settings.github.retry")}
          </Button>
        </div>
      ) : installation ? (
        <div className="flex items-center justify-between rounded-md border border-subtle p-4">
          <div className="flex items-center gap-3">
            {installation.account_avatar_url && (
              <Avatar
                src={installation.account_avatar_url}
                name={installation.account_login}
                size="lg"
                shape="circle"
              />
            )}
            <div className="flex flex-col gap-1">
              <div className="flex items-center gap-2">
                <span className="text-14 font-medium">{installation.account_login}</span>
                {installation.account_type && (
                  <span className="rounded-xs bg-layer-1 px-2 py-0.5 text-11 text-tertiary">
                    {installation.account_type}
                  </span>
                )}
                <span
                  className={
                    installation.is_active
                      ? "rounded-xs bg-success-subtle px-2 py-0.5 text-11 font-medium text-success-primary"
                      : "rounded-xs bg-danger-subtle px-2 py-0.5 text-11 font-medium text-danger-primary"
                  }
                >
                  {installation.is_active
                    ? t("workspace_settings.settings.github.installation.status.active")
                    : installation.suspended_at
                      ? t("workspace_settings.settings.github.installation.status.suspended")
                      : t("workspace_settings.settings.github.installation.status.inactive")}
                </span>
              </div>
              <span className="text-12 text-tertiary">
                {t("workspace_settings.settings.github.installation.installation_id", {
                  id: installation.installation_id,
                })}
              </span>
            </div>
          </div>
          <Button variant="error-outline" size="sm" onClick={() => setIsDisconnectModalOpen(true)}>
            {t("workspace_settings.settings.github.installation.disconnect_button")}
          </Button>
        </div>
      ) : (
        <EmptyStateCompact
          assetKey="settings"
          title={t("workspace_settings.settings.github.installation.empty.title")}
          description={t("workspace_settings.settings.github.installation.empty.description")}
          actions={[
            {
              label: t("workspace_settings.settings.github.installation.connect_button"),
              onClick: handleConnect,
              disabled: isConnecting,
            },
            {
              label: t("workspace_settings.settings.github.installation.manual.trigger"),
              variant: "link",
              onClick: () => setIsRegisterModalOpen(true),
            },
          ]}
          align="start"
          rootClassName="py-10"
        />
      )}
    </div>
  );
}
