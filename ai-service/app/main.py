import json
import os
import re
import time
from io import BytesIO
from typing import Any, Dict, List

from fastapi import FastAPI
from fastapi import HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

try:
    from openai import OpenAI
except Exception:  # pragma: no cover
    OpenAI = None

from app.engines.pipeline import merge_engine_with_llm, run_deterministic_pipeline
from app.engines.risk_engine import export_risk_matrix
from app.engines.schema_validator import validate_llm_payload
from app.export_xlsx import build_xlsx_bytes

app = FastAPI(title="AI Testcase Service")


class GenerateRequest(BaseModel):
    sourceType: str = "requirements"
    content: str = ""
    testTechnique: str = "black-box"
    promptMode: str = "default"
    customPrompt: str = ""
    documents: List[Dict[str, str]] = []
    includeWhitebox: bool = False
    includeOracle: bool = False
    includeOptimization: bool = False
    whiteboxDescription: str = ""
    coverageCriterion: str = "all-states"


class TestCase(BaseModel):
    id: str
    technique: str
    designMethod: str
    title: str
    precondition: str
    input: str
    steps: str
    expected: str
    oracle: str = ""
    priority: str
    traceability: List[str] = []


class TestArtifacts(BaseModel):
    inputVariables: List[str] = Field(default_factory=list)
    equivalencePartitions: List[Dict[str, str]] = Field(default_factory=list)
    boundaryValues: List[Dict[str, Any]] = Field(default_factory=list)
    decisionTableRules: List[Dict[str, str]] = Field(default_factory=list)
    missingItems: List[str] = Field(default_factory=list)
    assumptions: List[str] = Field(default_factory=list)
    requirementsStructured: List[Dict[str, Any]] = Field(default_factory=list)
    coverageItems: List[str] = Field(default_factory=list)
    riskItems: List[Dict[str, Any]] = Field(default_factory=list)
    stateModel: Dict[str, Any] = Field(default_factory=dict)
    testSuiteOptimization: Dict[str, Any] = Field(default_factory=dict)
    traceability: List[Dict[str, Any]] = Field(default_factory=list)
    testStrategies: List[Dict[str, Any]] = Field(default_factory=list)
    engineMetadata: Dict[str, Any] = Field(default_factory=dict)


class GenerateResponse(BaseModel):
    model: str
    testTechnique: str
    promptVersion: str
    promptUsed: str
    llmRawOutput: str
    artifacts: TestArtifacts
    testcases: List[TestCase]
    engineMetadata: Dict[str, Any] = Field(default_factory=dict)
    timingMetrics: Dict[str, Any] = Field(default_factory=dict)


@app.get("/health")
def health():
    return {"status": "ok", "service": "ai-service"}


ALLOWED_METHODS = [
    "EP",
    "BVA",
    "Combinatorial",
    "StateTransition",
    "DecisionTable",
]

PROMPT_VERSION = "autotestdesign-v6-fr-complete"
ENABLE_PARSE_FALLBACK = os.getenv("ENABLE_PARSE_FALLBACK", "false").strip().lower() == "true"

TARGET_APP_CONTEXT = (
    "Target application is FitnessAI: a real-time fitness assistant with MediaPipe Pose landmarks, "
    "/api/analytics/pose posture analysis, exercise state machines, training plans, record filtering, "
    "history/dashboard analytics, BMI and calorie estimation. All generated risks, test plans, "
    "coverage items and testcases must target FitnessAI, not the AutoTestDesign tool itself.\n"
)

ASSIGNMENT_TEST_DESIGN_GUIDANCE = (
    "Assignment-derived obligations for the LLM output: structure the imported FitnessAI requirements; "
    "identify coverage items and traceability for interactive designer review; assign risk score and "
    "priority to key target-application requirements; generate black-box testcases using at least "
    "equivalence partitioning, boundary value analysis and decision table testing; include state-transition "
    "modeling when behavior has states; synthesize concrete test oracles; and provide a structured JSON "
    "artifact that can be exported. Treat input/import capability and export UI capability as tool features "
    "already handled by AutoTestDesign, not as FitnessAI requirements to test.\n"
)

FITNESSAI_TEST_FOCUS = (
    "FitnessAI test focus: exerciseType valid/invalid classes for SQUAT, PUSHUP, PLANK and JUMPING_JACK; "
    "landmarks length and visibility boundaries including 32, 33 and 34 points; pose response fields "
    "count, score, feedback, state and angle; complete versus illegal state-machine cycles and cooldown; "
    "record filtering rule count < 3 && durationSeconds < 30; plan difficulty, set/rep/rest and skip-rest "
    "flows; dashboard refresh, activity distribution and calorie oracle using MET * weightKg * durationHours.\n"
)


def _compose_content(content: str, documents: List[Dict[str, str]]) -> str:
    chunks: List[str] = []

    if str(content).strip():
        chunks.append(f"[manual-input]\n{str(content).strip()}")

    for index, item in enumerate(documents or [], start=1):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", f"file-{index}"))
        text = str(item.get("content", "")).strip()
        doc_type = str(item.get("type", ""))
        if not text:
            continue
        header = f"[file-{index}] name={name}"
        if doc_type:
            header += f" type={doc_type}"
        chunks.append(f"{header}\n{text}")

    return "\n\n".join(chunks)


