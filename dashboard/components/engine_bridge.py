"""
Runs engine code (anything needing pandas-ta) in the kairos_env subprocess instead of
importing it into the dashboard process. Keeps the dashboard's interpreter free of
pandas-ta, and matches the spec's principle that the dashboard and the algo engine are
independent processes.
"""
import json
import subprocess

import streamlit as st

from config.settings import ENGINE_PYTHON, PROJECT_ROOT


def run_screener(top_n: int | None = 6, timeout: int = 120) -> tuple[list[dict], str | None]:
    """Returns (results, error_message). error_message is None on success."""
    code = (
        "import json; "
        "from engine.screener import run_india_screener; "
        f"print(json.dumps(run_india_screener(top_n={top_n!r})))"
    )
    try:
        result = subprocess.run(
            [ENGINE_PYTHON, "-c", code],
            capture_output=True, text=True, cwd=str(PROJECT_ROOT), timeout=timeout,
        )
    except FileNotFoundError:
        return [], f"Engine Python not found at {ENGINE_PYTHON}. Set ENGINE_PYTHON in .env."
    except subprocess.TimeoutExpired:
        return [], "Screener timed out — live data fetch took too long."

    if result.returncode != 0:
        last_line = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "unknown error"
        return [], f"Screener failed: {last_line}"

    try:
        return json.loads(result.stdout.strip().splitlines()[-1]), None
    except (json.JSONDecodeError, IndexError):
        return [], "Screener returned unexpected output."
