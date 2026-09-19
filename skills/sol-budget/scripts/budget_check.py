#!/usr/bin/env python3
"""Measurements against budgets. Emits PERF_GATE: pass|fail for CI and verify-generated-diff.

Reads perf/budget.md, perf/measurements.csv and perf/budget_revisions.md. Three ways to
fail, and one escape:

- a node's p99 over its allowed time, unless budget_revisions.md carries a dated entry
  naming that node;
- the sum of node p99s over the window minus margin. That sum is the serial upper
  bound, not budget.md's derived critical path: a graph with overlap can beat it, so
  the finding says so rather than claiming a missed deadline;
- a row whose `graph` digest is not budget.md's, which means the SOL it was compared
  against belongs to a different dataflow. Refused, never silently accepted — a speedup
  reported against a stale ceiling is the failure mode this whole gate exists to stop.

A measured time under its own SOL is a MODEL_DEFECT, not a win: `sol.model_defect` names
the machine-model row to re-measure.
"""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sol import ModelDefect  # noqa: E402

SUMMARY = "Measurements against budgets; emits PERF_GATE for CI."

PASS = "PERF_GATE: pass"
FAIL = "PERF_GATE: fail"


@dataclass(frozen=True)
class Budget:
    node: str
    regime: str
    sol_ms: float
    fraction: float
    allowed_ms: float


@dataclass(frozen=True)
class Measurement:
    node: str
    mean_ms: float
    p99_ms: float
    sol_ms: float
    ratio: float
    build: str
    date: str
    graph: str


def _tables(text: str) -> list[tuple[list[str], list[list[str]]]]:
    """Every pipe table in a markdown document as (header, rows)."""
    tables: list[tuple[list[str], list[list[str]]]] = []
    current: list[list[str]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            if set("".join(cells)) <= set("-: "):
                continue
            current.append(cells)
        elif current:
            tables.append((current[0], current[1:]))
            current = []
    if current:
        tables.append((current[0], current[1:]))
    return tables


def _header_value(text: str, key: str) -> str:
    for line in text.splitlines():
        if line.startswith(f"{key}:"):
            return line.split(":", 1)[1].strip()
    raise ModelDefect(f"budget.md has no `{key}:` header line")


def load_budget(path: Path) -> tuple[str, float, list[Budget]]:
    text = path.read_text()
    digest = _header_value(text, "graph")
    allowed_path = float(_header_value(text, "allowed critical path").split()[0])
    tables = _tables(text)
    if not tables:
        raise ModelDefect("budget.md has no budget table")
    budgets = [
        Budget(row[0], row[1], float(row[2]), float(row[3]), float(row[4]))
        for row in tables[0][1]
    ]
    return digest, allowed_path, budgets


def load_measurements(path: Path) -> list[Measurement]:
    with path.open(newline="") as fh:
        return [
            Measurement(
                node=row["node"],
                mean_ms=float(row["mean_ms"]),
                p99_ms=float(row["p99_ms"]),
                sol_ms=float(row["sol_ms"]),
                ratio=float(row["ratio"]),
                build=row.get("build", ""),
                date=row.get("date", ""),
                graph=row.get("graph", ""),
            )
            for row in csv.DictReader(fh)
        ]


REVISION_COLUMNS = ["date", "node", "allowed p99 (ms)", "reason"]


def load_revisions(path: Path) -> set[str]:
    """Nodes with a dated revision entry. An undated row is not a revision."""
    if not path.exists():
        return set()
    revised: set[str] = set()
    for header, rows in _tables(path.read_text()):
        if header != REVISION_COLUMNS:
            # Positional: a reordered header would clear the wrong node, or every node.
            raise ModelDefect(
                f"budget_revisions.md table header is {header}, expected {REVISION_COLUMNS}"
            )
        revised.update(row[1] for row in rows if len(row) >= 4 and row[0] and row[3])
    return revised


def check(perf: Path) -> tuple[bool, list[str]]:
    digest, allowed_path, budgets = load_budget(perf / "budget.md")
    measurements = load_measurements(perf / "measurements.csv")
    revised = load_revisions(perf / "budget_revisions.md")
    by_node = {b.node: b for b in budgets}
    findings: list[str] = []

    latest: dict[str, Measurement] = {}
    for m in measurements:
        if m.graph != digest:
            findings.append(
                f"{m.node}: measured against graph {m.graph or '(none)'}, budget.md is "
                f"{digest}. Re-derive the SOL before comparing — never report against a "
                "ceiling from a different dataflow."
            )
            continue
        latest[m.node] = m

    for node, m in sorted(latest.items()):
        budget = by_node.get(node)
        if budget is None:
            findings.append(f"{node}: measured but absent from budget.md")
            continue
        if m.sol_ms > 0 and m.p99_ms < m.sol_ms:
            findings.append(
                f"MODEL_DEFECT: {node} p99 {m.p99_ms:.3f} ms is under its SOL "
                f"{m.sol_ms:.3f} ms ({budget.regime} regime). Re-measure that row; a stage "
                "faster than its floor is a broken model, not a result."
            )
            continue
        if m.p99_ms > budget.allowed_ms:
            if node in revised:
                continue
            findings.append(
                f"{node}: p99 {m.p99_ms:.3f} ms over budget {budget.allowed_ms:.3f} ms "
                f"({budget.regime}, {budget.fraction:.2f} of SOL {budget.sol_ms:.3f} ms). "
                "Kill it or add a dated budget_revisions.md entry naming this node."
            )

    serial_total = sum(m.p99_ms for m in latest.values())
    if allowed_path and serial_total > allowed_path:
        findings.append(
            f"total node p99: {serial_total:.3f} ms over window minus margin "
            f"{allowed_path:.3f} ms. This is the serial upper bound, not the critical "
            "path — a graph with real overlap can still fit, so confirm against a "
            "measured end-to-end time before calling the deadline missed."
        )
    return not findings, findings


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=SUMMARY)
    ap.add_argument("--perf", type=Path, default=Path("perf"))
    args = ap.parse_args(argv)
    try:
        ok, findings = check(args.perf)
    except (ModelDefect, FileNotFoundError, KeyError) as exc:
        print(f"{FAIL}\n{exc}", file=sys.stderr)
        return 1
    for finding in findings:
        print(f"  {finding}", file=sys.stderr)
    print(PASS if ok else FAIL, file=sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
