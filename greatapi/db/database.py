from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()

SQLALCHEMY_DATABASE_URL = "sqlite:///./sql_app.db"

engine = create_engine(SQLALCHEMY_DATABASE_URL, echo=True)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db():
	db = SessionLocal()

	try:
		yield db
	finally:
		db.close()
