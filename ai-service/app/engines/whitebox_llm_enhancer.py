"""LLM enhancement scaffolding for deterministic Java white-box designs.

This module deliberately does not identify CFG nodes, coverage items, paths,
or coverage targets. It only prepares prompt context and validates optional
LLM responses that add human-facing review guidance.
"""

from __future__ import annotations

import json
import os
import re
from copy import deepcopy
from typing import Any, Dict, List, Tuple


ALLOWED_ENHANCEMENT_FIELDS = {
    "naturalLanguageTitle",
    "refinedInputSuggestions",
    "refinedSetupSuggestions",
    "refinedOracleSuggestions",
    "reviewerQuestions",
    "reviewerWarnings",
    "testIntentSummary",
}
FORBIDDEN_LLM_FIELDS = {
    "cfg",
    "path",
    "coverageItems",
    "coverageTargets",
    "testSequences",
    "nodes",
    "edges",
    "sourceNodeId",
    "sourceEdgeId",
    "sourceDecisionId",
    "sourceStatementId",
}


def enhance_whitebox_design_with_llm(design: Dict[str, Any], llm_client: Any = None) -> Dict[str, Any]:
    """Attach LLM enhancement placeholders or parsed LLM enhancements.

    When llm_client is None, no model call is made; each item contains a
    deterministic promptPreview plus a warning that the real client was not
    configured. When llm_client is provided, it is called through an
    OpenAI-compatible API and only the allowed human-facing fields are accepted
    from the response.
    """
    result = deepcopy(design) if isinstance(design, dict) else {}
    enhanced: List[Dict[str, Any]] = []
    warnings: List[str] = []
    testcases = _testcases_by_sequence_id(result.get("testcases", []))

    for sequence in result.get("testSequences", []) or []:
        if not isinstance(sequence, dict):
            continue
        base_sequence_id = str(sequence.get("id") or "")
        testcase = testcases.get(base_sequence_id, {})
        prompt = build_llm_enhancement_prompt(result, sequence, testcase)
        item = _empty_enhancement(base_sequence_id, prompt)
        raw_response, call_warning = _call_llm_client(llm_client, prompt)
        if call_warning:
            item["reviewerWarnings"].append(call_warning)
        if raw_response:
            parsed, parse_warnings = parse_llm_enhancement_response(raw_response)
            item.update(parsed)
            item["reviewerWarnings"] = _unique(item["reviewerWarnings"] + parse_warnings)
        enhanced.append(item)

    result["llmEnhancedTestcases"] = enhanced
    result.setdefault("summary", {})
    if isinstance(result["summary"], dict):
        result["summary"]["llmEnhancementMode"] = "prompt-preview" if llm_client is None else "llm-assisted"
        result["summary"]["llmBoundary"] = (
            "LLM may explain coverage items, refine input/setup/oracle, and draft natural-language design notes, "
            "but must not create/delete coverage items or modify CFG paths."
        )
    if warnings:
        result["warnings"] = _unique([str(item) for item in result.get("warnings", []) if str(item).strip()] + warnings)
    return result


def build_llm_enhancement_prompt(
    design: Dict[str, Any],
    sequence: Dict[str, Any],
    testcase: Dict[str, Any] | None = None,
) -> str:
    """Build a deterministic prompt for one white-box sequence."""
    testcase = testcase if isinstance(testcase, dict) else {}
    coverage_targets = [str(item) for item in sequence.get("coverageTargets", []) or [] if str(item).strip()]
    context = {
        "sourceFile": design.get("sourceFile", "JavaSource.java"),
        "sourceSnippet": _truncate(str(design.get("sourceSnippet") or ""), 6000),
        "baseSequenceId": sequence.get("id", ""),
        "baseTitle": sequence.get("title", testcase.get("title", "")),
        "methodId": sequence.get("methodId", ""),
        "coverageTargets": coverage_targets,
        "coverageItems": _coverage_items_for_targets(design.get("coverageItems", []), coverage_targets),
        "path": sequence.get("path", []),
        "pathConstraints": sequence.get("pathConstraints", []),
        "inputHints": sequence.get("inputHints", {}),
        "setupHints": sequence.get("setupHints", []),
        "constraintConflicts": sequence.get("constraintConflicts", []),
        "exceptionTriggerHints": sequence.get("exceptionTriggerHints", []),
        "oracleHints": sequence.get("oracleHints", {}),
        "needsReview": bool(sequence.get("needsReview", True)),
        "baseTestcase": {
            "id": testcase.get("id", ""),
            "title": testcase.get("title", ""),
            "input": testcase.get("input", ""),
            "expected": testcase.get("expected", ""),
            "oracle": testcase.get("oracle", ""),
        },
    }
    schema = {
        "naturalLanguageTitle": "short human-readable test title, e.g. Reject invalid pose analysis request",
        "testIntentSummary": "one or two sentences describing what this sequence verifies",
        "refinedInputSuggestions": ["external input, request body, query/path parameter suggestions only"],
        "refinedSetupSuggestions": ["mock/stub/environment setup suggestions"],
        "refinedOracleSuggestions": ["assertions such as HTTP status/body/exception expectations"],
        "reviewerQuestions": ["questions for unmapped constraints or ambiguous trigger sites"],
        "reviewerWarnings": ["warnings about uncertainty or manual review"],
    }
    return (
        "You are enhancing deterministic Java white-box test design output into human-friendly review notes.\n"
        "Hard boundary: do not create, delete, rename, or modify CFG nodes, CFG edges, coverageItems, coverageTargets, "
        "or paths. Do not generate JUnit, Mockito, or MockMvc code in this phase.\n"
        "Return JSON only with exactly these allowed fields: "
        + ", ".join(sorted(ALLOWED_ENHANCEMENT_FIELDS))
        + ".\n"
        "Guidance: turn pathConstraints into external inputs only when they clearly refer to method parameters or request fields. "
        "Map internal variables/fields to setup suggestions or reviewer questions. Use oracleHints for status/body suggestions.\n\n"
        "Allowed output schema:\n"
        + json.dumps(schema, ensure_ascii=False, indent=2)
        + "\n\nDeterministic context:\n"
        + json.dumps(context, ensure_ascii=False, indent=2)
    )


