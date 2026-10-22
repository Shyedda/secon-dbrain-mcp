import json
import sys
from pathlib import Path

import tomlkit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import install_agents


def make_vault(tmp_path, *, integration=None):
    root = tmp_path / "Library with spaces"
    (root / "Sistema").mkdir(parents=True)
    config = {"integration": integration or {}}
    (root / "Sistema" / "config.json").write_text(json.dumps(config), encoding="utf-8")
    return root


def test_generic_emits_portable_stdio_json_and_honors_overrides(tmp_path):
    root = make_vault(tmp_path, integration={"mcp_name": "research_library"})
    python = tmp_path / "Python Runtime" / "python.exe"
    actual = install_agents.generic(root, python)

    assert actual == {
        "mcpServers": {
            "research_library": {
                "command": str(python.resolve()),
                "args": ["-X", "utf8", str((Path(install_agents.__file__).parent / "mcp_server.py").resolve()), "--root", str(root.resolve())],
                "env": install_agents.ENV,
            }
        }
    }
    assert json.loads(json.dumps(actual)) == actual


def test_external_library_uses_the_code_environment(tmp_path, monkeypatch):
    root = make_vault(tmp_path)
    selected = []
    def interpreter(path):
        selected.append(path)
        return Path(sys.executable)
    monkeypatch.setattr(install_agents, "python_executable", interpreter)
    install_agents.generic(root)
    assert selected == [install_agents.CODE_ROOT]


def test_skill_renders_library_path_and_agent_without_private_policy(tmp_path):
    root = make_vault(tmp_path, integration={"mcp_name": "research_library"})
    distribution = root / "Sistema" / "distribution"
    distribution.mkdir()
    (distribution / "skill.md").write_text("Vault={{root}} Agent={{agent}} MCP={{mcp_name}}", encoding="utf-8")

    assert install_agents._skill_text("generic-agent", root) == f"Vault={root.resolve()} Agent=generic-agent MCP=research_library"
    assert "github.com/Shyedda" not in install_agents._skill_text("generic-agent", root)


def test_codex_merge_is_idempotent_and_preserves_unrelated_settings(tmp_path, monkeypatch):
    root = make_vault(tmp_path, integration={"instructions_extra": "Local integration policy."})
    home = tmp_path / "Codex Home"
    home.mkdir()
    settings = home / "config.toml"
    settings.write_text('model = "gpt-test"\nmodel_reasoning_effort = "high"\n\n[mcp_servers.other]\ncommand = "other"\nargs = []\n', encoding="utf-8")
    monkeypatch.setenv("CODEX_HOME", str(home))
    monkeypatch.setattr(install_agents, "python_executable", lambda vault: Path("C:/Tools/Python/python.exe"))

    first = install_agents.codex(apply=True, root=root)
    snapshot = settings.read_text(encoding="utf-8")
    second = install_agents.codex(apply=True, root=root)

    parsed = tomlkit.parse(settings.read_text(encoding="utf-8"))
    assert parsed["model"] == "gpt-test"
    assert parsed["model_reasoning_effort"] == "high"
    assert parsed["mcp_servers"]["other"]["command"] == "other"
    assert parsed["mcp_servers"]["secon_dbrain"]["args"][-2:] == ["--root", str(root.resolve())]
    assert "Local integration policy." in (home / "AGENTS.md").read_text(encoding="utf-8")
    assert snapshot == settings.read_text(encoding="utf-8")
    assert first["apply"] and second["apply"]


def test_codex_refuses_name_collision_with_another_library(tmp_path, monkeypatch):
    root = make_vault(tmp_path)
    home = tmp_path / "Another Codex Home"
    home.mkdir()
    settings = home / "config.toml"
    settings.write_text('[mcp_servers.secon_dbrain]\ncommand = "python"\nargs = ["mcp_server.py", "--root", "C:/Somewhere Else"]\n', encoding="utf-8")
    before = settings.read_text(encoding="utf-8")
    monkeypatch.setenv("CODEX_HOME", str(home))
    monkeypatch.setattr(install_agents, "python_executable", lambda vault: Path("C:/Tools/Python/python.exe"))

    try:
        install_agents.codex(root=root)
    except RuntimeError as exc:
        assert "outro comando ou biblioteca" in str(exc)
    else:
        raise AssertionError("A colisão com outra biblioteca deveria ser recusada")
    assert settings.read_text(encoding="utf-8") == before


