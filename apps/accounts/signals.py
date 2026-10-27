from django.contrib.auth.models import Group
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import User

ROLE_GROUPS = {User.Role.PME: "PME", User.Role.TRANSPORTEUR: "Transporteur", User.Role.ADMIN: "Administrateur"}


@receiver(post_save, sender=User)
def sync_role_group(sender, instance, raw=False, **kwargs):
    """Keep each user in exactly the group matching their role."""
    if raw:
        return
    group = Group.objects.filter(name=ROLE_GROUPS.get(instance.role)).first()
    if group is None:
        return
    others = instance.groups.filter(name__in=ROLE_GROUPS.values()).exclude(pk=group.pk)
    if others.exists():
        instance.groups.remove(*others)
    instance.groups.add(group)
