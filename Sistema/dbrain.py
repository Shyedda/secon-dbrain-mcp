"""SecOn Dbrain CLI. Every writer operation is explicit."""
from __future__ import annotations
import argparse
import difflib
import json
import re
import sys
import unicodedata
import uuid
from pathlib import Path
import yaml
from filelock import FileLock
from common import ROOT, NOTE_DIRS, actor, config, schema, eligible, file_hash, load_json, now, relative, safe_name, save_json, note_dirs, library_path

def _normal(text):
    return re.sub(r"[^a-z0-9]+", " ", unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode().lower()).strip()

def similar_notes(root, title, aliases=()):
    """Titles/aliases of existing notes close to a new one; prevents parallel agents duplicating a concept."""
    wanted = {_normal(title), *(_normal(a) for a in aliases)} - {""}
    personal = set(schema(root)["personal_types"])
    exact, close = [], []
    for folder in sorted(set(note_dirs(root).values())):
        for path in (Path(root) / folder).rglob("*.md"):
            names, kind = {_normal(path.stem)}, None
            try:
                text = path.read_text(encoding="utf-8-sig")
                if text.startswith("---\n"):
                    meta = yaml.safe_load(text.split("---", 2)[1]) or {}
                    kind = meta.get("type")
                    names |= {_normal(meta.get("title", "")), *(_normal(a) for a in meta.get("aliases") or [])}
            except (OSError, yaml.YAMLError, ValueError):
                pass
            names.discard("")
            rel = relative(root, path)
            # Only another synthesized note is a duplicate; a book card or map with the same name is a relation.
            if names & wanted and kind in personal:
                exact.append(rel)
            elif names & wanted:
                close.append(rel)
            elif any(difflib.SequenceMatcher(None, a, b).ratio() >= .8 for a in names for b in wanted):
                close.append(rel)
    return exact, close

def new_note(root, kind, title, areas=None, by=None, allow_similar=False, aliases=None):
    root = Path(root)
    vocabulary = schema(root)
    unknown = [a for a in areas or [] if a not in vocabulary["areas"]]
    if unknown:
        raise ValueError(f"Área desconhecida: {unknown}; use {sorted(vocabulary['areas'])}")
    exact, close = similar_notes(root, title, aliases or [])
    if exact and not allow_similar:
        raise ValueError(f"Já existe nota com este título/alias: {exact}. Edite-a ou use --allow-similar se for outro conceito.")
    folder = library_path(root, note_dirs(root)[kind])
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (safe_name(title) + ".md")
    source = library_path(root, config(root).get("template_dir", "90-Templates")) / (kind + ".md")
    if not source.exists():
        raise RuntimeError(f"Template ausente: {source}")
    text = source.read_text(encoding="utf-8")
    front, body = text.split("---", 2)[1:]
    metadata = yaml.safe_load(front)
    author = actor(by)
    metadata.update({"id": str(uuid.uuid4()), "type": kind, "title": title, "created": now()[:10], "updated": now()[:10], "areas": areas or [], "aliases": aliases or metadata.get("aliases", []), "status": "needs-review", "created_by": author})
    body = body.replace("{{title}}", title).strip()
    # 'x' prevents silent replacement if a title already exists.
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write("---\n" + yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False) + "---\n\n" + body + "\n")
    state = root / ".dbrain"
    state.mkdir(exist_ok=True)
    with FileLock(str(state / "queue.lock"), timeout=10):
        queue = load_json(state / "queue.json", [])
        rel = relative(root, path)
        if rel not in queue:
            queue.append(rel)
        save_json(state / "queue.json", queue)
    return {"created": str(path), "created_by": author, "queued": True, "similar_notes": close + exact, "next": f'.\\dbrain.ps1 update --path "{relative(root, path)}"'}

