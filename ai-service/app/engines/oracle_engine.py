import re
from typing import Any, Dict, List


ORACLE_RULES = [
    (
        re.compile(r"landmarks\.length\s*=\s*33", re.I),
        "HTTP 200；响应包含 count/score/feedback/state/angle",
    ),
    (
        re.compile(r"landmarks\.length\s*=\s*(32|34)", re.I),
        "HTTP 4xx 或业务错误码；错误信息说明 landmarks 数量非法",
    ),
    (
        re.compile(r"exerciseType\s*=\s*INVALID", re.I),
        "HTTP 4xx；响应不得为 5xx；错误包含 exerciseType",
    ),
    (
        re.compile(r"count\s*=\s*2.*durationSeconds\s*=\s*29", re.I),
        "历史记录中不存在该条；仪表盘统计不增加",
    ),
    (
        re.compile(r"count\s*=\s*2.*durationSeconds\s*=\s*(30|31)", re.I),
        "记录成功入库；历史与统计更新",
    ),
    (
        re.compile(r"UP.*DESCENDING.*DOWN.*ASCENDING.*UP", re.I),
        "最终 state=UP 且 count 较初始值 +1",
    ),
    (
        re.compile(r"UP.*DESCENDING.*UP", re.I),
        "count 保持不变；feedback 提示动作未完成",
    ),
    (
        re.compile(r"卡路里|calorie|MET", re.I),
        "卡路里 ≈ MET × weightKg × (durationSeconds/3600)，允许 ±5% 误差",
    ),
]


def synthesize_oracle(case: Dict[str, Any], requirements: List[Dict[str, Any]]) -> str:
    if str(case.get("oracle", "")).strip():
        return str(case["oracle"]).strip()

    blob = " ".join(
        [
            str(case.get("title", "")),
            str(case.get("input", "")),
            str(case.get("expected", "")),
            str(case.get("steps", "")),
        ]
    )
    for pattern, oracle in ORACLE_RULES:
        if pattern.search(blob):
            return oracle

    trace = case.get("traceability") or []
    for req_id in trace:
        for req in requirements:
            if req.get("id") == req_id:
                return f"断言满足需求 {req_id}：{req.get('expectedAction', case.get('expected', ''))}"

    method = str(case.get("designMethod", ""))
    if method == "DecisionTable":
        return f"决策表预期：{case.get('expected', '规则成立')}"
    if method == "BVA":
        return f"边界断言：{case.get('expected', '边界行为符合规格')}"
    if method == "EP":
        return f"等价类断言：{case.get('expected', '有效/无效类行为符合规格')}"
    if method == "StateTransition":
        return str(case.get("expected", "状态序列结果可观测"))

    return str(case.get("expected", "可重复观测的系统输出"))


def attach_oracles(testcases: List[Dict[str, Any]], requirements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    enriched: List[Dict[str, Any]] = []
    for case in testcases:
        item = dict(case)
        item["oracle"] = synthesize_oracle(item, requirements)
        item["oracleSource"] = "rule-oracle-engine"
        enriched.append(item)
    return enriched
