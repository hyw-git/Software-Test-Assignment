"""
generation_pipeline.py
======================
Map-Reduce / Multi-Worker 测试用例生成管线。

架构概览
--------

  ┌─────────────────────────────────────────────────────────┐
  │                       调用方                             │
  │  (main.py / FastAPI endpoint)                           │
  └──────────────────────┬──────────────────────────────────┘
                         │ selected_techniques + 原始输入
                         ▼
  ┌─────────────────────────────────────────────────────────┐
  │           GlobalContext  (不可变共享数据快照)             │
  │  • requirements_structured  ← 已结构化需求               │
  │  • risk_items               ← 已确认风险列表              │
  │  • coverage_criterion       ← all-states / all-transitions│
  │  • whitebox_description     ← 用户自定义状态图             │
  │  • optimization_mode        ← risk-first / minimize      │
  └──────────────────────┬──────────────────────────────────┘
                         │
                         ▼
  ┌─────────────────────────────────────────────────────────┐
  │     route_and_execute(context, selected_techniques)     │
  │                                                         │
  │   Router: technique → Worker 映射                        │
  │   asyncio.gather 并发调度所有激活的 Worker               │
  └──────────────────────┬──────────────────────────────────┘
                         │ List[WorkerResult]
                         ▼
  ┌─────────────────────────────────────────────────────────┐
  │                   Reduce 阶段                            │
  │   合并所有 Worker 结果 → 最终 artifacts + testcases      │
  └─────────────────────────────────────────────────────────┘

支持的 selected_techniques
--------------------------
    "EP"               → worker_ep
    "BVA"              → worker_bva
    "DecisionTable"    → worker_decision_table
    "Combinatorial"    → worker_combinatorial
    "StateTransition"  → worker_state_transition
    "Oracle"           → worker_oracle        (后处理，依赖已聚合用例)
    "Optimization"     → worker_optimization  (后处理，依赖已聚合用例)
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# 现有引擎导入
# ---------------------------------------------------------------------------
from .blackbox_fallbacks import (
    build_boundary_values,
    build_decision_table_rules,
    build_equivalence_partitions,
    build_coverage_items,
    generate_bva_cases,
    generate_combinatorial_cases,
    generate_decision_table_cases,
    generate_ep_cases,
)
from .oracle_engine import attach_oracles
from .strategy_builder import build_test_strategies
from .suite_optimizer import optimize_test_suite
from .state_model_engine import build_state_model, generate_state_transition_sequences

# 新 LLM-backed Worker（延迟导入，避免循环）
try:
    from .state_transition_worker import worker_state_transition_llm as _st_llm_worker
    _ST_WORKER = _st_llm_worker
except Exception:  # noqa: BLE001  (模块缺失或 networkx 未安装时安全降级)
    _st_fallback_logger = logging.getLogger(__name__)
    _st_fallback_logger.warning(
        "state_transition_worker 导入失败，ST Worker 将使用内置确定性实现"
    )
    _ST_WORKER = None  # type: ignore[assignment]

try:
    from .whitebox_java_worker import worker_whitebox_java as _WB_JAVA_WORKER
except Exception:  # noqa: BLE001
    _wb_java_logger = logging.getLogger(__name__)
    _wb_java_logger.warning("whitebox_java_worker import failed; WhiteBoxJava will be unavailable.")
    _WB_JAVA_WORKER = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

PIPELINE_VERSION = "generation-pipeline-v1"

# 全量技术集合，供 Router 参考
ALL_TECHNIQUES: List[str] = [
    "EP",
    "BVA",
    "DecisionTable",
    "Combinatorial",
    "StateTransition",
    "WhiteBoxJava",
]

# 后处理步骤（依赖其他 Worker 输出，不可并发）
POST_PROCESS_STEPS: List[str] = ["Oracle", "Optimization"]


# ---------------------------------------------------------------------------
# GlobalContext  —— 封装从前一阶段传递过来的共享只读数据
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GlobalContext:
    """
    不可变的共享上下文快照，由调用方一次性组装后传入 Router。

    字段说明
    --------
    requirements_structured : List[Dict]
        前一步（QRA 阶段）已解析并结构化的需求列表。
        格式遵循 requirement_parser 输出：含 id / feature / inputFields /
        expectedAction / conditions / ranges 等字段。

    risk_items : List[Dict]
        用户在 QRA Review 界面确认（可能已手工修改）后的风险列表。
        含 reqId / impact / likelihood / riskScore / priority 字段。
        Router 会将其传递给 worker_optimization 用于 risk-first 排序。

    coverage_criterion : str
        白盒覆盖准则："all-states" 或 "all-transitions"。

    whitebox_description : str
        可选：用户以自由文本或 JSON 描述的状态机，
        供 worker_state_transition 解析自定义模型。

    optimization_mode : str
        套件优化策略："risk-first"（按风险分降序）或 "minimize"（最小化用例数）。

    extra : Dict
        预留扩展字段，调用方可放任意附加信息（如 LLM raw text、prompt version）。
    """

    requirements_structured: List[Dict[str, Any]] = field(default_factory=list)
    risk_items: List[Dict[str, Any]] = field(default_factory=list)
    coverage_criterion: str = "all-states"
    whitebox_description: str = ""
    optimization_mode: str = "risk-first"
    extra: Dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # 工厂方法：从 FastAPI / generation request kwargs 快速构建
    # ------------------------------------------------------------------
    @classmethod
    def from_pipeline_kwargs(
        cls,
        requirements: List[Dict[str, Any]],
        risk_items: List[Dict[str, Any]],
        coverage_criterion: str = "all-states",
        whitebox_description: str = "",
        optimization_mode: str = "risk-first",
        **extra: Any,
    ) -> "GlobalContext":
        """
        便捷工厂，适配现有 generation_pipeline 调用约定。

        示例
        ----
        ctx = GlobalContext.from_pipeline_kwargs(
            requirements=reqs,
            risk_items=risks,
            coverage_criterion="all-transitions",
            whitebox_description="UP -> DOWN -> UP",
        )
        """
        return cls(
            requirements_structured=requirements,
            risk_items=risk_items,
            coverage_criterion=coverage_criterion,
            whitebox_description=whitebox_description,
            optimization_mode=optimization_mode,
            extra=extra,
        )


# ---------------------------------------------------------------------------
# WorkerResult  —— 单个 Worker 的返回值
# ---------------------------------------------------------------------------

@dataclass
class WorkerResult:
    """
    每个 Worker 协程的统一返回格式，方便 Reduce 阶段合并。

    Attributes
    ----------
    technique : str
        产生该结果的技术名称（如 "EP"、"BVA" …）。
    testcases : List[Dict]
        本 Worker 生成的测试用例列表。
    artifacts : Dict
        本 Worker 的附属工件（如等价类、边界值表等），Key 为字段名。
    elapsed_ms : int
        Worker 执行耗时（毫秒），用于 timingMetrics。
    error : Optional[str]
        若 Worker 执行出错，记录异常信息；正常时为 None。
    """

    technique: str
    testcases: List[Dict[str, Any]] = field(default_factory=list)
    artifacts: Dict[str, Any] = field(default_factory=dict)
    elapsed_ms: int = 0
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Worker 骨架  —— 每个 Worker 是一个 async 协程
# ---------------------------------------------------------------------------
# 暂不实现具体细节，只写好签名、docstring 与 TODO 标记，
# 保证 Router 可以正确 await 并收到 WorkerResult。
# ---------------------------------------------------------------------------

async def worker_ep(ctx: GlobalContext, start_index: int = 1) -> WorkerResult:
    """
    Worker: 等价类划分 (Equivalence Partitioning)
    -----------------------------------------------
    对 ctx.requirements_structured 中每条需求，生成有效类与无效类测试用例。

    TODO:
        - 调用 generate_ep_cases(ctx.requirements_structured, start_index)
        - 返回 EP 测试用例列表与等价类分区工件
    """
    t0 = time.perf_counter()
    try:
        # --- 实现占位 ---
        cases, _ = generate_ep_cases(ctx.requirements_structured, start_index)
        eq_partitions = build_equivalence_partitions(ctx.requirements_structured)
        return WorkerResult(
            technique="EP",
            testcases=cases,
            artifacts={"equivalencePartitions": eq_partitions},
            elapsed_ms=int((time.perf_counter() - t0) * 1000),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("worker_ep failed")
        return WorkerResult(technique="EP", error=str(exc),
                            elapsed_ms=int((time.perf_counter() - t0) * 1000))


async def worker_bva(ctx: GlobalContext, start_index: int = 1) -> WorkerResult:
    """
    Worker: 边界值分析 (Boundary Value Analysis)
    ---------------------------------------------
    对有数值范围限制的字段（landmarks.length、durationSeconds 等）生成边界用例。

    TODO:
        - 调用 generate_bva_cases(ctx.requirements_structured, start_index)
        - 返回 BVA 测试用例列表与边界值工件
    """
    t0 = time.perf_counter()
    try:
        cases, _ = generate_bva_cases(ctx.requirements_structured, start_index)
        bv_items = build_boundary_values(ctx.requirements_structured)
        return WorkerResult(
            technique="BVA",
            testcases=cases,
            artifacts={"boundaryValues": bv_items},
            elapsed_ms=int((time.perf_counter() - t0) * 1000),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("worker_bva failed")
        return WorkerResult(technique="BVA", error=str(exc),
                            elapsed_ms=int((time.perf_counter() - t0) * 1000))


async def worker_decision_table(ctx: GlobalContext, start_index: int = 1) -> WorkerResult:
    """
    Worker: 决策表测试 (Decision Table Testing)
    --------------------------------------------
    解析需求中的条件组合，生成决策表规则及对应用例。

    TODO:
        - 调用 build_decision_table_rules(ctx.requirements_structured)
        - 再调用 generate_decision_table_cases(rules, start_index)
        - 返回 DT 测试用例列表与决策表规则工件
    """
    t0 = time.perf_counter()
    try:
        rules = build_decision_table_rules(ctx.requirements_structured)
        cases, _ = generate_decision_table_cases(rules, start_index)
        return WorkerResult(
            technique="DecisionTable",
            testcases=cases,
            artifacts={"decisionTableRules": rules},
            elapsed_ms=int((time.perf_counter() - t0) * 1000),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("worker_decision_table failed")
        return WorkerResult(technique="DecisionTable", error=str(exc),
                            elapsed_ms=int((time.perf_counter() - t0) * 1000))


async def worker_combinatorial(ctx: GlobalContext, start_index: int = 1) -> WorkerResult:
    """
    Worker: 组合/两两配对测试 (Combinatorial / Pairwise)
    -----------------------------------------------------
    提取多因子组合，使用 Pairwise 策略减少用例数量。

    TODO:
        - 调用 generate_combinatorial_cases(ctx.requirements_structured, start_index)
        - 返回 Combinatorial 测试用例列表
    """
    t0 = time.perf_counter()
    try:
        cases, _ = generate_combinatorial_cases(ctx.requirements_structured, start_index)
        return WorkerResult(
            technique="Combinatorial",
            testcases=cases,
            artifacts={},
            elapsed_ms=int((time.perf_counter() - t0) * 1000),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("worker_combinatorial failed")
        return WorkerResult(technique="Combinatorial", error=str(exc),
                            elapsed_ms=int((time.perf_counter() - t0) * 1000))


async def worker_state_transition(ctx: GlobalContext, start_index: int = 1) -> WorkerResult:
    """
    Worker: 状态迁移测试 (State Transition Testing)
    ------------------------------------------------
    根据 ctx.whitebox_description 或需求中的状态关键词，
    构建状态机模型，按 ctx.coverage_criterion 生成迁移序列用例。

    TODO:
        - 调用 build_state_model(ctx.requirements_structured, ctx.coverage_criterion, ctx.whitebox_description)
        - 调用 generate_state_transition_sequences(state_model, ctx.coverage_criterion, start_index)
        - 返回 StateTransition 测试用例列表与状态机模型工件
    """
    t0 = time.perf_counter()
    try:
        state_model = build_state_model(
            ctx.requirements_structured,
            ctx.coverage_criterion,
            ctx.whitebox_description,
        )
        if not state_model:
            return WorkerResult(
                technique="StateTransition",
                testcases=[],
                artifacts={"stateModel": {}},
                elapsed_ms=int((time.perf_counter() - t0) * 1000),
            )
        cases, _ = generate_state_transition_sequences(
            state_model, ctx.coverage_criterion, start_index
        )
        return WorkerResult(
            technique="StateTransition",
            testcases=cases,
            artifacts={"stateModel": state_model},
            elapsed_ms=int((time.perf_counter() - t0) * 1000),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("worker_state_transition failed")
        return WorkerResult(technique="StateTransition", error=str(exc),
                            elapsed_ms=int((time.perf_counter() - t0) * 1000))


# ---------------------------------------------------------------------------
# TECHNIQUE → WORKER 映射表
# ---------------------------------------------------------------------------

_TECHNIQUE_WORKER_MAP: Dict[str, Any] = {
    "EP":              worker_ep,
    "BVA":             worker_bva,
    "DecisionTable":   worker_decision_table,
    "Combinatorial":   worker_combinatorial,
    # 优先使用 LLM+networkx 版 ST Worker；若导入失败则回退到内置确定性实现
    "StateTransition": _ST_WORKER if _ST_WORKER is not None else worker_state_transition,
}
if _WB_JAVA_WORKER is not None:
    _TECHNIQUE_WORKER_MAP["WhiteBoxJava"] = _WB_JAVA_WORKER

try:
    from .blackbox_workers import LLM_WORKER_OVERRIDES as _BB_OVERRIDES
    for _tech, _worker_fn in _BB_OVERRIDES.items():
        _TECHNIQUE_WORKER_MAP[_tech] = _worker_fn
except ImportError:
    logger.warning("blackbox_workers 导入失败，将使用内置确定性黑盒 Worker")
except Exception as e:  # noqa: BLE001
    logger.warning(f"加载 LLM_WORKER_OVERRIDES 失败: {e}")


# ---------------------------------------------------------------------------
# Reduce  ——  合并所有 WorkerResult → 最终输出
# ---------------------------------------------------------------------------

def _reduce_worker_results(
    ctx: GlobalContext,
    results: List[WorkerResult],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    将并发 Worker 的输出 merge 成统一的 (testcases, artifacts)。

    merge 规则
    ----------
    - testcases  : 按 Worker 顺序拼接，重新分配顺序 ID。
    - artifacts  : 各 Worker 的 artifacts 字典浅合并，
                   列表型字段（如 boundaryValues）追加合并。
    - coverage_items : 汇总所有 designMethod 与需求特征。
    """
    merged_testcases: List[Dict[str, Any]] = []
    merged_artifacts: Dict[str, Any] = {
        "equivalencePartitions": [],
        "boundaryValues": [],
        "decisionTableRules": [],
        "stateModel": {},
    }

    for result in results:
        if result.error:
            logger.warning("Worker %s returned error: %s", result.technique, result.error)
            continue
        merged_testcases.extend(result.testcases)

        # 合并 artifacts 字段
        for key, value in result.artifacts.items():
            if isinstance(value, list):
                existing = merged_artifacts.get(key, [])
                if isinstance(existing, list):
                    merged_artifacts[key] = existing + value
                else:
                    merged_artifacts[key] = value
            else:
                # 非列表（如 stateModel dict）：后写覆盖
                if value:
                    merged_artifacts[key] = value

    # 重新分配 ID：每个技术（designMethod）独立计数
    # 例如 TC-EP-001, TC-EP-002 … TC-BVA-001 … TC-ST-001 …
    _method_counters: Dict[str, int] = {}
    for case in merged_testcases:
        method = case.get("designMethod", "UNK")
        # 前缀映射：使用完整缩写而非截断，保持可读性
        prefix_map = {
            "EP":              "EP",
            "BVA":             "BVA",
            "DecisionTable":   "DT",
            "Combinatorial":   "CB",
            "StateTransition": "ST",
            "WhiteBoxJava":    "WBJ",
        }
        prefix = prefix_map.get(method, method[:3].upper())
        _method_counters[prefix] = _method_counters.get(prefix, 0) + 1
        case["id"] = f"TC-{prefix}-{_method_counters[prefix]:03d}"

    # 构建 coverageItems
    existing_coverage_items = merged_artifacts.get("coverageItems", [])
    if not isinstance(existing_coverage_items, list):
        existing_coverage_items = []
    methods_used = {c.get("designMethod", "") for c in merged_testcases}
    blackbox_methods = {m for m in methods_used if m != "WhiteBoxJava"}
    blackbox_coverage = build_coverage_items(
        ctx.requirements_structured, blackbox_methods  # type: ignore[arg-type]
    ) if blackbox_methods else []
    merged_artifacts["coverageItems"] = existing_coverage_items + blackbox_coverage
    merged_artifacts["inputVariables"] = sorted(
        {f for req in ctx.requirements_structured for f in (req.get("inputFields") or [])}
    )

    return merged_testcases, merged_artifacts