def vocabulary_errors(meta, vocabulary):
    """Controlled vocabulary shared by Obsidian Bases and search filters."""
    errors = []
    if meta.get("type") and meta["type"] not in vocabulary["types"]:
        errors.append(f"type desconhecido: {meta['type']}")
    if meta.get("status") and meta["status"] not in vocabulary["status"]:
        errors.append(f"status desconhecido: {meta['status']}")
    for area in meta.get("areas") or []:
        if area not in vocabulary["areas"]:
            errors.append(f"área desconhecida: {area}")
    if meta.get("created_by") and not re.fullmatch(r"[a-z][a-z0-9-]{1,31}", str(meta["created_by"])):
        errors.append("created_by inválido")
    for field, pattern in vocabulary["patterns"].items():
        for value in meta.get(field) or []:
            if not re.fullmatch(pattern, str(value)):
                errors.append(f"{field} fora do padrão {pattern}: {value}")
    return errors

def check(root, originals=False):
    from indexer import generation, readonly_db, scan
    from extraction import markdown
    import numpy as np
    root = Path(root)
    result = {"errors": [], "warnings": [], "checked_notes": 0, "originals_verified": 0}
    cfg = config(root)
    vocabulary = schema(root)
    missing_author = []
    paths = list(scan(root, cfg))
    md_paths = [p for p in paths if p.suffix.lower() == ".md"]
    stems = {p.stem for p in md_paths}
    # Resolve ordinary note and PDF wikilinks without traversing the source study tree.
    ids = {}
    for path in md_paths:
        try:
            extracted = markdown(path, relative(root, path))
            result["checked_notes"] += 1
            if not extracted.get("excluded"):
                meta = extracted["metadata"]
                result["errors"].extend(f"{relative(root, path)}: {e}" for e in vocabulary_errors(meta, vocabulary))
                if not meta.get("created_by"):
                    missing_author.append(relative(root, path))
            sid = extracted.get("source_id")
            if sid and sid in ids:
                result["errors"].append(f"ID duplicado: {path} e {ids[sid]}")
            if sid:
                ids[sid] = path
            text = path.read_text(encoding="utf-8-sig")
            for link in re.findall(r"\[\[([^\]]+)\]\]", text):
                target = link.split("|", 1)[0].split("#", 1)[0]
                if not target or "://" in target:
                    continue
                if not ((root / target).exists() or (root / (target + ".md")).exists() or (path.parent / target).exists() or (path.parent / (target + ".md")).exists() or target in stems):
                    result["errors"].append(f"Wikilink não resolvido em {relative(root,path)}: {target}")
        except Exception as exc:
            result["errors"].append(f"{path}: {exc}")
    if missing_author:
        result["warnings"].append(f"{len(missing_author)} notas sem created_by (proveniência humana/agente): " + ", ".join(missing_author[:10]))
    directory = generation(root)
    if directory:
        db = readonly_db(directory / "knowledge.sqlite")
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            result["errors"].append("SQLite corrompido")
        if db.execute('PRAGMA foreign_key_check').fetchone():
            result['errors'].append('Referência de chunk para fonte inexistente')
        count = db.execute("SELECT count(*) FROM chunks").fetchone()[0]
        vectors = np.load(directory / "vectors.npy", mmap_mode="r")
        if vectors.shape != (count, 384):
            result["errors"].append("Dimensões de vetores inconsistentes")
        mapping=db.execute('SELECT count(DISTINCT vector_row),min(vector_row),max(vector_row) FROM chunks').fetchone()
        if count and tuple(mapping)!=(count,0,count-1):
            result['errors'].append('Mapeamento de linhas vetoriais inconsistente')
        manifest = load_json(directory / "manifest.json")
        if manifest["model"] != "lexical" and len(vectors):
            norms = np.linalg.norm(vectors, axis=1)
            if not np.allclose(norms, 1, atol=.002):
                result["errors"].append("Vetores sem normalização L2")
        # Verify each stored chunk against its immutable source unit, not a guessed page.
        bad = 0
        for document in db.execute("SELECT * FROM documents"):
            ext = load_json(root / document["cache"])
            for chunk in db.execute("SELECT text,locator FROM chunks WHERE source_id=?", (document["id"],)):
                loc = json.loads(chunk["locator"])
                unit = ext["units"][loc["unit"]]
                expected = unit["text"].replace("\x00", "")[loc["char_start"]:loc["char_end"]]
                bad += expected != chunk["text"]
        if bad:
            result["errors"].append(f"{bad} citações não correspondem ao texto da fonte")
        result["chunks_verified"] = count
        db.close()
    else:
        result["warnings"].append("Base ainda não indexada")
    if originals:
        baseline = load_json(root / ".dbrain/originals-baseline.json", {})
        for rel, entry in baseline.get("books", {}).items():
            p = root / rel
            if not p.exists() or file_hash(p) != entry["sha256"]:
                result["errors"].append("Original divergiu: " + rel)
            else:
                result["originals_verified"] += 1
        for path, entry in baseline.get("study", {}).items():
            p = Path(path)
            if not p.exists() or file_hash(p) != entry["sha256"]:
                result["errors"].append("Original de Estudo divergiu: " + path)
            else:
                result["originals_verified"] += 1
    result["ok"] = not result["errors"]
    return result

