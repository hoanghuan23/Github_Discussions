import os
from pathlib import Path

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / ".env")


class Settings:
    database_url: str = os.getenv(
        "DATABASE_URL",
        f"sqlite:///{ROOT_DIR / 'data' / 'github_discussions.db'}",
    )
    github_token: str | None = os.getenv("GITHUB_TOKEN")
    github_graphql_url: str = os.getenv(
        "GITHUB_GRAPHQL_URL",
        "https://api.github.com/graphql",
    )
    github_page_size: int = int(os.getenv("GITHUB_PAGE_SIZE", "50"))
    lookback_hours: int = int(os.getenv("LOOKBACK_HOURS", "24"))
    scheduler_interval_seconds: int = int(os.getenv("SCHEDULER_INTERVAL_SECONDS", "60"))


settings = Settings()
