import requests
import os

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

def generate_summary(cleaning_data):
    prompt = f"""
    Analyze this hospital cleaning session:
    Coverage: {cleaning_data['coverage_percent']}%
    Duration: {cleaning_data['duration']} minutes
    Stress Level: {cleaning_data['stress_level']}

    Provide a concise professional summary.
    """

    response = requests.post(
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent",
        params={"key": GEMINI_API_KEY},
        json={"contents":[{"parts":[{"text": prompt}]}]}
    )

    return response.json()