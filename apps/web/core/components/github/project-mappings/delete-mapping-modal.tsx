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
  onDelete: () => Promise<void>;
  mappingLabel: string;
};

export function DeleteMappingModal(props: Props) {
  const { isOpen, onClose, onDelete, mappingLabel } = props;
  const { t } = useTranslation();
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleClose = () => {
    onClose();
    setIsSubmitting(false);
  };

  const handleSubmit = async () => {
    setIsSubmitting(true);
    try {
      await onDelete();
      setToast({
        type: TOAST_TYPE.SUCCESS,
        title: t("common.success"),
        message: t("project_settings.github.mapping.delete_modal.success"),
      });
      handleClose();
    } catch (error) {
      const typedError = error as { status?: number };
      const message =
        typedError?.status === 403
          ? t("project_settings.github.mapping.delete_modal.forbidden")
          : t("project_settings.github.mapping.delete_modal.failed");
      setToast({ type: TOAST_TYPE.ERROR, title: t("common.error"), message });
      setIsSubmitting(false);
    }
  };

  return (
    <AlertModalCore
      isOpen={isOpen}
      handleClose={handleClose}
      handleSubmit={handleSubmit}
      isSubmitting={isSubmitting}
      title={t("project_settings.github.mapping.delete_modal.title")}
      content={t("project_settings.github.mapping.delete_modal.content", { repo: mappingLabel })}
    />
  );
}
