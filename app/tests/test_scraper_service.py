from datetime import UTC, datetime, timedelta

from app.db.models import (
    AnalyticsCache,
    Discussion,
    DiscussionMetric,
    PipelineJob,
    Source,
    SourceDiscussion,
)
from app.services.github_client import (
    GitHubDiscussion,
    GitHubDiscussionMetrics,
    GitHubRepository,
)
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


class SequencedGitHubClient:
    def __init__(self, items):
        self.items = items
        self.index = 0

    def fetch_recent_discussions(self, owner, repo, created_since, include_comments=False):
        assert owner == "vercel"
        assert repo == "next.js"
        item = self.items[self.index]
        self.index += 1
        return [item]


class RecordingGitHubClient:
    def __init__(self, items=None):
        self.items = items or []
        self.calls = []

    def fetch_recent_discussions(self, owner, repo, created_since, include_comments=False):
        self.calls.append(
            {
                "owner": owner,
                "repo": repo,
                "created_since": created_since,
                "include_comments": include_comments,
            }
        )
        return self.items


class RecordingOrganizationRepositoriesClient(RecordingGitHubClient):
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


class PartiallyFailingMetricClient:
    def fetch_discussion_metrics_by_id(self, github_discussion_id):
        if github_discussion_id == "D_metric_fail":
            raise RuntimeError("temporary GitHub error")
        return GitHubDiscussionMetrics(
            github_discussion_id="D_metric_success",
            comments_count=12,
            upvote_count=8,
        )


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
        assert job.job_type == "new_discussions"
        assert job.discussions_found == 1
        assert job.discussions_new == 1
        assert db.query(DiscussionMetric).count() == 1
        assert db.query(SourceDiscussion).count() == 1
        assert db.query(PipelineJob).count() == 1
    finally:
        db.close()


def test_update_due_metrics_continues_after_discussion_error(tmp_path, monkeypatch):
    session_factory = make_test_session(tmp_path)
    db = session_factory()
    now = datetime(2026, 7, 14, 10, 0, 0)
    try:
        source = Source(
            source_type="repository",
            identifier="vercel/next.js",
            is_active=True,
            is_accessible=True,
            include_comments=False,
            created_at=now,
        )
        db.add(source)
        db.flush()
        discussions = [
            Discussion(
                github_discussion_id="D_metric_fail",
                source_id=source.id,
                repo_full_name="vercel/next.js",
                discussion_number=1,
                title="Metric fail",
                comments_count=1,
                upvote_count=1,
                html_url="https://github.com/vercel/next.js/discussions/1",
                discussion_created_at=now - timedelta(days=1),
                discussion_updated_at=now - timedelta(days=1),
                created_at=now - timedelta(days=1),
                is_tracked=True,
                is_deleted=False,
                last_metric_update=now - timedelta(hours=2),
                next_metric_update=now - timedelta(seconds=1),
                metric_tier="very_low",
            ),
            Discussion(
                github_discussion_id="D_metric_success",
                source_id=source.id,
                repo_full_name="vercel/next.js",
                discussion_number=2,
                title="Metric success",
                comments_count=2,
                upvote_count=2,
                html_url="https://github.com/vercel/next.js/discussions/2",
                discussion_created_at=now - timedelta(days=1),
                discussion_updated_at=now - timedelta(days=1),
                created_at=now - timedelta(days=1),
                is_tracked=True,
                is_deleted=False,
                last_metric_update=now - timedelta(hours=2),
                next_metric_update=now - timedelta(seconds=1),
                metric_tier="very_low",
            ),
        ]
        db.add_all(discussions)
        db.flush()
        db.add_all(
            [
                SourceDiscussion(
                    source_id=source.id,
                    discussion_id=discussion.id,
                    first_seen_at=discussion.discussion_created_at,
                    last_seen_at=discussion.discussion_created_at,
                )
                for discussion in discussions
            ]
        )
        db.commit()
        monkeypatch.setattr("app.services.scraper.utcnow", lambda: now)

        job = ScraperService(PartiallyFailingMetricClient()).update_due_metrics(
            db,
            source,
        )

        success = (
            db.query(Discussion)
            .filter(Discussion.github_discussion_id == "D_metric_success")
            .one()
        )
        assert job.status == "done"
        assert job.source_id == source.id
        assert job.discussions_found == 1
        assert job.discussions_updated == 1
        assert job.items_failed == 1
        assert success.comments_count == 12
        assert success.upvote_count == 8
        assert success.title == "Metric success"
        assert success.html_url == "https://github.com/vercel/next.js/discussions/2"
        assert success.discussion_number == 2
        assert db.query(DiscussionMetric).count() == 1
    finally:
        db.close()


