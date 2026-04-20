import os
import uuid
import secrets
import tempfile
import traceback
from dotenv import load_dotenv

from fastapi import FastAPI, UploadFile, File, Request, Depends, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.models import ReviewIssue, ReviewReport, SectionCheck
from app.tools.extraction_tools import extract_text_from_file, extract_basic_metadata
from app.tools.structure_tools import (
    detect_template_type,
    check_required_sections,
    check_abstract_rules,
    check_keywords_rules,
)
from app.tools.citation_tools import check_reference_count, check_apa_intext_citations
from app.tools.compliance_tools import check_language_requirements, check_ethics_requirements
from app.tools.scoring_tools import compute_score
from app.agent import generate_editorial_feedback
from app.db import supabase

from openai import OpenAI

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = FastAPI(title="AI Submission Reviewer", version="0.2.0")

app.mount(
    "/static",
    StaticFiles(directory=os.path.join(BASE_DIR, "static")),
    name="static"
)

templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

security = HTTPBasic()

USERNAME = os.getenv("APP_USERNAME", "admin")
PASSWORD = os.getenv("APP_PASSWORD", "1234")

client = OpenAI()


def verify(credentials: HTTPBasicCredentials = Depends(security)) -> bool:
    correct_username = secrets.compare_digest(credentials.username, USERNAME)
    correct_password = secrets.compare_digest(credentials.password, PASSWORD)

    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=401,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Basic"},
        )

    return True


@app.get("/", response_class=HTMLResponse)
async def home(request: Request, auth: bool = Depends(verify)):
    return templates.TemplateResponse(request, "index.html")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/review-file", response_model=ReviewReport)
async def review_file(file: UploadFile = File(...)):
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in [".docx", ".pdf"]:
        return JSONResponse(
            status_code=400,
            content={"error": "Only .docx and .pdf are supported."}
        )

    file_bytes = await file.read()
    file_name = f"{uuid.uuid4()}{ext}"
    temp_path = None

    try:
        # Upload Supabase
        try:
            supabase.storage.from_("papers").upload(file_name, file_bytes)
            file_url = supabase.storage.from_("papers").get_public_url(file_name)
        except Exception as storage_error:
            raise RuntimeError(
                "Supabase Storage upload failed."
            ) from storage_error

        # Temp file
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            tmp.write(file_bytes)
            temp_path = tmp.name

        result = extract_text_from_file(temp_path)

        text = result.get("text") if isinstance(result, dict) else result
        text = str(text)

        if not text.strip():
            raise ValueError("No text extracted")

        metadata = extract_basic_metadata(text)

        template_key = detect_template_type(text)
        section_result = check_required_sections(text, template_key)
        abstract_result = check_abstract_rules(text, template_key)
        keywords_result = check_keywords_rules(text, template_key)
        references_result = check_reference_count(text, template_key)
        citation_result = check_apa_intext_citations(text)
        language_result = check_language_requirements(text)
        ethics_result = check_ethics_requirements(text)

        issues = []

        for m in section_result["missing"]:
            issues.append(
                ReviewIssue(
                    severity="critical",
                    category="structure",
                    message=f"Missing section: {m}"
                )
            )

        for p in abstract_result.get("problems", []):
            issues.append(
                ReviewIssue(
                    severity="warning",
                    category="abstract",
                    message=p
                )
            )

        for p in keywords_result.get("problems", []):
            issues.append(
                ReviewIssue(
                    severity="warning",
                    category="keywords",
                    message=p
                )
            )

        for p in references_result.get("problems", []):
            issues.append(
                ReviewIssue(
                    severity="critical",
                    category="references",
                    message=p
                )
            )

        if not citation_result["ok"]:
            issues.append(
                ReviewIssue(
                    severity="warning",
                    category="citations",
                    message="No APA citations"
                )
            )

        if not language_result["ok"]:
            issues.append(
                ReviewIssue(
                    severity="warning",
                    category="language",
                    message=language_result["message"]
                )
            )

        if not ethics_result["ok"]:
            issues.append(
                ReviewIssue(
                    severity="info",
                    category="ethics",
                    message="Check ethics manually"
                )
            )

        score = compute_score(issues)

        paper = supabase.table("papers").insert({
            "filename": file.filename,
            "file_url": file_url,
            "score": score,
            "template_type": template_key,
            "metadata": metadata,
        }).execute()

        paper_id = paper.data[0]["id"]

        suggestions = [
            "Fix missing sections",
            "Improve abstract",
            "Check references APA",
        ]

        # OpenAI safe
        try:
            editorial_feedback = await generate_editorial_feedback(
                text=text,
                template_type=template_key,
                issues=issues,
                metadata=metadata,
                score=score,
            )
        except Exception:
            editorial_feedback = "Editorial feedback unavailable."

        supabase.table("reviews").insert({
            "paper_id": paper_id,
            "issues": [i.model_dump() for i in issues],
            "suggestions": suggestions,
            "editorial_feedback": editorial_feedback,
        }).execute()

        return ReviewReport(
            filename=file.filename,
            template_type=template_key,
            score=score,
            issues=issues,
            section_check=SectionCheck(**section_result),
            metadata=metadata,
            suggestions=suggestions,
            raw_text_preview=text[:1500],
            editorial_feedback=editorial_feedback,
        )

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": str(e), "trace": traceback.format_exc()}
        )

    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


@app.get("/test-openai")
async def test_openai():
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Say OK if API works."}
            ]
        )
        return {"response": response.choices[0].message.content}
    except Exception as e:
        return {"error": str(e)}