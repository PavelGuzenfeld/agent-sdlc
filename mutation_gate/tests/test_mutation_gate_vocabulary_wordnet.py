"""Intent: #110 (decisions 12, 37 of #103) — a canonical word a diff adds to a
dictionary layer blocks when it shares a WordNet synset, restricted to the
parts of speech both concepts declare, with an existing canonical word; a
pair in [[distinct]] or a waiver clears it; vocabulary_synonyms = "report"
turns the block into a report line; every dictionary change lists added,
changed and removed concepts under a "Dictionary" heading.

Driven through cli.main. The test image carries no git, so discover and the
diff / pre-image are stubbed; the config load, the loader, the waiver match
and the exit code are real. The synset lookup is stubbed by default so the
suite needs no network; one test at the bottom exercises real nltk WordNet
data and skips cleanly when it is not available.
"""

import zipfile
from pathlib import Path

import pytest

from mutation_gate import cli, mutants, runner, token, vocabulary, vocabulary_wordnet
from mutation_gate.repo import Config, GateError, Repo

DOMAIN = ".vocabulary.toml"
OPTED_IN = f'vocabulary = "{DOMAIN}"\n'
BLOCK_MODE = OPTED_IN + 'vocabulary_synonyms = "block"\n'
REPORT_MODE = OPTED_IN + 'vocabulary_synonyms = "report"\n'

LOCUS = '[[concept]]\nword = "locus"\nmeaning = "a site"\npos = ["noun"]\n'
GIZMO = '[[concept]]\nword = "gizmo"\nmeaning = "an unnamed device"\npos = ["noun"]\n'
CUSHION = '[[concept]]\nword = "cushion"\nmeaning = "something that softens"\npos = ["noun", "verb"]\n'
WOBBLE = '[[concept]]\nword = "wobble"\nmeaning = "something that softens contact"\npos = ["noun", "verb"]\n'
FOO_VERB = '[[concept]]\nword = "foo"\nmeaning = "to do a thing"\npos = ["verb"]\n'


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _repo(tmp_path: Path, toml: str, domain: str) -> Repo:
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    _write(root, ".mutation-gate.toml", toml)
    _write(root, DOMAIN, domain)
    return Repo(root=root, origin="", remotes=(), config=Config.load(root))


def _stub_git(monkeypatch, pre: dict[str, str]) -> None:
    def fake_git(*args: str, cwd=None) -> str:
        rel = args[-1].split(":", 1)[1]
        if rel not in pre:
            raise GateError(f"git show: path {rel!r} does not exist")
        return pre[rel]

    monkeypatch.setattr(vocabulary_wordnet, "git", fake_git)


def _fake_synsets(table: dict[tuple[str, str], frozenset[str]]):
    def fn(word: str, pos: str) -> frozenset[str]:
        return table.get((word, pos), frozenset())
    return fn


def _gate(monkeypatch, tmp_path: Path, repo: Repo, added: dict[str, set[int]],
          pre: dict[str, str], synsets=None) -> int:
    monkeypatch.setattr(cli, "discover", lambda cwd=None: repo)
    monkeypatch.setattr(mutants, "changed_lines", lambda root, staged: added)
    monkeypatch.setattr(cli.vocabulary_path, "git", lambda *a, **k: "")
    _stub_git(monkeypatch, pre)
    if synsets is not None:
        monkeypatch.setattr(vocabulary_wordnet, "synset_names", synsets)
    for mod in (cli, runner, token):
        monkeypatch.setattr(mod, "CACHE_ROOT", tmp_path / "cache")
    return cli.main(["--staged", "--no-adversary"])


def test_locus_added_beside_position_blocks_naming_both(tmp_path, monkeypatch, capsys):
    repo = _repo(tmp_path, BLOCK_MODE, LOCUS)
    synsets = _fake_synsets({
        ("locus", "noun"): frozenset({"s1"}),
        ("position", "noun"): frozenset({"s1", "s2"}),
    })
    code = _gate(monkeypatch, tmp_path, repo, {DOMAIN: {2}}, {}, synsets)
    err = capsys.readouterr().err
    assert code == 1
    assert "`locus` shares a WordNet sense with `position`" in err
    assert 'Add `locus = "position"` under [reject]' in err


