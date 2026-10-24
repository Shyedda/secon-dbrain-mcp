"""Public defaults must not inherit a maintainer's personal collection profile."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from retrieval import EXPANSIONS


def defaults():
    system = Path(__file__).resolve().parents[1]
    baseline = system / "distribution" if (system / "distribution").is_dir() else system
    return baseline, json.loads((baseline / "schema.json").read_text(encoding="utf-8")), json.loads((baseline / "config.json").read_text(encoding="utf-8"))


def test_public_schema_starts_with_general_purpose_fields_only():
    baseline, schema, _ = defaults()
    assert schema["areas"] == {"geral": "Geral"}
    assert schema["created_by"] == ["human", "agent", "import"]
    assert set(schema["list_fields"]) == {"areas", "aliases", "sources", "tags", "stack"}
    assert set(schema["patterns"]) == {"stack"}
    assert set(schema["filters"]) == {"areas", "type", "language", "status", "source_id", "created_by", "stack", "tags"}
    assert not (baseline / "profiles/security/schema.json").exists()


def test_public_configuration_has_no_personal_overrides_or_domain_expansions():
    _, _, config = defaults()
    assert config["lexical_expansions"] == EXPANSIONS == {}
    assert "instructions_extra" not in config["integration"]
    assert config["ocr"]["pages"] == {}
