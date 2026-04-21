import os
import uuid
import secrets
import tempfile
import traceback
from dotenv import load_dotenv
import hashlib

from fastapi import FastAPI, UploadFile, File, Request, Depends, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from collections import defaultdict

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

        keywords_present = "Keywords" in section_result.get("present", [])

        for p in keywords_result.get("problems", []):
            normalized_problem = p.strip().lower()

            if keywords_present and normalized_problem == "keywords section is missing.":
                continue

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

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    auth: bool = Depends(verify),
):
    try:
        search = (request.query_params.get("search") or "").strip()
        template_filter = (request.query_params.get("template") or "").strip()
        min_score_raw = (request.query_params.get("min_score") or "").strip()
        sort_by = (request.query_params.get("sort") or "newest").strip()

        try:
            min_score = int(min_score_raw) if min_score_raw else None
        except ValueError:
            min_score = None

        papers_response = (
            supabase.table("papers")
            .select("*")
            .execute()
        )

        reviews_response = (
            supabase.table("reviews")
            .select("*")
            .execute()
        )

        papers = papers_response.data or []
        reviews = reviews_response.data or []

        reviews_by_paper_id = defaultdict(list)
        for review in reviews:
            paper_id = review.get("paper_id")
            if paper_id is not None:
                reviews_by_paper_id[paper_id].append(review)

        rows = []
        for paper in papers:
            paper_id = paper.get("id")
            linked_reviews = reviews_by_paper_id.get(paper_id, [])
            latest_review = linked_reviews[0] if linked_reviews else None

            filename = str(paper.get("filename") or "")
            template_type = str(paper.get("template_type") or "")
            score = paper.get("score")

            if search and search.lower() not in filename.lower():
                continue

            if template_filter and template_type != template_filter:
                continue

            if min_score is not None:
                try:
                    if score is None or float(score) < min_score:
                        continue
                except (TypeError, ValueError):
                    continue

            issue_count = len(latest_review.get("issues", [])) if latest_review else 0

            rows.append({
                "paper": paper,
                "latest_review": latest_review,
                "reviews_count": len(linked_reviews),
                "issue_count": issue_count,
            })

        if sort_by == "score_desc":
            rows.sort(key=lambda x: x["paper"].get("score") if x["paper"].get("score") is not None else -1, reverse=True)
        elif sort_by == "score_asc":
            rows.sort(key=lambda x: x["paper"].get("score") if x["paper"].get("score") is not None else 9999)
        elif sort_by == "filename_asc":
            rows.sort(key=lambda x: (x["paper"].get("filename") or "").lower())
        elif sort_by == "filename_desc":
            rows.sort(key=lambda x: (x["paper"].get("filename") or "").lower(), reverse=True)
        else:
            rows.sort(key=lambda x: str(x["paper"].get("id") or ""), reverse=True)

        scores = []
        for row in rows:
            value = row["paper"].get("score")
            try:
                if value is not None:
                    scores.append(float(value))
            except (TypeError, ValueError):
                pass

        templates_available = sorted(
            {
                str(p.get("template_type"))
                for p in papers
                if p.get("template_type")
            }
        )

        stats = {
            "total_papers": len(rows),
            "total_reviews": sum(row["reviews_count"] for row in rows),
            "avg_score": round(sum(scores) / len(scores), 1) if scores else "N/A",
            "high_score_count": sum(1 for s in scores if s >= 90),
        }

        return templates.TemplateResponse(
            request,
            "dashboard.html",
            {
                "rows": rows,
                "stats": stats,
                "filters": {
                    "search": search,
                    "template": template_filter,
                    "min_score": min_score_raw,
                    "sort": sort_by,
                },
                "templates_available": templates_available,
            },
        )

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "error": f"Dashboard error: {str(e)}",
                "trace": traceback.format_exc(),
            },
        )
@app.post("/review-file", response_model=ReviewReport)
async def review_file(file: UploadFile = File(...)):
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in [".docx", ".pdf"]:
        return JSONResponse(
            status_code=400,
            content={"error": "Only .docx and .pdf are supported."}
        )

    file_bytes = await file.read()
    file_hash = hashlib.md5(file_bytes).hexdigest()

    temp_path = None

    try:
        # CHECK DUPLICATE (HASH)
        existing = (
            supabase.table("papers")
            .select("*")
            .eq("file_hash", file_hash)
            .execute()
        )

        if existing.data:
            paper = existing.data[0]
            paper_id = paper["id"]
            file_url = paper.get("file_url")
        else:
            file_name = f"{uuid.uuid4()}{ext}"

            supabase.storage.from_("papers").upload(file_name, file_bytes)
            file_url = supabase.storage.from_("papers").get_public_url(file_name)

            paper_insert = supabase.table("papers").insert({
                "filename": file.filename,
                "file_url": file_url,
                "file_hash": file_hash,
            }).execute()

            paper_id = paper_insert.data[0]["id"]

        # TEMP FILE
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            tmp.write(file_bytes)
            temp_path = tmp.name

        result = extract_text_from_file(temp_path)
        text = result.get("text") if isinstance(result, dict) else result
        text = str(text)

        if not text.strip():
            raise ValueError("No text extracted from document")

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

        for m in section_result.get("missing", []):
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

        keywords_present = "Keywords" in section_result.get("present", [])

        for p in keywords_result.get("problems", []):
            if keywords_present and p.lower().strip() == "keywords section is missing.":
                continue

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

        suggestions = []
        if section_result.get("missing"):
            suggestions.append("Fix missing sections")
        if abstract_result.get("problems"):
            suggestions.append("Improve abstract")
        if references_result.get("problems"):
            suggestions.append("Check references APA")
        if not citation_result["ok"]:
            suggestions.append("Check in-text citations consistency")
        if not suggestions:
            suggestions.append("Submission is structurally strong. Proceed with editorial review.")

        # UPDATE PAPER (no duplicate)
        supabase.table("papers").update({
            "score": score,
            "template_type": template_key,
            "metadata": metadata,
        }).eq("id", paper_id).execute()

        # OpenAI
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

        # INSERT REVIEW
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
            content={
                "error": str(e),
                "trace": traceback.format_exc(),
            }
        )

    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)

@app.post("/papers/{paper_id}/status")
async def update_paper_status(
    paper_id: str,
    request: Request,
    auth: bool = Depends(verify),
):
    try:
        form = await request.form()
        new_status = str(form.get("editorial_status", "")).strip().lower()

        allowed_statuses = {"submitted", "revise", "accepted", "rejected"}
        if new_status not in allowed_statuses:
            return JSONResponse(
                status_code=400,
                content={"error": "Invalid editorial status."}
            )

        supabase.table("papers").update({
            "editorial_status": new_status
        }).eq("id", paper_id).execute()

        return RedirectResponse(url="/dashboard", status_code=303)

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "error": f"Status update error: {str(e)}",
                "trace": traceback.format_exc(),
            },
        )