def test_codex_allows_python_change_only_for_same_explicit_library(tmp_path, monkeypatch):
    root = make_vault(tmp_path)
    monkeypatch.setattr(install_agents, "python_executable", lambda vault: Path("C:/Tools/New Python/python.exe"))
    _, desired = install_agents._mcp(root)
    legacy_python = str(Path("C:/Tools/Old Python/python.exe").resolve())
    current = {"command": legacy_python, "args": desired["args"]}
    elsewhere = {"command": legacy_python, "args": desired["args"][:-1] + [str(tmp_path / "Elsewhere")]}

    assert install_agents._codex_server_matches(current, desired, root.resolve())
    assert not install_agents._codex_server_matches(elsewhere, desired, root.resolve())


def test_codex_upgrades_legacy_canonical_registration(tmp_path, monkeypatch):
    root = make_vault(tmp_path)
    monkeypatch.setattr(install_agents, "ROOT", root.resolve())
    home = tmp_path / "Legacy Codex Home"
    home.mkdir()
    settings = home / "config.toml"
    command = str(Path("C:/Tools/Python/python.exe").resolve())
    command_toml = command.replace("\\", "\\\\")
    server = str((Path(install_agents.__file__).parent / "mcp_server.py").resolve())
    server_toml = server.replace("\\", "\\\\")
    settings.write_text(
        f'[mcp_servers.secon_dbrain]\ncommand = "{command_toml}"\nargs = ["-X", "utf8", "{server_toml}"]\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("CODEX_HOME", str(home))
    monkeypatch.setattr(install_agents, "python_executable", lambda vault: Path(command))

    install_agents.codex(apply=True, root=root)

    parsed = tomlkit.parse(settings.read_text(encoding="utf-8"))
    assert parsed["mcp_servers"]["secon_dbrain"]["args"][-2:] == ["--root", str(root.resolve())]


def test_skill_render_failure_does_not_change_codex_config(tmp_path, monkeypatch):
    root = make_vault(tmp_path, integration={"skill": "Sistema/distribution/missing.md"})
    home = tmp_path / "Codex Home with broken skill"
    home.mkdir()
    settings = home / "config.toml"
    settings.write_text('model = "keep-me"\n', encoding="utf-8")
    before = settings.read_text(encoding="utf-8")
    monkeypatch.setenv("CODEX_HOME", str(home))
    monkeypatch.setattr(install_agents, "python_executable", lambda vault: Path("C:/Tools/Python/python.exe"))

    try:
        install_agents.codex(apply=True, root=root)
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("A skill ausente deveria interromper a instalação")

    assert settings.read_text(encoding="utf-8") == before
    assert not (home / "AGENTS.md").exists()
    assert not (home / "skills" / "secon-dbrain" / "SKILL.md").exists()


def test_instructions_block_from_another_root_is_not_replaced(tmp_path):
    root = make_vault(tmp_path)
    another = tmp_path / "Different Library"
    (another / "Sistema").mkdir(parents=True)
    (another / "Sistema" / "config.json").write_text('{"integration": {}}', encoding="utf-8")
    path = tmp_path / "AGENTS.md"
    path.write_text(install_agents.instruction("codex", another), encoding="utf-8")
    before = path.read_text(encoding="utf-8")

    try:
        install_agents._merge_block(path, "codex", root)
    except RuntimeError as exc:
        assert "pertence a outra biblioteca" in str(exc)
    else:
        raise AssertionError("Um bloco vinculado a outra raiz deveria ser preservado")
    assert path.read_text(encoding="utf-8") == before
