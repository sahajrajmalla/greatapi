from __future__ import annotations


def say_hello(name: str | None = None) -> str:
    if name is None:
        return 'Hello mewow!'
    else:
        return f'Hello, {name}!'
