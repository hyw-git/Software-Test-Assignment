"""CFG-based coverage item generation for Java white-box analysis."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple


SUPPORTED_CRITERIA = {"statement", "branch", "statement+branch"}
BRANCH_EDGE_TYPES = {"true", "false", "case", "default", "exception", "loop-exit", "loop-back", "normal"}
BRANCH_LABELS = {"true", "false", "case", "default", "exception", "normal"}


def normalize_coverage_criterion(value: str) -> Tuple[str, List[str]]:
    criterion = str(value or "").strip().lower()
    warnings: List[str] = []
    aliases = {
        "statements": "statement",
        "statement coverage": "statement",
        "statement-coverage": "statement",
        "decision": "branch",
        "decision coverage": "branch",
        "branch-coverage": "branch",
        "decision+statement": "statement+branch",
        "branch+statement": "statement+branch",
        "all-states": "statement+branch",
        "all-transitions": "statement+branch",
        "all-transition-pairs": "statement+branch",
        "": "statement+branch",
    }
    normalized = aliases.get(criterion, criterion)
    if normalized not in SUPPORTED_CRITERIA:
        warnings.append(f"Unsupported white-box coverage criterion '{value}', using statement+branch.")
        normalized = "statement+branch"
    elif normalized != criterion:
        warnings.append(f"Coverage criterion '{value}' was normalized to '{normalized}' for Java white-box analysis.")
    return normalized, warnings


def generate_coverage_items(
    analysis: Dict[str, Any],
    coverage_criterion: str,
    reviewer_overrides: Dict[str, Any] | None = None,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Create selected coverage items from CFG nodes and decision edges."""
    criterion, warnings = normalize_coverage_criterion(coverage_criterion)
    overrides = reviewer_overrides if isinstance(reviewer_overrides, dict) else {}
    selection = overrides.get("coverageItemSelection", {})
    if not isinstance(selection, dict):
        selection = {}

    source_name = str(analysis.get("sourceName") or "JavaSource.java")
    include_statement = criterion in {"statement", "statement+branch"}
    include_branch = criterion in {"branch", "statement+branch"}
    items: List[Dict[str, Any]] = []
    statement_index = 1
    branch_index = 1

    for class_item in analysis.get("classes", []) or []:
        class_name = str(class_item.get("name") or "JavaClass")
        for method in class_item.get("methods", []) or []:
            method_id = str(method.get("id") or "")
            cfg = method.get("cfg") if isinstance(method.get("cfg"), dict) else {}
            nodes = cfg.get("nodes", []) if isinstance(cfg.get("nodes"), list) else []
            edges = cfg.get("edges", []) if isinstance(cfg.get("edges"), list) else []
            nodes_by_id = {str(node.get("id")): node for node in nodes if isinstance(node, dict)}

            if include_statement:
                for node in nodes:
                    if not isinstance(node, dict):
                        continue
                    statement_id = str(node.get("statementId") or "")
                    if not statement_id:
                        continue
                    node_type = str(node.get("type") or "")
                    if node_type not in {"statement", "decision", "return", "throw", "catch"}:
                        continue
                    line = node.get("line")
                    item_id = f"COV-STMT-{statement_index:03d}"
                    statement_index += 1
                    items.append(
                        _with_selection(
                            {
                                "id": item_id,
                                "type": "statement",
                                "methodId": method_id,
                                "className": class_name,
                                "methodName": method.get("name", ""),
                                "location": _location(source_name, line),
                                "target": f"Execute {node.get('kind', node_type)} at line {line}",
                                "sourceStatementId": statement_id,
                                "sourceNodeId": node.get("id", ""),
                                "selected": True,
                            },
                            selection,
                        )
                    )

            if include_branch:
                decision_edges = _decision_branch_edges(edges, nodes_by_id)
                for decision_id, decision_node, outgoing_edges in decision_edges:
                    exception_count = sum(1 for edge in outgoing_edges if _branch_label(edge).lower().startswith("exception"))
                    exception_index = 0
                    for edge in outgoing_edges:
                        line = decision_node.get("line")
                        condition = str(edge.get("condition") or _decision_condition(method, decision_id) or decision_node.get("text") or "decision")
                        label = _branch_label(edge)
                        if label.lower().startswith("exception"):
                            exception_index += 1
                        suffix = _branch_suffix(label, exception_index if exception_count > 1 and label.lower().startswith("exception") else None)
                        item_id = f"COV-BR-{branch_index:03d}-{suffix}"
                        items.append(
                            _with_selection(
                                {
                                    "id": item_id,
                                    "type": "branch",
                                    "methodId": method_id,
                                    "className": class_name,
                                    "methodName": method.get("name", ""),
                                    "location": _location(source_name, line),
                                    "target": _branch_target(decision_node, label, condition),
                                    "sourceDecisionId": decision_id,
                                    "sourceNodeId": decision_node.get("id", ""),
                                    "sourceEdgeId": edge.get("id", ""),
                                    "branchLabel": label,
                                    "branchValue": _branch_value(label),
                                    "selected": True,
                                },
                                selection,
                            )
                        )
                    branch_index += 1

    manual_items = overrides.get("manualCoverageItems", [])
    if isinstance(manual_items, list):
        for index, item in enumerate(manual_items, start=1):
            if not isinstance(item, dict):
                continue
            manual = {
                "id": str(item.get("id") or f"COV-MANUAL-{index:03d}"),
                "type": str(item.get("type") or "manual"),
                "methodId": str(item.get("methodId") or ""),
                "location": str(item.get("location") or "manual-review"),
                "target": str(item.get("target") or item.get("description") or "Manual coverage item"),
                "selected": bool(item.get("selected", True)),
                "needsReview": True,
            }
            for key in ("className", "methodName", "sourceStatementId", "sourceDecisionId", "sourceNodeId", "sourceEdgeId"):
                if item.get(key) is not None:
                    manual[key] = item.get(key)
            items.append(_with_selection(manual, selection))

    return items, warnings


