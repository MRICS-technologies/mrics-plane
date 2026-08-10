/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
// plane internal packages
import { InstanceService } from "@plane/services";
import { Button } from "@plane/propel/button";
import { TOAST_TYPE, setToast } from "@plane/propel/toast";
import type { IInstanceGitHubAppConfiguration } from "@plane/types";
import { Input } from "@plane/ui";

type Props = {
  config: IInstanceGitHubAppConfiguration;
};

const instanceService = new InstanceService();

/** Submits GitHub's App Manifest flow via a hidden, auto-submitting form --
 * the browser POSTs straight to GitHub, so no manifest data ever touches our
 * own network layer beyond the initial `/manifest/` call that builds it. */
function submitManifest(postUrl: string, manifest: unknown, state: string) {
  const form = document.createElement("form");
  form.method = "POST";
  form.action = postUrl;
  form.style.display = "none";

  const manifestInput = document.createElement("input");
  manifestInput.type = "hidden";
  manifestInput.name = "manifest";
  manifestInput.value = JSON.stringify(manifest);
  form.appendChild(manifestInput);

  const stateInput = document.createElement("input");
  stateInput.type = "hidden";
  stateInput.name = "state";
  stateInput.value = state;
  form.appendChild(stateInput);

  document.body.appendChild(form);
  form.submit();
}

export function GitHubAppManifestSetupCard(props: Props) {
  const { config } = props;
  const [isCreating, setIsCreating] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [organization, setOrganization] = useState("");
  const [publicBaseUrl, setPublicBaseUrl] = useState("");

  const handleAutomatedSetup = async () => {
    setIsCreating(true);
    try {
      const { manifest, post_url, state } = await instanceService.createGitHubAppManifest({
        organization: organization.trim() || undefined,
        public_base_url: publicBaseUrl.trim() || undefined,
      });
      submitManifest(post_url, manifest, state);
    } catch (error) {
      const typedError = error as { status?: number; data?: { error?: string } };
      setToast({
        type: TOAST_TYPE.ERROR,
        title: "Error",
        message:
          typedError?.data?.error === "already_configured"
            ? "A GitHub App is already configured on this instance. Remove the existing configuration before creating a new one."
            : "Failed to start the automated GitHub App setup. Please try again.",
      });
      setIsCreating(false);
    }
  };

  return (
    <div className="flex flex-col gap-4 rounded-lg border border-subtle p-6">
      <div className="flex flex-col gap-1">
        <div className="text-16 font-medium text-primary">Automated setup (recommended)</div>
        <div className="text-13 text-tertiary">
          Creates a GitHub App for this instance automatically -- GitHub prefills the name, webhook, and permissions,
          you just confirm and install it.
        </div>
      </div>

      {config.configured ? (
        <p className="text-13 text-tertiary">
          A GitHub App is already configured on this instance. Remove the existing configuration below before running
          automated setup again.
        </p>
      ) : (
        <>
          <Button variant="primary" size="lg" onClick={handleAutomatedSetup} loading={isCreating} className="w-fit">
            {isCreating ? "Redirecting to GitHub..." : "Create GitHub App"}
          </Button>

          <button
            type="button"
            onClick={() => setShowAdvanced((prev) => !prev)}
            className="w-fit text-12 text-tertiary underline"
          >
            {showAdvanced
              ? "Hide advanced options"
              : "Advanced options (GitHub Enterprise, tunnel/reverse-proxy hosts)"}
          </button>

          {showAdvanced && (
            <div className="flex flex-col gap-3">
              <div className="flex flex-col gap-1">
                <label htmlFor="manifest_organization" className="text-13 font-medium">
                  Organization <span className="text-tertiary">(optional)</span>
                </label>
                <Input
                  id="manifest_organization"
                  type="text"
                  value={organization}
                  onChange={(e) => setOrganization(e.target.value)}
                  placeholder="Create the app under this GitHub organization instead of your personal account"
                />
              </div>
              <div className="flex flex-col gap-1">
                <label htmlFor="manifest_public_base_url" className="text-13 font-medium">
                  Public base URL <span className="text-tertiary">(optional)</span>
                </label>
                <Input
                  id="manifest_public_base_url"
                  type="text"
                  value={publicBaseUrl}
                  onChange={(e) => setPublicBaseUrl(e.target.value)}
                  placeholder="https://plane.example.com"
                />
                <span className="text-11 text-tertiary">
                  Override the URL GitHub uses for webhooks and callbacks -- needed when this instance is behind a
                  tunnel or reverse proxy.
                </span>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
