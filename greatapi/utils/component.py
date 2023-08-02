from __future__ import annotations

from typing import Any
from typing import Optional

from sqlalchemy import cast
from sqlalchemy import func
from sqlalchemy import inspect
from sqlalchemy import or_
from sqlalchemy import select
from sqlalchemy import String
from sqlalchemy.orm import Session

from greatapi.core.history.schemas import HistorySchema
from greatapi.db.admin.default import History
from greatapi.db.admin.user import User
from greatapi.db.database import Base
from greatapi.db.database import engine
# from greatapi.utils.helpers import get_models_count


def fetch_table_data(TABLE_CLASS: Base, page: int = 1, name: Optional[str] = None) -> tuple[list[str], list[dict[str, Any]]]:
    query = select(TABLE_CLASS)

    if name is not None and name != 'all_history':
        # Get all columns in the TABLE_CLASS
        columns = [
            getattr(TABLE_CLASS, c_attr.key)
            for c_attr in inspect(TABLE_CLASS).attrs
        ]

        # Create a list of filter conditions for each column containing the 'name' value
        filter_conditions = [
            cast(column, String).ilike(f'%{name}%') for column in columns
        ]

        # Combine the filter conditions using the 'or_' operator
        query = query.filter(or_(*filter_conditions))

    # Add DISTINCT clause to the query to eliminate duplicate rows
    query = query.distinct()

    # Calculate the offset and limit for pagination
    PAGE_SIZE = 10
    offset = (page - 1) * PAGE_SIZE
    query = query.offset(offset).limit(PAGE_SIZE)

    result = engine.execute(query)

    # Extract specific attributes from the query result and convert them into a list of dictionaries
    keys = result._metadata.keys
    items = [(row) for row in result]

    return (keys, items)


def get_models_count(TABLE_CLASS: Base) -> int:
    query = select([func.count()]).select_from(TABLE_CLASS)
    result = engine.execute(query).scalar()
    return result


def fetch_app_list(admin_settings: dict[str, dict[str, Any]]) -> list[str]:
    return [key.capitalize() for key in admin_settings.keys()]


def fetch_app_list_with_count(admin_settings: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    return [{'name': key.capitalize(), 'total_count': len(values)} for key, values in admin_settings.items() if key != 'default']


def fetch_models_by_app(admin_settings: dict[str, dict[str, Any]], app_name: str) -> list[str]:
    return [key for key in admin_settings[app_name].keys()]


def fetch_models_by_app_with_count(admin_settings: dict[str, dict[str, Any]], app_name: str) -> list[dict[str, Any]]:
    return [{'name': key.capitalize(), 'total_count': get_models_count(values)} for key, values in admin_settings[app_name].items()]


def query_history_table(db: Session, limit: int = 3) -> list[HistorySchema]:
    history = db.query(History).order_by(History.created_date.desc()).limit(limit).all()
    return history


def get_user_by_email(email: str, db: Session) -> User:
    user = db.query(User).filter(User.email == email).first()
    return user
