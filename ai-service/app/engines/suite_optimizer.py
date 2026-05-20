from typing import Any, Dict, List, Set


def _risk_map(risk_items: List[Dict[str, Any]]) -> Dict[str, int]:
    mapping: Dict[str, int] = {}
    for item in risk_items:
        req_id = str(item.get("reqId", ""))
        mapping[req_id] = int(item.get("riskScore", 0))
    return mapping


def _case_risk_score(case: Dict[str, Any], risk_mapping: Dict[str, int]) -> int:
    trace = case.get("traceability") or []
    scores = [risk_mapping.get(str(ref), 0) for ref in trace]
    priority_boost = {"high": 3, "medium": 2, "low": 1}.get(str(case.get("priority", "medium")).lower(), 1)
    return max(scores + [priority_boost])


def optimize_test_suite(
    testcases: List[Dict[str, Any]],
    risk_items: List[Dict[str, Any]],
    coverage_items: List[str],
    mode: str = "risk-first",
) -> Dict[str, Any]:
    risk_mapping = _risk_map(risk_items)
    ranked = sorted(
        testcases,
        key=lambda item: (_case_risk_score(item, risk_mapping), str(item.get("id", ""))),
        reverse=True,
    )

    if mode == "minimize":
        seen_coverage: Set[str] = set()
        optimized: List[Dict[str, Any]] = []
        removed: List[str] = []

        for case in ranked:
            trace = set(str(t) for t in (case.get("traceability") or []))
            method = str(case.get("designMethod", ""))
            signature = frozenset(trace | {method})
            if signature and signature.issubset(seen_coverage):
                removed.append(str(case.get("id", "")))
                continue
            seen_coverage.update(trace)
            seen_coverage.add(method)
            optimized.append(case)

        return {
            "mode": "minimize",
            "algorithm": "greedy-coverage-dedup",
            "optimizedSuite": [c.get("id") for c in optimized],
            "removedCases": removed,
            "coverageItemsAddressed": sorted(seen_coverage),
            "source": "rule-suite-optimizer",
        }

    optimized_ids = [c.get("id") for c in ranked]
    high_risk_ids = [c.get("id") for c in ranked if _case_risk_score(c, risk_mapping) >= 9]
    removed = [c.get("id") for c in testcases if c.get("id") not in set(high_risk_ids[: max(6, len(high_risk_ids))])]

    return {
        "mode": "risk-first",
        "algorithm": "risk-score-sort + top-k retention",
        "optimizedSuite": high_risk_ids if high_risk_ids else optimized_ids[:8],
        "removedCases": removed[: max(0, len(testcases) - len(high_risk_ids or optimized_ids[:8]))],
        "coverageItemsAddressed": coverage_items[:10],
        "source": "rule-suite-optimizer",
    }
