from __future__ import annotations

from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from greatapi.config import GREATAPI_ADMIN_TEMPLATE_PATH
from greatapi.db.database import Base
from greatapi.utils.component import fetch_admin_by_app
from greatapi.utils.component import fetch_app_list
from greatapi.utils.component import fetch_table_data
from greatapi.utils.inferring_router import InferringRouter

admin_router = InferringRouter(tags=['Admin'])
templates = Jinja2Templates(directory=str(GREATAPI_ADMIN_TEMPLATE_PATH))


class AdminSite:
    admin_settings: dict[str, dict[str, Base]] = {}

    @admin_router.get('/', response_class=HTMLResponse)
    async def fetch_dashboard_page(self, request: Request) -> HTMLResponse:
        items = [
            {'type': 'edit', 'date': 'Feb 20, 2022'},
            {'type': 'create', 'date': 'Feb 20, 2022'},
        ]
        apps = fetch_app_list(self.admin_settings)
        return templates.TemplateResponse(
            'dashboard/index.html',
            {
                'request': request,
                'active': 'dashboard',
                'history_items': items,
                'groups': apps,
            },
        )

    @admin_router.get('/login', response_class=HTMLResponse)
    async def fetch_login_page(self, request: Request) -> HTMLResponse:
        return templates.TemplateResponse('authentication/login.html', {'request': request})

    @admin_router.get('/account', response_class=HTMLResponse)
    async def fetch_account_page(self, request: Request) -> HTMLResponse:
        return templates.TemplateResponse('dashboard/account.html', {'request': request})

    @admin_router.get('/settings', response_class=HTMLResponse)
    async def fetch_settings_page(self, request: Request) -> HTMLResponse:
        return templates.TemplateResponse('dashboard/settings.html', {'request': request})

    @admin_router.get('/group/group-item/{group_name}/{group_item}', response_class=HTMLResponse)
    async def fetch_model_items_page(self, request: Request, group_name: str, group_item: str) -> HTMLResponse:
        titles = []
        items = []
        sidebar_groups = []

        test_slug = 'this-is-static-slug-make-dynamic'

        if group_item in ['Blogs', 'Categories', 'Comments']:
            sidebar_groups = ['Blogs', 'Categories', 'Comments']
            titles = ['Name', 'Slug', 'Date', 'Is_pinned']
            items = [
                ['The First Blog', 'first-blog', 'Feb 20, 2022', True],
                ['The Second Blog', 'second-blog', 'Feb 20, 2022', False],
            ]
        else:
            sidebar_groups = ['Users']
            titles = ['Name', 'Email', 'Is_superuser']
            items = [
                ['Diwash Lamichhane', 'happiness404@gmail.com', False],
                ['Sahaj Raj Malla', 'sahajakalegend@gmail.com', True],
            ]

        return templates.TemplateResponse(
            'dashboard/items.html',
            {
                'request': request,
                'active': 'dashboard',
                'group_name': group_name,
                'group_item': group_item,
                'titles': titles,
                'items': items,
                'slug': test_slug,
                'sidebar_groups': sidebar_groups,
            },
        )

    @admin_router.get('/add_item', response_class=HTMLResponse)
    async def fetch_add_item_page(self, request: Request) -> HTMLResponse:
        return templates.TemplateResponse('dashboard/add_item.html', {'request': request})

    @admin_router.get('/group/{group_name}', response_class=HTMLResponse)
    async def fetch_app_page(self, request: Request, group_name: str) -> HTMLResponse:
        items = []

        sidebar_groups = ['User', 'Images']

        if group_name == 'User':
            items = [{'name': 'Users', 'total_count': 2}]
        else:
            items = [
                {'name': 'Blogs', 'total_count': 2},
                {'name': 'Categories', 'total_count': 2},
                {'name': 'Comments', 'total_count': 2},
            ]

        return templates.TemplateResponse(
            'dashboard/group.html',
            {
                'request': request,
                'active': 'dashboard',
                'group_name': group_name,
                'items': items,
                'sidebar_groups': sidebar_groups,
            },
        )

    @admin_router.get('/history', response_class=HTMLResponse)
    async def fetch_history_page(self, request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            'dashboard/history.html',
            {
                'request': request,
                'active': 'history',
                'history_items': [{'type': 'edit', 'date': 'Feb 20, 2022'}, {'type': 'create', 'date': 'Feb 20, 2022'}],
            },
        )

    @admin_router.get('/delete_user', response_class=HTMLResponse)
    async def fetch_delete_user_page(self, request: Request) -> HTMLResponse:
        return templates.TemplateResponse('dashboard/delete_user.html', {'request': request})

    @admin_router.get('/visualization', response_class=HTMLResponse)
    async def fetch_visualization_page(self, request: Request) -> HTMLResponse:
        return templates.TemplateResponse('dashboard/visualization.html', {'request': request, 'active': 'visualization'})

    @admin_router.get('/test_me')
    async def fetch_test_me(self, request: Request) -> str:
        user = self.admin_settings.get('user')
        print('user ----------------------------------------------')
        print(user)
        print('self ----------------------------------------------')
        print(self.admin_settings)

        print('TABLE NAME: ', user['users'].__tablename__)  # type: ignore

        table_data = fetch_table_data(
            self.admin_settings.get(        # type: ignore
                'user',
            ).get('users'),
        )
        print('TABLE DATA: ', table_data)
        app_list = fetch_app_list(self.admin_settings)
        print('app_list DATA: ', app_list)

        admin_by_app = fetch_admin_by_app(self.admin_settings, 'user')
        print('admin_by_app DATA: ', admin_by_app)

        return 'HELLO'
