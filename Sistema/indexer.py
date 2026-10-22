"""Incremental writer and immutable generation publication."""
from __future__ import annotations
import json
import os
import shutil
import sqlite3
import sys
import time
import uuid
from collections import defaultdict
from contextlib import contextmanager
from pathlib import Path
import numpy as np
from filelock import FileLock, Timeout
from common import ROOT, PIPELINE, actor, config, digest, eligible, file_hash, load_json, now, relative, save_json, stable_id
from extraction import markdown, pdf, make_chunks
from embeddings import E5

DDL = """
CREATE TABLE documents(id TEXT PRIMARY KEY, metadata TEXT NOT NULL, paths TEXT NOT NULL, sha TEXT NOT NULL, cache TEXT NOT NULL, coverage TEXT NOT NULL);
CREATE TABLE chunks(rowid INTEGER PRIMARY KEY, id TEXT UNIQUE NOT NULL, source_id TEXT NOT NULL REFERENCES documents(id), title TEXT, section TEXT, text TEXT, passage TEXT, embedding_key TEXT, locator TEXT, vector_row INTEGER);
CREATE INDEX chunk_source ON chunks(source_id);
CREATE INDEX chunk_embedding ON chunks(embedding_key);
CREATE VIRTUAL TABLE search USING fts5(title, aliases, section, text, content='', tokenize='unicode61 remove_diacritics 2');
"""

def generation(root):
    root = Path(root)
    pointer = load_json(root / ".dbrain/index/CURRENT.json")
    if not pointer:
        return None
    name = pointer.get("generation", "")
    if not name or Path(name).name != name or name in {".", ".."}:
        raise RuntimeError("Ponteiro de geração inválido")
    path = root / ".dbrain/index/generations" / name
    if not path.is_dir():
        raise RuntimeError("Geração atual ausente")
    return path

def readonly_db(path):
    connection = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro&immutable=1", uri=True)
    connection.row_factory = sqlite3.Row
    return connection

def scan(root, cfg, scopes=None):
    """Only scopes are walked; directories/symlinks cannot escape the allowlist."""
    root = Path(root).resolve()
    selected = [(root / x).resolve() for x in (scopes or cfg["include"])]
    seen = set()
    for path in selected:
        rel = relative(root, path)
        if scopes and not any(rel == x or rel.startswith(x + "/") for x in cfg["include"]):
            raise ValueError(f"Caminho fora das pastas de conhecimento: {rel}")
        if path.is_file():
            candidates = [path]
        elif path.is_dir():
            candidates = []
            for directory, dirs, files in os.walk(path, followlinks=False):
                dirs[:] = [d for d in dirs if not d.startswith(".") and d not in {"node_modules", "__pycache__", "vpn-server"} and not (Path(directory)/d).is_symlink()]
                candidates.extend(Path(directory) / f for f in files)
        else:
            continue  # Deleted explicit path is still processed via prior manifest.
        for item in candidates:
            if item.is_symlink() or not eligible(root, item, cfg):
                continue
            rp = relative(root, item)
            if rp not in seen:
                seen.add(rp)
                yield item

def in_scope(path, scopes):
    return not scopes or any(path == s or path.startswith(s.rstrip("/") + "/") for s in scopes)

@contextmanager
def writer(root, operation, wait=0, by=None):
    """Single writer for index and catalog. Waiting is explicit; the lock is never broken."""
    state = Path(root) / ".dbrain"
    state.mkdir(parents=True, exist_ok=True)
    owner_path = state / "writer-owner.json"
    try:
        lock = FileLock(str(state / "writer.lock"), timeout=wait)
        lock.acquire()
    except Timeout:
        owner = load_json(owner_path) or {}
        detail = f" por {owner.get('by')} desde {owner.get('since')} ({owner.get('operation')}, pid {owner.get('pid')})" if owner else ""
        raise RuntimeError(f"Outro processo está escrevendo no índice{detail}. Repita com --wait 900 ou aguarde; não apague writer.lock.") from None
    try:
        save_json(owner_path, {"pid": os.getpid(), "by": actor(by), "operation": operation, "since": now()})
        yield
    finally:
        save_json(owner_path, None)
        lock.release()

def update(root=ROOT, scopes=None, lexical=False, rebuild=False, progress=None, fail_before_publish=False, reextract=False, wait=0, by=None):
    root = Path(root).resolve()
    cfg = config(root)
    state = root / ".dbrain"
    state.mkdir(parents=True, exist_ok=True)
    normalized = [relative(root, root / p) for p in scopes] if scopes else None
    if rebuild and scopes:
        raise ValueError("Reconstrução exige escopo completo")
    if reextract and not scopes:
        raise ValueError('Reextração seletiva exige --path')
    with writer(root, "rebuild" if rebuild else f"update {normalized or 'all'}", wait, by):
        try:
            result = _update(root, cfg, normalized, lexical, rebuild, progress or (lambda _: None), fail_before_publish, reextract)
        except Exception as exc:
            save_json(state / 'last-error.json', {'time': now(), 'scope': normalized or 'all', 'error': str(exc), 'type': type(exc).__name__})
            raise
        save_json(state / 'last-error.json', None)
        return result

