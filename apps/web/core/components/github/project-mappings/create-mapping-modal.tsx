/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect } from "react";
import { Controller, useForm } from "react-hook-form";
// plane imports
import { useTranslation } from "@plane/i18n";
import { Button } from "@plane/propel/button";
import { TOAST_TYPE, setToast } from "@plane/propel/toast";
import type { TCreateMappingPayload, TGithubEnabledRepository } from "@plane/types";
import { CustomSearchSelect, EModalPosition, EModalWidth, Input, ModalCore } from "@plane/ui";

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
        setToast({ type: TOAST_TYPE.ERROR, title: t("common.error"), message });
      });
  };

  const repositoryOptions = enabledRepositories.map((repository) => ({
    value: repository.id,
    query: repository.full_name,
    content: <p>{repository.full_name}</p>,
  }));

  return (
    <ModalCore isOpen={isOpen} handleClose={handleClose} position={EModalPosition.TOP} width={EModalWidth.XL}>
      <form onSubmit={handleSubmit(handleFormSubmit)}>
        <div className="flex flex-col gap-4 p-5">
          <h3 className="text-lg font-medium">{t("project_settings.github.mapping.modal.title")}</h3>
          <p className="text-13 text-tertiary">{t("project_settings.github.mapping.modal.description")}</p>

          <div className="flex flex-col gap-1">
            <label htmlFor="repository_id" className="text-13 font-medium">
              {t("project_settings.github.mapping.modal.repository_label")}
            </label>
            <Controller
              name="repository_id"
              control={control}
              rules={{ required: t("project_settings.github.mapping.modal.repository_required") }}
              render={({ field: { value, onChange } }) => (
                <CustomSearchSelect
                  value={value}
                  options={repositoryOptions}
                  onChange={onChange}
                  label={
                    repositoryOptions.find((option) => option.value === value)?.query ??
                    t("project_settings.github.mapping.modal.repository_placeholder")
                  }
                />
              )}
            />
            {errors.repository_id && (
              <span className="text-11 text-danger-primary">{errors.repository_id.message}</span>
            )}
          </div>

          <div className="flex flex-col gap-1">
            <label htmlFor="base_branch" className="text-13 font-medium">
              {t("project_settings.github.mapping.modal.base_branch_label")}
            </label>
            <Controller
              name="base_branch"
              control={control}
              render={({ field }) => <Input id="base_branch" type="text" placeholder="main" {...field} />}
            />
            <span className="text-11 text-tertiary">{t("project_settings.github.mapping.modal.base_branch_hint")}</span>
          </div>
        </div>
        <div className="flex items-center justify-end gap-2 border-t border-subtle p-4">
          <Button variant="secondary" size="sm" onClick={handleClose} type="button">
            {t("common.cancel")}
          </Button>
          <Button variant="primary" size="sm" type="submit" loading={isSubmitting}>
            {isSubmitting ? t("common.adding") : t("project_settings.github.mapping.modal.submit")}
          </Button>
        </div>
      </form>
    </ModalCore>
  );
}
