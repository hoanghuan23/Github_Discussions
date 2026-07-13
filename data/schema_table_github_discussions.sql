-- GitHub Discussions crawler schema (minimal)
-- Mục tiêu:
--   - Theo dõi discussion mới/cập nhật trong repository GitHub.
--   - Xếp hạng độ hot theo comments_count và upvote_count.
--   - Chỉ crawl nội dung comment khi sources.include_comments = 1.

PRAGMA foreign_keys = ON;

CREATE TABLE sources (
    id INTEGER PRIMARY KEY,

    source_type VARCHAR(40) NOT NULL
        CHECK (source_type IN (
            'repository',
            'organization_repositories',
            'organization_discussions',
            'category'
        )),

    -- Quy ước identifier:
    -- repository:                   solidjs/solid
    -- organization_repositories:    vercel
    -- organization_discussions:     community
    -- category:                     solidjs/solid/general
    identifier VARCHAR(300) NOT NULL,

    is_active BOOLEAN NOT NULL DEFAULT 1,
    is_accessible BOOLEAN NOT NULL DEFAULT 1,
    include_comments BOOLEAN NOT NULL DEFAULT 0,

    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_scraped DATETIME,
    next_scrape DATETIME,

    schedule_tier INTEGER,
    schedule_override_minutes INTEGER,

    UNIQUE (source_type, identifier)
);

CREATE INDEX idx_sources_next_scrape
    ON sources (is_active, is_accessible, next_scrape);


CREATE TABLE discussions (
    id INTEGER PRIMARY KEY,

    -- GitHub Discussion dùng GraphQL Node ID dạng chuỗi.
    github_discussion_id VARCHAR(100) NOT NULL,
    source_id INTEGER REFERENCES sources(id) ON DELETE SET NULL,
    repo_full_name VARCHAR(300) NOT NULL,
    discussion_number INTEGER NOT NULL,

    title TEXT NOT NULL,
    author_login VARCHAR(100),
    category_name VARCHAR(200),

    comments_count INTEGER NOT NULL DEFAULT 0,
    upvote_count INTEGER NOT NULL DEFAULT 0,
    html_url TEXT NOT NULL,

    discussion_created_at DATETIME NOT NULL,
    discussion_updated_at DATETIME NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    is_tracked BOOLEAN NOT NULL DEFAULT 1,
    tracking_until DATETIME,
    is_deleted BOOLEAN NOT NULL DEFAULT 0,

    last_metric_update DATETIME,
    next_metric_update DATETIME,
    metric_tier VARCHAR(20) NOT NULL DEFAULT 'bootstrap'
        CHECK (metric_tier IN (
            'hot', 'high', 'medium', 'low', 'very_low', 'bootstrap'
        )),

    UNIQUE (github_discussion_id),
    UNIQUE (repo_full_name, discussion_number)
);

CREATE INDEX idx_discussions_created
    ON discussions (discussion_created_at);
CREATE INDEX idx_discussions_hot
    ON discussions (comments_count DESC, upvote_count DESC);
CREATE INDEX idx_discussions_metric_due
    ON discussions (is_tracked, next_metric_update);
CREATE INDEX idx_discussions_source
    ON discussions (source_id);


-- Một discussion có thể được tìm thấy từ nhiều source.
CREATE TABLE source_discussions (
    source_id INTEGER NOT NULL,
    discussion_id INTEGER NOT NULL,

    first_seen_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (source_id, discussion_id),

    FOREIGN KEY (source_id)
        REFERENCES sources(id) ON DELETE CASCADE,
    FOREIGN KEY (discussion_id)
        REFERENCES discussions(id) ON DELETE CASCADE
);

CREATE INDEX idx_source_discussions_discussion
    ON source_discussions (discussion_id);


