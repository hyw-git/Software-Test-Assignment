"""Generation-pipeline worker for deterministic Java white-box test design."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from app.engines.worker_contract import WorkerResult

from .whitebox_coverage import generate_coverage_items, normalize_coverage_criterion
from .whitebox_java_analyzer import analyze_java_source
from .whitebox_llm_enhancer import enhance_whitebox_design_with_llm
from .whitebox_sequence_generator import generate_test_sequences


logger = logging.getLogger(__name__)
WORKER_VERSION = "whitebox-java-cfg-worker-v5"
LLM_BOUNDARY_NOTE = (
    "LLM may later explain coverage items, refine input/setup/oracle, and draft JUnit, "
    "but must not create/delete CFG coverage items."
)


def generate_java_whitebox_design(
    source_code: str,
    source_name: str = "JavaSource.java",
    coverage_criterion: str = "statement+branch",
    reviewer_overrides: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Return deterministic CFG-based Java white-box design artifacts."""
    warnings: List[str] = []
    criterion, criterion_warnings = normalize_coverage_criterion(coverage_criterion)
    warnings.extend(criterion_warnings)
    analysis = analyze_java_source(source_code, source_name=source_name)
    warnings.extend([str(item) for item in analysis.get("warnings", []) if str(item).strip()])
    coverage_items, coverage_warnings = generate_coverage_items(analysis, criterion, reviewer_overrides or {})
    warnings.extend(coverage_warnings)
    sequence_warnings: List[str] = []
    sequences = generate_test_sequences(analysis, coverage_items, sequence_warnings)
    warnings.extend(sequence_warnings)
    return {
        "sourceFile": source_name,
        "sourceSnippet": _source_snippet(source_code),
        "language": "java",
        "analysis": analysis,
        "coverageItems": coverage_items,
        "testSequences": sequences,
        "summary": {
            "coverageCriterion": criterion,
            "methodCount": sum(len(item.get("methods", []) or []) for item in analysis.get("classes", []) or []),
            "coverageItemCount": len(coverage_items),
            "sequenceCount": len(sequences),
            "identificationMode": "deterministic CFG-based coverage item identification",
            "llmBoundary": LLM_BOUNDARY_NOTE,
        },
        "warnings": _unique(warnings),
    }


async def worker_whitebox_java(ctx: Any, start_index: int = 1) -> WorkerResult:
    """Analyze Java code and generate coverage-oriented white-box sequences."""
    t0 = time.perf_counter()
    warnings: List[str] = []
    try:
        source, source_name = _extract_java_source(ctx)
        if not source.strip():
            return WorkerResult(
                technique="WhiteBoxJava",
                testcases=[],
                artifacts={
                    "whiteboxAnalysis": {"language": "java", "sourceName": source_name, "classes": [], "warnings": ["No Java source was provided."]},
                    "coverageItems": [],
                    "testSequences": [],
                    "llmEnhancedTestcases": [],
                    "warnings": ["No Java source was provided."],
                    "llmReadyWhiteboxContext": {
                        "sourceFile": source_name,
                        "coverageItems": [],
                        "testSequences": [],
                        "testcases": [],
                        "notes": [
                            "Coverage items are deterministic CFG-based results.",
                            "LLM must not add/delete coverage items.",
                            "LLM may refine input data, mock setup, oracle, and JUnit drafts.",
                        ],
                    },
                    "engineMetadata": {
                        "workerVersion": WORKER_VERSION,
                        "identificationMode": "deterministic CFG-based coverage item identification",
                        "llmBoundary": LLM_BOUNDARY_NOTE,
                    },
                },
                elapsed_ms=int((time.perf_counter() - t0) * 1000),
            )

        overrides = _reviewer_overrides(ctx)
        design = generate_java_whitebox_design(
            source,
            source_name=source_name,
            coverage_criterion=getattr(ctx, "coverage_criterion", "statement+branch"),
            reviewer_overrides=overrides,
        )
        analysis = design["analysis"]
        coverage_items = design["coverageItems"]
        sequences = design["testSequences"]
        warnings.extend(design["warnings"])
        criterion = str(design.get("summary", {}).get("coverageCriterion") or "statement+branch")
        cases = _sequences_to_testcases(sequences, analysis, start_index)
        enhancement_input = {
            **design,
            "testcases": cases,
        }
        llm_client = _make_llm_client()
        loop = asyncio.get_running_loop()
        enhanced_design = await loop.run_in_executor(
            None,
            lambda: enhance_whitebox_design_with_llm(enhancement_input, llm_client=llm_client),
        )
        llm_enhanced_cases = enhanced_design.get("llmEnhancedTestcases", [])
        llm_ready_context = {
            "sourceFile": design.get("sourceFile", source_name),
            "sourceSnippet": design.get("sourceSnippet", ""),
            "coverageItems": coverage_items,
            "testSequences": sequences,
            "testcases": cases,
            "llmEnhancedTestcases": llm_enhanced_cases,
            "notes": [
                "Coverage items are deterministic CFG-based results.",
                "LLM must not add/delete coverage items.",
                "LLM may refine input data, mock setup, oracle, and JUnit drafts.",
            ],
        }

        return WorkerResult(
            technique="WhiteBoxJava",
            testcases=cases,
            artifacts={
                "whiteboxAnalysis": analysis,
                "coverageItems": coverage_items,
                "testSequences": sequences,
                "llmEnhancedTestcases": llm_enhanced_cases,
                "warnings": _unique(warnings),
                "llmReadyWhiteboxContext": llm_ready_context,
                "engineMetadata": {
                    "workerVersion": WORKER_VERSION,
                    "coverageCriterion": criterion,
                    "sequenceCount": len(sequences),
                    "coverageItemCount": len(coverage_items),
                    "identificationMode": "deterministic CFG-based coverage item identification",
                    "llmBoundary": LLM_BOUNDARY_NOTE,
                },
            },
            elapsed_ms=int((time.perf_counter() - t0) * 1000),
        )
    except Exception as exc:  # noqa: BLE001
        return WorkerResult(
            technique="WhiteBoxJava",
            testcases=[],
            artifacts={"warnings": [f"WhiteBoxJava worker failed: {exc}"]},
            error=str(exc),
            elapsed_ms=int((time.perf_counter() - t0) * 1000),
        )


