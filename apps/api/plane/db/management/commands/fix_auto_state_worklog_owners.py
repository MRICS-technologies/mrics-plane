# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Re-attribute automatic In Progress worklogs to the user who started them.

Before the attribution fix, closing an automatic STARTED-state session handed
the whole session to whoever moved the issue out of STARTED. This command finds
each automatic session's real starter from the state activity that opened it
and moves the session back to that user.

Dry-run by default. Pass ``--apply`` to write the changes.
"""

import csv
from collections import defaultdict

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date

from plane.db.models import IssueActivity, State, User, WorkItemWorklog
from plane.db.models.state import StateGroup
from plane.db.models.time_tracking import activity_instant


class Command(BaseCommand):
    help = "Re-attribute automatic In Progress worklogs to the user who moved the issue into In Progress."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Write changes. Without it the command only reports.")
        parser.add_argument(
            "--tolerance-seconds",
            type=int,
            default=300,
            help="Max gap between a session start and the matching state change (default 300).",
        )
        parser.add_argument("--since", type=str, default=None, help="Only sessions started on/after YYYY-MM-DD.")
        parser.add_argument(
            "--backup-csv",
            type=str,
            default=None,
            help="Write worklog_id,old_logged_by_id,new_logged_by_id for every change (rollback file).",
        )

    def handle(self, *args, **options):
        tolerance = options["tolerance_seconds"]
        if tolerance <= 0:
            raise CommandError("--tolerance-seconds must be positive")

        worklogs = WorkItemWorklog.objects.filter(
            source=WorkItemWorklog.Source.AUTO_STATE,
            started_at__isnull=False,
        )
        if options["since"]:
            since = parse_date(options["since"])
            if since is None:
                raise CommandError("--since must be YYYY-MM-DD")
            worklogs = worklogs.filter(started_at__date__gte=since)
        worklogs = list(worklogs.only("id", "issue_id", "project_id", "logged_by_id", "started_at", "duration"))
        if not worklogs:
            self.stdout.write("No automatic worklogs found.")
            return

        project_ids = {w.project_id for w in worklogs}
        started_state_ids = defaultdict(set)
        for state_id, project_id in State.objects.filter(
            project_id__in=project_ids, group=StateGroup.STARTED.value
        ).values_list("id", "project_id"):
            started_state_ids[project_id].add(str(state_id))

        entries_by_issue = defaultdict(list)
        activities = IssueActivity.objects.filter(
            issue_id__in={w.issue_id for w in worklogs},
            field="state",
            actor_id__isnull=False,
        ).only("id", "issue_id", "project_id", "actor_id", "old_identifier", "new_identifier", "epoch", "created_at")
        for activity in activities:
            started = started_state_ids.get(activity.project_id, set())
            new_started = activity.new_identifier is not None and str(activity.new_identifier) in started
            old_started = activity.old_identifier is not None and str(activity.old_identifier) in started
            if new_started and not old_started:
                entries_by_issue[activity.issue_id].append((activity_instant(activity), activity.actor_id))

        valid_users = set(User.objects.values_list("id", flat=True))
        changes = []
        unmatched = 0
        for worklog in worklogs:
            best = None
            for instant, actor_id in entries_by_issue.get(worklog.issue_id, []):
                gap = abs((instant - worklog.started_at).total_seconds())
                if gap <= tolerance and (best is None or gap < best[0]):
                    best = (gap, actor_id)
            if best is None:
                unmatched += 1
                continue
            starter_id = best[1]
            if starter_id == worklog.logged_by_id or starter_id not in valid_users:
                continue
            changes.append((worklog, starter_id))

        emails = dict(
            User.objects.filter(id__in={w.logged_by_id for w, _ in changes} | {s for _, s in changes}).values_list(
                "id", "email"
            )
        )
        moved = defaultdict(float)
        writer = csv.writer(self.stdout)
        writer.writerow(["worklog_id", "issue_id", "started_at", "hours", "from_user", "to_user"])
        for worklog, starter_id in changes:
            hours = float(worklog.duration or 0)
            writer.writerow(
                [
                    worklog.id,
                    worklog.issue_id,
                    worklog.started_at.isoformat(),
                    f"{hours:.4f}",
                    emails.get(worklog.logged_by_id, worklog.logged_by_id),
                    emails.get(starter_id, starter_id),
                ]
            )
            moved[emails.get(worklog.logged_by_id, str(worklog.logged_by_id))] -= hours
            moved[emails.get(starter_id, str(starter_id))] += hours

        self.stdout.write(
            f"Scanned {len(worklogs)} automatic worklogs; {len(changes)} to re-attribute; "
            f"{unmatched} without a matching state change (left unchanged)."
        )
        for user, hours in sorted(moved.items(), key=lambda item: item[1]):
            self.stdout.write(f"  {user}: {hours:+.2f} h")

        if options["backup_csv"] and changes:
            with open(options["backup_csv"], "w", newline="") as handle:
                backup = csv.writer(handle)
                backup.writerow(["worklog_id", "old_logged_by_id", "new_logged_by_id"])
                for worklog, starter_id in changes:
                    backup.writerow([worklog.id, worklog.logged_by_id, starter_id])
            self.stdout.write(f"Rollback file written: {options['backup_csv']}")

        if not options["apply"]:
            self.stdout.write("Dry run only. Re-run with --apply to write these changes.")
            return

        with transaction.atomic():
            for worklog, starter_id in changes:
                WorkItemWorklog.objects.filter(pk=worklog.pk, logged_by_id=worklog.logged_by_id).update(
                    logged_by_id=starter_id
                )
        applied_at = timezone.now().isoformat()
        self.stdout.write(self.style.SUCCESS(f"Applied {len(changes)} re-attributions at {applied_at}."))
