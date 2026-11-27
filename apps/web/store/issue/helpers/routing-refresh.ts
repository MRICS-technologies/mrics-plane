/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

/**
 * MRICS routing rules (not in upstream Plane). When a work item gains a label or a parent, a rule can add its
 * team's leader as an assignee on the server. Neither the PATCH (no body) nor the sub-issues POST reports it,
 * so these helpers read the assignees back.
 */

import { clone, uniq } from "lodash-es";
import { runInAction } from "mobx";
import type { TIssue } from "@plane/types";
import type { IssueService } from "@/services/issue";
import type { IIssueRootStore } from "../root.store";

type TRoutingRefreshStore = {
  rootIssueStore: IIssueRootStore;
  issueService: IssueService;
  /** Regroups a layout after the assignees change. */
  updateIssueList?: (issue?: TIssue, issueBeforeUpdate?: TIssue) => void;
};

/** Whether an update can fire a routing rule: a label the work item didn't have, or a new parent. */
const mayRouteIssue = (issueBeforeUpdate: TIssue | undefined, data: Partial<TIssue>) =>
  (!!data.parent_id && data.parent_id !== issueBeforeUpdate?.parent_id) ||
  (data.label_ids ?? []).some((labelId) => !issueBeforeUpdate?.label_ids?.includes(labelId));

/**
 * Reads the work items' assignees back and adds the ones that are new on the server: not in the store when the
 * call starts, nor in `knownAssigneeIds`. Add only: a rule never removes anyone, and an assignee edit made in the
 * meantime must survive. Writes nothing when nothing is new. Best effort: the change itself has succeeded.
 */
export const refreshRoutedAssignees = async (
  store: TRoutingRefreshStore,
  workspaceSlug: string,
  projectId: string,
  issueIds: string[],
  knownAssigneeIds: string[] = []
) => {
  const { issues } = store.rootIssueStore;
  const before = new Map(
    issueIds.map((issueId) => [issueId, [...knownAssigneeIds, ...(issues.getIssueById(issueId)?.assignee_ids ?? [])]])
  );
  try {
    const serverIssues = await store.issueService.retrieveIssues(workspaceSlug, projectId, issueIds);
    runInAction(() => {
      for (const { id, assignee_ids: serverAssigneeIds = [] } of serverIssues) {
        const issue = clone(issues.getIssueById(id));
        if (!issue) continue;
        const current = issue.assignee_ids ?? [];
        const added = serverAssigneeIds.filter((assigneeId) => !before.get(id)?.includes(assigneeId));
        const assigneeIds = uniq([...current, ...added]);
        if (assigneeIds.length === current.length) continue;
        issues.updateIssue(id, { assignee_ids: assigneeIds });
        store.updateIssueList?.({ ...issue, assignee_ids: assigneeIds }, issue);
      }
    });
  } catch {
    // The next fetch of the work items shows them.
  }
};

/**
 * After an update that may fire a rule: adds the assignee the rule may have added and, when the work item's
 * history is loaded, re-reads it for the rule's entry (the detail page loads the history in parallel with the
 * PATCH, so it can miss that entry).
 */
export const refreshRoutedIssue = async (
  store: TRoutingRefreshStore,
  workspaceSlug: string,
  projectId: string,
  issueId: string,
  issueBeforeUpdate: TIssue | undefined,
  data: Partial<TIssue>
) => {
  if (!mayRouteIssue(issueBeforeUpdate, data)) return;
  // The assignees before the PATCH count as known too, so one removed while it ran doesn't come back.
  await refreshRoutedAssignees(store, workspaceSlug, projectId, [issueId], issueBeforeUpdate?.assignee_ids);
  const { activity } = store.rootIssueStore.issueDetail;
  if (!activity.getActivitiesByIssueId(issueId)) return;
  await activity.fetchActivities(workspaceSlug, projectId, issueId).catch(() => undefined);
};
