/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useForm } from "react-hook-form";
// plane imports
import { useTranslation } from "@plane/i18n";
import { Button } from "@plane/propel/button";
import { TOAST_TYPE, setToast } from "@plane/propel/toast";
import { EModalPosition, EModalWidth, Input, ModalCore } from "@plane/ui";

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
          type: TOAST_TYPE.ERROR,
          title: t("common.error"),
          message:
            error?.status === 409
              ? t("workspace_settings.settings.github.installation.manual.modal.errors.conflict")
              : t("workspace_settings.settings.github.installation.manual.modal.errors.register_failed"),
        });
      });
  };

  return (
    <ModalCore isOpen={isOpen} handleClose={handleClose} position={EModalPosition.TOP} width={EModalWidth.XL}>
      <form onSubmit={handleSubmit(handleFormSubmit)}>
        <div className="flex flex-col gap-4 p-5">
          <h3 className="text-lg font-medium">
            {t("workspace_settings.settings.github.installation.manual.modal.title")}
          </h3>
          <p className="text-13 text-tertiary">
            {t("workspace_settings.settings.github.installation.manual.modal.description")}
          </p>

          <div className="flex flex-col gap-1">
            <label htmlFor="installation_id" className="text-13 font-medium">
              {t("workspace_settings.settings.github.installation.manual.modal.installation_id_label")}
            </label>
            <Input
              id="installation_id"
              type="number"
              min={1}
              hasError={Boolean(errors.installation_id)}
              placeholder={t(
                "workspace_settings.settings.github.installation.manual.modal.installation_id_placeholder"
              )}
              {...register("installation_id", {
                required: t("workspace_settings.settings.github.installation.manual.modal.installation_id_required"),
                validate: (value) =>
                  Number(value) > 0 ||
                  t("workspace_settings.settings.github.installation.manual.modal.installation_id_invalid"),
              })}
            />
            {errors.installation_id && (
              <span className="text-11 text-danger-primary">{errors.installation_id.message}</span>
            )}
          </div>

          <div className="flex flex-col gap-1">
            <label htmlFor="account_login" className="text-13 font-medium">
              {t("workspace_settings.settings.github.installation.manual.modal.account_login_label")}
            </label>
            <Input
              id="account_login"
              type="text"
              hasError={Boolean(errors.account_login)}
              placeholder={t("workspace_settings.settings.github.installation.manual.modal.account_login_placeholder")}
              {...register("account_login", {
                required: t("workspace_settings.settings.github.installation.manual.modal.account_login_required"),
              })}
            />
            {errors.account_login && (
              <span className="text-11 text-danger-primary">{errors.account_login.message}</span>
            )}
          </div>

          <div className="flex flex-col gap-1">
            <label htmlFor="account_type" className="text-13 font-medium">
              {t("workspace_settings.settings.github.installation.manual.modal.account_type_label")}{" "}
              <span className="text-tertiary">
                {t("workspace_settings.settings.github.installation.manual.modal.account_type_optional")}
              </span>
            </label>
            <Input
              id="account_type"
              type="text"
              placeholder={t("workspace_settings.settings.github.installation.manual.modal.account_type_placeholder")}
              {...register("account_type")}
            />
          </div>
        </div>
        <div className="flex items-center justify-end gap-2 border-t border-subtle p-4">
          <Button variant="secondary" size="sm" onClick={handleClose} type="button">
            {t("common.cancel")}
          </Button>
          <Button variant="primary" size="sm" type="submit" loading={isSubmitting}>
            {isSubmitting
              ? t("workspace_settings.settings.github.installation.manual.modal.submitting")
              : t("workspace_settings.settings.github.installation.manual.modal.submit")}
          </Button>
        </div>
      </form>
    </ModalCore>
  );
}
