import google.generativeai as genai
from app.core.config import settings

def configure_gemini():
    """Configure Gemini with API key."""
    if not settings.GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY not configured. Add it to your .env file.")
    genai.configure(api_key=settings.GEMINI_API_KEY)

async def get_llm_response(prompt: str, system_prompt: str = None) -> str:
    """
    Get a response from Gemini 1.5 Flash (Free tier).
    15 requests/min, 1M tokens/day — more than enough for MVP.
    """
    configure_gemini()

    model = genai.GenerativeModel(
        model_name=settings.GEMINI_MODEL,
        system_instruction=system_prompt if system_prompt else
            "You are TalentMesh, an expert AI recruitment screening agent. Always return valid JSON when asked."
    )

    response = model.generate_content(
        prompt,
        generation_config=genai.GenerationConfig(
            temperature=0.1,
            max_output_tokens=2048,
        )
    )
    return response.text

async def get_scoring_response(prompt: str) -> str:
    """
    Dedicated call for scoring and ranking tasks.
    Uses higher token limit for detailed justifications.
    """
    configure_gemini()

    model = genai.GenerativeModel(
        model_name=settings.GEMINI_MODEL,
        system_instruction="""You are TalentMesh, an expert AI recruitment screening agent.
        You analyse CVs and job descriptions to produce accurate, fair, and justified 
        candidate rankings. Always be objective, specific, and provide clear reasoning.
        Return responses in valid JSON format only. No markdown, no backticks, just JSON."""
    )

    response = model.generate_content(
        prompt,
        generation_config=genai.GenerationConfig(
            temperature=0.1,
            max_output_tokens=4096,
        )
    )
    return response.text
