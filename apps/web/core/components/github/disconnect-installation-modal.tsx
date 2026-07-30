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
  onDisconnect: () => Promise<void>;
};

export function DisconnectInstallationModal(props: Props) {
  const { isOpen, onClose, onDisconnect } = props;
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleClose = () => {
    onClose();
    setIsSubmitting(false);
  };

  const handleSubmit = async () => {
    setIsSubmitting(true);
    try {
      await onDisconnect();
      setToast({ type: TOAST_TYPE.SUCCESS, title: "Success!", message: "GitHub installation disconnected." });
      handleClose();
    } catch (error) {
      const typedError = error as { status?: number; data?: { error?: string } };
      setToast({
        type: TOAST_TYPE.ERROR,
        title: "Error!",
        message:
          typedError?.status === 409
            ? (typedError?.data?.error ?? "Remove project mappings before disconnecting this installation.")
            : "This installation could not be disconnected.",
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
      title="Disconnect GitHub installation"
      content="This removes the registered installation from this workspace. Repositories enabled under it will also be removed. This action cannot be undone."
    />
  );
}
