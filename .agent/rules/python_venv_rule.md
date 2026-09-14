---
alwaysApply: true
always_on: true
trigger: always_on
applyTo: "**/*.py"
description: Always use virtual environment with uv for Python projects
---

# Python Virtual Environment Rule

- For any Python project that contains a `pyproject.toml` file, always ensure `uv` is used for environment and dependency management when running commands in the terminal (e.g., `uv run python script.py`, `uv run pytest`, `uv run ruff check`).
- Detection: If a `pyproject.toml` or `uv.lock` file is present in the project root or relevant subdirectory.
- Action: Use `uv run` to execute commands within the managed `.venv`, or run `uv sync` to install/synchronize dependencies.
- If no virtual environment exists or dependencies are out of date, the agent should run `uv sync` (or `uv sync --all-groups` if dev dependencies are needed).
