from pathlib import Path
from dotenv import load_dotenv
import os

PROJECT_ROOT = Path(__file__).resolve().parent.parent

load_dotenv(PROJECT_ROOT / ".env")

# System
EXECUTION_MODE = os.getenv("EXECUTION_MODE", "PAPER")
ACTIVE_MARKET = os.getenv("ACTIVE_MARKET", "INDIA")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
DB_PATH = os.getenv("DB_PATH", str(PROJECT_ROOT / "database" / "kairos.db"))
LOG_PATH = os.getenv("LOG_PATH", str(PROJECT_ROOT / "logs" / "kairos.log"))

# The dashboard intentionally runs on a plain interpreter without pandas-ta (see memory
# checkpoint for why). Anything needing engine/data.indicators (the screener, signal
# generation) is delegated to this venv via subprocess instead of importing in-process.
ENGINE_PYTHON = os.getenv("ENGINE_PYTHON", str(PROJECT_ROOT / "kairos_env" / "bin" / "python3"))

# Capital
STARTING_CAPITAL_INR = float(os.getenv("STARTING_CAPITAL_INR", 10000))
STARTING_CAPITAL_USD = float(os.getenv("STARTING_CAPITAL_USD", 100))

# Zerodha
ZERODHA_API_KEY = os.getenv("ZERODHA_API_KEY", "")
ZERODHA_API_SECRET = os.getenv("ZERODHA_API_SECRET", "")
ZERODHA_ACCESS_TOKEN = os.getenv("ZERODHA_ACCESS_TOKEN", "")

# Alpaca
ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "")
ALPACA_BASE_URL = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")

# OANDA
OANDA_API_KEY = os.getenv("OANDA_API_KEY", "")
OANDA_ACCOUNT_ID = os.getenv("OANDA_ACCOUNT_ID", "")
OANDA_ENVIRONMENT = os.getenv("OANDA_ENVIRONMENT", "practice")

# Risk (can be overridden via .env)
MAX_RISK_PER_TRADE_PCT = float(os.getenv("MAX_RISK_PER_TRADE_PCT", 0.02))
MAX_PORTFOLIO_HEAT_PCT = float(os.getenv("MAX_PORTFOLIO_HEAT_PCT", 0.10))
DAILY_LOSS_LIMIT_PCT = float(os.getenv("DAILY_LOSS_LIMIT_PCT", 0.05))
MAX_DRAWDOWN_HALT_PCT = float(os.getenv("MAX_DRAWDOWN_HALT_PCT", 0.20))

# Notifications
ALERT_EMAIL = os.getenv("ALERT_EMAIL", "")
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))

# AI assistant (optional — keys stored for a future in-dashboard help feature, not yet built)
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
