from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from greatapi.config import GREATAPI_ADMIN_STATIC_PATH
from greatapi.db.database import engine
from greatapi.db.models.user import Base
from greatapi.routers import admin, auth, index, user

app = FastAPI()

app.mount("/static", StaticFiles(directory=GREATAPI_ADMIN_STATIC_PATH), name="static")

Base.metadata.create_all(engine)

app.include_router(admin.router)
app.include_router(index.router)
app.include_router(user.router)
app.include_router(auth.router)
