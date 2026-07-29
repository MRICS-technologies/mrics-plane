/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useMemo } from "react";
import type { ColumnDef, Row } from "@tanstack/react-table";
import { observer } from "mobx-react";
import { useParams } from "next/navigation";
import useSWR from "swr";
import { UserRound } from "lucide-react";
import type { AnalyticsTableDataMap, IContributorAnalyticsResponse, IContributorAnalyticsRow } from "@plane/types";
import { Avatar } from "@plane/ui";
import { getFileURL } from "@plane/utils";
import { useAnalytics } from "@/hooks/store/use-analytics";
import { AnalyticsService } from "@/services/analytics.service";
import { exportCSV } from "../export";
import { InsightTable } from "../insight-table";

const analyticsService = new AnalyticsService();

const formatDuration = (seconds = 0) => {
  if (seconds < 60) return seconds > 0 ? "<1m" : "0m";
  const totalMinutes = Math.floor(seconds / 60);
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  if (hours === 0) return `${minutes}m`;
  return minutes > 0 ? `${hours}h ${minutes.toString().padStart(2, "0")}m` : `${hours}h`;
};

const Metric = ({ label, value }: { label: string; value: string | number }) => (
  <div className="flex min-w-32 flex-col gap-2 border-r border-subtle pr-6 last:border-r-0">
    <span className="text-12 text-tertiary">{label}</span>
    <span className="text-20 font-semibold text-primary">{value}</span>
  </div>
);

export const ContributorAnalyticsSection = observer(function ContributorAnalyticsSection() {
  const params = useParams();
  const workspaceSlug = params.workspaceSlug.toString();
  const { selectedProjects } = useAnalytics();
  const projectIds = selectedProjects.length > 0 ? selectedProjects.join(",") : undefined;

  const { data, isLoading } = useSWR<IContributorAnalyticsResponse>(
    `contributor-analytics-${workspaceSlug}-${projectIds ?? "all"}`,
    () => analyticsService.getContributorAnalytics(workspaceSlug, projectIds)
  );

  const columns: ColumnDef<AnalyticsTableDataMap["contributors"]>[] = useMemo(
    () => [
      {
        accessorKey: "display_name",
        header: () => <div className="text-left">Contributor</div>,
        cell: ({ row }: { row: Row<IContributorAnalyticsRow> }) => (
          <div className="flex items-center gap-2 text-left">
            {row.original.avatar_url ? (
              <Avatar
                name={row.original.display_name}
                src={getFileURL(row.original.avatar_url)}
                size={24}
                shape="circle"
              />
            ) : (
              <div className="flex size-6 items-center justify-center rounded-full bg-layer-1">
                <UserRound className="size-3.5 text-secondary" />
              </div>
            )}
            <div className="min-w-0">
              <div className="truncate text-13 text-primary">{row.original.display_name}</div>
              {row.original.email && <div className="truncate text-11 text-tertiary">{row.original.email}</div>}
            </div>
          </div>
        ),
        meta: {
          export: { key: "Contributor", value: (row) => row.original.display_name },
        },
      },
      {
        accessorKey: "assigned_work_items",
        header: () => <div className="text-right">Assigned</div>,
        cell: ({ row }) => <div className="text-right">{row.original.assigned_work_items}</div>,
        meta: { export: { key: "Assigned", value: (row) => row.original.assigned_work_items } },
      },
      {
        accessorKey: "completed_work_items",
        header: () => <div className="text-right">Completed</div>,
        cell: ({ row }) => <div className="text-right">{row.original.completed_work_items}</div>,
        meta: { export: { key: "Completed", value: (row) => row.original.completed_work_items } },
      },
      {
        accessorKey: "started_work_items",
        header: () => <div className="text-right">In progress</div>,
        cell: ({ row }) => <div className="text-right">{row.original.started_work_items}</div>,
        meta: { export: { key: "In progress", value: (row) => row.original.started_work_items } },
      },
      {
        accessorKey: "completion_rate",
        header: () => <div className="text-right">Completion</div>,
        cell: ({ row }) => <div className="text-right">{row.original.completion_rate.toFixed(1)}%</div>,
        meta: { export: { key: "Completion rate", value: (row) => `${row.original.completion_rate}%` } },
      },
      {
        accessorKey: "auto_tracked_seconds",
        header: () => <div className="text-right">Progress time</div>,
        cell: ({ row }) => <div className="text-right">{formatDuration(row.original.auto_tracked_seconds)}</div>,
        meta: {
          export: { key: "Progress time", value: (row) => formatDuration(row.original.auto_tracked_seconds) },
        },
      },
      {
        accessorKey: "logged_work_seconds",
        header: () => <div className="text-right">Logged work</div>,
        cell: ({ row }) => <div className="text-right">{formatDuration(row.original.logged_work_seconds)}</div>,
        meta: {
          export: { key: "Logged work", value: (row) => formatDuration(row.original.logged_work_seconds) },
        },
      },
      {
        accessorKey: "total_tracked_seconds",
        header: () => <div className="text-right">Total tracked</div>,
        cell: ({ row }) => (
          <div className="text-right font-medium text-primary">
            {formatDuration(row.original.total_tracked_seconds)}
          </div>
        ),
        meta: {
          export: { key: "Total tracked", value: (row) => formatDuration(row.original.total_tracked_seconds) },
        },
      },
    ],
    []
  );

  return (
    <div className="flex flex-col gap-8">
      <div className="overflow-x-auto border-y border-subtle py-4">
        <div className="flex min-w-max gap-6 px-1">
          <Metric label="Contributors" value={data?.summary.member_count ?? 0} />
          <Metric label="Completed work items" value={data?.summary.completed_work_items ?? 0} />
          <Metric label="Currently in progress" value={data?.summary.started_work_items ?? 0} />
          <Metric label="Progress time" value={formatDuration(data?.summary.auto_tracked_seconds)} />
          <Metric label="Logged work" value={formatDuration(data?.summary.logged_work_seconds)} />
          <Metric label="Total tracked" value={formatDuration(data?.summary.total_tracked_seconds)} />
        </div>
      </div>

      <div className="flex flex-col gap-3">
        <div>
          <h2 className="text-16 font-medium text-primary">Contributor breakdown</h2>
          <p className="mt-1 text-12 text-tertiary">
            Task counts use current assignees. Progress and logged time use the member recorded on each worklog.
          </p>
        </div>
        <InsightTable<"contributors">
          analyticsType="contributors"
          data={data?.contributors}
          isLoading={isLoading}
          columns={columns}
          headerText="contributors"
          onExport={(rows) => data && exportCSV(rows, columns, workspaceSlug)}
        />
      </div>
    </div>
  );
});

export function Contributors() {
  return (
    <div className="px-6 py-4">
      <h1 className="mb-4 text-20 font-bold md:mb-6">Contributor analytics</h1>
      <ContributorAnalyticsSection />
    </div>
  );
}
