from typing import Any, Dict, List, Tuple


REQUIRED_ARTIFACT_KEYS = (
    "requirementsStructured",
    "riskItems",
    "testcases",
)

ALLOWED_METHODS = {"EP", "BVA", "Combinatorial", "StateTransition", "DecisionTable"}


def validate_llm_payload(payload: Dict[str, Any]) -> Tuple[bool, List[str]]:
    issues: List[str] = []
    if not isinstance(payload, dict):
        return False, ["payload is not a JSON object"]

    reqs = payload.get("requirementsStructured")
    if not isinstance(reqs, list) or not reqs:
        issues.append("missing or empty requirementsStructured")

    risks = payload.get("riskItems")
    if not isinstance(risks, list) or not risks:
        issues.append("missing or empty riskItems")

    cases = payload.get("testcases")
    if not isinstance(cases, list) or not cases:
        issues.append("missing or empty testcases")
    else:
        methods = set()
        for item in cases:
            if not isinstance(item, dict):
                continue
            method = str(item.get("designMethod", "")).strip()
            if method in ALLOWED_METHODS:
                methods.add(method)
        if len(methods) < 3:
            issues.append(f"testcases need >=3 design methods, got {sorted(methods)}")

    for risk in risks if isinstance(risks, list) else []:
        if not isinstance(risk, dict):
            continue
        impact = risk.get("impact")
        likelihood = risk.get("likelihood")
        score = risk.get("riskScore")
        if impact is not None and likelihood is not None and score is not None:
            try:
                if int(impact) * int(likelihood) != int(score):
                    issues.append(f"riskScore mismatch for {risk.get('reqId', '?')}")
            except (TypeError, ValueError):
                issues.append("invalid risk numeric fields")

    return len(issues) == 0, issues
