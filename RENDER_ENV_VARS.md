# Render Environment Variables

Add these in Render → Environment → Edit Variables

## Required
| Key | Value |
|-----|-------|
| `GROQ_API_KEY` | From console.groq.com |
| `GMAIL_USER` | yourname@gmail.com |
| `GMAIL_APP_PASSWORD` | 16-char app password (no spaces) |

## Optional — improves profile verification
| Key | Value | Effect |
|-----|-------|--------|
| `GITHUB_TOKEN` | From github.com/settings/tokens | Raises rate limit 60→5000/hr |
| `KAGGLE_USERNAME` | Your Kaggle username | Enables Kaggle tier verification |
| `KAGGLE_KEY` | From kaggle.com → Settings → API | Required with KAGGLE_USERNAME |

## Getting a Gmail App Password
1. myaccount.google.com → Security
2. Enable 2-Step Verification
3. Search "App Passwords" → Create → name it TalentMesh
4. Copy 16-char code, remove spaces before pasting into Render

## Getting a Kaggle API Key
1. kaggle.com → Profile → Settings → API
2. Click "Create New Token" → downloads kaggle.json
3. Copy username and key values into Render

## Profile Verification Bonus Points
| Platform     | Condition              | Bonus |
|--------------|------------------------|-------|
| LinkedIn     | Profile URL verified   | +3    |
| GitHub       | 5+ public repos        | +4–6  |
| Kaggle       | Expert/Master/GM tier  | +2–5  |
| StackOverflow| 500+ reputation        | +1–5  |
| **Max total**|                        | **+10** |
