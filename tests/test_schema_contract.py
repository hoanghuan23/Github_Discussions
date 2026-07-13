from sqlalchemy import inspect
from sqlalchemy import text

from tests.helpers import make_test_session


def test_existing_schema_tables_are_available(tmp_path):
    session_factory = make_test_session(tmp_path)
    inspector = inspect(session_factory.kw["bind"])

    assert set(inspector.get_table_names()) == {
        "analytics_cache",
        "discussion_comments",
        "discussion_metrics",
        "discussions",
        "pipeline_jobs",
        "pipeline_logs",
        "source_discussions",
        "sources",
    }


def test_discussions_schema_has_expected_contract_columns(tmp_path):
    session_factory = make_test_session(tmp_path)
    inspector = inspect(session_factory.kw["bind"])
    columns = {column["name"] for column in inspector.get_columns("discussions")}

    assert {
        "github_discussion_id",
        "repo_full_name",
        "discussion_number",
        "comments_count",
        "upvote_count",
        "metric_tier",
        "next_metric_update",
    }.issubset(columns)


def test_sources_schema_accepts_expected_source_types(tmp_path):
    session_factory = make_test_session(tmp_path)
    db = session_factory()
    try:
        for source_type, identifier in [
            ("repository", "solidjs/solid"),
            ("organization_repositories", "vercel"),
            ("organization_discussions", "community"),
            ("category", "solidjs/solid/general"),
        ]:
            db.execute(
                text(
                    """
                INSERT INTO sources (source_type, identifier)
                VALUES (:source_type, :identifier)
                """
                ),
                {"source_type": source_type, "identifier": identifier},
            )
        db.commit()
    finally:
        db.close()
