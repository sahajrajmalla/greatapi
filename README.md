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

Before we dive into the tutorial, make sure you have the following requirements in place:

- Python 3.6 or higher installed on your system.
- Familiarity with Python programming language concepts.

GreatAPI is built upon the foundation of the following robust libraries:

- FastAPI: A modern, fast, web framework for building APIs with Python.
- uvicorn: ASGI server that runs FastAPI applications.
- typer: A command-line interface library for building CLI applications.
- jinja2: A templating engine for Python.
- SQLAlchemy: A powerful Object-Relational Mapping (ORM) library for Python.

## Installation

To install GreatAPI and its dependencies, use `pip`:

```bash
pip install greatapi

```

## Getting Started

### Step 1: Start a New Project

To begin working with GreatAPI, let's create a new project. Open your terminal and execute the following command:

```bash
greatapi startproject myproject

```

This will create a new directory named "myproject" with the basic structure to get you started.

    myproject/

    ├──__init__.py

    ├──settings.py

    main.py

### Step 2: Create a New App

An app in GreatAPI is a modular unit that encapsulates specific functionality of your project. To create a new app, run the following command:

```bash
greatapi startapp myapp

```

This will generate a new directory named "myapp" containing the necessary files and folders for your app.

    myapp/

    ├──__init__.py

    ├──models.py

    ├──repository.py

    ├──router.py

    ├──schemas.py

### Step 3: Run the Server

Now, it's time to run the development server. Execute the following command:

```bash
greatapi runserver

```
### Step 4: Creating a Superuser

After running the server, let's create a superuser to manage the administration of your project. Execute the following command:

```bash
greatapi createsuperuser

```

Follow the prompts to create the superuser account and again run the server.



The server will start, and you can access your application at http://localhost:8000/. Additionally, GreatAPI provides a beautifully designed built-in Admin Panel accessible at http://localhost:8000/admin.
