import json
import re
from typing import Any, Dict, List, Tuple


DEFAULT_SQUAT_STATE_MODEL = {
    "states": ["UP", "DESCENDING", "DOWN", "ASCENDING", "COOLDOWN"],
    "transitions": [
        {"from": "UP", "to": "DESCENDING", "condition": "angle decreasing"},
        {"from": "DESCENDING", "to": "DOWN", "condition": "angle < threshold stable"},
        {"from": "DOWN", "to": "ASCENDING", "condition": "angle increasing"},
        {"from": "ASCENDING", "to": "UP", "condition": "angle restored, count+1"},
        {"from": "UP", "to": "COOLDOWN", "condition": "after valid rep"},
        {"from": "COOLDOWN", "to": "UP", "condition": "cooldown elapsed"},
    ],
    "coverageCriterion": "all-states",
}


def parse_custom_state_model(description: str) -> Dict[str, Any]:
    text = str(description or "").strip()
    if not text:
        return {}

    if text.startswith("{"):
        try:
            payload = json.loads(text)
            if isinstance(payload, dict) and payload.get("states"):
                payload.setdefault("source", "user-json-state-model")
                return payload
        except json.JSONDecodeError:
            pass

    states = re.findall(r"\b([A-Z][A-Z0-9_]*)\b", text)
    states = list(dict.fromkeys(states))[:12]
    transitions: List[Dict[str, str]] = []
    for match in re.finditer(r"([A-Z][A-Z0-9_]*)\s*(?:->|→|—>)\s*([A-Z][A-Z0-9_]*)", text):
        transitions.append(
            {
                "from": match.group(1),
                "to": match.group(2),
                "condition": "parsed from whitebox description",
            }
        )

    if states:
        return {
            "states": states,
            "transitions": transitions or [{"from": states[i], "to": states[(i + 1) % len(states)], "condition": "sequential"} for i in range(min(len(states), 4))],
            "coverageCriterion": "all-states",
            "source": "parsed-whitebox-description",
        }
    return {}


def build_state_model(
    requirements: List[Dict[str, Any]],
    coverage_criterion: str = "all-states",
    whitebox_description: str = "",
) -> Dict[str, Any]:
    custom = parse_custom_state_model(whitebox_description)
    if custom:
        custom["coverageCriterion"] = coverage_criterion
        return custom

    for req in requirements:
        feature = str(req.get("feature", ""))
        if "状态" in feature or "state" in feature.lower():
            model = dict(DEFAULT_SQUAT_STATE_MODEL)
            model["coverageCriterion"] = coverage_criterion
            model["source"] = "rule-whitebox-engine"
            return model
    return {}


def _build_transition_paths(transitions: List[Dict[str, str]], states: List[str], criterion: str) -> List[List[str]]:
    sequences: List[List[str]] = []
    if criterion == "all-transitions":
        for tr in transitions:
            sequences.append([tr.get("from", ""), tr.get("to", "")])
        return sequences or [[s] for s in states]

    sequences = [[state] for state in states]
    if transitions:
        path = [transitions[0].get("from", states[0])]
        for tr in transitions:
            path.append(tr.get("to", ""))
        if len(path) >= 2:
            sequences.append(path)
    if len(states) >= 4:
        sequences.append(states[:4] + [states[0]])
    return sequences


def generate_state_transition_sequences(
    state_model: Dict[str, Any],
    coverage_criterion: str = "all-states",
    start_index: int = 1,
) -> Tuple[List[Dict[str, Any]], int]:
    if not state_model:
        return [], start_index

    states = state_model.get("states") or []
    transitions = state_model.get("transitions") or []
    criterion = coverage_criterion or state_model.get("coverageCriterion", "all-states")
    sequences = _build_transition_paths(transitions, states, criterion)

    if ["UP", "DESCENDING", "UP"] not in sequences and "UP" in states:
        sequences.append(["UP", "DESCENDING", "UP"])

    cases: List[Dict[str, Any]] = []
    idx = start_index
    for seq in sequences:
        seq_label = "->".join(seq)
        is_invalid_short = len(seq) == 3 and seq[0] == seq[-1] and "DOWN" not in seq
        cases.append(
            {
                "id": f"TC-ST-{idx:03d}",
                "technique": "white-box",
                "designMethod": "StateTransition",
                "title": f"状态迁移-{seq_label}",
                "precondition": f"状态机初始状态 {states[0] if states else 'INIT'}",
                "input": f"帧序列触发: {seq_label}",
                "steps": "按序列提交连续帧并观察 state 与 count",
                "expected": "非法短循环不计数" if is_invalid_short else "按覆盖准则完成迁移",
                "oracle": "count 不变" if is_invalid_short else "观测状态序列与计数符合模型",
                "priority": "high",
                "traceability": ["REQ-POSE-002"],
            }
        )
        idx += 1
    return cases, idx
