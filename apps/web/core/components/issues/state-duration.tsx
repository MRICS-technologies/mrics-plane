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
  const remainingSeconds = totalSeconds % 60;

  if (hours > 0) return `${hours}h ${minutes}m`;
  if (minutes > 0) return `${minutes}m ${remainingSeconds}s`;
  return `${remainingSeconds}s`;
};

const formatTimestamp = (value: string | null) => {
  if (!value) return "—";
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
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
  const label = isActive
    ? `In progress ${formatDuration(data.active_started_seconds)}`
    : formatDuration(data.total_started_seconds);

  return (
    <div
      className={cn(
        "border-custom-border-200 bg-custom-background-80 inline-flex max-w-full items-center gap-1 rounded-full border px-2 py-0.5 text-11 font-medium text-secondary",
        {
          "border-green-500/30 bg-green-500/10 text-green-600": isActive,
        },
        className
      )}
      title={`Auto-tracked time in started states: ${formatDuration(data.total_started_seconds)}`}
    >
      <Clock className="size-3 flex-shrink-0" />
      <span className="truncate">{label}</span>
    </div>
  );
};

export const IssueStateDurationReport = (props: TStateDurationProps) => {
  const { className } = props;
  const { data, isLoading, error } = useIssueStateDuration(props);

  if (isLoading)
    return (
      <div className={cn("border-custom-border-200 bg-custom-background-90 rounded-lg border p-3", className)}>
        <div className="bg-custom-background-80 h-4 w-36 animate-pulse rounded" />
      </div>
    );

  if (error || !data) return null;

  const isActive = data.current_state?.group === "started";
  const recentSessions = data.sessions.slice(Math.max(data.sessions.length - 5, 0));
  const latestSessions: TStateDurationSession[] = [];
  for (const session of recentSessions) latestSessions.unshift(session);

  return (
    <section className={cn("border-custom-border-200 bg-custom-background-90 rounded-lg border p-3", className)}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <div className="text-sm flex items-center gap-2 font-semibold text-primary">
            <Clock className="size-4 text-secondary" />
            <span>Time in progress</span>
          </div>
          <p className="text-xs text-secondary">Automatically tracked from Started/In Progress state changes.</p>
        </div>
        <div className="text-right">
          <div className="text-lg font-semibold text-primary">{formatDuration(data.total_started_seconds)}</div>
          <div className="text-11 text-tertiary">total started time</div>
        </div>
      </div>

      <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-3">
        <div className="bg-custom-background-100 rounded-md p-2">
          <div className="text-11 text-tertiary uppercase">Current state</div>
          <div className="text-xs mt-1 font-medium text-primary">{data.current_state?.name ?? "—"}</div>
        </div>
        <div className="bg-custom-background-100 rounded-md p-2">
          <div className="text-11 text-tertiary uppercase">Active session</div>
          <div className={cn("text-xs mt-1 font-medium", isActive ? "text-green-600" : "text-primary")}>
            {isActive ? formatDuration(data.active_started_seconds) : "Not running"}
          </div>
        </div>
        <div className="bg-custom-background-100 rounded-md p-2">
          <div className="text-11 text-tertiary uppercase">Completed sessions</div>
          <div className="text-xs mt-1 font-medium text-primary">{data.sessions.length}</div>
        </div>
      </div>

      {latestSessions.length > 0 && (
        <div className="border-custom-border-200 mt-3 border-t pt-3">
          <div className="text-xs mb-2 font-medium text-secondary">Recent auto-tracked sessions</div>
          <div className="space-y-1.5">
            {latestSessions.map((session) => (
              <div
                key={session.id}
                className="bg-custom-background-100 text-xs flex flex-wrap items-center justify-between gap-2 rounded-md px-2 py-1.5"
              >
                <div className="min-w-0 text-secondary">
                  <span>{formatTimestamp(session.started_at)}</span>
                  <span className="px-1 text-tertiary">→</span>
                  <span>{formatTimestamp(session.stopped_at)}</span>
                </div>
                <div className="font-medium text-primary">{formatDuration(session.duration_seconds)}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
};
