import httpx
import re


def extract_stackoverflow_user_id(url: str) -> str | None:
    """
    Extract user ID from a StackOverflow profile URL.
    Handles formats like:
      - stackoverflow.com/users/12345/username
      - stackoverflow.com/users/12345
    """
    if not url:
        return None
    match = re.search(r'stackoverflow\.com/users/(\d+)', url)
    if match:
        return match.group(1)
    # Plain numeric ID passed
    if url.isdigit():
        return url
    return None


async def verify_stackoverflow(stackoverflow_url: str) -> dict | None:
    """
    Verify a StackOverflow profile using the free public Stack Exchange API.
    No credentials required — 300 requests/day unauthenticated, 10000 with key.

    Returns reputation, badge counts, top tags — strong signal for
    backend/data engineering roles.

    API docs: api.stackexchange.com
    """
    user_id = extract_stackoverflow_user_id(stackoverflow_url)
    if not user_id:
        print(f"  [StackOverflow] Could not extract user ID from: {stackoverflow_url}")
        return None

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:

            # Fetch user profile
            profile_resp = await client.get(
                f"https://api.stackexchange.com/2.3/users/{user_id}",
                params={
                    "site":  "stackoverflow",
                    "filter": "default",
                }
            )
            if profile_resp.status_code != 200:
                print(f"  [StackOverflow] Profile not found: user {user_id}")
                return None

            profile_data = profile_resp.json()
            items = profile_data.get("items", [])
            if not items:
                print(f"  [StackOverflow] No profile data for user {user_id}")
                return None

            user = items[0]

            # Fetch top tags (what topics they answer most)
            tags_resp = await client.get(
                f"https://api.stackexchange.com/2.3/users/{user_id}/top-answer-tags",
                params={"site": "stackoverflow", "pagesize": 5}
            )
            top_tags = []
            if tags_resp.status_code == 200:
                tags_data = tags_resp.json()
                top_tags = [
                    t.get("tag_name")
                    for t in tags_data.get("items", [])[:5]
                    if t.get("tag_name")
                ]

        reputation   = user.get("reputation", 0)
        badge_counts = user.get("badge_counts", {})

        result = {
            "user_id":        user_id,
            "display_name":   user.get("display_name", ""),
            "reputation":     reputation,
            "gold_badges":    badge_counts.get("gold", 0),
            "silver_badges":  badge_counts.get("silver", 0),
            "bronze_badges":  badge_counts.get("bronze", 0),
            "top_tags":       top_tags,
            "answer_count":   user.get("answer_count", 0),
            "question_count": user.get("question_count", 0),
            "member_since":   user.get("creation_date", 0),
            "profile_url":    user.get("link", ""),
        }
        print(
            f"  [StackOverflow] Verified: {user.get('display_name')} — "
            f"Reputation: {reputation:,}, "
            f"Tags: {', '.join(top_tags[:3])}"
        )
        return result

    except Exception as e:
        print(f"  [StackOverflow] Error checking user {user_id}: {e}")
        return None


def stackoverflow_reputation_score(reputation: int) -> int:
    """
    Convert StackOverflow reputation to a bonus contribution.
    Reputation reflects sustained technical contribution over time.
    """
    if reputation >= 10000:
        return 5   # Very active, recognised expert
    elif reputation >= 3000:
        return 4
    elif reputation >= 1000:
        return 3
    elif reputation >= 500:
        return 2
    elif reputation >= 100:
        return 1
    return 0
