"""Tests for the explicit runtime manifest allowlist and CLI."""
from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import runtime_manifest


def _make_root(root: Path, files: dict[str, bytes] | None = None) -> Path:
    for rel in runtime_manifest.RUNTIME_FILES:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((files or {}).get(rel, b"runtime\n"))
    return root


def test_non_runtime_configuration_and_corpus_do_not_change_fingerprint(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_manifest, "RUNTIME_FILES", ["Sistema/core.py"])
    first = _make_root(tmp_path / "first", {"Sistema/core.py": b"same\n"})
    second = _make_root(tmp_path / "second", {"Sistema/core.py": b"same\n"})
    (first / "Sistema/config.json").write_text('{"private": true}', encoding="utf-8")
    (second / "Sistema/config.json").write_text('{"private": false}', encoding="utf-8")
    (first / "PDFs").mkdir()
    (first / "PDFs/book.pdf").write_bytes(b"private corpus")
    (second / "Markdown").mkdir()
    (second / "Markdown/note.md").write_text("different corpus", encoding="utf-8")

    assert runtime_manifest.build_manifest(first) == runtime_manifest.build_manifest(second)


def test_runtime_modification_and_missing_file_are_detected(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_manifest, "RUNTIME_FILES", ["Sistema/a.py", "Sistema/b.py"])
    first = _make_root(tmp_path / "first")
    second = _make_root(tmp_path / "second")
    (second / "Sistema/a.py").write_bytes(b"changed\n")
    left = runtime_manifest.build_manifest(first)
    modified = runtime_manifest.build_manifest(second)
    assert runtime_manifest._differences(left, modified)["differences"]
    (second / "Sistema/b.py").unlink()
    try:
        runtime_manifest.build_manifest(second)
    except FileNotFoundError as error:
        assert Path(str(error).split(": ", 1)[-1]).name == "b.py"
    else:
        raise AssertionError("missing runtime file must fail manifest construction")


def test_lf_crlf_and_utf8_bom_are_equivalent(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_manifest, "RUNTIME_FILES", ["Sistema/text.md"])
    lf = _make_root(tmp_path / "lf", {"Sistema/text.md": "ação\nlinha\n".encode("utf-8")})
    crlf_bom = _make_root(tmp_path / "crlf", {"Sistema/text.md": b"\xef\xbb\xbf" + "ação\r\nlinha\r\n".encode("utf-8")})

    assert runtime_manifest.build_manifest(lf) == runtime_manifest.build_manifest(crlf_bom)


def test_cli_write_check_and_detect_changes(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(runtime_manifest, "RUNTIME_FILES", ["Sistema/a.py", "Sistema/b.py"])
    root = _make_root(tmp_path / "collection")
    assert runtime_manifest.main(["--root", str(root), "--write"]) == 0
    saved_path = root / "Sistema/runtime-manifest.json"
    assert b"\r\n" not in saved_path.read_bytes()
    assert json.loads(saved_path.read_text(encoding="utf-8"))["version"] == 1
    assert runtime_manifest.main(["--root", str(root), "--check"]) == 0
    saved = json.loads(saved_path.read_text(encoding="utf-8"))
    saved["fingerprint"] = "0" * 64
    saved_path.write_text(json.dumps(saved), encoding="utf-8")
    assert runtime_manifest.main(["--root", str(root), "--check"]) == 1
    assert '"path": "fingerprint"' in capsys.readouterr().out
    assert runtime_manifest.main(["--root", str(root), "--write"]) == 0
    (root / "Sistema/a.py").write_bytes(b"changed\n")
    assert runtime_manifest.main(["--root", str(root), "--check"]) == 1
    assert '"differences"' in capsys.readouterr().out


def test_cli_compare_uses_allowlist_and_returns_difference_status(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(runtime_manifest, "RUNTIME_FILES", ["Sistema/a.py"])
    first = _make_root(tmp_path / "first", {"Sistema/a.py": b"same\n"})
    second = _make_root(tmp_path / "second", {"Sistema/a.py": b"same\n"})
    (first / "Sistema/config.json").write_text("private one", encoding="utf-8")
    (second / "Sistema/config.json").write_text("private two", encoding="utf-8")
    assert runtime_manifest.main(["--root", str(first), "--compare", str(second)]) == 0
    (second / "Sistema/a.py").write_bytes(b"different\n")
    assert runtime_manifest.main(["--root", str(first), "--compare", str(second)]) == 1
    assert '"Sistema/a.py"' in capsys.readouterr().out
