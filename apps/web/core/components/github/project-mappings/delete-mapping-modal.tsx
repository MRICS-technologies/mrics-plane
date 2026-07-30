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
  mappingLabel: string;
};

export function DeleteMappingModal(props: Props) {
  const { isOpen, onClose, onDelete, mappingLabel } = props;
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleClose = () => {
    onClose();
    setIsSubmitting(false);
  };

  const handleSubmit = async () => {
    setIsSubmitting(true);
    try {
      await onDelete();
      setToast({ type: TOAST_TYPE.SUCCESS, title: "Success!", message: "Mapping removed." });
      handleClose();
    } catch (error) {
      const typedError = error as { status?: number };
      let message = "This mapping could not be removed.";
      if (typedError?.status === 403) message = "You do not have permission to remove this mapping.";
      setToast({ type: TOAST_TYPE.ERROR, title: "Error!", message });
      setIsSubmitting(false);
    }
  };

  return (
    <AlertModalCore
      isOpen={isOpen}
      handleClose={handleClose}
      handleSubmit={handleSubmit}
      isSubmitting={isSubmitting}
      title="Remove mapping"
      content={
        <>
          Remove the mapping to <span className="font-medium">{mappingLabel}</span> from this project?
        </>
      }
    />
  );
}
