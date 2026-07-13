from datetime import UTC, datetime

from app.db.models import DiscussionMetric, PipelineJob, Source, SourceDiscussion
from app.services.github_client import GitHubDiscussion, GitHubRepository
from app.services.scraper import ScraperService
from app.tests.helpers import make_test_session


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


class FakeOrganizationGitHubClient:
    def fetch_recent_discussions(self, owner, repo, created_since, include_comments=False):
        assert owner == "community"
        assert repo == "community"
        return [
            GitHubDiscussion(
                github_discussion_id="OD_123",
                repo_full_name="community/community",
                discussion_number=11,
                title="Org discussion",
                author_login="octocat",
                category_name="General",
                comments_count=4,
                upvote_count=6,
                html_url="https://github.com/orgs/community/discussions/11",
                discussion_created_at=datetime(2026, 1, 1),
                discussion_updated_at=datetime(2026, 1, 2),
            )
        ]


class FakeOrganizationRepositoriesGitHubClient:
    def fetch_discussion_enabled_repositories(self, organization):
        assert organization == "vercel"
        return [
            GitHubRepository(
                name="next.js",
                name_with_owner="vercel/next.js",
                has_discussions_enabled=True,
            ),
            GitHubRepository(
                name="turborepo",
                name_with_owner="vercel/turborepo",
                has_discussions_enabled=True,
            ),
        ]

    def fetch_recent_discussions(self, owner, repo, created_since, include_comments=False):
        if (owner, repo) == ("vercel", "next.js"):
            return [
                GitHubDiscussion(
                    github_discussion_id="D_next_recent",
                    repo_full_name="vercel/next.js",
                    discussion_number=95735,
                    title="Recent Next.js discussion",
                    author_login="octocat",
                    category_name="General",
                    comments_count=1,
                    upvote_count=2,
                    html_url="https://github.com/vercel/next.js/discussions/95735",
                    discussion_created_at=datetime(2026, 7, 13),
                    discussion_updated_at=datetime(2026, 7, 13),
                )
            ]
        assert (owner, repo) == ("vercel", "turborepo")
        return []


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


def test_scrape_organization_discussions_source_upserts_metrics(tmp_path):
    session_factory = make_test_session(tmp_path)
    db = session_factory()
    try:
        source = Source(
            source_type="organization_discussions",
            identifier="community",
            is_active=True,
            is_accessible=True,
            include_comments=False,
            created_at=datetime.now(UTC).replace(tzinfo=None),
        )
        db.add(source)
        db.commit()
        db.refresh(source)

        job = ScraperService(FakeOrganizationGitHubClient()).scrape_source(db, source)

        assert job.status == "done"
        assert job.discussions_found == 1
        assert job.discussions_new == 1
        assert db.query(DiscussionMetric).count() == 1
        assert db.query(SourceDiscussion).count() == 1
        assert db.query(PipelineJob).count() == 1
    finally:
        db.close()


def test_scrape_organization_repositories_checks_repos_and_upserts_recent_metrics(
    tmp_path,
):
    session_factory = make_test_session(tmp_path)
    db = session_factory()
    try:
        source = Source(
            source_type="organization_repositories",
            identifier="vercel",
            is_active=True,
            is_accessible=True,
            include_comments=False,
            created_at=datetime.now(UTC).replace(tzinfo=None),
        )
        db.add(source)
        db.commit()
        db.refresh(source)

        job = ScraperService(
            FakeOrganizationRepositoriesGitHubClient()
        ).scrape_source(db, source)

        assert job.status == "done"
        assert job.discussions_found == 1
        assert job.discussions_new == 1
        assert job.items_failed == 0
        assert db.query(DiscussionMetric).count() == 1
        assert db.query(SourceDiscussion).count() == 1
        assert db.query(PipelineJob).count() == 1
    finally:
        db.close()
