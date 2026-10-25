"""Exercise local preparation and source-backed MCP enrichment without a provider."""
import asyncio
import json
import os
from pathlib import Path
import sys
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import config, digest, file_hash, load_json, save_json, schema
from indexer import generation, update, writer
from knowledge_pipeline import overview, plan_enrichment, prepare, read_enrichment_task, submit_enrichment
from retrieval import Knowledge


@pytest.fixture
def collection(tmp_path):
    root = tmp_path / "Acervo com espaços e ação"
    current = Path(__file__).resolve().parents[2]
    cfg = {"include": ["PDFs", "Markdown", "Conhecimento"], "pdf_roots": ["PDFs"], "input_dirs": {"pdf": "PDFs", "markdown": "Markdown"}, "knowledge_dir": "Conhecimento", "chunk_tokens": 400, "overlap_tokens": 40, "embedding_batch": 4, "ocr": {}}
    save_json(root / "Sistema/config.json", cfg)
    save_json(root / "Sistema/schema.json", schema(current))
    (root / "Markdown").mkdir()
    (root / "PDFs").mkdir()
    (root / "Markdown/estudo.md").write_text("# Controle de acesso\n\nMARCADOR_FONTE_ORIGINAL A autorização deve ser verificada para cada operação. O cliente pode fornecer identificadores, mas o servidor verifica o acesso.\n\n## Limitações\n\nA regra depende do contexto e dos requisitos do sistema.\n", encoding="utf-8")
    (root / "Markdown/README.md").write_text("---\nrag_exclude: true\n---\nGuia de entrada.\n", encoding="utf-8")
    (root / "PDFs/formato-errado.md").write_text("NUNCA_INDEXAR", encoding="utf-8")
    return root


def test_local_preparation_is_queryable_idempotent_and_preserves_inputs(collection):
    source = collection / "Markdown/estudo.md"
    original = source.read_bytes()
    first = prepare(collection, lexical=True)
    assert first["provider_calls"] == 0 and first["source_count"] == 1
    kb = Knowledge(collection)
    assert any(h["path"].endswith("estudo.md") for h in kb.search("MARCADOR_FONTE_ORIGINAL")["results"])
    assert not kb.search("NUNCA_INDEXAR")["results"]
    report = overview(collection)
    assert report["source_count"] == 1
    assert report["sources"][0]["indexed_units"] == report["sources"][0]["units"]
    assert len(report["derived"]) == 3
    before = generation(collection)
    second = prepare(collection, lexical=True)
    assert not second["generated_or_updated"] and second["derived_update"] is None
    assert second["source_update"]["content_reads"] == 0
    assert generation(collection) == before
    assert source.read_bytes() == original


def test_bounded_enrichment_cites_sources_and_excludes_stale_summaries(collection):
    prepare(collection, lexical=True)
    task_id = plan_enrichment(collection, max_tasks=1, max_input_tokens=1000)["tasks"][0]["task_id"]
    task = read_enrichment_task(collection, task_id)
    assert task["references"][0]["citation"] == 0
    assert len(task["text"]) <= 200
    summary = "MARCADOR_RESUMO_GOLD A autorização deve ser verificada no servidor para cada operação [0]."
    result = submit_enrichment(collection, task_id, "Autorização por operação", summary, [0])
    assert result["status"] == "needs-review" and result["semantic_validation"] is False
    kb = Knowledge(collection)
    hits = kb.search("MARCADOR_RESUMO_GOLD")["results"]
    assert hits and hits[0]["derivation"]["source_refs"][0]["unit"] == task["references"][0]["unit"]
    again = submit_enrichment(collection, task_id, "Autorização por operação", summary, [0])
    assert again["generation"] == result["generation"]
    source = collection / "Markdown/estudo.md"
    source.write_text(source.read_text(encoding="utf-8") + "\nFonte revisada.\n", encoding="utf-8")
    assert not kb.search("MARCADOR_RESUMO_GOLD")["results"]
    with pytest.raises(ValueError, match="desatualizado"):
        kb.read(hits[0]["source_id"])
    with pytest.raises(ValueError, match="alterada"):
        read_enrichment_task(collection, task_id)
    prepare(collection, lexical=True)
    assert not kb.search("MARCADOR_RESUMO_GOLD")["results"]
    fresh = plan_enrichment(collection, max_tasks=1)["tasks"][0]["task_id"]
    assert fresh != task_id


