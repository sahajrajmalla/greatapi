# CLI

```bash
greatapi --help
greatapi --version
```

Run commands from your project root — the directory containing `main.py`.

## Scaffolding

### `startproject`

```bash
greatapi startproject myapp
greatapi startproject myapp --directory /srv/myapp
```

Writes a project that runs: `main.py` with root and health endpoints, a settings
module holding `INSTALLED_APPS`, Alembic wiring, a `.gitignore`, a README, and a
`.env.example` carrying a freshly generated secret key.

The name must be a valid Python identifier, not a keyword, and not something
that would shadow a framework module.

### `startapp`

```bash
greatapi startapp blog
```

Writes a working vertical slice — model, schemas, repository, router and admin
registration — and adds the app to `INSTALLED_APPS`, so it serves requests and
appears in the admin without another edit.

### `generate-secret`

```bash
greatapi generate-secret
export GREATAPI_SECRET_KEY="$(greatapi generate-secret)"
```

## Running

### `runserver`

```bash
greatapi runserver
greatapi runserver --host 0.0.0.0 --port 8080 --no-reload
greatapi runserver --workers 4              # reload turns off
greatapi runserver --app myapp.main:app
```

Calls uvicorn in-process rather than shelling out, so an import error in your
app is a real traceback.

For production, run uvicorn or gunicorn directly — see
[Deployment](deployment.md).

### `routes`

```bash
greatapi routes
```

```
GET                    /admin                          dashboard
POST                   /admin/login                    login_submit
GET                    /blog/items                     read_items
GET                    /jobs/{job_id}                  read_job
```

## Database

```bash
greatapi makemigrations -m "add posts"
greatapi makemigrations --empty -m "backfill slugs"
greatapi migrate
greatapi migrate <revision>
greatapi downgrade -1
greatapi downgrade base
greatapi history
```

## Users

```bash
greatapi createsuperuser
```

Prompts for email, username, name and password. For CI and container
entrypoints:

```bash
greatapi createsuperuser --noinput \
  --email admin@example.com --username admin --password "$ADMIN_PASSWORD"
```

or from the environment:

```bash
export GREATAPI_SUPERUSER_EMAIL=admin@example.com
export GREATAPI_SUPERUSER_USERNAME=admin
export GREATAPI_SUPERUSER_PASSWORD=...
greatapi createsuperuser --noinput
```

It creates the schema if it is missing, so it works on a fresh database, and
refuses a duplicate email or username.

## Without the console script

```bash
python -m greatapi.cli runserver
```

Useful in containers, or against a checkout that is not installed.
