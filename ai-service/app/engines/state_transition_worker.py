"""
state_transition_worker.py
==========================
状态迁移测试（State Transition Testing）Map-Reduce Worker。

职责划分
--------
- **LLM 阶段**：阅读结构化需求，输出标准状态图 JSON（states + transitions）。
  LLM 只做信息提取，不生成测试用例。
- **图论遍历阶段**：使用 networkx 有向图，依据覆盖准则精确遍历：
    * 0-switch（all-transitions）：遍历有向图中的所有边。
      每条边 A→B 对应一条测试路径 [A, B]。
    * 1-switch（all-transition-pairs）：遍历所有连续边对（A→B, B→C）。
      对每条入边与出边的合法接续，生成路径 [A, B, C]。
- **用例构造**：将路径序列转换为标准 WorkerResult 格式的测试用例 dict。

降级策略（与 blackbox_workers 一致）
-------------------------------------
  无 API Key / LLM 调用失败 / 返回无效 JSON
    → 直接使用现有 state_model_engine.build_state_model 确定性状态机
    → 同样走 networkx 图论遍历，保证一致性

依赖
----
  networkx >= 3.x     （需在 requirements.txt 中声明）
  openai              （可选，降级时不需要）
  app.engines.state_model_engine.build_state_model  （降级 fallback）
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# networkx 导入（允许优雅降级：若未安装则使用纯 Python 备用逻辑）
# ---------------------------------------------------------------------------
try:
    import networkx as nx  # type: ignore[import]
    _HAS_NX = True
except ImportError:  # pragma: no cover
    nx = None  # type: ignore[assignment]
    _HAS_NX = False

from app.engines.worker_contract import WorkerResult
from app.engines.state_model_engine import build_state_model

logger = logging.getLogger(__name__)

WORKER_VERSION = "st-worker-v1"


# ===========================================================================
# 第一阶段：LLM 提取状态图 JSON
# ===========================================================================

# ── System Prompt ──────────────────────────────────────────────────────────

_ST_EXTRACT_SYSTEM_PROMPT = """\
You are a software test analyst specializing in state machine modeling.

TASK: Read the provided structured requirements and extract a COMPLETE state
diagram in JSON format.

OUTPUT RULES — STRICT:
1. Return ONLY a single JSON object. No prose, no markdown, no code fences.
2. The JSON object MUST have exactly these two top-level keys:
   "states"      : a non-empty JSON array of state name strings (SCREAMING_SNAKE_CASE).
   "transitions" : a JSON array of transition objects, each with:
                     "from"      : source state name (must be in "states")
                     "to"        : target state name (must be in "states")
                     "event"     : the trigger event / condition (short string, Chinese OK)
                     "action"    : observable side effect (e.g. "count+1", "", "过滤")
3. Every state that appears in "transitions" MUST also appear in "states".
4. Do NOT invent states not implied by the requirements.
5. Self-loops are allowed only when the requirements explicitly describe them.
6. If the requirements describe NO state machine, return:
   {"states": [], "transitions": []}

CONTEXT:
Read the structured requirements JSON carefully and identify ALL finite state
machines described or implied within them. For each FSM:
- Extract every named state (use SCREAMING_SNAKE_CASE).
- Extract every valid state transition, its trigger event, and its observable
  action.
- Do NOT invent states or transitions that are not supported by the
  requirements text.
- Illegal or short-circuit paths (sequences that skip mandatory intermediate
  states) MUST NOT appear in the model — they are test anti-paths, not
  valid transitions.
- If the requirements contain no state machine, return:
  {"states": [], "transitions": []}
"""

_ST_EXTRACT_USER_PROMPT_TEMPLATE = """\
Below are already-structured requirements.
Extract the complete state machine model from them.

=== Structured Requirements ===
{reqs_json}

{user_guidance}