def test_generated_files_and_submitted_human_edits_are_never_overwritten(collection):
    prepare(collection, lexical=True)
    card = next((collection / "Conhecimento/10-Fontes").glob("Indice*.md"))
    card.write_text(card.read_text(encoding="utf-8") + "\nEDIÇÃO HUMANA\n", encoding="utf-8")
    card_bytes = card.read_bytes()
    source = collection / "Markdown/estudo.md"
    source.write_text(source.read_text(encoding="utf-8") + "\nMudança que exige novo mapa.\n", encoding="utf-8")
    result = prepare(collection, lexical=True)
    assert card.relative_to(collection).as_posix() in result["human_edits_preserved"]
    assert card.read_bytes() == card_bytes
    task = plan_enrichment(collection, max_tasks=1)["tasks"][0]
    result = submit_enrichment(collection, task["task_id"], "Síntese", "A fonte descreve controle de acesso e suas limitações [0].", [0])
    note = collection / result["path"]
    note.write_text(note.read_text(encoding="utf-8") + "\nOutra edição humana.\n", encoding="utf-8")
    original = note.read_bytes()
    with pytest.raises(ValueError, match="preservado"):
        submit_enrichment(collection, task["task_id"], "Síntese", "A fonte descreve controle de acesso e suas limitações [0].", [0])
    assert note.read_bytes() == original


def test_enrichment_limits_locks_and_derived_sources_are_enforced(collection):
    prepare(collection, lexical=True)
    with pytest.raises(ValueError):
        plan_enrichment(collection, max_tasks=11)
    with pytest.raises(ValueError):
        read_enrichment_task(collection, "../../fora")
    derived = overview(collection)["derived"][0]["source_id"]
    with pytest.raises(ValueError, match="originais"):
        plan_enrichment(collection, source_ids=[derived])
    task = plan_enrichment(collection, max_tasks=1)["tasks"][0]
    with pytest.raises(ValueError):
        submit_enrichment(collection, task["task_id"], "Título", "Sem referência adequada e com uma alegação.", [99])
    with writer(collection, "teste", 0, "human"):
        with pytest.raises(RuntimeError, match="Outro processo"):
            plan_enrichment(collection)


def test_submission_recovers_after_file_creation_before_task_completion(collection, monkeypatch):
    import knowledge_pipeline
    prepare(collection, lexical=True)
    task = plan_enrichment(collection, max_tasks=1)["tasks"][0]
    real_save = knowledge_pipeline.save_json
    def fail_completion(path, value):
        if isinstance(value, dict) and value.get("status") == "submitted":
            raise OSError("Falha simulada após escrita")
        return real_save(path, value)
    monkeypatch.setattr(knowledge_pipeline, "save_json", fail_completion)
    summary = "O servidor verifica a autorização para cada operação [0]."
    with pytest.raises(OSError, match="simulada"):
        submit_enrichment(collection, task["task_id"], "Síntese recuperável", summary, [0])
    monkeypatch.setattr(knowledge_pipeline, "save_json", real_save)
    result = submit_enrichment(collection, task["task_id"], "Síntese recuperável", summary, [0])
    assert result["indexed"] and len(list((collection / "Conhecimento/20-Notas").glob("*.md"))) == 1


