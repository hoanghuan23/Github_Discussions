from dataclasses import dataclass, field
from datetime import datetime

import requests

from app.core.config import settings


@dataclass(frozen=True)
class GitHubComment:
    github_comment_id: str
    author_login: str | None
    comment_body: str | None
    html_url: str | None
    comment_created_at: datetime


@dataclass(frozen=True)
class GitHubDiscussion:
    github_discussion_id: str
    repo_full_name: str
    discussion_number: int
    title: str
    author_login: str | None
    category_name: str | None
    comments_count: int
    upvote_count: int
    html_url: str
    discussion_created_at: datetime
    discussion_updated_at: datetime
    comments: list[GitHubComment] = field(default_factory=list)


DISCUSSIONS_QUERY = """
query($owner: String!, $repo: String!, $first: Int!, $after: String, $commentsFirst: Int!) {
  repository(owner: $owner, name: $repo) {
    nameWithOwner
    discussions(first: $first, after: $after, orderBy: {field: CREATED_AT, direction: DESC}) {
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
        author {
          login
        }
        category {
          name
        }
        comments(first: $commentsFirst) {
          totalCount
          nodes {
            id
            body
            url
            createdAt
            author {
              login
            }
          }
        }
      }
    }
  }
}
"""

DISCUSSION_BY_NUMBER_QUERY = """
query($owner: String!, $repo: String!, $number: Int!, $commentsFirst: Int!) {
  repository(owner: $owner, name: $repo) {
    nameWithOwner
    discussion(number: $number) {
      id
      number
      title
      url
      createdAt
      updatedAt
      upvoteCount
      author {
        login
      }
      category {
        name
      }
      comments(first: $commentsFirst) {
        totalCount
        nodes {
          id
          body
          url
          createdAt
          author {
            login
          }
        }
      }
    }
  }
}
"""


def parse_github_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)


class GitHubGraphQLClient:
    def __init__(self, token: str | None = None, endpoint: str | None = None):
        self.token = token if token is not None else settings.github_token
        self.endpoint = endpoint or settings.github_graphql_url

    def fetch_recent_discussions(
        self,
        owner: str,
        repo: str,
        created_since: datetime,
        include_comments: bool = False,
    ) -> list[GitHubDiscussion]:
        if not self.token:
            raise RuntimeError("GITHUB_TOKEN is required to crawl GitHub Discussions")

        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        page_size = settings.github_page_size
        comments_first = 50 if include_comments else 0
        after = None
        found: list[GitHubDiscussion] = []

        while True:
            payload = {
                "query": DISCUSSIONS_QUERY,
                "variables": {
                    "owner": owner,
                    "repo": repo,
                    "first": page_size,
                    "after": after,
                    "commentsFirst": comments_first,
                },
            }
            response = requests.post(
                self.endpoint,
                headers=headers,
                json=payload,
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
            if data.get("errors"):
                raise RuntimeError(data["errors"])

            repository = data.get("data", {}).get("repository")
            if not repository:
                raise RuntimeError("GitHub repository not found or inaccessible")

            discussions = repository["discussions"]["nodes"] or []
            should_stop = False
            for item in discussions:
                created_at = parse_github_datetime(item["createdAt"])
                if created_at < created_since.replace(tzinfo=None):
                    should_stop = True
                    break
                found.append(self._parse_discussion(repository["nameWithOwner"], item))

            page_info = repository["discussions"]["pageInfo"]
            if should_stop or not page_info["hasNextPage"]:
                break
            after = page_info["endCursor"]

        return found

    def _parse_discussion(self, repo_full_name: str, item: dict) -> GitHubDiscussion:
        comments = []
        for node in item.get("comments", {}).get("nodes") or []:
            comments.append(
                GitHubComment(
                    github_comment_id=node["id"],
                    author_login=node["author"]["login"] if node.get("author") else None,
                    comment_body=node.get("body"),
                    html_url=node.get("url"),
                    comment_created_at=parse_github_datetime(node["createdAt"]),
                )
            )

        return GitHubDiscussion(
            github_discussion_id=item["id"],
            repo_full_name=repo_full_name,
            discussion_number=item["number"],
            title=item["title"],
            author_login=item["author"]["login"] if item.get("author") else None,
            category_name=item["category"]["name"] if item.get("category") else None,
            comments_count=item["comments"]["totalCount"],
            upvote_count=item["upvoteCount"],
            html_url=item["url"],
            discussion_created_at=parse_github_datetime(item["createdAt"]),
            discussion_updated_at=parse_github_datetime(item["updatedAt"]),
            comments=comments,
        )

    def fetch_discussion_by_number(
        self,
        owner: str,
        repo: str,
        number: int,
        include_comments: bool = False,
    ) -> GitHubDiscussion:
        if not self.token:
            raise RuntimeError("GITHUB_TOKEN is required to crawl GitHub Discussions")

        response = requests.post(
            self.endpoint,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
            json={
                "query": DISCUSSION_BY_NUMBER_QUERY,
                "variables": {
                    "owner": owner,
                    "repo": repo,
                    "number": number,
                    "commentsFirst": 50 if include_comments else 0,
                },
            },
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        if data.get("errors"):
            raise RuntimeError(data["errors"])

        repository = data.get("data", {}).get("repository")
        discussion = repository.get("discussion") if repository else None
        if not repository or not discussion:
            raise RuntimeError("GitHub discussion not found or inaccessible")

        return self._parse_discussion(repository["nameWithOwner"], discussion)
