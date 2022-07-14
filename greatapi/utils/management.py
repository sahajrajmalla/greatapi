from __future__ import annotations

from pathlib import Path

from jinja2 import Template


def jinja_tpl_to_py(input_file_name: str, base_copy_path: Path, base_paste_path: Path, name: str, type: str) -> None:
    if '.py-tpl' in input_file_name:
        output_file_name = input_file_name.replace('-tpl', '')

        with open(base_copy_path.joinpath(input_file_name)) as input_template:
            template_file_content = Template(input_template.read())

        if type == 'startproject':
            jinja_template = template_file_content.render(project_name=name)
        elif type == 'startapp':
            jinja_template = template_file_content.render()
        else:
            raise Exception('Unknown type')

        with open(base_paste_path.joinpath(output_file_name), 'w+') as output_template:
            output_template.write(jinja_template)
    else:
        pass


def setup_app_template(base_copy_path: Path, base_paste_path: Path, app_name: str) -> None:
    setup_type = 'startapp'

    if not base_paste_path.exists():
        base_paste_path.mkdir(parents=False, exist_ok=False)

    for child in base_copy_path.iterdir():
        child_path = Path(child)
        jinja_tpl_to_py(
            child_path.name, base_copy_path,
            base_paste_path, app_name, setup_type,
        )


def setup_project_template(base_copy_path: Path, base_paste_path: Path, project_name: str) -> None:
    setup_type = 'startproject'
    paste_project_path = base_paste_path.joinpath(project_name)

    if not paste_project_path.exists():
        paste_project_path.mkdir(parents=False, exist_ok=False)

    for child in base_copy_path.iterdir():
        child_path = Path(child)
        if child_path.is_dir():
            for inner_child in child_path.iterdir():
                inner_child_path = Path(inner_child)
                jinja_tpl_to_py(
                    inner_child_path.name, child_path,
                    paste_project_path, project_name, setup_type,
                )
        else:
            jinja_tpl_to_py(
                child_path.name, base_copy_path,
                base_paste_path, project_name, setup_type,
            )
