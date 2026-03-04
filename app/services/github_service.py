import httpx
import re
from app.core.config import settings


def extract_github_username(url: str) -> str | None:
    """Extract username from a GitHub profile URL."""
    if not url:
        return None
    match = re.search(r'github\.com/([\w\-]+)', url)
    if match:
        username = match.group(1)
        # Skip common non-profile paths
        if username.lower() in {"orgs", "apps", "marketplace", "features", "topics"}:
            return None
        return username
    if "/" not in url and "." not in url:
        return url
    return None


async def verify_github(github_url: str) -> dict | None:
    """
    Verify a GitHub profile using GitHub's free public REST API.
    No credentials required for public profiles.
    Optionally uses GITHUB_TOKEN for higher rate limits (5000/hr vs 60/hr).

    Returns profile stats useful for scoring technical candidates.
    """
    username = extract_github_username(github_url)
    if not username:
        return None

    headers = {"Accept": "application/vnd.github.v3+json"}
    if settings.GITHUB_TOKEN:
        headers["Authorization"] = f"token {settings.GITHUB_TOKEN}"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:

            # Fetch profile
            profile_resp = await client.get(
                f"https://api.github.com/users/{username}",
                headers=headers
            )
            if profile_resp.status_code != 200:
                print(f"  [GitHub] Profile not found: {username}")
                return None

            profile = profile_resp.json()

            # Fetch recent repos for language + activity analysis
            repos_resp = await client.get(
                f"https://api.github.com/users/{username}/repos"
                f"?per_page=30&sort=updated",
                headers=headers
            )
            repos = repos_resp.json() if repos_resp.status_code == 200 else []

        # Analyse languages
        languages: dict = {}
        total_stars = 0
        for repo in repos:
            lang = repo.get("language")
            if lang:
                languages[lang] = languages.get(lang, 0) + 1
            total_stars += repo.get("stargazers_count", 0)

        top_languages = [
            lang for lang, _ in
            sorted(languages.items(), key=lambda x: x[1], reverse=True)[:5]
        ]

        result = {
            "username":       username,
            "name":           profile.get("name", ""),
            "public_repos":   profile.get("public_repos", 0),
            "followers":      profile.get("followers", 0),
            "bio":            profile.get("bio", ""),
            "company":        profile.get("company", ""),
            "top_languages":  top_languages,
            "total_stars":    total_stars,
            "account_created": profile.get("created_at", "")[:10],
            "last_active":    profile.get("updated_at", "")[:10],
        }
        print(
            f"  [GitHub] Verified: {username} — "
            f"{result['public_repos']} repos, "
            f"{result['followers']} followers, "
            f"languages: {', '.join(top_languages[:3])}"
        )
        return result

    except Exception as e:
        print(f"  [GitHub] Error checking {username}: {e}")
        return None
