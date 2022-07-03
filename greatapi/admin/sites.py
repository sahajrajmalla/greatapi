from __future__ import annotations
from greatapi.utils.inferring_router import InferringRouter

from typing import Any
from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from greatapi.config import GREATAPI_ADMIN_TEMPLATE_PATH

router = InferringRouter(prefix='', tags=['Admin'])
templates = Jinja2Templates(directory=str(GREATAPI_ADMIN_TEMPLATE_PATH))

class AdminSite:
    @router.get('/', response_class=HTMLResponse)
    async def fetch_dashboard_page(self, request: Request) -> HTMLResponse:
        items = [
            {'type': 'edit', 'date': 'Feb 20, 2022'},
            {'type': 'create', 'date': 'Feb 20, 2022'},
        ]
        groups = [{'name': 'User', 'total_count': 2}, {'name': 'Images', 'total_count': 2}]
        return templates.TemplateResponse(
            'dashboard/index.html',
            {
                'request': request,
                'active': 'dashboard',
                'history_items': items,
                'groups': groups,
            },
        )


    @router.get('/login', response_class=HTMLResponse)
    async def fetch_login_page(self, request: Request) -> HTMLResponse:
        return templates.TemplateResponse('authentication/login.html', {'request': request})


    @router.get('/account', response_class=HTMLResponse)
    async def fetch_account_page(self, request: Request) -> HTMLResponse:
        return templates.TemplateResponse('dashboard/account.html', {'request': request})


    @router.get('/settings', response_class=HTMLResponse)
    async def fetch_settings_page(self, request: Request) -> HTMLResponse:
        return templates.TemplateResponse('dashboard/settings.html', {'request': request})


    @router.get('/group/group-item/{group_name}/{group_item}', response_class=HTMLResponse)
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


    @router.get('/add_item', response_class=HTMLResponse)
    async def fetch_add_item_page(self, request: Request) -> HTMLResponse:
        return templates.TemplateResponse('dashboard/add_item.html', {'request': request})


    @router.get('/group/{group_name}', response_class=HTMLResponse)
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


    @router.get('/history', response_class=HTMLResponse)
    async def fetch_history_page(self, request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            'dashboard/history.html',
            {
                'request': request,
                'active': 'history',
                'history_items': [{'type': 'edit', 'date': 'Feb 20, 2022'}, {'type': 'create', 'date': 'Feb 20, 2022'}],
            },
        )


    @router.get('/delete_user', response_class=HTMLResponse)
    async def fetch_delete_user_page(self, request: Request) -> HTMLResponse:
        return templates.TemplateResponse('dashboard/delete_user.html', {'request': request})


    @router.get('/visualization', response_class=HTMLResponse)
    async def fetch_visualization_page(self, request: Request) -> HTMLResponse:
        return templates.TemplateResponse('dashboard/visualization.html', {'request': request, 'active': 'visualization'})
