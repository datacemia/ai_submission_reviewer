import re
from typing import List


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def count_words(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text))


def split_lines(text: str) -> List[str]:
    text = text.replace("\r", "\n")
    raw_lines = text.split("\n")

    lines: List[str] = []

    for line in raw_lines:
        line = re.sub(r"\s+", " ", line).strip()
        if not line:
            continue

        # découpe possible titre numéroté + contenu collé
        match = re.match(r"^((?:\d+(?:\.\d+)*)\.?\s+[A-Z][A-Za-z0-9 \-\(\)&/]+?)(?:\s{2,}|$)(.*)$", line)
        if match:
            title = match.group(1).strip()
            rest = match.group(2).strip()

            lines.append(title)
            if rest:
                lines.append(rest)
            continue

        lines.append(line)

    return lines


def extract_section_content(text: str, section_name: str, all_sections: list[str]) -> str:
    text = normalize_text(text)

    numbering = r"(?:\d+(?:\.\d+)*)\.?\s*"

    pattern = rf"(?ims)^\s*(?:{numbering})?{re.escape(section_name)}\s*:?\s*$"
    match = re.search(pattern, text)

    if not match:
        return ""

    start = match.end()

    remaining_sections = [
        s for s in all_sections
        if s.lower() != section_name.lower()
    ]

    if not remaining_sections:
        return text[start:].strip()

    next_pattern = rf"(?ims)^\s*(?:{numbering})?(?:{'|'.join(map(re.escape, remaining_sections))})\s*:?\s*$"
    next_match = re.search(next_pattern, text[start:])

    if not next_match:
        return text[start:].strip()

    return text[start:start + next_match.start()].strip()