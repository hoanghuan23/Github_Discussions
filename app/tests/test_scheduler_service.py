import logging
from datetime import datetime, timedelta
from types import SimpleNamespace

from app.db.models import Discussion, Source, SourceDiscussion
from app.services.scheduler import run_due_once
from app.tests.helpers import make_test_session


def test_run_due_once_scrapes_due_sources_and_runs_due_metrics(
    tmp_path,
    caplog,
    monkeypatch,
):
    session_factory = make_test_session(tmp_path)
    now = datetime(2026, 7, 14, 9, 32, 0)
    calls = {"scraped": [], "metrics": 0}

    db = session_factory()
    try:
        due_source = Source(
            source_type="repository",
            identifier="vercel/next.js",
            is_active=True,
            is_accessible=True,
            include_comments=False,
            created_at=now,
            next_scrape=now - timedelta(seconds=1),
        )
        future_source = Source(
            source_type="repository",
            identifier="python/cpython",
            is_active=True,
            is_accessible=True,
            include_comments=False,
            created_at=now,
            next_scrape=now + timedelta(minutes=10),
        )
        db.add_all([due_source, future_source])
        db.flush()
        discussion = Discussion(
            github_discussion_id="D_due",
            source_id=due_source.id,
            repo_full_name="vercel/next.js",
            discussion_number=10,
            title="Due discussion",
            comments_count=1,
            upvote_count=1,
            html_url="https://github.com/vercel/next.js/discussions/10",
            discussion_created_at=now,
            discussion_updated_at=now,
            created_at=now,
            is_tracked=True,
            is_deleted=False,
            last_metric_update=now - timedelta(hours=1),
            next_metric_update=now - timedelta(seconds=1),
            metric_tier="very_low",
        )
        db.add(discussion)
        db.flush()
        db.add(
            SourceDiscussion(
                source_id=due_source.id,
                discussion_id=discussion.id,
                first_seen_at=now,
                last_seen_at=now,
            )
        )
        db.commit()
    finally:
        db.close()

    class FakeScraperService:
        def scrape_source(self, db, source, job_type="new_discussions"):
            calls["scraped"].append((source.identifier, job_type))
            return SimpleNamespace(
                discussions_found=2,
                discussions_new=1,
                discussions_updated=1,
                items_failed=0,
            )

        def update_due_metrics(self, db):
            calls["metrics"] += 1
            return SimpleNamespace(
                discussions_found=1,
                discussions_updated=1,
                items_failed=0,
            )

    monkeypatch.setattr("app.services.scheduler.utcnow", lambda: now)
    with caplog.at_level(logging.INFO, logger="github_discussions.scheduler"):
        result = run_due_once(
            session_factory=session_factory,
            scraper_factory=FakeScraperService,
        )

    assert calls == {"scraped": [("vercel/next.js", "new_discussions")], "metrics": 1}
    assert result.sources_due == 1
    assert result.metrics_due == 1
    assert result.sources_processed == 1
    assert result.posts_processed == 3
    assert "Scheduler bat dau chu ky | sources_due=1 metrics_due=1" in caplog.text
    assert (
        "Hoan tat scrape bai moi | source=vercel/next.js id=1 found=2 new=1 updated=1 failed=0"
        in caplog.text
    )
    assert "Hoan tat cap nhat metrics | updated=1 failed=0" in caplog.text
