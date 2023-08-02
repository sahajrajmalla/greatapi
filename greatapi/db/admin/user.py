from __future__ import annotations

from sqlalchemy import Boolean  # Add this import for the new field
from sqlalchemy import Column
from sqlalchemy import Integer
from sqlalchemy import String

from greatapi.db.database import Base


class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String)
    username = Column(String)
    email = Column(String)
    password = Column(String)
    contact_number = Column(String)
    # Add the is_admin field with a default value of False
    is_admin = Column(Boolean, default=False)
    # blogs = relationship("Blog", back_populates="creator")
