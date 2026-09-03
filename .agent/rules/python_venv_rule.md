---
alwaysApply: true
always_on: true
trigger: always_on
applyTo: "**/*.py"
description: Always use virtual environment for Python projects with requirements.txt
---

# Python Virtual Environment Rule

- For any Python project that contains a `requirements.txt` file, always ensure a virtual environment is used when running commands in the terminal (e.g., `pip install`, `python script.py`, `pytest`).
- Detection: If a `requirements.txt` file is present in the project root or relevant subdirectory.
- Action: Activation of a virtual environment (e.g., `venv`, `.venv`) before executing terminal commands.
- If no virtual environment exists, the agent should propose creating one (`python -m venv venv`) and installing dependencies (`pip install -r requirements.txt`).