def _extract_java_source(ctx: Any) -> Tuple[str, str]:
    extra = getattr(ctx, "extra", {}) if getattr(ctx, "extra", None) is not None else {}
    source_content = str(extra.get("sourceContent") or "")
    whitebox_description = str(getattr(ctx, "whitebox_description", "") or "")
    java_blocks, java_source_name = _extract_java_file_blocks(source_content)
    if java_blocks:
        source_content = "\n\n".join(java_blocks)
    candidates = [source_content]
    if whitebox_description.strip() and whitebox_description.strip() != source_content.strip():
        candidates.append(whitebox_description)
    combined = "\n\n".join(part for part in candidates if part.strip())
    if not combined.strip():
        return "", "JavaSource.java"

    fenced = re.findall(r"```(?:java)?\s*([\s\S]*?)```", combined, flags=re.IGNORECASE)
    if fenced:
        return "\n\n".join(block.strip() for block in fenced if block.strip()), java_source_name or _source_name_from_headers(combined)

    lines = []
    for line in combined.splitlines():
        stripped = line.strip()
        if re.fullmatch(r"\[(manual-input|csv-input)\]", stripped):
            continue
        if re.match(r"\[file-\d+\]\s+name=", stripped):
            continue
        lines.append(line)
    return "\n".join(lines).strip(), java_source_name or _source_name_from_headers(combined)


def _make_llm_client() -> Optional[Any]:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        from openai import OpenAI  # type: ignore[import]
    except ImportError:
        logger.warning("openai package is not installed; WhiteBoxJava LLM enhancement will emit prompt previews only.")
        return None
    base_url = os.getenv("OPENAI_BASE_URL", "").strip()
    if base_url:
        return OpenAI(api_key=api_key, base_url=base_url)
    return OpenAI(api_key=api_key)


def _extract_java_file_blocks(text: str) -> Tuple[List[str], str]:
    blocks: List[str] = []
    current: List[str] = []
    current_is_java = False
    first_name = ""

    def flush() -> None:
        nonlocal current
        if current_is_java and any(line.strip() for line in current):
            blocks.append("\n".join(current).strip())
        current = []

    for line in str(text or "").splitlines():
        match = re.match(r"\[file-\d+\]\s+name=([^\s]+)", line.strip())
        if match:
            flush()
            name = match.group(1).strip()
            current_is_java = name.lower().endswith(".java")
            if current_is_java and not first_name:
                first_name = name
            continue
        if re.match(r"\[(manual-input|csv-input)\]", line.strip()):
            flush()
            current_is_java = False
            continue
        if current_is_java:
            current.append(line)
    flush()
    return blocks, first_name


def _source_name_from_headers(text: str) -> str:
    for match in re.finditer(r"\[file-\d+\]\s+name=([^\s]+)", text):
        name = match.group(1).strip()
        if name.lower().endswith(".java"):
            return name
    return "JavaSource.java"


def _reviewer_overrides(ctx: Any) -> Dict[str, Any]:
    extra = getattr(ctx, "extra", {}) if getattr(ctx, "extra", None) is not None else {}
    for key in ("reviewerOverrides", "reviewer_overrides"):
        value = extra.get(key)
        if isinstance(value, dict):
            return value
    return {}