def test_reading_gold_verifies_bytes_even_if_source_timestamp_was_preserved(collection):
    prepare(collection, lexical=True)
    task = plan_enrichment(collection, max_tasks=1)["tasks"][0]
    result = submit_enrichment(collection, task["task_id"], "Síntese", "A fonte descreve o controle de acesso no servidor [0].", [0])
    source = collection / "Markdown/estudo.md"
    stat = source.stat()
    source.write_bytes(source.read_bytes().replace(b"servidor", b"CLIENTEX"))
    os.utime(source, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    from extraction import markdown
    sid = markdown(collection / result["path"], result["path"])["source_id"]
    with pytest.raises(ValueError, match="desatualizado"):
        Knowledge(collection).read(sid)


def test_mcp_writers_are_opt_in_and_complete_a_real_protocol_roundtrip(collection, tmp_path):
    prepare(collection, lexical=True)
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    def payload(result):
        assert not result.isError, result.content
        return result.structuredContent or json.loads(result.content[0].text)

    async def exercise(allow):
        script = Path(__file__).resolve().parents[1] / "mcp_server.py"
        args = [str(script), "--root", str(collection)] + (["--allow-writes"] if allow else [])
        params = StdioServerParameters(command=sys.executable, args=args, cwd=str(tmp_path), env={**os.environ, "PYTHONUTF8": "1", "HF_HUB_OFFLINE": "1"})
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as client:
                await client.initialize()
                names = {tool.name for tool in (await client.list_tools()).tools}
                assert ("submit_enrichment" in names) is allow
                assert ("prepare_knowledge" in names) is allow
                assert payload(await client.call_tool("knowledge_overview", {}))["source_count"] == 1
                if allow:
                    plan = payload(await client.call_tool("plan_enrichment", {"max_tasks": 1}))
                    task_id = plan["tasks"][0]["task_id"]
                    task = payload(await client.call_tool("read_enrichment_task", {"task_id": task_id}))
                    assert task["content_is_untrusted_reference"]
                    result = payload(await client.call_tool("submit_enrichment", {"task_id": task_id, "title": "Síntese MCP", "summary": "MARCADOR_MCP_GOLD O servidor verifica autorização por operação [0].", "citations": [0]}))
                    assert result["indexed"] and result["status"] == "needs-review"

    async def both():
        await exercise(False)
        await exercise(True)
    asyncio.run(asyncio.wait_for(both(), timeout=45))


def test_navigation_maps_have_stable_names_ids_and_are_noop_when_unchanged(collection):
    import yaml

    result = prepare(collection, lexical=True)
    inventory = collection / "Conhecimento/00-Inicio/Mapa geral do acervo.md"
    topics = collection / "Conhecimento/00-Inicio/Mapa de temas.md"
    assert inventory.is_file() and topics.is_file()
    assert result["generated_or_updated"]
    first = {path: path.read_bytes() for path in (inventory, topics)}
    ids = {path: yaml.safe_load(path.read_text(encoding="utf-8").split("---", 2)[1])["id"] for path in (inventory, topics)}
    assert list((collection / "Conhecimento/10-Fontes").glob("Indice*.md"))

    repeated = prepare(collection, lexical=True)
    assert repeated["generated_or_updated"] == []
    assert repeated["derived_update"] is None
    assert {path: path.read_bytes() for path in (inventory, topics)} == first

    source = collection / "Markdown/estudo.md"
    source.write_text(source.read_text(encoding="utf-8") + "\nUma nova evidência de autorização.\n", encoding="utf-8")
    changed = prepare(collection, lexical=True)
    assert changed["generated_or_updated"]
    assert {path: yaml.safe_load(path.read_text(encoding="utf-8").split("---", 2)[1])["id"] for path in (inventory, topics)} == ids
    assert all(path.read_bytes() != first[path] for path in (inventory, topics))
    histories = list((collection / ".dbrain/knowledge/history/maps").rglob("*.md"))
    assert all(any(path.read_bytes() == old for path in histories) for old in first.values())
    kb = Knowledge(collection)
    map_hits = kb.search("Mapa geral do acervo")["results"]
    assert not any("history/maps" in hit["path"] for hit in map_hits)


def test_legacy_map_migration_preserves_content_and_archives_only_registered_bytes(collection):
    import yaml

    prepare(collection, lexical=True)
    stable = collection / "Conhecimento/00-Inicio/Mapa geral do acervo.md"
    original = stable.read_bytes()
    original_id = yaml.safe_load(stable.read_text(encoding="utf-8").split("---", 2)[1])["id"]
    legacy = stable.with_name("Mapa geral do acervo - abcdef123456.md")
    legacy.write_bytes(original)
    stable.unlink()
    registry_path = collection / ".dbrain/knowledge/generated-files.json"
    registry = load_json(registry_path)
    registry.pop(stable.relative_to(collection).as_posix(), None)
    registry[legacy.relative_to(collection).as_posix()] = file_hash(legacy)
    save_json(registry_path, registry)

    source = collection / "Markdown/estudo.md"
    source.write_text(source.read_text(encoding="utf-8") + "\nMudança para disparar a migração.\n", encoding="utf-8")
    result = prepare(collection, lexical=True)
    migrated = stable.read_bytes()
    assert yaml.safe_load(stable.read_text(encoding="utf-8").split("---", 2)[1])["id"] == original_id
    assert not legacy.exists()
    assert legacy.relative_to(collection).as_posix() in result["archived_maps"]
    assert migrated != original  # The stable map reflects the changed source.
    assert any(p.read_bytes() == original for p in (collection / ".dbrain/knowledge/history/maps").rglob("*.md"))


def test_map_edits_and_unregistered_legacy_names_are_preserved(collection):
    prepare(collection, lexical=True)
    stable = collection / "Conhecimento/00-Inicio/Mapa geral do acervo.md"
    legacy = collection / "Conhecimento/00-Inicio/Mapa por tema - 123456abcdef.md"
    unregistered = collection / "Conhecimento/00-Inicio/Mapa geral do acervo - 987654abcdef.md"
    stable.write_text(stable.read_text(encoding="utf-8") + "\nEDIÇÃO HUMANA NO MAPA ESTÁVEL\n", encoding="utf-8")
    legacy.write_text("# Mapa legado editado\n\nEDIÇÃO HUMANA LEGADA\n", encoding="utf-8")
    unregistered.write_text("# Mapa não registrado\n\nEDIÇÃO HUMANA\n", encoding="utf-8")
    expected = {path: path.read_bytes() for path in (stable, legacy, unregistered)}
    registry_path = collection / ".dbrain/knowledge/generated-files.json"
    registry = load_json(registry_path)
    registry[legacy.relative_to(collection).as_posix()] = digest("conteúdo anterior, diferente da edição atual")
    save_json(registry_path, registry)

    source = collection / "Markdown/estudo.md"
    source.write_text(source.read_text(encoding="utf-8") + "\nAlteração da fonte.\n", encoding="utf-8")
    result = prepare(collection, lexical=True)
    assert all(path.exists() and path.read_bytes() == data for path, data in expected.items())
    preserved = set(result["human_edits_preserved"])
    assert {path.relative_to(collection).as_posix() for path in (stable, legacy, unregistered)} <= preserved
    archived = set(result["archived_maps"])
    assert legacy.relative_to(collection).as_posix() not in archived
    assert unregistered.relative_to(collection).as_posix() not in archived


def test_topic_map_omits_navigation_noise_but_keeps_relevant_shared_terms(collection):
    (collection / "Markdown/estudo.md").write_text(
        "# Autorização no servidor\n\nControle de acesso autorização servidor política validação. "
        "figure example what table figura exemplo. Contexto único alfa.\n", encoding="utf-8")
    (collection / "Markdown/segundo.md").write_text(
        "# Autorização no servidor\n\nControle de acesso autorização servidor política validação. "
        "figure example what table figura exemplo. Contexto único beta.\n", encoding="utf-8")
    prepare(collection, lexical=True)
    topics = (collection / "Conhecimento/00-Inicio/Mapa de temas.md").read_text(encoding="utf-8").lower()
    headings = {line[3:].strip() for line in topics.splitlines() if line.startswith("## ")}
    assert headings & {"autorização", "servidor", "controle", "acesso", "política", "validação"}
    assert not headings & {"figure", "example", "what", "table", "figura", "exemplo"}


def test_retry_with_source_scope_retires_archived_legacy_map_after_publish_failure(collection, monkeypatch):
    import knowledge_pipeline

    prepare(collection, lexical=True)
    stable = collection / "Conhecimento/00-Inicio/Mapa geral do acervo.md"
    legacy = stable.with_name("Mapa geral do acervo - abcdef123456.md")
    legacy.write_bytes(stable.read_bytes())
    stable.unlink()
    registry_path = collection / ".dbrain/knowledge/generated-files.json"
    registry = load_json(registry_path)
    registry.pop(stable.relative_to(collection).as_posix(), None)
    registry[legacy.relative_to(collection).as_posix()] = file_hash(legacy)
    save_json(registry_path, registry)
    source = collection / "Markdown/estudo.md"
    source.write_text(source.read_text(encoding="utf-8") + "\nMudança antes da falha de publicação.\n", encoding="utf-8")

    real_update = knowledge_pipeline.update
    calls = 0

    def fail_second_update(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("Falha simulada ao publicar mapas")
        return real_update(*args, **kwargs)

    monkeypatch.setattr(knowledge_pipeline, "update", fail_second_update)
    with pytest.raises(OSError, match="publicar mapas"):
        prepare(collection, paths=["Markdown/estudo.md"], lexical=True)
    assert not legacy.exists()

    monkeypatch.setattr(knowledge_pipeline, "update", real_update)
    prepare(collection, paths=["Markdown/estudo.md"], lexical=True)
    hits = Knowledge(collection).search("Mapa geral do acervo")["results"]
    assert not any("Mapa geral do acervo - abcdef123456.md" in hit["path"] for hit in hits)
    assert not any("history/maps" in hit["path"] for hit in hits)


def test_human_edit_racing_stable_map_capture_is_restored_and_reported(collection, monkeypatch):
    import knowledge_pipeline

    prepare(collection, lexical=True)
    stable = collection / "Conhecimento/00-Inicio/Mapa geral do acervo.md"
    source = collection / "Markdown/estudo.md"
    source.write_text(source.read_text(encoding="utf-8") + "\nMudança que atualiza o mapa.\n", encoding="utf-8")
    real_rename = knowledge_pipeline.os.rename
    captured = {}

    def edit_before_capture(src, dst, *args, **kwargs):
        nonlocal captured
        if Path(src) == stable and not captured:
            stable.write_bytes(stable.read_bytes() + b"\nEDICAO HUMANA DURANTE CAPTURA\n")
            captured["bytes"] = stable.read_bytes()
        return real_rename(src, dst, *args, **kwargs)

    monkeypatch.setattr(knowledge_pipeline.os, "rename", edit_before_capture)
    result = prepare(collection, lexical=True)
    rel = stable.relative_to(collection).as_posix()
    assert captured["bytes"]
    assert stable.is_file() and stable.read_bytes() == captured["bytes"]
    assert rel in result["human_edits_preserved"]


def test_human_edit_racing_legacy_map_capture_is_restored_and_reported(collection, monkeypatch):
    import knowledge_pipeline

    prepare(collection, lexical=True)
    legacy = collection / "Conhecimento/00-Inicio/Mapa geral do acervo - abcdef123456.md"
    stable = collection / "Conhecimento/00-Inicio/Mapa geral do acervo.md"
    legacy.write_bytes(stable.read_bytes())
    stable.unlink()
    registry_path = collection / ".dbrain/knowledge/generated-files.json"
    registry = load_json(registry_path)
    registry.pop(stable.relative_to(collection).as_posix(), None)
    registry[legacy.relative_to(collection).as_posix()] = file_hash(legacy)
    save_json(registry_path, registry)
    real_rename = knowledge_pipeline.os.rename
    captured = {}

    def edit_before_capture(src, dst, *args, **kwargs):
        if Path(src) == legacy and not captured:
            legacy.write_bytes(legacy.read_bytes() + b"\nEDICAO HUMANA DURANTE CAPTURA\n")
            captured["bytes"] = legacy.read_bytes()
        return real_rename(src, dst, *args, **kwargs)

    monkeypatch.setattr(knowledge_pipeline.os, "rename", edit_before_capture)
    result = prepare(collection, lexical=True)
    rel = legacy.relative_to(collection).as_posix()
    assert captured["bytes"]
    assert legacy.is_file() and legacy.read_bytes() == captured["bytes"]
    assert rel in result["human_edits_preserved"]


def test_legacy_map_recreated_after_rename_is_preserved_reported_and_indexed(collection, monkeypatch):
    import yaml
    import knowledge_pipeline

    prepare(collection, lexical=True)
    legacy = collection / "Conhecimento/00-Inicio/Mapa geral do acervo - abcdef123456.md"
    stable = collection / "Conhecimento/00-Inicio/Mapa geral do acervo.md"
    legacy.write_bytes(stable.read_bytes())
    stable.unlink()
    registry_path = collection / ".dbrain/knowledge/generated-files.json"
    registry = load_json(registry_path)
    registry.pop(stable.relative_to(collection).as_posix(), None)
    registry[legacy.relative_to(collection).as_posix()] = file_hash(legacy)
    save_json(registry_path, registry)
    original = legacy.read_bytes()
    human_bytes = original + b"\nEDICAO HUMANA APOS RENAME\n"
    legacy_id = yaml.safe_load(original.decode("utf-8").split("---", 2)[1])["id"]
    real_rename = knowledge_pipeline.os.rename
    recreated = {}

    def recreate_after_capture(src, dst, *args, **kwargs):
        outcome = real_rename(src, dst, *args, **kwargs)
        if Path(src) == legacy and not recreated:
            legacy.write_bytes(human_bytes)
            recreated["done"] = True
        return outcome

    monkeypatch.setattr(knowledge_pipeline.os, "rename", recreate_after_capture)
    result = prepare(collection, lexical=True)
    rel = legacy.relative_to(collection).as_posix()
    assert recreated["done"]
    assert legacy.is_file() and legacy.read_bytes() == human_bytes
    assert rel in result["human_edits_preserved"]
    stable_id = yaml.safe_load(stable.read_text(encoding="utf-8").split("---", 2)[1])["id"]
    assert stable_id != legacy_id
    hits = Knowledge(collection).search("Mapa geral do acervo")["results"]
    hit_paths = {Path(hit["path"]).resolve().relative_to(collection).as_posix() for hit in hits}
    assert rel in hit_paths
    assert stable.relative_to(collection).as_posix() in hit_paths
