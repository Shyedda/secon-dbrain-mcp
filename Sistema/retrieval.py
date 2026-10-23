"""Read-only hybrid retrieval over one pinned generation per request."""
from __future__ import annotations
import json
import re
import time
from collections import Counter
from pathlib import Path
import numpy as np
from filelock import FileLock, Timeout
from common import ROOT, config, load_json, schema
from indexer import generation, readonly_db
from embeddings import E5

STOP = set("a o as os de da do das dos em na no nas nos um uma e ou para por com que como qual quais what how the a an and or to of in is are does do for on my meu minha seus suas this that".split())
EXPANSIONS = {"autorização": "authorization", "autenticação": "authentication", "acesso": "access", "segurança": "security", "ameaças": "threat", "ameaça": "threat", "injeção": "injection", "dependências": "dependencies", "segredos": "secrets", "vulnerabilidades": "vulnerabilities", "vulnerabilidade": "vulnerability", "contêineres": "containers", "privilégios": "privileges", "sessão": "session", "sessões": "sessions", "cadeia": "supply", "assinatura": "signature", "assinaturas": "signatures", "logs": "logging", "incidentes": "incident", "criptografia": "encryption", "validação": "validation", "redes": "networks", "ameaçamento": "threat"}
EXPANSIONS.update({'análise':'analysis', 'estática':'static', 'revisão':'review', 'humana':'human', 'rastreabilidade':'traceability', 'configuração':'configuration', 'configurações':'configuration', 'versionar':'versioning', 'entrega':'deployment', 'consultas':'queries', 'parametrizadas':'prepared statements', 'privilégio':'privilege', 'mínimo':'least', 'dados':'data', 'camadas':'layers', 'profundidade':'depth', 'autenticidade':'authenticity', 'identidades':'identities', 'orçamento':'budget', 'privacidade':'privacy'})


def navigation(section, lead):
    tail = section.rsplit('>', 1)[-1].strip().casefold()
    return tail in {'cover', 'title page', 'copyright', 'index', 'contributors', 'contents', 'table of contents'} or bool(re.match(r'^\s*(table of contents|copyright\s+[©(])', lead, re.I))