def _sequences_to_testcases(sequences: List[Dict[str, Any]], analysis: Dict[str, Any], start_index: int) -> List[Dict[str, Any]]:
    method_names = _method_names(analysis)
    cases: List[Dict[str, Any]] = []
    for offset, sequence in enumerate(sequences):
        method_id = str(sequence.get("methodId") or "")
        method_name = method_names.get(method_id, method_id or "Java method")
        coverage_targets = [str(item) for item in sequence.get("coverageTargets", []) if str(item).strip()]
        setup_hints = _sequence_setup_hints(sequence)
        cases.append(
            {
                "id": f"TC-WBJ-{start_index + offset:03d}",
                "technique": "white-box",
                "designMethod": "WhiteBoxJava",
                "title": str(sequence.get("title") or f"White-box sequence for {method_name}"),
                "precondition": f"Java method {method_name} is available for review; generated sequence is design-level and not executable JUnit.",
                "input": json.dumps(sequence.get("inputHints", {}), ensure_ascii=False),
                "steps": _path_to_steps(sequence.get("path", [])),
                "expected": _sequence_expected(sequence),
                "oracle": _sequence_oracle(sequence),
                "priority": "medium" if sequence.get("needsReview") else "high",
                "traceability": coverage_targets,
                "sequenceId": sequence.get("id"),
                "coverageTargets": coverage_targets,
                "pathConstraints": _list_of_strings(sequence.get("pathConstraints", [])),
                "setup": "\n".join(setup_hints),
                "setupHints": setup_hints,
                "constraintConflicts": _list_of_strings(sequence.get("constraintConflicts", [])),
                "exceptionTriggerHints": _list_of_dicts(sequence.get("exceptionTriggerHints", [])),
                "oracleHints": sequence.get("oracleHints") if isinstance(sequence.get("oracleHints"), dict) else {},
                "needsReview": bool(sequence.get("needsReview", True)),
            }
        )
    return cases


def _sequence_setup_hints(sequence: Dict[str, Any]) -> List[str]:
    hints = _list_of_strings(sequence.get("setupHints", []))
    triggers = _list_of_dicts(sequence.get("exceptionTriggerHints", []))
    if triggers:
        hints.append("Configure one of the possible throw sites to throw the caught exception.")
    return _unique(hints)


def _sequence_expected(sequence: Dict[str, Any]) -> str:
    oracle = sequence.get("oracleHints") if isinstance(sequence.get("oracleHints"), dict) else {}
    status = str(oracle.get("httpStatusHint") or "unknown")
    return_text = str(oracle.get("returnText") or "").strip()
    exit_kind = str(oracle.get("exitKind") or "normal")
    if return_text:
        status_part = f" HTTP {status}" if status != "unknown" else ""
        return f"Expected path exits by {exit_kind}{status_part}: {return_text}"
    return str(sequence.get("expectedBehaviorHint") or "Follow the selected white-box path.")


def _sequence_oracle(sequence: Dict[str, Any]) -> str:
    oracle = sequence.get("oracleHints") if isinstance(sequence.get("oracleHints"), dict) else {}
    status = str(oracle.get("httpStatusHint") or "unknown")
    body_hint = str(oracle.get("bodyHint") or "").strip()
    review = "Reviewer should confirm concrete expected return/exception values before executable test implementation."
    if status != "unknown" or body_hint:
        return f"{review} Status hint: {status}. Return/body hint: {body_hint or 'unknown'}"
    return review


def _list_of_strings(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _list_of_dicts(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _source_snippet(source_code: str, limit: int = 12000) -> str:
    text = str(source_code or "")
    if len(text) <= limit:
        return text
    return text[:limit] + "\n... [truncated]"


def _method_names(analysis: Dict[str, Any]) -> Dict[str, str]:
    names: Dict[str, str] = {}
    for class_item in analysis.get("classes", []) or []:
        class_name = str(class_item.get("name") or "")
        for method in class_item.get("methods", []) or []:
            method_id = str(method.get("id") or "")
            method_name = str(method.get("name") or "")
            names[method_id] = f"{class_name}.{method_name}" if class_name else method_name
    return names


def _path_to_steps(path: Any) -> str:
    lines = []
    for index, item in enumerate(path if isinstance(path, list) else [], start=1):
        if not isinstance(item, dict):
            continue
        if item.get("type") == "node":
            descriptor = item.get("nodeType") or "node"
            detail = item.get("text") or item.get("nodeId") or ""
            line = f" at line {item.get('line')}" if item.get("line") else ""
            lines.append(f"{index}. Visit {descriptor} {item.get('nodeId')}{line}: {detail}")
        elif item.get("type") == "edge":
            label = item.get("label") or item.get("edgeType") or "edge"
            condition = f" when {item.get('condition')}" if item.get("condition") else ""
            lines.append(f"{index}. Take {label} edge {item.get('edgeId')} from {item.get('from')} to {item.get('to')}{condition}")
        elif item.get("type") == "decision":
            lines.append(
                f"{index}. Evaluate {item.get('decisionId')} as {item.get('expectedValue')}: {item.get('condition')}"
            )
        elif item.get("type") == "statement":
            lines.append(f"{index}. Execute {item.get('statementId')} at line {item.get('line')}")
        else:
            lines.append(f"{index}. Review manual target: {item.get('target', '')}")
    return "\n".join(lines) or "Review generated white-box sequence."


def _unique(values: List[str]) -> List[str]:
    seen = set()
    result = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result
