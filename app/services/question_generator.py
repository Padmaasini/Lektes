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
    clean = response.strip().replace("```json", "").replace("```", "").strip()
    return json.loads(clean)
