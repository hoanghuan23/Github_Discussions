import json
import os
from pathlib import Path

import requests
from dotenv import load_dotenv


GRAPHQL_URL = "https://api.github.com/graphql"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = PROJECT_ROOT / ".env"

GITHUB_DISCUSSION_ID = "D_kwDOBC3Cis4AnvSc"


DISCUSSION_BY_ID_QUERY = """
query($discussionId: ID!) {
  node(id: $discussionId) {
    ... on Discussion {
      id
      number
      title
      url
      comments {
        totalCount
      }
      upvoteCount
    }
  }
}
"""


def github_graphql_request(query: str, variables: dict) -> dict:
    load_dotenv(ENV_FILE)
    github_token = os.getenv("GITHUB_TOKEN")

    if not github_token:
        raise RuntimeError("Khong tim thay GITHUB_TOKEN trong file .env")

    response = requests.post(
        GRAPHQL_URL,
        headers={
            "Authorization": f"Bearer {github_token}",
            "Content-Type": "application/json",
        },
        json={
            "query": query,
            "variables": variables,
        },
        timeout=30,
    )

    response.raise_for_status()
    payload = response.json()

    if payload.get("errors"):
        raise RuntimeError(json.dumps(payload["errors"], ensure_ascii=False, indent=2))

    return payload


def format_discussion_metrics(discussion: dict) -> dict:
    if discussion is None:
        raise RuntimeError("Khong tim thay Discussion")

    return {
        "github_discussion_id": discussion["id"],
        "discussion_number": discussion["number"],
        "title": discussion["title"],
        "comments_count": discussion["comments"]["totalCount"],
        "upvote_count": discussion["upvoteCount"],
        "html_url": discussion["url"],
    }


def get_discussion_metrics(github_discussion_id: str) -> dict:
    github_discussion_id = github_discussion_id.strip()

    if not github_discussion_id or github_discussion_id == "D_kwDO_REPLACE_ME":
        raise RuntimeError("Hay truyen github_discussion_id that")

    payload = github_graphql_request(
        DISCUSSION_BY_ID_QUERY,
        {"discussionId": github_discussion_id},
    )
    discussion = payload.get("data", {}).get("node")
    return format_discussion_metrics(discussion)


if __name__ == "__main__":
    metrics = get_discussion_metrics(GITHUB_DISCUSSION_ID)
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
