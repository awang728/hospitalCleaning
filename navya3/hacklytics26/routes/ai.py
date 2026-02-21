from fastapi import APIRouter
import os
import requests
from datetime import datetime

router = APIRouter(prefix="/ai", tags=["ai"])

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")  # set this in .env or environment

@router.post("/summary")
async def generate_session_summary(data: dict):
    """
    Generate a natural language summary using Gemini
    Expects: {"coverage_percent": 85.5, "duration": 120, "stress_level": 0.65, ...}
    """
    if not GEMINI_API_KEY:
        return {"error": "Gemini API key not configured"}

    prompt = f"""
    You are a hospital hygiene compliance assistant.
    Analyze this cleaning session data and provide a concise, professional summary:
    - Room: {data.get('room_id', 'unknown')}
    - Coverage: {data.get('coverage_percent', 'N/A')}%
    - Duration: {data.get('duration', 'N/A')} seconds
    - Stress level: {data.get('stress_level', 'N/A')}
    - Engagement: {data.get('engagement_level', 'N/A')}

    Highlight any risks (low coverage, high stress) and suggest one improvement.
    Keep response under 100 words.
    """

    try:
        response = requests.post(
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key=" + GEMINI_API_KEY,
            json={
                "contents": [{
                    "parts": [{"text": prompt}]
                }]
            }
        )
        response.raise_for_status()
        result = response.json()
        text = result["candidates"][0]["content"]["parts"][0]["text"]
        return {"summary": text.strip()}
    except Exception as e:
        return {"error": f"Failed to generate summary: {str(e)}"}