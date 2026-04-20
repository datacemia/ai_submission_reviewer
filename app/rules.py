from typing import Any

TEMPLATES: dict[str, dict[str, Any]] = {
    "academic_article": {
        "label": "Academic Article",
        "required_sections": [
            "Abstract",
            "Keywords",
            "Introduction",
            "Background",
            "Insights and Applications",
            "Conclusions",
            "References",
        ],
        "optional_sections": [
            "Figures and Tables",
        ],
        "abstract_min_words": 150,
        "abstract_max_words": 300,
        "keywords_min": 3,
        "keywords_max": 5,
        "min_references": 20,
    },
    "research_article": {
        "label": "Research Article",
        "required_sections": [
            "Abstract",
            "Keywords",
            "Introduction",
            "Literature Review",
            "Methodology",
            "Results",
            "Discussion",
            "Conclusion",
            "References",
        ],
        "optional_sections": [
            "Research Objectives",
            "Conceptual Framework",
            "Recommendations",
            "Acknowledgements",
        ],
        "abstract_min_words": 150,
        "abstract_max_words": 300,
        "keywords_min": 3,
        "keywords_max": 5,
        "min_references": 20,
    },
}