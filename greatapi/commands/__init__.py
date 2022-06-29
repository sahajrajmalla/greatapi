from __future__ import annotations

import typer

from greatapi.commands.runserver import server_initialization
from greatapi.commands.startapp import application_initialization
from greatapi.commands.startproject import project_initialization

app = typer.Typer()


@app.command()
def runserver() -> None:
    server_initialization()


@app.command()
def startproject(project_name: str) -> None:
    project_initialization(project_name)


@app.command()
def startapp(app_name: str) -> None:
    application_initialization(app_name)
