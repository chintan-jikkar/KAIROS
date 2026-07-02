"""
Stub heavy production dependencies that are not available in the test environment.
pandas_ta requires a build environment (C extensions) that isn't installed here;
stubbing it at the sys.modules level lets engine.screener and engine.backtest
import cleanly so all pure-logic tests can run.
"""
import sys
from unittest.mock import MagicMock

sys.modules.setdefault("pandas_ta", MagicMock())
