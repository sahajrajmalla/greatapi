"""Exception types raised by the framework itself."""

from __future__ import annotations

__all__ = [
    "GreatAPIError",
    "ImproperlyConfigured",
    "MissingDependencyError",
]


class GreatAPIError(Exception):
    """Base class for every error GreatAPI raises."""


class ImproperlyConfigured(GreatAPIError):  # noqa: N818 - matches Django's name
    """Settings are missing or inconsistent, and the app cannot safely start."""


class MissingDependencyError(GreatAPIError, ImportError):
    """An optional feature was used without its optional dependency installed.

    GreatAPI ships the code for every feature in the base wheel and only moves
    third-party SDKs into extras, so reaching for an uninstalled provider raises
    this instead of a bare ``ImportError`` from deep inside an import chain.
    """

    def __init__(self, package: str, extra: str, feature: str) -> None:
        self.package = package
        self.extra = extra
        self.feature = feature
        super().__init__(
            f"{feature} needs the '{package}' package, which is not installed.\n"
            f'Install it with:  pip install "greatapi[{extra}]"'
        )
