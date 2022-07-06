from __future__ import annotations

from typing import Any

import sqlalchemy

from greatapi.db.database import Base
from greatapi.db.database import engine


def fetch_table_data(TABLE_CLASS: Base) -> list[dict[str, str]]:
    query = sqlalchemy.select(TABLE_CLASS)
    result = engine.execute(query).fetchall()
    result_dict = [record._mapping for record in result]
    return result_dict


def fetch_app_list(admin_settings: dict[str, dict[str, Any]]) -> list[str]:
    return [key for key in admin_settings.keys()]


def fetch_admin_by_app(admin_settings: dict[str, dict[str, Any]], app_name: str) -> list[str]:
    return [key for key in admin_settings[app_name]]
