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

const FULL_NAME_PATTERN = /^[^\s/]+\/[^\s/]+$/;

type TFormValues = {
  github_repository_id: string;
  full_name: string;
};

const DEFAULT_VALUES: TFormValues = {
  github_repository_id: "",
  full_name: "",
};

type Props = {
  isOpen: boolean;
  onClose: () => void;
  onRegister: (data: { github_repository_id: number; full_name: string }) => Promise<void>;
};

export function RegisterRepositoryModal(props: Props) {
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
    await onRegister({
      github_repository_id: Number(data.github_repository_id),
      full_name: data.full_name,
    })
      .then(() => handleClose())
      .catch((error: { status?: number; data?: Record<string, string | string[]> }) => {
        const fieldErrors = error?.data;
        if (error?.status === 400 && fieldErrors) {
          if (fieldErrors.github_repository_id) {
            setError("github_repository_id", {
              message: Array.isArray(fieldErrors.github_repository_id)
                ? fieldErrors.github_repository_id[0]
                : fieldErrors.github_repository_id,
            });
          }
          if (fieldErrors.full_name) {
            setError("full_name", {
              message: Array.isArray(fieldErrors.full_name) ? fieldErrors.full_name[0] : fieldErrors.full_name,
            });
          }
          return;
        }

        let message = t("workspace_settings.settings.github.repositories.manual.modal.errors.register_failed");
        if (error?.status === 409)
          message = t("workspace_settings.settings.github.repositories.manual.modal.errors.conflict");
        if (error?.status === 422)
          message = t("workspace_settings.settings.github.repositories.manual.modal.errors.not_configured");
        setToast({ type: TOAST_TYPE.ERROR, title: t("common.error"), message });
      });
  };

  return (
    <ModalCore isOpen={isOpen} handleClose={handleClose} position={EModalPosition.TOP} width={EModalWidth.XL}>
      <form onSubmit={handleSubmit(handleFormSubmit)}>
        <div className="flex flex-col gap-4 p-5">
          <h3 className="text-lg font-medium">
            {t("workspace_settings.settings.github.repositories.manual.modal.title")}
          </h3>
          <p className="text-13 text-tertiary">
            {t("workspace_settings.settings.github.repositories.manual.modal.description")}
          </p>

          <div className="flex flex-col gap-1">
            <label htmlFor="github_repository_id" className="text-13 font-medium">
              GitHub repository ID
            </label>
            <Input
              id="github_repository_id"
              type="number"
              min={1}
              hasError={Boolean(errors.github_repository_id)}
              placeholder="e.g. 123456789"
              {...register("github_repository_id", {
                required: "GitHub repository ID is required.",
                validate: (value) => Number(value) > 0 || "GitHub repository ID must be a positive number.",
              })}
            />
            {errors.github_repository_id && (
              <span className="text-11 text-danger-primary">{errors.github_repository_id.message}</span>
            )}
          </div>

          <div className="flex flex-col gap-1">
            <label htmlFor="full_name" className="text-13 font-medium">
              Full name
            </label>
            <Input
              id="full_name"
              type="text"
              hasError={Boolean(errors.full_name)}
              placeholder="owner/repository"
              {...register("full_name", {
                required: "Full name is required.",
                validate: (value) =>
                  FULL_NAME_PATTERN.test(value) ||
                  "Full name must be exactly 'owner/repository' with no whitespace or extra slashes.",
              })}
            />
            {errors.full_name && <span className="text-11 text-danger-primary">{errors.full_name.message}</span>}
          </div>
        </div>
        <div className="flex items-center justify-end gap-2 border-t border-subtle p-4">
          <Button variant="secondary" size="sm" onClick={handleClose} type="button">
            Cancel
          </Button>
          <Button variant="primary" size="sm" type="submit" loading={isSubmitting}>
            {isSubmitting ? "Adding..." : "Add repository"}
          </Button>
        </div>
      </form>
    </ModalCore>
  );
}
