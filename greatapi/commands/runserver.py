import subprocess
import typer

def server_initialization() -> None:
    result = subprocess.run(["uvicorn", "main:app", "--reload"])