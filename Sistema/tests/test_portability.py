"""Portable library paths; all sources are generated in temporary directories."""
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import config, eligible, note_dirs, save_json, schema
from dbrain import new_note
from indexer import update
from retrieval import Knowledge
from setup_environment import inspect_python


@pytest.fixture
def portable(tmp_path):
    root = tmp_path / "Coleção independente com espaços"
    system = Path(__file__).resolve().parents[1]
    cfg = json.loads((system / "config.json").read_text(encoding="utf-8"))
    cfg.update(include=["Documentos", "Notas"], pdf_roots=["Documentos"],
               note_dirs={kind: "Notas" for kind in note_dirs(system.parent)},
               catalog_dir="Notas/Fontes", lexical_expansions={})
    save_json(root / "Sistema/config.json", cfg)
    save_json(root / "Sistema/schema.json", schema(system.parent))
    (root / "90-Templates").mkdir()
    (root / "90-Templates/concept.md").write_text((system.parent / "90-Templates/concept.md").read_text(encoding="utf-8"), encoding="utf-8")
    (root / "Documentos").mkdir()
    (root / "Notas").mkdir()
    return root


def test_configured_folders_and_note_identity(portable):
    cfg = config(portable)
    assert eligible(portable, portable / "Documentos/manual.pdf", cfg)
    assert not eligible(portable, portable / "Documentos/segredo.md", cfg)
    assert not eligible(portable, portable / "Notas/AGENTS.md", cfg)
    result = new_note(portable, "concept", "Conhecimento de demonstração", by="other-agent")
    path = Path(result["created"])
    original = path.read_bytes()
    assert path.parent == portable / "Notas"
    first = update(portable, lexical=True)
    second = update(portable, lexical=True)
    assert first["documents"] == 1
    assert second["new_embeddings"] == second["content_reads"] == 0
    assert path.read_bytes() == original


def test_configuration_cannot_create_notes_outside_library(portable):
    cfg = config(portable)
    cfg["note_dirs"] = {"concept": "../escape"}
    save_json(portable / "Sistema/config.json", cfg)
    with pytest.raises(ValueError, match="fora"):
        new_note(portable, "concept", "Não criar fora", by="human")


def test_cli_root_is_honored_from_other_directory(portable, tmp_path):
    script = Path(__file__).resolve().parents[1] / "dbrain.py"
    result = subprocess.run([sys.executable, str(script), "--root", str(portable), "status"], cwd=tmp_path, capture_output=True, text=True, check=True)
    assert json.loads(result.stdout)["indexed"] is False


def test_mcp_reads_only_the_selected_library(portable, tmp_path):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    text = "# Demonstração\n\nMARCADOR_COLECAO_ISOLADA descreve uma fonte sintética."
    (portable / "Notas/fonte.md").write_text(text, encoding="utf-8")
    update(portable, lexical=True)

    def data(result):
        assert not result.isError
        return result.structuredContent or json.loads(result.content[0].text)

    async def verify():
        script = Path(__file__).resolve().parents[1] / "mcp_server.py"
        params = StdioServerParameters(command=sys.executable, args=[str(script), "--root", str(portable)], cwd=str(tmp_path), env={**os.environ, "HF_HUB_OFFLINE": "1"})
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                assert sorted(t.name for t in tools.tools) == ["knowledge_status", "read_knowledge", "search_knowledge"]
                status = data(await session.call_tool("knowledge_status", {}))
                assert status["documents"] == 1
                answer = data(await session.call_tool("search_knowledge", {"query": "MARCADOR_COLECAO_ISOLADA"}))
                hit = answer["results"][0]
                result = data(await session.call_tool("read_knowledge", {"source_id": hit["source_id"], "locator": hit["locator"]}))
                assert "MARCADOR_COLECAO_ISOLADA" in result["text"]
    asyncio.run(asyncio.wait_for(verify(), timeout=30))


def test_setup_rejects_codex_cache(monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: SimpleNamespace(stdout=json.dumps({"version": [3, 12, 14], "base": "C:/cache/codex-runtimes/python", "executable": "python"})))
    with pytest.raises(ValueError, match="Codex"):
        inspect_python("python")
