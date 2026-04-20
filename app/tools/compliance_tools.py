def check_language_requirements(text: str) -> dict:
    # Placeholder heuristic
    ascii_ratio = sum(1 for ch in text if ord(ch) < 128) / max(len(text), 1)
    return {
        "ok": ascii_ratio > 0.85,
        "message": "Likely English-compatible content." if ascii_ratio > 0.85 else "Language may need manual verification.",
    }


def check_ethics_requirements(text: str) -> dict:
    lower = text.lower()
    found_originality = "original" in lower or "originality" in lower
    found_conflict = "conflict of interest" in lower or "conflicts of interest" in lower

    return {
        "ok": found_originality or found_conflict,
        "notes": {
            "originality_statement_found": found_originality,
            "conflict_of_interest_found": found_conflict,
        },
    }