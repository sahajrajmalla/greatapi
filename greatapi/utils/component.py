from __future__ import annotations

from typing import Any

from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy.orm import Session

from greatapi.core.history.schemas import HistorySchema
from greatapi.db.database import Base
from greatapi.db.database import engine
from greatapi.db.models.default import History
# from greatapi.utils.helpers import get_models_count


def fetch_table_data(TABLE_CLASS: Base) -> tuple[list[str], list[dict[str, Any]]]:
    query = select(TABLE_CLASS)
    result = engine.execute(query)
    return (result._metadata.keys, result.fetchall())


def get_models_count(TABLE_CLASS: Base) -> int:
    query = select([func.count()]).select_from(TABLE_CLASS)
    result = engine.execute(query).scalar()
    return result


def fetch_app_list(admin_settings: dict[str, dict[str, Any]]) -> list[str]:
    return [key.capitalize() for key in admin_settings.keys()]


def fetch_app_list_with_count(admin_settings: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    return [{'name': key.capitalize(), 'total_count': len(values)} for key, values in admin_settings.items()]


def fetch_models_by_app(admin_settings: dict[str, dict[str, Any]], app_name: str) -> list[str]:
    return [key for key in admin_settings[app_name].keys()]


def fetch_models_by_app_with_count(admin_settings: dict[str, dict[str, Any]], app_name: str) -> list[dict[str, Any]]:
    return [{'name': key.capitalize(), 'total_count': get_models_count(values)} for key, values in admin_settings[app_name].items()]


def query_history_table(db: Session, limit: int = 3) -> list[HistorySchema]:
    history = db.query(History).order_by(History.created_date.desc()).limit(limit).all()
    return history
