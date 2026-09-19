"""Intent: the gate criteria. A budget nobody can fail is decoration."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import budget_check  # noqa: E402
from sol import ModelDefect  # noqa: E402

DIGEST = "sha256:0123456789abcdef"

BUDGET = f"""# Budget

graph: {DIGEST}
window: 33.300 ms, margin 25%
critical path SOL: 4.000 ms
allowed critical path: 24.975 ms

| node | regime | SOL (ms) | fraction | allowed p99 (ms) |
|---|---|---|---|---|
| capture | memory | 2.000 | 0.70 | 4.000 |
| infer | compute | 8.000 | 0.85 | 10.000 |
"""

HEADER = "node,mean_ms,p99_ms,sol_ms,ratio,build,date,graph"


def _perf(tmp_path, rows, revisions=None, budget=BUDGET):
    perf = tmp_path / "perf"
    perf.mkdir()
    (perf / "budget.md").write_text(budget)
    (perf / "measurements.csv").write_text("\n".join([HEADER, *rows]) + "\n")
    if revisions is not None:
        (perf / "budget_revisions.md").write_text(revisions)
    return perf


def _row(node, p99, sol_ms, graph=DIGEST):
    return f"{node},{p99},{p99},{sol_ms},{p99 / sol_ms},abc123,2026-09-16,{graph}"


def test_a_p99_inside_its_budget_passes(tmp_path):
    perf = _perf(tmp_path, [_row("capture", 3.0, 2.0)])
    assert budget_check.check(perf) == (True, [])


def test_a_p99_over_budget_fails_and_says_by_how_much(tmp_path):
    perf = _perf(tmp_path, [_row("capture", 6.0, 2.0)])
    ok, findings = budget_check.check(perf)
    assert not ok
    assert "over budget 4.000 ms" in findings[0]


def test_a_dated_revision_naming_the_node_clears_the_failure(tmp_path):
    perf = _perf(
        tmp_path,
        [_row("capture", 6.0, 2.0)],
        revisions=(
            "| date | node | allowed p99 (ms) | reason |\n"
            "|---|---|---|---|\n"
            "| 2026-09-16 | capture | 6.500 | VIC now shares the fabric with the encoder |\n"
        ),
    )
    assert budget_check.check(perf) == (True, [])


def test_a_revision_for_a_different_node_does_not_clear_this_one(tmp_path):
    perf = _perf(
        tmp_path,
        [_row("capture", 6.0, 2.0)],
        revisions=(
            "| date | node | allowed p99 (ms) | reason |\n"
            "|---|---|---|---|\n"
            "| 2026-09-16 | infer | 12.000 | different node entirely |\n"
        ),
    )
    ok, findings = budget_check.check(perf)
    assert not ok
    assert findings[0].startswith("capture:")


def test_an_undated_revision_row_is_not_a_revision(tmp_path):
    perf = _perf(
        tmp_path,
        [_row("capture", 6.0, 2.0)],
        revisions=(
            "| date | node | allowed p99 (ms) | reason |\n"
            "|---|---|---|---|\n"
            "|  | capture | 6.500 | forgot the date |\n"
        ),
    )
    assert budget_check.check(perf)[0] is False


def test_a_measurement_against_another_graph_is_refused_not_compared(tmp_path):
    perf = _perf(tmp_path, [_row("capture", 1.0, 2.0, graph="sha256:deadbeefdeadbeef")])
    ok, findings = budget_check.check(perf)
    assert not ok
    assert "Re-derive the SOL before comparing" in findings[0]


def test_a_p99_under_its_own_sol_is_a_model_defect_not_a_win(tmp_path):
    perf = _perf(tmp_path, [_row("capture", 1.0, 2.0)])
    ok, findings = budget_check.check(perf)
    assert not ok
    assert findings[0].startswith("MODEL_DEFECT: capture")


def test_the_serial_total_over_the_window_fails_even_when_every_node_passes(tmp_path):
    budget = BUDGET.replace("allowed critical path: 24.975 ms", "allowed critical path: 5.000 ms")
    perf = _perf(tmp_path, [_row("capture", 3.0, 2.0), _row("infer", 9.0, 8.0)], budget=budget)
    ok, findings = budget_check.check(perf)
    assert not ok
    assert findings[-1].startswith("total node p99: 12.000 ms")


def test_the_window_finding_is_the_sum_and_says_so_rather_than_claiming_a_critical_path(tmp_path):
    # capture and infer would overlap on different units: longest path 9 ms, sum 12 ms.
    # The check has no edges, so it can only report the sum — and must not call it the
    # critical path, or a pipeline that meets its deadline reads as a failure.
    budget = BUDGET.replace("allowed critical path: 24.975 ms", "allowed critical path: 10.000 ms")
    perf = _perf(tmp_path, [_row("capture", 3.0, 2.0), _row("infer", 9.0, 8.0)], budget=budget)
    finding = budget_check.check(perf)[1][-1]
    assert "12.000 ms" in finding
    assert "serial upper bound, not the critical path" in finding


def test_a_reordered_revisions_header_is_refused_rather_than_read_positionally(tmp_path):
    perf = _perf(
        tmp_path,
        [_row("capture", 6.0, 2.0)],
        revisions=(
            "| node | date | allowed p99 (ms) | reason |\n"
            "|---|---|---|---|\n"
            "| capture | 2026-09-16 | 6.500 | columns swapped |\n"
        ),
    )
    with pytest.raises(ModelDefect, match="header"):
        budget_check.check(perf)


def test_a_measured_node_absent_from_the_budget_fails(tmp_path):
    perf = _perf(tmp_path, [_row("undeclared", 3.0, 2.0)])
    ok, findings = budget_check.check(perf)
    assert not ok
    assert "absent from budget.md" in findings[0]


def test_a_budget_without_its_graph_header_is_refused(tmp_path):
    perf = _perf(tmp_path, [_row("capture", 3.0, 2.0)], budget=BUDGET.replace(f"graph: {DIGEST}", ""))
    with pytest.raises(ModelDefect, match="graph"):
        budget_check.check(perf)


def test_main_emits_the_gate_line_and_a_nonzero_exit_on_failure(tmp_path, capsys):
    perf = _perf(tmp_path, [_row("capture", 6.0, 2.0)])
    assert budget_check.main(["--perf", str(perf)]) == 1
    assert budget_check.FAIL in capsys.readouterr().err


def test_main_exits_zero_and_says_pass_when_every_node_is_inside_budget(tmp_path, capsys):
    perf = _perf(tmp_path, [_row("capture", 3.0, 2.0)])
    assert budget_check.main(["--perf", str(perf)]) == 0
    assert budget_check.PASS in capsys.readouterr().err
