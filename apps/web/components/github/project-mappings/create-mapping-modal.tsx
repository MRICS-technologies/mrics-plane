/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect } from "react";
import { Controller, useForm } from "react-hook-form";
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
import { FieldLabel } from "@makeplane/propel/elements/field";
import { Select } from "@plane/blocks/select";
import { setToast } from "@plane/blocks/toast";
import { useTranslation } from "@plane/i18n";
import type { TCreateMappingPayload, TGithubEnabledRepository } from "@plane/types";

type TFormValues = {
  repository_id: string;
  base_branch: string;
};

const DEFAULT_VALUES: TFormValues = {
  repository_id: "",
  base_branch: "",
};

type Props = {
  isOpen: boolean;
  onClose: () => void;
  onCreate: (data: TCreateMappingPayload) => Promise<void>;
  enabledRepositories: TGithubEnabledRepository[];
};

export function CreateMappingModal(props: Props) {
  const { isOpen, onClose, onCreate, enabledRepositories } = props;
  const { t } = useTranslation();
  const {
    control,
    handleSubmit,
    reset,
    setValue,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<TFormValues>({ defaultValues: DEFAULT_VALUES });

  const selectedRepositoryId = watch("repository_id");

  // Prefill the base branch from the repository's GitHub default branch
  // instead of the model's hardcoded "dev" fallback -- still editable.
  useEffect(() => {
    const repository = enabledRepositories.find((repo) => repo.id === selectedRepositoryId);
    if (repository?.default_branch) {
      setValue("base_branch", repository.default_branch);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedRepositoryId]);

  const handleClose = () => {
    onClose();
    setTimeout(() => reset(DEFAULT_VALUES), 300);
  };

  const handleFormSubmit = async (data: TFormValues) => {
    await onCreate({ repository_id: data.repository_id, base_branch: data.base_branch.trim() || undefined })
      .then(() => handleClose())
      .catch((error: { status?: number }) => {
        let message = t("project_settings.github.mapping.errors.create_failed");
        if (error?.status === 409) message = t("project_settings.github.mapping.errors.conflict");
        if (error?.status === 403) message = t("project_settings.github.mapping.errors.forbidden");
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
                <DialogTitle>{t("project_settings.github.mapping.modal.title")}</DialogTitle>
                <DialogDescription>{t("project_settings.github.mapping.modal.description")}</DialogDescription>
              </DialogHeading>
            </DialogHeader>
            <DialogBody render={<div className="flex flex-col gap-4" />}>
              <div className="flex flex-col gap-1.5">
                <FieldLabel size="lg" inset={false} htmlFor="repository_id">
                  {t("project_settings.github.mapping.modal.repository_label")}
                </FieldLabel>
                <Controller
                  name="repository_id"
                  control={control}
                  rules={{ required: t("project_settings.github.mapping.modal.repository_required") }}
                  render={({ field: { value, onChange } }) => (
                    <Select<TGithubEnabledRepository>
                      getValues={() => enabledRepositories}
                      value={enabledRepositories.find((repository) => repository.id === value) ?? null}
                      onChange={onChange}
                      getOptionValue={(repository) => repository.id}
                      getOptionLabel={(repository) => repository.full_name}
                      placeholder={t("project_settings.github.mapping.modal.repository_placeholder")}
                      contentSizing="anchor"
                    >
                      <Select.Trigger<TGithubEnabledRepository> id="repository_id" variant="select-lg">
                        <Select.Value />
                      </Select.Trigger>
                    </Select>
                  )}
                />
                {errors.repository_id && (
                  <span className="text-11 text-danger-primary">{errors.repository_id.message}</span>
                )}
              </div>

              <Controller
                name="base_branch"
                control={control}
                render={({ field }) => (
                  <InputField
                    size="lg"
                    orientation="vertical"
                    id="base_branch"
                    type="text"
                    placeholder="main"
                    label={t("project_settings.github.mapping.modal.base_branch_label")}
                    hint={t("project_settings.github.mapping.modal.base_branch_hint")}
                    {...field}
                  />
                )}
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
              label={isSubmitting ? t("common.adding") : t("project_settings.github.mapping.modal.submit")}
            />
          </DialogActions>
        </form>
      </DialogContent>
    </Dialog>
  );
}
