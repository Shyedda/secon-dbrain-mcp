"""Portable library paths; all sources are generated in temporary directories."""
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import NOTE_DIRS, config, eligible, file_hash, note_dirs, save_json, schema
from dbrain import new_note
from indexer import update
from retrieval import Knowledge
from setup_environment import inspect_python


@pytest.fixture
def portable(tmp_path):
    root = tmp_path / "Coleção independente com espaços"
    system = Path(__file__).resolve().parents[1]
    cfg = json.loads((system / "config.json").read_text(encoding="utf-8"))
    cfg.update(include=["Documentos", "Notas"], pdf_roots=["Documentos"], template_dir="90-Templates",
               note_dirs={kind: "Notas" for kind in note_dirs(system.parent)},
               catalog_dir="Notas/Fontes", lexical_expansions={})
    save_json(root / "Sistema/config.json", cfg)
    save_json(root / "Sistema/schema.json", schema(system.parent))
    (root / "90-Templates").mkdir()
    (root / "90-Templates/concept.md").write_text((system.parent / config(system.parent).get("template_dir", "90-Templates") / "concept.md").read_text(encoding="utf-8"), encoding="utf-8")
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
                assert sorted(t.name for t in tools.tools) == ["knowledge_overview", "knowledge_status", "read_enrichment_task", "read_knowledge", "search_knowledge"]
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


def test_structured_library_indexes_pdfs_and_markdown_without_its_guides(portable):
    """The shipped layout works with real PDFs and plain Markdown, without editing either."""
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    folders = ["00-Inicio", "10-Fontes", "20-Notas", "30-Procedimentos", "40-Experimentos", "Livros", "Documentos", "Markdown"]
    cfg = config(portable)
    cfg.update(include=[*folders, "Notas"], pdf_roots=["Livros", "Documentos"], note_dirs=NOTE_DIRS.copy())
    save_json(portable / "Sistema/config.json", cfg)
    originals = {}
    for index, folder in enumerate(folders):
        directory = portable / folder
        directory.mkdir(exist_ok=True)
        (directory / "README.md").write_text('---\nrag_exclude: true\n---\n# GUIDE_EXCLUDED_MARKER\n', encoding="utf-8")
        if folder in cfg["pdf_roots"]:
            path = directory / "synthetic.pdf"
            writer = PdfWriter()
            page = writer.add_blank_page(width=400, height=300)
            font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
            page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): font})})
            stream = DecodedStreamObject()
            stream.set_data(f'BT /F1 12 Tf 40 220 Td (PUBLIC_PDF_MARKER_{index} describes a synthetic manual for testing.) Tj ET'.encode())
            page[NameObject('/Contents')] = writer._add_object(stream)
            with path.open('wb') as output:
                writer.write(output)
            # Markdown inside a PDF root is deliberately not a source.
            (directory / "wrong-format.md").write_text('WRONG_LOCATION_MARKER', encoding="utf-8")
        else:
            path = directory / "ação.md"
            path.write_text(f'# Synthetic section\n\nPUBLIC_MD_MARKER_{index} is a reference written for testing.\n', encoding="utf-8")
        originals[path] = file_hash(path)
    # Existing clones can keep their old notes without moving them.
    legacy = portable / 'Notas/legacy.md'
    legacy.write_text('# Legacy section\n\nLEGACY_NOTE_MARKER remains queryable.\n', encoding='utf-8')
    originals[legacy] = file_hash(legacy)
    for folder in ('Anexos', '90-Templates', 'Sistema'):
        (portable / folder).mkdir(exist_ok=True)
        (portable / folder / 'not-knowledge.md').write_text('OUT_OF_SCOPE_MARKER', encoding='utf-8')
    assert eligible(portable, portable / 'Livros/synthetic.pdf', cfg)
    assert eligible(portable, portable / 'Documentos/synthetic.pdf', cfg)
    assert eligible(portable, portable / 'Markdown/ação.md', cfg)
    assert not eligible(portable, portable / 'Markdown/ignored.pdf', cfg)
    result = update(portable, lexical=True)
    assert result['documents'] == len(originals)
    knowledge = Knowledge(portable)
    assert knowledge.status()['pdf_files'] == 2
    assert not knowledge.search('GUIDE_EXCLUDED_MARKER')['results']
    assert not knowledge.search('WRONG_LOCATION_MARKER')['results']
    assert not knowledge.search('OUT_OF_SCOPE_MARKER')['results']
    for index, folder in enumerate(folders):
        marker = f'PUBLIC_PDF_MARKER_{index}' if folder in cfg['pdf_roots'] else f'PUBLIC_MD_MARKER_{index}'
        hit = knowledge.search(marker)['results'][0]
        assert hit['all_paths'] == [f'{folder}/synthetic.pdf' if folder in cfg['pdf_roots'] else f'{folder}/ação.md']
        reading = knowledge.read(hit['source_id'], hit['locator'])
        assert marker in reading['text']
        if folder in cfg['pdf_roots']:
            assert reading['locator']['pdf_page'] == 1
    assert knowledge.search('LEGACY_NOTE_MARKER')['results']
    noop = update(portable, lexical=True)
    assert noop['content_reads'] == noop['new_embeddings'] == 0
    assert {path: file_hash(path) for path in originals} == originals


@pytest.mark.parametrize('kind,folder', NOTE_DIRS.items())
def test_structured_library_creates_notes_in_the_matching_folder(portable, kind, folder):
    system = Path(__file__).resolve().parents[1]
    source = system / 'distribution/templates' / (kind + '.md')
    if not source.exists():
        source = system.parent / config(system.parent).get('template_dir', '90-Templates') / (kind + '.md')
    (portable / '90-Templates' / (kind + '.md')).write_text(source.read_text(encoding='utf-8'), encoding='utf-8')
    cfg = config(portable)
    cfg['note_dirs'] = NOTE_DIRS.copy()
    save_json(portable / 'Sistema/config.json', cfg)
    created = new_note(portable, kind, f'Synthetic {kind}', by='human')
    assert Path(created['created']).parent == portable / folder
