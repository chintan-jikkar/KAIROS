#!/bin/bash
# KAIROS stopper — double-click to stop the running dashboard.
lsof -ti tcp:8501 2>/dev/null | xargs kill 2>/dev/null
pkill -f "streamlit run dashboard/app.py" 2>/dev/null
echo "KAIROS stopped. You can close this window."
sleep 1
