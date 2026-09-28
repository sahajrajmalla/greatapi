"""GreatAPI - the batteries-included FastAPI framework.

Admin, auth, migrations, jobs and streaming out of the box::

    from greatapi import GreatAPI, admin

    app = GreatAPI(title="My Backend")

Install ``greatapi[ai]`` to add LLM providers, a tool-calling agent loop and
token/cost accounting under :mod:`greatapi.ai`.
"""

from __future__ import annotations

__version__ = "2.0.1"

__all__ = [
    "GreatAPI",
    "GreatAPIError",
    "MissingDependencyError",
    "__version__",
    "admin",
    "get_settings",
    "jobs",
    "keys",
    "streaming",
]

from greatapi import admin, jobs, keys, streaming
from greatapi.application import GreatAPI
from greatapi.conf.settings import get_settings
from greatapi.exceptions import GreatAPIError, MissingDependencyError
