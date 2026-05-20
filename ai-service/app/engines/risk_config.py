"""Configurable risk matrix for FR 2.0 (impact × likelihood)."""

FEATURE_WEIGHTS = {
    "姿态分析": {"impact": 5, "likelihood": 4, "rationale": "Core real-time pose API"},
    "状态机计数": {"impact": 5, "likelihood": 4, "rationale": "Incorrect counting affects user trust"},
    "记录过滤": {"impact": 4, "likelihood": 3, "rationale": "Bad filter corrupts analytics"},
    "训练计划": {"impact": 3, "likelihood": 3, "rationale": "Plan flow errors reduce engagement"},
    "仪表盘统计": {"impact": 3, "likelihood": 3, "rationale": "Stats drive goals and feedback"},
    "通用功能": {"impact": 3, "likelihood": 3, "rationale": "Default weight"},
}

PRIORITY_THRESHOLDS = [
    (16, "high"),
    (9, "medium"),
    (0, "low"),
]


def get_risk_matrix() -> dict:
    return {
        "formula": "riskScore = impact × likelihood",
        "priorityThresholds": [{"minScore": t[0], "priority": t[1]} for t in PRIORITY_THRESHOLDS],
        "featureWeights": FEATURE_WEIGHTS,
    }
