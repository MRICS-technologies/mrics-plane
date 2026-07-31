/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { Controller, useForm } from "react-hook-form";
// plane imports
import { Button } from "@plane/propel/button";
import { TOAST_TYPE, setToast } from "@plane/propel/toast";
import { CustomSearchSelect, EModalPosition, EModalWidth, ModalCore } from "@plane/ui";
// services
import type { TCreateMappingPayload, TGithubEnabledRepository } from "@/services/github-sync.service";

type TFormValues = {
  repository_id: string;
};

const DEFAULT_VALUES: TFormValues = {
  repository_id: "",
};

type Props = {
  isOpen: boolean;
  onClose: () => void;
  onCreate: (data: TCreateMappingPayload) => Promise<void>;
  enabledRepositories: TGithubEnabledRepository[];
};

export function CreateMappingModal(props: Props) {
  const { isOpen, onClose, onCreate, enabledRepositories } = props;
  const {
    control,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<TFormValues>({ defaultValues: DEFAULT_VALUES });

  const handleClose = () => {
    onClose();
    setTimeout(() => reset(DEFAULT_VALUES), 300);
  };

  const handleFormSubmit = async (data: TFormValues) => {
    await onCreate({ repository_id: data.repository_id })
      .then(() => handleClose())
      .catch((error: { status?: number }) => {
        let message = "This mapping could not be created.";
        if (error?.status === 409) message = "This project already has a mapping. Remove it before adding a new one.";
        if (error?.status === 403) message = "You do not have permission to create a mapping for this project.";
        setToast({ type: TOAST_TYPE.ERROR, title: "Error!", message });
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
          <h3 className="text-lg font-medium">Add mapping</h3>
          <p className="text-13 text-tertiary">Map this project to one of the workspace&apos;s enabled repositories.</p>

          <div className="flex flex-col gap-1">
            <label htmlFor="repository_id" className="text-13 font-medium">
              Repository
            </label>
            <Controller
              name="repository_id"
              control={control}
              rules={{ required: "A repository is required." }}
              render={({ field: { value, onChange } }) => (
                <CustomSearchSelect
                  value={value}
                  options={repositoryOptions}
                  onChange={onChange}
                  label={repositoryOptions.find((option) => option.value === value)?.query ?? "Select a repository"}
                />
              )}
            />
            {errors.repository_id && (
              <span className="text-11 text-danger-primary">{errors.repository_id.message}</span>
            )}
          </div>
        </div>
        <div className="flex items-center justify-end gap-2 border-t border-subtle p-4">
          <Button variant="secondary" size="sm" onClick={handleClose} type="button">
            Cancel
          </Button>
          <Button variant="primary" size="sm" type="submit" loading={isSubmitting}>
            {isSubmitting ? "Adding..." : "Add mapping"}
          </Button>
        </div>
      </form>
    </ModalCore>
  );
}
