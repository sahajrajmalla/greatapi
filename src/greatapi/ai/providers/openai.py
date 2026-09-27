"""OpenAI adapter. Needs ``pip install "greatapi[openai]"``.

Subclasses the httpx-only OpenAI-compatible provider rather than duplicating the
wire format: the only differences are the default base URL, the credential, and
requiring the SDK to be present so users get the error they expect. If you do
not want the SDK at all, use ``local:`` with ``openai_base_url`` pointed at
``https://api.openai.com/v1``.
"""

from __future__ import annotations

from greatapi.ai.providers.base import require
from greatapi.ai.providers.openai_compatible import OpenAICompatibleProvider
from greatapi.conf.settings import get_settings

__all__ = ["OpenAIProvider"]

_OPENAI_BASE_URL = "https://api.openai.com/v1"


class OpenAIProvider(OpenAICompatibleProvider):
    name = "openai"

    def __init__(self, base_url: str | None = None, api_key: str | None = None) -> None:
        require("openai", "openai", "The OpenAI provider")
        settings = get_settings()
        super().__init__(
            base_url=base_url or settings.openai_base_url or _OPENAI_BASE_URL,
            api_key=api_key,
        )
