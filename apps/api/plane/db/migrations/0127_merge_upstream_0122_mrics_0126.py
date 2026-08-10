# Merge the upstream v1.4.1 and MRICS custom migration branches.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("db", "0122_alter_draftissue_assignees_alter_issue_assignees_and_more"),
        ("db", "0126_github_webhook_pr_linking"),
    ]

    operations = []
