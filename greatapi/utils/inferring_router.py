from __future__ import annotations

from typing import Any
from typing import Callable
from typing import get_type_hints
from typing import TYPE_CHECKING

from fastapi import APIRouter
from fastapi.responses import HTMLResponse


class InferringRouter(APIRouter):
    """
    Overrides the route decorator logic to use the annotated return type as the `response_model` if unspecified.
    """

    if not TYPE_CHECKING:  # pragma: no branch

        def add_api_route(self, path: str, endpoint: Callable[..., Any], **kwargs: Any) -> None:
            if kwargs.get('response_model') is HTMLResponse:
                kwargs['response_model'] = get_type_hints(endpoint).get('return')
            return super().add_api_route(path, endpoint, **kwargs)
