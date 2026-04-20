from app.models import ReviewIssue


def compute_score(issues: list[ReviewIssue]) -> int:
    score = 100
    for issue in issues:
        if issue.severity == "critical":
            score -= 15
        elif issue.severity == "warning":
            score -= 7
        else:
            score -= 3
    return max(score, 0)