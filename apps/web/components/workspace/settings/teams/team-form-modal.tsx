/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { Button } from "@makeplane/propel/components/button";
import {
  Dialog,
  DialogActions,
  DialogBody,
  DialogContent,
  DialogHeader,
  DialogHeading,
  DialogMain,
  DialogTitle,
} from "@makeplane/propel/components/dialog";
import { InputField } from "@makeplane/propel/components/input-field";
import { useTranslation } from "@plane/i18n";

type Props = {
  title: string;
  submitLabel: string;
  initialName?: string;
  onClose: () => void;
  /** Resolves when saved; a rejection keeps the dialog open (the caller shows the error). */
  onSubmit: (name: string) => Promise<void>;
};

/** Create or rename a team: just the name. Mounted only while open, so it starts from `initialName`. */
export function TeamFormModal(props: Props) {
  const { title, submitLabel, initialName = "", onClose, onSubmit } = props;
  const { t } = useTranslation();
  const [name, setName] = useState(initialName);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [showError, setShowError] = useState(false);

  const handleSubmit = async (event: React.SyntheticEvent) => {
    event.preventDefault();
    if (!name.trim()) {
      setShowError(true);
      return;
    }
    setIsSubmitting(true);
    try {
      await onSubmit(name.trim());
      onClose();
    } catch {
      // The caller already showed a toast.
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogContent size="sm">
        <form onSubmit={(event) => void handleSubmit(event)} className="flex min-h-0 flex-1 flex-col">
          <DialogMain>
            <DialogHeader>
              <DialogHeading>
                <DialogTitle>{title}</DialogTitle>
              </DialogHeading>
            </DialogHeader>
            <DialogBody render={<div className="flex flex-col gap-1.5" />}>
              <InputField
                size="lg"
                orientation="vertical"
                id="team_name"
                type="text"
                maxLength={255}
                label={t("workspace_settings.settings.teams.form.name_label")}
                placeholder={t("workspace_settings.settings.teams.form.name_placeholder")}
                value={name}
                onChange={(event) => setName(event.target.value)}
              />
              {showError && !name.trim() && (
                <span className="text-11 text-danger-primary">
                  {t("workspace_settings.settings.teams.form.name_required")}
                </span>
              )}
            </DialogBody>
          </DialogMain>
          <DialogActions>
            <Button variant="secondary" size="md" stretch="auto" label={t("common.cancel")} onClick={onClose} />
            <Button
              variant="primary"
              size="md"
              stretch="auto"
              type="submit"
              loading={isSubmitting}
              label={submitLabel}
            />
          </DialogActions>
        </form>
      </DialogContent>
    </Dialog>
  );
}