def test_scrape_source_refreshes_daily_analytics_cache_and_source_tier(
    tmp_path,
    monkeypatch,
):
    session_factory = make_test_session(tmp_path)
    db = session_factory()
    crawl_times = [
        datetime(2026, 7, 14, 10, 0, 0),
        datetime(2026, 7, 14, 18, 0, 0),
        datetime(2026, 7, 15, 10, 0, 0),
    ]
    items = [
        GitHubDiscussion(
            github_discussion_id="D_123",
            repo_full_name="vercel/next.js",
            discussion_number=10,
            title="Test discussion",
            author_login="octocat",
            category_name="General",
            comments_count=10,
            upvote_count=16,
            html_url="https://github.com/vercel/next.js/discussions/10",
            discussion_created_at=datetime(2026, 1, 1),
            discussion_updated_at=datetime(2026, 1, 2),
        ),
        GitHubDiscussion(
            github_discussion_id="D_123",
            repo_full_name="vercel/next.js",
            discussion_number=10,
            title="Test discussion updated",
            author_login="octocat",
            category_name="General",
            comments_count=30,
            upvote_count=80,
            html_url="https://github.com/vercel/next.js/discussions/10",
            discussion_created_at=datetime(2026, 1, 1),
            discussion_updated_at=datetime(2026, 1, 2),
        ),
        GitHubDiscussion(
            github_discussion_id="D_123",
            repo_full_name="vercel/next.js",
            discussion_number=10,
            title="Test discussion next day",
            author_login="octocat",
            category_name="General",
            comments_count=100,
            upvote_count=100,
            html_url="https://github.com/vercel/next.js/discussions/10",
            discussion_created_at=datetime(2026, 1, 1),
            discussion_updated_at=datetime(2026, 1, 2),
        ),
    ]

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

        call_count = {"value": 0}

        def fake_utcnow():
            index = min(call_count["value"] // 2, len(crawl_times) - 1)
            call_count["value"] += 1
            return crawl_times[index]

        monkeypatch.setattr("app.services.scraper.utcnow", fake_utcnow)
        service = ScraperService(SequencedGitHubClient(items))

        service.scrape_source(db, source)
        first_cache = db.query(AnalyticsCache).one()
        assert first_cache.date.isoformat() == "2026-07-14"
        assert first_cache.total_discussions == 1
        assert first_cache.total_comments == 10
        assert first_cache.total_upvotes == 16
        assert source.schedule_tier == 2
        assert source.next_scrape == crawl_times[0] + timedelta(minutes=240)

        service.scrape_source(db, source)
        caches = db.query(AnalyticsCache).all()
        assert len(caches) == 1
        assert caches[0].total_comments == 30
        assert caches[0].total_upvotes == 80
        assert source.schedule_tier == 3
        assert source.next_scrape == crawl_times[1] + timedelta(minutes=120)

        service.scrape_source(db, source)
        caches = db.query(AnalyticsCache).order_by(AnalyticsCache.date).all()
        assert len(caches) == 2
        assert caches[1].date.isoformat() == "2026-07-15"
        assert caches[1].total_comments == 100
        assert caches[1].total_upvotes == 100
        assert source.schedule_tier == 4
        assert source.next_scrape == crawl_times[2] + timedelta(minutes=60)
    finally:
        db.close()


def test_new_discussions_uses_latest_created_at_as_crawl_boundary(
    tmp_path,
    monkeypatch,
):
    session_factory = make_test_session(tmp_path)
    db = session_factory()
    now = datetime(2026, 7, 14, 10, 0, 0)
    latest_created_at = datetime(2026, 7, 14, 9, 30, 0)
    try:
        source = Source(
            source_type="repository",
            identifier="vercel/next.js",
            is_active=True,
            is_accessible=True,
            include_comments=False,
            created_at=now,
        )
        db.add(source)
        db.flush()
        discussion = Discussion(
            github_discussion_id="D_latest",
            source_id=source.id,
            repo_full_name="vercel/next.js",
            discussion_number=20,
            title="Latest known discussion",
            comments_count=1,
            upvote_count=1,
            html_url="https://github.com/vercel/next.js/discussions/20",
            discussion_created_at=latest_created_at,
            discussion_updated_at=latest_created_at,
            created_at=latest_created_at,
            is_tracked=True,
            is_deleted=False,
            metric_tier="very_low",
        )
        db.add(discussion)
        db.flush()
        db.add(
            SourceDiscussion(
                source_id=source.id,
                discussion_id=discussion.id,
                first_seen_at=latest_created_at,
                last_seen_at=latest_created_at,
            )
        )
        db.commit()
        db.refresh(source)
        monkeypatch.setattr("app.services.scraper.utcnow", lambda: now)

        client = RecordingGitHubClient()
        job = ScraperService(client).scrape_source(db, source, job_type="new_discussions")

        assert job.status == "done"
        assert client.calls[0]["created_since"] == latest_created_at + timedelta(
            microseconds=1
        )
    finally:
        db.close()


def test_new_discussions_uses_repo_specific_latest_boundary_for_organization_repos(
    tmp_path,
    monkeypatch,
):
    session_factory = make_test_session(tmp_path)
    db = session_factory()
    now = datetime(2026, 7, 14, 10, 0, 0)
    latest_next = datetime(2026, 7, 14, 9, 45, 0)
    latest_turbo = datetime(2026, 7, 14, 8, 15, 0)
    try:
        source = Source(
            source_type="organization_repositories",
            identifier="vercel",
            is_active=True,
            is_accessible=True,
            include_comments=False,
            created_at=now,
        )
        db.add(source)
        db.flush()
        discussions = [
            Discussion(
                github_discussion_id="D_next_latest",
                source_id=source.id,
                repo_full_name="vercel/next.js",
                discussion_number=30,
                title="Latest Next.js",
                comments_count=1,
                upvote_count=1,
                html_url="https://github.com/vercel/next.js/discussions/30",
                discussion_created_at=latest_next,
                discussion_updated_at=latest_next,
                created_at=latest_next,
                is_tracked=True,
                is_deleted=False,
                metric_tier="very_low",
            ),
            Discussion(
                github_discussion_id="D_turbo_latest",
                source_id=source.id,
                repo_full_name="vercel/turborepo",
                discussion_number=40,
                title="Latest Turborepo",
                comments_count=1,
                upvote_count=1,
                html_url="https://github.com/vercel/turborepo/discussions/40",
                discussion_created_at=latest_turbo,
                discussion_updated_at=latest_turbo,
                created_at=latest_turbo,
                is_tracked=True,
                is_deleted=False,
                metric_tier="very_low",
            ),
        ]
        db.add_all(discussions)
        db.flush()
        db.add_all(
            [
                SourceDiscussion(
                    source_id=source.id,
                    discussion_id=discussion.id,
                    first_seen_at=discussion.discussion_created_at,
                    last_seen_at=discussion.discussion_created_at,
                )
                for discussion in discussions
            ]
        )
        db.commit()
        db.refresh(source)
        monkeypatch.setattr("app.services.scraper.utcnow", lambda: now)

        client = RecordingOrganizationRepositoriesClient()
        job = ScraperService(client).scrape_source(db, source, job_type="new_discussions")

        assert job.status == "done"
        assert client.calls == [
            {
                "owner": "vercel",
                "repo": "next.js",
                "created_since": latest_next + timedelta(microseconds=1),
                "include_comments": False,
            },
            {
                "owner": "vercel",
                "repo": "turborepo",
                "created_since": latest_turbo + timedelta(microseconds=1),
                "include_comments": False,
            },
        ]
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
        assert job.job_type == "new_discussions"
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
        assert job.job_type == "new_discussions"
        assert job.discussions_found == 1
        assert job.discussions_new == 1
        assert job.items_failed == 0
        assert db.query(DiscussionMetric).count() == 1
        assert db.query(SourceDiscussion).count() == 1
        assert db.query(PipelineJob).count() == 1
    finally:
        db.close()
