/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { API_BASE_URL } from "@plane/constants";
import type { TApiError, TProjectRoutingRule, TProjectRoutingRuleCreate } from "@plane/types";
import { APIService } from "@/services/api.service";

export class ProjectRoutingRuleService extends APIService {
  constructor() {
    super(API_BASE_URL);
  }

  private async unwrap<T>(call: Promise<{ data: T }>): Promise<T> {
    return call
      .then((response) => response?.data)
      .catch((error) => {
        throw { status: error?.response?.status, data: error?.response?.data } as TApiError;
      });
  }

  async list(workspaceSlug: string, projectId: string): Promise<TProjectRoutingRule[]> {
    return this.unwrap(this.get(`/api/workspaces/${workspaceSlug}/projects/${projectId}/routing-rules/`));
  }

  /** Creates a rule; existing work items are left alone. A duplicate gets 409 with the existing rule's id. */
  async create(
    workspaceSlug: string,
    projectId: string,
    data: TProjectRoutingRuleCreate
  ): Promise<TProjectRoutingRule> {
    return this.unwrap(this.post(`/api/workspaces/${workspaceSlug}/projects/${projectId}/routing-rules/`, data));
  }

  /** Turns the rule on or off; turning on an inactive rule gets 400 with the reason under `enabled`. */
  async setEnabled(
    workspaceSlug: string,
    projectId: string,
    ruleId: string,
    enabled: boolean
  ): Promise<TProjectRoutingRule> {
    return this.unwrap(
      this.patch(`/api/workspaces/${workspaceSlug}/projects/${projectId}/routing-rules/${ruleId}/`, { enabled })
    );
  }

  async remove(workspaceSlug: string, projectId: string, ruleId: string): Promise<void> {
    return this.unwrap(this.delete(`/api/workspaces/${workspaceSlug}/projects/${projectId}/routing-rules/${ruleId}/`));
  }
}
