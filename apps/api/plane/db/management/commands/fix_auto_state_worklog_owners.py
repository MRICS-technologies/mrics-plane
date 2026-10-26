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

from plane.db.models import Issue, IssueActivity, State, User, WorkItemWorklog
from plane.db.models.state import StateGroup
from plane.db.models.time_tracking import activity_instant


class Command(BaseCommand):
    help = "Re-attribute automatic In Progress worklogs to the user who moved the issue into In Progress."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Write changes. Without it the command only reports.")
        parser.add_argument(
            "--tolerance-seconds",
            type=int,
            default=30,
            help="Max gap between a session start and the matching state change (default 30).",
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
        worklogs = list(
            worklogs.order_by("started_at", "id").only(
                "id", "issue_id", "project_id", "logged_by_id", "started_at", "stopped_at", "duration"
            )
        )
        if not worklogs:
            self.stdout.write("No automatic worklogs found.")
            return

        project_ids = {w.project_id for w in worklogs}
        issue_ids = {w.issue_id for w in worklogs}
        started_state_ids = defaultdict(set)
        for state_id, project_id in State.objects.filter(
            project_id__in=project_ids, group=StateGroup.STARTED.value
        ).values_list("id", "project_id"):
            started_state_ids[project_id].add(str(state_id))

        # Candidate session starts: (instant, actor_id, source). Deleted users keep
        # their entry (actor_id None) so a neighbour cannot win by default.
        entries_by_issue = defaultdict(list)
        activities = IssueActivity.objects.filter(issue_id__in=issue_ids, field="state").only(
            "id", "issue_id", "project_id", "actor_id", "old_identifier", "new_identifier", "epoch", "created_at"
        )
        for activity in activities:
            started = started_state_ids.get(activity.project_id, set())
            new_started = activity.new_identifier is not None and str(activity.new_identifier) in started
            old_started = activity.old_identifier is not None and str(activity.old_identifier) in started
            if new_started and not old_started:
                entries_by_issue[activity.issue_id].append(
                    (activity_instant(activity), activity.actor_id, f"activity:{activity.id}")
                )
        # Issues created directly in a STARTED state log no state activity; the
        # creator started that session.
        for issue_id, created_at, created_by_id in Issue.all_objects.filter(id__in=issue_ids).values_list(
            "id", "created_at", "created_by_id"
        ):
            entries_by_issue[issue_id].append((created_at, created_by_id, "issue_created"))

        active_users = set(User.objects.filter(is_active=True).values_list("id", flat=True))
        changes = []
        skipped = defaultdict(list)
        for worklog in worklogs:
            matches = []
            for instant, actor_id, source in entries_by_issue.get(worklog.issue_id, []):
                gap = abs((instant - worklog.started_at).total_seconds())
                if gap > tolerance:
                    continue
                if worklog.stopped_at is not None and instant >= worklog.stopped_at:
                    continue
                matches.append((gap, actor_id, source))
            if not matches:
                skipped["no matching session start"].append(worklog)
                continue
            if len({actor_id for _, actor_id, _ in matches}) > 1:
                skipped["ambiguous: several people started it"].append(worklog)
                continue
            gap, starter_id, source = min(matches, key=lambda m: (m[0], m[2]))
            if starter_id is None:
                skipped["starter user deleted"].append(worklog)
                continue
            if starter_id == worklog.logged_by_id:
                continue
            if starter_id not in active_users:
                skipped["starter user inactive"].append(worklog)
                continue
            changes.append((worklog, starter_id, gap, source))

        emails = dict(
            User.objects.filter(id__in={w.logged_by_id for w, *_ in changes} | {c[1] for c in changes}).values_list(
                "id", "email"
            )
        )
        moved = defaultdict(float)
        writer = csv.writer(self.stdout)
        writer.writerow(
            ["worklog_id", "issue_id", "started_at", "hours", "from_user", "to_user", "gap_seconds", "matched_on"]
        )
        for worklog, starter_id, gap, source in changes:
            hours = float(worklog.duration or 0)
            writer.writerow(
                [
                    worklog.id,
                    worklog.issue_id,
                    worklog.started_at.isoformat(),
                    f"{hours:.4f}",
                    emails.get(worklog.logged_by_id, worklog.logged_by_id),
                    emails.get(starter_id, starter_id),
                    f"{gap:.1f}",
                    source,
                ]
            )
            moved[emails.get(worklog.logged_by_id, str(worklog.logged_by_id))] -= hours
            moved[emails.get(starter_id, str(starter_id))] += hours

        self.stdout.write(f"Scanned {len(worklogs)} automatic worklogs; {len(changes)} to re-attribute.")
        for reason, rows in skipped.items():
            hours = sum(float(w.duration or 0) for w in rows)
            self.stdout.write(f"  left unchanged ({reason}): {len(rows)} sessions, {hours:.2f} h")
            for w in rows:
                self.stdout.write(f"    {w.id} issue={w.issue_id} started_at={w.started_at.isoformat()}")
        for user, hours in sorted(moved.items(), key=lambda item: item[1]):
            self.stdout.write(f"  {user}: {hours:+.2f} h")

        if options["apply"] and changes and not options["backup_csv"]:
            raise CommandError("--apply requires --backup-csv so the change can be rolled back.")

        if options["backup_csv"] and changes:
            with open(options["backup_csv"], "w", newline="") as handle:
                backup = csv.writer(handle)
                backup.writerow(["worklog_id", "old_logged_by_id", "new_logged_by_id"])
                for worklog, starter_id, *_ in changes:
                    backup.writerow([worklog.id, worklog.logged_by_id, starter_id])
            self.stdout.write(f"Rollback file written: {options['backup_csv']}")

        if not options["apply"]:
            self.stdout.write("Dry run only. Re-run with --apply --backup-csv <file> to write these changes.")
            return
        if not changes:
            self.stdout.write("Nothing to apply.")
            return

        applied = 0
        now = timezone.now()
        with transaction.atomic():
            for worklog, starter_id, *_ in changes:
                applied += WorkItemWorklog.objects.filter(pk=worklog.pk, logged_by_id=worklog.logged_by_id).update(
                    logged_by_id=starter_id, updated_at=now
                )
        self.stdout.write(
            self.style.SUCCESS(f"Applied {applied} of {len(changes)} re-attributions at {now.isoformat()}.")
        )
