<div align="center">

<img src="https://raw.githubusercontent.com/sahajrajmalla/greatapi/master/greatapi/admin/static/greatapi_readme.svg" alt="GreatAPI"/>

<i>GreatAPI framework, Full-stack FastAPI framework</i>

![GitHub Workflow Status](https://img.shields.io/github/workflow/status/sahajrajmalla/greatapi/%F0%9F%8E%A8%20Linter?style=for-the-badge)
![PyPI - Downloads](https://img.shields.io/pypi/dm/greatapi?color=green&style=for-the-badge)
![PyPI](https://img.shields.io/pypi/v/greatapi?style=for-the-badge)
![PyPI - Python Version](https://img.shields.io/pypi/pyversions/greatapi?style=for-the-badge)
<hr

Documentation: https://greatapi.readthedocs.io/en/latest/

Source Code: https://github.com/sahajrajmalla/greatapi

PyPI Package: https://pypi.org/project/greatapi/


<hr>
</div>

## **Contributors**
Some of the major contributors to GreatAPI are:
- [@thebrowl](https://github.com/thebrowl) -> [Admin Panel Design]
- [@lamdiv](https://github.com/lamdiv) -> [Admin Panel Development with Jinja2]
- [@Avi777](https://github.com/Avi777) -> [Consultant]
## **Requirements**

- Python 3.6+
- GreatAPI stands on the shoulders of giants:
    - FastAPI
    - uvicorn
    - typer
    - jinja2
    - SQLAlchemy

## **Installation**

```bash
pip install greatapi
```

## **Getting Started**

### ***Startproject: To create a new project***

```bash
greatapi startproject <project_name>
```

### ***Startapp: To create a new app***

```bash
greatapi startapp <app_name>
```

### ***Running: To run the server***

```bash
greatapi runserver
```
Then you can access the server at http://localhost:8000/ where you will find a beautiful built-in Admin Panel.

Afterwards, you can normally implement your API logic using FastAPI itself.

## **License**

This project is licensed under the terms of the MIT license.
