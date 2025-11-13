from rest_framework import permissions


class IsSuperUser(permissions.BasePermission):
    """
    Allows access only to Django super‑users.
    """

    def has_permission(self, request, view):
        return bool(
            request.user and request.user.is_authenticated and request.user.is_superuser
        )
