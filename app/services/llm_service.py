from app.core.config import settings

async def get_llm_response(prompt: str, system_prompt: str = None) -> str:
    """
    Get a response from the LLM.
    Uses Groq (free tier) with Llama 3.1 as primary.
    Falls back gracefully if API key not configured.
    """
    if not settings.GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY not configured. Add it to your .env file.")

    try:
        from groq import Groq
        client = Groq(api_key=settings.GROQ_API_KEY)

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = client.chat.completions.create(
            model=settings.GROQ_MODEL,
            messages=messages,
            temperature=0.1,   # Low temp for consistent structured output
            max_tokens=2048
        )
        return response.choices[0].message.content

    except Exception as e:
        print(f"Groq API error: {e}")
        raise

async def get_scoring_response(prompt: str) -> str:
    """Dedicated call for scoring tasks — uses slightly higher token limit."""
    if not settings.GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY not configured.")

    from groq import Groq
    client = Groq(api_key=settings.GROQ_API_KEY)

    response = client.chat.completions.create(
        model=settings.GROQ_MODEL,
        messages=[
            {
                "role": "system",
                "content": """You are Lektes, an expert AI recruitment screening agent.
                You analyse CVs and job descriptions to produce accurate, fair, and justified 
                candidate rankings. Always be objective, specific, and provide clear reasoning.
                Return responses in valid JSON format only."""
            },
            {"role": "user", "content": prompt}
        ],
        temperature=0.1,
        max_tokens=4096
    )
    return response.choices[0].message.content
