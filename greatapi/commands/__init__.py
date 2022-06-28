from __future__ import annotations

import typer

app = typer.Typer()
from greatapi.commands.startproject import project_initialization


@app.command()
def cli(first_arg: str, second_arg: str) -> None:
    typer.echo(first_arg)
    typer.echo(type(first_arg))
    if first_arg == "startproject":
        project_initialization(second_arg)
    else:
        typer.echo("Command not found!")
