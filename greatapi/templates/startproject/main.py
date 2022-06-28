from db.database import engine
from db.models.user import Base
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from src.routers import admin, auth, index, user

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")

Base.metadata.create_all(engine)

app.include_router(admin.router)
app.include_router(index.router)
app.include_router(user.router)
app.include_router(auth.router)
