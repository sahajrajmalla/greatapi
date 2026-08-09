"""The admin: registry behaviour and CRUD round-trips."""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy import String, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from greatapi.admin import ModelAdmin, get_registry, is_sensitive, register
from greatapi.admin.charts import Series, bar_chart, line_chart, sparkline
from greatapi.admin.registry import REDACTED, format_value, humanise
from greatapi.admin.templating import Page
from greatapi.db.models import AuditLog, User
from greatapi.security.csrf import CSRF_FIELD_NAME
from tests.conftest import csrf_token


class TestRegistry:
    def test_register_as_a_decorator(self) -> None:
        @register(User)
        class UserAdmin(ModelAdmin):
            list_display = ("id", "username")

        assert isinstance(get_registry().entries[User], UserAdmin)

    def test_register_as_a_plain_call_uses_defaults(self) -> None:
        register(User)
        assert User in get_registry().entries

    def test_register_accepts_several_models(self) -> None:
        register([User, AuditLog])
        assert {User, AuditLog} <= set(get_registry().entries)

    def test_a_non_model_is_refused(self) -> None:
        with pytest.raises(Exception, match="not a GreatAPI model"):
            register(dict)  # type: ignore[arg-type]

    def test_a_non_modeladmin_is_refused(self) -> None:
        with pytest.raises(Exception, match="must inherit from"):

            @register(User)
            class NotAnAdmin:  # type: ignore[misc]
                pass

    def test_slug_and_label(self) -> None:
        admin = ModelAdmin(User)
        assert admin.slug == "greatapi_user"
        assert admin.label == "User"


class TestFieldSelection:
    def test_sensitive_columns_are_never_visible(self) -> None:
        admin = ModelAdmin(User)  # no list_display: every column is a candidate
        visible = admin.visible_field_names()
        assert "username" in visible
        assert "hashed_password" not in visible

    def test_display_value_redacts_rather_than_omits(self, admin_user: User) -> None:
        assert ModelAdmin(User).display_value(admin_user, "hashed_password") == REDACTED

    def test_exclude_is_honoured(self) -> None:
        class Narrow(ModelAdmin):
            exclude = ("email",)

        assert "email" not in Narrow(User).visible_field_names()

    def test_readonly_fields_are_not_editable(self) -> None:
        class WithReadonly(ModelAdmin):
            readonly_fields = ("username",)

        assert "username" not in WithReadonly(User).editable_field_names()

    def test_search_fields_drop_sensitive_names(self) -> None:
        class Reckless(ModelAdmin):
            search_fields = ("username", "hashed_password")

        assert Reckless(User).searchable_field_names() == ["username"]

    @pytest.mark.parametrize(
        "name",
        ["password", "hashed_password", "api_key", "secret_token", "PRIVATE_KEY", "salt"],
    )
    def test_sensitive_names_are_detected(self, name: str) -> None:
        assert is_sensitive(name)

    @pytest.mark.parametrize("name", ["username", "email", "title", "keyword", "monkey_count"])
    def test_ordinary_names_are_not(self, name: str) -> None:
        assert not is_sensitive(name)

    def test_form_fields_infer_input_types(self) -> None:
        specs = {spec.name: spec for spec in ModelAdmin(User).form_fields()}
        assert specs["is_admin"].input_type == "checkbox"
        # String(320) is a long single line, not prose -- an email input must
        # not become a textarea.
        assert specs["email"].input_type == "text"
        assert specs["email"].max_length == 320


