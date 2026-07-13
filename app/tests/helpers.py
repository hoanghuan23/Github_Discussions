from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


ROOT_DIR = Path(__file__).resolve().parents[2]


def make_test_session(tmp_path):
    db_path = tmp_path / "github_discussions.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    raw = engine.raw_connection()
    try:
        raw.executescript(
            (ROOT_DIR / "data" / "schema_table_github_discussions_minimal.sql")
            .read_text(encoding="utf-8")
        )
        raw.commit()
    finally:
        raw.close()

    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