# ---------------------------------------------------------------------------
# Router  ——  核心入口
# ---------------------------------------------------------------------------

async def route_and_execute(
    context: GlobalContext,
    selected_techniques: List[str],
    *,
    include_oracle: bool = True,
    include_optimization: bool = True,
) -> Dict[str, Any]:
    """
    根据 selected_techniques 动态唤醒对应 Worker，并发执行后 Reduce 结果。

    Parameters
    ----------
    context : GlobalContext
        已组装完毕的共享上下文（需求、风险、覆盖准则等）。
    selected_techniques : List[str]
        用户/前端传入的技术列表，例如 ["EP", "BVA", "StateTransition"]。
        未知技术名称会被忽略并记录 warning。
    include_oracle : bool
        是否在 Reduce 后执行 Oracle 后处理（attach_oracles）。
    include_optimization : bool
        是否在 Reduce 后执行套件优化（optimize_test_suite）。

    Returns
    -------
    Dict[str, Any]
        与 FastAPI GenerateResponse 工件格式兼容的输出字典，包含：
        requirementsStructured, riskItems, coverageItems, testStrategies,
        stateModel, testSuiteOptimization, traceability, testcases,
        engineMetadata, timingMetrics 等字段。
    """
    wall_start = time.perf_counter()

    # ── 1. Router: 解析 selected_techniques → 构建 coroutine 列表 ──────────
    coroutines = []
    activated: List[str] = []
    unknown: List[str] = []

    # 计算每个 Worker 在全局 testcases 中的起始 ID，避免并发冲突
    # 简单策略：预估 + 留余量（精确偏移在 Reduce 阶段统一重编）
    start_idx = 1

    for technique in selected_techniques:
        worker_fn = _TECHNIQUE_WORKER_MAP.get(technique)
        if worker_fn is None:
            unknown.append(technique)
            logger.warning(
                "route_and_execute: unknown technique '%s', skipped. "
                "Supported: %s",
                technique,
                list(_TECHNIQUE_WORKER_MAP.keys()),
            )
            continue
        # 每个 Worker 拿到当前 start_idx（Reduce 阶段会统一重编 ID）
        coroutines.append(worker_fn(context, start_index=start_idx))
        activated.append(technique)
        start_idx += 50  # 预留 50 个 ID 间隔，避免 Worker 内部冲突

    if not coroutines:
        logger.warning(
            "route_and_execute: no valid techniques selected (input=%s). "
            "Falling back to empty result.",
            selected_techniques,
        )
        coroutines = [worker_ep(context, 1)]  # 保证最小输出
        activated = ["EP"]

    logger.info(
        "route_and_execute: dispatching %d workers → %s",
        len(coroutines),
        activated,
    )

    # ── 2. Map: asyncio.gather 并发执行所有 Worker ─────────────────────────
    gather_start = time.perf_counter()
    worker_results: List[WorkerResult] = await asyncio.gather(*coroutines)
    gather_ms = int((time.perf_counter() - gather_start) * 1000)

    logger.info(
        "route_and_execute: all workers completed in %d ms (workers=%s)",
        gather_ms,
        [(r.technique, r.elapsed_ms) for r in worker_results],
    )

    # ── 3. Reduce: 合并 Worker 输出 ────────────────────────────────────────
    testcases, artifacts = _reduce_worker_results(context, worker_results)

    # ── 4. 后处理: Oracle（依赖完整 testcases 列表）───────────────────────
    if include_oracle and testcases:
        testcases = attach_oracles(testcases, context.requirements_structured)

    # ── 5. 后处理: Strategy Builder ────────────────────────────────────────
    test_strategies = build_test_strategies(
        context.requirements_structured,
        testcases,
        artifacts.get("coverageItems", []),
    )

    # ── 6. 后处理: Suite Optimization（依赖 risk_items）──────────────────
    optimization: Dict[str, Any] = {}
    if include_optimization and testcases:
        optimization = optimize_test_suite(
            testcases,
            context.risk_items,
            artifacts.get("coverageItems", []),
            mode=context.optimization_mode,
        )

    # ── 7. Traceability ───────────────────────────────────────────────────
    traceability = _build_traceability(context.requirements_structured, testcases)

    # ── 8. 组装最终输出 ───────────────────────────────────────────────────
    total_ms = int((time.perf_counter() - wall_start) * 1000)
    worker_timing = {r.technique: r.elapsed_ms for r in worker_results}

    return {
        # 核心工件
        "requirementsStructured": context.requirements_structured,
        "riskItems": context.risk_items,
        "inputVariables": artifacts.get("inputVariables", []),
        "equivalencePartitions": artifacts.get("equivalencePartitions", []),
        "decisionTableRules": artifacts.get("decisionTableRules", []),
        "boundaryValues": artifacts.get("boundaryValues", []),
        "coverageItems": artifacts.get("coverageItems", []),
        "testStrategies": test_strategies,
        "stateModel": artifacts.get("stateModel", {}),
        "testSuiteOptimization": optimization,
        "traceability": traceability,
        "testcases": testcases,
        "whiteboxAnalysis": artifacts.get("whiteboxAnalysis", {}),
        "testSequences": artifacts.get("testSequences", []),
        "llmEnhancedTestcases": artifacts.get("llmEnhancedTestcases", []),
        "llmReadyWhiteboxContext": artifacts.get("llmReadyWhiteboxContext", {}),
        "warnings": artifacts.get("warnings", []),
        "missingItems": [],
        "assumptions": [
            "Map-Reduce 管线并发执行多技术 Worker",
            f"已激活技术: {activated}",
        ],
        # 元数据
        "engineMetadata": {
            "pipelineVersion": PIPELINE_VERSION,
            "activatedTechniques": activated,
            "unknownTechniques": unknown,
            "caseCount": len(testcases),
            "requirementCount": len(context.requirements_structured),
            "strategyCount": len(test_strategies),
            "workerTimingMs": worker_timing,
            "gatherMs": gather_ms,
        },
        "timingMetrics": {
            "engineMs": total_ms,
            "llmMs": 0,
            "totalMs": total_ms,
            "engineMeetsNfr": total_ms <= 2000,
        },
    }


