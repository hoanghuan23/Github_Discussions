import os
from dotenv import load_dotenv
import requests
import json
from datetime import datetime, timedelta, timezone

url = "https://api.github.com/graphql"
OWNER = "vercel"
REPO = "next.js"
SOURCE_ID = None
PAGE_SIZE = 50
LOOKBACK_HOURS = 24

load_dotenv()
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

headers = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Content-Type": "application/json",
}

query = """
query($owner: String!, $repo: String!, $first: Int!, $after: String) {
    repository(owner: $owner, name: $repo) {
        nameWithOwner
        discussions(
        first: $first
        after: $after
        orderBy: {field: CREATED_AT, direction: DESC}
        ){
            pageInfo {
                hasNextPage
                endCursor
            }
            nodes {
                id
                number
                title
                url
                createdAt
                updatedAt
                upvoteCount
                isAnswered
                author {
                    login
                }
                category {
                    name
                }
                comments {
                    totalCount
                }
            }
        }
    }
}
"""

created_since = datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)
after = None
repository = None
recent_discussions = []

while True:
    response = requests.post(
        url,
        headers=headers,
        json={
            "query": query,
            "variables": {
                "owner": OWNER,
                "repo": REPO,
                "first": PAGE_SIZE,
                "after": after,
            },
        },
        timeout=30,
    )

    response.raise_for_status()
    data = response.json()

    if "errors" in data:
        raise RuntimeError(data["errors"])
    if "data" not in data:
        raise RuntimeError(f"Github response: {data}")

    repository = data["data"]["repository"]
    discussions = repository["discussions"]["nodes"]

    should_stop = False
    for item in discussions:
        created_at = datetime.fromisoformat(item["createdAt"].replace("Z", "+00:00"))
        if created_at < created_since:
            should_stop = True
            break

        recent_discussions.append(item)

    page_info = repository["discussions"]["pageInfo"]
    if should_stop or not page_info["hasNextPage"]:
        break

    after = page_info["endCursor"]

print(
    f"Found {len(recent_discussions)} discussions created in last "
    f"{LOOKBACK_HOURS}h since {created_since.isoformat()}"
)

for item in recent_discussions:
    discussion = {
        "github_discussion_id": item["id"],
        "repo_full_name": repository["nameWithOwner"],
        "discussion_number": item["number"],
        "title": item["title"],
        "author_login": item["author"]["login"] if item["author"] else None,
        "category_name": item["category"]["name"] if item["category"] else None,
        "comments_count": item["comments"]["totalCount"],
        "upvote_count": item["upvoteCount"],
        "html_url": item["url"],
        "createdAt": item["createdAt"],
    }
    print(json.dumps(discussion, ensure_ascii=False, indent=2))
