import os
from dotenv import load_dotenv
from agents import Agent, Runner
from openai import AsyncOpenAI
from app.prompts import EDITORIAL_REPORT_PROMPT

load_dotenv()

client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

review_agent = Agent(
    name="Submission Compliance Reviewer",
    instructions=EDITORIAL_REPORT_PROMPT,
    model="gpt-4.1-mini",
)

async def generate_editorial_feedback(payload: dict) -> str:
    prompt = f"""
Validation payload:
{payload}

Write the editorial review report now.
"""
    result = await Runner.run(review_agent, prompt)
    return result.final_output