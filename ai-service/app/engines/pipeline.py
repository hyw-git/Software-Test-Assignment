import time
from typing import Any, Dict, List, Optional, Tuple

from .blackbox_engine import generate_blackbox_artifacts
from .oracle_engine import attach_oracles
from .requirement_parser import parse_content_blocks
from .risk_engine import score_requirements
from .strategy_builder import build_test_strategies
from .suite_optimizer import optimize_test_suite
from .whitebox_engine import build_state_model, generate_state_transition_sequences


ENGINE_VERSION = "autotestdesign-engine-v2"


def _build_traceability(requirements: List[Dict[str, Any]], testcases: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    trace: List[Dict[str, Any]] = []
    for req in requirements:
        req_id = str(req.get("id", ""))
        linked_cases = [
            str(c.get("id"))
            for c in testcases
            if req_id in [str(t) for t in (c.get("traceability") or [])]
        ]
        trace.append(
            {
                "reqId": req_id,
                "coverageItems": [f"{req.get('feature')}:结构化", f"{req.get('feature')}:黑盒设计"],
                "testcases": linked_cases,
            }
        )
    return trace


def run_deterministic_pipeline(
    content: str,
    include_whitebox: bool = True,
    include_oracle: bool = True,
    include_optimization: bool = True,
    coverage_criterion: str = "all-states",
    optimization_mode: str = "risk-first",
    whitebox_description: str = "",
) -> Dict[str, Any]:
    started = time.perf_counter()
    requirements, parse_channel = parse_content_blocks(content)
    risks = score_requirements(requirements)
    blackbox = generate_blackbox_artifacts(requirements)
    testcases: List[Dict[str, Any]] = list(blackbox.get("testcases") or [])

    state_model: Dict[str, Any] = {}
    if include_whitebox:
        state_model = build_state_model(requirements, coverage_criterion, whitebox_description)
        if state_model:
            st_cases, _ = generate_state_transition_sequences(state_model, coverage_criterion, start_index=len(testcases) + 1)
            testcases.extend(st_cases)

    if include_oracle:
        testcases = attach_oracles(testcases, requirements)

    coverage_items = list(blackbox.get("coverageItems") or [])
    test_strategies = build_test_strategies(requirements, testcases, coverage_items)

    optimization: Dict[str, Any] = {}
    if include_optimization:
        optimization = optimize_test_suite(testcases, risks, coverage_items, mode=optimization_mode)

    traceability = _build_traceability(requirements, testcases)
    engine_ms = int((time.perf_counter() - started) * 1000)

    return {
        "requirementsStructured": requirements,
        "riskItems": risks,
        "inputVariables": blackbox.get("inputVariables", []),
        "equivalencePartitions": blackbox.get("equivalencePartitions", []),
        "decisionTableRules": blackbox.get("decisionTableRules", []),
        "boundaryValues": blackbox.get("boundaryValues", []),
        "coverageItems": coverage_items,
        "testStrategies": test_strategies,
        "stateModel": state_model,
        "testSuiteOptimization": optimization,
        "traceability": traceability,
        "testcases": testcases,
        "missingItems": [],
        "assumptions": ["规则引擎对输入进行确定性解析、策略映射与测试设计"],
        "engineMetadata": {
            "engineVersion": ENGINE_VERSION,
            "parseChannel": parse_channel,
            "engineMs": engine_ms,
            "frEngines": {
                "FR1.0": "requirement_parser.parse_content_blocks",
                "FR1.1": "requirement_parser (CSV RFC + numbered text)",
                "FR2.0": "risk_engine.score_requirements + risk_config",
                "FR3.0": "blackbox_engine (EP/BVA/DT/Pairwise)",
                "FR4.0": "whitebox_engine (custom JSON/arrow model + sequences)",
                "FR5.0": "oracle_engine.attach_oracles",
                "FR6.0": "export via backend/frontend multi-format",
                "FR7.0": "suite_optimizer.optimize_test_suite",
            },
            "caseCount": len(testcases),
            "requirementCount": len(requirements),
            "strategyCount": len(test_strategies),
        },
        "timingMetrics": {"engineMs": engine_ms, "llmMs": 0, "totalMs": engine_ms},
    }


def _merge_cases(engine_cases: List[Dict[str, Any]], llm_cases: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_id: Dict[str, Dict[str, Any]] = {}
    for case in engine_cases:
        by_id[str(case.get("id", ""))] = case
    for case in llm_cases:
        cid = str(case.get("id", ""))
        if cid and cid not in by_id:
            by_id[cid] = case
        elif cid and cid in by_id:
            merged = dict(by_id[cid])
            for key in ("title", "steps", "expected", "oracle"):
                llm_val = str(case.get(key, "")).strip()
                if llm_val and (not str(merged.get(key, "")).strip() or key == "oracle"):
                    merged[key] = llm_val
            by_id[cid] = merged
    return list(by_id.values())


def _normalize_coverage_item(item: Any) -> str:
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, dict):
        for key in ("label", "name", "id", "feature", "coverageItem", "description"):
            value = item.get(key)
            if value:
                return str(value).strip()
    return str(item).strip()


def _merge_list(primary: List[Any], secondary: List[Any], key_fn) -> List[Any]:
    seen = set()
    merged: List[Any] = []
    for item in primary + secondary:
        key = key_fn(item)
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
    return merged


def _merge_coverage_items(primary: List[Any], secondary: List[Any]) -> List[str]:
    seen = set()
    merged: List[str] = []
    for item in primary + secondary:
        normalized = _normalize_coverage_item(item)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        merged.append(normalized)
    return merged


def merge_engine_with_llm(
    engine: Dict[str, Any],
    llm_artifacts: Optional[Dict[str, Any]],
    llm_cases: Optional[List[Dict[str, Any]]],
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    llm_artifacts = llm_artifacts if isinstance(llm_artifacts, dict) else {}
    llm_cases = llm_cases if isinstance(llm_cases, list) else []

    merged_artifacts = {
        "inputVariables": _merge_list(engine.get("inputVariables", []), llm_artifacts.get("inputVariables", []), lambda x: x),
        "equivalencePartitions": _merge_list(
            engine.get("equivalencePartitions", []),
            llm_artifacts.get("equivalencePartitions", []),
            lambda x: str(x.get("id", x.get("description", ""))),
        ),
        "boundaryValues": _merge_list(
            engine.get("boundaryValues", []),
            llm_artifacts.get("boundaryValues", []),
            lambda x: str(x.get("field", "")),
        ),
        "decisionTableRules": _merge_list(
            engine.get("decisionTableRules", []),
            llm_artifacts.get("decisionTableRules", []),
            lambda x: str(x.get("conditions", "")),
        ),
        "requirementsStructured": _merge_list(
            engine.get("requirementsStructured", []),
            llm_artifacts.get("requirementsStructured", []),
            lambda x: str(x.get("id", "")),
        ),
        "coverageItems": _merge_coverage_items(
            engine.get("coverageItems", []),
            llm_artifacts.get("coverageItems", []),
        ),
        "testStrategies": _merge_list(
            engine.get("testStrategies", []),
            llm_artifacts.get("testStrategies", []),
            lambda x: str(x.get("id", x.get("method", ""))),
        ),
        "riskItems": _merge_list(
            engine.get("riskItems", []),
            llm_artifacts.get("riskItems", []),
            lambda x: str(x.get("reqId", "")),
        ),
        "stateModel": engine.get("stateModel") or llm_artifacts.get("stateModel") or {},
        "testSuiteOptimization": engine.get("testSuiteOptimization") or llm_artifacts.get("testSuiteOptimization") or {},
        "traceability": _merge_list(
            engine.get("traceability", []),
            llm_artifacts.get("traceability", []),
            lambda x: str(x.get("reqId", x.get("ref", ""))),
        ),
        "missingItems": _merge_list(engine.get("missingItems", []), llm_artifacts.get("missingItems", []), lambda x: str(x)),
        "assumptions": _merge_list(engine.get("assumptions", []), llm_artifacts.get("assumptions", []), lambda x: str(x)),
        "engineMetadata": engine.get("engineMetadata", {}),
        "timingMetrics": engine.get("timingMetrics", {}),
    }

    merged_cases = _merge_cases(engine.get("testcases", []), llm_cases)
    if merged_artifacts.get("engineMetadata"):
        merged_artifacts["engineMetadata"]["mergedCaseCount"] = len(merged_cases)

    reqs = merged_artifacts.get("requirementsStructured", [])
    merged_artifacts["testStrategies"] = build_test_strategies(
        reqs,
        merged_cases,
        merged_artifacts.get("coverageItems", []),
    )

    if merged_artifacts.get("testSuiteOptimization") and merged_cases:
        merged_artifacts["testSuiteOptimization"] = optimize_test_suite(
            merged_cases,
            merged_artifacts.get("riskItems", []),
            merged_artifacts.get("coverageItems", []),
            mode=str(merged_artifacts["testSuiteOptimization"].get("mode", "risk-first")),
        )

    merged_artifacts["traceability"] = _build_traceability(reqs, merged_cases)

    return merged_artifacts, merged_cases
