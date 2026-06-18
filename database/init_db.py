"""Run once to create kairos.db with all tables."""
from pathlib import Path
from sqlalchemy import create_engine
from database.models import Base

DB_PATH = Path(__file__).parent / "kairos.db"

def init_database():
    engine = create_engine(f"sqlite:///{DB_PATH}")
    Base.metadata.create_all(engine)
    print(f"KAIROS DB initialized at {DB_PATH}")
    return engine

if __name__ == "__main__":
    init_database()