class TestCrud:
    async def test_list_search_and_paginate(
        self, admin_client: httpx.AsyncClient, session: AsyncSession
    ) -> None:
        from greatapi.security.passwords import hash_password

        for index in range(30):
            session.add(
                User(
                    email=f"person{index}@example.com",
                    username=f"person{index}",
                    hashed_password=hash_password("hunter2hunter2"),
                )
            )
        await session.commit()

        first = await admin_client.get("/admin/model/auth/greatapi_user")
        assert first.status_code == 200
        assert "Page 1 of" in first.text

        second = await admin_client.get("/admin/model/auth/greatapi_user", params={"page": 2})
        assert second.status_code == 200

        found = await admin_client.get("/admin/model/auth/greatapi_user", params={"q": "person7"})
        assert "person7@example.com" in found.text
        assert "person12@example.com" not in found.text

    async def test_create_edit_delete_round_trip(
        self, admin_client: httpx.AsyncClient, session: AsyncSession
    ) -> None:
        token = csrf_token(admin_client)

        created = await admin_client.post(
            "/admin/model/system/greatapi_audit_log/new",
            data={"action": "create", "message": "hand written", CSRF_FIELD_NAME: token},
        )
        # The audit log is read-only, so creation is refused rather than crashing.
        assert created.status_code == 403

        from greatapi.security.passwords import hash_password

        record = User(
            username="newcomer",
            email="newcomer@example.com",
            hashed_password=hash_password("hunter2hunter2"),
        )
        session.add(record)
        await session.commit()
        await session.refresh(record)

        edited = await admin_client.post(
            f"/admin/model/auth/greatapi_user/{record.id}",
            data={
                "username": "renamed",
                "email": "newcomer@example.com",
                "is_active": "on",
                CSRF_FIELD_NAME: token,
            },
        )
        assert edited.status_code == 303
        await session.refresh(record)
        assert record.username == "renamed"

        record_id = record.id  # read before expiring; the row is about to go
        deleted = await admin_client.post(
            f"/admin/model/auth/greatapi_user/{record_id}/delete",
            data={CSRF_FIELD_NAME: token},
        )
        assert deleted.status_code == 303
        # The delete happened in the request's session; expire ours so the
        # identity map does not answer from cache.
        session.expire_all()
        assert await session.get(User, record_id) is None

    async def test_validation_errors_come_back_on_the_form(
        self, admin_client: httpx.AsyncClient, plain_user: User
    ) -> None:
        response = await admin_client.post(
            f"/admin/model/auth/greatapi_user/{plain_user.id}",
            data={"username": "", "email": "", CSRF_FIELD_NAME: csrf_token(admin_client)},
        )
        assert response.status_code == 400
        assert "This field is required." in response.text

    async def test_a_model_needing_an_uneditable_column_cannot_be_created(
        self, admin_client: httpx.AsyncClient
    ) -> None:
        """A password is required and never writable, so say so up front."""
        from greatapi.admin import ModelAdmin

        admin = ModelAdmin(User)
        reason = admin.creation_blocked_reason()
        assert reason is not None and "hashed_password" in reason
        assert admin.creatable is False

        response = await admin_client.get("/admin/model/auth/greatapi_user/new")
        assert response.status_code == 403

    async def test_a_duplicate_is_a_message_not_a_500(
        self, admin_client: httpx.AsyncClient, admin_user: User, plain_user: User
    ) -> None:
        # Renaming one user onto another's username violates a unique index.
        response = await admin_client.post(
            f"/admin/model/auth/greatapi_user/{plain_user.id}",
            data={
                "username": admin_user.username,
                "email": plain_user.email,
                CSRF_FIELD_NAME: csrf_token(admin_client),
            },
        )
        assert response.status_code == 400
        assert "already exists" in response.text
        # The shell still renders: a rollback must not break the signed-in user.
        assert admin_user.username in response.text

    async def test_an_unknown_model_is_404(self, admin_client: httpx.AsyncClient) -> None:
        assert (await admin_client.get("/admin/model/nope/nothing")).status_code == 404

    async def test_an_unknown_record_is_404(self, admin_client: httpx.AsyncClient) -> None:
        response = await admin_client.get("/admin/model/auth/greatapi_user/424242")
        assert response.status_code == 404

    async def test_a_read_only_model_refuses_creation(
        self, admin_client: httpx.AsyncClient
    ) -> None:
        # The audit log is registered with can_create=False.
        response = await admin_client.get("/admin/model/system/greatapi_audit_log/new")
        assert response.status_code == 403

    async def test_changes_are_audited(
        self, admin_client: httpx.AsyncClient, session: AsyncSession, plain_user: User
    ) -> None:
        await admin_client.post(
            f"/admin/model/auth/greatapi_user/{plain_user.id}",
            data={
                "username": "audited",
                "email": plain_user.email,
                CSRF_FIELD_NAME: csrf_token(admin_client),
            },
        )
        messages = [row.message for row in (await session.execute(select(AuditLog))).scalars()]
        assert any("updated" in message for message in messages)


class TestPasswordReset:
    async def test_an_admin_can_set_another_password(
        self, admin_client: httpx.AsyncClient, plain_user: User, session: AsyncSession
    ) -> None:
        original = plain_user.hashed_password
        response = await admin_client.post(
            f"/admin/model/auth/greatapi_user/{plain_user.id}/set-password",
            data={"new_password": "brandnew1pass", CSRF_FIELD_NAME: csrf_token(admin_client)},
        )
        assert response.status_code == 303

        await session.refresh(plain_user)
        assert plain_user.hashed_password != original
        assert plain_user.hashed_password.startswith("$argon2")

    async def test_a_weak_password_is_refused(
        self, admin_client: httpx.AsyncClient, plain_user: User
    ) -> None:
        response = await admin_client.post(
            f"/admin/model/auth/greatapi_user/{plain_user.id}/set-password",
            data={"new_password": "short", CSRF_FIELD_NAME: csrf_token(admin_client)},
        )
        assert response.status_code == 400


