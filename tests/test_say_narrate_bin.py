import importlib.util
import shutil
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "bin" / "say-narrate.py"


def _load_from(path: Path):
    spec = importlib.util.spec_from_file_location("say_narrate_probe", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_bin_is_the_scripts_own_directory_under_a_plugin_only_install(monkeypatch, tmp_path):
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home-without-claude"))
    plugin_bin = tmp_path / "plugin" / "bin"
    plugin_bin.mkdir(parents=True)
    shutil.copy(MODULE_PATH, plugin_bin / "say-narrate.py")

    module = _load_from(plugin_bin / "say-narrate.py")

    assert module.BIN == str(plugin_bin)


def test_bin_ignores_a_plugin_root_that_points_somewhere_else(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", "/fake/plugin/root")
    legacy_bin = tmp_path / ".claude" / "bin"
    legacy_bin.mkdir(parents=True)
    (legacy_bin / "say-narrate.py").symlink_to(MODULE_PATH)

    module = _load_from(legacy_bin / "say-narrate.py")

    assert module.BIN == str(legacy_bin)
