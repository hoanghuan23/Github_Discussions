from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.db.models import Discussion, DiscussionMetric, PipelineJob, Source
from app.db.session import get_db
from app.main import app
from app.services.github_client import GitHubDiscussion, GitHubRepository
from app.tests.helpers import make_test_session


def test_health_and_list_endpoints(tmp_path):
    session_factory = make_test_session(tmp_path)

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    db = session_factory()
    now = datetime.now(UTC).replace(tzinfo=None)
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
        github_discussion_id="D_123",
        source_id=source.id,
        repo_full_name="vercel/next.js",
        discussion_number=10,
        title="Test discussion",
        comments_count=3,
        upvote_count=7,
        html_url="https://github.com/vercel/next.js/discussions/10",
        discussion_created_at=now,
        discussion_updated_at=now,
        created_at=now,
        is_tracked=True,
        is_deleted=False,
        metric_tier="low",
    )
    job = PipelineJob(
        job_type="scrape_discussions",
        source_id=source.id,
        status="done",
        created_at=now,
        started_at=now,
        finished_at=now,
    )
    db.add_all([discussion, job])
    db.commit()
    db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        client = TestClient(app)
        assert client.get("/health").status_code == 200
        assert client.get("/sources").json()[0]["identifier"] == "vercel/next.js"
        assert client.get("/discussions").json()[0]["repo_full_name"] == "vercel/next.js"
        assert client.get("/jobs").json()[0]["status"] == "done"
    finally:
        app.dependency_overrides.clear()


def test_create_source_reuses_existing_identifier(tmp_path, monkeypatch):
    session_factory = make_test_session(tmp_path)

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    class FakeScraperService:
        def scrape_source(self, db, source):
            now = datetime.now(UTC).replace(tzinfo=None)
            job = PipelineJob(
                job_type="scrape_discussions",
                source_id=source.id,
                status="done",
                created_at=now,
                started_at=now,
                finished_at=now,
            )
            db.add(job)
            db.commit()
            db.refresh(job)
            return job

    monkeypatch.setattr("app.api.sources.ScraperService", FakeScraperService)
    app.dependency_overrides[get_db] = override_get_db
    try:
        client = TestClient(app)
        payload = {
            "url": "https://github.com/vercel/next.js/discussions",
            "include_comments": False,
        }
        first = client.post("/sources", json=payload)
        second = client.post("/sources", json={"url": "vercel/next.js"})

        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["source"]["id"] == second.json()["source"]["id"]

        db = session_factory()
        try:
            assert db.query(Source).count() == 1
            assert db.query(PipelineJob).count() == 2
        finally:
            db.close()
    finally:
        app.dependency_overrides.clear()


