import os
import uuid
import secrets
import tempfile
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
# from app.agent import generate_editorial_feedback
from app.db import supabase

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = FastAPI(title="AI Submission Reviewer", version="0.2.0")

app.mount(
    "/static",
    StaticFiles(directory=os.path.join(BASE_DIR, "static")),
    name="static"
)

templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# 🔐 Auth
security = HTTPBasic()
USERNAME = os.getenv("APP_USERNAME", "admin")
PASSWORD = os.getenv("APP_PASSWORD", "1234")


def verify(credentials: HTTPBasicCredentials = Depends(security)) -> bool:
    if not (
        secrets.compare_digest(credentials.username, USERNAME)
        and secrets.compare_digest(credentials.password, PASSWORD)
    ):
        raise HTTPException(status_code=401, detail="Unauthorized")
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
        # 📦 Upload Supabase
        supabase.storage.from_("papers").upload(file_name, file_bytes)
        file_url = supabase.storage.from_("papers").get_public_url(file_name)

        # 📄 Temp file
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            tmp.write(file_bytes)
            temp_path = tmp.name

        # 🔍 Extract text
        result = extract_text_from_file(temp_path)

        # ✅ FIX CRITIQUE
        if isinstance(result, dict):
            text = result.get("text") or result.get("content") or str(result)
        else:
            text = result

        if not isinstance(text, str):
            text = str(text)

        if not text.strip():
            raise ValueError("No text extracted from document")

        # 🧠 Metadata + analysis
        metadata = extract_basic_metadata(text)
        template_key = detect_template_type(text)

        section_result = check_required_sections(text, template_key)
        abstract_result = check_abstract_rules(text, template_key)
        keywords_result = check_keywords_rules(text, template_key)
        references_result = check_reference_count(text, template_key)
        citation_result = check_apa_intext_citations(text)
        language_result = check_language_requirements(text)
        ethics_result = check_ethics_requirements(text)

        issues: list[ReviewIssue] = []

        # 🚨 Issues detection
        for missing in section_result["missing"]:
            issues.append(ReviewIssue(
                severity="critical",
                category="structure",
                message=f"Missing required section: {missing}"
            ))

        for p in abstract_result.get("problems", []):
            issues.append(ReviewIssue("warning", "abstract", p))

        keywords_present = "Keywords" in section_result.get("present", [])

        for p in keywords_result.get("problems", []):
            if keywords_present and p.lower().strip() == "keywords section is missing.":
                continue
            issues.append(ReviewIssue("warning", "keywords", p))

        for p in references_result.get("problems", []):
            issues.append(ReviewIssue("critical", "references", p))

        if not citation_result["ok"]:
            issues.append(ReviewIssue("warning", "citations", "No APA-like in-text citations detected."))

        if not language_result["ok"]:
            issues.append(ReviewIssue("warning", "language", language_result["message"]))

        if not ethics_result["ok"]:
            issues.append(ReviewIssue("info", "ethics", "Ethics/originality statements may require manual verification."))

        score = compute_score(issues)

        # 💾 Save paper
        paper = supabase.table("papers").insert({
            "filename": file.filename,
            "file_url": file_url,
            "score": score,
            "template_type": template_key,
            "metadata": metadata,
        }).execute()

        paper_id = paper.data[0]["id"]

        suggestions = [
            "Add all missing required sections.",
            "Ensure the abstract length and structure follow the selected template.",
            "Verify that references follow APA 7th edition.",
            "Check that in-text citations are consistent with the reference list.",
        ]

        # 💾 Save review
        supabase.table("reviews").insert({
            "paper_id": paper_id,
            "issues": [i.model_dump() for i in issues],
            "suggestions": suggestions,
            "editorial_feedback": "Editorial feedback temporarily disabled."
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
            editorial_feedback="Editorial feedback temporarily disabled."
        )

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )

    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)