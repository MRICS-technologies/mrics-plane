# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import re
from rest_framework.response import Response
from rest_framework import status
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any
from django.db.models import QuerySet, Q, Count, DecimalField, Sum
from django.http import HttpRequest
from django.db.models.functions import Coalesce, TruncMonth
from django.utils import timezone
from datetime import datetime, time, timedelta
from plane.app.views.base import BaseAPIView
from plane.app.permissions import ROLE, allow_permission
from plane.db.models import (
    Project,
    Issue,
    Cycle,
    Module,
    CycleIssue,
    ModuleIssue,
    IssueAssignee,
    ProjectMember,
    WorkItemWorklog,
)
from django.db import models
from django.db.models import F, Case, When, Value
from django.db.models.functions import Concat
from plane.utils.build_chart import build_analytics_chart
from plane.utils.date_utils import (
    get_analytics_filters,
)


class ProjectAdvanceAnalyticsBaseView(BaseAPIView):
    def initialize_workspace(self, slug: str, type: str) -> None:
        self._workspace_slug = slug
        self.filters = get_analytics_filters(
            slug=slug,
            type=type,
            user=self.request.user,
            date_filter=self.request.GET.get("date_filter", None),
            project_ids=self.request.GET.get("project_ids", None),
        )


class ProjectAdvanceAnalyticsEndpoint(ProjectAdvanceAnalyticsBaseView):
    def get_filtered_counts(self, queryset: QuerySet) -> Dict[str, int]:
        def get_filtered_count() -> int:
            if self.filters["analytics_date_range"]:
                return queryset.filter(
                    created_at__gte=self.filters["analytics_date_range"]["current"]["gte"],
                    created_at__lte=self.filters["analytics_date_range"]["current"]["lte"],
                ).count()
            return queryset.count()

        return {
            "count": get_filtered_count(),
        }

    def get_work_items_stats(self, project_id, cycle_id=None, module_id=None) -> Dict[str, Dict[str, int]]:
        """
        Returns work item stats for the workspace, or filtered by cycle_id or module_id if provided.
        """
        base_queryset = None
        if cycle_id is not None:
            cycle_issues = CycleIssue.objects.filter(**self.filters["base_filters"], cycle_id=cycle_id).values_list(
                "issue_id", flat=True
            )
            base_queryset = Issue.issue_objects.filter(id__in=cycle_issues)
        elif module_id is not None:
            module_issues = ModuleIssue.objects.filter(**self.filters["base_filters"], module_id=module_id).values_list(
                "issue_id", flat=True
            )
            base_queryset = Issue.issue_objects.filter(id__in=module_issues)
        else:
            base_queryset = Issue.issue_objects.filter(**self.filters["base_filters"], project_id=project_id)

        return {
            "total_work_items": self.get_filtered_counts(base_queryset),
            "started_work_items": self.get_filtered_counts(base_queryset.filter(state__group="started")),
            "backlog_work_items": self.get_filtered_counts(base_queryset.filter(state__group="backlog")),
            "un_started_work_items": self.get_filtered_counts(base_queryset.filter(state__group="unstarted")),
            "completed_work_items": self.get_filtered_counts(base_queryset.filter(state__group="completed")),
        }

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER])
    def get(self, request: HttpRequest, slug: str, project_id: str) -> Response:
        self.initialize_workspace(slug, type="analytics")

        # Optionally accept cycle_id or module_id as query params
        cycle_id = request.GET.get("cycle_id", None)
        module_id = request.GET.get("module_id", None)
        return Response(
            self.get_work_items_stats(cycle_id=cycle_id, module_id=module_id, project_id=project_id),
            status=status.HTTP_200_OK,
        )


