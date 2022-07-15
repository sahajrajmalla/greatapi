from __future__ import annotations

from typing import Any

from fastapi import Depends
from fastapi import Form
from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from greatapi.config import GREATAPI_ADMIN_TEMPLATE_PATH
from greatapi.db.database import Base
from greatapi.db.database import get_db
from greatapi.utils.component import fetch_app_list
from greatapi.utils.component import fetch_app_list_with_count
from greatapi.utils.component import fetch_models_by_app
from greatapi.utils.component import fetch_models_by_app_with_count
from greatapi.utils.component import fetch_table_data
from greatapi.utils.component import query_history_table
from greatapi.utils.inferring_router import InferringRouter

admin_router = InferringRouter(tags=['Admin'])
templates = Jinja2Templates(directory=str(GREATAPI_ADMIN_TEMPLATE_PATH))


class AdminSite:
    admin_settings: dict[str, dict[str, Base]] = {}

    @admin_router.get('/admin', response_class=HTMLResponse)
    async def fetch_dashboard_page(self, request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
        items = query_history_table(db)
        apps = fetch_app_list_with_count(self.admin_settings)
        return templates.TemplateResponse(
            'dashboard/index.html',
            {
                'request': request,
                'active': 'dashboard',
                'history_items': items,
                'groups': apps,
            },
        )

    @admin_router.get('/admin/login', response_class=HTMLResponse)
    async def fetch_login_page(self, request: Request) -> HTMLResponse:
        return templates.TemplateResponse('authentication/login.html', {'request': request})

    @admin_router.get('/admin/account', response_class=HTMLResponse)
    async def fetch_account_page(self, request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            'dashboard/account.html', {
                'request': request,
                'user_info': {
                    'name': 'Admin',
                    'username': 'admin',
                    'email': 'admin@site.com',
                    'contact': '980000000',
                },
            },
        )

    @admin_router.get('/admin/settings', response_class=HTMLResponse)
    async def fetch_settings_page(self, request: Request) -> HTMLResponse:
        return templates.TemplateResponse('dashboard/settings.html', {'request': request})

    @admin_router.get('/admin/visualization', response_class=HTMLResponse)
    async def fetch_visualization_page(self, request: Request) -> HTMLResponse:
        return templates.TemplateResponse('dashboard/visualization.html', {'request': request, 'active': 'visualization'})

    @admin_router.get('/admin/history', response_class=HTMLResponse)
    async def fetch_history_page(self, request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
        return templates.TemplateResponse(
            'dashboard/history.html',
            {
                'request': request,
                'active': 'history',
                'history_items': query_history_table(db, 10),
                'params': '?Draft=True',
            },
        )

    @admin_router.get('/admin/delete_user', response_class=HTMLResponse)
    async def fetch_delete_user_page(self, request: Request) -> HTMLResponse:
        return templates.TemplateResponse('dashboard/delete_user.html', {'request': request})

    @admin_router.post('/admin/add_item/test')
    def create_an_item(self, name: str = Form(), price: int = Form(), on_offer: bool = Form()) -> Any:
        # db_item=db.query(models.Item).filter(models.Item.name==item.name).first()

        # if db_item is not None:
        #     raise HTTPException(status_code=400,detail="Item already exists")

        # new_item=models.Item(
        #     name=item.name,
        #     price=item.price,
        #     description=item.description,
        #     on_offer=item.on_offer
        # )

        # db.add(new_item)
        # db.commit()

        return {
            'name': name,
            'price': price,
            'on_offer': on_offer,
        }

    @admin_router.get('/admin/{group_name}/{group_item}', response_class=HTMLResponse)
    async def fetch_model_items_page(self, request: Request, group_name: str, group_item: str) -> HTMLResponse:
        titles, items = fetch_table_data(
            self.admin_settings[group_name.lower()][group_item.lower()],
        )
        sidebar_groups = fetch_models_by_app(self.admin_settings, group_name.lower())

        return templates.TemplateResponse(
            'dashboard/items.html',
            {
                'request': request,
                'active': 'dashboard',
                'group_name': group_name,
                'group_item': group_item,
                'titles': [title.capitalize() for title in titles],
                'items': items,
                'sidebar_groups': sidebar_groups,

                # TODO: need to dynamically change the filters
                'params': '?Draft=True',
            },
        )

    @admin_router.get('/admin/{group_name}/{group_item}/add_item', response_class=HTMLResponse)
    async def fetch_add_item_page(self, request: Request) -> HTMLResponse:

        return templates.TemplateResponse('dashboard/add_item.html', {'request': request})

    @admin_router.get('/admin/{group_name}/{group_item}/{id}', response_class=HTMLResponse)
    async def fetch_details_item_page(self, request: Request, group_name: str, group_item: str, id: str) -> HTMLResponse:
        return templates.TemplateResponse(
            'dashboard/add_item.html',
            {
                'request': request,
                'group_name': group_name,
                'group_item': group_item,
                'id': id,
            },

        )

    @admin_router.get('/admin/{app_name}', response_class=HTMLResponse)
    async def fetch_app_page(self, request: Request, app_name: str) -> HTMLResponse:
        sidebar_groups = fetch_app_list(self.admin_settings)

        items = fetch_models_by_app_with_count(self.admin_settings, app_name.lower())

        return templates.TemplateResponse(
            'dashboard/group.html',
            {
                'request': request,
                'active': 'dashboard',
                'group_name': app_name,
                'items': items,
                'sidebar_groups': sidebar_groups,
            },
        )

    @admin_router.get('/test_me')
    async def fetch_test_me(self, request: Request, db: Session = Depends(get_db)) -> str:
        user = self.admin_settings.get('user')
        print('user ----------------------------------------------')
        print(user)
        print('self ----------------------------------------------')
        print(self.admin_settings)

        print('TABLE NAME: ', user['users'].__tablename__)  # type: ignore

        table_data_key, table_data_values = fetch_table_data(
            self.admin_settings.get(        # type: ignore
                'user',
            ).get('users'),
        )
        print('table_data_key DATA: ', table_data_key)
        print('table_data_values DATA: ', table_data_values)

        app_list = fetch_app_list_with_count(self.admin_settings)
        print('app_list DATA: ', app_list)

        admin_by_app = fetch_models_by_app_with_count(self.admin_settings, 'user')
        print('fetch_models_by_app_with_count DATA: ', admin_by_app)

        history = query_history_table(db)
        print('history DATA: ', history)

        return 'HELLO'
