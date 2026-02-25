import httpx
from app.core.config import settings

async def verify_github(github_url: str) -> dict:
    """
    Verify a GitHub profile using GitHub's free REST API.
    No auth required for public profiles (60 req/hour unauthenticated,
    5000/hour with a token).
    """
    try:
        username = extract_github_username(github_url)
        if not username:
            return None

        headers = {"Accept": "application/vnd.github.v3+json"}
        if settings.GITHUB_TOKEN:
            headers["Authorization"] = f"token {settings.GITHUB_TOKEN}"

        async with httpx.AsyncClient() as client:
            # Get profile
            profile_resp = await client.get(
                f"https://api.github.com/users/{username}",
                headers=headers,
                timeout=10
            )

            if profile_resp.status_code != 200:
                return None

            profile = profile_resp.json()

            # Get repos for language analysis
            repos_resp = await client.get(
                f"https://api.github.com/users/{username}/repos?per_page=30&sort=updated",
                headers=headers,
                timeout=10
            )
            repos = repos_resp.json() if repos_resp.status_code == 200 else []

            # Analyse languages used
            languages = {}
            for repo in repos:
                lang = repo.get("language")
                if lang:
                    languages[lang] = languages.get(lang, 0) + 1

            top_languages = sorted(languages.items(), key=lambda x: x[1], reverse=True)[:5]

            return {
                "username": username,
                "name": profile.get("name", ""),
                "public_repos": profile.get("public_repos", 0),
                "followers": profile.get("followers", 0),
                "following": profile.get("following", 0),
                "bio": profile.get("bio", ""),
                "company": profile.get("company", ""),
                "top_languages": [lang for lang, _ in top_languages],
                "account_created": profile.get("created_at", "")[:10],
                "last_active": profile.get("updated_at", "")[:10],
                "total_stars": sum(r.get("stargazers_count", 0) for r in repos),
            }

    except Exception as e:
        print(f"  GitHub API error for {github_url}: {e}")
        return None

def extract_github_username(url: str) -> str:
    """Extract username from GitHub URL."""
    if not url:
        return None
    import re
    match = re.search(r'github\.com/([\w\-]+)', url)
    if match:
        return match.group(1)
    if "/" not in url and "." not in url:
        return url
    return None