Return ONLY the JSON object {{\"states\": [...], \"transitions\": [...]}}.
"""


# ── LLM 工具 ───────────────────────────────────────────────────────────────

def _make_llm_client() -> Optional[Any]:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        from openai import OpenAI  # type: ignore[import]
    except ImportError:
        return None
    base_url = os.getenv("OPENAI_BASE_URL", "").strip()
    if base_url:
        return OpenAI(api_key=api_key, base_url=base_url)
    return OpenAI(api_key=api_key)


def _llm_model() -> str:
    return os.getenv("OPENAI_MODEL", "deepseek-chat").strip()


def _call_llm_sync(client: Any, system: str, user: str) -> str:
    model = _llm_model()
    try:
        if hasattr(client, "responses") and hasattr(client.responses, "create"):
            resp = client.responses.create(
                model=model,
                input=f"{system}\n\n{user}",
                temperature=0.0,
            )
            text = getattr(resp, "output_text", "") or ""
            return text.strip()
        if hasattr(client, "chat") and hasattr(client.chat.completions, "create"):
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user",   "content": user},
                ],
                temperature=0.0,
            )
            choices = getattr(resp, "choices", None) or []
            if choices:
                msg = getattr(choices[0], "message", None)
                if msg:
                    return (getattr(msg, "content", "") or "").strip()
    except Exception as exc:  # noqa: BLE001
        logger.warning("ST Worker LLM 调用失败: %s", exc)
    return ""


def _parse_state_graph_json(raw: str) -> Dict[str, Any]:
    """
    从 LLM 输出中健壮提取 {"states": [...], "transitions": [...]} JSON。
    返回空 dict 表示解析失败。
    """
    text = (raw or "").strip()
    if not text:
        return {}

    # 1. 直接解析
    candidate = _try_json(text)
    if _valid_graph(candidate):
        return candidate  # type: ignore[return-value]

    # 2. ```json 代码块
    for block in re.findall(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE):
        c = _try_json(block)
        if _valid_graph(c):
            return c  # type: ignore[return-value]

    # 3. 首个 {} 平衡块
    obj_start = text.find("{")
    if obj_start != -1:
        snippet = _balanced_extract(text, obj_start, "{", "}")
        c = _try_json(snippet)
        if _valid_graph(c):
            return c  # type: ignore[return-value]

    return {}


def _try_json(text: str) -> Any:
    try:
        text = re.sub(r",\s*([}\]])", r"\1", text)  # 尾部逗号
        text = re.sub(r"\bNone\b", "null",  text)
        text = re.sub(r"\bTrue\b", "true",  text)
        text = re.sub(r"\bFalse\b", "false", text)
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None


def _balanced_extract(text: str, start: int, open_ch: str, close_ch: str) -> str:
    depth, in_str, escape = 0, False, False
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
                return text[start : i + 1]
    return text[start:]


def _valid_graph(obj: Any) -> bool:
    """检查提取出的对象是否满足最低状态图 schema。"""
    return (
        isinstance(obj, dict)
        and isinstance(obj.get("states"), list)
        and isinstance(obj.get("transitions"), list)
    )


# ===========================================================================
# 第二阶段：networkx 图论遍历
# ===========================================================================


def build_nx_digraph(states: List[str], transitions: List[Dict[str, Any]]) -> Any:
    """
    将状态图数据转换为 networkx 有向图（MultiDiGraph 支持平行边）。

    节点属性 : {"label": state_name}
    边属性   : {"event": str, "action": str}
    """
    if not _HAS_NX:
        raise ImportError("networkx 未安装，无法构建有向图。请在 requirements.txt 中添加 networkx。")

    G = nx.MultiDiGraph()
    for s in states:
        G.add_node(s, label=s)
    for tr in transitions:
        src = tr.get("from", "")
        dst = tr.get("to", "")
        if src and dst and src in G and dst in G:
            G.add_edge(
                src, dst,
                event=tr.get("event", ""),
                action=tr.get("action", ""),
            )
    return G


def traverse_0_switch(G: Any) -> List[List[str]]:
    """
    0-switch 覆盖（= all-transitions）：遍历有向图中的每一条边。
    每条边 u → v 生成路径 [u, v]。
    当存在平行边时，每条平行边仍各生成一条路径。

    Returns
    -------
    List[List[str]]
        路径列表，每条路径为节点标签序列。
    """
    paths: List[List[str]] = []
    seen: set = set()
    for u, v, data in G.edges(data=True):
        key = (u, v, data.get("event", ""))
        if key not in seen:
            paths.append([u, v])
            seen.add(key)
    return paths


def traverse_1_switch(G: Any) -> List[List[str]]:
    """
    1-switch 覆盖（= all-transition-pairs）：遍历所有连续两条边的组合，
    即对每条边 A→B，枚举 B 的所有出边 B→C，生成路径 [A, B, C]。

    Returns
    -------
    List[List[str]]
        路径列表，每条路径为 3 节点序列（或 2 节点，当 B 无出边）。
    """
    paths: List[List[str]] = []
    seen: set = set()
    for u, v, d1 in G.edges(data=True):
        out_edges = list(G.out_edges(v, data=True))
        if not out_edges:
            # B 无出边：退化为 0-switch 路径
            key = (u, v, "")
            if key not in seen:
                paths.append([u, v])
                seen.add(key)
            continue
        for _, w, d2 in out_edges:
            key = (u, v, d1.get("event", ""), v, w, d2.get("event", ""))
            if key not in seen:
                paths.append([u, v, w])
                seen.add(key)
    return paths


def _pure_python_0_switch(transitions: List[Dict[str, Any]]) -> List[List[str]]:
    """networkx 不可用时的纯 Python 0-switch 降级实现。"""
    seen: set = set()
    paths: List[List[str]] = []
    for tr in transitions:
        src, dst = tr.get("from", ""), tr.get("to", "")
        if src and dst and (src, dst) not in seen:
            paths.append([src, dst])
            seen.add((src, dst))
    return paths


def _pure_python_1_switch(transitions: List[Dict[str, Any]]) -> List[List[str]]:
    """networkx 不可用时的纯 Python 1-switch 降级实现。"""
    # 构建出边表
    out: Dict[str, List[str]] = {}
    for tr in transitions:
        src, dst = tr.get("from", ""), tr.get("to", "")
        if src and dst:
            out.setdefault(src, []).append(dst)

    seen: set = set()
    paths: List[List[str]] = []
    for tr in transitions:
        u, v = tr.get("from", ""), tr.get("to", "")
        if not (u and v):
            continue
        nexts = out.get(v, [])
        if not nexts:
            if (u, v) not in seen:
                paths.append([u, v])
                seen.add((u, v))
            continue
        for w in nexts:
            if (u, v, w) not in seen:
                paths.append([u, v, w])
                seen.add((u, v, w))
    return paths


# ===========================================================================
# 第三阶段：路径 → 测试用例
# ===========================================================================

def _paths_to_cases(
    paths: List[List[str]],
    state_model: Dict[str, Any],
    coverage_criterion: str,
    start_index: int = 1,
    traceability: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    将路径列表转换为标准测试用例 dict 列表。

    规则
    ----
    - 非法短循环检测：路径长度 == 3，首尾节点相同，且中间节点不经过
      终止状态（含 DOWN / BOTTOM / 任何 _DOWN$ 后缀状态）。
      → 此类路径标记为「非法短循环」用例，预期 count 不变。
    - 其余路径按覆盖准则标注。
    """
    states: List[str] = state_model.get("states", [])
    init_state = states[0] if states else "INIT"
    # 终止状态集合：状态名的任一「_」分隔段完全匹配终止关键词
    # 使用完整词匹配，防止 DESCENDING 被 DOWN 误匹配
    terminal_keywords = {"DOWN", "BOTTOM", "END", "COMPLETE", "FINISH"}
    terminal_states: set = {
        s for s in states
        if any(token in terminal_keywords for token in s.upper().split("_"))
        or s.upper() in terminal_keywords
    }

    criterion_label = _criterion_label(coverage_criterion)
    trace_refs = list(traceability or _state_model_traceability(state_model))

    cases: List[Dict[str, Any]] = []
    for i, path in enumerate(paths, start=start_index):
        seq_label = " → ".join(path)
        is_short_circuit = (
            len(path) == 3
            and path[0] == path[-1]
            and not any(s in terminal_states for s in path[1:-1])
        )
        cases.append({
            "id":            f"TC-ST-{i:03d}",
            "technique":     "black-box",
            "designMethod":  "StateTransition",
            "title":         f"ST[{criterion_label}] {seq_label}",
            "precondition":  f"状态机处于初始状态 {init_state}，传感器数据流已就绪",
            "input":         f"帧序列触发路径: {seq_label}",
            "steps": (
                f"1. 将系统置于 {path[0]} 状态。\n"
                + "".join(
                    f"{j+2}. 触发从 {path[j]} 到 {path[j+1]} 的转换事件。\n"
                    for j in range(len(path) - 1)
                )
                + f"{len(path)+1}. 观察最终状态与计数器值。"
            ),
            "expected": (
                "系统停留在原状态，计数器 count 不变（非法短循环不计数）"
                if is_short_circuit
                else f"系统依次经过 {seq_label}，最终状态与计数符合规格"
            ),
            "oracle": (
                "断言 count == count_before"
                if is_short_circuit
                else f"断言最终状态 == {path[-1]} 且 count 符合预期增量"
            ),
            "priority":      "high" if is_short_circuit else "medium",
            "traceability":  trace_refs,
            "tags":          ["short-circuit-invalid"] if is_short_circuit else [criterion_label],
        })
    return cases


def _criterion_label(coverage_criterion: str) -> str:
    criterion = str(coverage_criterion or "all-states")
    if "1-switch" in criterion or criterion == "all-transition-pairs":
        return "1-switch (all-transition-pairs)"
    if criterion == "all-transitions":
        return "0-switch (all-transitions)"
    if criterion == "all-states":
        return "all-states"
    return criterion


def _state_model_traceability(state_model: Dict[str, Any]) -> List[str]:
    refs: List[str] = []
    for key in ("sourceReqIds", "reqIds", "traceability"):
        values = state_model.get(key)
        if isinstance(values, list):
            refs.extend(str(value).strip() for value in values if str(value).strip())
    single = str(state_model.get("sourceReqId", "")).strip()
    if single:
        refs.append(single)
    return list(dict.fromkeys(refs))


def _context_requirement_ids(ctx: Any) -> List[str]:
    return [
        str(req.get("id", "")).strip()
        for req in (getattr(ctx, "requirements_structured", []) or [])
        if str(req.get("id", "")).strip()
    ]


def _prompt_guidance(ctx: Any) -> str:
    extra = getattr(ctx, "extra", {}) or {}
    technique_prompts = extra.get("techniquePrompts") if isinstance(extra.get("techniquePrompts"), dict) else {}
    global_prompt = str(extra.get("globalPrompt", "") or "").strip()
    technique_prompt = str(technique_prompts.get("StateTransition", "") or "").strip()
    parts: List[str] = []
    if global_prompt:
        parts.append(f"Global user guidance:\n{global_prompt}")
    if technique_prompt:
        parts.append(f"StateTransition specific user guidance:\n{technique_prompt}")
    if not parts:
        return ""
    return "=== User Guidance (secondary to state-machine extraction rules) ===\n" + "\n\n".join(parts)


def _attach_context_traceability(state_graph: Dict[str, Any], ctx: Any) -> List[str]:
    existing = _state_model_traceability(state_graph)
    if existing:
        return existing

    req_ids = _context_requirement_ids(ctx)
    if not req_ids:
        return []

    states = {str(s).lower() for s in (state_graph.get("states") or [])}
    matched: List[str] = []
    for req in getattr(ctx, "requirements_structured", []) or []:
        req_id = str(req.get("id", "")).strip()
        blob = " ".join(
            [
                str(req.get("feature", "")),
                " ".join(str(c) for c in (req.get("conditions") or [])),
                str(req.get("expectedAction", "")),
            ]
        ).lower()
        if req_id and (
            "state" in blob
            or "transition" in blob
            or "->" in blob
            or any(state and state in blob for state in states)
        ):
            matched.append(req_id)

    return list(dict.fromkeys(matched or req_ids))


# ===========================================================================
# Worker 主入口
# ===========================================================================

async def worker_state_transition_llm(
    ctx: GlobalContext,
    start_index: int = 1,
) -> WorkerResult:
    """
    ST Worker：
    1. 调用 LLM 从结构化需求中提取状态图 JSON（states + transitions）。
    2. 用 networkx 按 ctx.coverage_criterion 精确遍历生成路径。
    3. 将路径转换为标准测试用例并返回 WorkerResult。

    降级策略
    --------
    - 无 API Key / LLM 调用失败 / JSON 解析失败
        → 使用 state_model_engine.build_state_model 的确定性状态机
        → 同样走 networkx 遍历，保证结果格式一致
    """
    t0 = time.perf_counter()
    client = _make_llm_client()

    state_graph: Dict[str, Any] = {}
    source_tag = "llm"

    # ── 1. 尝试 LLM 提取状态图 ──────────────────────────────────────────
    if client is not None:
        reqs_json = json.dumps(ctx.requirements_structured, ensure_ascii=False, indent=2)
        user_prompt = _ST_EXTRACT_USER_PROMPT_TEMPLATE.format(
            reqs_json=reqs_json,
            user_guidance=_prompt_guidance(ctx),
        )
        try:
            raw_text = await asyncio.get_event_loop().run_in_executor(
                None,
                _call_llm_sync,
                client, _ST_EXTRACT_SYSTEM_PROMPT, user_prompt,
            )
            state_graph = _parse_state_graph_json(raw_text)
            if state_graph.get("states"):
                logger.info(
                    "ST Worker: LLM 提取到 %d 状态, %d 转换",
                    len(state_graph["states"]),
                    len(state_graph.get("transitions", [])),
                )
            else:
                logger.warning("ST Worker: LLM 未返回有效状态图，降级至确定性引擎")
                state_graph = {}
                source_tag = "deterministic-engine:llm-empty-graph"
        except Exception as exc:  # noqa: BLE001
            logger.warning("ST Worker: LLM 调用异常 %s，降级", exc)
            state_graph = {}
            source_tag = f"deterministic-engine:executor-error:{exc}"
    else:
        logger.info("ST Worker: 无 LLM 客户端，使用确定性引擎")
        source_tag = "deterministic-engine:no-llm-client"

    # ── 2. 降级：用确定性引擎补充状态图 ─────────────────────────────────
    if not state_graph.get("states"):
        state_graph = build_state_model(
            ctx.requirements_structured,
            ctx.coverage_criterion,
            ctx.whitebox_description,
        )
        if not state_graph:
            logger.warning("ST Worker: 确定性引擎也未检测到状态机，返回空结果")
            return WorkerResult(
                technique="StateTransition",
                testcases=[],
                artifacts={"stateModel": {}, "workerSource": source_tag},
                elapsed_ms=int((time.perf_counter() - t0) * 1000),
            )

    # ── 3. networkx 图论遍历 ──────────────────────────────────────────────
    states: List[str] = state_graph.get("states", [])
    transitions: List[Dict[str, Any]] = state_graph.get("transitions", [])
    criterion = ctx.coverage_criterion  # "all-states" | "all-transitions" | "1-switch"
    trace_refs = _attach_context_traceability(state_graph, ctx)

    # 判断覆盖准则
    use_1_switch = "1-switch" in criterion or criterion == "all-transition-pairs"
    use_all_states = criterion == "all-states"

    if use_all_states:
        paths = [[s] for s in states]
    elif _HAS_NX:
        try:
            G = build_nx_digraph(states, transitions)
            paths = traverse_1_switch(G) if use_1_switch else traverse_0_switch(G)
        except Exception as exc:  # noqa: BLE001
            logger.warning("ST Worker: networkx 遍历失败 %s，使用纯 Python 降级", exc)
            paths = (
                _pure_python_1_switch(transitions) if use_1_switch
                else _pure_python_0_switch(transitions)
            )
    else:
        logger.warning("ST Worker: networkx 未安装，使用纯 Python 遍历")
        paths = (
            _pure_python_1_switch(transitions) if use_1_switch
            else _pure_python_0_switch(transitions)
        )

    # 若遍历后无路径（状态机只有孤立节点），至少为每个状态生成一条"到达"用例
    if not paths and states:
        paths = [[s] for s in states]

    # ── 4. 路径 → 测试用例 ────────────────────────────────────────────────
    cases = _paths_to_cases(paths, state_graph, criterion, start_index, trace_refs)

    logger.info(
        "ST Worker: criterion=%s, paths=%d, cases=%d, source=%s, elapsed=%dms",
        criterion, len(paths), len(cases), source_tag,
        int((time.perf_counter() - t0) * 1000),
    )

    return WorkerResult(
        technique="StateTransition",
        testcases=cases,
        artifacts={
            "stateModel": {
                **state_graph,
                "coverageCriterion": criterion,
                "switchLevel": "all-states" if use_all_states else ("1-switch" if use_1_switch else "0-switch"),
                "pathCount": len(paths),
                "sourceReqIds": trace_refs,
                "workerSource": source_tag,
                "workerVersion": WORKER_VERSION,
            },
        },
        elapsed_ms=int((time.perf_counter() - t0) * 1000),
    )


# ---------------------------------------------------------------------------
# 供 generation_pipeline._TECHNIQUE_WORKER_MAP 注册的快捷引用
# ---------------------------------------------------------------------------

#: 注册到 Router（调用方决定是否启用，可替换原有 worker_state_transition）
ST_WORKER_LLM = worker_state_transition_llm
