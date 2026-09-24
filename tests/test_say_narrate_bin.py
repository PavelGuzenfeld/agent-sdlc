import importlib.util
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "bin" / "say-narrate.py"


def _load(monkeypatch, plugin_root):
    if plugin_root is None:
        monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    else:
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", plugin_root)
    spec = importlib.util.spec_from_file_location("say_narrate_probe", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_bin_resolves_under_plugin_root_when_set(monkeypatch):
    module = _load(monkeypatch, "/fake/plugin/root")
    assert module.BIN == "/fake/plugin/root/bin"


def test_bin_falls_back_to_legacy_claude_bin_when_unset(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    module = _load(monkeypatch, None)
    assert module.BIN == str(tmp_path / ".claude" / "bin")
