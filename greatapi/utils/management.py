from __future__ import annotations

import shutil
from pathlib import Path


def copy_files_and_dirs(base_copy_path: Path, base_paste_path: Path, name: str) -> None:
    if not base_paste_path.exists():
        base_paste_path.mkdir(parents=False, exist_ok=False)

    for child in base_copy_path.iterdir():
        child_path = Path(child)
        if child_path.is_dir():
            shutil.copytree(child, base_paste_path.joinpath(name))
        else:
            shutil.copyfile(child, base_paste_path.joinpath(child.name))
