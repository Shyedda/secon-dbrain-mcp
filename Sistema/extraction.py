"""Immutable source extraction; OCR output never overwrites a PDF."""
from __future__ import annotations
import json
import re
import shutil
import subprocess
from pathlib import Path
import yaml
from common import digest, save_json, load_json, stable_id

def markdown(path, relative_path):
    text = Path(path).read_text(encoding="utf-8-sig")
    meta, body, first_line = {}, text, 1
    if text.startswith("---\n"):
        end = re.search(r"^---\s*$", text[4:], re.M)
        if not end:
            raise ValueError("YAML frontmatter não terminado")
        offset = 4 + end.start()
        meta = yaml.safe_load(text[4:offset]) or {}
        if not isinstance(meta, dict):
            raise ValueError("YAML precisa ser um mapa")
        body_offset = 4 + end.end()
        body = text[body_offset:].lstrip("\n")
        first_line = text[:len(text) - len(body)].count("\n") + 1
    if meta.get("rag_exclude") is True:
        return {"excluded": True, "metadata": meta}
    for field in ("areas", "aliases", "sources", "tags", "cwe", "owasp", "attack", "capec", "stack"):
        if field in meta and not isinstance(meta[field], list):
            raise ValueError(f"Propriedade {field} precisa ser uma lista")
    source_id = str(meta.get("id") or "")
    if source_id in {"", "{{id}}", "identificador-estavel"}:
        source_id = None  # Manifest assigns an ID without modifying the user's note.
    title = str(meta.get("title") or Path(path).stem)
    sections, current, heading = [], [], title
    start = first_line
    fence = False
    for num, line in enumerate(body.splitlines(), first_line):
        if line.lstrip().startswith(("```", "~~~")):
            fence = not fence
        if not fence and re.match(r"^#{1,6}\s+", line):
            if current and "\n".join(current).strip():
                sections.append({"text": "\n".join(current), "section": heading, "line_start": start, "line_end": num - 1, "method": "markdown", "quality": "text"})
            heading = line.lstrip("# ")
            current, start = [line], num
        else:
            current.append(line)
    if current and "\n".join(current).strip():
        sections.append({"text": "\n".join(current), "section": heading, "line_start": start, "line_end": first_line + len(body.splitlines()) - 1, "method": "markdown", "quality": "text"})
    return {"source_id": source_id, "metadata": {**meta, "title": title, "type": meta.get("type", "note"), "areas": meta.get("areas", []), "aliases": meta.get("aliases", []), "language": meta.get("language", "pt-BR"), "status": meta.get("status", "imported"), "sources": meta.get("sources", [])}, "units": sections, "raw_text": text, "semantic_hash": digest(body), "coverage": {"units": len(sections), "warnings": []}}

def tesseract_path(root):
    local = Path(root) / ".dbrain/tools/tesseract/tesseract.exe"
    return str(local) if local.exists() else shutil.which("tesseract")

