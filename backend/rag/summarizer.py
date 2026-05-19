from config import settings

def summarize_document(text: str, filename: str) -> str:
    try:
        from groq import Groq
        client = Groq(api_key=settings.groq_api_key)
        truncated = text[:8000]
        prompt = (
            f"Summarize this document in 3-5 sentences covering main topic, "
            f"key findings, and conclusions.\n\nDocument: {filename}\n\nContent: {truncated}"
        )
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
        )
        return response.choices[0].message.content or ""
    except Exception as e:
        return f"Summary unavailable: {str(e)}"