/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
import { AutomationsOutline } from "@makeplane/propel/icons";
// hooks
import { useIssueDetail } from "@/hooks/store/use-issue-detail";
// components
import { IssueActivityBlockComponent } from "./";

type TIssueRoutingRuleActivity = { activityId: string; ends: "top" | "bottom" | undefined };

/** A routing rule matched but assigned nobody; the actor is the routing rule bot ("Routing rule"). */
export const IssueRoutingRuleActivity = observer(function IssueRoutingRuleActivity(props: TIssueRoutingRuleActivity) {
  const { activityId, ends } = props;
  // hooks
  const {
    activity: { getActivityById },
  } = useIssueDetail();

  const activity = getActivityById(activityId);

  if (!activity) return <></>;

  return (
    <IssueActivityBlockComponent
      icon={<AutomationsOutline className="h-3.5 w-3.5 flex-shrink-0 text-secondary" aria-hidden="true" />}
      activityId={activityId}
      ends={ends}
      // The routing rule bot has no profile page to link to.
      customUserName={activity.actor_detail?.is_bot ? activity.actor_detail.display_name : undefined}
    >
      {/* The server's own English sentence, e.g. `routing rule matched (label "Flutter" → team Flutter), team has no leader`. */}
      {activity.comment}
    </IssueActivityBlockComponent>
  );
});