def test_noun_concept_is_never_matched_against_an_existing_verb_only_word(
    tmp_path, monkeypatch, capsys
):
    pre_domain = '[[concept]]\nword = "vroom"\nmeaning = "to go fast"\npos = ["verb"]\n'
    post_domain = pre_domain + GIZMO
    repo = _repo(tmp_path, BLOCK_MODE, post_domain)
    synsets = _fake_synsets({
        ("gizmo", "noun"): frozenset({"s1"}),
        ("vroom", "noun"): frozenset({"s1"}),
    })
    code = _gate(monkeypatch, tmp_path, repo, {DOMAIN: {5}}, {DOMAIN: pre_domain}, synsets)
    assert code == 0


def test_wobble_beside_cushion_passes_when_the_pair_is_distinct(tmp_path, monkeypatch, capsys):
    pre_domain = CUSHION
    post_domain = CUSHION + WOBBLE + '[[distinct]]\npair = ["wobble", "cushion"]\n'
    repo = _repo(tmp_path, OPTED_IN, post_domain)
    synsets = _fake_synsets({
        ("wobble", "verb"): frozenset({"v1"}),
        ("cushion", "verb"): frozenset({"v1"}),
    })
    code = _gate(monkeypatch, tmp_path, repo, {DOMAIN: {5}}, {DOMAIN: pre_domain}, synsets)
    err = capsys.readouterr().err
    assert code == 0
    assert "shares a WordNet sense" not in err


def test_wobble_beside_cushion_blocks_without_a_distinct_entry(tmp_path, monkeypatch, capsys):
    pre_domain = CUSHION
    post_domain = CUSHION + WOBBLE
    repo = _repo(tmp_path, BLOCK_MODE, post_domain)
    synsets = _fake_synsets({
        ("wobble", "verb"): frozenset({"v1"}),
        ("cushion", "verb"): frozenset({"v1"}),
    })
    code = _gate(monkeypatch, tmp_path, repo, {DOMAIN: {5}}, {DOMAIN: pre_domain}, synsets)
    err = capsys.readouterr().err
    assert code == 1
    assert "`wobble` shares a WordNet sense with `cushion`" in err


def test_verb_concept_is_never_matched_against_noun_senses(tmp_path, monkeypatch, capsys):
    repo = _repo(tmp_path, BLOCK_MODE, FOO_VERB)
    synsets = _fake_synsets({
        ("foo", "verb"): frozenset({"shared"}),
        ("position", "noun"): frozenset({"shared"}),
    })
    code = _gate(monkeypatch, tmp_path, repo, {DOMAIN: {2}}, {}, synsets)
    assert code == 0


def test_new_word_with_no_collision_passes_and_reports_it_added(tmp_path, monkeypatch, capsys):
    repo = _repo(tmp_path, OPTED_IN, GIZMO)
    synsets = _fake_synsets({})
    code = _gate(monkeypatch, tmp_path, repo, {DOMAIN: {2}}, {}, synsets)
    err = capsys.readouterr().err
    assert code == 0
    assert err.splitlines()[:3] == ["Dictionary", f"  {DOMAIN}", "    added: gizmo"]


def test_removed_concept_prints_under_the_dictionary_heading(tmp_path, monkeypatch, capsys):
    repo = _repo(tmp_path, OPTED_IN, "")
    code = _gate(monkeypatch, tmp_path, repo, {DOMAIN: {1}}, {DOMAIN: GIZMO})
    err = capsys.readouterr().err
    assert code == 0
    assert err.splitlines()[:3] == ["Dictionary", f"  {DOMAIN}", "    removed: gizmo"]


def test_report_mode_prints_the_collision_and_does_not_block(tmp_path, monkeypatch, capsys):
    repo = _repo(tmp_path, REPORT_MODE, LOCUS)
    synsets = _fake_synsets({
        ("locus", "noun"): frozenset({"s1"}),
        ("position", "noun"): frozenset({"s1"}),
    })
    code = _gate(monkeypatch, tmp_path, repo, {DOMAIN: {2}}, {}, synsets)
    err = capsys.readouterr().err
    assert code == 0
    assert "`locus` shares a WordNet sense with `position`" in err


