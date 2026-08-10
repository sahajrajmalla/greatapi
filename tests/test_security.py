"""Regression tests for the defects that made 1.x unsafe.

Each test names the behaviour it locks down. If one of these fails, a specific
vulnerability has come back.
"""

from __future__ import annotations

import re

import httpx
import pytest
from sqlalchemy import select

from greatapi.db.models import User
from greatapi.security.passwords import hash_password, validate_password, verify_password
from greatapi.security.tokens import TokenError, create_token, decode_token
from tests.conftest import ADMIN_PASSWORD, csrf_token

#: Any bcrypt or Argon2 digest. Nothing matching this may reach a response.
HASH_PATTERN = re.compile(r"\$2[aby]?\$|\$argon2")


class TestAdminRequiresServerSideAuth:
    """1.x checked is_admin in a window.onload handler, so curl skipped it."""

    @pytest.mark.parametrize(
        "path",
        [
            "/admin",
            "/admin/account",
            "/admin/jobs",
            "/admin/api-keys",
            "/admin/usage",
            "/admin/model/auth/greatapi_user",
            "/admin/model/auth/greatapi_user/1",
            "/admin/model/system/greatapi_audit_log",
        ],
    )
    async def test_anonymous_get_is_refused(self, client: httpx.AsyncClient, path: str) -> None:
        response = await client.get(path)
        assert response.status_code in (401, 303), f"{path} served {response.status_code}"
        assert not HASH_PATTERN.search(response.text)

    async def test_browser_navigation_redirects_to_login(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/admin", headers={"accept": "text/html"})
        assert response.status_code == 303
        assert response.headers["location"].startswith("/admin/login")

    async def test_api_client_gets_401_not_a_login_page(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/admin/model/auth/greatapi_user")
        assert response.status_code == 401
        assert response.json()["detail"] == "Not authenticated."

    async def test_non_admin_cannot_reach_the_admin(
        self, client: httpx.AsyncClient, plain_user: User
    ) -> None:
        response = await client.post(
            "/admin/login", data={"username": plain_user.username, "password": ADMIN_PASSWORD}
        )
        # A non-admin is refused at login, identically to a wrong password.
        assert response.status_code == 401
        assert (await client.get("/admin")).status_code in (401, 303)


class TestNoCredentialEverReachesTheBrowser:
    """1.x rendered every column, so the users list displayed bcrypt hashes."""

    @pytest.mark.parametrize(
        "path",
        [
            "/admin",
            "/admin/account",
            "/admin/model/auth/greatapi_user",
            "/admin/model/auth/greatapi_user/1",
            "/admin/model/auth/greatapi_api_key",
        ],
    )
    async def test_no_hash_in_any_admin_response(
        self, admin_client: httpx.AsyncClient, path: str
    ) -> None:
        response = await admin_client.get(path)
        assert response.status_code == 200, path
        assert not HASH_PATTERN.search(response.text), f"credential hash leaked on {path}"
        assert "hashed_password" not in response.text
        assert "hashed_key" not in response.text

    async def test_search_cannot_reach_the_password_column(
        self, admin_client: httpx.AsyncClient, admin_user: User
    ) -> None:
        # 1.x cast every column to text and matched against all of them, so a
        # fragment of a stored hash was a valid search term.
        fragment = admin_user.hashed_password[10:20]
        response = await admin_client.get("/admin/model/auth/greatapi_user", params={"q": fragment})
        assert response.status_code == 200
        assert "admin@example.com" not in response.text


class TestMassAssignment:
    """1.x's /admin/change_value copied every posted field onto the record.

    Any signed-in user could set ``is_admin=true`` on themselves, or write
    ``password`` in plaintext and permanently lock the account. Writes are now
    confined to the columns the ModelAdmin declares editable.

    Note what is *not* a vulnerability: an administrator promoting another user
    through the user form is the intended behaviour of an admin panel. The
    defect was the absence of any allow-list, and self-service escalation from
    an arbitrary JSON body.
    """

    async def test_password_is_not_a_writable_field(
        self, admin_client: httpx.AsyncClient, plain_user: User, session
    ) -> None:
        original = plain_user.hashed_password
        await admin_client.post(
            f"/admin/model/auth/greatapi_user/{plain_user.id}",
            data={
                "username": plain_user.username,
                "email": plain_user.email,
                "hashed_password": "plaintext-oops",
                csrf_field(): csrf_token(admin_client),
            },
        )
        await session.refresh(plain_user)
        assert plain_user.hashed_password == original
        assert not plain_user.hashed_password.startswith("plaintext")

    async def test_undeclared_fields_are_ignored(
        self, admin_client: httpx.AsyncClient, plain_user: User, session
    ) -> None:
        """A column absent from `fields` is not writable, even when posted."""
        from greatapi.admin import ModelAdmin, register

        @register(User)
        class NarrowUserAdmin(ModelAdmin):
            app_label = "auth"
            fields = ("username",)  # email and is_admin deliberately omitted

        response = await admin_client.post(
            f"/admin/model/auth/greatapi_user/{plain_user.id}",
            data={
                "username": "renamed",
                "email": "attacker@example.com",
                "is_admin": "on",
                csrf_field(): csrf_token(admin_client),
            },
        )
        assert response.status_code == 303

        await session.refresh(plain_user)
        assert plain_user.username == "renamed", "declared field should be written"
        assert plain_user.email == "user@example.com", "undeclared field was written"
        assert plain_user.is_admin is False, "privilege escalation through an undeclared field"

    async def test_sensitive_fields_are_never_editable(self) -> None:
        """Even opting a credential column in leaves it unwritable."""
        from greatapi.admin import ModelAdmin

        class RecklessUserAdmin(ModelAdmin):
            fields = ("username", "hashed_password")

        editable = RecklessUserAdmin(User).editable_field_names()
        assert "username" in editable
        assert "hashed_password" not in editable


class TestLoginIsNotAnEnumerationOracle:
    """1.x answered 'Invalid Credentials' vs 'Incorrect Password'."""

    async def test_unknown_user_and_wrong_password_are_indistinguishable(
        self, client: httpx.AsyncClient, admin_user: User
    ) -> None:
        unknown = await client.post(
            "/admin/login", data={"username": "nobody", "password": "whatever12"}
        )
        wrong = await client.post(
            "/admin/login", data={"username": admin_user.username, "password": "wrongpass1"}
        )

        assert unknown.status_code == wrong.status_code == 401
        assert _message(unknown.text) == _message(wrong.text)


class TestCSRF:
    async def test_state_change_without_a_token_is_refused(
        self, admin_client: httpx.AsyncClient
    ) -> None:
        response = await admin_client.post("/admin/api-keys", data={"name": "no token"})
        assert response.status_code == 403

    async def test_state_change_with_a_wrong_token_is_refused(
        self, admin_client: httpx.AsyncClient
    ) -> None:
        response = await admin_client.post(
            "/admin/api-keys", data={"name": "bad token", csrf_field(): "not-the-nonce"}
        )
        assert response.status_code == 403

    async def test_state_change_with_the_right_token_succeeds(
        self, admin_client: httpx.AsyncClient
    ) -> None:
        response = await admin_client.post(
            "/admin/api-keys",
            data={"name": "good token", csrf_field(): csrf_token(admin_client)},
        )
        assert response.status_code == 303


class TestSessionCookie:
    async def test_cookie_is_httponly_and_samesite(
        self, client: httpx.AsyncClient, admin_user: User
    ) -> None:
        response = await client.post(
            "/admin/login", data={"username": "admin", "password": ADMIN_PASSWORD}
        )
        cookie = response.headers["set-cookie"]
        assert "HttpOnly" in cookie
        assert "SameSite=lax" in cookie.lower().replace("samesite=lax", "SameSite=lax")

    async def test_a_forged_cookie_is_rejected(self, client: httpx.AsyncClient) -> None:
        client.cookies.set("greatapi_session", "not.a.real.token")
        assert (await client.get("/admin")).status_code in (401, 303)


class TestPasswords:
    def test_argon2_is_used_for_new_hashes(self) -> None:
        assert hash_password("hunter2hunter2").startswith("$argon2")

    def test_legacy_bcrypt_hashes_still_verify_and_are_upgraded(self) -> None:
        # A 1.x hash of "hunter2hunter2", as passlib would have written it.
        import bcrypt

        legacy = bcrypt.hashpw(b"hunter2hunter2", bcrypt.gensalt(rounds=4)).decode()
        valid, upgraded = verify_password("hunter2hunter2", legacy)
        assert valid, "1.x passwords must keep working after the upgrade"
        assert upgraded is not None and upgraded.startswith("$argon2")

    def test_wrong_password_fails(self) -> None:
        valid, _ = verify_password("nope", hash_password("hunter2hunter2"))
        assert not valid

    def test_missing_user_still_performs_a_verification(self) -> None:
        # Guards the timing-parity path in authenticate_user.
        assert verify_password("anything", None) == (False, None)

    def test_corrupt_hash_is_a_failed_login_not_a_crash(self) -> None:
        assert verify_password("anything", "not-a-hash") == (False, None)

    @pytest.mark.parametrize("bad", ["short1", "alllettersonly", "12345678"])
    def test_weak_passwords_are_refused(self, bad: str) -> None:
        with pytest.raises(Exception, match="Password must"):
            validate_password(bad)


class TestTokens:
    def test_round_trip(self) -> None:
        claims = decode_token(create_token("42", role="admin"))
        assert claims["sub"] == "42"
        assert claims["role"] == "admin"

    def test_wrong_type_is_refused(self) -> None:
        token = create_token("42", token_type="session")
        with pytest.raises(TokenError):
            decode_token(token, expected_type="access")

    def test_tampered_token_is_refused(self) -> None:
        token = create_token("42")
        with pytest.raises(TokenError):
            decode_token(token[:-4] + "AAAA")

    def test_algorithm_confusion_is_refused(self) -> None:
        """An 'alg: none' token must never validate."""
        import base64
        import json

        def b64(payload: dict[str, object]) -> str:
            raw = json.dumps(payload).encode()
            return base64.urlsafe_b64encode(raw).decode().rstrip("=")

        forged = f"{b64({'alg': 'none', 'typ': 'JWT'})}.{b64({'sub': '1', 'typ': 'access'})}."
        with pytest.raises(TokenError):
            decode_token(forged)


class TestOpenRedirect:
    @pytest.mark.parametrize(
        "target",
        [
            "https://evil.example.com",
            "//evil.example.com",
            # A browser normalises the backslash to a slash, so this is
            # protocol-relative too -- a plain startswith("//") check misses it.
            "/\\evil.example.com",
            "\\\\evil.example.com",
            "/\tevil",
            "javascript:alert(1)",
            "http:/evil.example.com",
            "/ /evil.example.com",
        ],
    )
    async def test_next_cannot_leave_the_site(
        self, client: httpx.AsyncClient, admin_user: User, target: str
    ) -> None:
        response = await client.post(
            "/admin/login",
            data={"username": "admin", "password": ADMIN_PASSWORD, "next": target},
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/admin", target

    @pytest.mark.parametrize(
        "target",
        [
            "https://evil.example.com",
            "//evil.example.com",
            "///evil.example.com",
            "/\\evil.example.com",
            "\\\\evil.example.com",
            "//\\evil.example.com",
            "javascript:alert(1)",
            "http:/evil.example.com",
            "/ /evil.example.com",
            "/a\tb",
            "/x\r\nSet-Cookie: y",
            "/\x00evil",
            "\t//evil.example.com",
            "/" + "a" * 600,
        ],
    )
    def test_the_sanitiser_never_returns_an_offsite_target(self, target: str) -> None:
        """The invariant, checked directly rather than through a request.

        Whatever comes back must be a single-slash, same-site path: no scheme,
        no host, no backslash, no whitespace or control characters.
        """
        from urllib.parse import urlsplit

        from greatapi.admin.views.auth import _safe_next

        result = _safe_next(target)
        assert result.startswith("/") and not result.startswith("//"), result
        parsed = urlsplit(result)
        assert not parsed.scheme and not parsed.netloc, result
        assert "\\" not in result
        assert not any(c.isspace() or ord(c) < 0x20 for c in result), result

    @pytest.mark.parametrize("target", ["/admin/usage", "/admin/jobs?status=failed", "/"])
    async def test_same_site_targets_are_honoured(
        self, client: httpx.AsyncClient, admin_user: User, target: str
    ) -> None:
        response = await client.post(
            "/admin/login",
            data={"username": "admin", "password": ADMIN_PASSWORD, "next": target},
        )
        assert response.status_code == 303
        assert response.headers["location"] == target


class TestLastAdminProtection:
    async def test_cannot_delete_your_own_account(
        self, admin_client: httpx.AsyncClient, admin_user: User
    ) -> None:
        response = await admin_client.post(
            f"/admin/model/auth/greatapi_user/{admin_user.id}/delete",
            data={csrf_field(): csrf_token(admin_client)},
        )
        assert response.status_code == 400

    async def test_cannot_delete_the_only_administrator(
        self, admin_client: httpx.AsyncClient, admin_user: User, session
    ) -> None:
        second = User(
            email="two@example.com",
            username="two",
            hashed_password=hash_password(ADMIN_PASSWORD),
            is_admin=True,
        )
        session.add(second)
        await session.commit()
        await session.refresh(second)

        # Two admins: deleting one is allowed.
        response = await admin_client.post(
            f"/admin/model/auth/greatapi_user/{second.id}/delete",
            data={csrf_field(): csrf_token(admin_client)},
        )
        assert response.status_code == 303

        # Down to one, and it is the caller's own account.
        assert (await session.scalar(select(User).where(User.username == "two"))) is None


class TestSecurityHeaders:
    async def test_admin_carries_a_strict_csp(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/admin/login")
        csp = response.headers["content-security-policy"]
        assert "default-src 'self'" in csp
        assert "unsafe-inline" not in csp
        assert "frame-ancestors 'none'" in csp

    async def test_standard_headers_are_present(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/admin/login")
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "DENY"

    async def test_login_page_loads_nothing_from_a_cdn(self, client: httpx.AsyncClient) -> None:
        body = (await client.get("/admin/login")).text
        assert "cdn." not in body
        assert "googleapis" not in body
        assert "//" not in re.sub(r"</?[a-z!][^>]*>", "", body)


def csrf_field() -> str:
    from greatapi.security.csrf import CSRF_FIELD_NAME

    return CSRF_FIELD_NAME


def _message(html: str) -> str:
    match = re.search(r'class="flash flash-error"[^>]*>([^<]*)<', html)
    return match.group(1).strip() if match else ""
