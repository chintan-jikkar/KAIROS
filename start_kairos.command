#!/bin/bash
# KAIROS launcher — double-click this file to start the dashboard.
cd "$(dirname "$0")"

# Use the Python that has the dashboard's dependencies (pyenv 3.11.15 has them; fall back to python3).
PY="$HOME/.pyenv/versions/3.11.15/bin/python3"
if ! { [ -x "$PY" ] && "$PY" -c "import streamlit" 2>/dev/null; }; then
  PY="python3"
fi

# Free port 8501 if a previous server is still running (prevents "Address already in use").
lsof -ti tcp:8501 2>/dev/null | xargs kill 2>/dev/null
sleep 1

# Open the app in your browser once the server is up.
( sleep 3; open "http://localhost:8501" ) &

echo "────────────────────────────────────────────────"
echo "  KAIROS is starting at http://localhost:8501"
echo "  Keep this window open while you use the app."
echo "  To stop: close this window, or double-click"
echo "  stop_kairos.command."
echo "────────────────────────────────────────────────"
exec "$PY" -m streamlit run dashboard/app.py --server.port 8501 --server.headless true