class ProjectAdvanceAnalyticsStatsEndpoint(ProjectAdvanceAnalyticsBaseView):
    def get_project_issues_stats(self) -> QuerySet:
        # Get the base queryset with workspace and project filters
        base_queryset = Issue.issue_objects.filter(**self.filters["base_filters"])

        # Apply date range filter if available
        if self.filters["chart_period_range"]:
            start_date, end_date = self.filters["chart_period_range"]
            base_queryset = base_queryset.filter(created_at__date__gte=start_date, created_at__date__lte=end_date)

        return (
            base_queryset.values("project_id", "project__name")
            .annotate(
                cancelled_work_items=Count("id", filter=Q(state__group="cancelled")),
                completed_work_items=Count("id", filter=Q(state__group="completed")),
                backlog_work_items=Count("id", filter=Q(state__group="backlog")),
                un_started_work_items=Count("id", filter=Q(state__group="unstarted")),
                started_work_items=Count("id", filter=Q(state__group="started")),
            )
            .order_by("project_id")
        )

    def get_work_items_stats(self, project_id, cycle_id=None, module_id=None) -> Dict[str, Dict[str, int]]:
        base_queryset = None
        if cycle_id is not None:
            cycle_issues = CycleIssue.objects.filter(**self.filters["base_filters"], cycle_id=cycle_id).values_list(
                "issue_id", flat=True
            )
            base_queryset = Issue.issue_objects.filter(id__in=cycle_issues)
        elif module_id is not None:
            module_issues = ModuleIssue.objects.filter(**self.filters["base_filters"], module_id=module_id).values_list(
                "issue_id", flat=True
            )
            base_queryset = Issue.issue_objects.filter(id__in=module_issues)
        else:
            base_queryset = Issue.issue_objects.filter(**self.filters["base_filters"], project_id=project_id)
        return (
            base_queryset.annotate(display_name=F("assignees__display_name"))
            .annotate(assignee_id=F("assignees__id"))
            .annotate(avatar=F("assignees__avatar"))
            .annotate(
                avatar_url=Case(
                    # If `avatar_asset` exists, use it to generate the asset URL
                    When(
                        assignees__avatar_asset__isnull=False,
                        then=Concat(
                            Value("/api/assets/v2/static/"),
                            "assignees__avatar_asset",  # Assuming avatar_asset has an id or relevant field
                            Value("/"),
                        ),
                    ),
                    # If `avatar_asset` is None, fall back to using `avatar` field directly
                    When(assignees__avatar_asset__isnull=True, then="assignees__avatar"),
                    default=Value(None),
                    output_field=models.CharField(),
                )
            )
            .values("display_name", "assignee_id", "avatar_url")
            .annotate(
                cancelled_work_items=Count("id", filter=Q(state__group="cancelled"), distinct=True),
                completed_work_items=Count("id", filter=Q(state__group="completed"), distinct=True),
                backlog_work_items=Count("id", filter=Q(state__group="backlog"), distinct=True),
                un_started_work_items=Count("id", filter=Q(state__group="unstarted"), distinct=True),
                started_work_items=Count("id", filter=Q(state__group="started"), distinct=True),
            )
            .order_by("display_name")
        )

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER])
    def get(self, request: HttpRequest, slug: str, project_id: str) -> Response:
        self.initialize_workspace(slug, type="chart")
        type = request.GET.get("type", "work-items")

        if type == "work-items":
            # Optionally accept cycle_id or module_id as query params
            cycle_id = request.GET.get("cycle_id", None)
            module_id = request.GET.get("module_id", None)
            return Response(
                self.get_work_items_stats(project_id=project_id, cycle_id=cycle_id, module_id=module_id),
                status=status.HTTP_200_OK,
            )

        return Response({"message": "Invalid type"}, status=status.HTTP_400_BAD_REQUEST)


