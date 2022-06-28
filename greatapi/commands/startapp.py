from __future__ import annotations

from pathlib import Path

from greatapi.utils.management import copy_files_and_dirs

ROOT_PACKAGE_PATH = Path(__file__).parent.parent


def application_initialization(app_name: str) -> None:
    base_copy_path = ROOT_PACKAGE_PATH.joinpath('templates', 'startapp')
    base_paste_path = Path(app_name)

    copy_files_and_dirs(base_copy_path, base_paste_path, app_name)
