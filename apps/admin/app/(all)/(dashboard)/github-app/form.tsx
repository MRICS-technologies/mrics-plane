/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { useForm } from "react-hook-form";
// plane internal packages
import { InstanceService } from "@plane/services";
import { TOAST_TYPE, setToast } from "@plane/propel/toast";
import { Button } from "@plane/propel/button";
import type {
  IInstanceGitHubAppConfiguration,
  TInstanceGitHubAppConfigurationKeys,
  TInstanceGitHubAppSecretMeta,
} from "@plane/types";
import { AlertModalCore, ToggleSwitch } from "@plane/ui";
// components
import type { TControllerInputFormField } from "@/components/common/controller-input";
import { ControllerInput } from "@/components/common/controller-input";
// local imports
import { GitHubAppManifestSetupCard } from "./manifest-setup-card";

type Props = {
  config: IInstanceGitHubAppConfiguration;
  onChange: (config: IInstanceGitHubAppConfiguration) => void;
};

type TFormValues = Record<Exclude<TInstanceGitHubAppConfigurationKeys, "GITHUB_APP_ENABLED">, string>;

const instanceService = new InstanceService();

const secretMeta = (meta: IInstanceGitHubAppConfiguration["private_key"]) => {
  if (!meta.configured) return "Not configured.";
  return `Configured • fingerprint ${meta.fingerprint} • updated ${meta.updated_at ? new Date(meta.updated_at).toLocaleString() : "-"}`;
};

const isSecretMeta = (value: unknown): value is TInstanceGitHubAppSecretMeta =>
  typeof value === "object" &&
  value !== null &&
  typeof (value as TInstanceGitHubAppSecretMeta).configured === "boolean" &&
  (typeof (value as TInstanceGitHubAppSecretMeta).fingerprint === "string" ||
    (value as TInstanceGitHubAppSecretMeta).fingerprint === null) &&
  (typeof (value as TInstanceGitHubAppSecretMeta).updated_at === "string" ||
    (value as TInstanceGitHubAppSecretMeta).updated_at === null);

const isValidConfiguration = (value: unknown): value is IInstanceGitHubAppConfiguration =>
  typeof value === "object" &&
  value !== null &&
  typeof (value as IInstanceGitHubAppConfiguration).configured === "boolean" &&
  typeof (value as IInstanceGitHubAppConfiguration).enabled === "boolean" &&
  isSecretMeta((value as IInstanceGitHubAppConfiguration).private_key) &&
  isSecretMeta((value as IInstanceGitHubAppConfiguration).webhook_secret) &&
  isSecretMeta((value as IInstanceGitHubAppConfiguration).client_secret);

const hasAnyConfiguration = (config: IInstanceGitHubAppConfiguration) =>
  Boolean(
    config.app_id ||
    config.app_slug ||
    config.client_id ||
    config.github_base_url ||
    config.html_base_url ||
    config.private_key.configured ||
    config.webhook_secret.configured ||
    config.client_secret.configured
  );

