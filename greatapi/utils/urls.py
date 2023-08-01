from __future__ import annotations

import inspect
from typing import Any

from greatapi.db.database import Base

# TODO: Substitute Any with AdminSite class type


def get_route_app(class_name: Any) -> str:
    module_path = inspect.getmodule(class_name).__name__  # type: ignore
    split_by_dot = module_path.split('.')
    return split_by_dot[-2]


def get_route_dict(REGISTERED_ADMINS: list[Any]) -> dict[str, dict[str, Base]]:
    registered_admins: dict[str, dict[str, Base]] = {}

    for admin_class in REGISTERED_ADMINS:
        app_name = get_route_app(admin_class)
        route_url = admin_class.__tablename__.lower()
        if app_name in registered_admins.keys():
            registered_admins[app_name].update({route_url: admin_class})
        else:
            registered_admins[app_name] = {route_url: admin_class}

    return registered_admins
