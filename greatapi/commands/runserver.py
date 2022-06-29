from __future__ import annotations

import subprocess


def server_initialization() -> None:
    subprocess.run(['uvicorn', 'main:app', '--reload'])