def main():
    parser = argparse.ArgumentParser(description="SecOn Dbrain: conhecimento local, incremental e rastreável")
    parser.add_argument("--root", type=Path, default=ROOT, help="Raiz da biblioteca (ou DBRAIN_ROOT); padrão: pasta do projeto")
    subs = parser.add_subparsers(dest="command", required=True)
    for name in ("update", "rebuild"):
        p = subs.add_parser(name, help="Atualizar somente mudanças" if name == "update" else "Reconstrução explícita após mudança de modelo/configuração")
        p.add_argument("--path", action="append", help="Arquivo/pasta relativo ao vault; pode repetir")
        p.add_argument("--lexical", action="store_true", help="Índice somente lexical (modo alternativo explícito)")
        p.add_argument('--reextract', action='store_true', help='Refazer extração somente de --path, por exemplo após OCR seletivo')
        p.add_argument("--wait", type=int, default=0, help="Segundos para aguardar outro escritor (outro agente) antes de falhar")
        p.add_argument("--by", help="Quem executa: human, codex, claude (padrão: variável DBRAIN_AGENT ou human)")
    p = subs.add_parser("new", help="Criar nota a partir de template e colocá-la na fila")
    p.add_argument("--type", required=True, choices=NOTE_DIRS)
    p.add_argument("--title", required=True)
    p.add_argument("--areas", default="", help="Áreas separadas por vírgula")
    p.add_argument("--aliases", default="", help="Siglas e termos alternativos separados por vírgula")
    p.add_argument("--by", help="Autor: human, codex, claude (padrão: DBRAIN_AGENT ou human)")
    p.add_argument("--allow-similar", action="store_true", help="Criar mesmo havendo nota com título/alias idêntico")
    p = subs.add_parser("search", help="Pesquisar sem alterar o índice")
    p.add_argument("query")
    p.add_argument("--limit", type=int, default=8)
    p.add_argument("--area")
    p.add_argument("--type")
    p.add_argument("--filter", action="append", default=[], metavar="CAMPO=VALOR", help="Filtro adicional (cwe, owasp, attack, stack, created_by, status...); pode repetir")
    p.add_argument("--lexical", action="store_true")
    p = subs.add_parser("read", help="Ler uma fonte cadastrada")
    p.add_argument("source_id")
    p.add_argument("--page", type=int)
    p.add_argument("--chunk")
    p.add_argument("--generation")
    subs.add_parser("status", help="Estado e cobertura, sem indexação")
    p = subs.add_parser("catalog", help="Criar ficha de um PDF já indexado, sem sobrescrever notas")
    p.add_argument("--path", required=True)
    p.add_argument("--title")
    p.add_argument("--author", action="append")
    p.add_argument("--areas", default="")
    p.add_argument("--wait", type=int, default=0)
    p.add_argument("--by")
    p = subs.add_parser("check", help="Verificar propriedades, links e citações")
    p.add_argument("--originals", action="store_true", help="Reler originais e conferir hashes")
    p = subs.add_parser("prune", help="Remover gerações antigas/não publicadas (simulação por padrão)")
    p.add_argument("--keep", type=int, default=3, help="Gerações publicadas recentes a manter além da atual")
    p.add_argument("--apply", action="store_true")
    subs.add_parser("setup-model", help="Baixar explicitamente o modelo fixado")
    p = subs.add_parser("mcp", help="Servidor STDIO; escrita de derivados é opt-in")
    p.add_argument("--allow-writes", action="store_true")
    p = subs.add_parser("prepare", help="Preparar fontes e mapas localmente, sem chamadas a provedor")
    p.add_argument("--path", action="append")
    p.add_argument("--lexical", action="store_true")
    p.add_argument("--wait", type=int, default=0)
    p.add_argument("--by")
    p = subs.add_parser("enrichment-plan", help="Planejar pequeno lote de sínteses para seu assistente")
    p.add_argument("--query")
    p.add_argument("--source-id", action="append")
    p.add_argument("--max-tasks", type=int, default=3)
    p.add_argument("--max-input-tokens", type=int, default=4000)
    p.add_argument("--by")
    p = subs.add_parser("enrichment-read", help="Ler um trecho limitado e as instruções de síntese")
    p.add_argument("task_id")
    p = subs.add_parser("enrichment-submit", help="Receber JSON title/summary/citations e indexar a síntese")
    p.add_argument("task_id")
    p.add_argument("--file", type=Path, required=True)
    p.add_argument("--by", default="agent")
    p.add_argument("--wait", type=int, default=0)
    subs.add_parser("overview", help="Cobertura de fontes, derivados e enriquecimento")
    args = parser.parse_args()
    root = args.root.resolve()
    if args.command == "prepare":
        from knowledge_pipeline import prepare
        result = prepare(root, args.path, args.lexical, args.wait, args.by, lambda msg: print(msg, file=sys.stderr, flush=True))
    elif args.command == "overview":
        from knowledge_pipeline import overview
        result = overview(root)
    elif args.command == "enrichment-plan":
        from knowledge_pipeline import plan_enrichment
        result = plan_enrichment(root, args.query, args.source_id, args.max_tasks, args.max_input_tokens, args.by)
    elif args.command == "enrichment-read":
        from knowledge_pipeline import read_enrichment_task
        result = read_enrichment_task(root, args.task_id)
    elif args.command == "enrichment-submit":
        from knowledge_pipeline import submit_enrichment
        payload = load_json(args.file)
        result = submit_enrichment(root, args.task_id, payload["title"], payload["summary"], payload["citations"], args.by, args.wait)
    elif args.command in {"update", "rebuild"}:
        from indexer import update
        result = update(root, args.path, args.lexical, args.command == "rebuild", lambda msg: print(msg, file=sys.stderr, flush=True), reextract=args.reextract, wait=args.wait, by=args.by)
    elif args.command == "prune":
        from indexer import prune
        result = prune(root, args.keep, args.apply)
    elif args.command == "new":
        result = new_note(root, args.type, args.title, [s.strip() for s in args.areas.split(",") if s.strip()], args.by, args.allow_similar, [s.strip() for s in args.aliases.split(",") if s.strip()])
    elif args.command == "catalog":
        from library import catalog_one
        result = catalog_one(root, args.path, args.title, args.author, [s.strip() for s in args.areas.split(",") if s.strip()], args.wait, args.by)
    elif args.command == "setup-model":
        from embeddings import setup_model
        result = setup_model(root)
    elif args.command == "check":
        result = check(root, args.originals)
    elif args.command == "mcp":
        from mcp_server import create_server
        create_server(root, allow_writes=args.allow_writes).run(transport="stdio")
        return
    else:
        from retrieval import Knowledge
        kb = Knowledge(root, getattr(args, "lexical", False))
        if args.command == "search":
            filters = {}
            if args.area:
                filters["areas"] = args.area
            if args.type:
                filters["type"] = args.type
            for item in args.filter:
                key, _, value = item.partition("=")
                if not value:
                    raise ValueError("Use --filter CAMPO=VALOR")
                filters.setdefault(key.strip(), []).append(value.strip())
            result = kb.search(args.query, filters, args.limit)
        elif args.command == "read":
            result = kb.read(args.source_id, {k: v for k, v in {"pdf_page": args.page, "chunk_id": args.chunk, "generation": args.generation}.items() if v})
        else:
            result = kb.status()
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    if args.command == "check" and not result["ok"]:
        sys.exit(2)

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    try:
        main()
    except Exception as exc:
        print(json.dumps({"error": str(exc), "type": type(exc).__name__}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
