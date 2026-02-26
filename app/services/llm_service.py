import asyncio
import google.generativeai as genai
from app.core.config import settings

def configure_gemini():
    if not settings.GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY not set.")
    genai.configure(api_key=settings.GEMINI_API_KEY)

def _call_gemini_sync(prompt: str, system_prompt: str, max_tokens: int) -> str:
    """Synchronous Gemini call — run this in a thread via asyncio.to_thread()."""
    configure_gemini()
    model = genai.GenerativeModel(
        model_name=settings.GEMINI_MODEL,
        system_instruction=system_prompt
    )
    response = model.generate_content(
        prompt,
        generation_config=genai.GenerationConfig(
            temperature=0.1,
            max_output_tokens=max_tokens,
        )
    )
    return response.text

async def get_llm_response(prompt: str, system_prompt: str = None) -> str:
    """
    Non-blocking Gemini call for CV parsing and general use.
    Runs in a thread so FastAPI's event loop stays free.
    """
    sp = system_prompt or "You are TalentMesh, an AI recruitment assistant. Return valid JSON when asked."
    return await asyncio.wait_for(
        asyncio.to_thread(_call_gemini_sync, prompt, sp, 2048),
        timeout=25.0
    )

async def get_scoring_response(prompt: str) -> str:
    """
    Non-blocking Gemini call for candidate scoring.
    Runs in a thread so FastAPI's event loop stays free.
    """
    sp = """You are TalentMesh, an expert AI recruitment screening agent.
Analyse CVs and job descriptions to produce accurate, fair, justified candidate rankings.
Always be objective and specific. Return valid JSON only — no markdown, no backticks."""
    return await asyncio.wait_for(
        asyncio.to_thread(_call_gemini_sync, prompt, sp, 1024),
        timeout=25.0
    )
