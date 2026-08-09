# The admin

Register a model and you get a list view, search, pagination, an edit form
generated from your columns, and delete — with an audit trail.

```python title="blog/admin.py"
from greatapi import admin
from blog.models import Post

@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "author", "published", "created_at")
    search_fields = ("title", "body")
    readonly_fields = ("created_at", "updated_at")
    ordering = "-created_at"
```

Any app in `INSTALLED_APPS` has its `admin.py` imported automatically, so that
is all the wiring there is.

## Options

| Option | Default | What it does |
|---|---|---|
| `list_display` | every safe column | Columns in the list view |
| `search_fields` | `()` | Columns the search box looks at. Empty hides it |
| `fields` | every editable column | Columns on the edit form |
| `readonly_fields` | `()` | Shown but never written |
| `exclude` | `()` | Hidden everywhere |
| `app_label` | the defining package | Sidebar grouping |
| `ordering` | `"-id"` | Default sort; `-` for descending |
| `can_create` / `can_edit` / `can_delete` | `True` | Available actions |
| `page_size` | `admin_page_size` | Rows per page |

## Credentials are never rendered

Columns are opt-in, and any name matching `password`, `secret`, `token`,
`hashed`, `salt`, `_key`, `credential` or `private` is redacted, excluded from
search, and not writable — even if you name it in `list_display` or `fields`.

That is two independent defences, because in 1.x the admin rendered every column
of every registered table: the users list displayed bcrypt hashes in the
browser, and the search box ran `ILIKE` across them.

```python
class RecklessAdmin(admin.ModelAdmin):
    fields = ("username", "hashed_password")   # the second is ignored
```

To set a password, use the dedicated action on the user's page, or
`greatapi createsuperuser`. There is no code path that writes a password through
the generic form, so there is none that can store one unhashed.

## Models you cannot create here

If a model has a required column the admin cannot write — a `User` needs a
password, and a password is never writable — the Add button is hidden and the
route explains why, rather than failing on a `NOT NULL` constraint.

## Everything is authenticated on the server

Every admin view sits behind a router-level `require_admin`, so a view added
tomorrow is protected by default rather than by remembering to protect it.

- Sessions are signed, `HttpOnly`, `SameSite=Lax` cookies. Nothing readable by
  JavaScript, so an XSS cannot lift the session.
- The CSRF token lives inside the signed session, so the double-submit check
  compares a value the client cannot forge against one it cannot read.
- Login is rate-limited per client and answers identically for an unknown user,
  a wrong password and a deactivated account.
- Every admin response carries a strict `Content-Security-Policy` — possible
  because no asset comes from a CDN.

## Configuration

```bash
GREATAPI_ADMIN_ENABLED=true
GREATAPI_ADMIN_PATH=/admin      # move it, or hide it behind a proxy
GREATAPI_ADMIN_TITLE=Acme
GREATAPI_ADMIN_PAGE_SIZE=25
```

```python
app = GreatAPI(title="myapp", admin=False)   # or turn it off entirely
```

## Customising the look

The stylesheet is one file, `greatapi/admin/static/greatapi.css`, hand-written
with no build step. Colours are CSS custom properties at the top:

```css
:root {
  --accent: #4f46e5;
  --radius: 10px;
}
```

Override the templates by pointing Jinja at your own directory ahead of the
bundled one:

```python
from greatapi.admin.templating import templates

templates.env.loader.searchpath.insert(0, "mytemplates")
```

Two rules to keep, because they are what makes the admin work offline and under
a strict CSP: no external requests, and no inline scripts, styles or event
handlers.
