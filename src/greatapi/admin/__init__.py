"""The admin site.

Register a model to get a list view, search, pagination and an edit form::

    from greatapi import admin

    @admin.register(Document)
    class DocumentAdmin(admin.ModelAdmin):
        list_display = ("id", "title", "created_at")
        search_fields = ("title",)
"""

from __future__ import annotations

__all__ = [
    "FieldSpec",
    "ModelAdmin",
    "build_admin_router",
    "get_registry",
    "is_sensitive",
    "register",
    "unregister_all",
]

from greatapi.admin.registry import (
    FieldSpec,
    ModelAdmin,
    get_registry,
    is_sensitive,
    register,
    unregister_all,
)
from greatapi.admin.router import build_admin_router