def prune(root=ROOT, keep=3, apply=False, by=None):
    """Remove old or unpublished generations. CURRENT and the newest published ones stay."""
    root = Path(root).resolve()
    base = root / ".dbrain/index/generations"
    current = generation(root)
    with writer(root, "prune", 0, by):
        names = sorted(p.name for p in base.iterdir() if p.is_dir()) if base.exists() else []
        # Names only have one-second resolution; the manifest is written once, at publication.
        published = sorted((n for n in names if (base / n / "manifest.json").exists()), key=lambda n: (base / n / "manifest.json").stat().st_mtime_ns)
        kept = set(published[-max(0, keep):]) | ({current.name} if current else set())
        removed, freed = [], 0
        for name in names:
            if name in kept:
                continue
            size = sum(f.stat().st_size for f in (base / name).rglob("*") if f.is_file())
            entry = {"generation": name, "published": name in published, "bytes": size}
            if apply:
                try:
                    shutil.rmtree(base / name)
                except OSError as exc:  # A reader on Windows may still hold a file open.
                    entry["error"] = str(exc)
            removed.append(entry)
            freed += size if "error" not in entry else 0
        return {"apply": apply, "current": current.name if current else None, "kept": sorted(kept), "removed": removed, "freed_mb": round(freed / 2**20, 1), "note": "Citações que fixam gerações removidas passam a ser lidas pela geração atual quando o trecho continua idêntico." if removed else None, "next": None if apply or not removed else r".\dbrain.ps1 prune --apply"}

