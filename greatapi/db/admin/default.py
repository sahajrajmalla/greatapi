from __future__ import annotations

from enum import Enum

from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy import Enum as SQLAlchemyEnum
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy.sql import func

from greatapi.db.database import Base
# from sqlalchemy import ForeignKey
# from sqlalchemy.orm import relationship


class CategoryEnum(str, Enum):
    edit = 'edit'
    create = 'create'
    delete = 'delete'


class History(Base):
    __tablename__ = 'history'

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String)
    category = Column(SQLAlchemyEnum(CategoryEnum))
    created_date = Column(DateTime(timezone=True), server_default=func.now())

    # blogs = relationship("Blog", back_populates="creator")
