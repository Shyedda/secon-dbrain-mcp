"""Add a human-editable catalog card for a newly indexed PDF."""
import json
from pathlib import Path
import yaml
from filelock import FileLock
from common import ROOT, actor, config, eligible, load_json, now, relative, safe_name, save_json, stable_id, note_dirs, library_path
from indexer import generation, readonly_db, writer, scan

def catalog_one(root, path, title=None, authors=None, areas=None, wait=0, by=None):
    root = Path(root).resolve()
    source = (root / path).resolve()
    if source.suffix.lower() != ".pdf" or not eligible(root, source, config(root)):
        raise ValueError("catalog aceita somente um PDF nas pastas pdf_roots cadastradas")
    rel = relative(root, source)
    directory = generation(root)
    if not directory:
        raise ValueError("Primeiro execute update --path para o PDF")
    manifest = load_json(directory / "manifest.json")
    record = manifest["files"].get(rel)
    if not record or not record.get("source_id"):
        raise ValueError("Primeiro execute update --path para o PDF")
    with writer(root, "catalog " + path, wait, by):
        db = readonly_db(directory / "knowledge.sqlite")
        row = db.execute("SELECT * FROM documents WHERE id=?", (record["source_id"],)).fetchone()
        db.close()
        metadata = json.loads(row["metadata"])
        paths = json.loads(row["paths"])
        if title:
            metadata["title"] = title
        if authors:
            metadata["authors"] = authors
        if areas:
            metadata["areas"] = areas
        filename = "Fonte - " + safe_name(metadata["title"]) + ".md"
        source_dir = library_path(root, note_dirs(root)["source"])
        target = library_path(root, config(root).get("catalog_dir", str(source_dir.relative_to(root) / "Livros"))) / filename
        # A renamed or retitled human card must not yield another card with the
        # same persistent identity. Do not assume its filename is still ours.
        cards = {p for p in scan(root, config(root)) if p.suffix.lower() == '.md'}
        cards.update(source_dir.rglob('*.md'))
        cards.update(target.parent.rglob('*.md'))
        for card in sorted(cards):
            if card.suffix.lower() != '.md':
                continue
            relative(root, card)
            text = card.read_text(encoding='utf-8-sig')
            if text.startswith('---'):
                front = yaml.safe_load(text.split('---', 2)[1]) or {}
                if isinstance(front, dict) and front.get('source_id') == record['source_id']:
                    return {'created': False, 'path': str(card), 'message': 'Ficha existente preservada; edite-a no seu editor Markdown.'}
        if target.exists():
            existing = target.read_text(encoding="utf-8-sig")
            front = yaml.safe_load(existing.split("---", 2)[1]) if existing.startswith("---") else {}
            if front.get("source_id") == record["source_id"]:
                return {"created": False, "path": str(target), "message": "Ficha existente preservada; edite-a no seu editor Markdown."}
            target = target.with_stem(target.stem + " - " + record["source_id"][:8])
        ext = load_json(root / row["cache"])
        props = {"id": stable_id("catalog:" + record["source_id"]), "type": "source", "title": metadata["title"], "authors": metadata.get("authors", []), "areas": metadata.get("areas", []), "language": metadata.get("language", "en"), "status": "imported", "created_by": actor(by), "source_id": record["source_id"], "source_files": paths, "pages": ext["coverage"].get("pages"), "bibliography_status": "needs-review", "created": now()[:10], "updated": now()[:10]}
        body = "# " + metadata["title"] + "\n\n## Originais\n\n" + "\n".join(f"- [[{p}]]" for p in paths) + "\n\n## Cobertura\n\nTexto extraído para busca; autoria, edição e qualidade visual precisam de revisão. Esta ficha não é um fichamento integral.\n\n## Sumário\n\n"
        for entry in ext.get("toc", []):
            if entry["level"] <= 1:
                body += f"- [[{paths[0]}#page={entry['page']}|{entry['title'].replace('|','-')} — PDF p. {entry['page']}]]\n"
        body += "\n## Minhas anotações\n\n"
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("x", encoding="utf-8") as stream:
            stream.write("---\n" + yaml.safe_dump(props, allow_unicode=True, sort_keys=False) + "---\n\n" + body)
        catalog = load_json(root / ".dbrain/catalog.json", {})
        dirty = load_json(root / ".dbrain/catalog-dirty.json", [])
        for p in paths:
            catalog[p] = {"source_id": record["source_id"], "metadata": metadata}
            if p not in dirty:
                dirty.append(p)
        save_json(root / ".dbrain/catalog.json", catalog)
        save_json(root / ".dbrain/catalog-dirty.json", dirty)
        with FileLock(str(root / ".dbrain/queue.lock"), timeout=10):
            queue = load_json(root / ".dbrain/queue.json", [])
            save_json(root / ".dbrain/queue.json", list(dict.fromkeys(queue + paths + [relative(root,target)])))
        return {"created": True, "path": str(target), "next": f'.\\dbrain.ps1 update --path "{rel}" --path "{relative(root,target)}"'}