class Knowledge:
    def __init__(self, root=ROOT, lexical=False):
        self.root = Path(root).resolve()
        self.lexical = lexical
        self.model = None
        self.query_cache = {}
        self.vocabulary = schema(self.root)
        self.expansions = config(self.root).get("lexical_expansions", EXPANSIONS)

    def _weight(self, meta):
        """Own synthesized notes outrank raw book pages at similar relevance; deprecated ones sink."""
        weight = 1.0
        if meta.get("generated_by_pipeline"):
            return 1.0 if meta.get("status") == "reviewed" else 0.8
        if meta.get("type") in self.vocabulary["personal_types"]:
            weight *= 1.3
            if meta.get("status") == "reviewed":
                weight *= 1.1
        if meta.get("status") == "deprecated":
            weight *= 0.5
        return weight

    def _pin(self, requested=None):
        if requested:
            if not re.fullmatch(r"[A-Za-z0-9_-]+", requested):
                raise ValueError("Geração inválida")
            selected = self.root / ".dbrain/index/generations" / requested
            if not (selected / "manifest.json").exists():
                raise ValueError("Geração indisponível")
        else:
            selected = generation(self.root)
        if not selected:
            raise RuntimeError("Base ainda não indexada; execute update")
        return selected, load_json(selected / "manifest.json")

    def _matches(self, meta, source_id, filters):
        if not filters:
            return True
        for key, value in filters.items():
            if key not in self.vocabulary["filters"]:
                raise ValueError(f"Filtro desconhecido: {key}; aceitos: {self.vocabulary['filters']}")
            expected = value if isinstance(value, list) else [value]
            actual = [source_id] if key == "source_id" else meta.get(key, [])
            actual = actual if isinstance(actual, list) else [actual]
            if not any(x in actual for x in expected):
                return False
        return True

    def search(self, query, filters=None, limit=8):
        query = str(query).strip()
        if not query or len(query) > 2000:
            raise ValueError("Consulta deve ter entre 1 e 2000 caracteres")
        limit = max(1, min(int(limit), 20))
        start = time.monotonic()
        directory, manifest = self._pin()
        db = readonly_db(directory / "knowledge.sqlite")
        try:
            docs = {r["id"]: {"metadata": json.loads(r["metadata"]), "paths": json.loads(r["paths"]), "sha": r["sha"]} for r in db.execute("SELECT * FROM documents")}
            from knowledge_pipeline import derivative_state
            derived_states = {sid: derivative_state(self.root, d["metadata"], manifest) for sid, d in docs.items()}
            allowed = {sid for sid, d in docs.items() if self._matches(d["metadata"], sid, filters) and not derived_states[sid]["stale"]}
            if not allowed:
                return {"generation": directory.name, "mode": "lexical", "results": [], "notice": "Nenhuma fonte corresponde aos filtros."}
            tokens = [t for t in re.findall(r"[\w]+(?:[-_.][\w]+)*", query.lower()) if t not in STOP]
            wants_navigation = bool(re.search(r'\b(sumário|índice|contents|index|bibliografia|autoria|authors?|capa|copyright)\b',query,re.I))
            def is_navigation(sid, section, lead):
                return not wants_navigation and docs[sid]['metadata'].get('type')=='book' and navigation(section or '',lead or '')
            db.create_function('is_navigation',3,is_navigation,deterministic=True)
            terms = list(dict.fromkeys(tokens + [self.expansions[t] for t in tokens if t in self.expansions]))[:40]
            lexical = []
            if terms:
                match = " OR ".join('"' + term.replace('"', '""') + '"' for term in terms)
                # Filter before limiting to avoid cross-domain starvation.
                placeholders = ','.join('?' for _ in allowed)
                lexical = [r[0] for r in db.execute(f"SELECT search.rowid FROM search JOIN chunks c ON search.rowid=c.rowid WHERE search MATCH ? AND c.source_id IN ({placeholders}) AND NOT is_navigation(c.source_id,c.section,substr(c.text,1,100)) ORDER BY bm25(search,3.0,4.0,2.0,1.0) LIMIT 60", (match, *sorted(allowed)))]
            semantic, similarities = [], {}
            warning = None
            mode = "lexical"
            if not self.lexical and manifest["model"] != "lexical":
                try:
                    if self.model is None:
                        self.model = E5(self.root, config(self.root).get("onnx_threads", 4))
                    if self.model.identity != manifest["model"]:
                        raise RuntimeError("Modelo difere da geração indexada")
                    if query not in self.query_cache:
                        self.query_cache[query] = self.model.encode([query], query=True)[0]
                        if len(self.query_cache) > 128:
                            self.query_cache.pop(next(iter(self.query_cache)))
                    vectors = np.load(directory / "vectors.npy", mmap_mode="r")
                    candidates = db.execute("SELECT rowid,source_id,vector_row FROM chunks WHERE NOT is_navigation(source_id,section,substr(text,1,100)) ORDER BY vector_row").fetchall()
                    if len(vectors):
                        scores = vectors @ self.query_cache[query]
                        candidate_ids = np.array([r["vector_row"] for r in candidates if r["source_id"] in allowed], dtype=np.int64)
                        count = min(60, len(candidate_ids))
                        if count:
                            selected = candidate_ids[np.argpartition(scores[candidate_ids], -count)[-count:]]
                            selected = selected[np.argsort(scores[selected])[::-1]]
                            by_vector = {r["vector_row"]: r["rowid"] for r in candidates}
                            semantic = [by_vector[int(i)] for i in selected]
                            similarities = {by_vector[int(i)]: float(scores[int(i)]) for i in selected}
                    del vectors
                    mode = "hybrid"
                except Exception as exc:
                    warning = "Busca semântica indisponível; usando lexical: " + str(exc)
            fused = Counter()
            for ranking in (lexical, semantic):
                for rank, rowid in enumerate(ranking, 1):
                    fused[rowid] += 1.0 / (60 + rank)
            for rowid in list(fused):
                source = db.execute("SELECT source_id FROM chunks WHERE rowid=?", (rowid,)).fetchone()[0]
                fused[rowid] *= self._weight(docs[source]["metadata"])
            results, seen, per_source = [], set(), Counter()
            for rowid, score in fused.most_common():
                row = db.execute("SELECT * FROM chunks WHERE rowid=?", (rowid,)).fetchone()
                sid, key = row["source_id"], row["embedding_key"]
                if key in seen or per_source[sid] >= max(2, limit // 2):
                    continue
                seen.add(key)
                per_source[sid] += 1
                document = docs[sid]
                locator = json.loads(row["locator"])
                path = document["paths"][0]
                record = manifest["files"][path]
                stale = self._changed(path, record)
                results.append({"source_id": sid, "chunk_id": row["id"], "title": document["metadata"]["title"], "type": document["metadata"].get("type"), "status": document["metadata"].get("status"), "created_by": document["metadata"].get("created_by"), "path": str(self.root / path), "all_paths": document["paths"], "section": row["section"], "locator": {**locator, "chunk_id": row["id"], "generation": directory.name}, "source_sha256": document["sha"], "excerpt": row["text"][:2200], "excerpt_truncated": len(row["text"]) > 2200, "score_rrf": round(score, 6), "semantic_similarity": similarities.get(rowid), "source_changed_since_index": stale})
                results[-1]["derivation"] = derived_states[sid]
                if len(results) >= limit:
                    break
            return {"generation": directory.name, "mode": mode, "warning": warning, "elapsed_ms": round(1000*(time.monotonic()-start), 1), "notice": "Resultados são candidatos a evidência, não uma resposta validada. Confirme o trecho com read_knowledge e declare ausência de cobertura quando não sustentar a pergunta.", "results": results}
        finally:
            db.close()

    def _writer(self):
        """Owner of writer.lock, if it is really held; a killed writer leaves only a stale record."""
        lock = FileLock(str(self.root / ".dbrain/writer.lock"), timeout=0)
        try:
            lock.acquire()
        except Timeout:
            return load_json(self.root / ".dbrain/writer-owner.json") or {"by": "desconhecido"}
        except OSError:
            return None
        lock.release()
        return None

    def _changed(self, path, record):
        try:
            stat = (self.root / path).stat()
            return stat.st_size != record["size"] or stat.st_mtime_ns != record["mtime_ns"]
        except OSError:
            return True

    def read(self, source_id, locator=None):
        locator = locator or {}
        if isinstance(locator, str):
            locator = {"chunk_id": locator}
        fallback = None
        try:
            directory, manifest = self._pin(locator.get("generation"))
        except ValueError:
            # Generation removed by prune: stable chunk IDs still resolve if the text is unchanged.
            if not locator.get("chunk_id"):
                raise
            fallback = locator.get("generation")
            directory, manifest = self._pin()
        db = readonly_db(directory / "knowledge.sqlite")
        try:
            document = db.execute("SELECT * FROM documents WHERE id=?", (source_id,)).fetchone()
            if not document:
                raise ValueError("Fonte não cadastrada nesta geração")
            metadata = json.loads(document["metadata"])
            from knowledge_pipeline import derivative_state
            derived = derivative_state(self.root, metadata, manifest, verify=metadata.get("layer") == "gold")
            if derived["stale"]:
                raise ValueError("Derivado desatualizado: consulte a fonte original e execute prepare/enriquecimento novamente")
            paths = json.loads(document["paths"])
            cache_path = (self.root / document["cache"]).resolve()
            if not cache_path.is_relative_to(self.root / ".dbrain/extractions"):
                raise ValueError("Cache fora do diretório permitido")
            extracted = load_json(cache_path)
            units = extracted["units"]
            chunk = None
            if locator.get("chunk_id"):
                chunk = db.execute("SELECT * FROM chunks WHERE source_id=? AND id=?", (source_id, locator["chunk_id"])).fetchone()
                if not chunk:
                    raise ValueError("Trecho não pertence à fonte/geração" + (f"; a geração {fallback} foi removida e o texto mudou desde então" if fallback else ""))
                exact = json.loads(chunk["locator"])
                index = exact["unit"]
            elif locator.get("pdf_page"):
                index = int(locator["pdf_page"]) - 1
            else:
                index = int(locator.get("unit", 0))
            if not 0 <= index < len(units):
                raise ValueError("Página/seção fora do documento")
            unit = units[index]
            # Search offsets identify the excerpt. Reading that hit returns its full
            # page/section, including context preceding a later chunk.
            offset = 0 if chunk is not None else max(0, int(locator.get("char_start", 0)))
            body = unit["text"][offset:offset + 14000]
            return {"source_id": source_id, "generation": directory.name, "title": metadata["title"], "metadata": metadata, "path": str(self.root / paths[0]), "all_paths": paths, "source_sha256": document["sha"], "source_changed_since_index": self._changed(paths[0], manifest["files"][paths[0]]), "locator": {k: v for k, v in unit.items() if k not in {"text", "raw_text"}}, "unit": index, "text": body, "has_more": offset + len(body) < len(unit["text"]), "next_char_start": offset + len(body), "next_locator": {"generation": directory.name, "unit": index, "char_start": offset + len(body)} if offset + len(body) < len(unit["text"]) else None, "total_units": len(units), "content_is_untrusted_reference": True, "requested_generation_removed": fallback}
        finally:
            db.close()

    def status(self):
        directory = generation(self.root)
        if not directory:
            return {"indexed": False, "instruction": "Execute .\\dbrain.ps1 update"}
        manifest = load_json(directory / "manifest.json")
        db = readonly_db(directory / "knowledge.sqlite")
        try:
            coverage = []
            summary = {"pages_in_unique_books": 0, "ocr_pages": 0, "low_text_pages": 0, "blank_pages": 0}
            for row in db.execute("SELECT id,metadata,coverage FROM documents"):
                meta, cov = json.loads(row["metadata"]), json.loads(row["coverage"])
                if meta.get('type') == 'book':
                    summary['pages_in_unique_books'] += cov.get('pages', 0)
                    for field in ('ocr_pages', 'low_text_pages', 'blank_pages'):
                        summary[field] += len(cov.get(field, []))
                if cov.get("warnings"):
                    coverage.append({"source_id": row["id"], "title": meta["title"], "warnings": cov["warnings"]})
            stale = [p for p, r in manifest["files"].items() if self._changed(p, r)]
            return {"indexed": True, "generation": directory.name, "created": manifest["created"], "files": len(manifest["files"]), "pdf_files": sum(r["kind"] == "pdf" for r in manifest["files"].values()), "documents": db.execute("SELECT count(*) FROM documents").fetchone()[0], "book_works": db.execute("SELECT count(*) FROM documents WHERE json_extract(metadata,'$.type')='book'").fetchone()[0], "chunks": db.execute("SELECT count(*) FROM chunks").fetchone()[0], "mode": "lexical" if manifest["model"] == "lexical" else "hybrid", "changed_or_missing_known_files": stale, "new_files_discovery": "Execute update ou update --path; status não percorre o vault para descobrir arquivos novos.", "queue": load_json(self.root / ".dbrain/queue.json", []), "coverage_summary": summary, "coverage_note": "OCR permanece sinalizado para revisão. Páginas de pouco texto podem conter capas, imagens e tabelas; ausência de erro não significa interpretação visual completa.", "coverage_warnings": coverage, "last_error": load_json(self.root / '.dbrain/last-error.json'), "writer_active": self._writer(), "last_update": load_json(self.root / ".dbrain/last-update.json")}
        finally:
            db.close()
