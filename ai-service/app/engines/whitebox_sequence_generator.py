"""CFG-based greedy test sequence generation for Java white-box coverage."""

from __future__ import annotations

from collections import deque
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .input_hint_generator import generate_input_hints


def generate_test_sequences(
    analysis: Dict[str, Any],
    coverage_items: List[Dict[str, Any]],
    warnings: List[str] | None = None,
) -> List[Dict[str, Any]]:
    """Generate design-level sequences by searching paths over each method CFG."""
    selected_items = [item for item in coverage_items if isinstance(item, dict) and bool(item.get("selected", True))]
    by_method = _group_by_method(selected_items)
    sequence_index = 1
    sequences: List[Dict[str, Any]] = []

    for class_item in analysis.get("classes", []) or []:
        for method in class_item.get("methods", []) or []:
            method_id = str(method.get("id") or "")
            method_items = by_method.get(method_id, [])
            if not method_items:
                continue

            covered: set[str] = set()
            branch_items = [item for item in method_items if item.get("type") == "branch"]
            statement_items = [item for item in method_items if item.get("type") == "statement"]
            manual_items = [item for item in method_items if item.get("type") == "manual"]

            for item in branch_items:
                if str(item.get("id") or "") in covered:
                    continue
                sequence, sequence_index = _sequence_for_branch(method, item, method_items, sequence_index, warnings)
                covered.update(sequence.get("coverageTargets", []))
                sequences.append(sequence)

            for item in statement_items:
                if str(item.get("id") or "") in covered:
                    continue
                sequence, sequence_index = _sequence_for_statement(method, item, method_items, sequence_index, warnings)
                covered.update(sequence.get("coverageTargets", []))
                sequences.append(sequence)

            for item in manual_items:
                sequence, sequence_index = _manual_sequence(method, item, sequence_index)
                sequences.append(sequence)

    global_manual = [item for item in selected_items if item.get("type") == "manual" and not item.get("methodId")]
    for item in global_manual:
        sequence, sequence_index = _manual_sequence({}, item, sequence_index)
        sequences.append(sequence)

    return sequences


def find_path(cfg: Dict[str, Any], start_node_id: str, target_node_id: str) -> List[Dict[str, Any]] | None:
    """Return a node/edge step path from start to target, or None."""
    nodes = _nodes_by_id(cfg)
    if start_node_id not in nodes or target_node_id not in nodes:
        return None
    if start_node_id == target_node_id:
        return [_node_step(nodes[start_node_id])]

    adjacency = _adjacency(cfg)
    queue = deque([(start_node_id, [_node_step(nodes[start_node_id])], {start_node_id})])
    while queue:
        node_id, steps, visited = queue.popleft()
        for edge in adjacency.get(node_id, []):
            next_node = str(edge.get("to") or "")
            if not next_node or next_node in visited or next_node not in nodes:
                continue
            next_steps = steps + [_edge_step(edge), _node_step(nodes[next_node])]
            if next_node == target_node_id:
                return next_steps
            queue.append((next_node, next_steps, visited | {next_node}))
    return None


def find_path_to_any_exit(cfg: Dict[str, Any], start_node_id: str, exit_node_ids: Iterable[str]) -> List[Dict[str, Any]] | None:
    """Return a path from start to the first reachable exit node."""
    for exit_id in exit_node_ids:
        path = find_path(cfg, start_node_id, str(exit_id))
        if path:
            return path
    return None


