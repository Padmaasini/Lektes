import httpx
import re
from app.core.config import settings


def extract_kaggle_username(url: str) -> str | None:
    """Extract username from a Kaggle profile URL."""
    if not url:
        return None
    match = re.search(r'kaggle\.com/([\w\-]+)', url)
    if match:
        username = match.group(1)
        # Skip non-profile paths
        if username.lower() in {"datasets", "competitions", "code", "models", "discuss"}:
            return None
        return username
    if "/" not in url and "." not in url:
        return url
    return None


async def verify_kaggle(kaggle_url: str) -> dict | None:
    """
    Verify a Kaggle profile using the official Kaggle REST API.
    Requires KAGGLE_USERNAME and KAGGLE_KEY in Render environment.

    Returns tier, competition count, dataset count — strong signal
    for data science / BI roles.
    """
    if not settings.KAGGLE_USERNAME or not settings.KAGGLE_KEY:
        print("  [Kaggle] Credentials not configured — skipping")
        return None

    username = extract_kaggle_username(kaggle_url)
    if not username:
        return None

    try:
        async with httpx.AsyncClient(
            auth=(settings.KAGGLE_USERNAME, settings.KAGGLE_KEY),
            timeout=10.0,
            headers={"Content-Type": "application/json"}
        ) as client:
            resp = await client.get(
                f"https://www.kaggle.com/api/v1/users/{username}/inbox",
            )

            # Use the public profile metadata endpoint instead
            profile_resp = await client.get(
                f"https://www.kaggle.com/api/v1/users/{username}"
            )

            if profile_resp.status_code != 200:
                print(f"  [Kaggle] Profile not found: {username} (status {profile_resp.status_code})")
                return None

            data = profile_resp.json()

        tier = data.get("tier", "Novice")
        result = {
            "username":          username,
            "display_name":      data.get("displayName", ""),
            "tier":              tier,
            "ranking":           data.get("ranking", None),
            "total_votes":       data.get("totalVotes", 0),
            "competitions_gold": data.get("competitionsGoldMedals", 0),
            "competitions_silver": data.get("competitionsSilverMedals", 0),
            "datasets_count":    data.get("datasetsCount", 0),
            "notebooks_count":   data.get("notebooksCount", 0),
        }
        print(
            f"  [Kaggle] Verified: {username} — "
            f"Tier: {tier}, "
            f"Competitions: {result['competitions_gold']}G/{result['competitions_silver']}S"
        )
        return result

    except Exception as e:
        print(f"  [Kaggle] Error checking {username}: {e}")
        return None


def kaggle_tier_score(tier: str) -> int:
    """
    Convert Kaggle tier to a bonus contribution.
    Grandmaster and Master are exceptional signals for data roles.
    """
    tiers = {
        "Grandmaster": 5,
        "Master":      4,
        "Expert":      3,
        "Contributor": 2,
        "Novice":      1,
    }
    return tiers.get(tier, 0)