# ---------------------------------------------------------------------------
# 辅助：Traceability（本模块内直接构建，避免旧流水线依赖）
# ---------------------------------------------------------------------------

def _build_traceability(
    requirements: List[Dict[str, Any]],
    testcases: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
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
                "coverageItems": [
                    f"{req.get('feature')}:结构化",
                    f"{req.get('feature')}:黑盒设计",
                ],
                "testcases": linked_cases,
            }
        )
    return trace


# ---------------------------------------------------------------------------
# 同步包装器  ——  供现有同步调用点（如 FastAPI endpoint）接入
# ---------------------------------------------------------------------------

def run_generation_pipeline(
    context: GlobalContext,
    selected_techniques: List[str],
    *,
    include_oracle: bool = True,
    include_optimization: bool = True,
) -> Dict[str, Any]:
    """
    route_and_execute 的同步包装，在无事件循环的环境（如单元测试、同步调用）中使用。

    示例
    ----
    ctx = GlobalContext.from_pipeline_kwargs(
        requirements=reqs,
        risk_items=risks,
        coverage_criterion="all-states",
    )
    result = run_generation_pipeline(ctx, ["EP", "BVA", "StateTransition"])
    """
    return asyncio.run(
        route_and_execute(
            context,
            selected_techniques,
            include_oracle=include_oracle,
            include_optimization=include_optimization,
        )
    )


