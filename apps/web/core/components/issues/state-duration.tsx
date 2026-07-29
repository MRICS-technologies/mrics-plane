// oxlint-disable no-shadow
/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import useSWR from "swr";
import { Clock } from "lucide-react";
// ui
import { cn } from "@plane/utils";
// components
import { SidebarPropertyListItem } from "@/components/common/layout/sidebar/property-list-item";
// services
import { IssueService } from "@/services/issue";

const issueService = new IssueService();

type TStateDurationSession = {
  id: string;
  state_group: string;
  state_name: string;
  started_at: string | null;
  stopped_at: string | null;
  duration_seconds: number;
  duration_hours: string;
  logged_by: string;
  source: string;
};

type TStateDurationSummary = {
  issue: string;
  current_state: {
    id: string;
    name: string;
    group: string;
  } | null;
  completed_started_seconds: number;
  completed_started_hours: string;
  active_started_at: string | null;
  active_started_seconds: number;
  active_started_hours: string;
  total_started_seconds: number;
  total_started_hours: string;
  sessions: TStateDurationSession[];
};

type TStateDurationProps = {
  workspaceSlug: string;
  projectId: string;
  issueId: string;
  className?: string;
};

const stateDurationKey = (workspaceSlug: string, projectId: string, issueId: string) =>
  `ISSUE_STATE_DURATION_${workspaceSlug}_${projectId}_${issueId}`;

const formatDuration = (seconds?: number) => {
  const totalSeconds = Math.max(0, Math.round(seconds ?? 0));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);

  if (hours > 0) return `${hours}h ${String(minutes).padStart(2, "0")}m`;
  if (minutes > 0) return `${minutes}m`;
  return "<1m";
};

const useIssueStateDuration = ({ workspaceSlug, projectId, issueId }: TStateDurationProps) =>
  useSWR<TStateDurationSummary>(
    workspaceSlug && projectId && issueId ? stateDurationKey(workspaceSlug, projectId, issueId) : null,
    () => issueService.retrieveStateDurations(workspaceSlug, projectId, issueId),
    {
      refreshInterval: (data) => (data?.current_state?.group === "started" ? 5000 : 0),
      revalidateOnFocus: true,
    }
  );

export const IssueStateDurationBadge = (props: TStateDurationProps) => {
  const { className } = props;
  const { data } = useIssueStateDuration(props);

  if (!data || data.total_started_seconds <= 0) return null;

  const isActive = data.current_state?.group === "started";

  return (
    <div
      className={cn("inline-flex items-center gap-1 text-11 text-tertiary", { "text-green-600": isActive }, className)}
      title={`Auto-tracked time in progress states: ${formatDuration(data.total_started_seconds)}`}
    >
      <Clock className="size-3 flex-shrink-0" />
      <span>{formatDuration(data.total_started_seconds)}</span>
    </div>
  );
};

export const IssueStateDurationProperty = (props: TStateDurationProps) => {
  const { className } = props;
  const { data, error } = useIssueStateDuration(props);

  if (error || !data || data.total_started_seconds <= 0) return null;

  const isActive = data.current_state?.group === "started";

  return (
    <SidebarPropertyListItem icon={Clock} label="Time in Progress">
      <div
        className={cn(
          "flex h-7.5 w-full items-center gap-1.5 rounded-sm px-2 text-body-xs-medium text-secondary",
          { "text-green-600": isActive },
          className
        )}
        title={`Auto-tracked from progress states: ${formatDuration(data.total_started_seconds)}`}
      >
        <span>{formatDuration(data.total_started_seconds)}</span>
        {isActive && <span className="text-green-600 text-11">running</span>}
      </div>
    </SidebarPropertyListItem>
  );
};
