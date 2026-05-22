"""
blackbox_workers.py
===================
为 Map-Reduce 生成管线提供专属黑盒测试技术 LLM Worker。

每个 Worker 都：
1. 接收 GlobalContext（无需再次分析需求，直接读取已结构化数据）。
2. 注入专门针对该技术的 System Prompt（强制技术规范、输出格式）。
3. 调用 LLM 生成测试用例，并将原始响应解析为标准 JSON 列表。
4. 在 LLM 不可用（无 API Key）或调用失败时，优雅降级至确定性引擎输出。
5. 返回与 generation_pipeline.WorkerResult 兼容的数据结构。

支持的 Workers
--------------
    worker_ep_llm(ctx)              → EP（等价类划分）Worker
    worker_bva_llm(ctx)             → BVA（边界值分析，单缺陷假设 + 三点法）Worker
    worker_decision_table(ctx)      → DecisionTable(决策表) Worker
    worker_conbinatorial(ctx)       → Conbinatorial(pairwise) Worker
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

# ── 确定性引擎（LLM 降级时使用）──────────────────────────────────────────
from app.engines.blackbox_fallbacks import (
    build_boundary_values,
    build_equivalence_partitions,
    generate_bva_cases,
    generate_ep_cases,
    generate_decision_table_cases,
    build_decision_table_rules,
    generate_combinatorial_cases,
    _case_id,
)
from app.engines.worker_contract import WorkerResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 工具常量
# ---------------------------------------------------------------------------

WORKER_PROMPT_VERSION = "blackbox-workers-v1"

# 标准 JSON 输出 Schema（用例列表元素）
_CASE_SCHEMA_DOC = """\
{
  "id": "TC-EP-001",
  "technique": "black-box",
  "designMethod": "EP",
  "title": "简明中文用例标题",
  "precondition": "前置条件",
  "input": "具体输入值（不得使用省略号）",
  "steps": "测试步骤（单句或多句）",
  "expected": "预期结果（可观察行为）",
  "expected_result": "同 expected，供向后兼容",
  "oracle": "测试预言（如何自动化判定通过/失败）",
  "priority": "high | medium | low",
  "traceability": ["REQ-XXX-001"]
}"""

# 可接受的优先级值
_VALID_PRIORITIES = frozenset({"high", "medium", "low"})


# ---------------------------------------------------------------------------
# LLM 客户端工厂（复用 main.py 的环境变量约定）
# ---------------------------------------------------------------------------

def _make_llm_client() -> Optional[Any]:
    """
    从环境变量读取 OPENAI_API_KEY / OPENAI_BASE_URL，返回 OpenAI 客户端。
    若无 API Key 或 openai 包未安装，返回 None。
    """
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        from openai import OpenAI  # type: ignore[import]
    except ImportError:
        logger.warning("openai 包未安装，LLM Worker 将降级至确定性引擎。")
        return None

    base_url = os.getenv("OPENAI_BASE_URL", "").strip()
    if base_url:
        return OpenAI(api_key=api_key, base_url=base_url)
    return OpenAI(api_key=api_key)


def _llm_model() -> str:
    return os.getenv("OPENAI_MODEL", "deepseek-chat").strip()


# ---------------------------------------------------------------------------
# LLM 调用（兼容新旧 SDK / OpenAI-Compatible Provider）
# ---------------------------------------------------------------------------

def _call_llm_sync(client: Any, system_prompt: str, user_prompt: str) -> str:
    """
    同步调用 LLM，兼容 responses API 与 chat.completions API。
    返回原始文本；出错时返回空字符串。
    """
    model = _llm_model()
    full_prompt = f"{system_prompt}\n\n{user_prompt}"

    try:
        # 新版 SDK — responses API
        if hasattr(client, "responses") and hasattr(client.responses, "create"):
            response = client.responses.create(
                model=model,
                input=full_prompt,
                temperature=0.1,   # 低温度：确定性输出，减少格式漂移
            )
            return _extract_text(response)

        # 旧版 SDK / OpenAI-Compatible — chat.completions API
        if hasattr(client, "chat") and hasattr(client.chat.completions, "create"):
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_prompt},
                ],
                temperature=0.1,
            )
            return _extract_text(response)

    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM 调用失败: %s", exc)

    return ""


def _extract_text(response: Any) -> str:
    """从 OpenAI SDK response 对象中提取文本内容。"""
    # responses API
    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()
    # chat.completions API
    choices = getattr(response, "choices", None)
    if isinstance(choices, list) and choices:
        message = getattr(choices[0], "message", None)
        if message is not None:
            content = getattr(message, "content", "")
            if isinstance(content, str):
                return content.strip()
    return ""


# ---------------------------------------------------------------------------
# JSON 解析工具
# ---------------------------------------------------------------------------

def _parse_case_list(raw_text: str) -> List[Dict[str, Any]]:
    """
    从 LLM 输出中健壮地提取测试用例列表。

    优先级：
    1. 直接解析整个文本为 JSON 数组。
    2. 提取 ```json ... ``` 代码块。
    3. 提取首个平衡的 JSON 数组片段。
    4. 若外层是对象，尝试读取 testcases / cases 字段。
    """
    text = str(raw_text or "").strip()
    if not text:
        return []

    # 1. 直接数组
    parsed = _try_json(text)
    if isinstance(parsed, list):
        return parsed

    # 2. ```json 代码块
    for block in re.findall(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE):
        parsed = _try_json(block)
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict):
            for key in ("testcases", "cases", "results", "data"):
                if isinstance(parsed.get(key), list):
                    return parsed[key]

    # 3. 首个平衡 JSON 数组
    array_start = text.find("[")
    if array_start != -1:
        candidate = _balanced_extract(text, array_start, "[", "]")
        parsed = _try_json(candidate)
        if isinstance(parsed, list):
            return parsed

    # 4. 对象中的 testcases 字段
    parsed = _try_json(text)
    if isinstance(parsed, dict):
        for key in ("testcases", "cases", "results", "data"):
            if isinstance(parsed.get(key), list):
                return parsed[key]

    logger.warning("_parse_case_list: 无法从 LLM 输出中解析测试用例列表，返回空列表。")
    return []


def _try_json(text: str) -> Any:
    try:
        # 清理常见 LLM 格式错误
        text = re.sub(r",\s*([}\]])", r"\1", text)   # 尾部逗号
        text = re.sub(r"\bNone\b", "null",  text)
        text = re.sub(r"\bTrue\b", "true",  text)
        text = re.sub(r"\bFalse\b", "false", text)
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None


def _balanced_extract(text: str, start: int, open_ch: str, close_ch: str) -> str:
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            escape = not escape and ch == "\\"
            if not escape and ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
            continue
        if ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return text[start:]


# ---------------------------------------------------------------------------
# 用例正规化
# ---------------------------------------------------------------------------

def _normalize_case(
    raw: Dict[str, Any],
    index: int,
    technique_prefix: str,
    design_method: str,
    default_traceability: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    将 LLM 返回的原始 dict 正规化为标准测试用例格式。

    - 补全缺失字段为安全默认值。
    - 统一 id 格式，防止 LLM 生成重复或非法 ID。
    - 将 expected_result 别名映射至 expected。
    - 校验 priority 枚举值。
    """
    # ID 优先使用 LLM 给出的值，否则自动生成
    raw_id = str(raw.get("id", "")).strip()
    case_id = raw_id if raw_id else f"TC-{technique_prefix}-{index:03d}"

    # expected / expected_result 双字段兼容
    expected = (
        str(raw.get("expected") or raw.get("expected_result") or "").strip()
        or "系统行为符合规格说明"
    )

    priority = str(raw.get("priority", "medium")).strip().lower()
    if priority not in _VALID_PRIORITIES:
        priority = "medium"

    traceability = [
        str(t).strip()
        for t in (raw.get("traceability") or [])
        if str(t).strip()
    ]
    for key in ("reqId", "requirementId", "requirement_id"):
        value = str(raw.get(key, "")).strip()
        if value and value not in traceability:
            traceability.append(value)
    if not traceability and default_traceability:
        traceability = list(default_traceability)

    return {
        "id":           case_id,
        "technique":    "black-box",
        "designMethod": design_method,
        "title":        str(raw.get("title", f"{design_method} 测试用例 {index}")).strip(),
        "precondition": str(raw.get("precondition", "系统已启动并接口可访问")).strip(),
        "input":        str(raw.get("input", "")).strip(),
        "steps":        str(raw.get("steps", "提交请求并观察响应")).strip(),
        "expected":     expected,
        "oracle":       str(raw.get("oracle", "")).strip(),
        "priority":     priority,
        "traceability": traceability,
    }


