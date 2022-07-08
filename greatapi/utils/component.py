from __future__ import annotations

from typing import Any

import sqlalchemy
from sqlalchemy.orm import Session

from greatapi.core.history.schemas import HistorySchema
from greatapi.db.database import Base
from greatapi.db.database import engine
from greatapi.db.models.default import History


def fetch_table_data(TABLE_CLASS: Base) -> list[dict[str, str]]:
    query = sqlalchemy.select(TABLE_CLASS)
    result = engine.execute(query).fetchall()
    result_dict = [record._mapping for record in result]
    return result_dict


def fetch_app_list(admin_settings: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    return [{'name': key.capitalize(), 'total_count': len(values)} for key, values in admin_settings.items()]


def fetch_admin_by_app(admin_settings: dict[str, dict[str, Any]], app_name: str) -> list[str]:
    return [key for key in admin_settings[app_name]]


def query_history_table(db: Session, limit: int = 3) -> list[HistorySchema]:
    history = db.query(History).order_by(History.created_date.desc()).limit(limit).all()
    return history
