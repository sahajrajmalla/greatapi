# GreatAPI - Full-stack FastAPI Framework

![GreatAPI](https://raw.githubusercontent.com/sahajrajmalla/greatapi/master/greatapi/admin/static/greatapi_readme.svg)

GreatAPI is a full-stack FastAPI framework designed to simplify and accelerate web application development. It leverages the power of FastAPI and integrates various essential tools to provide a seamless development experience.

[![Linter](https://github.com/sahajrajmalla/greatapi/actions/workflows/linter.yml/badge.svg)](https://github.com/sahajrajmalla/greatapi/actions/workflows/linter.yml)
![PyPI - Downloads](https://img.shields.io/pypi/dm/greatapi?color=green&style=for-the-badge)
![PyPI](https://img.shields.io/pypi/v/greatapi?style=for-the-badge)
![PyPI - Python Version](https://img.shields.io/pypi/pyversions/greatapi?style=for-the-badge)

## Documentation
Explore our comprehensive documentation to get started with GreatAPI: [Documentation](https://greatapi.readthedocs.io/en/latest/)

## Source Code
Find the source code on GitHub: [GitHub Repository](https://github.com/sahajrajmalla/greatapi)

## PyPI Package
Install GreatAPI using PyPI: [PyPI Package](https://pypi.org/project/greatapi/)

## Contributors
Major contributors to GreatAPI:

- [@thebrowl](https://github.com/thebrowl) -> Admin Panel Design
- [@lamdiv](https://github.com/lamdiv) -> Admin Panel Development with Jinja2
- [@Avi777](https://github.com/Avi777) -> Consultant

## Requirements

- Python 3.6+
- GreatAPI stands on the shoulders of giants:
    - FastAPI
    - uvicorn
    - typer
    - jinja2
    - SQLAlchemy

## Installation

```bash
pip install greatapi
```

## Getting Started

### Startproject: Create a new project

```bash
greatapi startproject <project_name>
```

### Startapp: Create a new app

```bash
greatapi startapp <app_name>
```

### Running: Run the server

```bash
greatapi runserver
```

The server will be accessible at http://localhost:8000/, and you will find a beautifully designed built-in Admin Panel.

From there, you can easily implement your API logic using FastAPI.

## License

This project is licensed under the terms of the MIT license. Feel free to use it and contribute to its development!