def _normalize_case_list(
    raw_cases: List[Dict[str, Any]],
    technique_prefix: str,
    design_method: str,
    start_index: int = 1,
    default_traceability: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    result = []
    for i, raw in enumerate(raw_cases, start=start_index):
        if not isinstance(raw, dict):
            continue
        result.append(_normalize_case(raw, i, technique_prefix, design_method, default_traceability))
    return result


def _requirement_ids(ctx: Any) -> List[str]:
    return [
        str(req.get("id", "")).strip()
        for req in (getattr(ctx, "requirements_structured", []) or [])
        if str(req.get("id", "")).strip()
    ]


def _prompt_guidance(ctx: Any, technique: str) -> str:
    extra = getattr(ctx, "extra", {}) or {}
    technique_prompts = extra.get("techniquePrompts") if isinstance(extra.get("techniquePrompts"), dict) else {}
    global_prompt = str(extra.get("globalPrompt", "") or "").strip()
    technique_prompt = str(technique_prompts.get(technique, "") or "").strip()
    parts: List[str] = []
    if global_prompt:
        parts.append(f"Global user guidance:\n{global_prompt}")
    if technique_prompt:
        parts.append(f"{technique} specific user guidance:\n{technique_prompt}")
    if not parts:
        return ""
    return "\n\n=== User Guidance (secondary to technique rules) ===\n" + "\n\n".join(parts) + "\n"


def _attach_traceability(
    cases: List[Dict[str, Any]],
    requirements: List[Dict[str, Any]],
    *,
    fallback_all: bool = False,
) -> List[Dict[str, Any]]:
    req_ids = [str(req.get("id", "")).strip() for req in requirements if str(req.get("id", "")).strip()]
    if not req_ids:
        return cases

    for case in cases:
        existing = [str(t).strip() for t in (case.get("traceability") or []) if str(t).strip()]
        if existing:
            case["traceability"] = existing
            continue

        blob = " ".join(
            str(case.get(key, ""))
            for key in ("title", "input", "steps", "expected", "oracle")
        ).lower()
        matched: List[str] = []
        for req in requirements:
            req_id = str(req.get("id", "")).strip()
            feature = str(req.get("feature", "")).strip().lower()
            cond_text = " ".join(str(c) for c in (req.get("conditions") or [])).lower()
            if req_id and (req_id.lower() in blob or (feature and feature in blob) or (cond_text and cond_text in blob)):
                matched.append(req_id)

        if matched:
            case["traceability"] = list(dict.fromkeys(matched))
        elif len(req_ids) == 1:
            case["traceability"] = req_ids[:1]
        elif fallback_all:
            case["traceability"] = req_ids
    return cases


# ---------------------------------------------------------------------------
# ① EP Worker  —  等价类划分 (Equivalence Partitioning)
# ---------------------------------------------------------------------------

# ── System Prompt ─────────────────────────────────────────────────────────

_EP_SYSTEM_PROMPT = """\
You are a meticulous black-box test designer specialized EXCLUSIVELY in
Equivalence Partitioning (EP).

STRICT TECHNIQUE RULES — MANDATORY:
1. You MUST ONLY use the Equivalence Partitioning technique. Do NOT include
   boundary values, state transitions, decision tables, or any other technique.
2. For EACH input variable or constraint in the requirements:
   a. Identify at least one VALID equivalence class (representative value is
      accepted by the system).
   b. Identify at least one INVALID equivalence class (representative value
      should be rejected with a meaningful error).
   c. Select EXACTLY ONE representative value per class — do not test
      multiple values for the same class in a single test case.
3. Each test case targets ONE equivalence class only.
4. Assign designMethod = "EP" to every test case.

CONTEXT:
- The structured requirements below are ALREADY PARSED. Do NOT re-analyze raw
  text — read the provided JSON directly and generate test cases from it.
- Derive ALL domain knowledge (input variables, valid values, constraints,
  expected behaviours) strictly from the requirements JSON — do NOT assume
  or hard-code any application-specific constants.
- Prioritize high-risk requirements (higher riskScore = higher priority).

OUTPUT FORMAT — STRICT JSON ARRAY ONLY:
Return a JSON array. Each element MUST match this schema:
""" + _CASE_SCHEMA_DOC + """

HARD CONSTRAINTS:
- Output ONLY the JSON array. No prose, no markdown headers, no explanation
  outside the array.
- All string values must be in Chinese except field names and enum values.
- Do NOT use ellipsis (…), Python expressions, or list comprehensions inside
  JSON strings.
- IDs must be unique: TC-EP-001, TC-EP-002, …
- input field must contain the CONCRETE representative value (not a description
  of the class).
"""

# ── User Prompt 工厂 ──────────────────────────────────────────────────────

def _ep_user_prompt(ctx: GlobalContext) -> str:
    reqs_json  = json.dumps(ctx.requirements_structured, ensure_ascii=False, indent=2)
    risks_json = json.dumps(ctx.risk_items,               ensure_ascii=False, indent=2)
    return (
        "Below are the already-structured requirements and risk items."
        " DO NOT re-parse them — use them directly.\n\n"
        f"=== Structured Requirements (authoritative) ===\n{reqs_json}\n\n"
        f"=== Risk Items (use for priority assignment) ===\n{risks_json}\n\n"
        "Task:\n"
        "Generate ONE test case per equivalence class (valid AND invalid) for each "
        "requirement. Follow the EP System Prompt rules strictly.\n"
        f"{_prompt_guidance(ctx, 'EP')}"
        "Return ONLY the JSON array of test cases."
    )


# ── Worker 主函数 ─────────────────────────────────────────────────────────

async def worker_ep_llm(
    ctx: GlobalContext,
    start_index: int = 1,
) -> WorkerResult:
    """
    EP Worker：调用 LLM 生成等价类划分测试用例。

    降级策略
    --------
    - LLM 不可用（无 API Key）→ 调用 generate_ep_cases() 确定性引擎
    - LLM 返回空内容        → 同上
    - LLM 返回无效 JSON     → 同上，并记录 warning
    """
    t0 = time.perf_counter()
    client = _make_llm_client()

    # ── 降级：无 LLM 客户端 ──────────────────────────────────────────────
    if client is None:
        logger.info("worker_ep_llm: no LLM client, falling back to deterministic engine.")
        return await _ep_deterministic_fallback(ctx, start_index, t0, reason="no-llm-client")

    # ── LLM 调用（在线程池中同步运行，避免阻塞 event loop）─────────────
    system_prompt = _EP_SYSTEM_PROMPT
    user_prompt   = _ep_user_prompt(ctx)

    try:
        raw_text = await asyncio.get_event_loop().run_in_executor(
            None,
            _call_llm_sync,
            client, system_prompt, user_prompt,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("worker_ep_llm: LLM executor failed: %s", exc)
        return await _ep_deterministic_fallback(ctx, start_index, t0, reason=f"executor-error:{exc}")

    # ── 解析 LLM 输出 ────────────────────────────────────────────────────
    if not raw_text:
        logger.warning("worker_ep_llm: LLM returned empty text, falling back.")
        return await _ep_deterministic_fallback(ctx, start_index, t0, reason="llm-empty")

    raw_cases = _parse_case_list(raw_text)
    if not raw_cases:
        logger.warning("worker_ep_llm: could not parse case list from LLM output, falling back.")
        return await _ep_deterministic_fallback(ctx, start_index, t0, reason="parse-failed")

    # ── 正规化 ───────────────────────────────────────────────────────────
    cases = _normalize_case_list(raw_cases, "EP", "EP", start_index, _requirement_ids(ctx))
    eq_partitions = build_equivalence_partitions(ctx.requirements_structured)

    logger.info("worker_ep_llm: generated %d EP cases via LLM.", len(cases))
    return WorkerResult(
        technique="EP",
        testcases=cases,
        artifacts={
            "equivalencePartitions": eq_partitions,
            "workerSource": "llm",
            "promptVersion": WORKER_PROMPT_VERSION,
        },
        elapsed_ms=int((time.perf_counter() - t0) * 1000),
    )


async def _ep_deterministic_fallback(
    ctx: GlobalContext,
    start_index: int,
    t0: float,
    reason: str = "fallback",
) -> WorkerResult:
    """EP 降级：使用确定性引擎生成。"""
    cases, _ = generate_ep_cases(ctx.requirements_structured, start_index)
    eq_partitions = build_equivalence_partitions(ctx.requirements_structured)
    return WorkerResult(
        technique="EP",
        testcases=cases,
        artifacts={
            "equivalencePartitions": eq_partitions,
            "workerSource": f"deterministic-engine:{reason}",
        },
        elapsed_ms=int((time.perf_counter() - t0) * 1000),
    )


# ---------------------------------------------------------------------------
# ② BVA Worker  —  边界值分析 (Boundary Value Analysis)
# ---------------------------------------------------------------------------

# ── System Prompt ─────────────────────────────────────────────────────────

_BVA_SYSTEM_PROMPT = """\
You are a meticulous black-box test designer specialized EXCLUSIVELY in
Boundary Value Analysis (BVA).

STRICT TECHNIQUE RULES — MANDATORY:

A. THREE-POINT METHOD (三点法) — Apply for EVERY boundary of every numeric
   input domain found in the requirements:

   For each boundary point B (either the minimum valid value or the maximum
   valid value of a domain), generate THREE separate test cases:
     1. B - 1  (one step BELOW the boundary) — typically INVALID
     2. B       (the boundary value itself)   — typically VALID
     3. B + 1  (one step ABOVE the boundary) — valid or invalid depending
                                                on whether B is min or max

   Concretely, for a valid domain [min, max]:
     Lower boundary cluster → test: min-1 (invalid), min (valid), min+1 (valid)
     Upper boundary cluster → test: max-1 (valid),  max (valid), max+1 (invalid)

   Each of these SIX points is a SEPARATE test case.
   If min == max (single-point domain), collapse to three points: min-1, min, min+1.

B. SINGLE FAULT ASSUMPTION (单缺陷假设) — CRITICAL RULE:
   When testing an INVALID boundary (e.g., min-1 or max+1):
   - ONLY ONE variable is allowed to be outside its valid domain at a time.
   - ALL other variables in the same test case MUST be set to their most
     representative VALID value (typically the nominal/midpoint value).
   - NEVER let two variables be simultaneously invalid in one test case.

C. SCOPE:
   - Only apply BVA to numeric inputs, string-length constraints, or count/
     duration thresholds found in the PROVIDED REQUIREMENTS JSON below.
   - Derive ALL boundary values strictly from the requirements JSON — do NOT
     assume or hard-code any domain-specific constants.
   - Do NOT use EP, state transitions, decision tables, or other techniques.
   - Assign designMethod = "BVA" to every test case.

OUTPUT FORMAT — STRICT JSON ARRAY ONLY:
Return a JSON array. Each element MUST match this schema:
""" + _CASE_SCHEMA_DOC + """

HARD CONSTRAINTS:
- Output ONLY the JSON array. No prose, no markdown, no explanation outside
  the array.
- All string values must be in Chinese except field names and enum values.
- input field must specify which variable is at the boundary value AND list all
  other variables at their valid nominal values.
- Each test case tests EXACTLY ONE boundary point of EXACTLY ONE variable.
- IDs must be unique: TC-BVA-001, TC-BVA-002, …
- Do NOT use ellipsis (…), Python expressions, or list comprehensions inside
  JSON strings.
"""

# ── User Prompt 工厂 ──────────────────────────────────────────────────────

def _bva_user_prompt(ctx: GlobalContext) -> str:
    reqs_json  = json.dumps(ctx.requirements_structured, ensure_ascii=False, indent=2)
    risks_json = json.dumps(ctx.risk_items,               ensure_ascii=False, indent=2)
    return (
        "Below are the already-structured requirements and risk items."
        " DO NOT re-parse them — use them directly.\n\n"
        f"=== Structured Requirements (authoritative) ===\n{reqs_json}\n\n"
        f"=== Risk Items (use for priority assignment) ===\n{risks_json}\n\n"
        "Task:\n"
        "Apply the BVA technique (three-point method + Single Fault Assumption) "
        "to every numeric input domain found in the requirements above.\n"
        "For each boundary point, generate ONE test case.\n"
        "Remember: when a variable is at an invalid boundary, ALL other variables "
        "in the same test case MUST be at their valid nominal values.\n"
        f"{_prompt_guidance(ctx, 'BVA')}"
        "Return ONLY the JSON array of test cases."
    )


# ── Worker 主函数 ─────────────────────────────────────────────────────────

async def worker_bva_llm(
    ctx: GlobalContext,
    start_index: int = 1,
) -> WorkerResult:
    """
    BVA Worker：调用 LLM 生成边界值分析测试用例。

    System Prompt 强制执行：
    - 三点法（min / min-1 / max）
    - 单缺陷假设（每次只让一个变量越界）

    降级策略与 worker_ep_llm 相同。
    """
    t0 = time.perf_counter()
    client = _make_llm_client()

    # ── 降级：无 LLM 客户端 ──────────────────────────────────────────────
    if client is None:
        logger.info("worker_bva_llm: no LLM client, falling back to deterministic engine.")
        return await _bva_deterministic_fallback(ctx, start_index, t0, reason="no-llm-client")

    # ── LLM 调用 ────────────────────────────────────────────────────────
    system_prompt = _BVA_SYSTEM_PROMPT
    user_prompt   = _bva_user_prompt(ctx)

    try:
        raw_text = await asyncio.get_event_loop().run_in_executor(
            None,
            _call_llm_sync,
            client, system_prompt, user_prompt,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("worker_bva_llm: LLM executor failed: %s", exc)
        return await _bva_deterministic_fallback(ctx, start_index, t0, reason=f"executor-error:{exc}")

    # ── 解析 LLM 输出 ────────────────────────────────────────────────────
    if not raw_text:
        logger.warning("worker_bva_llm: LLM returned empty text, falling back.")
        return await _bva_deterministic_fallback(ctx, start_index, t0, reason="llm-empty")

    raw_cases = _parse_case_list(raw_text)
    if not raw_cases:
        logger.warning("worker_bva_llm: could not parse case list from LLM output, falling back.")
        return await _bva_deterministic_fallback(ctx, start_index, t0, reason="parse-failed")

    # ── 后校验：单缺陷假设守卫 ──────────────────────────────────────────
    # 仅记录 warning，不丢弃用例（LLM 经过 Prompt 约束后大概率符合规则）
    _single_fault_guard(raw_cases)

    # ── 正规化 ───────────────────────────────────────────────────────────
    cases = _normalize_case_list(raw_cases, "BVA", "BVA", start_index, _requirement_ids(ctx))
    bv_items = build_boundary_values(ctx.requirements_structured)

    logger.info("worker_bva_llm: generated %d BVA cases via LLM.", len(cases))
    return WorkerResult(
        technique="BVA",
        testcases=cases,
        artifacts={
            "boundaryValues": bv_items,
            "workerSource": "llm",
            "promptVersion": WORKER_PROMPT_VERSION,
        },
        elapsed_ms=int((time.perf_counter() - t0) * 1000),
    )


async def _bva_deterministic_fallback(
    ctx: GlobalContext,
    start_index: int,
    t0: float,
    reason: str = "fallback",
) -> WorkerResult:
    """BVA 降级：使用确定性引擎生成。"""
    cases, _ = generate_bva_cases(ctx.requirements_structured, start_index)
    bv_items = build_boundary_values(ctx.requirements_structured)
    return WorkerResult(
        technique="BVA",
        testcases=cases,
        artifacts={
            "boundaryValues": bv_items,
            "workerSource": f"deterministic-engine:{reason}",
        },
        elapsed_ms=int((time.perf_counter() - t0) * 1000),
    )


# ---------------------------------------------------------------------------
# 单缺陷假设后校验守卫
# ---------------------------------------------------------------------------

# 常见无效值关键词 —— 若 input 字段包含多个此类词汇则视为可疑
_INVALID_KEYWORDS = frozenset({
    "invalid", "illegal", "非法", "无效", "错误",
    "超出", "越界", "null", "none", "undefined", "empty", "空",
})

def _single_fault_guard(raw_cases: List[Dict[str, Any]]) -> None:
    """
    启发式检查 BVA 用例是否违反单缺陷假设。
    若 input 字段中出现超过 1 个"无效值指示词"，则发出 warning。
    这是尽力而为的检查，不会丢弃或修改用例。
    """
    for i, case in enumerate(raw_cases, start=1):
        input_text = str(case.get("input", "")).lower()
        hit_count = sum(1 for kw in _INVALID_KEYWORDS if kw in input_text)
        if hit_count >= 2:
            logger.warning(
                "单缺陷假设可能违反（BVA 用例 #%d '%s'）: input 字段包含 %d 个无效值指示词。"
                " 请人工复核该用例是否同时让多个变量越界。input=%r",
                i, case.get("title", ""), hit_count, case.get("input", ""),
            )


# ---------------------------------------------------------------------------
# 便捷导出：供 generation_pipeline._TECHNIQUE_WORKER_MAP 替换默认 Worker
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# ③ DecisionTable Worker  —  决策表 (Decision Table)
# ---------------------------------------------------------------------------

_DT_SYSTEM_PROMPT = """\
You are an expert black-box test designer specializing in Decision Table Testing.

Your task is to extract independent business rules from the given structured requirements.
A "Rule" in a decision table consists of:
- conditions: The combination of conditions that trigger the action.
- actions: The actions to be taken when the conditions are met.
- expected: The expected result of taking the action.

STRICT RULES:
- Output ONLY a JSON array of rule objects.
- Each object must have exactly these keys: "conditions", "actions", "expected".
- All values should be strings in Chinese (except if the original requirement is in English or for enums).
- Do not output any explanation, markdown formatting outside the JSON block, or prose.

Example:
[
  {
    "conditions": "count<3, duration<30",
    "actions": "过滤记录",
    "expected": "不写入数据库"
  }
]
"""

def _dt_user_prompt(ctx: GlobalContext) -> str:
    reqs_json = json.dumps(ctx.requirements_structured, ensure_ascii=False, indent=2)
    return (
        "Below are the structured requirements:\n\n"
        f"{reqs_json}\n\n"
        f"{_prompt_guidance(ctx, 'DecisionTable')}"
        "Extract the decision table rules. Return ONLY the JSON array of rule objects."
    )

async def worker_decision_table_llm(ctx: GlobalContext, start_index: int = 1) -> WorkerResult:
    t0 = time.perf_counter()
    client = _make_llm_client()

    if client is None:
        logger.info("worker_decision_table_llm: no LLM client, falling back.")
        return await _dt_deterministic_fallback(ctx, start_index, t0, "no-llm-client")

    system_prompt = _DT_SYSTEM_PROMPT
    user_prompt = _dt_user_prompt(ctx)

    try:
        raw_text = await asyncio.get_event_loop().run_in_executor(
            None, _call_llm_sync, client, system_prompt, user_prompt
        )
    except Exception as exc:
        logger.warning("worker_decision_table_llm: LLM executor failed: %s", exc)
        return await _dt_deterministic_fallback(ctx, start_index, t0, f"executor-error:{exc}")

    if not raw_text:
        return await _dt_deterministic_fallback(ctx, start_index, t0, "llm-empty")

    rules = _try_json(_balanced_extract(raw_text, raw_text.find("["), "[", "]") if "[" in raw_text else raw_text)
    if not isinstance(rules, list):
        rules = _parse_case_list(raw_text) # fallback parsing

    if not rules or not isinstance(rules, list):
        logger.warning("worker_decision_table_llm: could not parse rules, falling back.")
        return await _dt_deterministic_fallback(ctx, start_index, t0, "parse-failed")

    # Clean rules
    clean_rules = []
    for r in rules:
        if isinstance(r, dict):
            clean_rules.append({
                "conditions": str(r.get("conditions", "")),
                "actions": str(r.get("actions", "")),
                "expected": str(r.get("expected", ""))
            })

    if not clean_rules:
        return await _dt_deterministic_fallback(ctx, start_index, t0, "no-valid-rules")

    cases, _ = generate_decision_table_cases(clean_rules, start_index)
    cases = _attach_traceability(cases, ctx.requirements_structured, fallback_all=True)
    
    logger.info("worker_decision_table_llm: generated %d cases via LLM.", len(cases))
    return WorkerResult(
        technique="DecisionTable",
        testcases=cases,
        artifacts={
            "decisionTableRules": clean_rules,
            "workerSource": "llm",
            "promptVersion": WORKER_PROMPT_VERSION,
        },
        elapsed_ms=int((time.perf_counter() - t0) * 1000),
    )

async def _dt_deterministic_fallback(ctx: GlobalContext, start_index: int, t0: float, reason: str) -> WorkerResult:
    rules = build_decision_table_rules(ctx.requirements_structured)
    cases, _ = generate_decision_table_cases(rules, start_index)
    cases = _attach_traceability(cases, ctx.requirements_structured, fallback_all=True)
    return WorkerResult(
        technique="DecisionTable",
        testcases=cases,
        artifacts={"decisionTableRules": rules, "workerSource": f"deterministic-engine:{reason}"},
        elapsed_ms=int((time.perf_counter() - t0) * 1000),
    )


# ---------------------------------------------------------------------------
# ④ Combinatorial Worker  —  组合测试 (Combinatorial)
# ---------------------------------------------------------------------------

_CB_SYSTEM_PROMPT = """\
You are an expert black-box test designer specializing in Combinatorial / Pairwise Testing.

Your task is to extract a parameter dictionary from the given structured requirements.
This dictionary maps each factor (parameter name) to a list of its possible representative values (levels).

STRICT RULES:
- Output ONLY a JSON object.
- Keys are parameter names (e.g., "exerciseType", "difficulty").
- Values are lists of strings representing the possible values.
- Do not output any explanation, markdown formatting outside the JSON block, or prose.

Example:
{
  "exerciseType": ["SQUAT", "YOGA", "RUNNING"],
  "difficulty": ["easy", "medium", "hard"],
  "skipRest": ["true", "false"]
}
"""

def _cb_user_prompt(ctx: GlobalContext) -> str:
    reqs_json = json.dumps(ctx.requirements_structured, ensure_ascii=False, indent=2)
    return (
        "Below are the structured requirements:\n\n"
        f"{reqs_json}\n\n"
        f"{_prompt_guidance(ctx, 'Combinatorial')}"
        "Extract the parameters and their possible values. Return ONLY the JSON object."
    )

def _generate_cb_cases_with_allpairspy(
    param_dict: Dict[str, List[str]],
    start_index: int,
    traceability: Optional[List[str]] = None,
) -> Tuple[List[Dict[str, Any]], int]:
    try:
        from allpairspy import AllPairs
    except ImportError:
        logger.warning("allpairspy not installed, cannot use exact pairwise logic. Falling back to simple combinations.")
        return _generate_simple_cb_cases(param_dict, start_index, traceability)

    if not param_dict:
        return [], start_index

    # Prepare parameters for AllPairs
    pairs_source = [(key, values) for key, values in param_dict.items() if values]
    keys = [key for key, _ in pairs_source]
    values_list = [values for _, values in pairs_source]
    
    if len(values_list) < 2:
        # Pairwise requires at least 2 parameters
        if not values_list:
             return [], start_index
        # Just generate one case for each value of the single parameter
        cases = []
        idx = start_index
        for val in values_list[0]:
            input_desc = f"{keys[0]}={val}"
            cases.append({
                "id": _case_id("TC-CB", idx),
                "technique": "black-box",
                "designMethod": "Combinatorial",
                "title": f"组合测试-{input_desc}",
                "precondition": "相关模块已启用",
                "input": input_desc,
                "steps": "执行组合场景并记录结果",
                "expected": "返回一致数据结构且无 5xx",
                "oracle": "",
                "priority": "medium",
                "traceability": list(traceability or []),
            })
            idx += 1
        return cases, idx

    cases = []
    idx = start_index
    for i, pairs in enumerate(AllPairs(values_list)):
        combo = dict(zip(keys, pairs))
        input_desc = ", ".join(f"{key}={value}" for key, value in combo.items())
        cases.append({
            "id": _case_id("TC-CB", idx),
            "technique": "black-box",
            "designMethod": "Combinatorial",
            "title": f"Pairwise组合-{input_desc}",
            "precondition": "相关模块已启用",
            "input": input_desc,
            "steps": "执行组合场景并记录结果",
            "expected": "各组合返回一致数据结构且无 5xx",
            "oracle": "",
            "priority": "medium",
            "traceability": list(traceability or []),
        })
        idx += 1
    return cases, idx


def _generate_simple_cb_cases(
    param_dict: Dict[str, List[str]],
    start_index: int,
    traceability: Optional[List[str]] = None,
) -> Tuple[List[Dict[str, Any]], int]:
    keys = [key for key, values in param_dict.items() if values]
    if not keys:
        return [], start_index

    max_rows = max(len(values) for values in (param_dict[key] for key in keys))
    cases: List[Dict[str, Any]] = []
    idx = start_index
    for row_index in range(max_rows):
        combo = {
            key: param_dict[key][row_index % len(param_dict[key])]
            for key in keys
        }
        input_desc = ", ".join(f"{key}={value}" for key, value in combo.items())
        cases.append({
            "id": _case_id("TC-CB", idx),
            "technique": "black-box",
            "designMethod": "Combinatorial",
            "title": f"Pairwise组合-{input_desc}",
            "precondition": "相关模块已启用",
            "input": input_desc,
            "steps": "执行组合场景并记录结果",
            "expected": "各组合返回一致的数据结构且无 5xx",
            "oracle": "",
            "priority": "medium",
            "traceability": list(traceability or []),
        })
        idx += 1
    return cases, idx

async def worker_combinatorial_llm(ctx: GlobalContext, start_index: int = 1) -> WorkerResult:
    t0 = time.perf_counter()
    client = _make_llm_client()

    if client is None:
        logger.info("worker_combinatorial_llm: no LLM client, falling back.")
        return await _cb_deterministic_fallback(ctx, start_index, t0, "no-llm-client")

    system_prompt = _CB_SYSTEM_PROMPT
    user_prompt = _cb_user_prompt(ctx)

    try:
        raw_text = await asyncio.get_event_loop().run_in_executor(
            None, _call_llm_sync, client, system_prompt, user_prompt
        )
    except Exception as exc:
        logger.warning("worker_combinatorial_llm: LLM executor failed: %s", exc)
        return await _cb_deterministic_fallback(ctx, start_index, t0, f"executor-error:{exc}")

    if not raw_text:
        return await _cb_deterministic_fallback(ctx, start_index, t0, "llm-empty")

    param_dict = _try_json(_balanced_extract(raw_text, raw_text.find("{"), "{", "}") if "{" in raw_text else raw_text)
    if not isinstance(param_dict, dict):
         # Try to find json block
         for block in re.findall(r"```(?:json)?\s*([\s\S]*?)\s*```", raw_text, re.IGNORECASE):
             parsed = _try_json(block)
             if isinstance(parsed, dict):
                 param_dict = parsed
                 break

    if not param_dict or not isinstance(param_dict, dict):
        logger.warning("worker_combinatorial_llm: could not parse parameter dictionary, falling back.")
        return await _cb_deterministic_fallback(ctx, start_index, t0, "parse-failed")

    # Clean parameter dict
    clean_params = {}
    for k, v in param_dict.items():
        if isinstance(v, list) and v:
            clean_params[str(k)] = [str(x) for x in v]

    if not clean_params:
        return await _cb_deterministic_fallback(ctx, start_index, t0, "no-valid-params")

    cases, _ = _generate_cb_cases_with_allpairspy(clean_params, start_index, _requirement_ids(ctx))
    if not cases:
        return await _cb_deterministic_fallback(ctx, start_index, t0, "pairwise-empty")
    
    logger.info("worker_combinatorial_llm: generated %d cases via LLM.", len(cases))
    return WorkerResult(
        technique="Combinatorial",
        testcases=cases,
        artifacts={
            "workerSource": "llm",
            "promptVersion": WORKER_PROMPT_VERSION,
        },
        elapsed_ms=int((time.perf_counter() - t0) * 1000),
    )

async def _cb_deterministic_fallback(ctx: GlobalContext, start_index: int, t0: float, reason: str) -> WorkerResult:
    cases, _ = generate_combinatorial_cases(ctx.requirements_structured, start_index)
    cases = _attach_traceability(cases, ctx.requirements_structured, fallback_all=True)
    return WorkerResult(
        technique="Combinatorial",
        testcases=cases,
        artifacts={"workerSource": f"deterministic-engine:{reason}"},
        elapsed_ms=int((time.perf_counter() - t0) * 1000),
    )


#: 将这四个 LLM Worker 注册到 Router 映射表（可选，调用方决定是否启用）
LLM_WORKER_OVERRIDES: Dict[str, Any] = {
    "EP":  worker_ep_llm,
    "BVA": worker_bva_llm,
    "DecisionTable": worker_decision_table_llm,
    "Combinatorial": worker_combinatorial_llm,
}
