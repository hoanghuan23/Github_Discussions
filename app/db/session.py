from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker

from app.core.config import ROOT_DIR, settings


engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False}
    if settings.database_url.startswith("sqlite")
    else {},
    future=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    inspector = inspect(engine)
    if inspector.has_table("sources"):
        return

    schema_path = ROOT_DIR / "data" / "schema_table_github_discussions.sql"
    if not schema_path.exists():
        raise RuntimeError(f"Schema file not found: {schema_path}")

    sql = schema_path.read_text(encoding="utf-8")
    raw_connection = engine.raw_connection()
    try:
        raw_connection.executescript(sql)
        raw_connection.commit()
    finally:
        raw_connection.close()


def ping_db() -> bool:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return True
