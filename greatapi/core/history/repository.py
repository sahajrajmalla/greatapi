from __future__ import annotations

from datetime import datetime
from datetime import timedelta
from typing import List
from typing import Optional
from typing import Union

from fastapi import HTTPException
from fastapi import status
from sqlalchemy import desc  # Import desc function to use for ordering

from greatapi.core.history.schemas import CategoryEnum
from greatapi.core.history.schemas import HistorySchema
from greatapi.db.admin.default import History
from greatapi.db.database import SessionLocal


def create_history(name: str, category: CategoryEnum, response: bool = False) -> Union[Optional[HistorySchema], None]:
    try:
        db = SessionLocal()
        new_history_item = History(
            name=name,
            category=category,
        )

        # Instead of using 'db.add', use 'db.merge' to associate the instance with the session
        new_history_item = db.merge(new_history_item)

        db.commit()

        # Refresh the instance to get the auto-generated primary key value
        db.refresh(new_history_item)

        if response:
            return new_history_item
        else:
            return None
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Something went wrong while creating history item',
        )
    finally:
        db.close()


def fetch_filtered_paginated_results(page: int = 1, size: int = 10, name: Optional[str] = None, category: Optional[str] = None, date_filter: Optional[str] = None) -> List[HistorySchema]:
    db = SessionLocal()

    query = db.query(History)

    # Calculate the offset and limit for pagination
    offset = (page - 1) * size
    limit = size

    if name is not None and name != 'all_history':
        query = query.filter(History.name.ilike(f'%{name}%'))

    # Filter by category if provided
    if category is not None and category != 'all_category':
        query = query.filter(History.category == category)

    # Calculate the date ranges for the selected date filter
    if date_filter is not None and date_filter != 'all_date':
        if date_filter == 'today':
            today = datetime.today().replace(hour=0, minute=0, second=0, microsecond=0)
            query = query.filter(History.created_date >= today)

        elif date_filter == 'week':
            today = datetime.today()
            week_start = today - timedelta(days=today.weekday())
            week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
            query = query.filter(History.created_date >= week_start)

        elif date_filter == 'month':
            today = datetime.today()
            month_start = today.replace(
                day=1, hour=0, minute=0, second=0, microsecond=0,
            )
            query = query.filter(History.created_date >= month_start)

        elif date_filter == 'year':
            today = datetime.today()
            year_start = today.replace(
                month=1, day=1, hour=0, minute=0, second=0, microsecond=0,
            )
            query = query.filter(History.created_date >= year_start)

    # Order by created_date in descending order
    query = query.order_by(desc(History.created_date))

    # Apply pagination to the query
    query = query.offset(offset).limit(limit)

    # Execute the query and get the search results
    search_results = query.all()

    return search_results