CREATE TABLE analytics_cache (
    id INTEGER PRIMARY KEY,
    source_id INTEGER NOT NULL,
    date DATE NOT NULL,

    total_discussions INTEGER NOT NULL DEFAULT 0,
    total_comments INTEGER NOT NULL DEFAULT 0,
    total_upvotes INTEGER NOT NULL DEFAULT 0,
    avg_comments_per_discussion FLOAT NOT NULL DEFAULT 0,
    top_discussion_id INTEGER,
    growth_rate FLOAT NOT NULL DEFAULT 0,
    cached_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (source_id, date),

    FOREIGN KEY (source_id)
        REFERENCES sources(id) ON DELETE CASCADE,
    FOREIGN KEY (top_discussion_id)
        REFERENCES discussions(id) ON DELETE SET NULL
);

CREATE INDEX idx_analytics_cache_source_date
    ON analytics_cache (source_id, date);


CREATE TABLE pipeline_jobs (
    id INTEGER PRIMARY KEY,

    job_type VARCHAR(30) NOT NULL DEFAULT 'scrape_discussions'
        CHECK (job_type IN (
            'scrape_discussions',
            'scrape_new_discussions',
            'update_metrics',
            'scrape_comments',
            'sync_repos'
        )),

    source_id INTEGER REFERENCES sources(id) ON DELETE SET NULL,

    status VARCHAR(10) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'running', 'done', 'failed')),

    discussions_found INTEGER NOT NULL DEFAULT 0,
    discussions_new INTEGER NOT NULL DEFAULT 0,
    discussions_updated INTEGER NOT NULL DEFAULT 0,
    items_failed INTEGER NOT NULL DEFAULT 0,

    error_message TEXT,
    started_at DATETIME,
    finished_at DATETIME,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_pipeline_jobs_source_time
    ON pipeline_jobs (source_id, started_at);
CREATE INDEX idx_pipeline_jobs_status
    ON pipeline_jobs (status, created_at);


-- Lưu lịch sử metric để theo dõi tốc độ tăng tương tác.
CREATE TABLE discussion_metrics (
    id INTEGER PRIMARY KEY,
    discussion_id INTEGER NOT NULL,

    comments_count INTEGER NOT NULL DEFAULT 0,
    upvote_count INTEGER NOT NULL DEFAULT 0,
    recorded_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    job_id INTEGER REFERENCES pipeline_jobs(id) ON DELETE SET NULL,

    FOREIGN KEY (discussion_id)
        REFERENCES discussions(id) ON DELETE CASCADE
);

CREATE INDEX idx_discussion_metrics_discussion_time
    ON discussion_metrics (discussion_id, recorded_at);
CREATE INDEX idx_discussion_metrics_recorded_at
    ON discussion_metrics (recorded_at);


-- Chỉ ghi bảng này khi source tương ứng có include_comments = 1.
CREATE TABLE discussion_comments (
    id INTEGER PRIMARY KEY,
    discussion_id INTEGER NOT NULL,

    github_comment_id VARCHAR(100) NOT NULL,
    author_login VARCHAR(100),
    comment_body TEXT,
    html_url TEXT,

    comment_created_at DATETIME NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (discussion_id)
        REFERENCES discussions(id) ON DELETE CASCADE,

    UNIQUE (github_comment_id)
);

CREATE INDEX idx_discussion_comments_discussion_time
    ON discussion_comments (discussion_id, comment_created_at);


CREATE TABLE pipeline_logs (
    id INTEGER PRIMARY KEY,

    job_id INTEGER REFERENCES pipeline_jobs(id) ON DELETE SET NULL,
    source_id INTEGER REFERENCES sources(id) ON DELETE SET NULL,

    log_level VARCHAR(20) NOT NULL DEFAULT 'ERROR'
        CHECK (log_level IN ('ERROR', 'WARNING')),

    message TEXT NOT NULL,
    error_type VARCHAR(100),
    error_details TEXT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_pipeline_logs_job
    ON pipeline_logs (job_id, created_at);
CREATE INDEX idx_pipeline_logs_source
    ON pipeline_logs (source_id, created_at);
