import asyncio
from app.core.config import settings

def _call_groq_sync(prompt: str, system_prompt: str, max_tokens: int) -> str:
    """Synchronous Groq call — imported lazily to avoid startup crash."""
    try:
        from groq import Groq
    except ImportError:
        raise RuntimeError("groq package not installed. Run: pip install groq")

    client = Groq(api_key=settings.GROQ_API_KEY)
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        temperature=0.1,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content

async def get_llm_response(prompt: str, system_prompt: str = None) -> str:
    sp = system_prompt or "You are TalentMesh, an AI recruitment assistant. Return valid JSON when asked. No markdown, no backticks."
    return await asyncio.wait_for(
        asyncio.to_thread(_call_groq_sync, prompt, sp, 2048),
        timeout=30.0
    )

async def get_scoring_response(prompt: str) -> str:
    sp = """You are TalentMesh, an expert AI recruitment screening agent.
Analyse CVs and job descriptions to produce accurate, fair, justified candidate rankings.
Always be objective and specific. Return valid JSON only — no markdown, no backticks, just raw JSON."""
    return await asyncio.wait_for(
        asyncio.to_thread(_call_groq_sync, prompt, sp, 1024),
        timeout=30.0
    )
