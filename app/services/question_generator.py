import json
from app.services.llm_service import get_scoring_response

async def generate_technical_questions(job, candidate) -> list:
    """
    Generate 2-3 tailored technical screening questions for a candidate.
    Each question includes an answer blueprint so HR knows what to listen for.
    """
    prompt = f"""
    Generate exactly 3 technical screening questions for this candidate interview.
    
    JOB TITLE: {job.title}
    JOB DESCRIPTION: {job.description[:1000]}
    REQUIRED SKILLS: {job.required_skills}
    
    CANDIDATE PROFILE:
    Name: {candidate.full_name}
    Skills: {candidate.skills}
    Experience: {candidate.experience_years} years
    Match Score: {candidate.match_score}%
    
    Rules:
    - Questions should probe the candidate's specific experience
    - Target any gaps between their CV and the job requirements
    - Questions should be open-ended, not yes/no
    - Provide a clear answer blueprint for each question
    
    Return ONLY this JSON array:
    [
        {{
            "question_number": 1,
            "question": "The interview question here",
            "what_to_listen_for": "Key concepts and points a good answer must cover",
            "weak_answer_looks_like": "What a poor or vague answer sounds like",
            "strong_answer_looks_like": "What an excellent answer includes",
            "follow_up": "A follow-up question if the initial answer is vague"
        }}
    ]
    
    Return ONLY the JSON array. No explanation.
    """

    response = await get_scoring_response(prompt)
    clean = response.strip().replace("```json", "").replace("```", "").strip()
    return json.loads(clean)
