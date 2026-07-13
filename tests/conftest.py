import os


os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/github_discussions_test_default.db")
os.environ.setdefault("GITHUB_TOKEN", "test-token")
