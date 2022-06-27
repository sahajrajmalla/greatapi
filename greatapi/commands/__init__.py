import typer

app = typer.Typer()

@app.command()
def cli(command_type: str):
    typer.echo("Hello World " + command_type)