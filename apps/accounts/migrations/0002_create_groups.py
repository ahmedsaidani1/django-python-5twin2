"""Create the PME / Transporteur / Administrateur groups with their model permissions."""

from django.contrib.auth.management import create_permissions
from django.db import migrations

GROUPS = {
    "PME": {
        "shipments.freightrequest": ["add", "change", "delete", "view"],
        "bookings.bookingrequest": ["add", "change", "view"],
        "messaging.message": ["add", "view"],
        "reviews.review": ["add", "view"],
        "trips.trip": ["view"],
        "accounts.companyprofile": ["change", "view"],
        "accounts.report": ["add"],
    },
    "Transporteur": {
        "trips.trip": ["add", "change", "delete", "view"],
        "trips.vehicle": ["add", "change", "delete", "view"],
        "bookings.bookingrequest": ["add", "change", "view"],
        "messaging.message": ["add", "view"],
        "reviews.review": ["view"],
        "shipments.freightrequest": ["view"],
        "accounts.carrierprofile": ["change", "view"],
        "accounts.report": ["add"],
    },
    "Administrateur": "__all__",
}


def create_groups(apps, schema_editor):
    for app_config in apps.get_app_configs():
        app_config.models_module = True
        create_permissions(app_config, apps=apps, verbosity=0)
        app_config.models_module = None
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    for name, spec in GROUPS.items():
        group, _ = Group.objects.get_or_create(name=name)
        if spec == "__all__":
            perms = Permission.objects.filter(
                content_type__app_label__in=[
                    "accounts", "shipments", "trips", "bookings", "messaging", "reviews", "notifications", "core",
                ]
            )
        else:
            perms = []
            for model_label, actions in spec.items():
                app_label, model = model_label.split(".")
                perms += list(
                    Permission.objects.filter(
                        content_type__app_label=app_label,
                        codename__in=[f"{a}_{model}" for a in actions],
                    )
                )
        group.permissions.set(perms)


def remove_groups(apps, schema_editor):
    apps.get_model("auth", "Group").objects.filter(name__in=GROUPS).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0001_initial"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
        ("core", "0001_initial"),
        ("shipments", "0001_initial"),
        ("trips", "0001_initial"),
        ("bookings", "0001_initial"),
        ("messaging", "0001_initial"),
        ("reviews", "0001_initial"),
        ("notifications", "0001_initial"),
    ]

    operations = [migrations.RunPython(create_groups, remove_groups)]
