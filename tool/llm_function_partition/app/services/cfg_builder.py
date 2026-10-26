import ast
import textwrap
from dataclasses import dataclass, field
from typing import Any

from app.services.localization import normalize_language, tr


CFGNode = dict[str, Any]
CFGEdge = dict[str, str]
Connector = tuple[str, str]


@dataclass
class CFGResult:
    function_name: str
    function_source: str
    bb_nodes: list[CFGNode]
    cfg_edges: list[CFGEdge]


@dataclass
class LoopContext:
    cond_id: str
    break_nodes: list[str] = field(default_factory=list)


class SymbolCollector(ast.NodeVisitor):
    def __init__(self) -> None:
        self.calls: set[str] = set()
        self.defs: set[str] = set()
        self.uses: set[str] = set()
        self.effects: set[str] = set()

    def visit_Call(self, node: ast.Call) -> None:
        name = self._call_name(node.func)
        if name:
            self.calls.add(name)
            if name in {"print", "input"}:
                self.effects.add("io")
            if name == "open":
                self.effects.update({"io", "filesystem"})
            if name.startswith("logger.") or name.startswith("logging."):
                self.effects.add("logging")
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Store):
            self.defs.add(node.id)
        elif isinstance(node.ctx, ast.Load):
            self.uses.add(node.id)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if isinstance(node.ctx, ast.Load):
            self.uses.add(ast.unparse(node))
        self.generic_visit(node)

    def visit_Raise(self, node: ast.Raise) -> None:
        self.effects.add("exception")
        self.generic_visit(node)

    @staticmethod
    def _call_name(node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            prefix = SymbolCollector._call_name(node.value)
            return f"{prefix}.{node.attr}" if prefix else node.attr
        return ""


class CFGBuilder:
    def __init__(self, function_source: str, base_lineno: int, language: str = "en") -> None:
        self.function_source = function_source
        self.base_lineno = base_lineno
        self.language = normalize_language(language)
        self.nodes: list[CFGNode] = []
        self.edges: list[CFGEdge] = []
        self._counter = 0

    def build(self, function_def: ast.FunctionDef | ast.AsyncFunctionDef) -> CFGResult:
        exits = self._build_statements(function_def.body, [])
        if not self.nodes:
            node = self._create_node("pass", kind="empty", start_line=1, end_line=1)
            exits = [(node["id"], "main")]
        if exits:
            last_line = len(self.function_source.splitlines()) or 1
            exit_node = self._create_node("EXIT", kind="exit", start_line=last_line, end_line=last_line)
            for source_id, edge_type in exits:
                self._add_edge(source_id, exit_node["id"], edge_type)
        return CFGResult(
            function_name=function_def.name,
            function_source=self.function_source,
            bb_nodes=self.nodes,
            cfg_edges=self.edges,
        )

    def _build_statements(
        self,
        statements: list[ast.stmt],
        incoming: list[Connector],
        loop_ctx: LoopContext | None = None,
    ) -> list[Connector]:
        current = incoming
        for stmt in statements:
            if isinstance(stmt, ast.If):
                current = self._handle_if(stmt, current, loop_ctx)
            elif isinstance(stmt, (ast.For, ast.AsyncFor, ast.While)):
                current = self._handle_loop(stmt, current, loop_ctx)
            elif isinstance(stmt, ast.Try):
                current = self._handle_try(stmt, current, loop_ctx)
            else:
                current = self._handle_simple_statement(stmt, current, loop_ctx)
        return current

    def _handle_simple_statement(
        self,
        stmt: ast.stmt,
        incoming: list[Connector],
        loop_ctx: LoopContext | None,
    ) -> list[Connector]:
        start_line, end_line = self._line_span(stmt)
        node = self._create_node(self._stmt_source(stmt), stmt, start_line=start_line, end_line=end_line)
        self._connect_incoming(incoming, node["id"])

        if isinstance(stmt, (ast.Return, ast.Raise)):
            return []
        if isinstance(stmt, ast.Break):
            if loop_ctx is not None:
                loop_ctx.break_nodes.append(node["id"])
            return []
        if isinstance(stmt, ast.Continue):
            if loop_ctx is not None:
                self._add_edge(node["id"], loop_ctx.cond_id, "continue")
            return []
        return [(node["id"], "main")]

    def _handle_if(
        self,
        stmt: ast.If,
        incoming: list[Connector],
        loop_ctx: LoopContext | None,
    ) -> list[Connector]:
        start_line, end_line = self._line_span(stmt, header_only=True)
        cond_node = self._create_node(
            f"if {ast.unparse(stmt.test)}",
            stmt.test,
            kind="condition",
            start_line=start_line,
            end_line=end_line,
        )
        self._connect_incoming(incoming, cond_node["id"])
        true_exits = self._build_statements(stmt.body, [(cond_node["id"], "true")], loop_ctx)
        false_incoming = [(cond_node["id"], "false")]
        false_exits = (
            self._build_statements(stmt.orelse, false_incoming, loop_ctx)
            if stmt.orelse
            else false_incoming
        )
        return true_exits + false_exits

    def _handle_loop(
        self,
        stmt: ast.For | ast.AsyncFor | ast.While,
        incoming: list[Connector],
        outer_loop_ctx: LoopContext | None,
    ) -> list[Connector]:
        if isinstance(stmt, ast.While):
            cond_code = f"while {ast.unparse(stmt.test)}"
        elif isinstance(stmt, ast.AsyncFor):
            cond_code = f"async for {ast.unparse(stmt.target)} in {ast.unparse(stmt.iter)}"
        else:
            cond_code = f"for {ast.unparse(stmt.target)} in {ast.unparse(stmt.iter)}"

        start_line, end_line = self._line_span(stmt, header_only=True)
        cond_node = self._create_node(
            cond_code,
            stmt,
            kind="loop",
            start_line=start_line,
            end_line=end_line,
        )
        self._connect_incoming(incoming, cond_node["id"])

        loop_ctx = LoopContext(cond_id=cond_node["id"])
        body_exits = self._build_statements(stmt.body, [(cond_node["id"], "true")], loop_ctx)
        for source_id, _ in body_exits:
            self._add_edge(source_id, cond_node["id"], "loop")

        exits: list[Connector] = [(cond_node["id"], "false")]
        exits.extend((node_id, "break") for node_id in loop_ctx.break_nodes)
        if stmt.orelse:
            exits = self._build_statements(stmt.orelse, exits, outer_loop_ctx)
        return exits

    def _handle_try(
        self,
        stmt: ast.Try,
        incoming: list[Connector],
        loop_ctx: LoopContext | None,
    ) -> list[Connector]:
        start_line, end_line = self._line_span(stmt, header_only=True)
        try_node = self._create_node("try", stmt, kind="try", start_line=start_line, end_line=end_line)
        self._connect_incoming(incoming, try_node["id"])
        body_exits = self._build_statements(stmt.body, [(try_node["id"], "main")], loop_ctx)

        handler_exits: list[Connector] = []
        for handler in stmt.handlers:
            label = "except"
            if handler.type is not None:
                label = f"except {ast.unparse(handler.type)}"
            handler_start, handler_end = self._line_span(handler, header_only=True)
            handler_node = self._create_node(
                label,
                handler,
                kind="except",
                start_line=handler_start,
                end_line=handler_end,
            )
            self._add_edge(try_node["id"], handler_node["id"], "exception")
            handler_exits.extend(self._build_statements(handler.body, [(handler_node["id"], "main")], loop_ctx))

        merged = body_exits + handler_exits
        if stmt.finalbody:
            final_start = self._relative_line(stmt.finalbody[0].lineno - 1) if stmt.finalbody else start_line
            final_node = self._create_node(
                "finally",
                stmt,
                kind="finally",
                start_line=final_start,
                end_line=final_start,
            )
            for source_id, edge_type in merged:
                self._add_edge(source_id, final_node["id"], edge_type)
            return self._build_statements(stmt.finalbody, [(final_node["id"], "main")], loop_ctx)
        return merged

    def _create_node(
        self,
        code: str,
        stmt: ast.AST | None = None,
        kind: str = "statement",
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> CFGNode:
        collector = SymbolCollector()
        if stmt is not None:
            collector.visit(stmt)
        node = {
            "id": self._new_node_id(),
            "code": code.strip() or "pass",
            "calls": sorted(collector.calls),
            "defs": sorted(collector.defs),
            "uses": sorted(collector.uses),
            "effects": sorted(collector.effects),
            "kind": kind,
            "intent": self._infer_intent(code.strip() or "pass", stmt, kind, collector),
            "start_line": start_line,
            "end_line": end_line,
        }
        self.nodes.append(node)
        return node

    def _connect_incoming(self, incoming: list[Connector], target_id: str) -> None:
        for source_id, edge_type in incoming:
            self._add_edge(source_id, target_id, edge_type)

    def _add_edge(self, from_id: str, to_id: str, edge_type: str) -> None:
        edge = {"from": from_id, "to": to_id, "type": edge_type}
        if edge not in self.edges:
            self.edges.append(edge)

    def _new_node_id(self) -> str:
        node_id = f"BB{self._counter}"
        self._counter += 1
        return node_id

    def _stmt_source(self, stmt: ast.AST) -> str:
        try:
            source = ast.get_source_segment(self.function_source, stmt)
        except (IndexError, ValueError):
            source = None
        return source if source else ast.unparse(stmt)

    def _line_span(self, stmt: ast.AST, header_only: bool = False) -> tuple[int, int]:
        lineno = getattr(stmt, "lineno", None)
        end_lineno = getattr(stmt, "end_lineno", None)
        if lineno is None:
            return (1, 1)
        start_line = self._relative_line(lineno)
        if header_only or end_lineno is None:
            return (start_line, start_line)
        return (start_line, self._relative_line(end_lineno))

    def _relative_line(self, absolute_lineno: int) -> int:
        return max(1, absolute_lineno - self.base_lineno)

    def _infer_intent(
        self,
        code: str,
        stmt: ast.AST | None,
        kind: str,
        collector: SymbolCollector,
    ) -> str:
        if isinstance(stmt, ast.Return):
            return tr(self.language, "cfg.return")
        if isinstance(stmt, ast.Raise):
            return tr(self.language, "cfg.raise")
        if isinstance(stmt, ast.Break):
            return tr(self.language, "cfg.break")
        if isinstance(stmt, ast.Continue):
            return tr(self.language, "cfg.continue")
        if kind == "loop":
            if isinstance(stmt, (ast.For, ast.AsyncFor)):
                return tr(self.language, "cfg.loop_for", target=ast.unparse(stmt.iter))
            if isinstance(stmt, ast.While):
                return tr(self.language, "cfg.loop_while", condition=ast.unparse(stmt.test))
            return tr(self.language, "cfg.loop")
        if kind == "condition":
            if isinstance(stmt, ast.expr):
                return tr(self.language, "cfg.condition_expr", condition=ast.unparse(stmt))
            return tr(self.language, "cfg.condition")
        if kind == "try":
            return tr(self.language, "cfg.try")
        if kind == "except":
            return tr(self.language, "cfg.except")
        if kind == "finally":
            return tr(self.language, "cfg.finally")
        if kind == "exit":
            return tr(self.language, "cfg.exit")
        if kind == "empty":
            return tr(self.language, "cfg.empty")

        if isinstance(stmt, (ast.Assign, ast.AnnAssign)) and collector.defs:
            defs = ", ".join(sorted(collector.defs))
            if self._looks_like_initialization(stmt):
                return tr(self.language, "cfg.initialize", names=defs)
            return tr(self.language, "cfg.compute_update", names=defs)
        if isinstance(stmt, ast.AugAssign) and collector.defs:
            defs = ", ".join(sorted(collector.defs))
            return tr(self.language, "cfg.update_running", names=defs)
        if isinstance(stmt, ast.Expr) and collector.calls:
            call_name = sorted(collector.calls)[0]
            return tr(self.language, "cfg.perform_call", name=call_name)
        if collector.calls:
            call_name = sorted(collector.calls)[0]
            return tr(self.language, "cfg.use_call", name=call_name)
        if collector.defs:
            defs = ", ".join(sorted(collector.defs))
            return tr(self.language, "cfg.prepare", names=defs)
        if collector.effects:
            return tr(self.language, "cfg.side_effect")
        return tr(self.language, "cfg.execute", code=code)

    @staticmethod
    def _looks_like_initialization(stmt: ast.AST) -> bool:
        value = getattr(stmt, "value", None)
        return isinstance(value, (ast.Constant, ast.List, ast.Dict, ast.Set, ast.Tuple))


def build_cfg_for_function(source_code: str, function_name: str, language: str = "en") -> CFGResult:
    language = normalize_language(language)
    source = textwrap.dedent(source_code).strip()
    if not source:
        raise ValueError(tr(language, "error.source_empty"))

    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise ValueError(tr(language, "error.invalid_python", error=exc)) from exc

    function_def = next(
        (
            node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name
        ),
        None,
    )
    if function_def is None:
        raise ValueError(tr(language, "error.function_not_found", function_name=function_name))

    function_source = ast.get_source_segment(source, function_def)
    if not function_source:
        function_source = ast.unparse(function_def)

    try:
        normalized_tree = ast.parse(function_source)
        normalized_function_def = next(
            (
                node
                for node in normalized_tree.body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name
            ),
            None,
        )
    except SyntaxError:
        normalized_function_def = None

    target_function_def = normalized_function_def or function_def
    base_lineno = 0 if normalized_function_def is not None else function_def.lineno - 1
    builder = CFGBuilder(function_source, base_lineno=base_lineno, language=language)
    return builder.build(target_function_def)
