from pathlib import Path

from greatapi.utils.management import copy_files_and_dirs

ROOT_PACKAGE_PATH = Path(__file__).parent.parent


def project_initialization(project_name: str) -> None:
    base_copy_path = ROOT_PACKAGE_PATH.joinpath("templates", "startproject")
    base_paste_path = Path(project_name)

    copy_files_and_dirs(base_copy_path, base_paste_path)
