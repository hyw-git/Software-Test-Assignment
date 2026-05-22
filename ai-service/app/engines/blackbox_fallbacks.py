import itertools
from typing import Any, Dict, List, Set, Tuple


def _case_id(prefix: str, index: int) -> str:
    return f"{prefix}-{index:03d}"


def build_equivalence_partitions(requirements: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    partitions: List[Dict[str, str]] = []
    for req in requirements:
        ranges = req.get("ranges") or {}
        enum_values = ranges.get("enum")
        if isinstance(enum_values, list) and enum_values:
            partitions.append(
                {
                    "id": f"EP-{req.get('id', 'X')}-VALID",
                    "description": f"{req.get('feature')} 合法枚举输入",
                    "type": "valid",
                    "expected": req.get("expectedAction", "处理成功"),
                }
            )
            partitions.append(
                {
                    "id": f"EP-{req.get('id', 'X')}-INVALID",
                    "description": f"{req.get('feature')} 非法枚举输入",
                    "type": "invalid",
                    "expected": "返回可解释错误",
                }
            )
        else:
            partitions.append(
                {
                    "id": f"EP-{req.get('id', 'X')}",
                    "description": f"{req.get('feature')} 有效输入类",
                    "type": "valid",
                    "expected": req.get("expectedAction", "符合规格"),
                }
            )
    return partitions


def build_boundary_values(requirements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """构建边界值元数据（用于 artifact 展示）。
    每个边界点 B 生成三点簇 [B-1, B, B+1]，即三点法标准结构。
    """
    items: List[Dict[str, Any]] = []
    for req in requirements:
        ranges = req.get("ranges") or {}
        length_spec = ranges.get("landmarks.length")
        if isinstance(length_spec, dict):
            lo: int = length_spec.get("min", 0)
            hi: int = length_spec.get("max", lo)
            items.append(
                {
                    "field": "landmarks.length",
                    "lowerCluster": [lo - 1, lo, lo + 1],
                    "upperCluster": [hi - 1, hi, hi + 1],
                    "rationale": "三点法：对下边界和上边界各取 B-1 / B / B+1",
                }
            )
        dur_spec = ranges.get("durationSeconds")
        if isinstance(dur_spec, dict):
            b: int = dur_spec.get("min", 30)
            items.append(
                {
                    "field": "durationSeconds",
                    "lowerCluster": [b - 1, b, b + 1],
                    "rationale": "三点法：单点边界 B-1 / B / B+1",
                }
            )
        elif "durationSeconds" in ranges or "count" in ranges:
            # 兼容旧格式：直接给出边界值数字
            raw = ranges.get("durationSeconds")
            b = int(raw) if isinstance(raw, (int, float)) else 30
            items.append(
                {
                    "field": "durationSeconds",
                    "lowerCluster": [b - 1, b, b + 1],
                    "rationale": "三点法：单点边界 B-1 / B / B+1",
                }
            )
        count_spec = ranges.get("count")
        if count_spec is not None:
            bc = int(count_spec) if isinstance(count_spec, (int, float)) else 3
            items.append(
                {
                    "field": "count",
                    "lowerCluster": [bc - 1, bc, bc + 1],
                    "rationale": "三点法：单点边界 B-1 / B / B+1",
                }
            )
    if not items:
        items.append(
            {
                "field": "contentLength",
                "lowerCluster": [0, 1, 2],
                "rationale": "通用输入长度下边界三点法",
            }
        )
    return items


def build_decision_table_rules(requirements: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    rules: List[Dict[str, str]] = []
    for req in requirements:
        cond_text = " ".join(str(c) for c in (req.get("conditions") or []))
        if "count" in cond_text.lower() and "duration" in cond_text.lower():
            combos = [
                ("count<3, duration<30", "过滤记录", "不写入数据库"),
                ("count<3, duration>=30", "接收记录", "记录入库"),
                ("count>=3, duration<30", "接收记录", "记录入库"),
                ("count>=3, duration>=30", "接收记录", "记录入库"),
            ]
            for conditions, actions, expected in combos:
                rules.append({"conditions": conditions, "actions": actions, "expected": expected})
        elif req.get("conditions"):
            rules.append(
                {
                    "conditions": "; ".join(req.get("conditions")),
                    "actions": req.get("expectedAction", "执行"),
                    "expected": req.get("expectedAction", "符合预期"),
                }
            )
    return rules


def generate_ep_cases(requirements: List[Dict[str, Any]], start_index: int = 1) -> Tuple[List[Dict[str, Any]], int]:
    cases: List[Dict[str, Any]] = []
    idx = start_index
    for req in requirements:
        ranges = req.get("ranges") or {}
        enum_values = ranges.get("enum") if isinstance(ranges.get("enum"), list) else []
        valid = enum_values[0] if enum_values else "valid-input"
        invalid = "INVALID_TYPE" if enum_values else "invalid-input"
        fields = ", ".join(req.get("inputFields") or ["input"])

        cases.append(
            {
                "id": _case_id("TC-EP", idx),
                "technique": "black-box",
                "designMethod": "EP",
                "title": f"EP-有效等价类-{req.get('feature')}",
                "precondition": "系统接口可访问",
                "input": f"{fields}={valid}",
                "steps": "提交请求并校验响应结构",
                "expected": str(req.get("expectedAction", "处理成功")),
                "oracle": "",
                "priority": "high",
                "traceability": [str(req.get("id", ""))],
            }
        )
        idx += 1
        cases.append(
            {
                "id": _case_id("TC-EP", idx),
                "technique": "black-box",
                "designMethod": "EP",
                "title": f"EP-无效等价类-{req.get('feature')}",
                "precondition": "系统接口可访问",
                "input": f"{fields}={invalid}",
                "steps": "提交非法输入",
                "expected": "返回 4xx 或可解释错误，不产生 5xx",
                "oracle": "",
                "priority": "medium",
                "traceability": [str(req.get("id", ""))],
            }
        )
        idx += 1
    return cases, idx


def generate_bva_cases(requirements: List[Dict[str, Any]], start_index: int = 1) -> Tuple[List[Dict[str, Any]], int]:
    """确定性 BVA 用例生成器（三点法 + 单缺陷假设）。

    对每个数值型边界 B（下边界 min 或上边界 max），生成三个测试用例：
      B-1 / B / B+1

    当某个变量处于无效边界点时（违反有效域），其他变量统一取标称值（单缺陷假设）。
    """
    cases: List[Dict[str, Any]] = []
    idx = start_index

    def _append(
        field: str,
        boundary_label: str,
        value: int,
        validity: str,
        extra_inputs: str,
        expected: str,
        req_id: str,
        priority: str = "high",
    ) -> None:
        nonlocal idx
        input_str = f"{field}={value}"
        if extra_inputs:
            input_str += f", {extra_inputs}"
        cases.append(
            {
                "id": _case_id("TC-BVA", idx),
                "technique": "black-box",
                "designMethod": "BVA",
                "title": f"BVA-{field}={value} ({boundary_label}, {validity})",
                "precondition": "系统接口可访问",
                "input": input_str,
                "steps": "提交请求并校验响应",
                "expected": expected,
                "oracle": "",
                "priority": priority,
                "traceability": [req_id],
            }
        )
        idx += 1

    for req in requirements:
        ranges = req.get("ranges") or {}
        req_id = str(req.get("id", ""))

        # ── landmarks.length 边界 ─────────────────────────────────────────
        length_spec = ranges.get("landmarks.length")
        if isinstance(length_spec, dict):
            lo: int = int(length_spec.get("min", 0))
            hi: int = int(length_spec.get("max", lo))
            nominal: int = length_spec.get("nominal") or ((lo + hi) // 2)
            ok_action = str(req.get("expectedAction", "姿态分析成功"))
            nominal_extra = ""  # landmarks.length 是唯一的输入变量（此处无其他变量需列出）

            # 下边界簇
            _append("landmarks.length", "下边界-1", lo - 1, "无效", nominal_extra,
                    "返回可解释错误，拒绝处理", req_id)
            _append("landmarks.length", "下边界", lo, "有效", nominal_extra,
                    ok_action, req_id)
            _append("landmarks.length", "下边界+1", lo + 1, "有效", nominal_extra,
                    ok_action, req_id)

            # 上边界簇（仅当 hi != lo 时展开，避免重复）
            if hi != lo:
                _append("landmarks.length", "上边界-1", hi - 1, "有效", nominal_extra,
                        ok_action, req_id)
                _append("landmarks.length", "上边界", hi, "有效", nominal_extra,
                        ok_action, req_id)
                _append("landmarks.length", "上边界+1", hi + 1, "无效", nominal_extra,
                        "返回可解释错误，拒绝处理", req_id)

        # ── durationSeconds 边界 ─────────────────────────────────────────
        dur_range = ranges.get("durationSeconds")
        nominal_count = 5  # 默认标称 count
        count_range = ranges.get("count")
        if isinstance(count_range, (int, float)):
            nominal_count = int(count_range)

        if isinstance(dur_range, dict):
            b_dur: int = int(dur_range.get("min", 30))
            _append("durationSeconds", "边界-1", b_dur - 1, "无效",
                    f"count={nominal_count}",
                    "记录被过滤，不写入数据库", req_id)
            _append("durationSeconds", "边界", b_dur, "有效",
                    f"count={nominal_count}",
                    "记录保存成功", req_id)
            _append("durationSeconds", "边界+1", b_dur + 1, "有效",
                    f"count={nominal_count}",
                    "记录保存成功", req_id)
        elif "durationSeconds" in ranges or "count" in ranges:
            # 兼容旧格式：直接存数值
            raw_dur = ranges.get("durationSeconds")
            b_dur = int(raw_dur) if isinstance(raw_dur, (int, float)) else 30
            _append("durationSeconds", "边界-1", b_dur - 1, "无效",
                    f"count={nominal_count}",
                    "记录被过滤，不写入数据库", req_id)
            _append("durationSeconds", "边界", b_dur, "有效",
                    f"count={nominal_count}",
                    "记录保存成功", req_id)
            _append("durationSeconds", "边界+1", b_dur + 1, "有效",
                    f"count={nominal_count}",
                    "记录保存成功", req_id)

        # ── count 边界（独立） ────────────────────────────────────────────
        nominal_dur = 60  # 默认标称 durationSeconds
        if isinstance(count_range, (int, float)):
            b_count: int = int(count_range)
            _append("count", "边界-1", b_count - 1, "无效",
                    f"durationSeconds={nominal_dur}",
                    "记录被过滤，不写入数据库", req_id)
            _append("count", "边界", b_count, "有效",
                    f"durationSeconds={nominal_dur}",
                    "记录保存成功", req_id)
            _append("count", "边界+1", b_count + 1, "有效",
                    f"durationSeconds={nominal_dur}",
                    "记录保存成功", req_id)

    # ── 保底：没有解析出任何用例时给通用用例 ────────────────────────────
    if not cases:
        for value, label, validity, expected in [
            (0, "下边界-1", "无效", "返回可解释错误"),
            (1, "下边界", "有效", "处理成功"),
            (2, "下边界+1", "有效", "处理成功"),
        ]:
            cases.append(
                {
                    "id": _case_id("TC-BVA", idx),
                    "technique": "black-box",
                    "designMethod": "BVA",
                    "title": f"BVA-contentLength={value} ({label}, {validity})",
                    "precondition": "系统接口可访问",
                    "input": f"contentLength={value}",
                    "steps": "提交请求并校验响应",
                    "expected": expected,
                    "oracle": "",
                    "priority": "high",
                    "traceability": [],
                }
            )
            idx += 1

    return cases, idx



def generate_decision_table_cases(rules: List[Dict[str, str]], start_index: int = 1) -> Tuple[List[Dict[str, Any]], int]:
    cases: List[Dict[str, Any]] = []
    idx = start_index
    for rule in rules:
        cases.append(
            {
                "id": _case_id("TC-DT", idx),
                "technique": "black-box",
                "designMethod": "DecisionTable",
                "title": f"决策表-{rule.get('conditions', '')[:40]}",
                "precondition": "决策表规则已配置",
                "input": rule.get("conditions", ""),
                "steps": "按条件组合提交数据",
                "expected": rule.get("expected", ""),
                "oracle": "",
                "priority": "high",
                "traceability": [],
            }
        )
        idx += 1
    return cases, idx


def _pairwise_combinations(factors: List[List[str]], labels: List[str], max_rows: int = 6) -> List[Dict[str, str]]:
    """Greedy pairwise coverage: each pair of factor levels appears together at least once."""
    if not factors:
        return []
    rows: List[Dict[str, str]] = []
    for values, label in zip(factors, labels):
        if not rows:
            rows = [{label: value} for value in values[: max_rows]]
            continue
        expanded: List[Dict[str, str]] = []
        for row in rows:
            for value in values:
                expanded.append({**row, label: value})
        rows = expanded[: max_rows * 2]

    seen_pairs = set()
    selected: List[Dict[str, str]] = []
    for row in rows:
        keys = list(row.keys())
        pairs = tuple(
            tuple(sorted((keys[i], row[keys[i]], keys[j], row[keys[j]])))
            for i in range(len(keys))
            for j in range(i + 1, len(keys))
        )
        if any(p not in seen_pairs for p in pairs) or not selected:
            selected.append(row)
            seen_pairs.update(pairs)
        if len(selected) >= max_rows:
            break
    return selected or rows[:max_rows]


def generate_combinatorial_cases(requirements: List[Dict[str, Any]], start_index: int = 1) -> Tuple[List[Dict[str, Any]], int]:
    """确定性 Combinatorial 用例生成器（Pairwise 两两覆盖）。

    从所有需求中收集枚举型因子及其可取值，使用贪心 Pairwise 算法减少用例数。
    若解析出 ≥2 个因子，则进行真正的 pairwise 组合；否则使用单因子遍历。
    """
    factors: List[List[str]] = []
    labels: List[str] = []
    seen_labels: set = set()

    # ── 从需求中收集所有枚举因子 ──────────────────────────────────────────
    for req in requirements:
        ranges = req.get("ranges") or {}
        enum_values = ranges.get("enum")
        if not (isinstance(enum_values, list) and len(enum_values) >= 2):
            continue

        # 优先用 inputFields 中的第一个枚举字段作为标签
        input_fields = req.get("inputFields") or []
        label = next(
            (f for f in input_fields if f not in seen_labels and f not in ("count", "durationSeconds", "landmarks")),
            None,
        )
        if label is None:
            # 无法确定字段名时用 feature 名称的首个单词
            label = (req.get("feature") or "factor").split()[0].lower()

        # 避免重复因子（同一 label 只取首次）
        if label in seen_labels:
            continue
        seen_labels.add(label)
        factors.append([str(v) for v in enum_values[:5]])
        labels.append(label)

    # ── 检测到训练计划类需求时，补充 skipRest 布尔因子 ──────────────────
    has_plan = any(
        "plan" in str(req.get("feature", "")).lower()
        or "难度" in str(req.get("feature", ""))
        or "difficulty" in " ".join(req.get("inputFields") or []).lower()
        for req in requirements
    )
    if has_plan and "skipRest" not in seen_labels:
        factors.append(["true", "false"])
        labels.append("skipRest")

    # ── 保底：若未能解析出 ≥2 个因子，使用通用占位 ──────────────────────
    if len(factors) < 2:
        factors = [["easy", "medium", "hard"], ["true", "false"]]
        labels = ["difficulty", "skipRest"]

    combos = _pairwise_combinations(factors, labels, max_rows=8)

    cases: List[Dict[str, Any]] = []
    idx = start_index

    # 获取可追溯的需求 ID
    req_ids = [str(req.get("id", "")) for req in requirements if req.get("id")]

    for combo in combos:
        input_desc = ", ".join(f"{key}={value}" for key, value in combo.items())
        cases.append(
            {
                "id": _case_id("TC-CB", idx),
                "technique": "black-box",
                "designMethod": "Combinatorial",
                "title": f"Pairwise组合-{input_desc}",
                "precondition": "相关模块已启用，接口可访问",
                "input": input_desc,
                "steps": "执行组合场景并记录结果",
                "expected": "各组合返回一致数据结构且无 5xx 错误",
                "oracle": "",
                "priority": "medium",
                "traceability": req_ids[:2],
            }
        )
        idx += 1
    return cases, idx



def build_coverage_items(requirements: List[Dict[str, Any]], methods_used: Set[str]) -> List[str]:
    items = [f"{req.get('feature')}:{req.get('id')}" for req in requirements]
    items.extend(sorted(methods_used))
    return items


def generate_blackbox_artifacts(requirements: List[Dict[str, Any]]) -> Dict[str, Any]:
    eq = build_equivalence_partitions(requirements)
    bva = build_boundary_values(requirements)
    dt_rules = build_decision_table_rules(requirements)

    cases: List[Dict[str, Any]] = []
    idx = 1
    ep_cases, idx = generate_ep_cases(requirements, idx)
    bva_cases, idx = generate_bva_cases(requirements, idx)
    dt_cases, idx = generate_decision_table_cases(dt_rules, idx)
    cb_cases, idx = generate_combinatorial_cases(requirements, idx)
    cases.extend(ep_cases + bva_cases + dt_cases + cb_cases)

    methods_used = {c["designMethod"] for c in cases}
    input_vars: List[str] = []
    for req in requirements:
        input_vars.extend(req.get("inputFields") or [])

    return {
        "inputVariables": sorted(set(input_vars)),
        "equivalencePartitions": eq,
        "boundaryValues": bva,
        "decisionTableRules": dt_rules,
        "testcases": cases,
        "coverageItems": build_coverage_items(requirements, methods_used),
    }