def test_create_source_crawls_discussions_and_metrics(tmp_path, monkeypatch):
    session_factory = make_test_session(tmp_path)

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    class FakeGitHubClient:
        def fetch_recent_discussions(
            self, owner, repo, created_since, include_comments=False
        ):
            assert owner == "community"
            assert repo == "community"
            return [
                GitHubDiscussion(
                    github_discussion_id="D_community_1",
                    repo_full_name="community/community",
                    discussion_number=42,
                    title="Welcome discussion",
                    author_login="octocat",
                    category_name="General",
                    comments_count=5,
                    upvote_count=9,
                    html_url="https://github.com/community/community/discussions/42",
                    discussion_created_at=datetime(2026, 1, 1),
                    discussion_updated_at=datetime(2026, 1, 2),
                )
            ]

    monkeypatch.setattr("app.services.scraper.GitHubGraphQLClient", FakeGitHubClient)
    app.dependency_overrides[get_db] = override_get_db
    try:
        client = TestClient(app)
        response = client.post(
            "/sources",
            json={"url": "https://github.com/community/community/discussions"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["job"]["status"] == "done"
        assert body["job"]["discussions_found"] == 1
        assert body["job"]["discussions_new"] == 1

        db = session_factory()
        try:
            discussion = db.query(Discussion).one()
            metric = db.query(DiscussionMetric).one()

            assert discussion.repo_full_name == "community/community"
            assert discussion.discussion_number == 42
            assert discussion.comments_count == 5
            assert discussion.upvote_count == 9
            assert metric.discussion_id == discussion.id
            assert metric.comments_count == 5
            assert metric.upvote_count == 9
        finally:
            db.close()
    finally:
        app.dependency_overrides.clear()


def test_create_source_crawls_organization_discussions(tmp_path, monkeypatch):
    session_factory = make_test_session(tmp_path)

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    class FakeGitHubClient:
        def fetch_recent_discussions(self, owner, repo, created_since, include_comments=False):
            assert owner == "community"
            assert repo == "community"
            return [
                GitHubDiscussion(
                    github_discussion_id="OD_community_1",
                    repo_full_name="community/community",
                    discussion_number=7,
                    title="Org welcome discussion",
                    author_login="octocat",
                    category_name="General",
                    comments_count=2,
                    upvote_count=4,
                    html_url="https://github.com/orgs/community/discussions/7",
                    discussion_created_at=datetime(2026, 1, 1),
                    discussion_updated_at=datetime(2026, 1, 2),
                )
            ]

    monkeypatch.setattr("app.services.scraper.GitHubGraphQLClient", FakeGitHubClient)
    app.dependency_overrides[get_db] = override_get_db
    try:
        client = TestClient(app)
        response = client.post(
            "/sources",
            json={"url": "https://github.com/orgs/community/discussions"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["job"]["status"] == "done"
        assert body["job"]["discussions_found"] == 1
        assert body["source"]["source_type"] == "organization_discussions"
        assert body["source"]["identifier"] == "community"

        db = session_factory()
        try:
            discussion = db.query(Discussion).one()
            metric = db.query(DiscussionMetric).one()

            assert discussion.repo_full_name == "community/community"
            assert discussion.discussion_number == 7
            assert metric.discussion_id == discussion.id
        finally:
            db.close()
    finally:
        app.dependency_overrides.clear()


def test_create_source_crawls_organization_repositories(tmp_path, monkeypatch):
    session_factory = make_test_session(tmp_path)

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    class FakeGitHubClient:
        def fetch_discussion_enabled_repositories(self, organization):
            assert organization == "vercel"
            return [
                GitHubRepository(
                    name="next.js",
                    name_with_owner="vercel/next.js",
                    has_discussions_enabled=True,
                )
            ]

        def fetch_recent_discussions(
            self, owner, repo, created_since, include_comments=False
        ):
            assert owner == "vercel"
            assert repo == "next.js"
            return [
                GitHubDiscussion(
                    github_discussion_id="D_vercel_next_recent",
                    repo_full_name="vercel/next.js",
                    discussion_number=95735,
                    title="Recent Vercel discussion",
                    author_login="octocat",
                    category_name="General",
                    comments_count=1,
                    upvote_count=2,
                    html_url="https://github.com/vercel/next.js/discussions/95735",
                    discussion_created_at=datetime(2026, 7, 13),
                    discussion_updated_at=datetime(2026, 7, 13),
                )
            ]

    monkeypatch.setattr("app.services.scraper.GitHubGraphQLClient", FakeGitHubClient)
    app.dependency_overrides[get_db] = override_get_db
    try:
        client = TestClient(app)
        response = client.post(
            "/sources",
            json={"url": "https://github.com/orgs/vercel/repositories"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["job"]["status"] == "done"
        assert body["job"]["discussions_found"] == 1
        assert body["source"]["source_type"] == "organization_repositories"
        assert body["source"]["identifier"] == "vercel"

        db = session_factory()
        try:
            discussion = db.query(Discussion).one()
            metric = db.query(DiscussionMetric).one()

            assert discussion.repo_full_name == "vercel/next.js"
            assert discussion.discussion_number == 95735
            assert metric.discussion_id == discussion.id
        finally:
            db.close()
    finally:
        app.dependency_overrides.clear()
