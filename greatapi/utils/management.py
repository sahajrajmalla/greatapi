import shutil
from pathlib import Path
from typing import Union


def copy_files_and_dirs(base_copy_path: Union[str, Path], base_paste_path: Union[str, Path]) -> None:
    if not base_paste_path.exists():
        base_paste_path.mkdir(parents=False, exist_ok=False)

    for child in base_copy_path.iterdir():
        child_path = Path(child)
        if child_path.is_dir():
            shutil.copytree(child, base_paste_path.joinpath(child.name))
        else:
            shutil.copyfile(child, base_paste_path.joinpath(child.name))
