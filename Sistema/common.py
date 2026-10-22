"""Shared paths and serialization; no network or background mutation on import."""
from __future__ import annotations
import hashlib
import json
import os
import re
import sys
import uuid
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

CODE_ROOT = Path(__file__).resolve().parent.parent
ROOT = Path(os.environ.get("DBRAIN_ROOT", CODE_ROOT)).expanduser().resolve()
SCHEMA = 1
PIPELINE = "dbrain-1"
NOTE_DIRS = {"concept": "20-Notas", "procedure": "30-Procedimentos", "checklist": "30-Procedimentos", "tool": "30-Procedimentos", "experiment": "40-Experimentos", "writeup": "40-Experimentos", "source": "10-Fontes", "case-study": "10-Fontes"}
AGENT_ENV = "DBRAIN_AGENT"  # codex, claude ou outro agente que execute comandos de escrita
EXCLUDED = {".git", ".ssh", ".venv", "node_modules", "__pycache__", "vpn-server", "90-Templates", "Sistema", ".obsidian", ".dbrain"}
NAMESPACE = uuid.UUID("6d376cde-bc51-4704-9f8e-dc147f68f91d")

def now():
    try:
        return datetime.now(ZoneInfo("America/Sao_Paulo")).isoformat(timespec="seconds")
    except Exception:
        from datetime import timezone, timedelta
        return datetime.now(timezone(timedelta(hours=-3))).isoformat(timespec="seconds")

def digest(data: str | bytes):
    return hashlib.sha256(data.encode("utf-8") if isinstance(data, str) else data).hexdigest()

def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def stable_id(value):
    return str(uuid.uuid5(NAMESPACE, value))

def load_json(path, default=None):
    path = Path(path)
    return json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else default

def save_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    with temp.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(obj, stream, ensure_ascii=False, indent=2, default=str)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)

def relative(root, path):
    resolved = Path(path).resolve()
    if not resolved.is_relative_to(Path(root).resolve()):
        raise ValueError("Caminho fora do vault")
    return resolved.relative_to(Path(root).resolve()).as_posix()

def safe_name(title):
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "-", title).strip(" .")[:150].rstrip(" .")
    if not name or name.upper().split(".")[0] in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(10)), *(f"LPT{i}" for i in range(10))}:
        raise ValueError("Título inválido para um arquivo Windows")
    return name

def config(root=ROOT):
    value = load_json(Path(root) / "Sistema/config.json")
    if not value:
        raise RuntimeError("Sistema/config.json ausente")
    return value

def schema(root=ROOT):
    """Controlled vocabulary shared by Obsidian notes, check and search filters."""
    value = load_json(library_path(root, config(root).get("schema_file", "Sistema/schema.json")))
    if not value:
        raise RuntimeError("Sistema/schema.json ausente")
    return value


def library_path(root, value):
    """Configuration paths stay inside their library; no external source traversal."""
    path = Path(root) / value
    relative(root, path)
    return path


def note_dirs(root=ROOT):
    configured = config(root).get("note_dirs", {})
    result = {**NOTE_DIRS, **configured}
    for value in result.values():
        library_path(root, value)
    return result


def python_executable(root=ROOT):
    """Use the library's environment when installed, otherwise the current Python."""
    root = Path(root).expanduser().resolve()
    for suffix in (".venv/Scripts/python.exe", ".venv/bin/python"):
        candidate = root / suffix
        if candidate.is_file():
            # On Unix the executable is a symlink; resolving it would bypass
            # pyvenv.cfg and start the base Python without this environment.
            return candidate
    return Path(sys.executable).absolute()

def actor(explicit=None):
    """Who performs a writer operation: explicit flag, agent environment or a human."""
    value = (explicit or os.environ.get(AGENT_ENV) or "human").strip().lower()
    if not re.fullmatch(r"[a-z][a-z0-9-]{1,31}", value):
        raise ValueError("Identificador de autor inválido")
    return value

def eligible(root, path, cfg):
    try:
        rel = Path(relative(root, path))
    except ValueError:
        return False
    if any(p in EXCLUDED or p.startswith(".") for p in rel.parts):
        return False
    if rel.name.upper() in {"AGENTS.MD", "CLAUDE.MD"}:
        return False
    if not any(rel == Path(x) or Path(x) in rel.parents for x in cfg["include"]):
        return False
    pdf_roots = [Path(x) for x in cfg.get("pdf_roots", ["Livros"])]
    is_pdf_area = any(rel == folder or folder in rel.parents for folder in pdf_roots)
    return (rel.suffix.lower() == ".md" and not is_pdf_area) or (rel.suffix.lower() == ".pdf" and is_pdf_area)
