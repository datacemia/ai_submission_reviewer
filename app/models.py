from pydantic import BaseModel, Field
from typing import List, Dict, Optional


class ReviewIssue(BaseModel):
    severity: str
    category: str
    message: str


class SectionCheck(BaseModel):
    present: List[str]
    missing: List[str]
    unexpected: List[str]


class ReviewReport(BaseModel):
    filename: Optional[str] = None
    template_type: str
    score: int
    issues: List[ReviewIssue]
    section_check: SectionCheck
    metadata: Dict[str, str | int | float | bool | None]
    suggestions: List[str]
    raw_text_preview: str
    editorial_feedback: Optional[str] = None