/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
import useSWR from "swr";
// plane imports
import { EUserPermissions, EUserPermissionsLevel } from "@plane/constants";
// components
import { NotAuthorizedView } from "@/components/auth-screens/not-authorized-view";
import { PageHead } from "@/components/core/page-title";
import { InstallationPanel, RepositoriesPanel } from "@/components/github";
import { GITHUB_INSTALLATION_KEY } from "@/components/github/swr-keys";
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
  // store hooks
  const { workspaceUserInfo, allowPermissions } = useUserPermissions();
  const { currentWorkspace } = useWorkspace();
  // derived values
  const canPerformWorkspaceAdminActions = allowPermissions([EUserPermissions.ADMIN], EUserPermissionsLevel.WORKSPACE);
  const pageTitle = currentWorkspace?.name ? `${currentWorkspace.name} - GitHub` : undefined;

  const { data: installation } = useSWR(
    canPerformWorkspaceAdminActions ? GITHUB_INSTALLATION_KEY(workspaceSlug) : null,
    canPerformWorkspaceAdminActions ? () => githubSyncService.getInstallation(workspaceSlug) : null
  );

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
