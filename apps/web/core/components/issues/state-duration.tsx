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

  if (hours > 0) return `${hours}h ${String(minutes).padStart(2, "0")}m`;
  if (minutes > 0) return `${minutes}m`;
  return "<1m";
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

  return (
    <div
      className={cn("inline-flex items-center gap-1 text-11 text-tertiary", { "text-green-600": isActive }, className)}
      title={`Auto-tracked time in started states: ${formatDuration(data.total_started_seconds)}`}
    >
      <Clock className="size-3 flex-shrink-0" />
      <span>{formatDuration(data.total_started_seconds)}</span>
    </div>
  );
};

export const IssueStateDurationReport = (props: TStateDurationProps) => {
  const { className } = props;
  const { data, error } = useIssueStateDuration(props);

  if (error || !data || (data.total_started_seconds <= 0 && data.sessions.length === 0)) return null;

  const isActive = data.current_state?.group === "started";
  const latestSessions: TStateDurationSession[] = [];
  for (const session of data.sessions.slice(-5)) latestSessions.unshift(session);

  return (
    <section className={cn("border-custom-border-200 rounded-md border px-3 py-2", className)}>
      <div className="text-xs flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5 font-medium text-secondary">
          <Clock className="size-3.5 flex-shrink-0" />
          <span>Time in progress</span>
          {isActive && <span className="text-green-600">{formatDuration(data.active_started_seconds)} running</span>}
        </div>
        <span className="font-medium text-primary">{formatDuration(data.total_started_seconds)}</span>
      </div>

      {latestSessions.length > 0 && (
        <div className="mt-1.5 space-y-0.5">
          {latestSessions.map((session) => (
            <div key={session.id} className="flex items-center justify-between gap-2 text-11 text-tertiary">
              <span className="truncate">
                {formatTimestamp(session.started_at)} → {formatTimestamp(session.stopped_at)}
              </span>
              <span className="flex-shrink-0">{formatDuration(session.duration_seconds)}</span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
};
