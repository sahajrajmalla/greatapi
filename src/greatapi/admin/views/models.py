"""Generic CRUD over any registered model.

Writes are restricted to the columns a :class:`~greatapi.admin.ModelAdmin`
declares editable. That is the fix for 1.x's ``/admin/change_value``, which
copied every posted field onto the record -- letting any signed-in user set
``is_admin=true`` on themselves, or overwrite ``password`` with plaintext.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Form, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import String, cast, func, or_, select
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import Response

from greatapi.admin.registry import FieldSpec, ModelAdmin, get_registry, humanise
from greatapi.admin.templating import flash_url, paginate, render
from greatapi.conf.settings import get_settings
from greatapi.db.base import Base
from greatapi.db.models import AuditAction, AuditLog, User
from greatapi.security.dependencies import AdminUser, DbSession
from greatapi.security.passwords import PasswordPolicyError, hash_password, validate_password

__all__ = ["models_router"]

models_router = APIRouter(prefix="/model", include_in_schema=False)


def _lookup(group: str, slug: str) -> ModelAdmin:
    model_admin = get_registry().find(group, slug)
    if model_admin is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such model is registered.")
    return model_admin


def _base_url(model_admin: ModelAdmin) -> str:
    settings = get_settings()
    return f"{settings.admin_path}/model/{model_admin.group}/{model_admin.slug}"


@models_router.get("/{group}/{slug}")
async def list_view(
    request: Request,
    session: DbSession,
    user: AdminUser,
    group: str,
    slug: str,
    page: int = Query(1, ge=1),
    q: str = Query("", max_length=200),
    sort: str = Query("", max_length=64),
    direction: str = Query("", alias="dir", pattern="^(asc|desc)?$"),
) -> Response:
    model_admin = _lookup(group, slug)
    settings = get_settings()
    size = model_admin.page_size or settings.admin_page_size

    columns = model_admin.visible_field_names()
    query = select(model_admin.model)

    searchable = model_admin.searchable_field_names()
    if q and searchable:
        # Only the columns the ModelAdmin nominates are searched. 1.x cast every
        # column to text and matched against all of them, password hashes included.
        query = query.where(
            or_(
                *(
                    cast(getattr(model_admin.model, name), String).ilike(f"%{q}%")
                    for name in searchable
                )
            )
        )

    total = await session.scalar(select(func.count()).select_from(query.subquery()))

    # `sort` comes from the query string, so it is only honoured when it names a
    # column already visible on this page -- otherwise it would be a way to
    # order by, and thereby infer, a redacted one.
    sort_column, descending = model_admin.ordering.lstrip("-"), model_admin.ordering.startswith("-")
    if sort and sort in columns:
        sort_column, descending = sort, direction == "desc"

    if hasattr(model_admin.model, sort_column):
        attribute = getattr(model_admin.model, sort_column)
        query = query.order_by(attribute.desc() if descending else attribute.asc())

    rows = list((await session.execute(query.offset((page - 1) * size).limit(size))).scalars())

    return render(
        request,
        "model_list.html",
        {
            "model_admin": model_admin,
            "columns": columns,
            "headers": [_label(name) for name in columns],
            "page": paginate(rows, int(total or 0), page, size),
            "query": q,
            "searchable": bool(searchable),
            "base_url": _base_url(model_admin),
            "sort": sort_column,
            "direction": "desc" if descending else "asc",
        },
        user=user,
        active=f"model:{model_admin.group}:{model_admin.slug}",
    )


@models_router.get("/{group}/{slug}/new")
async def create_form(request: Request, user: AdminUser, group: str, slug: str) -> Response:
    model_admin = _lookup(group, slug)
    _assert_creatable(model_admin)
    return render(
        request,
        "model_form.html",
        {
            "model_admin": model_admin,
            "fields": model_admin.form_fields(),
            "instance": None,
            "values": {},
            "errors": {},
            "base_url": _base_url(model_admin),
        },
        user=user,
        active=f"model:{model_admin.group}:{model_admin.slug}",
    )


@models_router.post("/{group}/{slug}/new")
async def create_submit(
    request: Request, session: DbSession, user: AdminUser, group: str, slug: str
) -> Response:
    model_admin = _lookup(group, slug)
    _assert_creatable(model_admin)

    form = await request.form()
    values, errors = _read_form(model_admin.form_fields(), form)
    if errors:
        return _form_with_errors(request, user, model_admin, None, values, errors)

    instance = model_admin.model(**values)
    session.add(instance)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        user, _ = await _recover(session, user, None)
        return _form_with_errors(
            request, user, model_admin, None, values, {"__all__": _integrity_message(exc)}
        )

    await session.refresh(instance)
    await _audit(session, user, AuditAction.create, model_admin, instance)
    return RedirectResponse(
        flash_url(_base_url(model_admin), "created"), status_code=status.HTTP_303_SEE_OTHER
    )


@models_router.get("/{group}/{slug}/{pk}")
async def edit_form(
    request: Request, session: DbSession, user: AdminUser, group: str, slug: str, pk: str
) -> Response:
    model_admin = _lookup(group, slug)
    instance = await _get_or_404(session, model_admin, pk)
    fields = model_admin.form_fields()
    return render(
        request,
        "model_form.html",
        {
            "model_admin": model_admin,
            "fields": fields,
            "instance": instance,
            "values": {spec.name: getattr(instance, spec.name, None) for spec in fields},
            "readonly": [
                (_label(name), model_admin.display_value(instance, name))
                for name in model_admin.readonly_fields
            ],
            "errors": {},
            "base_url": _base_url(model_admin),
            "supports_password": isinstance(instance, User),
        },
        user=user,
        active=f"model:{model_admin.group}:{model_admin.slug}",
    )


@models_router.post("/{group}/{slug}/{pk}")
async def edit_submit(
    request: Request, session: DbSession, user: AdminUser, group: str, slug: str, pk: str
) -> Response:
    model_admin = _lookup(group, slug)
    if not model_admin.can_edit:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This model is read-only.")
    instance = await _get_or_404(session, model_admin, pk)

    form = await request.form()
    values, errors = _read_form(model_admin.form_fields(), form)
    if errors:
        return _form_with_errors(request, user, model_admin, instance, values, errors)

    for name, value in values.items():
        setattr(instance, name, value)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        user, recovered = await _recover(session, user, instance)
        return _form_with_errors(
            request, user, model_admin, recovered, values, {"__all__": _integrity_message(exc)}
        )

    await _audit(session, user, AuditAction.update, model_admin, instance)
    return RedirectResponse(
        flash_url(f"{_base_url(model_admin)}/{_identity(instance)}", "saved"),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@models_router.post("/{group}/{slug}/{pk}/delete")
async def delete_submit(
    session: DbSession, user: AdminUser, group: str, slug: str, pk: str
) -> Response:
    model_admin = _lookup(group, slug)
    if not model_admin.can_delete:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This model cannot be deleted from here.")
    instance = await _get_or_404(session, model_admin, pk)

    # Deleting the last administrator would lock everyone out of the admin,
    # including whoever is doing it.
    if isinstance(instance, User):
        if instance.id == user.id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot delete your own account.")
        if instance.is_admin and await _admin_count(session) <= 1:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "Cannot delete the only administrator."
            )

    await session.delete(instance)
    await session.commit()
    await _audit(session, user, AuditAction.delete, model_admin, instance, refreshed=False)
    return RedirectResponse(
        flash_url(_base_url(model_admin), "deleted"), status_code=status.HTTP_303_SEE_OTHER
    )


@models_router.post("/{group}/{slug}/{pk}/set-password")
async def set_password(
    session: DbSession,
    user: AdminUser,
    group: str,
    slug: str,
    pk: str,
    new_password: str = Form(...),
) -> Response:
    """Reset another user's password.

    A dedicated, explicitly-named action -- passwords are never writable through
    the generic form, so there is no path that stores one unhashed.
    """
    model_admin = _lookup(group, slug)
    instance = await _get_or_404(session, model_admin, pk)
    if not isinstance(instance, User):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That model has no password.")

    try:
        validate_password(new_password)
    except PasswordPolicyError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    instance.hashed_password = hash_password(new_password)
    await session.commit()
    await _audit(session, user, AuditAction.update, model_admin, instance, note="password reset")
    return RedirectResponse(
        flash_url(f"{_base_url(model_admin)}/{pk}", "password-changed"),
        status_code=status.HTTP_303_SEE_OTHER,
    )


# -- helpers --------------------------------------------------------------


async def _get_or_404(session: AsyncSession, model_admin: ModelAdmin, pk: str) -> Base:
    instance: Base | None = await session.get(model_admin.model, _coerce_pk(pk))
    if instance is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That record no longer exists.")
    return instance


def _coerce_pk(pk: str) -> int | str:
    try:
        return int(pk)
    except ValueError:
        return pk


async def _admin_count(session: Any) -> int:
    return int(
        await session.scalar(select(func.count()).select_from(User).where(User.is_admin.is_(True)))
        or 0
    )


def _label(name: str) -> str:
    return humanise(name)


def _assert_creatable(model_admin: ModelAdmin) -> None:
    if not model_admin.can_create:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This model is read-only.")
    reason = model_admin.creation_blocked_reason()
    if reason is not None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, reason)


def _identity(obj: Any) -> Any | None:
    """The primary key of a persistent object, without triggering a load.

    Reading `obj.id` on an expired instance would itself need IO, which is the
    very thing this exists to avoid.
    """
    identity = sa_inspect(obj).identity
    return identity[0] if identity else None


async def _recover(
    session: AsyncSession, user: User, instance: Base | None
) -> tuple[User, Base | None]:
    """Re-load what the template needs after a rollback.

    A rollback expires every object in the session. The admin shell renders
    `current_user.username` and the form renders `instance.id`; touching an
    expired attribute from Jinja needs database IO outside the async context,
    which surfaces as SQLAlchemy's MissingGreenlet rather than as anything that
    names the real problem.
    """
    user_id = _identity(user)
    reloaded_user = (await session.get(User, user_id) if user_id is not None else None) or user

    reloaded_instance = instance
    if instance is not None:
        identifier = _identity(instance)
        if identifier is not None:
            reloaded_instance = await session.get(type(instance), identifier) or instance
    return reloaded_user, reloaded_instance


def _read_form(fields: list[FieldSpec], form: Any) -> tuple[dict[str, Any], dict[str, str]]:
    values: dict[str, Any] = {}
    errors: dict[str, str] = {}

    for spec in fields:
        raw = form.get(spec.name)
        if spec.input_type == "checkbox":
            values[spec.name] = raw is not None
            continue

        text = (raw or "").strip() if isinstance(raw, str) else ""
        if not text:
            if spec.required:
                errors[spec.name] = "This field is required."
            else:
                values[spec.name] = None
            continue

        try:
            values[spec.name] = _coerce(spec, text)
        except ValueError as exc:
            errors[spec.name] = str(exc)

    return values, errors


def _coerce(spec: FieldSpec, text: str) -> Any:
    if spec.input_type == "number":
        try:
            return int(text)
        except ValueError:
            raise ValueError("Enter a whole number.") from None
    if spec.input_type == "number-float":
        try:
            return float(text)
        except ValueError:
            raise ValueError("Enter a number.") from None
    if spec.input_type == "datetime-local":
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            raise ValueError("Enter a valid date and time.") from None
    if spec.input_type == "date":
        try:
            return date.fromisoformat(text)
        except ValueError:
            raise ValueError("Enter a valid date.") from None
    if spec.choices and text not in spec.choices:
        raise ValueError(f"Choose one of: {', '.join(spec.choices)}.")
    if spec.max_length and len(text) > spec.max_length:
        raise ValueError(f"Keep this under {spec.max_length} characters.")
    return text


def _integrity_message(exc: IntegrityError) -> str:
    detail = str(getattr(exc, "orig", exc))
    if "UNIQUE" in detail.upper() or "duplicate key" in detail.lower():
        return "A record with those values already exists."
    return "That change conflicts with an existing record."


def _form_with_errors(
    request: Request,
    user: User,
    model_admin: ModelAdmin,
    instance: Base | None,
    values: dict[str, Any],
    errors: dict[str, str],
) -> Response:
    return render(
        request,
        "model_form.html",
        {
            "model_admin": model_admin,
            "fields": model_admin.form_fields(),
            "instance": instance,
            "values": values,
            "errors": errors,
            "base_url": _base_url(model_admin),
            "supports_password": isinstance(instance, User),
        },
        user=user,
        active=f"model:{model_admin.group}:{model_admin.slug}",
        status_code=status.HTTP_400_BAD_REQUEST,
    )


async def _audit(
    session: Any,
    actor: User,
    action: AuditAction,
    model_admin: ModelAdmin,
    instance: Base,
    *,
    note: str = "",
    refreshed: bool = True,
) -> None:
    identifier = getattr(instance, "id", None) if refreshed else None
    suffix = f" ({note})" if note else ""
    session.add(
        AuditLog(
            action=action,
            message=f"{actor.username} {action.value}d {model_admin.label}{suffix}",
            object_type=model_admin.model.__name__,
            object_id=str(identifier) if identifier is not None else None,
            actor_id=actor.id,
        )
    )
    await session.commit()
