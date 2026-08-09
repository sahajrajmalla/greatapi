"""Model registration for the admin site.

Registration is explicit and field-level, because the 1.x admin rendered every
column of every registered table -- which meant the users list displayed bcrypt
hashes, and the search box ran ``ILIKE`` across them.

Here, columns are opt-in via ``list_display``/``fields``, and a name that looks
sensitive is redacted even if somebody opts it in by mistake. The safe thing is
the default and the unsafe thing is not reachable by accident.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any, TypeVar

from sqlalchemy import Boolean, Date, DateTime, Float, Integer, Numeric, String, Text, inspect
from sqlalchemy.orm import ColumnProperty

from greatapi.db.base import Base
from greatapi.exceptions import GreatAPIError

__all__ = [
    "REDACTED",
    "FieldSpec",
    "ModelAdmin",
    "format_value",
    "get_registry",
    "humanise",
    "is_sensitive",
    "register",
    "unregister_all",
]

REDACTED = "••••••••"

#: Any column whose name matches is never rendered, searched or edited.
_SENSITIVE_PATTERNS = (
    r"password",
    r"secret",
    r"token",
    r"_key$",
    r"^key$",
    r"hashed",
    r"salt",
    r"credential",
    r"private",
)
_SENSITIVE_RE = re.compile("|".join(_SENSITIVE_PATTERNS), re.IGNORECASE)

M = TypeVar("M", bound=type[Base])


def is_sensitive(name: str) -> bool:
    """True when a column name looks like it holds a credential."""
    return _SENSITIVE_RE.search(name) is not None


@dataclass(frozen=True, slots=True)
class FieldSpec:
    """A column as the admin needs to render and validate it."""

    name: str
    label: str
    input_type: str
    nullable: bool
    readonly: bool
    sensitive: bool
    max_length: int | None = None
    choices: tuple[str, ...] | None = None

    @property
    def required(self) -> bool:
        return not self.nullable and not self.readonly


class ModelAdmin:
    """Declares how one model appears in the admin.

    ::

        @admin.register(Document)
        class DocumentAdmin(admin.ModelAdmin):
            list_display = ("id", "title", "status", "created_at")
            search_fields = ("title",)
            readonly_fields = ("created_at",)
    """

    #: Columns shown in the list view. Empty means "every non-sensitive column".
    list_display: Sequence[str] = ()
    #: Columns the search box looks at. Empty disables search.
    search_fields: Sequence[str] = ()
    #: Columns shown on the edit form. Empty means "every editable column".
    fields: Sequence[str] = ()
    #: Columns rendered but never written.
    readonly_fields: Sequence[str] = ()
    #: Columns hidden everywhere.
    exclude: Sequence[str] = ()
    #: Grouping label in the sidebar.
    app_label: str = ""
    #: Default ordering column; prefix with ``-`` for descending.
    ordering: str = "-id"
    can_create: bool = True
    can_edit: bool = True
    can_delete: bool = True
    page_size: int | None = None

    model: type[Base]

    def __init__(self, model: type[Base]) -> None:
        self.model = model

    # -- identity ---------------------------------------------------------

    @property
    def slug(self) -> str:
        # `__tablename__` is typed loosely on DeclarativeBase, hence the cast.
        return str(self.model.__tablename__).lower()

    @property
    def label(self) -> str:
        return _humanise(self.model.__name__)

    @property
    def group(self) -> str:
        if self.app_label:
            return self.app_label
        # Fall back to the defining package, e.g. `myapp.models` -> `myapp`.
        module: str = getattr(self.model, "__module__", "") or ""
        parts = [part for part in module.split(".") if part not in {"models", "__main__"}]
        return parts[-1] if parts else "application"

    # -- introspection ----------------------------------------------------

    def _columns(self) -> dict[str, Any]:
        mapper = inspect(self.model)
        return {
            prop.key: prop.columns[0]
            for prop in mapper.attrs
            if isinstance(prop, ColumnProperty) and prop.columns
        }

    def visible_field_names(self) -> list[str]:
        """Columns safe to show, honouring ``list_display``/``exclude``."""
        columns = self._columns()
        excluded = set(self.exclude)
        candidates = list(self.list_display) if self.list_display else list(columns)
        return [
            name
            for name in candidates
            if name in columns and name not in excluded and not is_sensitive(name)
        ]

    def editable_field_names(self) -> list[str]:
        columns = self._columns()
        excluded = set(self.exclude) | {"id"}
        candidates = list(self.fields) if self.fields else list(columns)
        return [
            name
            for name in candidates
            if name in columns
            and name not in excluded
            and name not in self.readonly_fields
            and not is_sensitive(name)
        ]

    def searchable_field_names(self) -> list[str]:
        columns = self._columns()
        return [
            name
            for name in self.search_fields
            if name in columns and not is_sensitive(name) and name not in self.exclude
        ]

    def form_fields(self) -> list[FieldSpec]:
        columns = self._columns()
        specs: list[FieldSpec] = []
        for name in self.editable_field_names():
            column = columns[name]
            specs.append(
                FieldSpec(
                    name=name,
                    label=_humanise(name),
                    input_type=_input_type(column),
                    nullable=bool(column.nullable),
                    readonly=False,
                    sensitive=False,
                    max_length=getattr(column.type, "length", None),
                    choices=_choices(column),
                )
            )
        return specs

    def display_value(self, instance: Base, name: str) -> Any:
        """Render one cell, redacting anything credential-shaped."""
        if is_sensitive(name):
            return REDACTED
        return format_value(getattr(instance, name, None))


@dataclass
class _Registry:
    entries: dict[type[Base], ModelAdmin] = field(default_factory=dict)

    def add(self, model: type[Base], model_admin: ModelAdmin) -> None:
        self.entries[model] = model_admin

    def by_group(self) -> dict[str, list[ModelAdmin]]:
        grouped: dict[str, list[ModelAdmin]] = {}
        for model_admin in self.entries.values():
            grouped.setdefault(model_admin.group, []).append(model_admin)
        for group in grouped.values():
            group.sort(key=lambda ma: ma.label)
        return dict(sorted(grouped.items()))

    def find(self, group: str, slug: str) -> ModelAdmin | None:
        for model_admin in self.entries.values():
            if model_admin.group.lower() == group.lower() and model_admin.slug == slug.lower():
                return model_admin
        return None

    def all(self) -> list[ModelAdmin]:
        return list(self.entries.values())


_registry = _Registry()


def get_registry() -> _Registry:
    return _registry


def register(
    model: type[Base] | Iterable[type[Base]],
) -> Callable[[type[ModelAdmin]], type[ModelAdmin]]:
    """Register one or more models with the admin.

    Works as a decorator, to customise the presentation::

        @admin.register(Document)
        class DocumentAdmin(admin.ModelAdmin):
            list_display = ("id", "title")

    and as a plain call, to accept the defaults::

        admin.register(Document)
        admin.register([Document, Comment])

    Both are supported because the model is registered with a default
    :class:`ModelAdmin` immediately; the returned decorator merely replaces it
    when one is actually applied.
    """
    models: list[type[Base]] = [model] if isinstance(model, type) else list(model)
    for candidate in models:
        if not issubclass(candidate, Base):
            raise GreatAPIError(
                f"{candidate!r} is not a GreatAPI model. Models must inherit from greatapi.db.Base."
            )
        _registry.add(candidate, ModelAdmin(candidate))

    def decorator(admin_class: type[ModelAdmin]) -> type[ModelAdmin]:
        if not issubclass(admin_class, ModelAdmin):
            raise GreatAPIError(
                f"{admin_class.__name__} must inherit from greatapi.admin.ModelAdmin."
            )
        for candidate in models:
            _registry.add(candidate, admin_class(candidate))
        return admin_class

    return decorator


def unregister_all() -> None:
    """Empty the registry. Used between tests."""
    _registry.entries.clear()


# -- helpers --------------------------------------------------------------


#: Words with a fixed casing, so `cost_usd` reads "Cost USD" not "Cost Usd",
#: and `latency_ms` reads "Latency ms" rather than shouting a unit symbol.
_SPECIAL_CASE = {
    "id": "ID",
    "api": "API",
    "llm": "LLM",
    "ai": "AI",
    "url": "URL",
    "uri": "URI",
    "usd": "USD",
    "ip": "IP",
    "ms": "ms",
    "csrf": "CSRF",
    "jwt": "JWT",
    "sql": "SQL",
    "ok": "OK",
}

# Split before a capital that starts a new word, but keep runs of capitals
# together, so LLMCall reads "LLM Call" rather than "L L M Call".
_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")


def humanise(name: str) -> str:
    """Turn ``llm_call`` or ``LLMCall`` into a readable label."""
    spaced = _CAMEL_BOUNDARY.sub(" ", name.replace("_", " ")).strip()
    return " ".join(
        _SPECIAL_CASE.get(word.lower(), word[:1].upper() + word[1:]) for word in spaced.split()
    )


_humanise = humanise


def _input_type(column: Any) -> str:
    column_type = column.type
    if isinstance(column_type, Boolean):
        return "checkbox"
    if isinstance(column_type, DateTime):
        return "datetime-local"
    if isinstance(column_type, Date):
        return "date"
    if isinstance(column_type, Integer):
        return "number"
    if isinstance(column_type, Float | Numeric):
        return "number-float"
    if isinstance(column_type, Text):
        return "textarea"
    if isinstance(column_type, String) and (column_type.length or 0) > 255:
        return "textarea"
    return "text"


def format_value(value: Any) -> Any:
    """Make a column value readable in a list or detail view.

    Booleans stay booleans so the template can badge them; everything else is
    rendered here, so a timestamp does not reach the page as
    ``2026-08-09 14:38:45.399992``.
    """
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, float):
        # Costs are small and the fractions matter; trim trailing zeros.
        return f"{value:.6f}".rstrip("0").rstrip(".") or "0"
    if isinstance(value, list | dict):
        return json.dumps(value, default=str)
    return value


def _choices(column: Any) -> tuple[str, ...] | None:
    enum_values = getattr(column.type, "enums", None)
    if enum_values:
        return tuple(enum_values)
    return None
