"""Intent: the acceptance list. Each test names the failure mode the skill
exists to prevent, not the function it calls."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import sol  # noqa: E402
from sol import Graph, GraphDefect, MachineModel, ModelDefect  # noqa: E402

# 1 GB/s everywhere makes every floor a round number of bytes, so a wrong floor is
# visible as a wrong byte count rather than hidden in float noise.
GB = 1e9

MODEL = """
# Machine model

```yaml
config: {chip: test, clocks: locked}
memory:
  dram: {shared: true}
  sram: {shared: false}
units:
  cpu:
    sustained_ops: {value: 1.0e9, unit: op/s, method: unit_bench, date: 2026-09-16}
    sustained_bytes: {value: 1.0e9, unit: B/s, method: unit_bench, date: 2026-09-16}
    dispatch_latency: {value: 0.0, unit: s, method: unit_bench, date: 2026-09-16}
    completion_latency: {value: 0.0, unit: s, method: unit_bench, date: 2026-09-16}
  dma:
    sustained_bytes: {value: 1.0e9, unit: B/s, method: unit_bench, date: 2026-09-16}
    dispatch_latency: {value: 0.0, unit: s, method: unit_bench, date: 2026-09-16}
    completion_latency: {value: 0.0, unit: s, method: unit_bench, date: 2026-09-16}
fabric:
  knee: {value: 1.0e9, unit: B/s, method: contention_sweep, date: 2026-09-16}
  theoretical: {value: 1.0e11, unit: B/s, method: datasheet, measured: false}
tax:
  syscall: {value: 1.0e-6, unit: s, method: tax_bench, date: 2026-09-16}
  cpu_ceiling: {value: 1.0e9, unit: B/s, method: tax_bench, date: 2026-09-16}
```
"""


def _model(text=MODEL):
    return MachineModel(sol.yaml.safe_load(sol._yaml_block(text)))


def _graph(nodes, edges=(), period=0.0, margin=0.25):
    return Graph(
        {
            "target": "test",
            "window": {"period_s": period, "margin": margin},
            "nodes": list(nodes),
            "edges": list(edges),
        }
    )


def _node(node_id, **kw):
    return {"id": node_id, "unit": "cpu", "memory": "dram", **kw}


def test_a_hidden_copy_raises_the_sol_once_it_is_made_explicit():
    hidden = _graph(
        [_node("produce", bytes=GB), _node("consume", bytes=GB)],
        [{"from": "produce", "to": "consume", "bytes": GB, "handoff": "copy"}],
    )
    explicit = _graph(
        [_node("produce", bytes=GB), _node("copy", unit="dma", bytes=GB), _node("consume", bytes=GB)],
        [
            {"from": "produce", "to": "copy", "bytes": GB, "handoff": "copy", "via": "copy"},
            {"from": "copy", "to": "consume", "bytes": GB, "handoff": "inplace"},
        ],
    )
    model = _model()
    assert sol.solve(explicit, model).critical_path > sol.solve(hidden, model).critical_path


def test_an_unpaid_copy_handoff_is_named_in_the_table():
    graph = _graph(
        [_node("produce", bytes=GB), _node("consume", bytes=GB)],
        [{"from": "produce", "to": "consume", "bytes": GB, "handoff": "copy"}],
    )
    assert [e.dst for e in graph.hidden_copies()] == ["consume"]


def test_an_explicit_copy_node_is_not_reported_as_hidden():
    graph = _graph(
        [_node("produce", bytes=GB), _node("copy", bytes=GB), _node("consume", bytes=GB)],
        [{"from": "produce", "to": "copy", "bytes": GB, "handoff": "copy", "via": "copy"}],
    )
    assert graph.hidden_copies() == []


def test_changing_the_graph_changes_the_digest_so_an_old_sol_cannot_be_reused():
    before = _graph([_node("a", bytes=GB)])
    after = _graph([_node("a", bytes=GB), _node("b", bytes=GB)])
    assert before.digest != after.digest


def test_reordering_nothing_leaves_the_digest_stable():
    spec = [_node("a", bytes=GB)]
    assert _graph(spec).digest == _graph(spec).digest


def test_a_stage_under_its_own_floor_is_a_model_defect_naming_the_row():
    graph = _graph([_node("a", bytes=GB)])
    floors = sol.solve(graph, _model()).floors["a"]
    message = sol.model_defect("a", floors, measured=floors.sol / 2)
    assert message is not None
    assert "MODEL_DEFECT" in message
    assert "units.cpu.sustained_bytes" in message


def test_a_stage_at_its_floor_is_not_a_model_defect():
    graph = _graph([_node("a", bytes=GB)])
    floors = sol.solve(graph, _model()).floors["a"]
    assert sol.model_defect("a", floors, measured=floors.sol) is None


def test_overlap_past_the_knee_lowers_the_memory_floors_and_terminates():
    # Four nodes, 1 GB each, on a 1 GB/s knee: 4 s of fabric demand cannot fit in the
    # 1 s the isolated per-unit bandwidth would predict.
    graph = _graph([_node(f"n{i}", bytes=GB) for i in range(4)])
    isolated = sol._floors(graph.nodes[0], _model(), sol.Bandwidth(GB, "units.cpu.sustained_bytes"))
    solution = sol.solve(graph, _model())
    assert solution.degraded
    assert solution.fabric_iters < sol.MAX_FABRIC_ITERS
    assert solution.floors["n0"].memory > isolated.memory


def test_unit_private_memory_is_not_degraded_by_fabric_contention():
    shared = _graph([_node(f"n{i}", bytes=GB) for i in range(4)])
    private = _graph([_node(f"n{i}", bytes=GB, memory="sram") for i in range(4)])
    assert not sol.solve(private, _model()).degraded
    assert sol.solve(private, _model()).floors["n0"].memory < sol.solve(shared, _model()).floors["n0"].memory


def test_an_undeclared_memory_type_is_refused_rather_than_assumed_shared():
    graph = _graph([_node("a", bytes=GB, memory="lpddr")])
    with pytest.raises(ModelDefect, match="not declared"):
        sol.solve(graph, _model())


def test_an_unmeasured_row_is_never_spent_as_a_floor():
    text = MODEL.replace(
        "sustained_bytes: {value: 1.0e9, unit: B/s, method: unit_bench, date: 2026-09-16}",
        "sustained_bytes: {value: 1.0e11, unit: B/s, method: datasheet, measured: false}",
        1,
    )
    graph = _graph([_node("a", bytes=GB)])
    with pytest.raises(ModelDefect, match="unmeasured"):
        sol.solve(graph, _model(text))


def test_theoretical_fabric_bandwidth_is_unreachable_from_a_floor():
    text = MODEL.replace(
        "  knee: {value: 1.0e9, unit: B/s, method: contention_sweep, date: 2026-09-16}\n", ""
    )
    graph = _graph([_node("a", bytes=GB)])
    with pytest.raises(ModelDefect, match="fabric.knee"):
        sol.solve(graph, _model(text))


def test_a_crossing_is_priced_and_not_treated_as_free():
    free = sol.solve(_graph([_node("a", bytes=GB)]), _model()).floors["a"]
    taxed = sol.solve(_graph([_node("a", bytes=GB, crossings=["syscall"])]), _model()).floors["a"]
    assert taxed.tax == pytest.approx(1.0e-6)  # exactly tax.syscall, no rounding involved
    assert free.tax == 0.0


def test_the_regime_names_the_floor_that_won():
    compute_bound = sol.solve(_graph([_node("a", ops=4e9, bytes=GB)]), _model()).floors["a"]
    assert compute_bound.regime == "compute"
    assert compute_bound.regime_row == "units.cpu.sustained_ops"


def test_the_critical_path_follows_the_longest_chain_not_the_node_count():
    chain = _graph(
        [_node("a", bytes=GB), _node("b", bytes=GB), _node("c", bytes=GB, memory="sram")],
        [{"from": "a", "to": "b"}],
    )
    solution = sol.solve(chain, _model())
    assert solution.critical_path == pytest.approx(
        solution.floors["a"].sol + solution.floors["b"].sol
    )


def test_a_cycle_is_refused_rather_than_walked_forever():
    graph = _graph(
        [_node("a", bytes=GB), _node("b", bytes=GB)],
        [{"from": "a", "to": "b"}, {"from": "b", "to": "a"}],
    )
    with pytest.raises(GraphDefect, match="cycle"):
        sol.solve(graph, _model())


def test_an_edge_sync_cost_lands_on_the_critical_path():
    plain = _graph([_node("a", bytes=GB), _node("b", bytes=GB)], [{"from": "a", "to": "b"}])
    synced = _graph(
        [_node("a", bytes=GB), _node("b", bytes=GB)],
        [{"from": "a", "to": "b", "sync": "syscall"}],
    )
    model = _model()
    delta = sol.solve(synced, model).critical_path - sol.solve(plain, model).critical_path
    assert delta == pytest.approx(1.0e-6)


def test_a_pipeline_sol_past_the_window_stops_before_any_implementation(tmp_path):
    perf = tmp_path / "perf"
    perf.mkdir()
    (perf / "machine_model.md").write_text(MODEL)
    (perf / "dataflow.yaml").write_text(
        "target: test\nwindow: {period_s: 0.5, margin: 0.25}\n"
        "nodes:\n  - {id: a, unit: cpu, memory: dram, bytes: 1.0e9}\n"
    )
    with pytest.raises(GraphDefect, match="window minus"):
        sol.derive(perf)


def test_budget_is_sol_divided_by_the_regimes_fraction():
    solution = sol.solve(_graph([_node("a", bytes=GB)]), _model())
    assert solution.budgets["a"] == pytest.approx(solution.floors["a"].sol / 0.70)


def test_a_per_node_fraction_overrides_the_regime_default():
    solution = sol.solve(_graph([_node("a", bytes=GB, fraction=0.5)]), _model())
    assert solution.budgets["a"] == pytest.approx(solution.floors["a"].sol / 0.5)


def test_derive_writes_both_artefacts_carrying_the_same_digest(tmp_path):
    perf = tmp_path / "perf"
    perf.mkdir()
    (perf / "machine_model.md").write_text(MODEL)
    (perf / "dataflow.yaml").write_text(
        "target: test\nwindow: {period_s: 4.0, margin: 0.25}\n"
        "nodes:\n  - {id: a, unit: cpu, memory: dram, bytes: 1.0e9}\n"
    )
    solution = sol.derive(perf)
    assert solution.digest in (perf / "sol_table.md").read_text()
    assert solution.digest in (perf / "budget.md").read_text()
