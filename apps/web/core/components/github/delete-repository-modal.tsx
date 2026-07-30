/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
// plane imports
import { TOAST_TYPE, setToast } from "@plane/propel/toast";
import { AlertModalCore } from "@plane/ui";

type Props = {
  isOpen: boolean;
  onClose: () => void;
  onDelete: () => Promise<void>;
  repositoryName: string;
};

export function DeleteRepositoryModal(props: Props) {
  const { isOpen, onClose, onDelete, repositoryName } = props;
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleClose = () => {
    onClose();
    setIsSubmitting(false);
  };

  const handleSubmit = async () => {
    setIsSubmitting(true);
    try {
      await onDelete();
      setToast({ type: TOAST_TYPE.SUCCESS, title: "Success!", message: "Repository removed." });
      handleClose();
    } catch (error) {
      const typedError = error as { status?: number; data?: { error?: string } };
      setToast({
        type: TOAST_TYPE.ERROR,
        title: "Error!",
        message:
          typedError?.status === 409
            ? (typedError?.data?.error ?? "Remove project mappings before deleting this repository.")
            : "This repository could not be removed.",
      });
      setIsSubmitting(false);
    }
  };

  return (
    <AlertModalCore
      isOpen={isOpen}
      handleClose={handleClose}
      handleSubmit={handleSubmit}
      isSubmitting={isSubmitting}
      title="Remove repository"
      content={
        <>
          Remove <span className="font-medium">{repositoryName}</span> from this workspace? Project mappings using this
          repository must be removed first.
        </>
      }
    />
  );
}
