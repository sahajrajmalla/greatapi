# Contributing to GreatAPI

Thanks for being here. Bug reports, documentation fixes and pull requests are
all welcome.

## Setting up

You need Python 3.10 or newer. Nothing else — no Node, no Docker, no database
server.

```bash
git clone https://github.com/sahajrajmalla/greatapi
cd greatapi
make install
```

That creates `.venv`, installs GreatAPI in editable mode with the `dev` and
`docs` extras, and installs the pre-commit hooks.

Check it worked:

```bash
make check     # ruff, mypy and the full test suite
make demo      # the example app, at http://127.0.0.1:8000
```

`make help` lists everything.

## Working on it

```bash
make format    # autofix lint and format
make lint      # ruff + mypy --strict
make test      # pytest with coverage
make docs      # the documentation site on :8001
make build     # build the wheel and validate it
```

The suite runs offline: the `echo` provider covers every AI path, so no test
needs an API key or a network connection. If you find yourself wanting one,
that is a sign the test should use `echo` or a mock transport instead.

Before opening a pull request:

```bash
make check
```

## Conventions

**Type hints everywhere.** `mypy --strict` runs over `src/greatapi` in CI.

**Tests for behaviour.** A new feature needs a test. A bug fix needs a test that
fails before the fix — that is what stops it coming back.

**Comments explain why.** The code says what it does. A comment earns its place
by saying why it does it that way, especially where the obvious approach is
wrong. See `db/base.py:UTCDateTime` or `jobs/queue.py:claim_jobs` for the shape.

**Commits follow [Conventional Commits](https://www.conventionalcommits.org):**

```
feat(admin): add bulk delete
fix(jobs): requeue a job interrupted by shutdown
docs(streaming): explain the heartbeat
test(keys): cover the budget ceiling
```

Types in use: `feat`, `fix`, `docs`, `test`, `refactor`, `perf`, `build`, `ci`,
`chore`. The changelog is written from them.

**One change per pull request.** A refactor and a bug fix in one diff is two
reviews wearing a trenchcoat.

## Project layout

```
src/greatapi/
  application.py     GreatAPI(FastAPI) -- lifespan and wiring
  apps.py            INSTALLED_APPS loading
  conf/settings.py   configuration, and the project/app templates
  db/                base, session, models, Alembic integration
  security/          passwords, tokens, sessions, CSRF, dependencies
  keys/              API keys: issuance, scopes, limits, budgets
  jobs/              the queue, the registry and the worker
  streaming.py       Server-Sent Events
  ai/                providers, agents, usage and pricing
  admin/             registry, views, templates, static assets
  cli/               the greatapi command
tests/               mirrors the above
examples/chat/       the runnable demo
docs/                the MkDocs site
```

## Touching the admin UI

The stylesheet is `src/greatapi/admin/static/greatapi.css`: hand-written, no
build step, no npm. Colours come from CSS custom properties at the top; change
one there rather than in a rule.

Two constraints that are not negotiable, because they are what makes the admin
work offline and under a strict CSP:

- **No external requests.** No CDN, no web fonts, no remote images.
- **No inline scripts, styles or event handlers.** Behaviour goes in
  `greatapi.js` and attaches via a `data-` attribute.

Charts are server-rendered inline SVG in `admin/charts.py`. There is no chart
library and there should not be one.

## Adding a provider

Implement `complete` and `stream` against `greatapi.ai.providers.base.Provider`,
translating to and from the neutral types in `ai/types.py`, then register it:

```python
from greatapi.ai.providers import register_provider

register_provider("myvendor", MyVendorProvider)
```

Import the SDK through `greatapi.ai.providers.base.require`, so a missing
dependency raises `MissingDependencyError` with the right install command
instead of an `ImportError`. Add an extra for it in `pyproject.toml`, and keep
it out of the base dependencies — the core install has no LLM dependency and
that is deliberate.

## Reporting a security issue

Please do not open a public issue. See [SECURITY.md](https://github.com/sahajrajmalla/greatapi/blob/master/SECURITY.md).

## Code of conduct

This project follows the [Contributor Covenant](https://github.com/sahajrajmalla/greatapi/blob/master/CODE_OF_CONDUCT.md).
