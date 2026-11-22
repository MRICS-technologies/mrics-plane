# Merge the upstream v1.5.0 and MRICS custom migration branches.

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("db", "0125_reset_project_deploy_board_identity"),
        ("db", "0130_issuegitlink_pr_link_per_issue"),
    ]

    operations = []