def _hours_to_seconds(hours: Decimal | None) -> int:
    if hours is None:
        return 0
    return int((hours * Decimal("3600")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _parse_contributor_date_range(request: HttpRequest):
    """Parse optional start_date/end_date query params (inclusive ISO YYYY-MM-DD).

    Returns (start_date, end_date, error_response). Both dates are None for
    all-time scope; error_response is a 400 Response when validation fails.
    """
    start_raw = request.GET.get("start_date")
    end_raw = request.GET.get("end_date")
    if start_raw is None and end_raw is None:
        return None, None, None
    if not start_raw or not end_raw:
        return None, None, Response(
            {"error": "start_date and end_date must both be provided together."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    iso_date_re = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    if not iso_date_re.match(start_raw) or not iso_date_re.match(end_raw):
        return None, None, Response(
            {"error": "start_date and end_date must be valid ISO dates (YYYY-MM-DD)."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    try:
        start_date = datetime.strptime(start_raw, "%Y-%m-%d").date()
        end_date = datetime.strptime(end_raw, "%Y-%m-%d").date()
    except ValueError:
        return None, None, Response(
            {"error": "start_date and end_date must be valid ISO dates (YYYY-MM-DD)."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if start_date > end_date:
        return None, None, Response(
            {"error": "start_date must not be after end_date."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return start_date, end_date, None


class ProjectContributorAnalyticsEndpoint(ProjectAdvanceAnalyticsBaseView):
    """Project/workspace contributor output and time totals.

    Task counts are attributed to current issue assignees. Time is attributed to
    the worklog owner (`logged_by`), which keeps manual/timer and automatic state
    duration accounting explicit rather than guessing from current assignment.
    """

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER], level="WORKSPACE")
    def get(self, request: HttpRequest, slug: str) -> Response:
        self.initialize_workspace(slug, type="chart")

        start_date, end_date, error_response = _parse_contributor_date_range(request)
        if error_response is not None:
            return error_response

        range_window = None
        if start_date is not None:
            local_tz = timezone.get_current_timezone()
            range_window = (
                timezone.make_aware(datetime.combine(start_date, time.min), local_tz),
                timezone.make_aware(datetime.combine(end_date + timedelta(days=1), time.min), local_tz),
            )

        project_ids = list(
            Project.objects.filter(**self.filters["project_filters"]).values_list("id", flat=True)
        )
        project_members = (
            ProjectMember.objects.filter(
                project_id__in=project_ids,
                is_active=True,
                member__is_active=True,
            )
            .select_related("member", "member__avatar_asset")
            .order_by("member__display_name", "member__email")
        )

        contributors = {}
        for project_member in project_members:
            member = project_member.member
            if member is None or member.id in contributors:
                continue
            contributors[member.id] = {
                "member_id": str(member.id),
                "display_name": member.display_name or member.email or "Unknown member",
                "email": member.email or "",
                "avatar_url": member.avatar_url,
                "assigned_work_items": 0,
                "completed_work_items": 0,
                "started_work_items": 0,
                "completion_rate": 0.0,
                "auto_tracked_seconds": 0,
                "logged_work_seconds": 0,
                "total_tracked_seconds": 0,
                "auto_sessions": 0,
                "logged_worklogs": 0,
            }

        completion_denominators = {}
        member_ids = list(contributors.keys())
        if member_ids:
            assignee_filters = {
                "project_id__in": project_ids,
                "assignee_id__in": member_ids,
                "issue__deleted_at__isnull": True,
            }
            if start_date is not None:
                assignee_filters["issue__created_at__date__gte"] = start_date
                assignee_filters["issue__created_at__date__lte"] = end_date

            assignment_stats = (
                IssueAssignee.objects.filter(**assignee_filters)
                .exclude(issue__state__group="cancelled")
                .values("assignee_id")
                .annotate(
                    assigned_work_items=Count("issue_id", distinct=True),
                    completed_work_items=Count(
                        "issue_id",
                        filter=Q(issue__state__group="completed"),
                        distinct=True,
                    ),
                    started_work_items=Count(
                        "issue_id",
                        filter=Q(issue__state__group="started"),
                        distinct=True,
                    ),
                    unstarted_work_items=Count(
                        "issue_id",
                        filter=Q(issue__state__group="unstarted"),
                        distinct=True,
                    ),
                    backlog_work_items=Count(
                        "issue_id",
                        filter=Q(issue__state__group="backlog"),
                        distinct=True,
                    ),
                )
            )
            for stat in assignment_stats:
                contributor = contributors.get(stat["assignee_id"])
                if contributor is None:
                    continue
                contributor.update(
                    assigned_work_items=stat["assigned_work_items"],
                    completed_work_items=stat["completed_work_items"],
                    started_work_items=stat["started_work_items"],
                )
                completion_denominators[stat["assignee_id"]] = (
                    stat["completed_work_items"]
                    + stat["started_work_items"]
                    + stat["unstarted_work_items"]
                    + stat["backlog_work_items"]
                )

            duration_field = DecimalField(max_digits=16, decimal_places=4)
            if range_window is not None:
                window_start, window_end = range_window
                completed_auto_rows = WorkItemWorklog.objects.filter(
                    project_id__in=project_ids,
                    logged_by_id__in=member_ids,
                    source=WorkItemWorklog.Source.AUTO_STATE,
                    stopped_at__isnull=False,
                    started_at__lt=window_end,
                    stopped_at__gt=window_start,
                ).values("logged_by_id", "started_at", "stopped_at")
                for row in completed_auto_rows:
                    contributor = contributors.get(row["logged_by_id"])
                    if contributor is None:
                        continue
                    overlap_start = max(row["started_at"], window_start)
                    overlap_end = min(row["stopped_at"], window_end)
                    contributor["auto_tracked_seconds"] += int((overlap_end - overlap_start).total_seconds())
                    contributor["auto_sessions"] += 1
            else:
                completed_auto_stats = (
                    WorkItemWorklog.objects.filter(
                        project_id__in=project_ids,
                        logged_by_id__in=member_ids,
                        source=WorkItemWorklog.Source.AUTO_STATE,
                        stopped_at__isnull=False,
                    )
                    .values("logged_by_id")
                    .annotate(
                        duration_hours=Coalesce(
                            Sum("duration"),
                            Value(Decimal("0")),
                            output_field=duration_field,
                        ),
                        session_count=Count("id"),
                    )
                )
                for stat in completed_auto_stats:
                    contributor = contributors.get(stat["logged_by_id"])
                    if contributor is None:
                        continue
                    contributor["auto_tracked_seconds"] += _hours_to_seconds(stat["duration_hours"])
                    contributor["auto_sessions"] += stat["session_count"]

            now = timezone.now()
            if range_window is not None:
                window_start, window_end = range_window
                open_effective_end = min(now, window_end)
                open_auto_worklogs = WorkItemWorklog.objects.filter(
                    project_id__in=project_ids,
                    logged_by_id__in=member_ids,
                    source=WorkItemWorklog.Source.AUTO_STATE,
                    stopped_at__isnull=True,
                    started_at__isnull=False,
                    started_at__lt=open_effective_end,
                ).values("logged_by_id", "started_at")
                for worklog in open_auto_worklogs:
                    contributor = contributors.get(worklog["logged_by_id"])
                    if contributor is None:
                        continue
                    overlap_start = max(worklog["started_at"], window_start)
                    overlap_seconds = (open_effective_end - overlap_start).total_seconds()
                    if overlap_seconds <= 0:
                        continue
                    contributor["auto_tracked_seconds"] += int(overlap_seconds)
                    contributor["auto_sessions"] += 1
            else:
                open_auto_worklogs = WorkItemWorklog.objects.filter(
                    project_id__in=project_ids,
                    logged_by_id__in=member_ids,
                    source=WorkItemWorklog.Source.AUTO_STATE,
                    stopped_at__isnull=True,
                    started_at__isnull=False,
                ).values("logged_by_id", "started_at")
                for worklog in open_auto_worklogs:
                    contributor = contributors.get(worklog["logged_by_id"])
                    if contributor is None:
                        continue
                    contributor["auto_tracked_seconds"] += max(
                        int((now - worklog["started_at"]).total_seconds()), 0
                    )
                    contributor["auto_sessions"] += 1

            logged_work_filters = {
                "project_id__in": project_ids,
                "logged_by_id__in": member_ids,
                "source__in": [
                    WorkItemWorklog.Source.MANUAL,
                    WorkItemWorklog.Source.TIMER,
                    WorkItemWorklog.Source.IMPORT,
                ],
            }
            if range_window is not None:
                logged_work_filters["date__gte"] = start_date
                logged_work_filters["date__lte"] = end_date

            logged_work_stats = (
                WorkItemWorklog.objects.filter(**logged_work_filters)
                .values("logged_by_id")
                .annotate(
                    duration_hours=Coalesce(
                        Sum("duration"),
                        Value(Decimal("0")),
                        output_field=duration_field,
                    ),
                    worklog_count=Count("id"),
                )
            )
            for stat in logged_work_stats:
                contributor = contributors.get(stat["logged_by_id"])
                if contributor is None:
                    continue
                contributor["logged_work_seconds"] = _hours_to_seconds(stat["duration_hours"])
                contributor["logged_worklogs"] = stat["worklog_count"]

        contributor_rows = []
        for member_id, contributor in contributors.items():
            completed = contributor["completed_work_items"]
            denominator = completion_denominators.get(member_id, 0)
            contributor["completion_rate"] = round((completed / denominator) * 100, 1) if denominator else 0.0
            contributor["total_tracked_seconds"] = (
                contributor["auto_tracked_seconds"] + contributor["logged_work_seconds"]
            )
            contributor_rows.append(contributor)

        contributor_rows.sort(key=lambda item: item["display_name"].lower())

        issues = Issue.issue_objects.filter(**self.filters["base_filters"]).exclude(state__group="cancelled")
        if start_date is not None:
            issues = issues.filter(created_at__date__gte=start_date, created_at__date__lte=end_date)
        issues = issues.distinct()

        return Response(
            {
                "summary": {
                    "project_count": len(project_ids),
                    "member_count": len(contributor_rows),
                    "total_work_items": issues.count(),
                    "completed_work_items": issues.filter(state__group="completed").count(),
                    "started_work_items": issues.filter(state__group="started").count(),
                    "auto_tracked_seconds": sum(
                        item["auto_tracked_seconds"] for item in contributor_rows
                    ),
                    "logged_work_seconds": sum(
                        item["logged_work_seconds"] for item in contributor_rows
                    ),
                    "total_tracked_seconds": sum(
                        item["total_tracked_seconds"] for item in contributor_rows
                    ),
                },
                "contributors": contributor_rows,
                "attribution": {
                    "task_counts": "current_assignees",
                    "time": "worklog_owner",
                    "scope": "date_range" if range_window is not None else "all_time",
                    "start_date": start_date.isoformat() if start_date is not None else None,
                    "end_date": end_date.isoformat() if end_date is not None else None,
                    "task_basis": "issue_created_at",
                    "time_basis": "worklog_date_or_session_overlap",
                },
            },
            status=status.HTTP_200_OK,
        )


class ProjectAdvanceAnalyticsChartEndpoint(ProjectAdvanceAnalyticsBaseView):
    def work_item_completion_chart(self, project_id, cycle_id=None, module_id=None) -> Dict[str, Any]:
        # Get the base queryset
        queryset = (
            Issue.issue_objects.filter(**self.filters["base_filters"])
            .filter(project_id=project_id)
            .select_related("workspace", "state", "parent")
            .prefetch_related("assignees", "labels", "issue_module__module", "issue_cycle__cycle")
        )

        if cycle_id is not None:
            cycle_issues = CycleIssue.objects.filter(**self.filters["base_filters"], cycle_id=cycle_id).values_list(
                "issue_id", flat=True
            )
            cycle = Cycle.objects.filter(id=cycle_id).first()
            if cycle and cycle.start_date:
                start_date = cycle.start_date.date()
                end_date = cycle.end_date.date()
            else:
                return {"data": [], "schema": {}}
            queryset = cycle_issues

        elif module_id is not None:
            module_issues = ModuleIssue.objects.filter(**self.filters["base_filters"], module_id=module_id).values_list(
                "issue_id", flat=True
            )
            module = Module.objects.filter(id=module_id).first()
            if module and module.start_date:
                start_date = module.start_date
                end_date = module.target_date
            else:
                return {"data": [], "schema": {}}
            queryset = module_issues

        else:
            project = Project.objects.filter(id=project_id).first()
            if project.created_at:
                start_date = project.created_at.date().replace(day=1)
            else:
                return {"data": [], "schema": {}}

        if cycle_id or module_id:
            # Get daily stats with optimized query
            daily_stats = (
                queryset.values("created_at__date")
                .annotate(
                    created_count=Count("id"),
                    completed_count=Count("id", filter=Q(issue__state__group="completed")),
                )
                .order_by("created_at__date")
            )

            # Create a dictionary of existing stats with summed counts
            stats_dict = {
                stat["created_at__date"].strftime("%Y-%m-%d"): {
                    "created_count": stat["created_count"],
                    "completed_count": stat["completed_count"],
                }
                for stat in daily_stats
            }

            # Generate data for all days in the range
            data = []
            current_date = start_date
            while current_date <= end_date:
                date_str = current_date.strftime("%Y-%m-%d")
                stats = stats_dict.get(date_str, {"created_count": 0, "completed_count": 0})
                data.append(
                    {
                        "key": date_str,
                        "name": date_str,
                        "count": stats["created_count"] + stats["completed_count"],
                        "completed_issues": stats["completed_count"],
                        "created_issues": stats["created_count"],
                    }
                )
                current_date += timedelta(days=1)
        else:
            # Apply date range filter if available
            if self.filters["chart_period_range"]:
                start_date, end_date = self.filters["chart_period_range"]
                queryset = queryset.filter(created_at__date__gte=start_date, created_at__date__lte=end_date)

            # Annotate by month and count
            monthly_stats = (
                queryset.annotate(month=TruncMonth("created_at"))
                .values("month")
                .annotate(
                    created_count=Count("id"),
                    completed_count=Count("id", filter=Q(state__group="completed")),
                )
                .order_by("month")
            )

            # Create dictionary of month -> counts
            stats_dict = {
                stat["month"].strftime("%Y-%m-%d"): {
                    "created_count": stat["created_count"],
                    "completed_count": stat["completed_count"],
                }
                for stat in monthly_stats
            }

            # Generate monthly data (ensure months with 0 count are included)
            data = []
            # include the current date at the end
            end_date = timezone.now().date()
            last_month = end_date.replace(day=1)
            current_month = start_date

            while current_month <= last_month:
                date_str = current_month.strftime("%Y-%m-%d")
                stats = stats_dict.get(date_str, {"created_count": 0, "completed_count": 0})
                data.append(
                    {
                        "key": date_str,
                        "name": date_str,
                        "count": stats["created_count"],
                        "completed_issues": stats["completed_count"],
                        "created_issues": stats["created_count"],
                    }
                )
                # Move to next month
                if current_month.month == 12:
                    current_month = current_month.replace(year=current_month.year + 1, month=1)
                else:
                    current_month = current_month.replace(month=current_month.month + 1)

        schema = {
            "completed_issues": "completed_issues",
            "created_issues": "created_issues",
        }

        return {"data": data, "schema": schema}

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST])
    def get(self, request: HttpRequest, slug: str, project_id: str) -> Response:
        self.initialize_workspace(slug, type="chart")
        type = request.GET.get("type", "projects")
        group_by = request.GET.get("group_by", None)
        x_axis = request.GET.get("x_axis", "PRIORITY")
        cycle_id = request.GET.get("cycle_id", None)
        module_id = request.GET.get("module_id", None)

        if type == "custom-work-items":
            queryset = (
                Issue.issue_objects.filter(**self.filters["base_filters"])
                .filter(project_id=project_id)
                .select_related("workspace", "state", "parent")
                .prefetch_related("assignees", "labels", "issue_module__module", "issue_cycle__cycle")
            )

            # Apply cycle/module filters if present
            if cycle_id is not None:
                cycle_issues = CycleIssue.objects.filter(**self.filters["base_filters"], cycle_id=cycle_id).values_list(
                    "issue_id", flat=True
                )
                queryset = queryset.filter(id__in=cycle_issues)

            elif module_id is not None:
                module_issues = ModuleIssue.objects.filter(
                    **self.filters["base_filters"], module_id=module_id
                ).values_list("issue_id", flat=True)
                queryset = queryset.filter(id__in=module_issues)

            # Apply date range filter if available
            if self.filters["chart_period_range"]:
                start_date, end_date = self.filters["chart_period_range"]
                queryset = queryset.filter(created_at__date__gte=start_date, created_at__date__lte=end_date)

            return Response(
                build_analytics_chart(queryset, x_axis, group_by),
                status=status.HTTP_200_OK,
            )

        elif type == "work-items":
            # Optionally accept cycle_id or module_id as query params
            cycle_id = request.GET.get("cycle_id", None)
            module_id = request.GET.get("module_id", None)

            return Response(
                self.work_item_completion_chart(project_id=project_id, cycle_id=cycle_id, module_id=module_id),
                status=status.HTTP_200_OK,
            )

        return Response({"message": "Invalid type"}, status=status.HTTP_400_BAD_REQUEST)
