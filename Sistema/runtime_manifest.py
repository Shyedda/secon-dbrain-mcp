"""Build and compare a content manifest for the shared SecOn Dbrain runtime."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


RUNTIME_FILES = [
    *(f"Sistema/{name}" for name in (
        "common.py",
        "dbrain.py",
        "embeddings.py",
        "extraction.py",
        "indexer.py",
        "library.py",
        "retrieval.py",
        "knowledge_pipeline.py",
        "mcp_server.py",
        "install_agents.py",
        "install_codex.py",
        "setup_environment.py",
        "requirements.txt",
        "requirements-lock.txt",
        "runtime_manifest.py",
    )),
    "dbrain.ps1",
    *(f"Sistema/tests/{name}" for name in (
        "test_incremental.py",
        "test_install_agents.py",
        "test_portability.py",
        "test_knowledge_pipeline.py",
        "test_distribution_defaults.py",
        "test_runtime_manifest.py",
    )),
    "Sistema/skills/dbrain-setup/SKILL.md",
    "Sistema/skills/dbrain-enrichment/SKILL.md",
    "docs/usage.md",
]


def _normalized_bytes(content: bytes) -> bytes:
    """Normalize UTF-8 BOM and CRLF only, matching Git text content on either OS."""
    if content.startswith(b"\xef\xbb\xbf"):
        content = content[3:]
    return content.replace(b"\r\n", b"\n")


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _file_hash(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise FileNotFoundError(f"Runtime file missing or invalid: {path}")
    return _sha256(_normalized_bytes(path.read_bytes()))


def _fingerprint(files: dict[str, str]) -> str:
    payload = json.dumps(files, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return _sha256(payload.encode("utf-8"))


def build_manifest(root: str | Path) -> dict[str, Any]:
    """Hash only the explicit runtime allowlist under *root*."""
    root = Path(root).resolve()
    files = {rel: _file_hash(root / rel) for rel in sorted(RUNTIME_FILES)}
    return {"version": 1, "files": files, "fingerprint": _fingerprint(files)}


def _differences(expected: dict[str, Any], actual: dict[str, Any]) -> dict[str, Any]:
    expected_files = expected.get("files", {})
    actual_files = actual.get("files", {})
    names = sorted(set(expected_files) | set(actual_files))
    changed = [
        {"path": name, "expected": expected_files.get(name), "actual": actual_files.get(name)}
        for name in names
        if expected_files.get(name) != actual_files.get(name)
    ]
    if expected.get("version") != actual.get("version"):
        changed.insert(0, {"path": "version", "expected": expected.get("version"), "actual": actual.get("version")})
    expected_fingerprint = _fingerprint(expected_files)
    if expected.get("fingerprint") != expected_fingerprint:
        changed.insert(0, {"path": "fingerprint", "expected": expected.get("fingerprint"),
                           "actual": expected_fingerprint, "reason": "saved fingerprint does not match saved files"})
    return {"expected_fingerprint": expected.get("fingerprint"),
            "actual_fingerprint": actual.get("fingerprint"), "differences": changed}


def _write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent,
                        help="collection root (default: parent of Sistema)")
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--write", action="store_true", help="write Sistema/runtime-manifest.json")
    actions.add_argument("--check", action="store_true", help="compare against the saved runtime manifest")
    actions.add_argument("--compare", type=Path, metavar="OTHER", help="compare this root with another collection root")
    args = parser.parse_args(argv)
    root = args.root.resolve()

    try:
        manifest = build_manifest(root)
        if args.write:
            target = root / "Sistema/runtime-manifest.json"
            _write_manifest(target, manifest)
            print(json.dumps({"written": str(target), "fingerprint": manifest["fingerprint"]}, ensure_ascii=False))
            return 0
        if args.check:
            target = root / "Sistema/runtime-manifest.json"
            if not target.is_file():
                print(json.dumps({"error": "saved manifest is missing", "path": str(target)}, ensure_ascii=False))
                return 1
            saved = json.loads(target.read_text(encoding="utf-8-sig"))
            report = _differences(saved, manifest)
            print(json.dumps(report, ensure_ascii=False))
            return int(bool(report["differences"]))
        if args.compare is not None:
            other_root = args.compare.resolve()
            other_manifest = build_manifest(other_root)
            report = _differences(manifest, other_manifest)
            report.update({"left_root": str(root), "right_root": str(other_root)})
            print(json.dumps(report, ensure_ascii=False))
            return int(bool(report["differences"]))

        print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except (OSError, json.JSONDecodeError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
