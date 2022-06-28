from __future__ import annotations

import typer

from greatapi.commands.startapp import application_initialization
from greatapi.commands.startproject import project_initialization

app = typer.Typer()


@app.command()
def cli(first_arg: str, second_arg: str) -> None:
    if first_arg == 'startproject':
        project_initialization(second_arg)
    elif first_arg == 'startapp':
        application_initialization(second_arg)
    else:
        typer.echo('Command not found!')
