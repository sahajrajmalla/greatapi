# Upgrading from GreatAPI 1.x to 2.0

2.0 is a rewrite. 1.x pinned FastAPI 0.78 and Pydantic v1, so there was no
gradual path forward — but the concepts carry over, and the mechanical work is
small. Budget an hour for a typical project.

**1.0.x stays on PyPI and keeps working.** Pin `greatapi==1.0.0` if you would
rather not move yet. It does, however, carry the security defects listed at the
bottom of this page, so please do move.

## Before you start

Back up your database. The table rename in step 4 is the only irreversible part.

## 1. Install

```bash
pip install --upgrade "greatapi==2.*"
# plus what you need:
pip install "greatapi[ai]"        # LLM providers and agents
pip install "greatapi[postgres]"  # asyncpg
```

Python 3.10 or newer is required.

## 2. Configuration moves to the environment

1.x had a signing key hardcoded in the package and a database URL that could not
be changed. Both are now settings.

```bash
greatapi generate-secret     # put the output in .env
```

```bash
# .env
GREATAPI_SECRET_KEY=<the generated value>
GREATAPI_DATABASE_URL=sqlite+aiosqlite:///./app.db
GREATAPI_DEBUG=false
```

> Every session and token issued by 1.x was signed with a key that shipped in
> the package. They are all invalid now, which is the point — everyone signs in
> again once.

Note the driver in the URL: `sqlite+aiosqlite`, or `postgresql+asyncpg`. 2.0 is
async throughout.

## 3. Rewrite `main.py`

1.x:

```python
from fastapi import FastAPI
from greatapi.admin.sites import admin_router, AdminSite
from greatapi.utils.cbv import _cbv
from greatapi.utils.urls import get_route_dict
from greatapi.core import auth_router, user_router, test_auth_router, history_router
from myproject import REGISTERED_ADMINS

app = FastAPI()
app.mount("/static", StaticFiles(directory=GREATAPI_ADMIN_STATIC_PATH), name="static")
admin.AdminBase.metadata.create_all(engine)
registered_admins = get_route_dict(REGISTERED_ADMINS)
admin_site = _cbv(admin_router, AdminSite, registered_admins)
app.include_router(admin_router)
app.include_router(auth_router)
...
```

2.0:

```python
from greatapi import GreatAPI
from myproject.settings import INSTALLED_APPS

app = GreatAPI(title="myproject", installed_apps=INSTALLED_APPS)
```

## 4. Models and admin registration

`REGISTERED_ADMINS = [User, Post]` becomes a `ModelAdmin` per model, which is
what lets 2.0 keep credentials out of the browser:

```python
# blog/admin.py
from greatapi import admin
from blog.models import Post

@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "created_at")
    search_fields = ("title",)
```

Your models keep working; only the import and column style change:

```python
# before
from greatapi.db.database import Base
from sqlalchemy import Column, Integer, String

class Post(Base):
    __tablename__ = "posts"
    id = Column(Integer, primary_key=True)
    title = Column(String)

# after
from greatapi.db import Base, TimestampMixin
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

class Post(TimestampMixin, Base):
    __tablename__ = "posts"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
```

Then list the app:

```python
# myproject/settings.py
INSTALLED_APPS: list[str] = ["blog"]
```

## 5. The framework tables were renamed

| 1.x | 2.0 |
|---|---|
| `users` | `greatapi_user` |
| `history` | `greatapi_audit_log` |

The `User` model also renames `password` to `hashed_password` and adds
`is_active`, `full_name` and `last_login_at`.

Generate a migration and edit it to rename rather than drop and recreate:

```bash
greatapi makemigrations -m "upgrade to greatapi 2.0"
```

```python
def upgrade() -> None:
    op.rename_table("users", "greatapi_user")
    op.alter_column("greatapi_user", "password", new_column_name="hashed_password")
    op.add_column("greatapi_user", sa.Column("is_active", sa.Boolean(),
                  nullable=False, server_default=sa.true()))
    op.add_column("greatapi_user", sa.Column("full_name", sa.String(255)))
    op.add_column("greatapi_user", sa.Column("last_login_at", greatapi.db.base.UTCDateTime()))
    op.rename_table("history", "greatapi_audit_log")
    # ... plus the create_table calls autogenerate produced for the new tables
```

```bash
greatapi migrate
```

**Existing passwords keep working.** 2.0 hashes with Argon2 but still verifies
bcrypt, and upgrades each hash the next time its owner signs in successfully.

## 6. Async endpoints and sessions

The shared module-level `SessionLocal()` is gone. Take a session as a dependency:

```python
# before
class BlogSite:
    db = SessionLocal()

    @router.get("/posts")
    def list_posts(self):
        return self.db.query(Post).all()

# after
from greatapi.security import DbSession
from sqlalchemy import select

@router.get("/posts")
async def list_posts(session: DbSession) -> list[PostOut]:
    return list((await session.execute(select(Post))).scalars())
```

## What moved

| 1.x | 2.0 |
|---|---|
| `greatapi.db.database.Base` | `greatapi.db.Base` |
| `greatapi.db.database.get_db` | `greatapi.db.get_session`, or `greatapi.security.DbSession` |
| `greatapi.db.admin.user.User` | `greatapi.db.User` |
| `greatapi.db.admin.default.History` | `greatapi.db.AuditLog` |
| `greatapi.core.auth.hashing.Hash.bcrypt` | `greatapi.security.hash_password` |
| `greatapi.core.auth.hashing.Hash.verify` | `greatapi.security.verify_password` (arguments now `(plain, hashed)`) |
| `greatapi.core.auth.jwt_token.create_access_token` | `greatapi.security.create_token` |
| `greatapi.config.GREATAPI_ADMIN_STATIC_PATH` | `greatapi.conf.settings.ADMIN_STATIC_DIR` |
| `greatapi.utils.cbv`, `greatapi.utils.inferring_router` | removed — use plain `APIRouter` |
| `greatapi.core.test_auth` | removed |
| `REGISTERED_ADMINS` | `@admin.register` |
| `/admin/{app}/{model}` | `/admin/model/{app}/{model}` |
| `/static/...` | `/admin/_static/...` |

## Why this is worth doing

1.x has defects that cannot be fixed compatibly:

- the JWT signing key was a literal in the source, published with every release
- the admin's only authorization check ran in browser JavaScript, so `curl`
  bypassed it entirely
- the users list rendered bcrypt hashes into the page
- `/admin/change_value` let any signed-in user set `is_admin` on themselves
- login distinguished "no such user" from "wrong password"
- `passlib` is unmaintained and errors against bcrypt 4.x, so new installs got a
  hashing layer that raised

All of these are fixed in 2.0, with a regression test each.

## Stuck?

Open a [discussion](https://github.com/sahajrajmalla/greatapi/discussions) with
your `main.py` and models, and we will help you work out the diff.
