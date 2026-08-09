"""Lets the CLI run as ``python -m greatapi.cli``.

Useful when the console script is not on PATH -- inside a container, from a
Makefile, or against a checkout that has not been installed.
"""

from __future__ import annotations

from greatapi.cli import main

if __name__ == "__main__":
    main()
