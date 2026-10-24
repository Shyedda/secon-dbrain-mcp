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
