"""Intent: dotfiles#60 — the isolated export must carry only the files it was
built from; run_isolated must not write its own prompt into the work dir it
hands to the isolated `claude` process."""

import subprocess as sp
from pathlib import Path

from mutation_gate import adversary


def test_run_isolated_does_not_write_prompt_into_the_work_dir(tmp_path, monkeypatch):
    seen = {}

    def fake_run(argv, **kwargs):
        seen["cwd_contents"] = sorted(p.name for p in Path(kwargs["cwd"]).rglob("*"))
        return sp.CompletedProcess(argv, 0, stdout="ok\n", stderr="")

    (tmp_path / "INTENT.md").write_text("intent\n")
    monkeypatch.setattr(adversary.shutil, "which", lambda name: "/usr/bin/claude")
    monkeypatch.setattr(adversary.subprocess, "run", fake_run)
    assert adversary.run_isolated("adversary", "the prompt", tmp_path) == "ok"
    assert "PROMPT.md" not in seen["cwd_contents"]
