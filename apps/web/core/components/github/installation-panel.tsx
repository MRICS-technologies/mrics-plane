/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { TriangleAlert } from "lucide-react";
import useSWR, { mutate } from "swr";
// plane imports
import { Button } from "@plane/propel/button";
import { EmptyStateCompact } from "@plane/propel/empty-state";
import { TOAST_TYPE, setToast } from "@plane/propel/toast";
import { Loader } from "@plane/ui";
// components
import { SettingsHeading } from "@/components/settings/heading";
// services
import { GithubSyncService } from "@/services/github-sync.service";
// local imports
import { DisconnectInstallationModal } from "./disconnect-installation-modal";
import { RegisterInstallationModal } from "./register-installation-modal";
import { GITHUB_INSTALLATION_KEY, GITHUB_REPOSITORIES_KEY } from "./swr-keys";

const githubSyncService = new GithubSyncService();

type Props = {
  workspaceSlug: string;
};

export function InstallationPanel(props: Props) {
  const { workspaceSlug } = props;
  const [isRegisterModalOpen, setIsRegisterModalOpen] = useState(false);
  const [isDisconnectModalOpen, setIsDisconnectModalOpen] = useState(false);
  const [isRetrying, setIsRetrying] = useState(false);

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

  const handleRegister = async (data: { installation_id: number; account_login: string; account_type?: string }) => {
    const created = await githubSyncService.createInstallation(workspaceSlug, data);
    mutate(GITHUB_INSTALLATION_KEY(workspaceSlug), created, false);
    setToast({ type: TOAST_TYPE.SUCCESS, title: "Success!", message: "GitHub installation registered." });
  };

  const handleDisconnect = async () => {
    await githubSyncService.deleteInstallation(workspaceSlug);
    mutate(GITHUB_INSTALLATION_KEY(workspaceSlug), null, false);
    mutate(GITHUB_REPOSITORIES_KEY(workspaceSlug), [], false);
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

      <SettingsHeading title="Installation" description="The GitHub App installation registered for this workspace." />

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
            <h6 className="text-14 font-medium">Something went wrong!</h6>
            <p className="text-13 text-tertiary">The installation could not be loaded, please try again.</p>
          </div>
          <Button variant="link" onClick={handleRetry} loading={isRetrying}>
            Try again
          </Button>
        </div>
      ) : installation ? (
        <div className="flex items-center justify-between rounded-md border border-subtle p-4">
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
                    : "rounded-xs bg-layer-1 px-2 py-0.5 text-11 font-medium text-tertiary"
                }
              >
                {installation.is_active ? "Active" : "Inactive"}
              </span>
            </div>
            <span className="text-12 text-tertiary">Installation ID: {installation.installation_id}</span>
          </div>
          <Button variant="error-outline" size="sm" onClick={() => setIsDisconnectModalOpen(true)}>
            Disconnect
          </Button>
        </div>
      ) : (
        <EmptyStateCompact
          assetKey="settings"
          title="No GitHub installation"
          description="Register a GitHub App installation ID to enable repositories for this workspace."
          actions={[{ label: "Register installation", onClick: () => setIsRegisterModalOpen(true) }]}
          align="start"
          rootClassName="py-10"
        />
      )}
    </div>
  );
}
