"""Reusable access-control mixins applied to every class-based view."""

from django.contrib.auth.mixins import AccessMixin
from django.core.exceptions import PermissionDenied


class RoleRequiredMixin(AccessMixin):
    """Anonymous → login redirect; authenticated with a wrong role → 403.

    ``allowed_roles`` empty means "any authenticated user".
    """

    allowed_roles: tuple[str, ...] = ()

    def dispatch(self, request, *args, **kwargs):
        user = request.user
        if not user.is_authenticated:
            return self.handle_no_permission()
        if self.allowed_roles and user.effective_role not in self.allowed_roles:
            raise PermissionDenied("Rôle non autorisé pour cette page.")
        return super().dispatch(request, *args, **kwargs)


def resolve_attr(obj, dotted: str):
    for part in dotted.split("."):
        obj = getattr(obj, part)
    return obj


class OwnerRequiredMixin:
    """Object-level ownership check for SingleObjectMixin views.

    ``owner_fields`` lists dotted paths to users allowed on the object
    (e.g. ``("pme",)`` or ``("sender", "receiver")``). Override
    ``is_owner`` for custom rules. Non-owners get a 403.
    """

    owner_fields: tuple[str, ...] = ("owner",)

    def is_owner(self, obj, user) -> bool:
        return any(resolve_attr(obj, f) == user for f in self.owner_fields)

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        if not self.is_owner(obj, self.request.user):
            raise PermissionDenied("Vous n'êtes pas propriétaire de cette ressource.")
        return obj
