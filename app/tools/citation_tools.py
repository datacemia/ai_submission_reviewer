import re
from app.rules import TEMPLATES
from app.utils.text_utils import extract_section_content


def check_reference_count(text: str, template_key: str) -> dict:
    template = TEMPLATES[template_key]
    all_sections = template["required_sections"] + template.get("optional_sections", [])
    references_text = extract_section_content(text, "References", all_sections)

    if not references_text:
        return {"ok": False, "count": 0, "problems": ["References section is missing."]}

    lines = [line.strip() for line in references_text.split("\n") if line.strip()]
    count = len(lines)

    problems = []
    if count < template["min_references"]:
        problems.append(f"Only {count} references found; minimum is {template['min_references']}.")

    return {
        "ok": len(problems) == 0,
        "count": count,
        "problems": problems,
    }


def check_apa_intext_citations(text: str) -> dict:
    # More flexible APA-like detection:
    # catches examples such as:
    # (Smith, 2020)
    # (Smith et al., 2020)
    # (Scranton P, 2007)
    # (Behera SR, 2025)
    # (GE Aerospace, 2008; Menon J, 2025)

    patterns = [
        r"\([A-Z][A-Za-z\-]+(?: et al\.)?,\s*\d{4}(?:, p{1,2}\.?\s*\d+(?:[-–]\d+)?)?\)",
        r"\([A-Z][A-Za-z\-]+\s+[A-Z]{1,3},\s*\d{4}(?:, p{1,2}\.?\s*\d+(?:[-–]\d+)?)?\)",
        r"\([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)*,\s*\d{4}(?:; [^)]+)?\)",
        r"\([^)]+,\s*\d{4}(?:; [^)]+,\s*\d{4})+\)",
    ]

    matches = []
    for pattern in patterns:
        matches.extend(re.findall(pattern, text))

    # remove duplicates while preserving order
    unique_matches = list(dict.fromkeys(matches))

    return {
        "count": len(unique_matches),
        "examples": unique_matches[:5],
        "ok": len(unique_matches) > 0,
    }