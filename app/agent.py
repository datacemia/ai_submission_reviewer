import os
from dotenv import load_dotenv
from agents import Agent, Runner, set_default_openai_client
from openai import AsyncOpenAI
from app.prompts import EDITORIAL_REPORT_PROMPT

load_dotenv()

client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
set_default_openai_client(client)

review_agent = Agent(
    name="Submission Compliance Reviewer",
    instructions=EDITORIAL_REPORT_PROMPT,
    model="gpt-4.1-mini",
)

async def generate_editorial_feedback(
    text: str,
    template_type: str,
    issues: list,
    metadata: dict,
    score: float | int,
) -> str:

    issue_lines = []
    for issue in issues:
        severity = getattr(issue, "severity", "unknown")
        category = getattr(issue, "category", "general")
        message = getattr(issue, "message", str(issue))
        issue_lines.append(f"- [{severity}] {category}: {message}")

    issues_block = "\n".join(issue_lines) if issue_lines else "No issues."

    prompt = f"""
Template: {template_type}
Score: {score}
Metadata: {metadata}

Issues:
{issues_block}

Text preview:
{text[:4000]}

Write a concise editorial review report.
"""

    result = await Runner.run(review_agent, prompt)

    return result.final_output