def build_prompt(source_type: str, content: str, prompt_mode: str = "default", custom_prompt: str = "") -> str:
    if prompt_mode == "custom" and str(custom_prompt).strip():
        return (
            f"{str(custom_prompt).strip()}\n\n"
            f"{TARGET_APP_CONTEXT}"
            f"{ASSIGNMENT_TEST_DESIGN_GUIDANCE}"
            "Output requirements (MUST follow):\n"
            "- Return JSON object only.\n"
            "- Include black-box testcases. Allowed methods: EP, BVA, Combinatorial, StateTransition, DecisionTable.\n"
            "- Include requirementsStructured, coverageItems, riskItems, stateModel, testSuiteOptimization, traceability.\n"
            "- Include testcases with fields: id, technique, designMethod, title, precondition, input, steps, expected, oracle, priority, traceability.\n"
            "- Keep testcase input values compact. Do not enumerate landmark objects; describe them as \"32/33/34 valid landmark objects\".\n"
            f"{FITNESSAI_TEST_FOCUS}"
            f"sourceType: {source_type}\n"
            f"content:\n{content[:6000]}"
        )

    return (
        "You are an expert software testing assistant for AutoTestDesign. "
        "Generate submission-ready testing artifacts for the chosen target application.\n"
        f"{TARGET_APP_CONTEXT}"
        f"{ASSIGNMENT_TEST_DESIGN_GUIDANCE}"
        "Use the provided content as the source of requirements; if details are missing, state assumptions.\n"
        "Testing techniques: black-box is required; include white-box modeling when asked. "
        "Allowed black-box methods: EP, BVA, Combinatorial, StateTransition, DecisionTable.\n"
        "Return JSON object only with this exact schema:\n"
        "{\n"
        '  "inputVariables": ["..."],\n'
        '  "equivalencePartitions": [{"id":"EP1","description":"...","type":"valid|invalid","expected":"..."}],\n'
        '  "boundaryValues": [{"field":"...","values":["..."],"rationale":"..."}],\n'
        '  "decisionTableRules": [{"conditions":"...","actions":"...","expected":"..."}],\n'
        '  "requirementsStructured": [{"id":"REQ-1","feature":"...","inputFields":["..."],"ranges":{},"conditions":["..."],"expectedAction":"..."}],\n'
        '  "coverageItems": ["..."],\n'
        '  "riskItems": [{"reqId":"REQ-1","impact":1,"likelihood":1,"riskScore":1,"priority":"high|medium|low","rationale":"..."}],\n'
        '  "stateModel": {"states":[],"transitions":[],"coverageCriterion":"all-states|all-transitions"},\n'
        '  "testSuiteOptimization": {"mode":"risk-first|minimize","optimizedSuite":["TC-..."],"removedCases":["TC-..."]},\n'
        '  "traceability": [{"reqId":"REQ-1","coverageItems":["..."],"testcases":["TC-..."]}],\n'
        '  "testcases": [{"id":"TC-BB-001","technique":"black-box","designMethod":"EP|BVA|Combinatorial|StateTransition|DecisionTable","title":"...","precondition":"...","input":"...","steps":"...","expected":"...","oracle":"...","priority":"high|medium|low","traceability":["REQ-..."]}],\n'
        '  "missingItems": ["unclear requirement ..."],\n'
        '  "assumptions": ["assumption ..."]\n'
        "}\n"
        "Constraints:\n"
        "1) Generate testcases.\n"
        "2) Cover all five black-box methods, at least one testcase each.\n"
        "3) Prefer concrete API-level or behavior-level checks for /api/analytics/pose, record saving, training plan and dashboard.\n"
        "4) Include edge cases and invalid inputs, especially landmark count 32/33/34 and record filtering count<3 & duration<30.\n"
        "5) Include risk score, priority and traceability from requirements to coverage items to testcases.\n"
        "6) IDs must be unique and stable.\n"
        "7) Strict JSON only: do not use Python/JavaScript expressions, list comprehensions, comments, trailing commas, or ellipsis. "
        "For repeated landmarks, write a descriptive string such as \"33 valid landmark objects\" instead of [{...} for _ in range(33)].\n"
        "8) Keep testcase input values compact. Do not enumerate landmark objects; describe them as "
        "\"32 valid landmark objects\", \"33 valid landmark objects\", or \"34 valid landmark objects\".\n"
        f"{FITNESSAI_TEST_FOCUS}"
        f"sourceType: {source_type}\n"
        f"content:\n{content[:6000]}"
    )


KNOWN_OUTPUT_KEYS = {
    "inputVariables",
    "equivalencePartitions",
    "boundaryValues",
    "decisionTableRules",
    "requirementsStructured",
    "coverageItems",
    "riskItems",
    "stateModel",
    "testSuiteOptimization",
    "traceability",
    "testcases",
    "missingItems",
    "assumptions",
}

KEY_ALIASES = {
    "testCases": "testcases",
    "test_cases": "testcases",
    "cases": "testcases",
    "requirements": "requirementsStructured",
    "structuredRequirements": "requirementsStructured",
    "coverage": "coverageItems",
    "risks": "riskItems",
    "riskAnalysis": "riskItems",
    "state_model": "stateModel",
    "suiteOptimization": "testSuiteOptimization",
    "testSuite": "testSuiteOptimization",
}

WRAPPER_KEYS = ("data", "artifacts", "artifact", "result", "output", "response")


def _payload_fragments(payload: Any) -> List[Any]:
    fragments = [payload]
    if not isinstance(payload, dict):
        return fragments

    for wrapper_key in WRAPPER_KEYS:
        wrapped = payload.get(wrapper_key)
        if isinstance(wrapped, (dict, list)):
            fragments.extend(_payload_fragments(wrapped))

    return fragments


def _merge_payloads(payloads: List[Any]):
    merged: Dict[str, Any] = {}
    for payload in payloads:
        for fragment in _payload_fragments(payload):
            if isinstance(fragment, list):
                if fragment and all(isinstance(item, dict) for item in fragment):
                    merged.setdefault("testcases", [])
                    merged["testcases"].extend(fragment)
                continue

            if not isinstance(fragment, dict):
                continue

            for key, value in fragment.items():
                canonical_key = KEY_ALIASES.get(key, key)
                if canonical_key not in KNOWN_OUTPUT_KEYS:
                    continue
                if isinstance(value, list):
                    merged.setdefault(canonical_key, [])
                    if isinstance(merged[canonical_key], list):
                        merged[canonical_key].extend(value)
                    else:
                        merged[canonical_key] = value
                elif isinstance(value, dict):
                    current = merged.get(canonical_key)
                    if isinstance(current, dict):
                        merged[canonical_key] = {**current, **value}
                    else:
                        merged[canonical_key] = value
                elif canonical_key not in merged:
                    merged[canonical_key] = value

    return merged or None