def test_default_synonyms_mode_is_report_not_block(tmp_path, monkeypatch, capsys):
    repo = _repo(tmp_path, OPTED_IN, LOCUS)
    synsets = _fake_synsets({
        ("locus", "noun"): frozenset({"s1"}),
        ("position", "noun"): frozenset({"s1"}),
    })
    code = _gate(monkeypatch, tmp_path, repo, {DOMAIN: {2}}, {}, synsets)
    err = capsys.readouterr().err
    assert code == 0
    assert "`locus` shares a WordNet sense with `position`" in err


def test_waived_collision_does_not_block(tmp_path, monkeypatch, capsys):
    repo_root_toml = OPTED_IN
    repo = _repo(tmp_path, repo_root_toml, LOCUS)
    _write(repo.root, ".mutation-gate-waivers.toml",
           '[[waiver]]\ncheck = "vocabulary-synonyms"\n'
           f'file = "{DOMAIN}"\nline = 2\n'
           'reason = "locus and position name different concepts here"\n')
    synsets = _fake_synsets({
        ("locus", "noun"): frozenset({"s1"}),
        ("position", "noun"): frozenset({"s1"}),
    })
    code = _gate(monkeypatch, tmp_path, repo, {DOMAIN: {2}}, {}, synsets)
    err = capsys.readouterr().err
    assert code == 0
    assert "shares a WordNet sense" not in err


def test_missing_nltk_refuses_cleanly_when_a_lookup_is_needed(tmp_path, monkeypatch, capsys):
    repo = _repo(tmp_path, OPTED_IN, LOCUS)
    monkeypatch.setattr(vocabulary_wordnet, "nltk", None)
    code = _gate(monkeypatch, tmp_path, repo, {DOMAIN: {2}}, {})
    err = capsys.readouterr().err
    assert code == 2
    assert err.count("\n") == 1
    assert "nltk" in err


def test_invalid_vocabulary_synonyms_value_is_refused(tmp_path, monkeypatch, capsys):
    repo = _repo(tmp_path, OPTED_IN + 'vocabulary_synonyms = "loud"\n', "")
    code = _gate(monkeypatch, tmp_path, repo, {}, {})
    err = capsys.readouterr().err
    assert code == 2
    assert "vocabulary_synonyms must be" in err


def test_check_absent_by_default_when_vocabulary_key_is_unset(tmp_path, monkeypatch, capsys):
    repo = _repo(tmp_path, "", LOCUS)
    assert repo.config.vocabulary == ""
    code = _gate(monkeypatch, tmp_path, repo, {DOMAIN: {2}}, {})
    assert code == 0
    assert "Dictionary" not in capsys.readouterr().err


def test_diff_layer_reports_added_changed_and_removed(tmp_path):
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    repo = Repo(root=root, origin="", remotes=(), config=Config())
    pre = LOCUS + GIZMO
    post = ('[[concept]]\nword = "locus"\nmeaning = "a different site"\npos = ["noun"]\n')
    _write(root, DOMAIN, post)

    def fake_git(*args: str, cwd=None) -> str:
        return pre

    import mutation_gate.vocabulary_wordnet as vw
    original = vw.git
    vw.git = fake_git
    try:
        diff = vw.diff_layer(repo, DOMAIN, True)
    finally:
        vw.git = original
    assert diff.added == ()
    assert diff.changed == ("locus",)
    assert diff.removed == ("gizmo",)


def test_diff_layer_returns_none_when_nothing_changed(tmp_path):
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    repo = Repo(root=root, origin="", remotes=(), config=Config())
    _write(root, DOMAIN, LOCUS)

    def fake_git(*args: str, cwd=None) -> str:
        return LOCUS

    import mutation_gate.vocabulary_wordnet as vw
    original = vw.git
    vw.git = fake_git
    try:
        assert vw.diff_layer(repo, DOMAIN, True) is None
    finally:
        vw.git = original


def _concept(word: str, pos: tuple[str, ...]) -> vocabulary.Concept:
    return vocabulary.Concept(word=word, meaning="m", pos=pos, reject=(), forms=(),
                               irregular={}, head=False, returns="", source="x.toml")


def test_word_line_returns_zero_when_the_word_is_not_in_the_text():
    assert vocabulary_wordnet._word_line('word = "other"\n', "locus") == 0


