from app.core.config import settings

async def verify_linkedin(linkedin_url: str) -> dict:
    """
    Verify a LinkedIn profile using the linkedin-api library (free).
    Extracts username from URL and fetches profile data.
    """
    if not settings.LINKEDIN_USERNAME or not settings.LINKEDIN_PASSWORD:
        print("  ⚠️  LinkedIn credentials not configured — skipping verification")
        return None

    try:
        username = extract_linkedin_username(linkedin_url)
        if not username:
            return None

        from linkedin_api import Linkedin
        api = Linkedin(settings.LINKEDIN_USERNAME, settings.LINKEDIN_PASSWORD)
        profile = api.get_profile(username)

        if not profile:
            return None

        # Extract relevant fields
        return {
            "name": f"{profile.get('firstName', '')} {profile.get('lastName', '')}".strip(),
            "headline": profile.get("headline", ""),
            "location": profile.get("locationName", ""),
            "connections": profile.get("connections", 0),
            "experience_count": len(profile.get("experience", [])),
            "skills_count": len(profile.get("skills", [])),
            "education_count": len(profile.get("education", [])),
            "summary": profile.get("summary", "")[:500] if profile.get("summary") else "",
        }

    except Exception as e:
        print(f"  LinkedIn API error: {e}")
        return None

def extract_linkedin_username(url: str) -> str:
    """Extract username from LinkedIn URL."""
    if not url:
        return None
    # Handle formats: linkedin.com/in/username, /in/username, username
    import re
    match = re.search(r'linkedin\.com/in/([\w\-]+)', url)
    if match:
        return match.group(1)
    # If just a username was passed
    if "/" not in url and "." not in url:
        return url
    return None
