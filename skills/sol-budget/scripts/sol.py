#!/usr/bin/env python3
"""Speed-of-light floors and budgets from a measured machine model and a dataflow.

Reads the yaml block inside perf/machine_model.md plus perf/dataflow.yaml; writes
perf/sol_table.md and perf/budget.md.

Two refusals carry the whole design. A row marked `measured: false` can be read but
never spent as a floor — a datasheet number in a measured column is how a budget
becomes fiction. And `fabric.theoretical` is never consulted at all: the only
bandwidth Phase 2 may spend is the §5 saturation knee, measured under the overlap
the pipeline actually creates.

The graph digest travels into budget.md and measurements.csv so a measurement taken
against one graph can never be compared to a ceiling derived from another.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - environment, not logic
    sys.exit("sol-budget needs PyYAML: pip install pyyaml")

SUMMARY = "Speed-of-light floors and budgets from a measured machine model and a dataflow."

FABRIC_TOL = 0.01
MAX_FABRIC_ITERS = 64

# Fraction of SOL a node is allowed to spend, by which floor won. A dispatch-dominated
# node gets the loosest budget because its floor is the least predictive.
FRACTION = {"memory": 0.70, "tax": 0.50, "compute": 0.85}
MARGIN = {"shared-fabric": 0.25, "bare-metal": 0.10}

INPLACE = "inplace"


class ModelDefect(RuntimeError):
    """The machine model is what needs fixing, not the implementation."""


class GraphDefect(RuntimeError):
    """The dataflow does not describe what the machine will actually do."""


@dataclass(frozen=True)
class Row:
    key: str
    value: float
    unit: str
    method: str
    date: str
    measured: bool

    def spend(self) -> float:
        if not self.measured:
            raise ModelDefect(
                f"{self.key} is unmeasured (method: {self.method!r}). A modelled or "
                "datasheet number is never a floor — run its bench, or drop the node."
            )
        return self.value

    def rate(self) -> float:
        """A row used as a divisor. Zero latency is a measurement; zero throughput is
        a row nobody filled in, and dividing by it would report an infinite floor."""
        if self.spend() <= 0:
            raise ModelDefect(f"{self.key} is {self.value}; a floor needs a positive rate")
        return self.value


@dataclass(frozen=True)
class Bandwidth:
    value: float
    row: str


@dataclass(frozen=True)
class Node:
    id: str
    unit: str
    ops: float = 0.0
    nbytes: float = 0.0
    memory: str = ""
    crossings: tuple[str, ...] = ()
    crossing_bytes: float = 0.0
    fraction: float | None = None


@dataclass(frozen=True)
class Edge:
    src: str
    dst: str
    nbytes: float = 0.0
    memory: str = ""
    handoff: str = INPLACE
    sync: str = ""
    # The node that pays for a copy/convert handoff. Named, never inferred: an
    # unpaid handoff is bytes moving that no floor in the table accounts for.
    via: str = ""


@dataclass(frozen=True)
class Floors:
    compute: float
    memory: float
    tax: float
    dispatch: float
    completion: float
    rows: dict[str, str]

    @property
    def regime(self) -> str:
        return max(("compute", self.compute), ("memory", self.memory), ("tax", self.tax),
                   key=lambda pair: pair[1])[0]

    @property
    def sol(self) -> float:
        return max(self.compute, self.memory, self.tax) + self.dispatch + self.completion

    @property
    def regime_row(self) -> str:
        return self.rows.get(self.regime, "")


class MachineModel:
    def __init__(self, raw: dict):
        self.config = raw.get("config") or {}
        self._rows = _flatten_rows(raw)
        self._shared = {
            name: bool(spec.get("shared", True))
            for name, spec in (raw.get("memory") or {}).items()
        }

    def row(self, key: str) -> Row:
        row = self._rows.get(key)
        if row is None:
            raise ModelDefect(
                f"machine model has no row {key!r} — Phase 1 is incomplete for this graph"
            )
        return row

    def knee(self) -> Bandwidth:
        """§5, never §2. `fabric.theoretical` is deliberately unreachable from here."""
        return Bandwidth(self.row("fabric.knee").rate(), "fabric.knee")

    def shared(self, memory: str) -> bool:
        if memory and memory not in self._shared:
            raise ModelDefect(
                f"memory type {memory!r} is not declared in the model's `memory:` section; "
                "whether it crosses the shared fabric decides every memory floor"
            )
        return self._shared.get(memory, True)

    @classmethod
    def load(cls, path: Path) -> MachineModel:
        return cls(yaml.safe_load(_yaml_block(path.read_text())) or {})


class Graph:
    def __init__(self, raw: dict):
        self.target = raw.get("target", "")
        window = raw.get("window") or {}
        self.period = float(window.get("period_s", 0.0))
        self.margin = float(window.get("margin", MARGIN[window.get("lane", "shared-fabric")]))
        self.nodes = [_node(n) for n in raw.get("nodes") or []]
        self.edges = [_edge(e) for e in raw.get("edges") or []]
        self._by_id = {n.id: n for n in self.nodes}
        if len(self._by_id) != len(self.nodes):
            raise GraphDefect("two nodes share an id; every node id must be unique")
        for e in self.edges:
            for end in (e.src, e.dst):
                if end not in self._by_id:
                    raise GraphDefect(f"edge references unknown node {end!r}")

    def node(self, node_id: str) -> Node:
        return self._by_id[node_id]

    @property
    def digest(self) -> str:
        payload = json.dumps(
            {
                "nodes": [vars(n) | {"crossings": list(n.crossings)} for n in self.nodes],
                "edges": [vars(e) for e in self.edges],
                "window": [self.period, self.margin],
            },
            sort_keys=True,
        )
        return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()[:16]

    def hidden_copies(self) -> list[Edge]:
        """Edges the handoff matrix prices as copy/convert with no node to pay for it."""
        return [
            e
            for e in self.edges
            if e.handoff != INPLACE and e.via not in self._by_id
        ]

    @classmethod
    def load(cls, path: Path) -> Graph:
        return cls(yaml.safe_load(path.read_text()) or {})


def _yaml_block(text: str) -> str:
    lines = text.splitlines()
    try:
        start = next(i for i, ln in enumerate(lines) if ln.strip() == "```yaml")
    except StopIteration:
        raise ModelDefect(
            "machine_model.md has no ```yaml block; the rows are the machine-readable half"
        ) from None
    for offset, ln in enumerate(lines[start + 1 :]):
        if ln.strip() == "```":
            return "\n".join(lines[start + 1 : start + 1 + offset])
    raise ModelDefect("machine_model.md's ```yaml block is never closed")


def _flatten_rows(raw: dict, prefix: str = "") -> dict[str, Row]:
    rows: dict[str, Row] = {}
    for name, spec in raw.items():
        if name in ("config", "memory") and not prefix:
            continue
        key = f"{prefix}{name}"
        if isinstance(spec, dict) and "value" in spec:
            rows[key] = Row(
                key=key,
                value=float(spec["value"]),
                unit=str(spec.get("unit", "")),
                method=str(spec.get("method", "")),
                date=str(spec.get("date", "")),
                measured=bool(spec.get("measured", True)),
            )
        elif isinstance(spec, dict):
            rows.update(_flatten_rows(spec, f"{key}."))
    return rows


def _node(raw: dict) -> Node:
    return Node(
        id=str(raw["id"]),
        unit=str(raw.get("unit", "")),
        ops=float(raw.get("ops", 0.0)),
        nbytes=float(raw.get("bytes", 0.0)),
        memory=str(raw.get("memory", "")),
        crossings=tuple(raw.get("crossings") or ()),
        crossing_bytes=float(raw.get("crossing_bytes", 0.0)),
        fraction=None if raw.get("fraction") is None else float(raw["fraction"]),
    )


def _edge(raw: dict) -> Edge:
    return Edge(
        src=str(raw["from"]),
        dst=str(raw["to"]),
        nbytes=float(raw.get("bytes", 0.0)),
        memory=str(raw.get("memory", "")),
        handoff=str(raw.get("handoff", INPLACE)),
        sync=str(raw.get("sync", "")),
        via=str(raw.get("via", "")),
    )


def _floors(node: Node, model: MachineModel, bw: Bandwidth) -> Floors:
    rows: dict[str, str] = {}
    compute = 0.0
    if node.ops:
        row = model.row(f"units.{node.unit}.sustained_ops")
        compute, rows["compute"] = node.ops / row.rate(), row.key
    memory = 0.0
    if node.nbytes:
        memory, rows["memory"] = node.nbytes / bw.value, bw.row
    tax = 0.0
    for crossing in node.crossings:
        row = model.row(f"tax.{crossing}")
        tax += row.spend()
        rows.setdefault("tax", row.key)
    if node.crossing_bytes:
        row = model.row(f"tax.{node.unit}_ceiling")
        tax += node.crossing_bytes / row.rate()
        rows.setdefault("tax", row.key)
    dispatch = _latency(model, node.unit, "dispatch_latency")
    completion = _latency(model, node.unit, "completion_latency")
    return Floors(compute, memory, tax, dispatch, completion, rows)


def _latency(model: MachineModel, unit: str, which: str) -> float:
    if not unit:
        return 0.0
    return model.row(f"units.{unit}.{which}").spend()


def _unit_bandwidth(node: Node, model: MachineModel) -> Bandwidth:
    if not node.nbytes:
        return Bandwidth(1.0, "")
    row = model.row(f"units.{node.unit}.sustained_bytes")
    return Bandwidth(row.rate(), row.key)


def _critical_path(graph: Graph, floors: dict[str, Floors], model: MachineModel) -> float:
    indegree = {n.id: 0 for n in graph.nodes}
    out: dict[str, list[Edge]] = {n.id: [] for n in graph.nodes}
    for e in graph.edges:
        indegree[e.dst] += 1
        out[e.src].append(e)
    finish = {n.id: floors[n.id].sol for n in graph.nodes}
    queue = deque(nid for nid, deg in indegree.items() if deg == 0)
    seen = 0
    while queue:
        nid = queue.popleft()
        seen += 1
        for e in out[nid]:
            sync = model.row(f"tax.{e.sync}").spend() if e.sync else 0.0
            finish[e.dst] = max(finish[e.dst], finish[nid] + sync + floors[e.dst].sol)
            indegree[e.dst] -= 1
            if indegree[e.dst] == 0:
                queue.append(e.dst)
    if seen != len(graph.nodes):
        raise GraphDefect("the dataflow has a cycle; a critical path needs a DAG")
    return max(finish.values(), default=0.0)


@dataclass
class Solution:
    floors: dict[str, Floors]
    critical_path: float
    fabric_iters: int
    degraded: bool
    digest: str
    allowed_critical_path: float
    budgets: dict[str, float] = field(default_factory=dict)


def solve(graph: Graph, model: MachineModel) -> Solution:
    """Floors, critical path, and budgets, with the fabric made self-consistent.

    Overlapping demand above the measured knee degrades every shared-memory node's
    bandwidth and re-derives; that raises the critical path, which lowers offered
    load, so the loop is monotone and terminates.
    """
    bw = {n.id: _unit_bandwidth(n, model) for n in graph.nodes}
    knee = graph_knee = model.knee().value
    fabric_bytes = sum(n.nbytes for n in graph.nodes if model.shared(n.memory))
    degraded = False
    for iteration in range(1, MAX_FABRIC_ITERS + 1):
        floors = {n.id: _floors(n, model, bw[n.id]) for n in graph.nodes}
        critical = _critical_path(graph, floors, model)
        if not fabric_bytes or critical <= 0:
            return _finish(graph, floors, critical, iteration, degraded)
        offered = fabric_bytes / critical
        if offered <= knee * (1 + FABRIC_TOL):
            return _finish(graph, floors, critical, iteration, degraded)
        degraded = True
        scale = graph_knee / offered
        bw = {
            n.id: Bandwidth(bw[n.id].value * scale, bw[n.id].row)
            if model.shared(n.memory)
            else bw[n.id]
            for n in graph.nodes
        }
    raise ModelDefect(
        "fabric self-consistency did not converge in "
        f"{MAX_FABRIC_ITERS} iterations — check fabric.knee and the per-node byte counts"
    )


def _finish(graph: Graph, floors, critical: float, iters: int, degraded: bool) -> Solution:
    window = graph.period * (1 - graph.margin) if graph.period else 0.0
    sol = Solution(floors, critical, iters, degraded, graph.digest, window)
    for node in graph.nodes:
        fraction = node.fraction or FRACTION[floors[node.id].regime]
        sol.budgets[node.id] = floors[node.id].sol / fraction
    return sol


def model_defect(node_id: str, floors: Floors, measured: float) -> str | None:
    """A stage faster than its own floor is a broken model row, never a result."""
    if measured >= floors.sol or floors.sol <= 0:
        return None
    return (
        f"MODEL_DEFECT: {node_id} measured {measured:.6g}s under its SOL {floors.sol:.6g}s "
        f"(regime {floors.regime}, row {floors.regime_row or 'unattributed'}). "
        "Re-measure that row before reporting anything."
    )


def _ms(seconds: float) -> str:
    return f"{seconds * 1e3:.3f}"


def render_sol_table(graph: Graph, model: MachineModel, sol: Solution) -> str:
    lines = [
        "# SOL table",
        "",
        f"graph: {sol.digest}",
        f"target: {graph.target}",
        f"machine model config: {json.dumps(model.config, sort_keys=True)}",
        f"fabric iterations: {sol.fabric_iters}"
        + (" (degraded below isolated BW)" if sol.degraded else ""),
        "",
        "| node | unit | regime | compute (ms) | memory (ms) | tax (ms) | SOL (ms) | row |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for node in graph.nodes:
        f = sol.floors[node.id]
        lines.append(
            f"| {node.id} | {node.unit} | {f.regime} | {_ms(f.compute)} | {_ms(f.memory)} "
            f"| {_ms(f.tax)} | {_ms(f.sol)} | {f.regime_row or '-'} |"
        )
    lines += ["", f"critical path SOL: {_ms(sol.critical_path)} ms"]
    hidden = graph.hidden_copies()
    if hidden:
        lines += ["", "## Hidden handoffs"]
        lines += [
            f"- {e.src} -> {e.dst} is `{e.handoff}` in the handoff matrix with no node "
            f"paying for it; {e.nbytes:.0f} B are missing from every floor above."
            for e in hidden
        ]
    return "\n".join(lines) + "\n"


def render_budget(graph: Graph, sol: Solution) -> str:
    lines = [
        "# Budget",
        "",
        f"graph: {sol.digest}",
        f"window: {_ms(graph.period)} ms, margin {graph.margin:.0%}",
        f"critical path SOL: {_ms(sol.critical_path)} ms",
        f"allowed critical path: {_ms(sol.allowed_critical_path)} ms",
        "",
        "| node | regime | SOL (ms) | fraction | allowed p99 (ms) |",
        "|---|---|---|---|---|",
    ]
    for node in graph.nodes:
        f = sol.floors[node.id]
        fraction = node.fraction or FRACTION[f.regime]
        lines.append(
            f"| {node.id} | {f.regime} | {_ms(f.sol)} | {fraction:.2f} "
            f"| {_ms(sol.budgets[node.id])} |"
        )
    return "\n".join(lines) + "\n"


def derive(perf: Path) -> Solution:
    model = MachineModel.load(perf / "machine_model.md")
    graph = Graph.load(perf / "dataflow.yaml")
    sol = solve(graph, model)
    (perf / "sol_table.md").write_text(render_sol_table(graph, model, sol))
    (perf / "budget.md").write_text(render_budget(graph, sol))
    if sol.allowed_critical_path and sol.critical_path > sol.allowed_critical_path:
        raise GraphDefect(
            f"critical path SOL {_ms(sol.critical_path)} ms exceeds the window minus "
            f"margin ({_ms(sol.allowed_critical_path)} ms). The graph is wrong, not the "
            "implementation — no amount of optimisation reaches this deadline."
        )
    return sol


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=SUMMARY)
    ap.add_argument("--perf", type=Path, default=Path("perf"))
    args = ap.parse_args(argv)
    try:
        sol = derive(args.perf)
    except (ModelDefect, GraphDefect) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(
        f"sol: {len(sol.floors)} nodes, critical path {_ms(sol.critical_path)} ms, "
        f"graph {sol.digest}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
