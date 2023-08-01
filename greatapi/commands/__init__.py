from __future__ import annotations

import typer

from greatapi.commands.createsuperuser import create_superuser_interactive  # Import the new command
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


@app.command()  # Add the createsuperuser command
def createsuperuser() -> None:
    create_superuser_interactive()
