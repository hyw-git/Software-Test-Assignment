from typing import Any, Dict, List


METHOD_META = {
    "EP": {
        "name": "Equivalence Partitioning",
        "isoRef": "ISO/IEC/IEEE 29119-4 — equivalence partitioning",
        "description": "Divide inputs into valid/invalid equivalence classes and select representative values.",
    },
    "BVA": {
        "name": "Boundary Value Analysis",
        "isoRef": "ISO/IEC/IEEE 29119-4 — boundary value analysis",
        "description": "Test values at, below, and above boundaries of input domains.",
    },
    "DecisionTable": {
        "name": "Decision Table Testing",
        "isoRef": "ISO/IEC/IEEE 29119-4 — decision table testing",
        "description": "Combine conditions and actions in a decision table for combinatorial business rules.",
    },
    "Combinatorial": {
        "name": "Combinatorial / Pairwise Testing",
        "isoRef": "ISO/IEC/IEEE 29119-4 — combinatorial test design techniques",
        "description": "Cover interactions of multiple factors with pairwise-reduced combinations.",
    },
    "StateTransition": {
        "name": "State Transition Testing",
        "isoRef": "ISO/IEC/IEEE 29119-4 — state transition testing",
        "description": "Exercise states and transitions per the state model and coverage criterion.",
    },
}

METHOD_META["WhiteBoxJava"] = {
    "name": "Java White-Box Testing",
    "isoRef": "Statement and branch coverage",
    "description": "Analyze Java method control flow and generate statement/branch coverage sequences.",
}


def build_test_strategies(
    requirements: List[Dict[str, Any]],
    testcases: List[Dict[str, Any]],
    coverage_items: List[Any],
) -> List[Dict[str, Any]]:
    strategies: List[Dict[str, Any]] = []
    methods_present = sorted(
        {str(c.get("designMethod", "")).strip() for c in testcases if c.get("designMethod") in METHOD_META}
    )

    for index, method in enumerate(methods_present, start=1):
        meta = METHOD_META[method]
        linked = [str(c.get("id", "")) for c in testcases if str(c.get("designMethod", "")) == method]
        linked_reqs = sorted(
            {
                str(ref)
                for c in testcases
                if str(c.get("designMethod", "")) == method
                for ref in (c.get("traceability") or [])
            }
        )
        strategies.append(
            {
                "id": f"STR-{index:03d}",
                "method": method,
                "name": meta["name"],
                "isoRef": meta["isoRef"],
                "description": meta["description"],
                "coverageItems": [item for item in coverage_items if method.lower() in _coverage_text(item).lower()][:5]
                or coverage_items[:2],
                "linkedRequirements": linked_reqs,
                "linkedTestcases": linked,
                "rationale": f"Selected based on the structured requirements using {method} per the test design scope.",
            }
        )
    return strategies


def _coverage_text(item: Any) -> str:
    if isinstance(item, dict):
        return " ".join(str(item.get(key, "")) for key in ("id", "type", "target", "methodId", "methodName"))
    return str(item)
