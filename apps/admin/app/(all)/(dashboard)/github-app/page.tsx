/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// components
import { PageWrapper } from "@/components/common/page-wrapper";
// types
import type { Route } from "./+types/page";

const InstanceGithubAppPage = (_props: Route.ComponentProps) => (
  <PageWrapper
    header={{
      title: "GitHub App",
      description: "Configure the GitHub App for this instance.",
    }}
  >
    <div />
  </PageWrapper>
);

export const meta: Route.MetaFunction = () => [{ title: "GitHub App Settings - God Mode" }];

export default InstanceGithubAppPage;
