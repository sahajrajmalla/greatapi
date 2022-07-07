from __future__ import annotations

from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy import Integer
from sqlalchemy import String

from greatapi.db.database import Base
# from sqlalchemy import ForeignKey

# from sqlalchemy.orm import relationship


class History(Base):
    __tablename__ = 'history'

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    type = Column(String)
    created_date = Column(DateTime)
    # blogs = relationship("Blog", back_populates="creator")
