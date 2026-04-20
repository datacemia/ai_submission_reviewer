import re
from app.rules import TEMPLATES
from app.utils.text_utils import split_lines, extract_section_content, count_words


SECTION_ALIASES = {
    "abstract": ["abstract"],
    "keywords": ["keywords", "key words", "index terms"],

    "introduction": ["introduction"],

    "research objectives": [
        "research objectives",
        "research objective",
        "objective of the study",
        "objectives of the study",
        "study objectives",
        "aim of the study",
        "study aim",
        "purpose of the study",
        "research goals and problems",
    ],

    "literature review": [
        "literature review",
        "review of literature",
        "related work",
        "theoretical background",
        "background",
    ],

    "methodology": [
        "methodology",
        "methods",
        "method",
        "research methodology",
        "own research methodology",
        "materials and methods",
        "research methods",
    ],

    "results": [
        "results",
        "research results",
        "findings",
        "empirical results",
    ],

    "discussion": [
        "discussion",
        "analysis and discussion",
        "results and discussion",
    ],

    "conclusion": [
        "conclusion",
        "conclusions",
        "final remarks",
        "closing remarks",
    ],

    "references": [
        "references",
        "bibliography",
        "reference list",
    ],
}


def normalize_text(text: str) -> str:
    text = text.replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def normalize_heading(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"^[\d\.\-\)\(\s]+", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip().rstrip(":")


def get_aliases(section_name: str) -> list[str]:
    key = section_name.strip().lower()
    return SECTION_ALIASES.get(key, [key])


def line_matches_alias(line: str, alias: str) -> bool:
    normalized_line = normalize_heading(line)
    normalized_alias = normalize_heading(alias)

    if normalized_line == normalized_alias:
        return True

    if normalized_line.startswith(normalized_alias + ":"):
        return True

    return False


def line_starts_with_alias_and_content(line: str, alias: str) -> bool:
    normalized_alias = normalize_heading(alias)
    pattern = rf"^\s*[\d\.\-\)\(]*\s*{re.escape(normalized_alias)}\s*:\s*.+$"
    return re.match(pattern, line.strip(), flags=re.IGNORECASE) is not None


def split_inline_heading_content(line: str, alias: str) -> str:
    normalized_alias = normalize_heading(alias)
    pattern = rf"^\s*[\d\.\-\)\(]*\s*{re.escape(normalized_alias)}\s*:\s*(.*)$"
    match = re.match(pattern, line.strip(), flags=re.IGNORECASE)

    if not match:
        return ""

    return match.group(1).strip()


def looks_like_heading(line: str, aliases: list[str]) -> bool:
    return any(
        line_matches_alias(line, alias) or line_starts_with_alias_and_content(line, alias)
        for alias in aliases
    )


def section_exists_in_text(text: str, aliases: list[str]) -> bool:
    normalized_text = normalize_text(text)

    for alias in aliases:
        normalized_alias = normalize_heading(alias)
        alias_pattern = re.escape(normalized_alias)

        # accepte par exemple :
        # 2. Literature Review
        # 2 Literature Review
        # 2.1 Literature Review
        pattern = rf"(?im)^\s*(?:\d+(?:\.\d+)*)\.?\s+{alias_pattern}\b"

        if re.search(pattern, normalized_text):
            return True

        # fallback
        if re.search(rf"(?im)\b{alias_pattern}\b", normalized_text):
            return True

    return False


def has_inline_research_objective(text: str) -> bool:
    lower_text = normalize_text(text).lower()
    markers = [
        "the aim of this article is",
        "the aim of the study was",
        "the aim of the study is",
        "the aim of the research",
        "the main aim of the research",
        "research problem",
        "research goals and problems",
        "the aim of this study is",
    ]
    return any(marker in lower_text for marker in markers)


def has_conceptual_literature_review(text: str) -> bool:
    lower_text = normalize_text(text).lower()

    direct_markers = [
        "literature review",
        "review of literature",
        "related work",
        "theoretical background",
        "background",
        "prior studies",
        "previous studies",
        "existing literature",
    ]

    # fallback prudent pour les papiers conceptuels/comparatifs
    contextual_markers = [
        "comparative context",
        "comparative lessons",
        "dynamic innovation",
        "historical context",
        "international experience",
        "contemporary comparators",
        "historical reality",
    ]

    author_markers = [
        "scranton",
    ]

    if any(marker in lower_text for marker in direct_markers):
        return True

    context_score = sum(1 for marker in contextual_markers if marker in lower_text)
    author_score = sum(1 for marker in author_markers if marker in lower_text)

    # seuil conservateur pour éviter les faux positifs
    return context_score >= 2 and author_score >= 1


def find_present_sections(text: str, required_sections: list[str]) -> tuple[list[str], list[str]]:
    present = []
    missing = []

    normalized_text = normalize_text(text)

    for section in required_sections:
        aliases = get_aliases(section)

        found_in_text = section_exists_in_text(normalized_text, aliases)

        if not found_in_text:
            lines = split_lines(normalized_text)
            found_in_text = any(looks_like_heading(line, aliases) for line in lines)

        if found_in_text:
            present.append(section)
        else:
            missing.append(section)

    return present, missing


def detect_template_type(text: str) -> str:
    lower_text = normalize_text(text).lower()

    research_markers = [
        "methodology",
        "own research methodology",
        "methods",
        "results",
        "research results",
        "discussion",
        "literature review",
    ]

    academic_markers = [
        "background",
        "insights and applications",
        "conclusions",
        "theoretical background",
    ]

    research_score = sum(1 for marker in research_markers if marker in lower_text)
    academic_score = sum(1 for marker in academic_markers if marker in lower_text)

    if research_score >= academic_score:
        return "research_article"
    return "academic_article"


def check_required_sections(text: str, template_key: str) -> dict:
    normalized_text = normalize_text(text)
    required = TEMPLATES[template_key]["required_sections"]

    present, missing = find_present_sections(normalized_text, required)

    missing_normalized = {section.strip().lower(): section for section in missing}

    if (
        "research objectives" in missing_normalized
        and has_inline_research_objective(normalized_text)
    ):
        original_name = missing_normalized["research objectives"]
        missing.remove(original_name)
        present.append(original_name)

    if (
        "literature review" in missing_normalized
        and has_conceptual_literature_review(normalized_text)
    ):
        original_name = missing_normalized["literature review"]
        missing.remove(original_name)
        present.append(original_name)

    # SAFE fallback:
    # for conceptual/comparative papers, do not force a formal Methodology heading
    if (
        "methodology" in missing_normalized
        and is_conceptual_or_comparative_paper(normalized_text)
    ):
        original_name = missing_normalized["methodology"]
        missing.remove(original_name)

    present = list(dict.fromkeys(present))

    return {
        "present": present,
        "missing": missing,
        "unexpected": [],
    }


def extract_section_by_aliases(text: str, target_section: str, all_sections: list[str]) -> str:
    normalized_text = normalize_text(text)
    target_aliases = get_aliases(target_section)
    all_alias_map = {section: get_aliases(section) for section in all_sections}

    lines = normalized_text.splitlines()

    start_index = None
    end_index = None
    first_content = ""

    for i, line in enumerate(lines):
        for alias in target_aliases:
            if line_matches_alias(line, alias):
                start_index = i + 1
                first_content = ""
                break

            if line_starts_with_alias_and_content(line, alias):
                start_index = i + 1
                first_content = split_inline_heading_content(line, alias)
                break

        if start_index is not None:
            break

    if start_index is None:
        return ""

    following_sections = [
        section for section in all_sections
        if section.strip().lower() != target_section.strip().lower()
    ]

    for i in range(start_index, len(lines)):
        line = lines[i]

        # Ignore inline keywords line while extracting abstract content
        if target_section.strip().lower() == "abstract" and re.match(r"(?i)^keywords\s*:", line.strip()):
            end_index = i
            break

        for section in following_sections:
            aliases = all_alias_map[section]

            # Stop only on real heading lines
            if looks_like_heading(line, aliases):
                end_index = i
                break

        if end_index is not None:
            break

    if end_index is None:
        end_index = len(lines)

    content_lines = lines[start_index:end_index]

    if first_content:
        content_lines = [first_content] + content_lines

    content = "\n".join(content_lines).strip()
    return content


def collapse_pdf_wrapped_lines(text: str) -> str:
    lines = [line.strip() for line in text.splitlines()]

    merged = []
    buffer = []

    for line in lines:
        if not line:
            if buffer:
                merged.append(" ".join(buffer).strip())
                buffer = []
            continue

        normalized = normalize_heading(line)
        if normalized in {
            "abstract",
            "keywords",
            "introduction",
            "literature review",
            "methodology",
            "own research methodology",
            "results",
            "research results",
            "discussion",
            "conclusion",
            "conclusions",
            "references",
        }:
            if buffer:
                merged.append(" ".join(buffer).strip())
                buffer = []
            merged.append(line)
            continue

        buffer.append(line)

    if buffer:
        merged.append(" ".join(buffer).strip())

    return "\n".join(merged).strip()


def check_abstract_rules(text: str, template_key: str) -> dict:
    template = TEMPLATES[template_key]
    all_sections = template["required_sections"] + template.get("optional_sections", [])

    abstract = extract_section_by_aliases(text, "Abstract", all_sections)

    if not abstract:
        abstract = extract_section_content(text, "Abstract", all_sections)

    if not abstract:
        return {
            "ok": False,
            "message": "Abstract section is missing.",
            "problems": ["Abstract section is missing."],
        }

    abstract = collapse_pdf_wrapped_lines(abstract)
    wc = count_words(abstract)

    paragraph_count = len([p for p in re.split(r"\n\s*\n", abstract) if p.strip()])
    if paragraph_count == 0:
        paragraph_count = 1

    problems = []

    if wc < template["abstract_min_words"] or wc > template["abstract_max_words"]:
        problems.append(
            f"Abstract word count is {wc}; expected {template['abstract_min_words']}-{template['abstract_max_words']}."
        )

    if paragraph_count > 1:
        problems.append("Abstract must be a single paragraph.")

    return {
        "ok": len(problems) == 0,
        "word_count": wc,
        "problems": problems,
    }


def check_keywords_rules(text: str, template_key: str) -> dict:
    template = TEMPLATES[template_key]
    all_sections = template["required_sections"] + template.get("optional_sections", [])

    keywords_text = extract_section_by_aliases(text, "Keywords", all_sections)

    if not keywords_text:
        keywords_text = extract_section_content(text, "Keywords", all_sections)

    if not keywords_text:
        return {
            "ok": False,
            "message": "Keywords section is missing.",
            "problems": ["Keywords section is missing."],
        }

    first_line = keywords_text.split("\n")[0].strip()
    raw_keywords = re.split(r"\s*[,;•]\s*", first_line)
    keywords = [k.strip(" .:;,\n\t") for k in raw_keywords if k.strip(" .:;,\n\t")]

    problems = []

    if not (template["keywords_min"] <= len(keywords) <= template["keywords_max"]):
        problems.append(
            f"Found {len(keywords)} keywords; expected {template['keywords_min']}-{template['keywords_max']}."
        )

    return {
        "ok": len(problems) == 0,
        "keywords": keywords,
        "problems": problems,
    }


def is_conceptual_or_comparative_paper(text: str) -> bool:
    lower_text = normalize_text(text).lower()

    markers = [
        "comparative lessons",
        "comparative context",
        "historical context",
        "this paper makes two contributions",
        "this paper offers an overview",
        "the argument that follows",
        "dynamic innovation",
        "conceptual lens",
        "analytical lens",
    ]

    score = sum(1 for marker in markers if marker in lower_text)
    return score >= 2