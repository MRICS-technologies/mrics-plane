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
        setToast({ type: "error", title: t("common.error"), message });
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
                <DialogTitle>{t("workspace_settings.settings.github.repositories.manual.modal.title")}</DialogTitle>
                <DialogDescription>
                  {t("workspace_settings.settings.github.repositories.manual.modal.description")}
                </DialogDescription>
              </DialogHeading>
            </DialogHeader>
            <DialogBody render={<div className="flex flex-col gap-4" />}>
              <InputField
                size="lg"
                orientation="vertical"
                id="github_repository_id"
                type="number"
                min={1}
                label="GitHub repository ID"
                placeholder="e.g. 123456789"
                error={errors.github_repository_id?.message}
                {...register("github_repository_id", {
                  required: "GitHub repository ID is required.",
                  validate: (value) => Number(value) > 0 || "GitHub repository ID must be a positive number.",
                })}
              />
              <InputField
                size="lg"
                orientation="vertical"
                id="full_name"
                type="text"
                label="Full name"
                placeholder="owner/repository"
                error={errors.full_name?.message}
                {...register("full_name", {
                  required: "Full name is required.",
                  validate: (value) =>
                    FULL_NAME_PATTERN.test(value) ||
                    "Full name must be exactly 'owner/repository' with no whitespace or extra slashes.",
                })}
              />
            </DialogBody>
          </DialogMain>
          <DialogActions>
            <Button variant="secondary" size="md" stretch="auto" label="Cancel" onClick={handleClose} />
            <Button
              variant="primary"
              size="md"
              stretch="auto"
              type="submit"
              loading={isSubmitting}
              label={isSubmitting ? "Adding..." : "Add repository"}
            />
          </DialogActions>
        </form>
      </DialogContent>
    </Dialog>
  );
}
