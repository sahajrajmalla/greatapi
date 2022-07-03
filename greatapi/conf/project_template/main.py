from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from greatapi.config import GREATAPI_ADMIN_STATIC_PATH
from greatapi.db.database import engine
from greatapi.db.models.user import Base
from greatapi.admin.sites import admin_router
from greatapi.admin.sites import AdminSite
from greatapi.utils.cbv import _cbv
from greatapi.core import auth_router, user_router, test_auth_router

app = FastAPI()

app.mount('/static', StaticFiles(directory=GREATAPI_ADMIN_STATIC_PATH), name='static')

Base.metadata.create_all(engine)


class ClassSahaj:
    name = "sahaj"

dummy_str = {"sahaj": ClassSahaj}

admin_site = _cbv(admin_router, AdminSite, dummy_str)



app.include_router(admin_router)
app.include_router(auth_router)
app.include_router(user_router)
app.include_router(test_auth_router)

