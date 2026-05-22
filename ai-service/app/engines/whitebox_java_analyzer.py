"""CFG-driven Java source analyzer for deterministic white-box design.

This module uses javalang to parse Java source and builds a simplified,
method-level control-flow graph (CFG). The model is intentionally lightweight:
it is meant to identify statement and branch coverage targets deterministically,
not to perform symbolic execution or decide test data with an LLM.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:  # pragma: no cover - exercised in environments with dependency present
    import javalang  # type: ignore[import]
except Exception:  # pragma: no cover
    javalang = None  # type: ignore[assignment]


_DECISION_KINDS = {
    "IfStatement": "if",
    "SwitchStatement": "switch",
    "ForStatement": "for",
    "WhileStatement": "while",
    "DoStatement": "do-while",
    "TryStatement": "try",
}

_STATEMENT_KINDS = {
    "IfStatement": "if",
    "SwitchStatement": "switch",
    "ForStatement": "for",
    "WhileStatement": "while",
    "DoStatement": "do-while",
    "TryStatement": "try",
    "ReturnStatement": "return",
    "ThrowStatement": "throw",
    "StatementExpression": "statement",
    "LocalVariableDeclaration": "declaration",
    "BreakStatement": "break",
    "ContinueStatement": "continue",
}


@dataclass
class PendingEdge:
    from_node: str
    edge_type: str = "normal"
    label: str = "normal"
    condition: str = ""


@dataclass
class FlowResult:
    normal: List[PendingEdge] = field(default_factory=list)
    breaks: List[PendingEdge] = field(default_factory=list)
    continues: List[PendingEdge] = field(default_factory=list)


def analyze_java_source(source_code: str, source_name: str = "JavaSource.java") -> Dict[str, Any]:
    """Parse Java source and return a JSON-serializable CFG-backed model."""
    warnings: List[str] = []
    source = str(source_code or "").strip()
    if not source:
        return {"language": "java", "sourceName": source_name, "classes": [], "warnings": ["Java source is empty."]}

    if javalang is None:
        return {
            "language": "java",
            "sourceName": source_name,
            "classes": [],
            "warnings": ["javalang is not installed; Java white-box analysis could not run."],
        }

    parsed, parse_source, line_offset, parse_warning = _parse_with_optional_wrapper(source)
    if parse_warning:
        warnings.append(parse_warning)
    if parsed is None:
        return {
            "language": "java",
            "sourceName": source_name,
            "classes": [],
            "warnings": warnings or ["Java parse failed."],
        }

    original_lines = source.splitlines()
    parse_lines = parse_source.splitlines()
    counters = {"method": 1, "statement": 1, "decision": 1}
    classes: List[Dict[str, Any]] = []

    for class_node in getattr(parsed, "types", []) or []:
        if class_node.__class__.__name__ not in {"ClassDeclaration", "EnumDeclaration", "InterfaceDeclaration"}:
            continue
        _analyze_class_node(class_node, "", source_name, original_lines, parse_lines, line_offset, counters, classes, warnings)

    if not classes:
        warnings.append("No Java class, interface, enum, method, or constructor declarations were found.")

    return {"language": "java", "sourceName": source_name, "classes": classes, "warnings": _unique(warnings)}


def _analyze_class_node(
    class_node: Any,
    outer_name: str,
    source_name: str,
    original_lines: List[str],
    parse_lines: List[str],
    line_offset: int,
    counters: Dict[str, int],
    classes: List[Dict[str, Any]],
    warnings: List[str],
) -> None:
    class_name = str(getattr(class_node, "name", "AnonymousClass"))
    qualified_name = f"{outer_name}.{class_name}" if outer_name else class_name
    class_item: Dict[str, Any] = {"name": qualified_name, "methods": []}
    method_nodes = list(getattr(class_node, "constructors", []) or []) + list(getattr(class_node, "methods", []) or [])
    if not method_nodes:
        warnings.append(f"Class {qualified_name} has no methods or constructors to analyze.")

    for method_node in method_nodes:
        method_id = f"M-{counters['method']:03d}"
        counters["method"] += 1
        builder = _MethodCfgBuilder(
            method_id=method_id,
            source_name=source_name,
            original_lines=original_lines,
            parse_lines=parse_lines,
            line_offset=line_offset,
            counters=counters,
        )
        method_item = builder.build(method_node, class_name)
        class_item["methods"].append(method_item)
        warnings.extend(builder.warnings)

    classes.append(class_item)
    for nested in _nested_type_declarations(class_node):
        _analyze_class_node(nested, qualified_name, source_name, original_lines, parse_lines, line_offset, counters, classes, warnings)


class _MethodCfgBuilder:
    def __init__(
        self,
        method_id: str,
        source_name: str,
        original_lines: List[str],
        parse_lines: List[str],
        line_offset: int,
        counters: Dict[str, int],
    ) -> None:
        self.method_id = method_id
        self.source_name = source_name
        self.original_lines = original_lines
        self.parse_lines = parse_lines
        self.line_offset = line_offset
        self.counters = counters
        self.node_counter = 1
        self.edge_counter = 1
        self.exit_counter = 1
        self.statements: List[Dict[str, Any]] = []
        self.decisions: List[Dict[str, Any]] = []
        self.exits: List[Dict[str, Any]] = []
        self.nodes: List[Dict[str, Any]] = []
        self.edges: List[Dict[str, Any]] = []
        self.warnings: List[str] = []

    def build(self, method_node: Any, class_name: str) -> Dict[str, Any]:
        is_constructor = method_node.__class__.__name__ == "ConstructorDeclaration"
        method_name = str(getattr(method_node, "name", "") or class_name)
        start_line = _adjust_line(_line_of(method_node), self.line_offset)
        end_line = _method_end_line(method_node, self.line_offset) or start_line
        entry_node_id = self._new_node(
            node_type="entry",
            line=start_line,
            kind="entry",
            text=f"entry {method_name}",
        )
        exit_node_id = self._new_node(
            node_type="exit",
            line=end_line,
            kind="exit",
            text=f"exit {method_name}",
        )
        body = list(getattr(method_node, "body", []) or [])
        flow = self._build_block(body, [PendingEdge(entry_node_id)], loop_depth=0, switch_depth=0)
        self._connect_pending(flow.normal, exit_node_id)
        if flow.breaks:
            self.warnings.append(f"Unresolved break statement(s) in {method_name}; labeled breaks are not modeled.")
        if flow.continues:
            self.warnings.append(f"Unresolved continue statement(s) in {method_name}; labeled continues are not modeled.")

        return_type = class_name if is_constructor else _type_to_text(getattr(method_node, "return_type", None))
        cfg = {
            "entryNodeId": entry_node_id,
            "exitNodeIds": [exit_node_id],
            "nodes": self.nodes,
            "edges": self.edges,
        }
        return {
            "id": self.method_id,
            "name": method_name,
            "kind": "constructor" if is_constructor else "method",
            "parameters": [_parameter_to_dict(param) for param in (getattr(method_node, "parameters", []) or [])],
            "returnType": return_type,
            "startLine": start_line,
            "endLine": end_line,
            "statements": self.statements,
            "decisions": self.decisions,
            "exits": self.exits,
            "cfg": cfg,
        }

    def _build_block(
        self,
        statements: Any,
        incoming: List[PendingEdge],
        loop_depth: int,
        switch_depth: int,
    ) -> FlowResult:
        flow = FlowResult(normal=list(incoming))
        for statement in _as_statement_list(statements):
            if not flow.normal:
                self.warnings.append(
                    f"Unreachable statement at line {_adjust_line(_line_of(statement), self.line_offset) or 'unknown'} was modeled without incoming CFG edge."
                )
            next_flow = self._build_statement(statement, flow.normal, loop_depth, switch_depth)
            flow = FlowResult(
                normal=next_flow.normal,
                breaks=flow.breaks + next_flow.breaks,
                continues=flow.continues + next_flow.continues,
            )
        return flow

    def _build_statement(
        self,
        node: Any,
        incoming: List[PendingEdge],
        loop_depth: int,
        switch_depth: int,
    ) -> FlowResult:
        if node is None:
            return FlowResult(normal=list(incoming))

        class_name = node.__class__.__name__
        if class_name == "BlockStatement":
            return self._build_block(getattr(node, "statements", []) or [], incoming, loop_depth, switch_depth)
        if class_name == "IfStatement":
            return self._build_if(node, incoming, loop_depth, switch_depth)
        if class_name == "SwitchStatement":
            return self._build_switch(node, incoming, loop_depth, switch_depth)
        if class_name in {"ForStatement", "WhileStatement"}:
            return self._build_pre_test_loop(node, incoming, loop_depth, switch_depth)
        if class_name == "DoStatement":
            return self._build_do_loop(node, incoming, loop_depth, switch_depth)
        if class_name == "TryStatement":
            return self._build_try(node, incoming, loop_depth, switch_depth)
        if class_name in {"ReturnStatement", "ThrowStatement"}:
            return self._build_terminal(node, incoming, "return" if class_name == "ReturnStatement" else "throw")
        if class_name == "BreakStatement":
            return self._build_break(node, incoming, loop_depth, switch_depth)
        if class_name == "ContinueStatement":
            return self._build_continue(node, incoming, loop_depth)
        if class_name in {"StatementExpression", "LocalVariableDeclaration"}:
            kind = "declaration" if class_name == "LocalVariableDeclaration" else "statement"
            node_id = self._new_statement_node(node, kind, "statement")
            self._connect_pending(incoming, node_id)
            return FlowResult(normal=[PendingEdge(node_id)])

        if class_name.endswith("Statement") or class_name.endswith("Declaration"):
            node_id = self._new_statement_node(node, "statement", "statement")
            self._connect_pending(incoming, node_id)
            return FlowResult(normal=[PendingEdge(node_id)])

        return FlowResult(normal=list(incoming))

    def _build_if(self, node: Any, incoming: List[PendingEdge], loop_depth: int, switch_depth: int) -> FlowResult:
        decision_id, decision_node_id, condition = self._new_decision_node(node, "if")
        self._connect_pending(incoming, decision_node_id)
        then_flow = self._build_block(
            _as_statement_list(getattr(node, "then_statement", None)),
            [PendingEdge(decision_node_id, "true", "true", condition)],
            loop_depth,
            switch_depth,
        )
        else_statement = getattr(node, "else_statement", None)
        if else_statement is None:
            else_flow = FlowResult(normal=[PendingEdge(decision_node_id, "false", "false", condition)])
        else:
            else_flow = self._build_block(
                _as_statement_list(else_statement),
                [PendingEdge(decision_node_id, "false", "false", condition)],
                loop_depth,
                switch_depth,
            )
        self._set_decision_branches(decision_id, [{"id": f"{decision_id}-T", "label": "true"}, {"id": f"{decision_id}-F", "label": "false"}])
        return FlowResult(
            normal=then_flow.normal + else_flow.normal,
            breaks=then_flow.breaks + else_flow.breaks,
            continues=then_flow.continues + else_flow.continues,
        )

    def _build_pre_test_loop(self, node: Any, incoming: List[PendingEdge], loop_depth: int, switch_depth: int) -> FlowResult:
        kind = _DECISION_KINDS.get(node.__class__.__name__, "while")
        decision_id, decision_node_id, condition = self._new_decision_node(node, kind)
        self._connect_pending(incoming, decision_node_id)
        body_flow = self._build_block(
            _as_statement_list(getattr(node, "body", None)),
            [PendingEdge(decision_node_id, "true", "true", condition)],
            loop_depth + 1,
            switch_depth,
        )
        self._connect_pending_as(body_flow.normal + body_flow.continues, decision_node_id, "loop-back", "loop-back", condition)
        self._set_decision_branches(decision_id, [{"id": f"{decision_id}-T", "label": "true"}, {"id": f"{decision_id}-F", "label": "false"}])
        return FlowResult(normal=[PendingEdge(decision_node_id, "false", "false", condition)] + body_flow.breaks)

    def _build_do_loop(self, node: Any, incoming: List[PendingEdge], loop_depth: int, switch_depth: int) -> FlowResult:
        line = _adjust_line(_line_of(node), self.line_offset)
        merge_node_id = self._new_node("merge", line, "do-while", "do-while body entry")
        self._connect_pending(incoming, merge_node_id)
        body_flow = self._build_block(
            _as_statement_list(getattr(node, "body", None)),
            [PendingEdge(merge_node_id)],
            loop_depth + 1,
            switch_depth,
        )
        decision_id, decision_node_id, condition = self._new_decision_node(node, "do-while")
        self._connect_pending(body_flow.normal + body_flow.continues, decision_node_id)
        self._new_edge(decision_node_id, merge_node_id, "loop-back", "true", condition)
        self._set_decision_branches(decision_id, [{"id": f"{decision_id}-T", "label": "true"}, {"id": f"{decision_id}-F", "label": "false"}])
        return FlowResult(normal=[PendingEdge(decision_node_id, "false", "false", condition)] + body_flow.breaks)

    def _build_switch(self, node: Any, incoming: List[PendingEdge], loop_depth: int, switch_depth: int) -> FlowResult:
        decision_id, decision_node_id, condition = self._new_decision_node(node, "switch")
        self._connect_pending(incoming, decision_node_id)
        cases = list(getattr(node, "cases", []) or [])
        normal: List[PendingEdge] = []
        breaks: List[PendingEdge] = []
        continues: List[PendingEdge] = []
        branches: List[Dict[str, Any]] = []
        has_default = False
        fallthrough: List[PendingEdge] = []

        for index, case in enumerate(cases, start=1):
            label = _switch_case_label(case)
            has_default = has_default or label == "default"
            edge_type = "default" if label == "default" else "case"
            branch_id = f"{decision_id}-D" if label == "default" else f"{decision_id}-C{index}"
            branches.append({"id": branch_id, "label": label})
            case_line = _adjust_line(_line_of(case), self.line_offset) or _case_first_statement_line(case, self.line_offset)
            case_entry_id = self._new_node("merge", case_line, "switch-case", f"switch case {label}")
            self._new_edge(decision_node_id, case_entry_id, edge_type, label, condition)
            self._connect_pending(fallthrough, case_entry_id)
            case_flow = self._build_block(
                getattr(case, "statements", []) or [],
                [PendingEdge(case_entry_id)],
                loop_depth,
                switch_depth + 1,
            )
            fallthrough = case_flow.normal
            breaks.extend(case_flow.breaks)
            continues.extend(case_flow.continues)

        normal.extend(fallthrough)
        if not cases or not has_default:
            branches.append({"id": f"{decision_id}-D", "label": "default"})
            normal.append(PendingEdge(decision_node_id, "default", "default", condition))

        self._set_decision_branches(decision_id, branches)
        return FlowResult(normal=normal + breaks, continues=continues)

    def _build_try(self, node: Any, incoming: List[PendingEdge], loop_depth: int, switch_depth: int) -> FlowResult:
        decision_id, decision_node_id, condition = self._new_decision_node(node, "try")
        self._connect_pending(incoming, decision_node_id)
        normal_condition = "try block completes without a caught exception"
        exception_condition = "a caught exception is thrown in the try block"
        try_node_start = len(self.nodes)
        try_flow = self._build_block(
            getattr(node, "block", []) or [],
            [PendingEdge(decision_node_id, "normal", "normal", normal_condition)],
            loop_depth,
            switch_depth,
        )
        trigger_hints = self._potential_exception_trigger_hints(self.nodes[try_node_start:])
        self._set_decision_extra(decision_id, {"exceptionTriggerHints": trigger_hints})
        catches = list(getattr(node, "catches", []) or [])
        catch_normals: List[PendingEdge] = []
        catch_breaks: List[PendingEdge] = []
        catch_continues: List[PendingEdge] = []
        branches = [{"id": f"{decision_id}-N", "label": "normal"}]

        for index, catch in enumerate(catches, start=1):
            catch_label = _catch_label(catch, index)
            catch_node_id = self._new_catch_node(catch, catch_label)
            self._new_edge(decision_node_id, catch_node_id, "exception", catch_label, exception_condition)
            catch_flow = self._build_block(
                getattr(catch, "block", []) or [],
                [PendingEdge(catch_node_id)],
                loop_depth,
                switch_depth,
            )
            catch_normals.extend(catch_flow.normal)
            catch_breaks.extend(catch_flow.breaks)
            catch_continues.extend(catch_flow.continues)
            branches.append({"id": f"{decision_id}-E{index}", "label": catch_label})

        normals = try_flow.normal + catch_normals
        finally_block = getattr(node, "finally_block", None)
        if finally_block:
            finally_flow = self._build_block(finally_block, normals, loop_depth, switch_depth)
            normals = finally_flow.normal
            catch_breaks.extend(finally_flow.breaks)
            catch_continues.extend(finally_flow.continues)
            self.warnings.append("Finally blocks are modeled for non-terminating paths only; return/throw-finally interaction needs review.")

        self._set_decision_branches(decision_id, branches)
        return FlowResult(
            normal=normals,
            breaks=try_flow.breaks + catch_breaks,
            continues=try_flow.continues + catch_continues,
        )

    def _build_terminal(self, node: Any, incoming: List[PendingEdge], kind: str) -> FlowResult:
        node_id = self._new_statement_node(node, kind, kind)
        self._connect_pending(incoming, node_id)
        exit_node_id = self._exit_node_id()
        self._new_edge(node_id, exit_node_id, "normal", "method-exit", "")
        statement_id = self._node_by_id(node_id).get("statementId", "")
        line = _adjust_line(_line_of(node), self.line_offset)
        text = self._statement_text(kind, node, line)
        self.exits.append(
            {
                "id": f"EXIT-{self.exit_counter:03d}",
                "methodId": self.method_id,
                "line": line,
                "kind": kind,
                "sourceStatementId": statement_id,
                "sourceNodeId": node_id,
                "text": text,
            }
        )
        self.exit_counter += 1
        return FlowResult()

    def _build_break(self, node: Any, incoming: List[PendingEdge], loop_depth: int, switch_depth: int) -> FlowResult:
        node_id = self._new_statement_node(node, "break", "statement")
        self._connect_pending(incoming, node_id)
        if getattr(node, "goto", None):
            self.warnings.append("Labeled break statements are not fully modeled and need manual review.")
        if loop_depth <= 0 and switch_depth <= 0:
            self.warnings.append("Break outside a modeled switch/loop may require manual review.")
        return FlowResult(breaks=[PendingEdge(node_id)])

    def _build_continue(self, node: Any, incoming: List[PendingEdge], loop_depth: int) -> FlowResult:
        node_id = self._new_statement_node(node, "continue", "statement")
        self._connect_pending(incoming, node_id)
        if loop_depth <= 0:
            self.warnings.append("Continue outside a modeled loop may require manual review.")
        return FlowResult(continues=[PendingEdge(node_id)])

    def _new_statement_node(self, ast_node: Any, kind: str, node_type: str) -> str:
        line = _adjust_line(_line_of(ast_node), self.line_offset)
        text = self._statement_text(kind, ast_node, line)
        statement_id = f"STMT-{self.counters['statement']:03d}"
        self.counters["statement"] += 1
        node_id = self._new_node(node_type, line, kind, text, statement_id=statement_id)
        self.statements.append(
            {
                "id": statement_id,
                "methodId": self.method_id,
                "line": line,
                "kind": kind,
                "text": text,
                "sourceNodeId": node_id,
            }
        )
        return node_id

    def _new_decision_node(self, ast_node: Any, kind: str) -> Tuple[str, str, str]:
        line = _adjust_line(_line_of(ast_node), self.line_offset)
        condition = self._condition_text(kind, ast_node, line)
        text = self._statement_text(kind, ast_node, line)
        statement_id = f"STMT-{self.counters['statement']:03d}"
        self.counters["statement"] += 1
        decision_id = f"DEC-{self.counters['decision']:03d}"
        self.counters["decision"] += 1
        node_id = self._new_node("decision", line, kind, text, statement_id=statement_id, decision_id=decision_id)
        self.statements.append(
            {
                "id": statement_id,
                "methodId": self.method_id,
                "line": line,
                "kind": kind,
                "text": text,
                "sourceNodeId": node_id,
            }
        )
        self.decisions.append(
            {
                "id": decision_id,
                "methodId": self.method_id,
                "line": line,
                "kind": kind,
                "condition": condition,
                "sourceNodeId": node_id,
                "sourceStatementId": statement_id,
                "branches": [],
            }
        )
        return decision_id, node_id, condition

    def _new_catch_node(self, catch_node: Any, label: str) -> str:
        line = _adjust_line(_line_of(catch_node), self.line_offset)
        statement_id = f"STMT-{self.counters['statement']:03d}"
        self.counters["statement"] += 1
        text = f"catch {label}"
        node_id = self._new_node("catch", line, "catch", text, statement_id=statement_id)
        self.statements.append(
            {
                "id": statement_id,
                "methodId": self.method_id,
                "line": line,
                "kind": "catch",
                "text": text,
                "sourceNodeId": node_id,
            }
        )
        return node_id

    def _set_decision_branches(self, decision_id: str, branches: List[Dict[str, Any]]) -> None:
        for decision in self.decisions:
            if decision.get("id") == decision_id:
                decision["branches"] = branches
                return

    def _set_decision_extra(self, decision_id: str, extra: Dict[str, Any]) -> None:
        for decision in self.decisions:
            if decision.get("id") == decision_id:
                decision.update(extra)
                return

    def _potential_exception_trigger_hints(self, nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        hints: List[Dict[str, Any]] = []
        for node in nodes:
            if node.get("type") not in {"statement", "return", "throw"}:
                continue
            text = str(node.get("text") or "")
            kind = str(node.get("kind") or "")
            if kind not in {"statement", "declaration", "return", "throw"}:
                continue
            if kind != "throw" and "(" not in text:
                continue
            hints.append(
                {
                    "line": node.get("line"),
                    "nodeId": node.get("id"),
                    "text": text,
                    "suggestedSetup": "Mock or configure this call to throw Exception",
                }
            )
        return hints

    def _new_node(
        self,
        node_type: str,
        line: Optional[int],
        kind: str,
        text: str,
        statement_id: Optional[str] = None,
        decision_id: Optional[str] = None,
    ) -> str:
        node_id = f"N-{self.node_counter:03d}"
        self.node_counter += 1
        self.nodes.append(
            {
                "id": node_id,
                "methodId": self.method_id,
                "type": node_type,
                "line": line,
                "statementId": statement_id,
                "decisionId": decision_id,
                "text": text,
                "kind": kind,
            }
        )
        return node_id

    def _new_edge(self, from_node: str, to_node: str, edge_type: str, label: str, condition: str) -> str:
        edge_id = f"E-{self.edge_counter:03d}"
        self.edge_counter += 1
        self.edges.append(
            {
                "id": edge_id,
                "from": from_node,
                "to": to_node,
                "type": edge_type,
                "label": label,
                "condition": condition,
            }
        )
        return edge_id

    def _connect_pending(self, pending: List[PendingEdge], target_node: str) -> None:
        for item in pending:
            self._new_edge(item.from_node, target_node, item.edge_type, item.label, item.condition)

    def _connect_pending_as(
        self,
        pending: List[PendingEdge],
        target_node: str,
        edge_type: str,
        label: str,
        condition: str,
    ) -> None:
        for item in pending:
            self._new_edge(item.from_node, target_node, edge_type, label, item.condition or condition)

    def _statement_text(self, kind: str, node: Any, line: Optional[int]) -> str:
        if kind in {"return", "throw"}:
            statement_text = _source_statement_text(self.original_lines, line)
            if statement_text:
                return statement_text
            parse_statement_text = _source_statement_text(self.parse_lines, (line or 0) + self.line_offset)
            if parse_statement_text:
                return parse_statement_text
        line_text = _source_line(self.original_lines, line)
        if line_text:
            return line_text
        parse_line = _source_line(self.parse_lines, (line or 0) + self.line_offset)
        if parse_line:
            return parse_line
        return kind

    def _condition_text(self, kind: str, node: Any, line: Optional[int]) -> str:
        source_line = _source_line(self.original_lines, line) or _source_line(self.parse_lines, (line or 0) + self.line_offset)
        if source_line:
            extracted = _extract_condition_from_line(kind, source_line)
            if extracted:
                return extracted

        if kind == "switch":
            return _compact_expr(getattr(node, "expression", None))
        if kind in {"for", "while", "do-while"}:
            control = getattr(node, "control", None)
            return _compact_expr(getattr(control, "condition", None)) if control is not None else _compact_expr(getattr(node, "condition", None))
        if kind == "try":
            return "try/catch control"
        return _compact_expr(getattr(node, "condition", None))

    def _node_by_id(self, node_id: str) -> Dict[str, Any]:
        for node in self.nodes:
            if node.get("id") == node_id:
                return node
        return {}

    def _exit_node_id(self) -> str:
        for node in self.nodes:
            if node.get("type") == "exit":
                return str(node.get("id"))
        raise RuntimeError("method exit node was not initialized")


def _parse_with_optional_wrapper(source: str) -> Tuple[Optional[Any], str, int, str]:
    try:
        return javalang.parse.parse(source), source, 0, ""  # type: ignore[union-attr]
    except Exception as first_exc:  # noqa: BLE001
        if re.search(r"\bclass\b|\binterface\b|\benum\b", source):
            return None, source, 0, f"Java parse failed: {first_exc}"

    wrapped = f"public class SnippetWrapper {{\n{source}\n}}"
    try:
        return (
            javalang.parse.parse(wrapped),  # type: ignore[union-attr]
            wrapped,
            1,
            "Input was parsed as a Java method/body snippet by wrapping it in SnippetWrapper.",
        )
    except Exception as second_exc:  # noqa: BLE001
        return None, source, 0, f"Java parse failed: {second_exc}"


def _as_statement_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if value.__class__.__name__ == "BlockStatement":
        return list(getattr(value, "statements", []) or [])
    return [value]


def _parameter_to_dict(param: Any) -> Dict[str, str]:
    return {"name": str(getattr(param, "name", "")), "type": _type_to_text(getattr(param, "type", None))}


def _type_to_text(type_node: Any) -> str:
    if type_node is None:
        return "void"
    name = str(getattr(type_node, "name", "") or getattr(type_node, "value", "") or type_node.__class__.__name__)
    arguments = getattr(type_node, "arguments", None) or []
    if arguments:
        parts = []
        for arg in arguments:
            arg_type = getattr(arg, "type", None)
            parts.append(_type_to_text(arg_type) if arg_type is not None else str(arg))
        name += f"<{', '.join(parts)}>"
    dimensions = getattr(type_node, "dimensions", None) or []
    return name + ("[]" * len(dimensions))


def _switch_case_label(case: Any) -> str:
    values = getattr(case, "case", None)
    if not values:
        return "default"
    first = values[0] if isinstance(values, list) else values
    value = getattr(first, "value", None)
    if value is not None:
        return str(value)
    return _compact_expr(first) or "case"


def _catch_label(catch: Any, index: int) -> str:
    parameter = getattr(catch, "parameter", None)
    types = getattr(parameter, "types", None) or []
    if types:
        return f"exception:{'|'.join(str(item) for item in types)}"
    return "exception" if index == 1 else f"exception:{index}"


def _extract_condition_from_line(kind: str, line_text: str) -> str:
    keyword = "while" if kind == "do-while" else kind
    if kind == "for":
        match = re.search(r"\bfor\s*\((.*)\)", line_text)
        if match:
            parts = match.group(1).split(";")
            return parts[1].strip() if len(parts) >= 2 else match.group(1).strip()
    elif kind == "try":
        return "try/catch control"
    else:
        match = re.search(rf"\b{re.escape(keyword)}\s*\((.*)\)", line_text)
        if match:
            return match.group(1).strip()
    return ""


def _case_first_statement_line(case: Any, line_offset: int) -> Optional[int]:
    statements = getattr(case, "statements", []) or []
    if not statements:
        return None
    return _adjust_line(_line_of(statements[0]), line_offset)


def _nested_type_declarations(class_node: Any) -> List[Any]:
    return [
        item
        for item in (getattr(class_node, "body", []) or [])
        if getattr(item, "__class__", None).__name__ in {"ClassDeclaration", "EnumDeclaration", "InterfaceDeclaration"}
    ]


def _compact_expr(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _line_of(node: Any) -> Optional[int]:
    position = getattr(node, "position", None)
    return int(position.line) if position and getattr(position, "line", None) else None


def _adjust_line(line: Optional[int], line_offset: int) -> Optional[int]:
    if line is None:
        return None
    return max(1, line - line_offset)


def _method_end_line(method_node: Any, line_offset: int) -> Optional[int]:
    lines = [_adjust_line(_line_of(method_node), line_offset) or 0]
    stack = list(_iter_child_nodes(method_node))
    seen: set[int] = set()
    while stack:
        child = stack.pop()
        if id(child) in seen:
            continue
        seen.add(id(child))
        child_line = _adjust_line(_line_of(child), line_offset)
        if child_line:
            lines.append(child_line)
        stack.extend(_iter_child_nodes(child))
    return max(lines) if lines else None


def _iter_child_nodes(node: Any) -> Iterable[Any]:
    attrs = getattr(node, "attrs", []) or []
    for attr in attrs:
        value = getattr(node, attr, None)
        yield from _iter_node_values(value)


def _iter_node_values(value: Any) -> Iterable[Any]:
    if value is None:
        return
    if hasattr(value, "attrs"):
        yield value
        return
    if isinstance(value, (list, tuple, set)):
        for item in value:
            yield from _iter_node_values(item)


def _source_line(lines: List[str], line: Optional[int]) -> str:
    if not line or line < 1 or line > len(lines):
        return ""
    return lines[line - 1].strip()


def _source_statement_text(lines: List[str], line: Optional[int]) -> str:
    if not line or line < 1 or line > len(lines):
        return ""
    collected: List[str] = []
    balance = 0
    for index in range(line - 1, min(len(lines), line + 12)):
        stripped = lines[index].strip()
        if not stripped:
            continue
        collected.append(stripped)
        balance += _paren_delta(stripped)
        if ";" in stripped and balance <= 0:
            break
    text = " ".join(collected).strip()
    text = re.sub(r"\s+", " ", text)
    return text


def _paren_delta(text: str) -> int:
    value = re.sub(r"\"(?:\\.|[^\"])*\"|'(?:\\.|[^'])*'", "", text)
    return value.count("(") - value.count(")")


def _unique(values: List[str]) -> List[str]:
    seen = set()
    result = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result
