from datetime import UTC, datetime

from app.db.models import DiscussionMetric, PipelineJob, Source, SourceDiscussion
from app.services.github_client import GitHubDiscussion
from app.services.scraper import ScraperService
from tests.helpers import make_test_session


class FakeGitHubClient:
    def fetch_recent_discussions(self, owner, repo, created_since, include_comments=False):
        assert owner == "vercel"
        assert repo == "next.js"
        return [
            GitHubDiscussion(
                github_discussion_id="D_123",
                repo_full_name="vercel/next.js",
                discussion_number=10,
                title="Test discussion",
                author_login="octocat",
                category_name="General",
                comments_count=3,
                upvote_count=7,
                html_url="https://github.com/vercel/next.js/discussions/10",
                discussion_created_at=datetime(2026, 1, 1),
                discussion_updated_at=datetime(2026, 1, 2),
            )
        ]


def test_scrape_source_upserts_discussion_metric_mapping_and_job(tmp_path):
    session_factory = make_test_session(tmp_path)
    db = session_factory()
    try:
        source = Source(
            source_type="repository",
            identifier="vercel/next.js",
            is_active=True,
            is_accessible=True,
            include_comments=False,
            created_at=datetime.now(UTC).replace(tzinfo=None),
        )
        db.add(source)
        db.commit()
        db.refresh(source)

        job = ScraperService(FakeGitHubClient()).scrape_source(db, source)

        assert job.status == "done"
        assert job.discussions_found == 1
        assert job.discussions_new == 1
        assert db.query(DiscussionMetric).count() == 1
        assert db.query(SourceDiscussion).count() == 1
        assert db.query(PipelineJob).count() == 1
    finally:
        db.close()