def _sequence_for_branch(
    method: Dict[str, Any],
    item: Dict[str, Any],
    method_items: List[Dict[str, Any]],
    sequence_index: int,
    warnings: List[str] | None,
) -> Tuple[Dict[str, Any], int]:
    cfg = method.get("cfg") if isinstance(method.get("cfg"), dict) else {}
    nodes = _nodes_by_id(cfg)
    edges = _edges_by_id(cfg)
    edge_id = str(item.get("sourceEdgeId") or "")
    target_edge = edges.get(edge_id)
    method_id = str(item.get("methodId") or method.get("id") or "")

    if not target_edge:
        message = f"No CFG edge found for coverage item {item.get('id')}."
        _append_warning(warnings, message)
        return _review_sequence(method_id, item, sequence_index, message), sequence_index + 1

    entry = str(cfg.get("entryNodeId") or "")
    exits = [str(exit_id) for exit_id in cfg.get("exitNodeIds", []) or []]
    prefix = find_path(cfg, entry, str(target_edge.get("from") or ""))
    suffix = find_path_to_any_exit(cfg, str(target_edge.get("to") or ""), exits)
    if not prefix or not suffix:
        message = f"No complete CFG path found for coverage item {item.get('id')} via edge {edge_id}."
        _append_warning(warnings, message)
        path = [_edge_step(target_edge)]
        return _review_sequence(method_id, item, sequence_index, message, path), sequence_index + 1

    path = prefix + [_edge_step(target_edge)] + suffix
    path = _dedupe_adjacent_duplicate_nodes(path)
    coverage_targets = _coverage_targets_for_path(path, method_items)
    hint_bundle = _hints_for_path(method, path)
    oracle_hints = _oracle_hints_for_path(path)
    exception_trigger_hints = _exception_trigger_hints_for_branch(method, item) if str(target_edge.get("type") or "") == "exception" else []
    needs_review = bool(hint_bundle["needsReview"] or oracle_hints["needsReview"])
    if str(item.get("branchLabel") or "").lower() not in {"true", "false"}:
        needs_review = True
    if str(target_edge.get("type") or "") == "exception" and not exception_trigger_hints:
        needs_review = True
    if str(target_edge.get("type") or "") == "exception":
        hint_bundle["setupHints"].append("Configure one of the possible throw sites to throw the caught exception.")
        if not exception_trigger_hints:
            hint_bundle["setupHints"].append("No concrete throw site was identified; reviewer/LLM must map the catch path to a mock or input setup.")

    sequence = {
        "id": f"SEQ-WB-{sequence_index:03d}",
        "methodId": method_id,
        "title": _branch_title(method, item, path),
        "coverageTargets": coverage_targets or [str(item.get("id") or "")],
        "path": path,
        "inputHints": hint_bundle["inputHints"],
        "pathConstraints": hint_bundle["pathConstraints"],
        "setupHints": hint_bundle["setupHints"],
        "constraintConflicts": hint_bundle["constraintConflicts"],
        "exceptionTriggerHints": exception_trigger_hints,
        "oracleHints": oracle_hints,
        "expectedBehaviorHint": _expected_branch_behavior(item),
        "needsReview": needs_review,
    }
    return sequence, sequence_index + 1


def _sequence_for_statement(
    method: Dict[str, Any],
    item: Dict[str, Any],
    method_items: List[Dict[str, Any]],
    sequence_index: int,
    warnings: List[str] | None,
) -> Tuple[Dict[str, Any], int]:
    cfg = method.get("cfg") if isinstance(method.get("cfg"), dict) else {}
    target_node_id = str(item.get("sourceNodeId") or "")
    method_id = str(item.get("methodId") or method.get("id") or "")
    entry = str(cfg.get("entryNodeId") or "")
    exits = [str(exit_id) for exit_id in cfg.get("exitNodeIds", []) or []]

    prefix = find_path(cfg, entry, target_node_id)
    suffix = find_path_to_any_exit(cfg, target_node_id, exits)
    if not prefix or not suffix:
        message = f"No complete CFG path found for statement coverage item {item.get('id')} at node {target_node_id}."
        _append_warning(warnings, message)
        return _review_sequence(method_id, item, sequence_index, message), sequence_index + 1

    path = prefix + suffix[1:]
    path = _dedupe_adjacent_duplicate_nodes(path)
    coverage_targets = _coverage_targets_for_path(path, method_items)
    hint_bundle = _hints_for_path(method, path)
    oracle_hints = _oracle_hints_for_path(path)
    sequence = {
        "id": f"SEQ-WB-{sequence_index:03d}",
        "methodId": method_id,
        "title": f"Cover statement {item.get('sourceStatementId') or item.get('id')}",
        "coverageTargets": coverage_targets or [str(item.get("id") or "")],
        "path": path,
        "inputHints": hint_bundle["inputHints"],
        "pathConstraints": hint_bundle["pathConstraints"],
        "setupHints": hint_bundle["setupHints"],
        "constraintConflicts": hint_bundle["constraintConflicts"],
        "exceptionTriggerHints": [],
        "oracleHints": oracle_hints,
        "expectedBehaviorHint": f"The method should execute the CFG node {target_node_id} at {item.get('location', 'the selected location')}.",
        "needsReview": bool(hint_bundle["needsReview"] or oracle_hints["needsReview"]),
    }
    return sequence, sequence_index + 1


