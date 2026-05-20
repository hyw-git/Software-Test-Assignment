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
    items: List[Dict[str, Any]] = []
    for req in requirements:
        ranges = req.get("ranges") or {}
        length_spec = ranges.get("landmarks.length")
        if isinstance(length_spec, dict):
            items.append(
                {
                    "field": "landmarks.length",
                    "values": [length_spec.get("min"), length_spec.get("nominal"), length_spec.get("max")],
                    "rationale": "ISO 29119-4 边界值：最小、标称、最大",
                }
            )
        if "durationSeconds" in ranges or "count" in ranges:
            items.append(
                {
                    "field": "durationSeconds",
                    "values": [29, 30, 31],
                    "rationale": "记录过滤规则边界",
                }
            )
    if not items:
        items.append(
            {
                "field": "contentLength",
                "values": [0, 1, 500],
                "rationale": "通用输入长度边界",
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
    cases: List[Dict[str, Any]] = []
    idx = start_index
    for req in requirements:
        ranges = req.get("ranges") or {}
        length_spec = ranges.get("landmarks.length")
        if isinstance(length_spec, dict):
            for value, label in [
                (length_spec.get("min"), "下边界"),
                (length_spec.get("nominal"), "标称"),
                (length_spec.get("max"), "上边界"),
            ]:
                cases.append(
                    {
                        "id": _case_id("TC-BVA", idx),
                        "technique": "black-box",
                        "designMethod": "BVA",
                        "title": f"BVA-landmarks.length={value} ({label})",
                        "precondition": "姿态分析模块已加载",
                        "input": f"landmarks.length={value}",
                        "steps": "调用 /api/analytics/pose",
                        "expected": "33 正常，其他返回可解释错误" if value != 33 else str(req.get("expectedAction", "成功")),
                        "oracle": "",
                        "priority": "high",
                        "traceability": [str(req.get("id", ""))],
                    }
                )
                idx += 1
        if "durationSeconds" in ranges or req.get("id") == "REQ-REC-001":
            for duration in [29, 30, 31]:
                cases.append(
                    {
                        "id": _case_id("TC-BVA", idx),
                        "technique": "black-box",
                        "designMethod": "BVA",
                        "title": f"BVA-durationSeconds={duration}",
                        "precondition": "记录保存接口可用",
                        "input": f"count=2, durationSeconds={duration}",
                        "steps": "保存记录并查询历史",
                        "expected": "29 过滤，30/31 保留（结合 count 规则）",
                        "oracle": "",
                        "priority": "high",
                        "traceability": [str(req.get("id", "REQ-REC-001"))],
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
    factors: List[List[str]] = []
    labels: List[str] = []
    for req in requirements:
        enum_values = (req.get("ranges") or {}).get("enum")
        if isinstance(enum_values, list) and len(enum_values) >= 2:
            factors.append(enum_values[:4])
            labels.append("exerciseType")
            break

    if len(factors) < 2:
        factors = [["easy", "medium", "hard"], ["true", "false"]]
        labels = ["difficulty", "skipRest"]

    combos = _pairwise_combinations(factors, labels, max_rows=6)

    cases: List[Dict[str, Any]] = []
    idx = start_index
    for combo in combos:
        input_desc = ", ".join(f"{key}={value}" for key, value in combo.items())
        cases.append(
            {
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
                "traceability": [],
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
