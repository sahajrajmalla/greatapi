from __future__ import annotations

import typer

app = typer.Typer()


@app.command()
def cli(command_type: str) -> None:
    typer.echo('Hello World ' + command_type)