def _update(root, cfg, scopes, lexical, rebuild, progress, fail_before_publish, reextract=False):
    started = time.monotonic()
    state = root / ".dbrain"
    old_dir = generation(root)
    old_manifest = load_json(old_dir / "manifest.json", {}) if old_dir else {}
    old_files = old_manifest.get("files", {})
    files = {k: dict(v) for k, v in old_files.items()}
    model = None if lexical else E5(root, cfg.get("onnx_threads", 4))
    model_id = model.identity if model else "lexical"
    pipeline = digest(json.dumps({"version": PIPELINE, "model": model_id, "tokens": cfg["chunk_tokens"], "overlap": cfg["overlap_tokens"], "ocr": cfg.get("ocr", {})}, sort_keys=True))
    if old_manifest and old_manifest.get("pipeline") != pipeline and not rebuild:
        raise RuntimeError("Modelo/configuração mudou: use rebuild explicitamente; update não reprocessa toda a biblioteca silenciosamente")
    stats = {"started": now(), "scope": scopes or "all", "scanned": 0, "content_reads": 0, "pdf_extractions": 0, "markdown_extractions": 0, "new_embeddings": 0, "reused_embeddings": 0, "removed": 0, "unchanged": 0, "errors": []}
    actual = set()
    changed = set()
    loaded = {}
    catalog = load_json(state / "catalog.json", {})
    catalog_dirty = load_json(state / "catalog-dirty.json", [])
    # Reuse exact source hashes after renames without reading every other file.
    prior_by_sha = {v.get("sha"): v for v in old_files.values()}
    semantic_ids = {v.get("semantic_hash"): v.get("source_id") for v in old_files.values() if v.get("kind") == "pdf" and not v.get("excluded")}
    for path in scan(root, cfg, scopes):
        rp = relative(root, path)
        actual.add(rp)
        stats["scanned"] += 1
        stat = path.stat()
        prev = old_files.get(rp)
        if prev and prev["size"] == stat.st_size and prev["mtime_ns"] == stat.st_mtime_ns and not rebuild and not reextract and rp not in catalog_dirty:
            stats["unchanged"] += 1
            continue
        try:
            sha = file_hash(path)
            stats["content_reads"] += 1
            if prev and sha == prev["sha"] and not rebuild and not reextract and rp not in catalog_dirty:
                files[rp] = {**prev, "size": stat.st_size, "mtime_ns": stat.st_mtime_ns}
                continue
            kind = "pdf" if path.suffix.lower() == ".pdf" else "markdown"
            cache_rel = f".dbrain/extractions/{sha}-{PIPELINE}.json"
            previous_cache = prev if prev and prev.get("sha") == sha else prior_by_sha.get(sha, {})
            cache_rel = previous_cache.get("cache", cache_rel)
            cache_path = root / cache_rel
            cached = load_json(cache_path)
            if cached and not reextract and not (rebuild and kind == "pdf" and cfg.get("ocr", {}).get("pages", {}).get(path.name)):
                extracted = cached
            else:
                progress(f"Extraindo {rp}")
                extracted = pdf(path, root, sha, cfg) if kind == "pdf" else markdown(path, rp)
                stats["pdf_extractions" if kind == "pdf" else "markdown_extractions"] += 1
                # Never replace a cache used by an earlier published generation.
                if cache_path.exists():
                    content_id = digest(json.dumps(extracted, sort_keys=True, ensure_ascii=False, default=str))[:16]
                    cache_rel = f".dbrain/extractions/{sha}-{PIPELINE}-{content_id}.json"
                    cache_path = root / cache_rel
                if not cache_path.exists():
                    save_json(cache_path, extracted)
            # Discard a racing read rather than publishing mixed metadata/content.
            after = path.stat()
            if (after.st_size, after.st_mtime_ns) != (stat.st_size, stat.st_mtime_ns):
                raise RuntimeError("Fonte mudou durante a extração; execute update novamente")
            record = {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns, "sha": sha, "kind": kind, "cache": cache_rel}
            if prev and prev.get("source_id"):
                changed.add(prev["source_id"])
            if extracted.get("excluded"):
                record["excluded"] = True
                files[rp] = record
                continue
            extracted = dict(extracted)
            extracted["metadata"] = {**extracted["metadata"], **catalog.get(rp, {}).get("metadata", {})}
            previous_identity = prev or prior_by_sha.get(sha, {})
            if kind == "pdf":
                sid = semantic_ids.get(extracted["semantic_hash"])
                if not sid:
                    # A changed occurrence of a duplicate becomes its own work.
                    shared = sum(v.get("source_id") == previous_identity.get("source_id") for v in old_files.values()) > 1
                    sid = previous_identity.get("source_id") if not shared else None
                    sid = sid or (catalog.get(rp, {}).get("source_id") if not shared else None) or stable_id("pdf:" + sha)
                semantic_ids[extracted["semantic_hash"]] = sid
            else:
                sid = extracted.get("source_id") or previous_identity.get("source_id") or stable_id("note:" + sha)
            record.update({"source_id": sid, "semantic_hash": extracted["semantic_hash"]})
            files[rp] = record
            loaded[rp] = extracted
            changed.add(sid)
        except Exception as exc:
            stats["errors"].append({"path": rp, "error": str(exc)})
    # Never infer removal outside the requested subtree.
    for rp in list(files):
        if in_scope(rp, scopes) and rp not in actual:
            record = files.pop(rp)
            if record.get("source_id"):
                changed.add(record["source_id"])
            stats["removed"] += 1
    # Failed input must not publish partial or stale updates under a fresh label.
    if stats["errors"]:
        save_json(state / "last-update.json", stats)
        raise RuntimeError("Atualização não publicada: " + json.dumps(stats["errors"], ensure_ascii=False))
    grouped = defaultdict(list)
    for path, record in files.items():
        if not record.get("excluded"):
            grouped[record["source_id"]].append(path)
    for sid, paths in grouped.items():
        if len(paths) > 1 and any(files[p]["kind"] == "markdown" for p in paths):
            raise ValueError(f"ID duplicado em notas: {paths}; gere um ID diferente para a cópia")
    if rebuild:
        changed.update(grouped)
    if old_manifest and files == old_files and not rebuild and not changed:
        stats.update({"generation": old_dir.name, "published": False, "elapsed_seconds": round(time.monotonic()-started, 3)})
        save_json(state / "last-update.json", stats)
        return stats
    name = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
    stage = state / "index/generations" / name
    stage.mkdir(parents=True)
    db_path = stage / "knowledge.sqlite"
    if old_dir:
        shutil.copy2(old_dir / "knowledge.sqlite", db_path)
        db = sqlite3.connect(db_path)
    else:
        db = sqlite3.connect(db_path)
        db.executescript(DDL)
    db.row_factory = sqlite3.Row
    try:
        for sid in changed:
            db.execute("DELETE FROM chunks WHERE source_id=?", (sid,))
            db.execute("DELETE FROM documents WHERE id=?", (sid,))
            paths = sorted(grouped.get(sid, []))
            if not paths:
                continue
            canonical = paths[0]
            record = files[canonical]
            ext = loaded.get(canonical) or load_json(root / record["cache"])
            ext = dict(ext)
            ext["metadata"] = {**ext["metadata"], **catalog.get(canonical, {}).get("metadata", {})}
            chunks = make_chunks(ext, sid, model, cfg["chunk_tokens"], cfg["overlap_tokens"])
            db.execute("INSERT INTO documents VALUES(?,?,?,?,?,?)", (sid, json.dumps(ext["metadata"], ensure_ascii=False, default=str), json.dumps(paths, ensure_ascii=False), record["sha"], record["cache"], json.dumps(ext["coverage"], ensure_ascii=False)))
            db.executemany("INSERT INTO chunks(id,source_id,title,section,text,passage,embedding_key,locator) VALUES(?,?,?,?,?,?,?,?)", [(c["id"], sid, ext["metadata"]["title"], c["section"], c["text"], c["passage"], c["embedding_key"], json.dumps(c["locator"], ensure_ascii=False)) for c in chunks])
        # Metadata-only updates/renames of duplicate occurrences retain all paths.
        for sid, paths in grouped.items():
            db.execute("UPDATE documents SET paths=? WHERE id=?", (json.dumps(sorted(paths), ensure_ascii=False), sid))
        rows = db.execute("SELECT rowid,embedding_key,passage FROM chunks ORDER BY rowid").fetchall()
        vector_path = stage / "vectors.npy"
        matrix = np.lib.format.open_memmap(vector_path, mode="w+", dtype=np.float32, shape=(len(rows), 384)) if rows else None
        cache = sqlite3.connect(state / "embeddings.sqlite")
        cache.execute("CREATE TABLE IF NOT EXISTS embeddings(model TEXT,key TEXT,vector BLOB,PRIMARY KEY(model,key))")
        pending = []
        batch = cfg.get("embedding_batch", 4)
        def flush():
            if not pending:
                return
            vectors = model.encode([entry[2] for entry in pending])
            if vectors.shape != (len(pending),384) or not np.isfinite(vectors).all() or not np.allclose(np.linalg.norm(vectors,axis=1),1,atol=.002):
                raise RuntimeError('Modelo retornou vetores inválidos; geração anterior preservada')
            for entry, vector in zip(pending, vectors):
                index, key, _ = entry
                matrix[index] = vector
                cache.execute("INSERT OR REPLACE INTO embeddings VALUES(?,?,?)", (model_id, key, vector.tobytes()))
                stats["new_embeddings"] += 1
            cache.commit()  # Interrupted runs can reuse completed batches.
            pending.clear()
            if stats["new_embeddings"] % 200 == 0:
                progress(f"Embeddings novos: {stats['new_embeddings']} / segmentos {len(rows)}")
        for i, row in enumerate(rows):
            if model:
                cached = cache.execute("SELECT vector FROM embeddings WHERE model=? AND key=?", (model_id, row["embedding_key"])).fetchone()
                if cached:
                    matrix[i] = np.frombuffer(cached[0], dtype=np.float32)
                    stats["reused_embeddings"] += 1
                else:
                    pending.append((i, row["embedding_key"], row["passage"]))
                    if len(pending) >= batch:
                        flush()
            else:
                matrix[i] = 0
            db.execute("UPDATE chunks SET vector_row=? WHERE rowid=?", (i, row["rowid"]))
        flush()
        cache.close()
        if matrix is not None:
            matrix.flush()
            del matrix
        else:
            np.save(vector_path, np.empty((0, 384), dtype=np.float32))
        # FTS is a small derived structure; sources and embeddings are not rebuilt.
        db.execute("INSERT INTO search(search) VALUES('delete-all')")
        for row in db.execute("SELECT c.rowid,c.title,c.section,c.text,d.metadata FROM chunks c JOIN documents d ON c.source_id=d.id").fetchall():
            meta = json.loads(row["metadata"])
            db.execute("INSERT INTO search(rowid,title,aliases,section,text) VALUES(?,?,?,?,?)", (row["rowid"], row["title"], " ".join(str(x) for x in meta.get("aliases", [])), row["section"], row["text"]))
        db.commit()
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("SQLite integrity check falhou")
        if db.execute("SELECT count(*) FROM chunks").fetchone()[0] != len(rows):
            raise RuntimeError("Contagem de chunks inconsistente")
        db.close()
        stats.update({"generation": name, "published": True, "documents": len(grouped), "files": len(files), "chunks": len(rows), "elapsed_seconds": round(time.monotonic()-started, 3)})
        manifest = {"schema": 1, "pipeline": pipeline, "model": model_id, "created": now(), "files": files, "stats": stats}
        save_json(stage / "manifest.json", manifest)
        if fail_before_publish:
            raise RuntimeError("Falha de teste antes de publicar")
        save_json(state / "index/CURRENT.json", {"generation": name})
        save_json(state / "last-update.json", stats)
        # Queue is advisory: targeted updates retain entries outside the subtree.
        with FileLock(str(state / "queue.lock"), timeout=10):
            queue = load_json(state / "queue.json", [])
            save_json(state / "queue.json", [p for p in queue if not in_scope(p, scopes) or (p not in actual and (root / p).exists())])
        save_json(state / "catalog-dirty.json", [p for p in catalog_dirty if not in_scope(p, scopes)])
        return stats
    except Exception:
        db.close()
        # Incomplete generation remains unreferenced for diagnosis; CURRENT intact.
        raise