export function InstanceGitHubAppConfigForm(props: Props) {
  const { config, onChange } = props;
  // states
  const [isEnabling, setIsEnabling] = useState(false);
  const [isTesting, setIsTesting] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
  const [showManualForm, setShowManualForm] = useState(config.configured);

  const {
    handleSubmit,
    control,
    reset,
    formState: { errors, isDirty, isSubmitting, dirtyFields },
  } = useForm<TFormValues>({
    defaultValues: {
      GITHUB_APP_ID: config.app_id ?? "",
      GITHUB_APP_SLUG: config.app_slug ?? "",
      GITHUB_APP_CLIENT_ID: config.client_id ?? "",
      GITHUB_APP_GITHUB_BASE_URL: config.github_base_url ?? "",
      GITHUB_APP_HTML_BASE_URL: config.html_base_url ?? "",
      GITHUB_APP_PRIVATE_KEY: "",
      GITHUB_APP_WEBHOOK_SECRET: "",
      GITHUB_APP_CLIENT_SECRET: "",
    },
  });

  const FORM_FIELDS: TControllerInputFormField[] = [
    {
      key: "GITHUB_APP_ID",
      type: "text",
      label: "App ID",
      placeholder: "123456",
      error: Boolean(errors.GITHUB_APP_ID),
      required: false,
    },
    {
      key: "GITHUB_APP_SLUG",
      type: "text",
      label: "App slug",
      placeholder: "my-plane-app",
      error: Boolean(errors.GITHUB_APP_SLUG),
      required: false,
    },
    {
      key: "GITHUB_APP_CLIENT_ID",
      type: "text",
      label: "Client ID",
      placeholder: "Iv1.abcdef1234567890",
      error: Boolean(errors.GITHUB_APP_CLIENT_ID),
      required: false,
    },
    {
      key: "GITHUB_APP_GITHUB_BASE_URL",
      type: "text",
      label: "GitHub API base URL",
      placeholder: "https://api.github.com",
      error: Boolean(errors.GITHUB_APP_GITHUB_BASE_URL),
      required: false,
    },
    {
      key: "GITHUB_APP_HTML_BASE_URL",
      type: "text",
      label: "GitHub base URL",
      placeholder: "https://github.com",
      error: Boolean(errors.GITHUB_APP_HTML_BASE_URL),
      required: false,
    },
  ];

  const SECRET_FIELDS: { field: TControllerInputFormField; meta: IInstanceGitHubAppConfiguration["private_key"] }[] = [
    {
      field: {
        key: "GITHUB_APP_PRIVATE_KEY",
        type: "password",
        label: "Private key",
        placeholder: "Leave blank to keep the current value",
        error: Boolean(errors.GITHUB_APP_PRIVATE_KEY),
        required: false,
      },
      meta: config.private_key,
    },
    {
      field: {
        key: "GITHUB_APP_WEBHOOK_SECRET",
        type: "password",
        label: "Webhook secret",
        placeholder: "Leave blank to keep the current value",
        error: Boolean(errors.GITHUB_APP_WEBHOOK_SECRET),
        required: false,
      },
      meta: config.webhook_secret,
    },
    {
      field: {
        key: "GITHUB_APP_CLIENT_SECRET",
        type: "password",
        label: "Client secret",
        placeholder: "Leave blank to keep the current value",
        error: Boolean(errors.GITHUB_APP_CLIENT_SECRET),
        required: false,
      },
      meta: config.client_secret,
    },
  ];

  const handleToggleEnabled = async () => {
    setIsEnabling(true);
    try {
      const updated = await instanceService.updateGitHubAppConfiguration({
        GITHUB_APP_ENABLED: !config.enabled,
      });
      onChange(updated);
      setToast({
        type: TOAST_TYPE.SUCCESS,
        title: "Configuration saved",
        message: `GitHub App is now ${updated.enabled ? "enabled" : "disabled"}.`,
      });
    } catch {
      setToast({
        type: TOAST_TYPE.ERROR,
        title: "Error",
        message: "Failed to update the GitHub App configuration. Please try again.",
      });
    } finally {
      setIsEnabling(false);
    }
  };

  const onSubmit = async (formData: TFormValues) => {
    const payload: Partial<Record<Exclude<TInstanceGitHubAppConfigurationKeys, "GITHUB_APP_ENABLED">, string>> = {};
    (Object.keys(dirtyFields) as (keyof TFormValues)[]).forEach((key) => {
      const value = formData[key];
      if (value.trim() !== "") payload[key] = value;
    });

    if (Object.keys(payload).length === 0) return;

    try {
      const updated = await instanceService.updateGitHubAppConfiguration(payload);
      onChange(updated);
      if (updated.reset_count) {
        setToast({
          type: TOAST_TYPE.SUCCESS,
          title: "GitHub App configuration saved",
          message: `App ID changed — ${updated.reset_count} workspace GitHub connection${updated.reset_count === 1 ? "" : "s"} were reset. Each workspace must reconnect.`,
        });
      } else {
        setToast({
          type: TOAST_TYPE.SUCCESS,
          title: "Done!",
          message: "GitHub App configuration saved. You should test it now.",
        });
      }
      reset({
        GITHUB_APP_ID: updated.app_id ?? "",
        GITHUB_APP_SLUG: updated.app_slug ?? "",
        GITHUB_APP_CLIENT_ID: updated.client_id ?? "",
        GITHUB_APP_GITHUB_BASE_URL: updated.github_base_url ?? "",
        GITHUB_APP_HTML_BASE_URL: updated.html_base_url ?? "",
        GITHUB_APP_PRIVATE_KEY: "",
        GITHUB_APP_WEBHOOK_SECRET: "",
        GITHUB_APP_CLIENT_SECRET: "",
      });
    } catch {
      setToast({
        type: TOAST_TYPE.ERROR,
        title: "Error",
        message: "Failed to save the GitHub App configuration. Please check your input and try again.",
      });
    }
  };

  const handleTestConnection = async () => {
    setIsTesting(true);
    try {
      const result = await instanceService.testGitHubAppConfiguration();
      if (result?.valid && isValidConfiguration(result.configuration)) {
        onChange(result.configuration);
        setToast({
          type: TOAST_TYPE.SUCCESS,
          title: "Connection valid",
          message: "The stored GitHub App credentials can sign requests locally.",
        });
      } else {
        setToast({
          type: TOAST_TYPE.ERROR,
          title: "Connection failed",
          message: "Failed to validate the GitHub App configuration.",
        });
      }
    } catch {
      setToast({
        type: TOAST_TYPE.ERROR,
        title: "Connection failed",
        message: "Failed to validate the GitHub App configuration.",
      });
    } finally {
      setIsTesting(false);
    }
  };

  const handleDelete = async () => {
    setIsDeleting(true);
    try {
      const updated = await instanceService.deleteGitHubAppConfiguration();
      onChange(updated);
      setToast({
        type: TOAST_TYPE.SUCCESS,
        title: "Configuration removed",
        message: "The GitHub App configuration has been removed from this instance.",
      });
      reset({
        GITHUB_APP_ID: "",
        GITHUB_APP_SLUG: "",
        GITHUB_APP_CLIENT_ID: "",
        GITHUB_APP_GITHUB_BASE_URL: "",
        GITHUB_APP_HTML_BASE_URL: "",
        GITHUB_APP_PRIVATE_KEY: "",
        GITHUB_APP_WEBHOOK_SECRET: "",
        GITHUB_APP_CLIENT_SECRET: "",
      });
      setIsDeleteModalOpen(false);
    } catch {
      setToast({
        type: TOAST_TYPE.ERROR,
        title: "Error",
        message: "Failed to remove the GitHub App configuration. Please try again.",
      });
    } finally {
      setIsDeleting(false);
    }
  };

  return (
    <div className="flex flex-col gap-8">
      <AlertModalCore
        variant="danger"
        isOpen={isDeleteModalOpen}
        handleClose={() => setIsDeleteModalOpen(false)}
        handleSubmit={handleDelete}
        isSubmitting={isDeleting}
        title="Remove GitHub App configuration"
        content="This will permanently remove the GitHub App credentials stored on this instance. You can reconfigure it again at any time."
        primaryButtonText={{ loading: "Removing", default: "Remove" }}
      />

      <GitHubAppManifestSetupCard config={config} />

      <div className="flex items-center justify-between gap-4 rounded-lg bg-layer-1 px-6 py-4">
        <div className="flex flex-col gap-1">
          <div className="text-14 font-medium text-primary">Enable GitHub App</div>
          <div className="text-13 text-tertiary">
            {config.configured
              ? "Turn the configured GitHub App on or off for this instance."
              : "Configure the App ID and private key below before enabling."}
          </div>
        </div>
        <ToggleSwitch value={config.enabled} onChange={handleToggleEnabled} size="sm" disabled={isEnabling} />
      </div>

      <button
        type="button"
        onClick={() => setShowManualForm((prev) => !prev)}
        className="w-fit text-14 font-medium text-primary underline"
      >
        {showManualForm ? "Hide manual configuration" : "Advanced / GitHub Enterprise: configure manually"}
      </button>

      {showManualForm && (
        <>
          <div className="flex flex-col gap-y-4">
            <div className="text-18 font-medium">App details</div>
            {FORM_FIELDS.map((field) => (
              <ControllerInput
                key={field.key}
                control={control}
                type={field.type}
                name={field.key}
                label={field.label}
                placeholder={field.placeholder}
                error={field.error}
                required={field.required}
              />
            ))}
          </div>

          <div className="flex flex-col gap-y-4">
            <div className="text-18 font-medium">Secrets</div>
            {SECRET_FIELDS.map(({ field, meta }) => (
              <div key={field.key} className="flex flex-col gap-1">
                <ControllerInput
                  control={control}
                  type={field.type}
                  name={field.key}
                  label={field.label}
                  placeholder={field.placeholder}
                  error={field.error}
                  required={field.required}
                />
                <p className="text-11 text-tertiary">{secretMeta(meta)}</p>
              </div>
            ))}
          </div>

          <div className="flex items-center gap-4">
            <Button
              variant="primary"
              size="lg"
              onClick={(e) => void handleSubmit(onSubmit)(e)}
              loading={isSubmitting}
              disabled={!isDirty}
            >
              {isSubmitting ? "Saving" : "Save changes"}
            </Button>
            <Button
              variant="secondary"
              size="lg"
              onClick={handleTestConnection}
              loading={isTesting}
              disabled={!config.configured || isTesting}
            >
              {isTesting ? "Testing" : "Test connection"}
            </Button>
            <Button
              variant="error-fill"
              size="lg"
              onClick={() => setIsDeleteModalOpen(true)}
              disabled={!hasAnyConfiguration(config)}
            >
              Remove configuration
            </Button>
          </div>
        </>
      )}
    </div>
  );
}
