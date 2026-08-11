/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
// plane imports
import { useTranslation } from "@plane/i18n";
import { TOAST_TYPE, setToast } from "@plane/propel/toast";
import { AlertModalCore } from "@plane/ui";

type Props = {
  isOpen: boolean;
  onClose: () => void;
  onDisconnect: () => Promise<void>;
};

export function DisconnectInstallationModal(props: Props) {
  const { isOpen, onClose, onDisconnect } = props;
  const { t } = useTranslation();
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleClose = () => {
    onClose();
    setIsSubmitting(false);
  };

  const handleSubmit = async () => {
    setIsSubmitting(true);
    try {
      await onDisconnect();
      setToast({
        type: TOAST_TYPE.SUCCESS,
        title: t("common.success"),
        message: t("workspace_settings.settings.github.installation.disconnect_modal.success"),
      });
      handleClose();
    } catch (error) {
      const typedError = error as { status?: number; data?: { error?: string } };
      setToast({
        type: TOAST_TYPE.ERROR,
        title: t("common.error"),
        message:
          typedError?.status === 409
            ? (typedError?.data?.error ??
              t("workspace_settings.settings.github.installation.disconnect_modal.conflict"))
            : t("workspace_settings.settings.github.installation.disconnect_modal.failed"),
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
      title={t("workspace_settings.settings.github.installation.disconnect_modal.title")}
      content={t("workspace_settings.settings.github.installation.disconnect_modal.content")}
    />
  );
}
