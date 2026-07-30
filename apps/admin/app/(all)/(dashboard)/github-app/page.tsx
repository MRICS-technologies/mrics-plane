/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import useSWR from "swr";
// plane internal packages
import { InstanceService } from "@plane/services";
import { Button } from "@plane/propel/button";
import { Loader } from "@plane/ui";
// components
import { PageWrapper } from "@/components/common/page-wrapper";
// types
import type { Route } from "./+types/page";
// local
import { InstanceGitHubAppConfigForm } from "./form";

const instanceService = new InstanceService();

const InstanceGithubAppPage = (_props: Route.ComponentProps) => {
  const {
    data: config,
    error,
    mutate,
  } = useSWR("INSTANCE_GITHUB_APP_CONFIGURATION", () => instanceService.getGitHubAppConfiguration());

  return (
    <PageWrapper
      header={{
        title: "GitHub App",
        description: "Configure the GitHub App for this instance.",
      }}
    >
      {config ? (
        <InstanceGitHubAppConfigForm config={config} onChange={(updated) => mutate(updated, { revalidate: false })} />
      ) : error ? (
        <div className="flex flex-col items-center gap-3 py-12 text-center">
          <div className="text-14 text-tertiary">Failed to load the GitHub App configuration.</div>
          <Button variant="secondary" size="sm" onClick={() => mutate()}>
            Retry
          </Button>
        </div>
      ) : (
        <Loader className="space-y-8">
          <Loader.Item height="50px" width="25%" />
          <Loader.Item height="50px" />
          <Loader.Item height="50px" />
          <Loader.Item height="50px" />
          <Loader.Item height="50px" width="50%" />
        </Loader>
      )}
    </PageWrapper>
  );
};

export const meta: Route.MetaFunction = () => [{ title: "GitHub App Settings - God Mode" }];

export default InstanceGithubAppPage;