def _manual_sequence(method: Dict[str, Any], item: Dict[str, Any], sequence_index: int) -> Tuple[Dict[str, Any], int]:
    method_id = str(item.get("methodId") or method.get("id") or "")
    return (
        {
            "id": f"SEQ-WB-{sequence_index:03d}",
            "methodId": method_id,
            "title": f"Manual coverage: {item.get('target', item.get('id', 'review item'))}",
            "coverageTargets": [str(item.get("id"))],
            "path": [{"type": "manual", "target": item.get("target", "")}],
            "inputHints": {},
            "pathConstraints": [],
            "setupHints": [],
            "constraintConflicts": [],
            "exceptionTriggerHints": [],
            "oracleHints": _empty_oracle_hints(),
            "expectedBehaviorHint": "Manual coverage item requires reviewer-supplied input data and oracle.",
            "needsReview": True,
        },
        sequence_index + 1,
    )


def _review_sequence(
    method_id: str,
    item: Dict[str, Any],
    sequence_index: int,
    message: str,
    path: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    return {
        "id": f"SEQ-WB-{sequence_index:03d}",
        "methodId": method_id,
        "title": f"Review coverage path for {item.get('id', 'coverage item')}",
        "coverageTargets": [str(item.get("id"))],
        "path": path or [{"type": "manual", "target": item.get("target", ""), "warning": message}],
        "inputHints": {},
        "pathConstraints": [],
        "setupHints": [],
        "constraintConflicts": [],
        "exceptionTriggerHints": [],
        "oracleHints": _empty_oracle_hints(),
        "expectedBehaviorHint": message,
        "needsReview": True,
    }


def _coverage_targets_for_path(path: List[Dict[str, Any]], items: List[Dict[str, Any]]) -> List[str]:
    node_ids = {str(step.get("nodeId") or "") for step in path if step.get("type") == "node"}
    edge_ids = {str(step.get("edgeId") or "") for step in path if step.get("type") == "edge"}
    targets: List[str] = []
    for item in items:
        item_id = str(item.get("id") or "")
        if not item_id:
            continue
        if item.get("type") == "statement" and str(item.get("sourceNodeId") or "") in node_ids:
            targets.append(item_id)
        elif item.get("type") == "branch" and str(item.get("sourceEdgeId") or "") in edge_ids:
            targets.append(item_id)
    return _unique(targets)


def _input_hints_for_path(path: List[Dict[str, Any]]) -> Tuple[Dict[str, Any], bool]:
    bundle = _hints_for_path({}, path)
    return bundle["inputHints"], bool(bundle["needsReview"])


def _hints_for_path(method: Dict[str, Any], path: List[Dict[str, Any]]) -> Dict[str, Any]:
    param_names = {str(param.get("name") or "") for param in method.get("parameters", []) or [] if isinstance(param, dict)}
    input_hints: Dict[str, Any] = {}
    path_constraints: List[str] = []
    setup_hints: List[str] = []
    conflicts: List[str] = []
    needs_review = False

    hints: Dict[str, Any] = {}
    for step in path:
        if step.get("type") != "edge":
            continue
        label = str(step.get("label") or "").lower()
        condition = str(step.get("condition") or "").strip()
        if label not in {"true", "false"}:
            if condition:
                path_constraints.append(condition)
            continue
        if not condition:
            needs_review = True
            continue
        expected_text = "true" if label == "true" else "false"
        path_constraints.append(f"{condition} == {expected_text}")
        edge_hints, edge_needs_review = generate_input_hints(condition, label == "true")
        if not edge_hints:
            setup_hints.append(f"Need reviewer/LLM to map this path constraint to external input or mock setup: {condition} == {expected_text}")
        for key, value in edge_hints.items():
            if key in param_names:
                if key in input_hints and input_hints[key] != value:
                    conflicts.append(f"{key}: {input_hints[key]!r} conflicts with {value!r} for {condition}")
                    needs_review = True
                else:
                    input_hints[key] = value
            else:
                setup_hints.append(_setup_hint_for_condition(condition, key, value))
        needs_review = needs_review or edge_needs_review
    # Keep the old helper shape available for compatibility while returning richer fields.
    hints.update(input_hints)
    internal_constraints = [
        item
        for item in path_constraints
        if item and not any(re.search(rf"\b{re.escape(param)}\b", item) for param in param_names if param)
    ]
    if internal_constraints:
        needs_review = True
    return {
        "inputHints": hints,
        "pathConstraints": _unique(path_constraints),
        "setupHints": _unique(setup_hints),
        "constraintConflicts": _unique(conflicts),
        "needsReview": bool(needs_review or conflicts),
    }


def _nodes_by_id(cfg: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {str(node.get("id")): node for node in cfg.get("nodes", []) or [] if isinstance(node, dict)}


def _edges_by_id(cfg: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {str(edge.get("id")): edge for edge in cfg.get("edges", []) or [] if isinstance(edge, dict)}


def _adjacency(cfg: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for edge in cfg.get("edges", []) or []:
        if not isinstance(edge, dict):
            continue
        grouped.setdefault(str(edge.get("from") or ""), []).append(edge)
    return grouped


def _node_step(node: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "type": "node",
        "nodeId": node.get("id"),
        "nodeType": node.get("type"),
        "line": node.get("line"),
        "text": node.get("text", ""),
        "statementId": node.get("statementId"),
        "decisionId": node.get("decisionId"),
    }


def _edge_step(edge: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "type": "edge",
        "edgeId": edge.get("id"),
        "from": edge.get("from"),
        "to": edge.get("to"),
        "label": edge.get("label") or edge.get("type"),
        "edgeType": edge.get("type"),
        "condition": edge.get("condition", ""),
    }


def _dedupe_adjacent_duplicate_nodes(path: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    for step in path:
        if (
            result
            and step.get("type") == "node"
            and result[-1].get("type") == "node"
            and step.get("nodeId") == result[-1].get("nodeId")
        ):
            continue
        result.append(step)
    return result


def _group_by_method(items: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for item in items:
        method_id = str(item.get("methodId") or "")
        grouped.setdefault(method_id, []).append(item)
    return grouped


def _branch_title(method: Dict[str, Any], item: Dict[str, Any], path: List[Dict[str, Any]] | None = None) -> str:
    method_name = str(method.get("name") or item.get("methodName") or "method")
    label = str(item.get("branchLabel") or item.get("branchValue") or "branch")
    condition = _decision_condition(method, str(item.get("sourceDecisionId") or ""))
    kind = _decision_kind(method, str(item.get("sourceDecisionId") or ""))
    normalized = label.lower()
    if kind == "try" and normalized == "normal":
        suffix = _first_boolean_branch_suffix(path or [], str(item.get("sourceEdgeId") or ""))
        return f"Cover {method_name} normal try path{suffix}"
    if kind == "try" and normalized.startswith("exception"):
        exception_type = label.split(":", 1)[1] if ":" in label else "exception"
        return f"Cover {method_name} exception path: {exception_type}"
    if kind == "switch":
        return f"Cover {method_name} switch case {label}"
    if normalized in {"true", "false"} and condition:
        return f"Cover {method_name} branch: {condition} == {normalized}"
    return f"Cover {method_name} {label} branch"


def _first_boolean_branch_suffix(path: List[Dict[str, Any]], after_edge_id: str) -> str:
    passed_target = not after_edge_id
    for step in path:
        if step.get("type") != "edge":
            continue
        if str(step.get("edgeId") or "") == after_edge_id:
            passed_target = True
            continue
        if not passed_target:
            continue
        label = str(step.get("label") or "").lower()
        condition = str(step.get("condition") or "").strip()
        if label in {"true", "false"} and condition:
            return f" with {condition} == {label}"
    return ""


def _expected_branch_behavior(item: Dict[str, Any]) -> str:
    label = item.get("branchLabel", item.get("branchValue"))
    return (
        f"The method should take CFG edge {item.get('sourceEdgeId')} for {label} branch of "
        f"{item.get('sourceDecisionId')} and then follow a reachable path to method exit."
    )


def _decision_condition(method: Dict[str, Any], decision_id: str) -> str:
    for decision in method.get("decisions", []) or []:
        if str(decision.get("id") or "") == decision_id:
            return str(decision.get("condition") or "")
    return ""


def _decision_kind(method: Dict[str, Any], decision_id: str) -> str:
    for decision in method.get("decisions", []) or []:
        if str(decision.get("id") or "") == decision_id:
            return str(decision.get("kind") or "")
    return ""


def _exception_trigger_hints_for_branch(method: Dict[str, Any], item: Dict[str, Any]) -> List[Dict[str, Any]]:
    decision_id = str(item.get("sourceDecisionId") or "")
    for decision in method.get("decisions", []) or []:
        if str(decision.get("id") or "") == decision_id:
            hints = decision.get("exceptionTriggerHints", [])
            return [hint for hint in hints if isinstance(hint, dict)]
    return []


def _setup_hint_for_condition(condition: str, variable: str, value: Any) -> str:
    return f"Set up or mock internal value '{variable}' as {value!r} to satisfy path constraint: {condition}"


def _oracle_hints_for_path(path: List[Dict[str, Any]]) -> Dict[str, Any]:
    exit_node = None
    for step in reversed(path):
        if step.get("type") != "node":
            continue
        node_type = str(step.get("nodeType") or "")
        if node_type in {"return", "throw", "catch"}:
            exit_node = step
            break
    if not exit_node:
        return _empty_oracle_hints()

    node_type = str(exit_node.get("nodeType") or "")
    text = _readable_return_text(str(exit_node.get("text") or ""))
    exit_kind = "catch" if node_type == "catch" else "throw" if node_type == "throw" else "return"
    return {
        "exitKind": exit_kind,
        "returnLine": exit_node.get("line") if exit_kind == "return" else None,
        "returnText": text,
        "httpStatusHint": _http_status_hint(text),
        "bodyHint": _body_hint(text),
        "needsReview": True,
    }


def _empty_oracle_hints() -> Dict[str, Any]:
    return {
        "exitKind": "normal",
        "returnLine": None,
        "returnText": "",
        "httpStatusHint": "unknown",
        "bodyHint": "",
        "needsReview": True,
    }


def _http_status_hint(text: str) -> str:
    if "ResponseEntity.ok" in text:
        return "200"
    if "badRequest" in text:
        return "400"
    if "internalServerError" in text:
        return "500"
    return "unknown"


def _body_hint(text: str) -> str:
    cleaned = _readable_return_text(str(text or ""))
    return cleaned[:240]


def _readable_return_text(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
    if not cleaned:
        return ""
    if cleaned.endswith("(") or cleaned.count("(") > cleaned.count(")"):
        for pattern in (
            "ResponseEntity.internalServerError().body",
            "ResponseEntity.badRequest().body",
            "ResponseEntity.ok",
            "Map.of",
        ):
            if pattern in cleaned:
                return f"{pattern}(...)"
    return cleaned[:500]


def _append_warning(warnings: List[str] | None, message: str) -> None:
    if warnings is not None and message not in warnings:
        warnings.append(message)


def _unique(values: List[str]) -> List[str]:
    seen = set()
    result = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result
