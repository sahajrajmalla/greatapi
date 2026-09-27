# Models and migrations

## Models

```python title="blog/models.py"
from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from greatapi.db import Base, TimestampMixin

class Post(TimestampMixin, Base):
    __tablename__ = "blog_post"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200), index=True)
    body: Mapped[str | None] = mapped_column(Text)
    published: Mapped[bool] = mapped_column(default=False)
```

`TimestampMixin` adds `created_at` and `updated_at`, maintained for you.

Every app in `INSTALLED_APPS` has its `models.py` imported at startup, which is
what puts its tables into the metadata — and therefore what lets autogenerate
see them.

## Timestamps are always timezone-aware

Use `greatapi.db.UTCDateTime` for datetime columns, as the framework does.
SQLite has no native timestamp type and hands values back naive even for
`DateTime(timezone=True)`, so comparing one against an aware `utcnow()` raises
`TypeError` at runtime, in whichever code path happens to load a stored date
first. `UTCDateTime` normalises in both directions, so SQLite and Postgres
behave identically.

```python
from greatapi.db import UTCDateTime, utcnow

expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
```

## Migrations

```bash
greatapi makemigrations -m "add posts"
greatapi migrate
```

| Command | What |
|---|---|
| `makemigrations -m "message"` | Generate a revision from your model changes |
| `makemigrations --empty` | A blank revision to fill in — data migrations |
| `migrate` | Apply everything outstanding |
| `migrate <revision>` | Apply up to a specific revision |
| `downgrade -1` | Roll back one |
| `downgrade base` | Roll back everything |
| `history` | What exists, and where you are |

Read what autogenerate produced before applying it. It is good at added and
removed columns, and cannot tell a rename from a drop-and-add.

## SQLite

`render_as_batch` is on, so Alembic rebuilds the table for changes SQLite cannot
`ALTER` in place. Without it every column change fails on the database most
people develop against.

## Postgres

```bash
pip install "greatapi[postgres]"
```

```bash
GREATAPI_DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/myapp
```

Percent-encode special characters in the password. GreatAPI escapes the URL
before handing it to Alembic, whose config parser would otherwise read a bare
`%` as interpolation.

## Tables GreatAPI owns

All prefixed `greatapi_`: `greatapi_user`, `greatapi_api_key`, `greatapi_job`,
`greatapi_audit_log`, `greatapi_llm_call`, `greatapi_agent_run`.

The last two are created even without the AI extra. Registering models
conditionally would make autogenerate propose dropping whatever the current
environment cannot see — a far worse failure than two tables that stay empty.

## Sharing a database with another service

Autogenerate ignores tables it does not know about, so it will not propose
dropping another service's schema.

## Creating tables without migrations

With `GREATAPI_DEBUG=true`, tables are created on boot — convenient while you
are exploring. With debug off they are not, so schema changes go through a
reviewed migration. Override explicitly if you need to:

```python
app = GreatAPI(title="myapp", create_tables=True)
```
