"""Project and app generation.

The 1.x version called ``mkdir(exist_ok=False)`` and let ``FileExistsError``
reach the terminal, and accepted any string as a name -- including Python
keywords and paths with separators in them, which produced a project that could
not be imported.
"""

from __future__ import annotations

import keyword
import re
import secrets
from pathlib import Path

from greatapi.conf.settings import PACKAGE_DIR
from greatapi.exceptions import GreatAPIError

__all__ = [
    "APP_TEMPLATE_DIR",
    "PROJECT_TEMPLATE_DIR",
    "generate_secret_key",
    "register_app",
    "render_tree",
    "validate_name",
]

PROJECT_TEMPLATE_DIR = PACKAGE_DIR / "conf" / "project_template"
APP_TEMPLATE_DIR = PACKAGE_DIR / "conf" / "app_template"

TEMPLATE_SUFFIX = ".py-tpl"
GENERIC_SUFFIX = "-tpl"

#: The scaffolding needs four substitutions and no logic, so it does them by
#: name rather than running a template engine.
#:
#: Jinja would mean choosing an autoescape setting, and the only correct choice
#: here is "off" -- these files are Python source, a .env and an alembic.ini, so
#: HTML-escaping a quote in a docstring would produce a project that does not
#: parse. Rather than carry a permanently-disabled safety feature and explain it
#: forever, there is no engine: no expression evaluation, and so no template
#: injection to reason about. `string.Template` is avoided for the same reason
#: in miniature -- alembic.ini contains `%` and `$` that it would misread.
PLACEHOLDERS = ("project_name", "app_name", "app_name.capitalize()", "secret_key")

#: Names that would shadow the framework or a standard module the templates use.
RESERVED_NAMES = {
    "greatapi",
    "fastapi",
    "starlette",
    "pydantic",
    "sqlalchemy",
    "alembic",
    "migrations",
    "test",
    "tests",
    "main",
    "admin",
    "models",
    "router",
    "schemas",
    "settings",
}


def validate_name(name: str, kind: str = "project") -> str:
    """Check that ``name`` can be a Python package, or explain why not."""
    if not name:
        raise GreatAPIError(f"A {kind} name is required.")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        raise GreatAPIError(
            f"{name!r} is not a valid {kind} name. Use letters, digits and "
            "underscores, starting with a letter or underscore."
        )
    if keyword.iskeyword(name):
        raise GreatAPIError(f"{name!r} is a Python keyword and cannot be a {kind} name.")
    if name.lower() in RESERVED_NAMES:
        raise GreatAPIError(
            f"{name!r} would shadow a module GreatAPI needs. Pick a different {kind} name."
        )
    return name


def generate_secret_key() -> str:
    """A signing key with 64 bytes of entropy."""
    return secrets.token_urlsafe(64)


def render_tree(source: Path, destination: Path, context: dict[str, str]) -> list[Path]:
    """Copy a template tree, rendering each file through Jinja.

    A trailing ``-tpl`` is stripped from the output name. Templates carry it so
    the source tree holds no importable ``.py`` and no ``.gitignore`` that would
    take effect inside this repository.

    ``.mako`` files are copied verbatim: they are Alembic's own templates, and
    rendering them here would consume the placeholders Alembic needs later.

    Path segments named after the project (``project_name``, ``app_name``) are
    renamed, so the generated package takes the user's name.
    """
    written: list[Path] = []
    destination.mkdir(parents=True, exist_ok=True)

    for entry in sorted(source.iterdir()):
        target_name = _output_name(entry.name, context)

        if entry.is_dir():
            written.extend(render_tree(entry, destination / target_name, context))
            continue

        raw = entry.read_text()
        content = raw if entry.suffix == ".mako" else _substitute(raw, context, entry)

        target = destination / target_name
        target.write_text(content)
        written.append(target)

    return written


def _substitute(raw: str, context: dict[str, str], source: Path) -> str:
    """Replace every ``{{ name }}`` placeholder, and refuse to leave one behind.

    An unrecognised placeholder means a typo in a template, which would
    otherwise ship to the user as literal ``{{ whatever }}`` in their new
    project. Failing here turns that into a bug we catch instead of one they do.
    """
    values = dict(context)
    if "app_name" in values:
        values["app_name.capitalize()"] = values["app_name"].capitalize()

    content = raw
    for name in PLACEHOLDERS:
        if name in values:
            content = content.replace("{{ " + name + " }}", values[name])

    leftover = re.search(r"\{\{\s*([^}]+?)\s*\}\}", content)
    if leftover is not None:
        raise GreatAPIError(
            f"{source.name} uses an unknown placeholder {{{{ {leftover.group(1)} }}}}. "
            f"Known placeholders: {', '.join(PLACEHOLDERS)}."
        )
    return content


def _output_name(name: str, context: dict[str, str]) -> str:
    for placeholder in ("project_name", "app_name"):
        if placeholder in context:
            name = name.replace(placeholder, context[placeholder])
    if name.endswith(TEMPLATE_SUFFIX):
        name = name[: -len(TEMPLATE_SUFFIX)] + ".py"
    elif name.endswith(GENERIC_SUFFIX):
        name = name[: -len(GENERIC_SUFFIX)]
    return name


def register_app(settings_file: Path, app_name: str) -> bool:
    """Add ``app_name`` to INSTALLED_APPS. Returns False if already present.

    This is the difference between ``startapp`` producing files you then have to
    wire up by hand and producing an app that is already running.
    """
    if not settings_file.exists():
        return False

    source = settings_file.read_text()
    if re.search(rf'^\s*["\']{re.escape(app_name)}["\']\s*,', source, re.MULTILINE):
        return False

    match = re.search(r"^INSTALLED_APPS\s*(?::[^=]+)?=\s*\[", source, re.MULTILINE)
    if match is None:
        return False

    insert_at = match.end()
    updated = f'{source[:insert_at]}\n    "{app_name}",{source[insert_at:]}'
    settings_file.write_text(updated)
    return True
