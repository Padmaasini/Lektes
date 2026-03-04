import httpx
import re


def extract_linkedin_username(url: str) -> str | None:
    """Extract username/slug from a LinkedIn profile URL."""
    if not url:
        return None
    match = re.search(r'linkedin\.com/in/([\w\-]+)', url)
    if match:
        return match.group(1)
    # Plain username passed directly
    if "/" not in url and "." not in url:
        return url
    return None


async def verify_linkedin(linkedin_url: str) -> dict | None:
    """
    Verify a LinkedIn profile by checking if the public URL is reachable.
    LinkedIn does not offer a free data API — this confirms the profile exists
    and is publicly visible without scraping or requiring credentials.

    Returns a dict with exists=True on success, None on failure.
    """
    username = extract_linkedin_username(linkedin_url)
    if not username:
        return None

    clean_url = f"https://www.linkedin.com/in/{username}/"

    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=8.0,
            headers={
                # Use a standard browser user-agent to avoid bot blocks
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            }
        ) as client:
            response = await client.get(clean_url)

        # 200 = public profile, 404 = profile not found, 999 = LinkedIn bot block
        if response.status_code == 200:
            print(f"  [LinkedIn] Profile verified: {username}")
            return {
                "username":     username,
                "profile_url":  clean_url,
                "exists":       True,
                "status_code":  response.status_code,
            }
        elif response.status_code == 404:
            print(f"  [LinkedIn] Profile not found: {username}")
            return None
        else:
            # 999 or other — LinkedIn bot detection, treat as unverified
            print(f"  [LinkedIn] Unverifiable (status {response.status_code}): {username}")
            return None

    except Exception as e:
        print(f"  [LinkedIn] Error checking {username}: {e}")
        return None
