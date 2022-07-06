from __future__ import annotations

from pathlib import Path

from greatapi.config import ROOT_PACKAGE_PATH
from greatapi.utils.management import setup_app_template


def application_initialization(app_name: str) -> None:
    base_copy_path = ROOT_PACKAGE_PATH.joinpath('conf', 'app_template')
    base_paste_path = Path(app_name)

    setup_app_template(base_copy_path, base_paste_path, app_name)
