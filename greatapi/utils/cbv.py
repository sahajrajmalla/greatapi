from __future__ import annotations

import inspect
from typing import Any
from typing import Callable
from typing import TypeVar

from fastapi import APIRouter
from fastapi import Depends
from starlette.routing import Route
from starlette.routing import WebSocketRoute

from greatapi.db.database import Base
from greatapi.db.models.user import User
# from typing import get_type_hints
# from pydantic.typing import is_classvar

T = TypeVar('T')

CBV_CLASS_KEY = '__cbv_class__'
DEFAULT_ADMIN_SETTINGS = {'user': {'users': User}}


def cbv(router: APIRouter) -> Callable[[type[T]], type[T]]:
    """
    This function returns a decorator that converts the decorated into a class-based view for the provided router.
    Any methods of the decorated class that are decorated as endpoints using the router provided to this function
    will become endpoints in the router. The first positional argument to the methods (typically `self`)
    will be populated with an instance created using FastAPI's dependency-injection.
    For more detail, review the documentation at
    https://fastapi-utils.davidmontague.xyz/user-guide/class-based-views/#the-cbv-decorator
    """

    def decorator(cls: type[T]) -> type[T]:
        return _cbv(router, cls)

    return decorator


def _cbv(router: APIRouter, cls: type[T], admin_settings: dict[str, dict[str, Base]] = DEFAULT_ADMIN_SETTINGS) -> type[T]:
    """
    Replaces any methods of the provided class `cls` that are endpoints of routes in `router` with updated
    function calls that will properly inject an instance of `cls`.
    """
    _init_cbv(admin_settings, cls)
    cbv_router = APIRouter()
    function_members = inspect.getmembers(cls, inspect.isfunction)
    functions_set = {func for _, func in function_members}
    cbv_routes = [
        route
        for route in router.routes
        if isinstance(route, (Route, WebSocketRoute)) and route.endpoint in functions_set
    ]
    for route in cbv_routes:
        router.routes.remove(route)
        _update_cbv_route_endpoint_signature(cls, route)
        cbv_router.routes.append(route)
    router.include_router(cbv_router)
    return cls


def _init_cbv(admin_settings: dict[str, dict[str, Base]], cls: type[Any]) -> None:
    """
    Idempotently modifies the provided `cls`, performing the following modifications:
    * The `__init__` function is updated to set any class-annotated dependencies as instance attributes
    * The `__signature__` attribute is updated to indicate to FastAPI what arguments should be passed to the initializer
    """
    if getattr(cls, CBV_CLASS_KEY, False):  # pragma: no cover
        return  # Already initialized
    old_init: Callable[..., Any] = cls.__init__
    old_signature = inspect.signature(old_init)
    old_parameters = list(old_signature.parameters.values())[
        1:
    ]  # drop `self` parameter
    new_parameters = [
        x for x in old_parameters if x.kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
    ]
    dependency_names: list[str] = []
    # for name, hint in get_type_hints(cls).items():
    #     if is_classvar(hint):
    #         continue
    #     parameter_kwargs = {'default': getattr(cls, name, Ellipsis)}
    #     dependency_names.append(name)
    #     new_parameters.append(
    #         inspect.Parameter(
    #             name=name, kind=inspect.Parameter.KEYWORD_ONLY,
    #             annotation=hint, **parameter_kwargs,
    #         ),
    #     )
    new_signature = old_signature.replace(parameters=new_parameters)

    def new_init(self: Any, *args: Any, **kwargs: Any) -> None:
        for dep_name in dependency_names:
            dep_value = kwargs.pop(dep_name)
            setattr(self, dep_name, dep_value)
        old_init(self, *args, **kwargs)

    setattr(cls, '__signature__', new_signature)
    setattr(cls, '__init__', new_init)
    setattr(cls, CBV_CLASS_KEY, True)
    setattr(cls, 'admin_settings', admin_settings)


def _update_cbv_route_endpoint_signature(cls: type[Any], route: Route | WebSocketRoute) -> None:
    """
    Fixes the endpoint signature for a cbv route to ensure FastAPI performs dependency injection properly.
    """
    try:
        old_endpoint = route.endpoint
        old_signature = inspect.signature(old_endpoint)
        old_parameters: list[inspect.Parameter] = list(
            old_signature.parameters.values(),
        )
        old_first_parameter = old_parameters[0]
        new_first_parameter = old_first_parameter.replace(default=Depends(cls))
        new_parameters = [new_first_parameter] + [
            parameter.replace(kind=inspect.Parameter.KEYWORD_ONLY) for parameter in old_parameters[1:]
        ]
        new_signature = old_signature.replace(parameters=new_parameters)
        setattr(route.endpoint, '__signature__', new_signature)
    except Exception as e:
        print('Exception Occurred while updating cbv endpoints with msg:', e)