# ---------------------------------------------------------------------------
# aggregate_results()  ——  公共结果聚合函数（供外部调用方或测试使用）
# ---------------------------------------------------------------------------

def aggregate_results(
    results_list: List[WorkerResult],
) -> Dict[str, Any]:
    """
    接收来自多个 Worker 的 WorkerResult 列表，合并为统一的前端响应格式。

    合并规则
    --------
    - **testcases**：按传入顺序拼接，每个技术独立重新编号（TC-EP-001, TC-BVA-001,
      TC-ST-001 …），确保 ID 唯一且语义清晰。
    - **artifacts**：列表型字段追加合并；非列表字段后写覆盖（stateModel 等）。
    - **metadata**：
        * ``total_cases``  : 所有技术的用例总数
        * ``by_technique`` : Dict[technique, int] — 各技术用例数量
        * ``elapsed_ms``   : Dict[technique, int] — 各 Worker 耗时（毫秒）
        * ``total_ms``     : 各 Worker 耗时之和（注意：并发执行时实际墙钟时间更短）
        * ``errors``       : 执行出错的技术及其错误信息

    Parameters
    ----------
    results_list : List[WorkerResult]
        来自 EP / BVA / ST（及其他）Worker 的返回值列表，顺序任意。

    Returns
    -------
    Dict[str, Any]
        包含 ``metadata`` 和 ``testcases`` 两个顶层键的完整聚合结果。

    示例
    ----
    >>> from app.engines.generation_pipeline import aggregate_results, WorkerResult
    >>> ep_result  = WorkerResult(technique="EP",  testcases=[...], elapsed_ms=12)
    >>> bva_result = WorkerResult(technique="BVA", testcases=[...], elapsed_ms=8)
    >>> st_result  = WorkerResult(technique="StateTransition", testcases=[...], elapsed_ms=45)
    >>> output = aggregate_results([ep_result, bva_result, st_result])
    >>> output["metadata"]["total_cases"]
    N
    """
    # ── 前缀映射表（与 _reduce_worker_results 保持一致）──────────────
    _PREFIX_MAP: Dict[str, str] = {
        "EP":              "EP",
        "BVA":            "BVA",
        "DecisionTable":  "DT",
        "Combinatorial":  "CB",
        "StateTransition": "ST",
        "WhiteBoxJava":   "WBJ",
    }

    # ── 合并 artifacts ──────────────────────────────────────────────────
    merged_artifacts: Dict[str, Any] = {
        "equivalencePartitions": [],
        "boundaryValues": [],
        "decisionTableRules": [],
        "stateModel": {},
    }

    # ── 元数据收集 ──────────────────────────────────────────────────────
    by_technique: Dict[str, int] = {}
    elapsed_ms: Dict[str, int] = {}
    errors: Dict[str, str] = {}

    all_cases: List[Dict[str, Any]] = []

    for result in results_list:
        tech = result.technique

        # 记录耗时（同一技术若出现多次，累加）
        elapsed_ms[tech] = elapsed_ms.get(tech, 0) + result.elapsed_ms

        # 记录错误
        if result.error:
            errors[tech] = result.error
            logger.warning("aggregate_results: Worker %s 报告错误: %s", tech, result.error)
            continue

        # 合并用例
        all_cases.extend(result.testcases)

        # 合并 artifacts
        for key, value in result.artifacts.items():
            if isinstance(value, list):
                existing = merged_artifacts.get(key, [])
                merged_artifacts[key] = (existing if isinstance(existing, list) else []) + value
            else:
                if value:
                    merged_artifacts[key] = value

    # ── 重新编号（每个技术独立计数）────────────────────────────────────
    _method_counters: Dict[str, int] = {}
    for case in all_cases:
        method = case.get("designMethod", "UNK")
        prefix = _PREFIX_MAP.get(method, method[:3].upper())
        _method_counters[prefix] = _method_counters.get(prefix, 0) + 1
        old_id = case.get("id", "")
        case["id"] = f"TC-{prefix}-{_method_counters[prefix]:03d}"
        if old_id != case["id"]:
            logger.debug("aggregate_results: 重编 ID %s → %s", old_id, case["id"])

    # ── 统计各技术用例数 ─────────────────────────────────────────────────
    for case in all_cases:
        # 从重编后的 ID 反推技术前缀，或直接用 designMethod
        method = case.get("designMethod", "UNK")
        by_technique[method] = by_technique.get(method, 0) + 1

    total_ms = sum(elapsed_ms.values())

    return {
        "metadata": {
            "total_cases":  len(all_cases),
            "by_technique": by_technique,
            "elapsed_ms":   elapsed_ms,
            "total_ms":     total_ms,
            "errors":       errors,
            "techniques_activated": [r.technique for r in results_list if not r.error],
        },
        "testcases":  all_cases,
        "artifacts":  merged_artifacts,
    }