def _decision_branch_edges(edges: List[Dict[str, Any]], nodes_by_id: Dict[str, Dict[str, Any]]) -> List[Tuple[str, Dict[str, Any], List[Dict[str, Any]]]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        from_node = nodes_by_id.get(str(edge.get("from") or ""))
        if not from_node or from_node.get("type") != "decision":
            continue
        edge_type = str(edge.get("type") or "")
        label = str(edge.get("label") or "")
        if edge_type not in BRANCH_EDGE_TYPES and not any(label.startswith(item) for item in BRANCH_LABELS):
            continue
        decision_id = str(from_node.get("decisionId") or "")
        if not decision_id:
            continue
        grouped.setdefault(decision_id, []).append(edge)

    result: List[Tuple[str, Dict[str, Any], List[Dict[str, Any]]]] = []
    for decision_id, outgoing in grouped.items():
        from_node = nodes_by_id.get(str(outgoing[0].get("from") or ""), {})
        result.append((decision_id, from_node, outgoing))
    return result


def _decision_condition(method: Dict[str, Any], decision_id: str) -> str:
    for decision in method.get("decisions", []) or []:
        if str(decision.get("id") or "") == decision_id:
            return str(decision.get("condition") or "")
    return ""


def _with_selection(item: Dict[str, Any], selection: Dict[str, Any]) -> Dict[str, Any]:
    item_id = str(item.get("id") or "")
    if item_id in selection:
        item["selected"] = bool(selection[item_id])
    return item


def _location(source_name: str, line: Any) -> str:
    return f"{source_name}:{line}" if line else source_name


def _branch_label(edge: Dict[str, Any]) -> str:
    label = str(edge.get("label") or edge.get("type") or "branch")
    if label == "loop-back":
        return "true"
    return label


def _branch_suffix(label: str, exception_index: int | None = None) -> str:
    normalized = str(label or "").strip().lower()
    if normalized == "true":
        return "T"
    if normalized == "false":
        return "F"
    if normalized == "normal":
        return "N"
    if normalized == "default":
        return "D"
    if normalized.startswith("exception"):
        return f"EXC{exception_index}" if exception_index is not None else "EXC"
    cleaned = "".join(ch for ch in normalized.upper() if ch.isalnum())
    return cleaned[:8] or "CASE"


def _branch_value(label: str) -> Any:
    normalized = str(label or "").strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    return label


def _branch_target(decision_node: Dict[str, Any], label: str, condition: str) -> str:
    kind = str(decision_node.get("kind") or "decision")
    normalized = str(label or "").strip().lower()
    if kind == "switch":
        return f"Take switch branch {label}: {condition}"
    if kind in {"for", "while", "do-while"}:
        if normalized == "true":
            return f"Enter loop by taking true branch: {condition}"
        if normalized == "false":
            return f"Skip or exit loop by taking false branch: {condition}"
    if kind == "try":
        return f"Take {label} try/catch branch: {condition}"
    return f"Take {label} branch of {kind}: {condition}"
