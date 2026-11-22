/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useForm } from "react-hook-form";
// plane imports
import { Button } from "@makeplane/propel/components/button";
import {
  Dialog,
  DialogActions,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogHeading,
  DialogMain,
  DialogTitle,
} from "@makeplane/propel/components/dialog";
import { InputField } from "@makeplane/propel/components/input-field";
import { setToast } from "@plane/blocks/toast";
import { useTranslation } from "@plane/i18n";

type TFormValues = {
  installation_id: string;
  account_login: string;
  account_type: string;
};

const DEFAULT_VALUES: TFormValues = {
  installation_id: "",
  account_login: "",
  account_type: "",
};

type Props = {
  isOpen: boolean;
  onClose: () => void;
  onRegister: (data: { installation_id: number; account_login: string; account_type?: string }) => Promise<void>;
};

export function RegisterInstallationModal(props: Props) {
  const { isOpen, onClose, onRegister } = props;
  const { t } = useTranslation();
  const {
    register,
    handleSubmit,
    reset,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<TFormValues>({ defaultValues: DEFAULT_VALUES });

  const handleClose = () => {
    onClose();
    setTimeout(() => reset(DEFAULT_VALUES), 300);
  };

  const handleFormSubmit = async (data: TFormValues) => {
    const installationId = Number(data.installation_id);

    await onRegister({
      installation_id: installationId,
      account_login: data.account_login.trim(),
      account_type: data.account_type.trim() || undefined,
    })
      .then(() => handleClose())
      .catch((error: { status?: number; data?: Record<string, string | string[]> }) => {
        const fieldErrors = error?.data;
        if (error?.status === 400 && fieldErrors) {
          if (fieldErrors.installation_id) {
            setError("installation_id", {
              message: Array.isArray(fieldErrors.installation_id)
                ? fieldErrors.installation_id[0]
                : fieldErrors.installation_id,
            });
          }
          if (fieldErrors.account_login) {
            setError("account_login", {
              message: Array.isArray(fieldErrors.account_login)
                ? fieldErrors.account_login[0]
                : fieldErrors.account_login,
            });
          }
          return;
        }

        setToast({
          type: "error",
          title: t("common.error"),
          message:
            error?.status === 409
              ? t("workspace_settings.settings.github.installation.manual.modal.errors.conflict")
              : t("workspace_settings.settings.github.installation.manual.modal.errors.register_failed"),
        });
      });
  };

  return (
    <Dialog
      open={isOpen}
      onOpenChange={(open) => {
        if (!open) handleClose();
      }}
    >
      <DialogContent size="sm">
        <form onSubmit={handleSubmit(handleFormSubmit)} className="flex min-h-0 flex-1 flex-col">
          <DialogMain>
            <DialogHeader>
              <DialogHeading>
                <DialogTitle>{t("workspace_settings.settings.github.installation.manual.modal.title")}</DialogTitle>
                <DialogDescription>
                  {t("workspace_settings.settings.github.installation.manual.modal.description")}
                </DialogDescription>
              </DialogHeading>
            </DialogHeader>
            <DialogBody render={<div className="flex flex-col gap-4" />}>
              <InputField
                size="lg"
                orientation="vertical"
                id="installation_id"
                type="number"
                min={1}
                label={t("workspace_settings.settings.github.installation.manual.modal.installation_id_label")}
                placeholder={t(
                  "workspace_settings.settings.github.installation.manual.modal.installation_id_placeholder"
                )}
                error={errors.installation_id?.message}
                {...register("installation_id", {
                  required: t("workspace_settings.settings.github.installation.manual.modal.installation_id_required"),
                  validate: (value) =>
                    Number(value) > 0 ||
                    t("workspace_settings.settings.github.installation.manual.modal.installation_id_invalid"),
                })}
              />
              <InputField
                size="lg"
                orientation="vertical"
                id="account_login"
                type="text"
                label={t("workspace_settings.settings.github.installation.manual.modal.account_login_label")}
                placeholder={t(
                  "workspace_settings.settings.github.installation.manual.modal.account_login_placeholder"
                )}
                error={errors.account_login?.message}
                {...register("account_login", {
                  required: t("workspace_settings.settings.github.installation.manual.modal.account_login_required"),
                })}
              />
              <InputField
                size="lg"
                orientation="vertical"
                id="account_type"
                type="text"
                label={`${t("workspace_settings.settings.github.installation.manual.modal.account_type_label")} ${t(
                  "workspace_settings.settings.github.installation.manual.modal.account_type_optional"
                )}`}
                placeholder={t("workspace_settings.settings.github.installation.manual.modal.account_type_placeholder")}
                {...register("account_type")}
              />
            </DialogBody>
          </DialogMain>
          <DialogActions>
            <Button variant="secondary" size="md" stretch="auto" label={t("common.cancel")} onClick={handleClose} />
            <Button
              variant="primary"
              size="md"
              stretch="auto"
              type="submit"
              loading={isSubmitting}
              label={
                isSubmitting
                  ? t("workspace_settings.settings.github.installation.manual.modal.submitting")
                  : t("workspace_settings.settings.github.installation.manual.modal.submit")
              }
            />
          </DialogActions>
        </form>
      </DialogContent>
    </Dialog>
  );
}
