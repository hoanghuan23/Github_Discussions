from urllib.parse import urlparse


SOURCE_TYPE_REPOSITORY = "repository"
SOURCE_TYPE_ORGANIZATION_REPOSITORIES = "organization_repositories"
SOURCE_TYPE_ORGANIZATION_DISCUSSIONS = "organization_discussions"
SOURCE_TYPE_CATEGORY = "category"

SOURCE_TYPES = {
    SOURCE_TYPE_REPOSITORY,
    SOURCE_TYPE_ORGANIZATION_REPOSITORIES,
    SOURCE_TYPE_ORGANIZATION_DISCUSSIONS,
    SOURCE_TYPE_CATEGORY,
}


def parse_source(value: str) -> tuple[str, str]:
    candidate = value.strip().removesuffix("/")
    if candidate.startswith("http://") or candidate.startswith("https://"):
        return parse_github_source_url(candidate)

    parts = [part for part in candidate.split("/") if part]
    if len(parts) == 2:
        return SOURCE_TYPE_REPOSITORY, candidate
    if len(parts) == 3:
        return SOURCE_TYPE_CATEGORY, "/".join(parts)

    raise ValueError("Source must be a supported GitHub source URL or identifier")


def parse_github_source_url(value: str) -> tuple[str, str]:
    parsed = urlparse(value)
    parts = [part for part in parsed.path.split("/") if part]
    if parsed.netloc.lower() != "github.com":
        raise ValueError("Only github.com source URLs are supported")

    if len(parts) >= 3 and parts[0] == "orgs" and parts[2] == "discussions":
        if len(parts) >= 5 and parts[3] == "categories":
            return SOURCE_TYPE_CATEGORY, f"{parts[1]}/{parts[4]}"
        return SOURCE_TYPE_ORGANIZATION_DISCUSSIONS, parts[1]

    if len(parts) >= 3 and parts[0] == "orgs" and parts[2] == "repositories":
        return SOURCE_TYPE_ORGANIZATION_REPOSITORIES, parts[1]

    if len(parts) >= 3 and parts[2] == "discussions":
        if len(parts) >= 5 and parts[3] == "categories":
            return SOURCE_TYPE_CATEGORY, f"{parts[0]}/{parts[1]}/{parts[4]}"
        return SOURCE_TYPE_REPOSITORY, f"{parts[0]}/{parts[1]}"

    raise ValueError("Unsupported GitHub Discussions source URL")


def parse_repo_identifier(value: str) -> str:
    source_type, identifier = parse_source(value)
    if source_type != SOURCE_TYPE_REPOSITORY:
        raise ValueError("Source must be a GitHub repository URL or owner/repo")
    return identifier


def split_repo_identifier(identifier: str) -> tuple[str, str]:
    owner, repo = identifier.split("/", 1)
    return owner, repo
