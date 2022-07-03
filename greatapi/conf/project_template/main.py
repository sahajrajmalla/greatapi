from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from greatapi.config import GREATAPI_ADMIN_STATIC_PATH
from greatapi.db.database import engine
from greatapi.db.models.user import Base
from greatapi.admin.sites import router
from greatapi.admin.sites import AdminSite
from greatapi.utils.cbv import _cbv

# from greatapi.routers import admin
# from greatapi.routers import auth
# from greatapi.routers import index
# from greatapi.routers import user




app = FastAPI()

app.mount('/static', StaticFiles(directory=GREATAPI_ADMIN_STATIC_PATH), name='static')

Base.metadata.create_all(engine)

# app.include_router(admin.router)
# app.include_router(index.router)
# app.include_router(user.router)
# app.include_router(auth.router)


class ClassSahaj:
    name = "sahaj"

dummy_str = {"sahaj": ClassSahaj}

admin_site = _cbv(router, dummy_str, AdminSite)



app.include_router(router)