class TestAccount:
    async def test_changing_your_own_password(
        self, admin_client: httpx.AsyncClient, admin_user: User, session: AsyncSession
    ) -> None:
        from tests.conftest import ADMIN_PASSWORD

        response = await admin_client.post(
            "/admin/account/password",
            data={
                "current_password": ADMIN_PASSWORD,
                "new_password": "replacement1x",
                "confirm_password": "replacement1x",
                CSRF_FIELD_NAME: csrf_token(admin_client),
            },
        )
        assert response.status_code == 303
        # The session is rotated, so the old cookie stops working.
        assert "greatapi_session" in response.headers.get("set-cookie", "")

    async def test_a_wrong_current_password_is_refused(
        self, admin_client: httpx.AsyncClient
    ) -> None:
        response = await admin_client.post(
            "/admin/account/password",
            data={
                "current_password": "not-it",
                "new_password": "replacement1x",
                "confirm_password": "replacement1x",
                CSRF_FIELD_NAME: csrf_token(admin_client),
            },
        )
        assert response.status_code == 400
        assert "current password is incorrect" in response.text

    async def test_mismatched_confirmation_is_refused(
        self, admin_client: httpx.AsyncClient
    ) -> None:
        from tests.conftest import ADMIN_PASSWORD

        response = await admin_client.post(
            "/admin/account/password",
            data={
                "current_password": ADMIN_PASSWORD,
                "new_password": "replacement1x",
                "confirm_password": "different1x",
                CSRF_FIELD_NAME: csrf_token(admin_client),
            },
        )
        assert response.status_code == 400
        assert "do not match" in response.text


class TestLabelsAndValues:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("LLMCall", "LLM Call"),
            ("APIKey", "API Key"),
            ("AgentRun", "Agent Run"),
            ("cost_usd", "Cost USD"),
            ("latency_ms", "Latency ms"),
            ("api_key_id", "API Key ID"),
            ("is_admin", "Is Admin"),
        ],
    )
    def test_labels_read_naturally(self, raw: str, expected: str) -> None:
        assert humanise(raw) == expected

    def test_timestamps_lose_their_microseconds(self) -> None:
        from greatapi.db.base import utcnow

        rendered = format_value(utcnow())
        assert isinstance(rendered, str)
        assert "." not in rendered

    def test_booleans_pass_through_for_badging(self) -> None:
        assert format_value(True) is True

    def test_small_floats_keep_their_precision(self) -> None:
        assert format_value(0.017766) == "0.017766"
        assert format_value(2.0) == "2"


class TestCharts:
    def test_an_empty_series_says_so_rather_than_drawing_nothing(self) -> None:
        assert "No data yet" in bar_chart(Series([], []))
        assert "No data yet" in line_chart(Series([], []))

    def test_a_bar_chart_renders_one_bar_per_value(self) -> None:
        markup = bar_chart(Series(["a", "b", "c"], [1.0, 2.0, 3.0]))
        assert markup.count("<rect") == 3
        assert "<svg" in markup

    def test_labels_are_thinned_when_bars_get_narrow(self) -> None:
        crowded = bar_chart(Series([f"2026-01-{d:02d}" for d in range(1, 29)], [1.0] * 28))
        assert crowded.count("<text") < 28, "labels must not overlap into a smear"

    def test_iso_dates_are_shortened(self) -> None:
        markup = bar_chart(Series(["2026-08-09"], [1.0]))
        # The tick is short; the hover title keeps the full date.
        assert 'class="chart-label">09/08<' in markup
        assert "<title>2026-08-09" in markup

    def test_values_are_escaped(self) -> None:
        markup = bar_chart(Series(["<script>"], [1.0]))
        assert "<script>" not in markup
        assert "&lt;script&gt;" in markup

    def test_a_sparkline_needs_two_points(self) -> None:
        assert "polyline" not in sparkline([1.0])
        assert "polyline" in sparkline([1.0, 2.0, 3.0])


class TestPagination:
    def test_page_arithmetic(self) -> None:
        page = Page(items=[], total=95, number=2, size=25)
        assert page.pages == 4
        assert page.has_previous and page.has_next
        assert (page.start_index, page.end_index) == (26, 50)

    def test_a_single_page(self) -> None:
        page = Page(items=[], total=3, number=1, size=25)
        assert page.pages == 1
        assert not page.has_previous and not page.has_next

    def test_an_empty_result(self) -> None:
        page = Page(items=[], total=0, number=1, size=25)
        assert page.start_index == 0


class TestCustomModel:
    async def test_a_user_model_appears_and_is_editable(
        self, admin_client: httpx.AsyncClient, engine: object
    ) -> None:
        from greatapi.db.base import Base

        class Widget(Base):
            __tablename__ = "test_widget"
            id: Mapped[int] = mapped_column(primary_key=True)
            name: Mapped[str] = mapped_column(String(100))

        async with engine.begin() as connection:  # type: ignore[attr-defined]
            await connection.run_sync(Base.metadata.create_all)

        @register(Widget)
        class WidgetAdmin(ModelAdmin):
            app_label = "shop"
            list_display = ("id", "name")
            search_fields = ("name",)

        # The registry is read at request time, so a late registration shows up.
        response = await admin_client.get("/admin/model/shop/test_widget")
        assert response.status_code == 200
        assert "Widget" in response.text

        Base.metadata.remove(Widget.__table__)
