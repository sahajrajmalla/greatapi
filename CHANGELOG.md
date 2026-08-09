# Changelog

Notable changes to GreatAPI. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [2.0.0]

A rewrite. 1.x pinned FastAPI 0.78 and Pydantic v1 and could not run on a
current Python; this release brings the whole stack forward and fixes a number
of security defects along the way. See [MIGRATION.md](https://github.com/sahajrajmalla/greatapi/blob/master/MIGRATION.md) to upgrade.

### Security

- **The JWT signing key is no longer a literal in the source.** 1.x shipped one
  in `core/auth/jwt_token.py`, published with every release, so anyone could
  forge an admin token for any GreatAPI deployment. `GREATAPI_SECRET_KEY` is now
  required and has no default.
- **The admin authenticates on the server.** 1.x checked `is_admin` from a
  `window.onload` handler, so the page's data had already been sent before the
  check ran and `curl` skipped it entirely.
- **Credentials never reach the browser.** 1.x rendered every column of every
  registered table, so the users list displayed bcrypt hashes and the search box
  ran `ILIKE` across them. Columns are opt-in and credential-shaped names are
  redacted regardless.
- **Writes are confined to declared fields.** 1.x's `/admin/change_value`
  copied every posted field onto the record, letting any signed-in user set
  `is_admin` on themselves or overwrite `password` in plaintext.
- **Login no longer enumerates accounts.** 1.x answered "Invalid Credentials"
  for an unknown user and "Incorrect Password" for a wrong one.
- Sessions are signed `HttpOnly` `SameSite=Lax` cookies rather than a token in
  `localStorage`, and admin form posts carry a CSRF token bound to the session.
- `python-jose` replaced with **PyJWT**, always decoding with an explicit
  algorithm list to block algorithm-confusion attacks.
- `passlib` replaced with **pwdlib** (Argon2id). passlib predates bcrypt 4.x and
  raises `AttributeError: module 'bcrypt' has no attribute '__about__'` against
  any current bcrypt, so 1.x installs had a hashing layer that errored. Existing
  bcrypt hashes still verify and are upgraded on next sign-in.
- Deleting a user takes an explicit target and refuses your own account or the
  last administrator. 1.x's endpoint deleted the caller.
- The debug endpoint `/test_me`, which printed table contents to stdout, and the
  `/admin/add_item/test` stub are gone.
- Security headers on every response, and a strict Content-Security-Policy on
  the admin — possible now that no asset comes from a CDN.

### Added

- `greatapi.ai` with provider adapters (Anthropic, OpenAI, any OpenAI-compatible
  endpoint, and an offline `echo` provider), a tool-calling `Agent`, and
  token/cost/latency accounting surfaced at `/admin/usage`.
- Server-Sent Events via `greatapi.streaming.sse`, with heartbeats, correct
  multi-line framing, `X-Accel-Buffering: no`, and cancellation of the upstream
  call when the client disconnects.
- A database-backed job queue with retries, exponential backoff and a status
  endpoint, running in-process.
- API keys with scopes, per-key rate limits and monthly spend caps.
- Alembic behind `greatapi makemigrations` / `migrate` / `downgrade` / `history`.
- `INSTALLED_APPS`: an app's models, admin registrations and router are wired by
  convention.
- `greatapi routes`, `greatapi generate-secret`, and `createsuperuser --noinput`.
- Layered extras: `[ai]`, `[anthropic]`, `[openai]`, `[local]`, `[postgres]`,
  `[all]`, `[dev]`, `[docs]`.
- A test suite (185 tests, 84% coverage) that runs with no network and no API key.

### Changed

- **Async throughout.** SQLAlchemy 2.0 `AsyncSession`, `aiosqlite` by default,
  `asyncpg` via `[postgres]`. 1.x held one process-wide `Session` shared by every
  request.
- **The database is configurable.** 1.x hardcoded SQLite with no override.
- `GreatAPI(...)` replaces the `_cbv(admin_router, AdminSite, get_route_dict(...))`
  incantation users had to copy into `main.py`.
- The admin UI is one hand-written stylesheet, self-hosted, with light and dark
  themes and a layout that works down to 375px. 1.x loaded Tailwind and Google
  Fonts from CDNs at runtime and broke without internet.
- Model CRUD moved to `/admin/model/{group}/{slug}`, so an application model
  named `usage` or `jobs` cannot shadow a built-in page.
- Framework tables are prefixed `greatapi_`.
- Packaging moved to `pyproject.toml`; `pre-commit` is no longer a runtime
  dependency; `py.typed` now backs the `Typing :: Typed` classifier.
- Python 3.10–3.14. FastAPI 0.115+, Pydantic v2, SQLAlchemy 2.0.

### Removed

- `greatapi.utils.cbv` and `greatapi.utils.inferring_router` — vendored
  `fastapi-utils` code that breaks against current FastAPI.
- `greatapi.core.test_auth`, whose class name made pytest try to collect it.
- The mockup admin pages, one of which hotlinked an image from matplotlib.org.

## [1.0.0]

The last 1.x release. Still installable, and unaffected by this rewrite.

[Unreleased]: https://github.com/sahajrajmalla/greatapi/compare/v2.0.0...HEAD
[2.0.0]: https://github.com/sahajrajmalla/greatapi/compare/v1.0.0...v2.0.0
[1.0.0]: https://github.com/sahajrajmalla/greatapi/releases/tag/v1.0.0
