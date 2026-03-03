import asyncio
from app.core.config import settings


def _call_groq_sync(prompt, system_prompt, max_tokens):
    from groq import Groq
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


async def get_llm_response(prompt, system_prompt=None):
    sp = system_prompt or "You are TalentMesh, an AI recruitment assistant. Return valid JSON when asked. No markdown."
    return await asyncio.wait_for(asyncio.to_thread(_call_groq_sync, prompt, sp, 2048), timeout=30.0)


async def get_scoring_response(prompt):
    sp = "You are TalentMesh, an expert AI recruitment screening agent. Return valid JSON only."
    return await asyncio.wait_for(asyncio.to_thread(_call_groq_sync, prompt, sp, 1024), timeout=30.0)
