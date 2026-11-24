/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import useSWR from "swr";
// plane imports
import { Select } from "@plane/blocks/select";
import { Loader } from "@plane/blocks/skeleton";
import { setToast } from "@plane/blocks/toast";
import { GITHUB_PROJECT_TEAM_REPOSITORIES_KEY } from "@plane/constants";
import { useTranslation } from "@plane/i18n";
import type { TRepoProjectMapping } from "@plane/types";
// components
import { SettingsHeading } from "@/components/settings/heading";
// services
import { GithubSyncService } from "@/services/github-sync.service";

const githubSyncService = new GithubSyncService();

type TRepositoryOption = { id: string; label: string };

type Props = {
  workspaceSlug: string;
  projectId: string;
  /** The project's mappings, already loaded by the panel. */
  mappings: TRepoProjectMapping[];
  /** Re-fetches the mappings: their "Team default for" hints follow the team defaults. */
  onChange: () => Promise<unknown>;
};

export function TeamDefaults(props: Props) {
  const { workspaceSlug, projectId, mappings, onChange } = props;
  const { t } = useTranslation();

  const {
    data: rows,
    error,
    isLoading,
    mutate,
  } = useSWR(GITHUB_PROJECT_TEAM_REPOSITORIES_KEY(workspaceSlug, projectId), () =>
    githubSyncService.getTeamRepositories(workspaceSlug, projectId)
  );

  // "" is the project default: the team has no repository of its own here.
  const options: TRepositoryOption[] = [
    { id: "", label: t("project_settings.github.team_defaults.project_default") },
    ...mappings.map((mapping) => ({
      id: mapping.id,
      label: mapping.repository_detail?.full_name ?? mapping.github_repo,
    })),
  ];

  const handleChange = async (teamId: string, mappingId: string) => {
    try {
      await githubSyncService.setTeamRepository(workspaceSlug, projectId, teamId, mappingId || null);
    } catch {
      setToast({
        type: "error",
        title: t("common.error.label"),
        message: t("project_settings.github.team_defaults.errors.save_failed"),
      });
    }
    await Promise.all([mutate(), onChange()]);
  };

  return (
    <div className="flex flex-col gap-2">
      <SettingsHeading
        variant="h6"
        title={t("project_settings.github.team_defaults.title")}
        description={t("project_settings.github.team_defaults.description")}
      />
      {isLoading ? (
        <Loader className="flex flex-col gap-2">
          <Loader.Item height="40px" />
        </Loader>
      ) : error ? (
        <p className="text-13 text-tertiary">{t("project_settings.github.team_defaults.errors.load_failed")}</p>
      ) : !rows?.length ? (
        <p className="text-13 text-tertiary">{t("project_settings.github.team_defaults.no_teams")}</p>
      ) : (
        <div>
          {rows.map((row) => (
            <div
              key={row.team.id}
              className="flex items-center justify-between gap-3 border-b border-subtle py-2"
              data-testid="team-default"
            >
              <div className="flex min-w-0 flex-col gap-0.5">
                <span className="truncate text-13 font-medium">{row.team.name}</span>
                <span className="text-11 text-tertiary">
                  {t("workspace_settings.settings.teams.member_count", { count: row.team.member_count })}
                </span>
              </div>
              <div className="w-64 max-w-[50%] flex-shrink-0">
                <Select<TRepositoryOption>
                  getValues={() => options}
                  value={options.find((option) => option.id === (row.mapping_id ?? "")) ?? options[0]}
                  onChange={(id) => void handleChange(row.team.id, id)}
                  getOptionValue={(option) => option.id}
                  getOptionLabel={(option) => option.label}
                  placeholder={row.team.name}
                  contentSizing="anchor"
                >
                  <Select.Trigger<TRepositoryOption> variant="select-md">
                    <Select.Value />
                  </Select.Trigger>
                </Select>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