def test_diff_layer_detects_a_pure_removal(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    repo = Repo(root=root, origin="", remotes=(), config=Config())
    _write(root, DOMAIN, "")
    monkeypatch.setattr(vocabulary_wordnet, "git", lambda *a, **k: GIZMO)
    diff = vocabulary_wordnet.diff_layer(repo, DOMAIN, True)
    assert diff.added == ()
    assert diff.changed == ()
    assert diff.removed == ("gizmo",)


def test_diffs_for_continues_past_a_layer_not_in_the_changed_set(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    repo = Repo(root=root, origin="", remotes=(), config=Config())
    _write(root, "a.toml", LOCUS)
    _write(root, "b.toml", GIZMO)
    monkeypatch.setattr(vocabulary_wordnet, "layers", lambda r: ["a.toml", "b.toml"])
    monkeypatch.setattr(vocabulary_wordnet, "git", lambda *a, **k: "")
    diffs = vocabulary_wordnet.diffs_for(repo, {"b.toml": {1}}, True)
    assert [d.source for d in diffs] == ["b.toml"]


def test_check_never_loads_the_dictionary_when_nothing_was_added(tmp_path, monkeypatch, capsys):
    repo = _repo(tmp_path, OPTED_IN, LOCUS)
    pre = LOCUS.replace("a site", "a different site")

    def boom(*a, **k):
        raise AssertionError("vocabulary.load must not run when nothing was added")

    monkeypatch.setattr(cli.vocabulary_check, "check", lambda *a, **k: [])
    monkeypatch.setattr(vocabulary_wordnet.vocabulary, "load", boom)
    code = _gate(monkeypatch, tmp_path, repo, {DOMAIN: {2}}, {DOMAIN: pre})
    err = capsys.readouterr().err
    assert code == 0
    assert err.splitlines()[:3] == ["Dictionary", f"  {DOMAIN}", "    changed: locus"]


def test_collisions_for_skips_a_word_missing_from_the_dictionary_without_stopping_the_rest(
    monkeypatch,
):
    real = _concept("real", ("noun",))
    bar = _concept("bar", ("noun",))
    dictionary = vocabulary.Dictionary(
        concepts={"bar": bar, "real": real}, matches={}, collections=frozenset(),
        distinct=frozenset(), conventions={},
    )
    diffs = [vocabulary_wordnet.DictionaryDiff(source="x.toml", added=("ghost", "real"),
                                                changed=(), removed=())]
    monkeypatch.setattr(vocabulary_wordnet, "synset_names",
                         _fake_synsets({("real", "noun"): frozenset({"s"}),
                                        ("bar", "noun"): frozenset({"s"})}))
    out = vocabulary_wordnet._collisions_for(dictionary, diffs, {"x.toml": 'word = "real"\n'})
    assert [c.other for c in out] == ["bar"]


def test_collisions_for_continues_past_a_distinct_pair_to_check_the_next_word(monkeypatch):
    buffer = _concept("buffer", ("noun",))
    cushion = _concept("cushion", ("noun",))
    cask = _concept("cask", ("noun",))
    dictionary = vocabulary.Dictionary(
        concepts={"cushion": cushion, "cask": cask, "buffer": buffer}, matches={},
        collections=frozenset(), distinct=frozenset({frozenset({"buffer", "cushion"})}),
        conventions={},
    )
    diffs = [vocabulary_wordnet.DictionaryDiff(source="x.toml", added=("buffer",),
                                                changed=(), removed=())]
    monkeypatch.setattr(vocabulary_wordnet, "synset_names",
                         _fake_synsets({("buffer", "noun"): frozenset({"s"}),
                                        ("cask", "noun"): frozenset({"s"}),
                                        ("cushion", "noun"): frozenset({"s"})}))
    out = vocabulary_wordnet._collisions_for(dictionary, diffs, {"x.toml": 'word = "buffer"\n'})
    assert [c.other for c in out] == ["cask"]


def test_collisions_for_records_one_collision_per_pair_across_two_shared_pos(monkeypatch):
    buffer = _concept("buffer", ("noun", "verb"))
    cushion = _concept("cushion", ("noun", "verb"))
    dictionary = vocabulary.Dictionary(
        concepts={"cushion": cushion, "buffer": buffer}, matches={}, collections=frozenset(),
        distinct=frozenset(), conventions={},
    )
    diffs = [vocabulary_wordnet.DictionaryDiff(source="x.toml", added=("buffer",),
                                                changed=(), removed=())]
    monkeypatch.setattr(vocabulary_wordnet, "synset_names",
                         _fake_synsets({("buffer", "noun"): frozenset({"s"}),
                                        ("cushion", "noun"): frozenset({"s"}),
                                        ("buffer", "verb"): frozenset({"t"}),
                                        ("cushion", "verb"): frozenset({"t"})}))
    out = vocabulary_wordnet._collisions_for(dictionary, diffs, {"x.toml": 'word = "buffer"\n'})
    assert len(out) == 1


class _FakeData:
    def __init__(self, ready_after: int):
        self.path: list[str] = []
        self._ready_after = ready_after
        self._calls = 0

    def find(self, resource: str) -> None:
        self._calls += 1
        if self._calls > self._ready_after:
            return
        raise LookupError("not found")


class _FakeNltk:
    def __init__(self, ready_after: int, download_ok: bool, write_zip: bool):
        self.data = _FakeData(ready_after)
        self._download_ok = download_ok
        self._write_zip = write_zip

    def download(self, name: str, download_dir: str, quiet: bool = True) -> bool:
        if self._write_zip:
            corpora = Path(download_dir) / "corpora"
            corpora.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(corpora / "wordnet.zip", "w") as archive:
                archive.writestr("wordnet/dummy.txt", "x")
        return self._download_ok


def test_ensure_data_extracts_the_fetched_zip_before_confirming(tmp_path, monkeypatch):
    monkeypatch.setattr(vocabulary_wordnet, "NLTK_DATA_DIR", tmp_path / "nltk_data")
    monkeypatch.setattr(vocabulary_wordnet, "nltk",
                         _FakeNltk(ready_after=1, download_ok=True, write_zip=True))
    vocabulary_wordnet._ensure_data()
    extracted = tmp_path / "nltk_data" / "corpora" / "wordnet" / "dummy.txt"
    assert extracted.read_text() == "x"


def test_ensure_data_refuses_cleanly_when_the_fetch_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(vocabulary_wordnet, "NLTK_DATA_DIR", tmp_path / "nltk_data")
    monkeypatch.setattr(vocabulary_wordnet, "nltk",
                         _FakeNltk(ready_after=99, download_ok=False, write_zip=False))
    with pytest.raises(GateError, match="could not be fetched"):
        vocabulary_wordnet._ensure_data()


def test_ensure_data_skips_the_download_when_already_found(tmp_path, monkeypatch):
    monkeypatch.setattr(vocabulary_wordnet, "NLTK_DATA_DIR", tmp_path / "nltk_data")
    fake = _FakeNltk(ready_after=0, download_ok=True, write_zip=False)

    def boom(*a, **k):
        raise AssertionError("download must not run when the data is already found")

    fake.download = boom
    monkeypatch.setattr(vocabulary_wordnet, "nltk", fake)
    vocabulary_wordnet._ensure_data()


def test_nltk_data_dir_lives_under_the_user_cache_root():
    from mutation_gate.repo import CACHE_ROOT
    assert vocabulary_wordnet.NLTK_DATA_DIR == CACHE_ROOT / "nltk_data"


def test_layers_includes_the_packaged_core_file_when_it_sits_under_the_repo_root(
    tmp_path, monkeypatch
):
    root = tmp_path / "repo"
    fake_core = root / "mutation_gate" / "vocabulary_core.toml"
    monkeypatch.setattr(vocabulary, "CORE_PATH", fake_core)
    repo = Repo(root=root, origin="", remotes=(), config=Config(vocabulary=DOMAIN))
    assert vocabulary_wordnet.layers(repo) == ["mutation_gate/vocabulary_core.toml", DOMAIN]


def test_layers_omits_the_core_file_when_it_sits_outside_the_repo_root(tmp_path, monkeypatch):
    repo = Repo(root=tmp_path / "repo", origin="", remotes=(), config=Config(vocabulary=DOMAIN))
    assert vocabulary_wordnet.layers(repo) == [DOMAIN]


def test_real_wordnet_finds_place_and_position_sharing_a_noun_sense():
    try:
        overlap = vocabulary_wordnet.synset_names("place", "noun") & \
            vocabulary_wordnet.synset_names("position", "noun")
    except GateError:
        pytest.skip("WordNet data not available offline in this environment")
    assert overlap
