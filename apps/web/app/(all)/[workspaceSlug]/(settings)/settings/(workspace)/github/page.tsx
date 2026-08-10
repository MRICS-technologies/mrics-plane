/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect } from "react";
import { observer } from "mobx-react";
import { useRouter, useSearchParams } from "next/navigation";
import useSWR from "swr";
// plane imports
import { EUserPermissions, EUserPermissionsLevel, GITHUB_INSTALLATION_KEY } from "@plane/constants";
import { useTranslation } from "@plane/i18n";
import { TOAST_TYPE, setToast } from "@plane/propel/toast";
// components
import { NotAuthorizedView } from "@/components/auth-screens/not-authorized-view";
import { PageHead } from "@/components/core/page-title";
import { InstallationPanel, RepositoriesPanel } from "@/components/github";
import { SettingsContentWrapper } from "@/components/settings/content-wrapper";
// hooks
import { useWorkspace } from "@/hooks/store/use-workspace";
import { useUserPermissions } from "@/hooks/store/user";
// services
import { GithubSyncService } from "@/services/github-sync.service";
// local imports
import type { Route } from "./+types/page";

const githubSyncService = new GithubSyncService();

function WorkspaceGithubSettingsPage({ params }: Route.ComponentProps) {
  // router
  const { workspaceSlug } = params;
  const searchParams = useSearchParams();
  const router = useRouter();
  const { t } = useTranslation();
  // store hooks
  const { workspaceUserInfo, allowPermissions } = useUserPermissions();
  const { currentWorkspace } = useWorkspace();
  // derived values
  const canPerformWorkspaceAdminActions = allowPermissions([EUserPermissions.ADMIN], EUserPermissionsLevel.WORKSPACE);
  const pageTitle = currentWorkspace?.name ? `${currentWorkspace.name} - GitHub` : undefined;

  const { data: installation, mutate: mutateInstallation } = useSWR(
    canPerformWorkspaceAdminActions ? GITHUB_INSTALLATION_KEY(workspaceSlug) : null,
    canPerformWorkspaceAdminActions ? () => githubSyncService.getInstallation(workspaceSlug) : null
  );

  // GitHub redirects back here after `/github/setup/` verifies the
  // installation (Phase 1 1.4 one-click install callback).
  useEffect(() => {
    const status = searchParams.get("github");
    if (!status) return;
    if (status === "connected") {
      setToast({
        type: TOAST_TYPE.SUCCESS,
        title: t("common.success"),
        message: t("workspace_settings.settings.github.installation.callback.connected"),
      });
      mutateInstallation();
    } else {
      setToast({
        type: TOAST_TYPE.ERROR,
        title: t("common.error"),
        message: t("workspace_settings.settings.github.installation.callback.failed"),
      });
    }
    router.replace(`/${workspaceSlug}/settings/github/`);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  if (workspaceUserInfo && !canPerformWorkspaceAdminActions) {
    return <NotAuthorizedView section="settings" className="h-auto" />;
  }

  return (
    <SettingsContentWrapper hugging>
      <PageHead title={pageTitle} />
      <div className="flex flex-col gap-10">
        <InstallationPanel workspaceSlug={workspaceSlug} />
        <RepositoriesPanel workspaceSlug={workspaceSlug} hasInstallation={Boolean(installation)} />
      </div>
    </SettingsContentWrapper>
  );
}

export default observer(WorkspaceGithubSettingsPage);
