# GitHub Discussions Crawler

Backend FastAPI để crawl GitHub Discussions bằng GitHub GraphQL API, lưu discussion/comment/metric/job vào SQLite theo schema có sẵn trong `data/schema_table_github_discussions_minimal.sql`.

Database hiện tại là contract chính của dự án. Code không tự thay đổi schema và mặc định dùng `data/github_discussions.db`.

## Chức Năng Chính

- Tạo source dạng repository từ URL GitHub hoặc `owner/repo`.
- Crawl discussion mới trong cửa sổ `LOOKBACK_HOURS`, mặc định 24 giờ.
- Upsert discussion theo `github_discussion_id` hoặc `(repo_full_name, discussion_number)`.
- Lưu mapping source-discussion trong `source_discussions`.
- Lưu snapshot metric vào `discussion_metrics`.
- Ghi trạng thái scrape/update vào `pipeline_jobs`.
- Chỉ crawl chi tiết comment vào `discussion_comments` khi source có `include_comments=true`.
- API để list source, discussion, job và chạy scrape/metric thủ công.

## Stack

- FastAPI
- SQLAlchemy 2.x
- Pydantic 2.x
- SQLite
- requests
- pytest, httpx

## Cài Đặt

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Tạo `.env` hoặc set env var trực tiếp:

```bash
GITHUB_TOKEN=ghp_xxx
DATABASE_URL=sqlite:///./data/github_discussions.db
LOOKBACK_HOURS=24
GITHUB_PAGE_SIZE=50
DEFAULT_SCRAPE_INTERVAL_MINUTES=60
DEFAULT_METRIC_INTERVAL_MINUTES=60
```

Env var trên hệ điều hành sẽ ưu tiên hơn giá trị trong `.env`.

## Chạy App

```bash
uvicorn app.main:app --reload
```

Khi app start, nếu database chưa có bảng `sources`, app sẽ tạo schema từ `data/schema_table_github_discussions_minimal.sql`. Nếu `data/github_discussions.db` đã có sẵn, app dùng nguyên schema hiện tại.

## API

- `GET /health`: health check.
- `POST /sources`: tạo source; source `repository` sẽ scrape ngay, các type khác hiện chỉ được lưu.
- `GET /sources`: list source.
- `GET /sources/{source_id}`: xem source.
- `POST /sources/{source_id}/scrape`: scrape source thủ công.
- `GET /discussions`: list discussion, filter bằng `repo_full_name`, `source_id`, `metric_tier`, `is_tracked`, `limit`, `offset`.
- `GET /discussions/{discussion_id}`: xem discussion.
- `POST /metrics/due/run`: update metric due thủ công.
- `GET /jobs`: list pipeline jobs.
- `GET /jobs/{job_id}`: xem job.

Ví dụ tạo source:

```bash
curl -X POST http://127.0.0.1:8000/sources \
  -H "Content-Type: application/json" \
  -d '{"url":"https://github.com/vercel/next.js/discussions","include_comments":false}'
```

Hoặc dùng `owner/repo`:

```bash
curl -X POST http://127.0.0.1:8000/sources \
  -H "Content-Type: application/json" \
  -d '{"url":"github/community","include_comments":true}'
```

## Database

Schema hiện có gồm:

- `sources`
- `discussions`
- `source_discussions`
- `analytics_cache`
- `pipeline_jobs`
- `discussion_metrics`
- `discussion_comments`
- `pipeline_logs`

`sources.source_type` hỗ trợ 4 kiểu: `repository`, `organization_repositories`, `organization_discussions`, `category`.
V1 chỉ crawl ngay `repository`; các type còn lại được lưu để mở rộng crawler sau.

## Cấu Trúc Thư Mục

```text
app/
  main.py                  # FastAPI app
  core/                    # Config
  db/                      # SQLAlchemy session, models, Pydantic schemas
  api/                     # Route modules
  repositories/            # Upsert discussion/comment/metric
  services/                # GitHub GraphQL client, source parser, scraper
tests/                     # Test suite
test_crawl_data/           # Prototype/debug scripts crawl GraphQL
data/                      # SQLite DB và SQL schema
```

## Test

```bash
pytest
```
