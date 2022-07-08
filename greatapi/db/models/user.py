from __future__ import annotations

from sqlalchemy import Column
from sqlalchemy import Integer
from sqlalchemy import String

from greatapi.db.database import Base


class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    username = Column(String)
    email = Column(String)
    password = Column(String)
    contact_number = Column(String)
    # blogs = relationship("Blog", back_populates="creator")
