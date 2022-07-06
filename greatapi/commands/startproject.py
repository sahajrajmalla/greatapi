from __future__ import annotations

from pathlib import Path

from greatapi.config import ROOT_PACKAGE_PATH
from greatapi.utils.management import setup_project_template


def project_initialization(project_name: str) -> None:
    base_copy_path = ROOT_PACKAGE_PATH.joinpath('conf', 'project_template')
    base_paste_path = Path('.')

    setup_project_template(base_copy_path, base_paste_path, project_name)