def _loads_json_candidate(candidate: str):
    candidate = str(candidate or "").strip()
    if not candidate:
        return None
    try:
        return json.loads(candidate)
    except Exception:
        pass

    repaired = _repair_json_candidate(candidate)
    if repaired != candidate:
        try:
            return json.loads(repaired)
        except Exception:
            return None

    return None


def _repair_json_candidate(candidate: str) -> str:
    repaired = str(candidate or "").strip()
    repaired = re.sub(r",\s*([}\]])", r"\1", repaired)
    repaired = re.sub(r"\bNone\b", "null", repaired)
    repaired = re.sub(r"\bTrue\b", "true", repaired)
    repaired = re.sub(r"\bFalse\b", "false", repaired)
    # Some LLMs put Python list comprehensions inside JSON examples.
    repaired = re.sub(
        r"\[\s*(\{[^][]*?\})\s+for\s+_\s+in\s+range\(\s*(\d+)\s*\)\s*\]",
        lambda match: f'["{match.group(2)} repeated objects: {match.group(1).replace(chr(34), chr(39))}"]',
        repaired,
        flags=re.DOTALL,
    )
    repaired = re.sub(
        r"\[\s*([\"'][^][]*?[\"'])\s+for\s+_\s+in\s+range\(\s*(\d+)\s*\)\s*\]",
        lambda match: f'["{match.group(2)} repeated values: {match.group(1).strip(chr(34)).strip(chr(39))}"]',
        repaired,
        flags=re.DOTALL,
    )
    return repaired


def _balanced_json_candidates(text: str) -> List[str]:
    candidates: List[str] = []
    stack: List[str] = []
    start = None
    in_string = False
    escape = False
    pairs = {"{": "}", "[": "]"}

    for index, char in enumerate(text):
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
            continue

        if char in pairs:
            if not stack:
                start = index
            stack.append(pairs[char])
            continue

        if stack and char == stack[-1]:
            stack.pop()
            if not stack and start is not None:
                candidates.append(text[start:index + 1])
                start = None

    return candidates


