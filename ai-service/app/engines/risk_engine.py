from typing import Any, Dict, List

from .risk_config import FEATURE_WEIGHTS, PRIORITY_THRESHOLDS, get_risk_matrix


def compute_risk_score(impact: int, likelihood: int) -> int:
    return max(1, min(25, int(impact) * int(likelihood)))


def score_to_priority(score: int) -> str:
    for threshold, label in PRIORITY_THRESHOLDS:
        if score >= threshold:
            return label
    return "low"


def score_requirements(requirements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    risks: List[Dict[str, Any]] = []
    for req in requirements:
        feature = str(req.get("feature", "通用功能"))
        weights = FEATURE_WEIGHTS.get(feature, FEATURE_WEIGHTS["通用功能"])
        impact = int(weights["impact"])
        likelihood = int(weights["likelihood"])
        rationale_suffix = weights.get("rationale", "")

        conditions = req.get("conditions") or []
        if any("状态" in str(c) for c in conditions):
            likelihood = min(5, likelihood + 1)
        if any("边界" in str(c) or "length" in str(c).lower() for c in conditions):
            impact = min(5, impact + 1)

        risk_score = compute_risk_score(impact, likelihood)
        risks.append(
            {
                "reqId": req.get("id", "REQ-UNKNOWN"),
                "impact": impact,
                "likelihood": likelihood,
                "riskScore": risk_score,
                "priority": score_to_priority(risk_score),
                "rationale": f"基于特性「{feature}」的确定性风险矩阵 (impact×likelihood)。{rationale_suffix}",
                "source": "rule-risk-engine",
                "matrixRef": "risk_config.FEATURE_WEIGHTS",
            }
        )
    return risks


def export_risk_matrix() -> dict:
    return get_risk_matrix()
