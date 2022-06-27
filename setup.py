from setuptools import setup, find_packages

# To use a consistent encoding
from codecs import open
from os import path

# The directory containing this file
HERE = path.abspath(path.dirname(__file__))

# Get the long description from the README file
with open(path.join(HERE, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

setup(
    name = 'greatapi',
    version = '0.0.2',
    description = 'GreatAPI Framework, FastAPI with admin panel',
    long_description=long_description,
    long_description_content_type="text/markdown",
    packages=["greatapi"],
    include_package_data=True,

    keywords="fastapi, api, django, admin, web-framework",
    classifiers=[
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Operating System :: OS Independent"
    ],

    install_requires = [
        "numpy",
        "fastapi",
        "uvicorn"
    ],

    extras_require = {
        'dev': [
            'pytest>=3.7',
        ],
    },

    url = 'https://github.com/greatapi/greatapi',
    author = 'Sahaj Raj Malla',
    author_email = 'mallasahajraj@gmail.com',
    license="MIT",
)