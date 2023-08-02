from __future__ import annotations

from typing import List
from typing import Optional

from fastapi import Depends
from fastapi import HTTPException
from fastapi import Query
from fastapi import status
from sqlalchemy.orm import Session

from greatapi.core.history.repository import create_history
from greatapi.core.history.repository import fetch_filtered_paginated_results
from greatapi.core.history.schemas import CategoryEnum
from greatapi.core.history.schemas import HistoryCreateSchema
from greatapi.core.history.schemas import HistorySchema
from greatapi.db.database import get_db
from greatapi.db.database import SessionLocal
from greatapi.utils.cbv import cbv
from greatapi.utils.inferring_router import InferringRouter

history_router = InferringRouter(tags=['History'])


@cbv(history_router)
class HistorySite:
    db = SessionLocal()

    @history_router.get('/get_all_history', response_model=List[HistorySchema], status_code=200)
    def get_all_history(
        self,
        page: int = Query(1, ge=1),
        size: int = Query(10, ge=1, le=100),
        db: Session = Depends(get_db),
    ) -> List[HistorySchema]:
        try:
            paginated_results = fetch_filtered_paginated_results(page=page, size=size)
            return paginated_results

        except Exception as e:
            # Return an error response if something goes wrong
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e),
            )
        finally:
            db.close()

    @history_router.post('/create_history', response_model=HistorySchema, status_code=status.HTTP_201_CREATED)
    def create_an_item(self, item: HistoryCreateSchema) -> Optional[HistorySchema]:
        new_history = create_history(
            name=item.name, category=item.category, response=True,
        )
        return new_history

    # API endpoint to search history items with date filters
    @history_router.get('/history/search/', response_model=List[HistorySchema], status_code=status.HTTP_200_OK)
    def search_history(
        self,
        page: int = Query(1, ge=1),
        size: int = Query(10, ge=1, le=100),
        db: Session = Depends(get_db),
        name: Optional[str] = Query(None, max_length=100),
        category: Optional[CategoryEnum] = Query(None),
        date_filter: Optional[str] = Query(None, max_length=50),
    ) -> List[HistorySchema]:
        try:
            search_result = fetch_filtered_paginated_results(
                page=page, size=size, name=name, category=category, date_filter=date_filter,
            )
            return search_result

        except Exception as e:
            # Return an error response if something goes wrong
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e),
            )
        finally:
            db.close()