def pdf(path, root, sha, cfg):
    import pypdfium2 as pdfium
    from pypdf import PdfReader
    path, root = Path(path), Path(root)
    doc = pdfium.PdfDocument(path)
    md = doc.get_metadata_dict()
    toc = []
    for item in doc.get_toc():
        destination = item.get_dest()
        page_number = destination.get_index() if destination is not None else None
        if page_number is not None:
            toc.append({"page": page_number + 1, "level": item.level, "title": item.get_title()})
    try:
        reader = PdfReader(str(path))
        labels = reader.page_labels
        printed_labels = "/PageLabels" in reader.trailer["/Root"]
    except Exception:
        labels, printed_labels = [], False
    units, warnings, raw = [], [], []
    low_text, empty, replaced = [], [], []
    selected = cfg.get("ocr", {}).get("pages", {}).get(path.name, [])
    ocr_dir = root / ".dbrain/ocr" / sha
    section = md.get("Title") or path.stem
    toc_by_page = {}
    for item in toc:
        toc_by_page.setdefault(item["page"], []).append(item)
    heading_stack = {}
    for page_index in range(len(doc)):
        number = page_index + 1
        if number in toc_by_page:
            for item in toc_by_page[number]:
                heading_stack = {k: v for k, v in heading_stack.items() if k < item["level"]}
                heading_stack[item["level"]] = item["title"]
            section = " > ".join(heading_stack[k] for k in sorted(heading_stack))
        page = doc[page_index]
        tp = page.get_textpage()
        text = tp.get_text_range().replace("\r\n", "\n").replace("\r", "\n")
        tp.close()
        raw.append(text)
        method, quality = "pdfium", "text"
        corrupt = text.count("\ufffd")
        if len(text.strip()) < 50:
            low_text.append(number)
            if not list(page.get_objects()):
                empty.append(number)
                quality = "blank"
            else:
                quality = "low-text-inspect-visual"
        if corrupt > 10:
            quality = "corrupt"
        ocr_json = ocr_dir / f"{number}.json"
        existing = load_json(ocr_json)
        if existing and existing.get("source_sha") == sha:
            text, method, quality = existing["text"], "tesseract", existing.get("quality", "ocr-needs-review")
            replaced.append(number)
        elif number in selected:
            exe = tesseract_path(root)
            if exe:
                ocr_dir.mkdir(parents=True, exist_ok=True)
                img_path = ocr_dir / f"{number}.png"
                bitmap = page.render(scale=300 / 72)
                image = bitmap.to_pil()
                image.save(img_path)
                image.close()
                bitmap.close()
                result = subprocess.run([exe, str(img_path), "stdout", "-l", cfg["ocr"].get("language", "eng+por"), "--psm", "3"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
                if result.returncode == 0 and result.stdout.strip():
                    text, method, quality = result.stdout, "tesseract", "ocr-needs-review"
                    save_json(ocr_json, {"source_sha": sha, "pdf_page": number, "text": text, "quality": quality, "dpi": 300})
                    replaced.append(number)
                else:
                    warnings.append({"page": number, "issue": "OCR falhou", "detail": result.stderr[-500:]})
            else:
                warnings.append({"page": number, "issue": "OCR necessário, Tesseract indisponível"})
        if quality == "corrupt":
            warnings.append({"page": number, "issue": "Texto corrompido não indexado", "invalid_chars": corrupt})
        # Keep page-local fidelity and raw text. Search normalization is conservative.
        units.append({"text": text, "raw_text": raw[-1], "section": section, "pdf_page": number, "page_label": str(labels[page_index]) if printed_labels and page_index < len(labels) else None, "method": method, "quality": quality})
        page.close()
    doc.close()
    normalized = re.sub(r"\s+", " ", "\n".join(raw)).strip()
    # Two image-only PDFs must not collapse into one work just because both
    # yielded an empty (or nearly empty) native text layer.
    sufficient_text = len(normalized) >= max(200, len(units)*20)
    semantic_hash = digest(normalized) if sufficient_text else digest('image-pdf:'+sha)
    if not sufficient_text and any(u['quality'] not in {'blank','text'} for u in units):
        warnings.append({'issue':'Pouco texto nativo; confira cobertura de OCR e páginas visuais'})
    return {"source_id": None, "metadata": {"title": md.get("Title") or path.stem, "authors": [md["Author"]] if md.get("Author") else [], "type": "book", "language": "en", "status": "imported", "areas": [], "aliases": []}, "units": units, "toc": toc, "semantic_hash": semantic_hash, "coverage": {"pages": len(units), "characters": sum(len(t) for t in raw), "dedup_basis": 'normalized-text' if sufficient_text else 'source-bytes', "low_text_pages": low_text, "blank_pages": empty, "ocr_pages": replaced, "warnings": warnings}}

def make_chunks(extracted, source_id, tokenizer=None, chunk_tokens=400, overlap=40):
    """Offsets map chunks to full page/section; code can be enlarged via read()."""
    chunks = []
    meta = extracted["metadata"]
    for unit_index, unit in enumerate(extracted["units"]):
        if unit.get("quality") in {"blank", "corrupt"} or not unit["text"].strip():
            continue
        # Keep line breaks/indentation. Do not fix source code or dehyphenate it.
        text = unit["text"].replace("\x00", "")
        heading = (meta["title"] + "\n" + unit.get("section", ""))[:500]
        if tokenizer:
            while len(tokenizer.tokens("passage: " + heading).ids) > 90:
                heading = heading[:int(len(heading) * .8)]
            encoding = tokenizer.tokens(text)
            offsets = encoding.offsets
            window = min(chunk_tokens, 505 - len(tokenizer.tokens("passage: " + heading + "\n").ids))
            starts = []
            pos = 0
            while pos < len(offsets):
                end = min(pos + window, len(offsets))
                # Prefer paragraph/newline boundaries, without dropping characters.
                if end < len(offsets):
                    for candidate in range(end - 1, max(pos + window // 2, pos + 1), -1):
                        between = text[offsets[candidate-1][1]:offsets[candidate][0]]
                        if "\n" in between:
                            end = candidate
                            break
                start_char = 0 if pos == 0 else offsets[pos][0]
                end_char = len(text) if end == len(offsets) else offsets[end][0]
                starts.append((start_char, end_char))
                if end == len(offsets):
                    break
                pos = max(pos + 1, end - min(overlap, (end-pos)//4))
        else:
            starts = [(p, min(p + 1200, len(text))) for p in range(0, len(text), 1100)]
        for part, (a, b) in enumerate(starts):
            body = text[a:b]
            if not body.strip():
                continue
            passage = heading + "\n" + body
            if tokenizer and len(tokenizer.tokenizer.encode("passage: " + passage).ids) > 512:
                raise ValueError("Chunk acima do limite; ajuste o segmentador")
            locator = {k: v for k, v in unit.items() if k not in {"text", "raw_text"}}
            locator.update({"unit": unit_index, "part": part, "char_start": a, "char_end": b})
            if "line_start" in unit:
                locator["line_start"] = unit["line_start"] + text[:a].count("\n")
                locator["line_end"] = unit["line_start"] + text[:b].count("\n")
            key = digest(passage)
            chunk_id = stable_id(f"{source_id}:{unit_index}:{part}:{key}")
            chunks.append({"id": chunk_id, "source_id": source_id, "text": body, "passage": passage, "embedding_key": key, "section": unit.get("section", ""), "locator": locator})
    return chunks
