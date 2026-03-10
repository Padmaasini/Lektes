import json
from app.services.llm_service import get_scoring_response


async def generate_interview_questions(job, candidate) -> list:
    """
    Generate 5 tailored interview questions for a candidate.
    Each question includes:
    - Plain English context so non-technical HR understands WHY this is being asked
    - 3 likely answer variations (strong / acceptable / weak)
    - A follow-up if the answer is vague
    - Space for HR to record the actual answer
    """
    prompt = f"""
You are helping a non-technical HR professional interview a candidate for a technical role.

JOB TITLE: {job.title}
REQUIRED SKILLS: {job.required_skills}
JOB DESCRIPTION: {job.description[:800]}

CANDIDATE NAME: {candidate.full_name}
CANDIDATE SKILLS: {candidate.skills}
CANDIDATE EXPERIENCE: {candidate.experience_years} years
CANDIDATE SCORE: {candidate.match_score}%
CANDIDATE RED FLAGS: {candidate.red_flags or "None"}

Generate exactly 5 interview questions. Mix of:
- 2 technical questions about their claimed skills (but phrased so HR can follow the answer)
- 1 question probing a gap or red flag in their profile
- 1 situational/behavioural question relevant to the role
- 1 motivation/culture fit question

For each question provide:
- A plain English note to HR explaining WHY this question is being asked and what skill/concern it probes
- 3 likely answer variations a candidate might give: one strong, one acceptable, one weak
- Each variation should be a realistic 2-3 sentence answer a real person might say
- A follow-up question if the initial answer is vague

Return ONLY this JSON array, no markdown, no explanation:
[
    {{
        "number": 1,
        "category": "Technical / Behavioural / Motivation / Gap Probe",
        "question": "The question to ask the candidate",
        "why_we_ask": "Plain English: what skill or concern this probes, and what a good answer tells you",
        "likely_answers": [
            {{
                "quality": "Strong",
                "answer": "A realistic strong answer a good candidate might give",
                "what_it_signals": "One sentence on what this signals about the candidate"
            }},
            {{
                "quality": "Acceptable",
                "answer": "A realistic acceptable answer — shows basic competence but not depth",
                "what_it_signals": "One sentence on what this signals"
            }},
            {{
                "quality": "Weak",
                "answer": "A realistic weak or evasive answer — vague or showing a gap",
                "what_it_signals": "One sentence on what this signals"
            }}
        ],
        "follow_up": "A follow-up question to probe deeper if the answer is vague"
    }}
]
"""

    response = await get_scoring_response(prompt)

    # ── Robust JSON extraction ────────────────────────────────
    # LLMs often wrap the array in ```json ... ``` or add a preamble sentence.
    # We strip known wrappers first, then fall back to finding the [ ... ] array
    # directly in the response using a bracket-balance scan.
    import re
    clean = response.strip()
    clean = re.sub(r"^```(?:json)?", "", clean, flags=re.MULTILINE).strip()
    clean = re.sub(r"```$", "", clean, flags=re.MULTILINE).strip()

    # If it still doesn't start with '[', find the first '[' and last ']'
    if not clean.startswith("["):
        start = clean.find("[")
        end   = clean.rfind("]")
        if start != -1 and end != -1 and end > start:
            clean = clean[start:end + 1]

    try:
        questions = json.loads(clean)
        # Validate it's a non-empty list of dicts
        if isinstance(questions, list) and questions:
            return questions
        raise ValueError("Empty or invalid question list")
    except Exception as parse_err:
        print(f"  ✗ Question JSON parse failed: {parse_err}")
        print(f"  Raw response (first 300 chars): {response[:300]}")
        # Return a minimal fallback so the email still has something useful
        return _fallback_questions(job, candidate)


def _fallback_questions(job, candidate) -> list:
    """
    Returns 3 generic questions if the LLM response can't be parsed.
    Better to send something than an empty section.
    """
    name = candidate.full_name or "the candidate"
    return [
        {
            "number": 1,
            "category": "Technical",
            "question": f"Can you walk me through a project where you used SQL or Python to analyse data?",
            "why_we_ask": "Checks whether the candidate has hands-on experience with the core tools for this role.",
            "likely_answers": [
                {"quality": "Strong",     "answer": "Describes a specific project with concrete outcomes and tools used.", "what_it_signals": "Candidate has real hands-on experience."},
                {"quality": "Acceptable", "answer": "Mentions a project but is vague on the details or outcome.",          "what_it_signals": "Some experience, but may need guidance."},
                {"quality": "Weak",       "answer": "Can only describe coursework or has no concrete example.",            "what_it_signals": "Limited practical experience."},
            ],
            "follow_up": "What was the most challenging part of that analysis?"
        },
        {
            "number": 2,
            "category": "Behavioural",
            "question": "Tell me about a time you had to explain a data finding to someone non-technical. How did you approach it?",
            "why_we_ask": "Data analysts must communicate findings clearly to business stakeholders.",
            "likely_answers": [
                {"quality": "Strong",     "answer": "Describes using visuals, avoiding jargon, and checking for understanding.", "what_it_signals": "Strong communication and empathy skills."},
                {"quality": "Acceptable", "answer": "Simplified the language but didn't tailor it to the audience.", "what_it_signals": "Basic awareness, room to grow."},
                {"quality": "Weak",       "answer": "Can't recall a specific example or says they prefer technical audiences.", "what_it_signals": "May struggle in cross-functional roles."},
            ],
            "follow_up": "What feedback did you get from that person?"
        },
        {
            "number": 3,
            "category": "Motivation",
            "question": f"Why are you applying for a Junior Data Analyst role at this stage of your career?",
            "why_we_ask": "Helps assess whether the candidate's motivations align with the role's scope and seniority.",
            "likely_answers": [
                {"quality": "Strong",     "answer": "Clear reason tied to building a specific skill or transitioning into data.", "what_it_signals": "Intentional career move with realistic expectations."},
                {"quality": "Acceptable", "answer": "General interest in data but unclear on the specific role.", "what_it_signals": "Genuine interest but may need more direction."},
                {"quality": "Weak",       "answer": "Vague answer about 'wanting to try something new' with no specifics.", "what_it_signals": "Low commitment risk — may leave quickly."},
            ],
            "follow_up": "Where do you see yourself in 2 years from this role?"
        },
    ]