def _balanced_json_from(text: str, start: int):
    pairs = {"{": "}", "[": "]"}
    opening = text[start] if 0 <= start < len(text) else ""
    expected = pairs.get(opening)
    if not expected:
        return None

    stack = [expected]
    in_string = False
    escape = False
    for index in range(start + 1, len(text)):
        char = text[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
            continue
        if char in pairs:
            stack.append(pairs[char])
            continue
        if stack and char == stack[-1]:
            stack.pop()
            if not stack:
                return text[start:index + 1]

    return None


def _extract_keyed_json_fragments(text: str) -> List[Any]:
    # If the model response is truncated, the top-level object may be invalid while
    # earlier fields are still complete. Recover complete known fields by key.
    fragments: List[Any] = []
    key_pattern = "|".join(re.escape(key) for key in list(KNOWN_OUTPUT_KEYS) + list(KEY_ALIASES.keys()))
    for match in re.finditer(rf'"({key_pattern})"\s*:', text):
        key = KEY_ALIASES.get(match.group(1), match.group(1))
        index = match.end()
        while index < len(text) and text[index].isspace():
            index += 1
        if index >= len(text) or text[index] not in "[{":
            continue

        candidate = _balanced_json_from(text, index)
        parsed = _loads_json_candidate(candidate or "")
        if parsed is not None:
            fragments.append({key: parsed})
        elif key == "testcases" and text[index] == "[":
            items = _extract_complete_array_items(text, index)
            if items:
                fragments.append({key: items})

    return fragments


def _extract_complete_array_items(text: str, start: int) -> List[Any]:
    items: List[Any] = []
    index = start + 1
    while index < len(text):
        while index < len(text) and (text[index].isspace() or text[index] == ","):
            index += 1
        if index >= len(text) or text[index] == "]":
            break
        if text[index] not in "[{":
            index += 1
            continue

        candidate = _balanced_json_from(text, index)
        if not candidate:
            break
        parsed = _loads_json_candidate(candidate)
        if parsed is not None:
            items.append(parsed)
        index += len(candidate)

    return items


def _extract_json_object(text: str):
    # Models often return explanations plus several JSON blocks. Parse and merge all usable pieces.
    payloads: List[Any] = []
    seen_candidates = set()

    direct = _loads_json_candidate(text)
    if direct is not None:
        payloads.append(direct)
        seen_candidates.add(str(text or "").strip())

    for code_block in re.findall(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE):
        normalized_block = code_block.strip()
        seen_candidates.add(normalized_block)
        parsed = _loads_json_candidate(code_block)
        if parsed is not None:
            payloads.append(parsed)

    for candidate in _balanced_json_candidates(text):
        normalized_candidate = candidate.strip()
        if normalized_candidate in seen_candidates:
            continue
        seen_candidates.add(normalized_candidate)
        parsed = _loads_json_candidate(candidate)
        if parsed is not None:
            payloads.append(parsed)

    payloads.extend(_extract_keyed_json_fragments(text))

    merged = _merge_payloads(payloads)
    if isinstance(merged, dict):
        return merged

    return None


def _legacy_extract_json_object(text: str):
    # Kept for reference of the older single-object strategy.
    try:
        payload = json.loads(text)
        if isinstance(payload, dict):
            return payload
        return None
    except Exception:
        pass

    code_block = re.search(r"```json\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    if code_block:
        try:
            payload = json.loads(code_block.group(1))
            if isinstance(payload, dict):
                return payload
        except Exception:
            pass

    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        return None

    try:
        payload = json.loads(match.group(0))
        if isinstance(payload, dict):
            return payload
        return None
    except Exception:
        return None


def _extract_response_text(response: Any) -> str:
    # Preferred path for newer OpenAI SDK response shape.
    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    # Fallback path for chat.completions style responses.
    choices = getattr(response, "choices", None)
    if isinstance(choices, list) and choices:
        message = getattr(choices[0], "message", None)
        if message is not None:
            content = getattr(message, "content", "")
            if isinstance(content, str):
                return content.strip()

    return ""


def _call_llm(client: Any, model: str, prompt: str):
    # Newer SDK (responses API)
    if hasattr(client, "responses") and hasattr(client.responses, "create"):
        return client.responses.create(
            model=model,
            input=prompt,
            temperature=0.2,
        )

    # Older SDK / provider-compatible path (chat.completions API)
    if hasattr(client, "chat") and hasattr(client.chat, "completions") and hasattr(client.chat.completions, "create"):
        return client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a black-box software testing assistant."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
        )

    raise RuntimeError("Current OpenAI SDK does not support responses or chat.completions APIs")


def _normalize_cases(payload, source_type: str) -> List[TestCase]:
    normalized: List[TestCase] = []
    if not isinstance(payload, list):
        return normalized

    for i, item in enumerate(payload, start=1):
        if not isinstance(item, dict):
            continue

        method = str(item.get("designMethod", "EP")).strip()
        if method not in ALLOWED_METHODS:
            method = "EP"

        normalized.append(
            TestCase(
                id=str(item.get("id", f"TC-BB-{i:03d}")),
                technique="black-box",
                designMethod=method,
                title=str(item.get("title", f"黑盒测试用例 {i}")),
                precondition=str(item.get("precondition", "系统已启动并接口可访问")),
                input=str(item.get("input", f"sourceType={source_type}")),
                steps=str(item.get("steps", "提交请求并观察响应")),
                expected=str(item.get("expected", "系统行为符合规格说明")),
                oracle=str(item.get("oracle", "")),
                priority=str(item.get("priority", "medium")),
                traceability=[str(value) for value in item.get("traceability", []) if str(value).strip()],
            )
        )

    return normalized


def _normalize_artifacts(payload) -> TestArtifacts:
    if not isinstance(payload, dict):
        return TestArtifacts(
            inputVariables=[],
            equivalencePartitions=[],
            boundaryValues=[],
            decisionTableRules=[],
            missingItems=[],
            assumptions=[],
        )

    def _safe_list(name: str):
        value = payload.get(name, [])
        return value if isinstance(value, list) else []

    def _normalize_traceability(values: List[Any]) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        for item in values:
            if isinstance(item, dict):
                normalized.append(item)
                continue
            if isinstance(item, str):
                ref = item.strip()
                if ref:
                    normalized.append({"ref": ref})
        return normalized

    input_vars = [str(item) for item in _safe_list("inputVariables") if str(item).strip()]

    eq_partitions = []
    for item in _safe_list("equivalencePartitions"):
        if isinstance(item, dict):
            eq_partitions.append(
                {
                    "id": str(item.get("id", "EPX")),
                    "description": str(item.get("description", "")),
                    "type": str(item.get("type", "valid")),
                    "expected": str(item.get("expected", "")),
                }
            )

    bva_items = []
    for item in _safe_list("boundaryValues"):
        if isinstance(item, dict):
            values = item.get("values", [])
            bva_items.append(
                {
                    "field": str(item.get("field", "")),
                    "values": values if isinstance(values, list) else [str(values)],
                    "rationale": str(item.get("rationale", "")),
                }
            )

    dt_rules = []
    for item in _safe_list("decisionTableRules"):
        if isinstance(item, dict):
            dt_rules.append(
                {
                    "conditions": str(item.get("conditions", "")),
                    "actions": str(item.get("actions", "")),
                    "expected": str(item.get("expected", "")),
                }
            )

    missing_items = [str(item) for item in _safe_list("missingItems") if str(item).strip()]
    assumptions = [str(item) for item in _safe_list("assumptions") if str(item).strip()]

    return TestArtifacts(
        inputVariables=input_vars,
        equivalencePartitions=eq_partitions,
        boundaryValues=bva_items,
        decisionTableRules=dt_rules,
        missingItems=missing_items,
        assumptions=assumptions,
        requirementsStructured=_safe_list("requirementsStructured"),
        coverageItems=[str(item) for item in _safe_list("coverageItems") if str(item).strip()],
        riskItems=_safe_list("riskItems"),
        stateModel=payload.get("stateModel", {}) if isinstance(payload.get("stateModel", {}), dict) else {},
        testSuiteOptimization=payload.get("testSuiteOptimization", {}) if isinstance(payload.get("testSuiteOptimization", {}), dict) else {},
        traceability=_normalize_traceability(_safe_list("traceability")),
        testStrategies=_safe_list("testStrategies"),
        engineMetadata=payload.get("engineMetadata", {}) if isinstance(payload.get("engineMetadata", {}), dict) else {},
    )


def _has_artifact_content(artifacts: TestArtifacts) -> bool:
    return any(
        [
            artifacts.inputVariables,
            artifacts.equivalencePartitions,
            artifacts.boundaryValues,
            artifacts.decisionTableRules,
            artifacts.missingItems,
            artifacts.assumptions,
            artifacts.requirementsStructured,
            artifacts.coverageItems,
            artifacts.riskItems,
            artifacts.stateModel,
            artifacts.testSuiteOptimization,
            artifacts.traceability,
            artifacts.testStrategies,
        ]
    )


def _mock_cases(source_type: str, content: str) -> List[TestCase]:
    head = content[:120] if content else "No content provided"
    is_fitness = "fitness" in content.lower() or "姿势" in content or "运动" in content

    if is_fitness:
        return [
            TestCase(
                id="TC-BB-001",
                technique="black-box",
                designMethod="EP",
                title="EP-有效运动类型输入",
                precondition="系统已加载运动分析模块",
                input="exerciseType=SQUAT 且 landmarks 数组完整",
                steps="提交姿势分析请求",
                expected="返回 count、score、feedback 等字段且状态码 200",
                oracle="HTTP 200 且字段完整",
                priority="high",
            ),
            TestCase(
                id="TC-BB-002",
                technique="black-box",
                designMethod="BVA",
                title="BVA-关键点数量边界",
                precondition="接口可调用",
                input="landmarks 数量=0, 1, 32, 33, 34",
                steps="分别提交请求并记录响应",
                expected="33 个关键点正常，其余输入触发可解释错误",
                oracle="33 正常，其他返回 4xx 或错误码",
                priority="high",
            ),
            TestCase(
                id="TC-BB-003",
                technique="black-box",
                designMethod="Combinatorial",
                title="组合输入-运动类型 x 训练模式",
                precondition="支持自由模式与计划模式",
                input="exerciseType∈{SQUAT,PUSHUP,PLANK,JUMPING_JACK}, mode∈{free,plan}",
                steps="覆盖关键组合并调用相关接口",
                expected="每种组合均返回一致的数据结构且无 5xx",
                oracle="HTTP 200 且返回结构一致",
                priority="medium",
            ),
            TestCase(
                id="TC-BB-004",
                technique="black-box",
                designMethod="StateTransition",
                title="状态迁移-俯卧撑计数状态机",
                precondition="状态机初始为 UP",
                input="连续帧触发 UP→DESCENDING→DOWN→ASCENDING→UP",
                steps="按状态序列提交帧数据",
                expected="仅在完整动作循环后计数 +1，非法跃迁不计数",
                oracle="计数仅在完整循环后增加",
                priority="high",
            ),
            TestCase(
                id="TC-BB-005",
                technique="black-box",
                designMethod="DecisionTable",
                title="决策表-记录过滤规则",
                precondition="记录保存接口可用",
                input="次数<3 与 时长<30 秒的四种组合",
                steps="按决策表逐条提交记录",
                expected="仅满足有效规则的记录入库，其余被过滤",
                oracle="无效组合入库数为 0",
                priority="high",
            ),
            TestCase(
                id="TC-BB-006",
                technique="black-box",
                designMethod="EP",
                title="EP-非法运动类型输入",
                precondition="姿态分析接口可访问",
                input="exerciseType=YOGA 或空值，landmarks 数组完整",
                steps="提交非法运动类型并观察错误处理",
                expected="返回 4xx 或明确的非法运动类型错误，不进入分析器",
                oracle="响应不得为 5xx，错误信息包含 exerciseType",
                priority="medium",
                traceability=["REQ-POSE-001"],
            ),
            TestCase(
                id="TC-BB-007",
                technique="black-box",
                designMethod="BVA",
                title="BVA-记录过滤时长边界",
                precondition="用户记录保存接口可用",
                input="count=2, durationSeconds=29/30/31",
                steps="分别保存三条记录并查询历史记录",
                expected="29 秒且次数小于 3 的记录被过滤，30/31 秒记录可保留",
                oracle="历史记录数量和每日统计与过滤规则一致",
                priority="high",
                traceability=["REQ-REC-001"],
            ),
            TestCase(
                id="TC-BB-008",
                technique="black-box",
                designMethod="DecisionTable",
                title="决策表-计划模式难度与跳过休息",
                precondition="训练计划模式已启用",
                input="difficulty∈{easy,medium,hard}; skipRest∈{true,false}",
                steps="创建计划训练，完成一组后分别跳过或等待休息",
                expected="组数、次数和休息状态根据难度与 skipRest 正确迁移",
                oracle="当前组、剩余次数和休息计时器符合计划配置",
                priority="medium",
                traceability=["REQ-PLAN-001"],
            ),
            TestCase(
                id="TC-BB-009",
                technique="black-box",
                designMethod="Combinatorial",
                title="组合输入-用户档案 x 运动类型 x 时长",
                precondition="用户已配置体重并完成训练",
                input="weight∈{50,80}, exerciseType∈{SQUAT,PUSHUP,PLANK}, duration∈{60,600}",
                steps="保存不同组合的运动记录并刷新仪表盘",
                expected="卡路里、趋势图和运动类型分布按组合正确更新",
                oracle="卡路里近似满足 MET × 体重 × 时长小时",
                priority="medium",
                traceability=["REQ-DASH-001"],
            ),
            TestCase(
                id="TC-BB-010",
                technique="black-box",
                designMethod="StateTransition",
                title="状态迁移-深蹲非法短循环不计数",
                precondition="深蹲分析器状态已重置",
                input="连续帧序列 UP→DESCENDING→UP，未进入 DOWN",
                steps="提交缺少 DOWN 状态的短循环帧序列",
                expected="状态可回到 UP，但 count 不增加",
                oracle="count 保持初始值，feedback 提示动作未完成或深度不足",
                priority="high",
                traceability=["REQ-POSE-002"],
            ),
        ]

    return [
        TestCase(
            id="TC-BB-001",
            technique="black-box",
            designMethod="EP",
            title="等价类划分-有效输入",
            precondition="系统在线且接口可访问",
            input=f"sourceType={source_type}; data={head}",
            steps="提交有效输入并调用生成接口",
            expected="系统成功处理并返回正确结果",
            priority="high",
        ),
        TestCase(
            id="TC-BB-002",
            technique="black-box",
            designMethod="BVA",
            title="边界值分析-空输入",
            precondition="请求体格式合法",
            input="空字符串或缺失字段",
            steps="提交 content 为空的请求",
            expected="系统返回参数错误提示",
            priority="high",
        ),
        TestCase(
            id="TC-BB-003",
            technique="black-box",
            designMethod="DecisionTable",
            title="决策表-来源类型与内容联合约束",
            precondition="sourceType 支持 requirements 和 codebase",
            input="sourceType=codebase, content=短模块描述",
            steps="提交 codebase 场景请求并检查返回字段完整性",
            expected="返回至少 1 条包含输入/预期结果的测试用例",
            priority="medium",
        ),
    ]


def _mock_artifacts(content: str) -> TestArtifacts:
    is_fitness = "fitness" in content.lower() or "姿势" in content or "运动" in content
    if is_fitness:
        return TestArtifacts(
            inputVariables=[
                "exerciseType",
                "trainingMode",
                "landmarksCount",
                "repCount",
                "durationSeconds",
            ],
            equivalencePartitions=[
                {
                    "id": "EP1",
                    "description": "exerciseType 属于支持集合",
                    "type": "valid",
                    "expected": "请求处理成功",
                },
                {
                    "id": "EP2",
                    "description": "exerciseType 非法值或空值",
                    "type": "invalid",
                    "expected": "返回参数错误",
                },
            ],
            boundaryValues=[
                {
                    "field": "landmarksCount",
                    "values": [0, 1, 32, 33, 34],
                    "rationale": "33 为关键点理论边界",
                },
                {
                    "field": "durationSeconds",
                    "values": [29, 30, 31],
                    "rationale": "过滤规则边界",
                },
            ],
            decisionTableRules=[
                {
                    "conditions": "count<3 且 duration<30",
                    "actions": "过滤该记录",
                    "expected": "不写入数据库",
                },
                {
                    "conditions": "count>=3 或 duration>=30",
                    "actions": "接收该记录",
                    "expected": "记录可入库",
                },
            ],
            missingItems=["未明确输入字段单位与取值范围"],
            assumptions=["landmarks 由上游姿势识别模块保证格式"],
            requirementsStructured=[
                {
                    "id": "REQ-POSE-001",
                    "feature": "姿态分析",
                    "inputFields": ["exerciseType", "landmarks"],
                    "ranges": {"landmarks.length": "33"},
                    "conditions": ["exerciseType in supported"],
                    "expectedAction": "返回计数与评分字段",
                },
                {
                    "id": "REQ-POSE-002",
                    "feature": "状态机计数",
                    "inputFields": ["landmark frame sequence", "exerciseType"],
                    "ranges": {"stableFrames": ">=2", "cooldownFrames": "10"},
                    "conditions": ["完整动作循环", "非法短循环"],
                    "expectedAction": "仅完整循环计数，非法跃迁不计数",
                },
                {
                    "id": "REQ-REC-001",
                    "feature": "运动记录过滤",
                    "inputFields": ["count", "durationSeconds"],
                    "ranges": {"count": ">=0", "durationSeconds": ">=0"},
                    "conditions": ["count < 3 and durationSeconds < 30"],
                    "expectedAction": "无效记录不入库，有效记录进入历史与统计",
                },
                {
                    "id": "REQ-PLAN-001",
                    "feature": "训练计划模式",
                    "inputFields": ["difficulty", "skipRest"],
                    "ranges": {"difficulty": "easy|medium|hard"},
                    "conditions": ["完成一组", "跳过休息"],
                    "expectedAction": "生成对应组数、次数和休息流程",
                },
                {
                    "id": "REQ-DASH-001",
                    "feature": "仪表盘统计",
                    "inputFields": ["weight", "exerciseType", "durationSeconds"],
                    "ranges": {"weight": ">0", "durationSeconds": ">0"},
                    "conditions": ["存在有效训练记录"],
                    "expectedAction": "展示趋势、卡路里和运动分布",
                },
            ],
            coverageItems=["姿态分析接口", "运动类型等价类", "关键点数量边界", "状态迁移", "记录过滤决策表", "计划模式组合", "仪表盘卡路里预言"],
            riskItems=[
                {
                    "reqId": "REQ-POSE-001",
                    "impact": 5,
                    "likelihood": 4,
                    "riskScore": 20,
                    "priority": "high",
                    "rationale": "核心功能且算法复杂",
                },
                {
                    "reqId": "REQ-POSE-002",
                    "impact": 5,
                    "likelihood": 4,
                    "riskScore": 20,
                    "priority": "high",
                    "rationale": "状态机错误会导致重复计数或漏计数",
                },
                {
                    "reqId": "REQ-REC-001",
                    "impact": 4,
                    "likelihood": 3,
                    "riskScore": 12,
                    "priority": "medium",
                    "rationale": "过滤规则错误会污染训练统计",
                },
                {
                    "reqId": "REQ-DASH-001",
                    "impact": 3,
                    "likelihood": 3,
                    "riskScore": 9,
                    "priority": "medium",
                    "rationale": "统计错误影响用户反馈和目标追踪",
                },
            ],
            stateModel={
                "states": ["UP", "DESCENDING", "DOWN", "ASCENDING", "COOLDOWN"],
                "transitions": [
                    {"from": "UP", "to": "DESCENDING", "condition": "angle begins decreasing"},
                    {"from": "DESCENDING", "to": "DOWN", "condition": "angle < threshold for stable frames"},
                    {"from": "DOWN", "to": "ASCENDING", "condition": "angle begins increasing"},
                    {"from": "ASCENDING", "to": "UP", "condition": "angle returns above threshold and count +1"},
                    {"from": "UP", "to": "COOLDOWN", "condition": "counted movement enters cooldown"},
                ],
                "coverageCriterion": "all-states",
            },
            testSuiteOptimization={
                "mode": "risk-first",
                "optimizedSuite": ["TC-BB-001", "TC-BB-002", "TC-BB-004", "TC-BB-005", "TC-BB-007", "TC-BB-010"],
                "removedCases": [],
            },
            traceability=[
                {
                    "reqId": "REQ-POSE-001",
                    "coverageItems": ["姿态分析接口", "运动类型等价类", "关键点数量边界"],
                    "testcases": ["TC-BB-001", "TC-BB-002", "TC-BB-006"],
                },
                {
                    "reqId": "REQ-POSE-002",
                    "coverageItems": ["状态迁移"],
                    "testcases": ["TC-BB-004", "TC-BB-010"],
                },
                {
                    "reqId": "REQ-REC-001",
                    "coverageItems": ["记录过滤决策表"],
                    "testcases": ["TC-BB-005", "TC-BB-007"],
                },
                {
                    "reqId": "REQ-PLAN-001",
                    "coverageItems": ["计划模式组合"],
                    "testcases": ["TC-BB-003", "TC-BB-008"],
                },
                {
                    "reqId": "REQ-DASH-001",
                    "coverageItems": ["仪表盘卡路里预言"],
                    "testcases": ["TC-BB-009"],
                },
            ],
        )

    return TestArtifacts(
        inputVariables=["sourceType", "contentLength"],
        equivalencePartitions=[
            {
                "id": "EP1",
                "description": "sourceType=requirements 且 content 非空",
                "type": "valid",
                "expected": "返回黑盒测试用例",
            },
            {
                "id": "EP2",
                "description": "content 为空",
                "type": "invalid",
                "expected": "返回参数错误",
            },
        ],
        boundaryValues=[
            {
                "field": "contentLength",
                "values": [0, 1, 500, 4000],
                "rationale": "覆盖空输入和截断边界",
            }
        ],
        decisionTableRules=[
            {
                "conditions": "sourceType 合法且 content 非空",
                "actions": "调用 LLM 生成",
                "expected": "返回结构化用例",
            }
        ],
        missingItems=[],
        assumptions=["输入文本可映射为可观察行为"],
        requirementsStructured=[],
        coverageItems=[],
        riskItems=[],
        stateModel={},
        testSuiteOptimization={},
        traceability=[],
    )


def _cases_to_markdown(cases: List[TestCase]) -> str:
    lines = [
        "# 自动化测试用例 Markdown 预览",
        "",
        "| ID | 设计方法 | 标题 | 优先级 | 预期结果 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in cases:
        title = str(item.title).replace("|", "\\|")
        expected = str(item.expected).replace("|", "\\|")
        lines.append(f"| {item.id} | {item.designMethod} | {title} | {item.priority} | {expected} |")

    lines.extend(["", "## 详细步骤", ""])
    for item in cases:
        lines.append(f"### {item.id} {item.title}")
        lines.append(f"- 前置条件: {item.precondition}")
        lines.append(f"- 输入: {item.input}")
        lines.append(f"- 步骤: {item.steps}")
        lines.append(f"- 预期: {item.expected}")
        if item.oracle:
            lines.append(f"- 预言: {item.oracle}")
        lines.append("")
    return "\n".join(lines)


def _finalize_generation(
    source_type: str,
    merged_content: str,
    model: str,
    prompt_used: str,
    llm_raw: str,
    llm_artifacts: Dict[str, Any],
    llm_cases: List[TestCase],
    include_whitebox: bool,
    include_oracle: bool,
    include_optimization: bool,
    coverage_criterion: str,
    whitebox_description: str = "",
    llm_ms: int = 0,
    llm_validation: Dict[str, Any] | None = None,
) -> GenerateResponse:
    engine = run_deterministic_pipeline(
        merged_content,
        include_whitebox=include_whitebox,
        include_oracle=include_oracle,
        include_optimization=include_optimization,
        coverage_criterion=coverage_criterion,
        whitebox_description=whitebox_description,
    )
    llm_artifact_dict = llm_artifacts if isinstance(llm_artifacts, dict) else {}
    llm_case_dicts = [item.model_dump() if hasattr(item, "model_dump") else dict(item) for item in llm_cases]
    merged_artifacts, merged_case_dicts = merge_engine_with_llm(engine, llm_artifact_dict, llm_case_dicts)
    merged_cases = _normalize_cases(merged_case_dicts, source_type)
    meta = merged_artifacts.get("engineMetadata", engine.get("engineMetadata", {}))
    if llm_validation:
        meta["llmValidation"] = llm_validation
    merged_artifacts["engineMetadata"] = meta
    engine_ms = int(meta.get("engineMs") or engine.get("timingMetrics", {}).get("engineMs") or 0)
    total_ms = engine_ms + int(llm_ms or 0)
    timing = {
        "engineMs": engine_ms,
        "llmMs": int(llm_ms or 0),
        "totalMs": total_ms,
        "engineMeetsNfr": engine_ms <= 2000,
        "note": "NFR target 2s applies to deterministic engine; LLM adds variable latency.",
    }
    merged_artifacts["timingMetrics"] = timing
    artifacts = _normalize_artifacts(merged_artifacts)
    if include_oracle:
        from app.engines.oracle_engine import attach_oracles

        case_dicts = [c.model_dump() for c in merged_cases]
        enriched = attach_oracles(case_dicts, merged_artifacts.get("requirementsStructured", []))
        merged_cases = _normalize_cases(enriched, source_type)

    return GenerateResponse(
        model=model,
        testTechnique="black-box",
        promptVersion=PROMPT_VERSION,
        promptUsed=prompt_used,
        llmRawOutput=llm_raw or _cases_to_markdown(merged_cases),
        artifacts=artifacts,
        testcases=merged_cases,
        engineMetadata=meta,
        timingMetrics=timing,
    )


def _mock_response(
    source_type: str,
    merged_content: str,
    reason: str = "mock-fallback",
    req: GenerateRequest | None = None,
) -> GenerateResponse:
    mock_cases = _mock_cases(source_type, merged_content)
    mock_artifacts = _mock_artifacts(merged_content)
    artifact_dict = mock_artifacts.model_dump() if hasattr(mock_artifacts, "model_dump") else {}
    include_whitebox = bool(req.includeWhitebox) if req is not None else True
    include_oracle = bool(req.includeOracle) if req is not None else True
    include_optimization = bool(req.includeOptimization) if req is not None else True
    coverage = str(req.coverageCriterion if req else "all-states")
    wb = str(req.whiteboxDescription if req else "")
    return _finalize_generation(
        source_type,
        merged_content,
        "mock+engine",
        reason,
        _cases_to_markdown(mock_cases),
        artifact_dict,
        mock_cases,
        include_whitebox,
        include_oracle,
        include_optimization,
        coverage,
        wb,
        0,
        {"passed": True, "source": "mock"},
    )


@app.get("/api/risk-matrix")
def risk_matrix():
    return {"message": "Configurable risk matrix for FR 2.0", "matrix": export_risk_matrix()}


class ExportArtifactsRequest(BaseModel):
    format: str = "json"
    artifacts: Dict[str, Any] = Field(default_factory=dict)
    testcases: List[Dict[str, Any]] = Field(default_factory=list)


@app.post("/export-artifacts")
def export_artifacts(req: ExportArtifactsRequest):
    fmt = str(req.format or "json").lower()
    if fmt in ("xlsx", "excel"):
        data = build_xlsx_bytes(req.artifacts, req.testcases)
        return Response(
            content=data,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=autotestdesign-artifacts.xlsx"},
        )
    return {"message": "Artifacts export", "artifacts": req.artifacts, "testcases": req.testcases}


@app.get("/prompt-template")
def prompt_template():
    return {
        "promptVersion": PROMPT_VERSION,
        "allowedMethods": ALLOWED_METHODS,
        "templatePreview": build_prompt("requirements", "<requirement_text_or_codebase_desc>"),
    }


@app.post("/generate-testcases", response_model=GenerateResponse)
def generate_testcases(req: GenerateRequest):
    merged_content = _compose_content(req.content, req.documents)
    include_whitebox = bool(req.includeWhitebox)
    include_oracle = bool(req.includeOracle)
    include_optimization = bool(req.includeOptimization)
    coverage_criterion = str(req.coverageCriterion or "all-states")

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    model = os.getenv("OPENAI_MODEL", "deepseek-chat").strip()

    if not api_key or OpenAI is None:
        return _mock_response(req.sourceType, merged_content, "mock-fallback:no-api-key", req)

    base_url = os.getenv("OPENAI_BASE_URL", "").strip()
    if base_url:
        client = OpenAI(api_key=api_key, base_url=base_url)
    else:
        client = OpenAI(api_key=api_key)

    prompt = build_prompt(
        req.sourceType,
        merged_content,
        prompt_mode=str(req.promptMode or "default"),
        custom_prompt=str(req.customPrompt or ""),
    )
    if req.includeWhitebox or req.includeOracle or req.includeOptimization:
        prompt += (
            "\n\nAdditional requirements:\n"
            f"- includeWhitebox: {str(req.includeWhitebox)}\n"
            f"- includeOracle: {str(req.includeOracle)}\n"
            f"- includeOptimization: {str(req.includeOptimization)}\n"
            f"- whiteboxDescription: {str(req.whiteboxDescription)[:1000]}\n"
            f"- coverageCriterion: {str(req.coverageCriterion)}\n"
        )

    llm_started = time.perf_counter()
    try:
        response = _call_llm(client, model, prompt)
        text = _extract_response_text(response)
    except Exception as error:
        if os.getenv("DISABLE_LLM_FAILURE_FALLBACK", "false").strip().lower() != "true":
            return _mock_response(req.sourceType, merged_content, f"mock-fallback:llm-request-failed:{error}", req)
        raise HTTPException(status_code=502, detail=f"LLM request failed: {error}")

    if not text:
        if os.getenv("DISABLE_LLM_FAILURE_FALLBACK", "false").strip().lower() != "true":
            return _mock_response(req.sourceType, merged_content, "mock-fallback:llm-empty-content", req)
        raise HTTPException(status_code=502, detail="LLM returned empty content")

    llm_ms = int((time.perf_counter() - llm_started) * 1000)
    payload = _extract_json_object(text) or {}
    llm_valid, llm_issues = validate_llm_payload(payload if isinstance(payload, dict) else {})
    llm_validation = {"passed": llm_valid, "issues": llm_issues, "source": "schema_validator"}
    cases = _normalize_cases(payload.get("testcases", []), req.sourceType)
    artifacts = _normalize_artifacts(payload)
    if not cases and ENABLE_PARSE_FALLBACK:
        cases = _mock_cases(req.sourceType, merged_content)
    artifact_dict = artifacts.model_dump() if hasattr(artifacts, "model_dump") else {}
    if not _has_artifact_content(artifacts) and ENABLE_PARSE_FALLBACK:
        artifact_dict = _mock_artifacts(merged_content).model_dump()

    rendered_raw = _cases_to_markdown(cases) if ENABLE_PARSE_FALLBACK and not _extract_json_object(text) else text

    return _finalize_generation(
        req.sourceType,
        merged_content,
        model,
        prompt,
        rendered_raw,
        artifact_dict,
        cases,
        include_whitebox,
        include_oracle,
        include_optimization,
        coverage_criterion,
        str(req.whiteboxDescription or ""),
        llm_ms,
        llm_validation,
    )
