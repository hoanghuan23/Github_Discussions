from datetime import datetime, timedelta

from app.db.models import Discussion
from app.repositories.discussions import upsert_discussion
from app.services.github_client import GitHubDiscussion
from app.tests.helpers import make_test_session


def test_upsert_discussion_sets_next_metric_update_by_tier(tmp_path):
    session_factory = make_test_session(tmp_path)
    db = session_factory()
    now = datetime(2026, 7, 14, 10, 0, 0)
    cases = [
        ("hot", 34, 0, 15),
        ("high", 17, 0, 20),
        ("medium", 7, 0, 45),
        ("low", 2, 0, 90),
        ("very_low", 1, 0, 180),
    ]

    try:
        for tier, comments_count, upvote_count, interval_minutes in cases:
            upsert_discussion(
                db,
                source_id=None,
                item=GitHubDiscussion(
                    github_discussion_id=f"D_{tier}",
                    repo_full_name="vercel/next.js",
                    discussion_number=interval_minutes,
                    title=f"{tier} discussion",
                    author_login="octocat",
                    category_name="General",
                    comments_count=comments_count,
                    upvote_count=upvote_count,
                    html_url=f"https://github.com/vercel/next.js/discussions/{interval_minutes}",
                    discussion_created_at=now,
                    discussion_updated_at=now,
                ),
                job_id=None,
                now=now,
                include_comments=False,
            )

        db.commit()

        discussions = {
            discussion.metric_tier: discussion
            for discussion in db.query(Discussion).all()
        }
        for tier, _, _, interval_minutes in cases:
            assert discussions[tier].next_metric_update == now + timedelta(
                minutes=interval_minutes
            )
    finally:
        db.close()
