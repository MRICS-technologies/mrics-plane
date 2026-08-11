/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import useSWR from "swr";
// plane internal packages
import { InstanceService } from "@plane/services";
import { Button } from "@plane/propel/button";
import { TOAST_TYPE, setToast } from "@plane/propel/toast";
import { Loader } from "@plane/ui";
// components
import { PageWrapper } from "@/components/common/page-wrapper";
// types
import type { Route } from "./+types/page";
// local
import { InstanceGitHubAppConfigForm } from "./form";

const instanceService = new InstanceService();

const MANIFEST_CALLBACK_MESSAGES: Record<string, string> = {
  conversion_failed: "GitHub could not finish creating the App. Please try automated setup again.",
  already_configured: "A GitHub App is already configured on this instance.",
  invalid_state: "This setup link expired or was already used. Please start automated setup again.",
  missing_code: "GitHub did not return a setup code. Please try automated setup again.",
};

const InstanceGithubAppPage = (_props: Route.ComponentProps) => {
  const searchParams = useSearchParams();
  const router = useRouter();
  const {
    data: config,
    error,
    mutate,
  } = useSWR("INSTANCE_GITHUB_APP_CONFIGURATION", () => instanceService.getGitHubAppConfiguration());

  // GitHub redirects the admin's browser back here after
  // `/api/instances/github-app/manifest/callback/` converts the manifest.
  useEffect(() => {
    const status = searchParams.get("github_app");
    if (!status) return;
    if (status === "connected") {
      setToast({ type: TOAST_TYPE.SUCCESS, title: "GitHub App connected", message: "The GitHub App is ready to use." });
      mutate();
    } else {
      setToast({
        type: TOAST_TYPE.ERROR,
        title: "Automated setup failed",
        message: MANIFEST_CALLBACK_MESSAGES[status] ?? "The automated GitHub App setup could not be completed.",
      });
    }
    router.replace("/github-app/");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

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