def parse_llm_enhancement_response(raw_response: Any) -> Tuple[Dict[str, Any], List[str]]:
    """Parse and sanitize an LLM response for allowed enhancement fields only."""
    warnings: List[str] = []
    parsed = _coerce_json_object(raw_response)
    if parsed is None:
        return _empty_fields(), ["LLM enhancement response was not valid JSON object."]

    forbidden = sorted(field for field in parsed if field in FORBIDDEN_LLM_FIELDS)
    if forbidden:
        warnings.append(f"Ignored forbidden LLM fields: {', '.join(forbidden)}.")

    result = _empty_fields()
    for key in ALLOWED_ENHANCEMENT_FIELDS:
        if key not in parsed:
            continue
        if key in {"naturalLanguageTitle", "testIntentSummary"}:
            result[key] = str(parsed.get(key) or "").strip()
        else:
            result[key] = _string_list(parsed.get(key))
    return result, warnings


def _empty_enhancement(base_sequence_id: str, prompt: str) -> Dict[str, Any]:
    item = {"baseSequenceId": base_sequence_id, **_empty_fields(), "promptPreview": prompt}
    return item


def _empty_fields() -> Dict[str, Any]:
    return {
        "naturalLanguageTitle": "",
        "testIntentSummary": "",
        "refinedInputSuggestions": [],
        "refinedSetupSuggestions": [],
        "refinedOracleSuggestions": [],
        "reviewerQuestions": [],
        "reviewerWarnings": [],
    }


def _call_llm_client(llm_client: Any, prompt: str) -> Tuple[Any, str]:
    if llm_client is None:
        return None, "Real LLM client is not configured; promptPreview was generated without model enhancement."
    model = _llm_model()
    try:
        if hasattr(llm_client, "responses") and hasattr(llm_client.responses, "create"):
            response = llm_client.responses.create(
                model=model,
                input=prompt,
                temperature=0.1,
            )
            return _extract_text(response), ""
        if hasattr(llm_client, "chat") and hasattr(llm_client.chat, "completions") and hasattr(llm_client.chat.completions, "create"):
            response = llm_client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a Java white-box test design enhancer. "
                            "Return JSON only and never modify CFG, path, coverageItems, or coverageTargets."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
            )
            return _extract_text(response), ""
        return None, "Real LLM client does not expose responses.create or chat.completions.create."
    except Exception as exc:  # noqa: BLE001
        return None, f"LLM enhancement call failed: {exc}"


def _llm_model() -> str:
    return os.getenv("OPENAI_MODEL", "deepseek-chat").strip() or "deepseek-chat"


def _extract_text(response: Any) -> str:
    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()
    choices = getattr(response, "choices", None)
    if isinstance(choices, list) and choices:
        message = getattr(choices[0], "message", None)
        if message is not None:
            content = getattr(message, "content", "")
            if isinstance(content, str):
                return content.strip()
    if isinstance(response, str):
        return response.strip()
    return ""


def _coerce_json_object(raw_response: Any) -> Dict[str, Any] | None:
    if isinstance(raw_response, dict):
        return raw_response
    text = _response_text(raw_response)
    if not text:
        return None
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else None
    except Exception:  # noqa: BLE001
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            return None
        try:
            value = json.loads(match.group(0))
            return value if isinstance(value, dict) else None
        except Exception:  # noqa: BLE001
            return None


def _response_text(raw_response: Any) -> str:
    if raw_response is None:
        return ""
    if isinstance(raw_response, str):
        return raw_response.strip()
    for attr in ("content", "text", "message"):
        value = getattr(raw_response, attr, None)
        if isinstance(value, str):
            return value.strip()
    return str(raw_response).strip()


def _coverage_items_for_targets(items: Any, targets: List[str]) -> List[Dict[str, Any]]:
    target_set = set(targets)
    return [
        item
        for item in (items if isinstance(items, list) else [])
        if isinstance(item, dict) and str(item.get("id") or "") in target_set
    ]


def _testcases_by_sequence_id(testcases: Any) -> Dict[str, Dict[str, Any]]:
    result: Dict[str, Dict[str, Any]] = {}
    for testcase in testcases if isinstance(testcases, list) else []:
        if not isinstance(testcase, dict):
            continue
        sequence_id = str(testcase.get("sequenceId") or "")
        if sequence_id:
            result[sequence_id] = testcase
    return result


def _string_list(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n... [truncated]"


def _unique(values: List[str]) -> List[str]:
    seen = set()
    result = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result
