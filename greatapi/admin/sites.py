from __future__ import annotations

from typing import Any
from typing import Dict
from typing import Optional
from typing import Union

from fastapi import Depends
from fastapi import Form
from fastapi import HTTPException
from fastapi import Query
from fastapi import Request
from fastapi import status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from jose import jwt
from jose.exceptions import ExpiredSignatureError
from jose.exceptions import JWTError
from sqlalchemy.orm import Session

from greatapi.config import GREATAPI_ADMIN_TEMPLATE_PATH
from greatapi.core.auth.hashing import Hash
from greatapi.core.auth.jwt_token import ALGORITHM
from greatapi.core.auth.jwt_token import SECRET_KEY
from greatapi.core.history.repository import create_history
from greatapi.core.history.repository import fetch_filtered_paginated_results
from greatapi.core.history.schemas import CategoryEnum
from greatapi.db.database import Base
from greatapi.db.database import get_db
from greatapi.utils.component import fetch_app_list
from greatapi.utils.component import fetch_app_list_with_count
from greatapi.utils.component import fetch_models_by_app
from greatapi.utils.component import fetch_models_by_app_with_count
from greatapi.utils.component import fetch_table_data
from greatapi.utils.component import get_user_by_email
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
    async def fetch_history_page(
        self,
        request: Request,
        page: int = Query(1, ge=1),
        db: Session = Depends(get_db),
        name: Optional[str] = Query(None, max_length=100),
        category: Optional[str] = Query(None),
        date_filter: Optional[str] = Query(None, max_length=50),
    ) -> HTMLResponse:
        PAGE_SIZE = 10
        return templates.TemplateResponse(
            'dashboard/history.html',
            {
                'request': request,
                'active': 'history',
                'history_items': fetch_filtered_paginated_results(
                    page, PAGE_SIZE, name, category, date_filter,
                ),
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
    async def fetch_model_items_page(
        self,
        request: Request,
        group_name: str,
        group_item: str,
        page: int = Query(1, ge=1),
        name: Optional[str] = Query(None, max_length=100),
    ) -> HTMLResponse:

        titles, items = fetch_table_data(
            self.admin_settings[group_name.lower()][group_item.lower()],
            page,
            name,
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
                'sidebar_groups': [groups.capitalize() for groups in sidebar_groups],
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

    def is_user_admin(self, email: str, db: Session) -> bool:
        user = get_user_by_email(email, db)
        if user and user.is_admin:  # Assuming there is an "is_admin" property in the User model
            return True
        return False

    @admin_router.post('/admin/check_admin')
    def check_admin(self, access_token: str = Form(...), db: Session = Depends(get_db)) -> Dict[str, Union[bool, str]]:
        try:
            decoded_token = jwt.decode(access_token, SECRET_KEY, algorithms=[ALGORITHM])
            email = decoded_token.get('sub')
            if email:
                is_admin = self.is_user_admin(email, db)
                return {'is_admin': is_admin}
        except ExpiredSignatureError:
            return {'is_admin': False, 'error': 'Token has expired.'}
        except JWTError:
            return {'is_admin': False, 'error': 'Invalid token.'}
        except Exception as e:
            print('Error:', e)
        return {'is_admin': False}

    @admin_router.post('/admin/info')
    def fetch_admin_info(self, access_token: str = Form(...), db: Session = Depends(get_db)) -> Dict[str, Union[bool, str]]:
        try:
            decoded_token = jwt.decode(access_token, SECRET_KEY, algorithms=[ALGORITHM])
            email = decoded_token.get('sub')
            if email:
                is_admin = self.is_user_admin(email, db)
                if is_admin:
                    user = get_user_by_email(email, db)
                    return user
        except ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail='Token has expired.',
            )
        except JWTError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid token.',
            )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='Access denied. Only admin users are allowed.',
        )

    @admin_router.post('/admin/change_password')
    def change_password(
        self,
        access_token: str = Form(...),
        old_password: str = Form(...),
        new_password: str = Form(...),
        db: Session = Depends(get_db),
    ) -> dict[str, bool]:
        try:
            decoded_token = jwt.decode(access_token, SECRET_KEY, algorithms=[ALGORITHM])
            email = decoded_token.get('sub')
            if email:
                user = get_user_by_email(email, db)
                if user and Hash.verify(user.password, old_password):
                    # Assuming you have a method Hash.bcrypt() to hash the password
                    user.password = Hash.bcrypt(new_password)
                    db.commit()

                    create_history(
                        name=f"{email}'s password changed successfully.", category=CategoryEnum.edit,
                    )

                    return {'password_changed': True}
        except ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail='Token has expired.',
            )
        except JWTError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid token.',
            )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='Access denied or old password incorrect.',
        )

    @admin_router.post('/admin/delete_user')
    def delete_user(self, access_token: str = Form(...), db: Session = Depends(get_db)) -> dict[str, bool]:
        try:
            decoded_token = jwt.decode(access_token, SECRET_KEY, algorithms=[ALGORITHM])
            email = decoded_token.get('sub')
            if email:
                user = get_user_by_email(email, db)
                if user and self.is_user_admin(email, db):
                    db.delete(user)
                    db.commit()
                    create_history(
                        name=f"{email}'s user deleted successfully.", category=CategoryEnum.delete,
                    )
                    return {'user_deleted': True}
                else:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail='Access denied or user not found.',
                    )
        except ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail='Token has expired.',
            )
        except JWTError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid token.',
            )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='Access denied or user not found.',
        )

    @admin_router.post('/admin/change_value')
    async def change_value(self, request: Request, db: Session = Depends(get_db)) -> dict[str, bool]:
        try:
            # Parse the JSON payload from the request body
            fields = await request.json()
            print('fields DATA: ', fields)
            access_token = fields.get('access_token')
            if access_token:
                decoded_token = jwt.decode(
                    access_token, SECRET_KEY, algorithms=[ALGORITHM],
                )
                email = decoded_token.get('sub')
                if email:
                    user = get_user_by_email(email, db)
                    if user:
                        for field, new_value in fields.items():
                            if field in user.__dict__ and field != 'access_token':
                                setattr(user, field, new_value)
                        db.commit()
                        create_history(
                            name=f"{email}'s field changed successfully.", category=CategoryEnum.edit,
                        )
                        return {'values_changed': True}
                    else:
                        raise HTTPException(
                            status_code=status.HTTP_404_NOT_FOUND, detail='User not found.',
                        )
        except ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail='Token has expired.',
            )
        except JWTError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid token.',
            )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='Access denied.',
        )
