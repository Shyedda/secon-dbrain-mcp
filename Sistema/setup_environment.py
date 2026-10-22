"""Create an isolated Python environment without touching knowledge or indexes."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

CODE_ROOT = Path(__file__).resolve().parent.parent


def inspect_python(executable):
    code = "import json,sys; print(json.dumps({'version':list(sys.version_info[:3]),'base':sys.base_prefix,'executable':sys.executable}))"
    result = subprocess.run([str(executable), "-c", code], check=True, capture_output=True, text=True)
    value = json.loads(result.stdout)
    if value["version"][:2] != [3, 12]:
        raise ValueError("Use Python 3.12 independente; informe --python CAMINHO")
    if "codex-runtimes" in value["base"].lower():
        raise ValueError("Python do cache do Codex não é independente. Instale Python 3.12 ou use uv python install 3.12 e informe --python.")
    return value


def setup(python, root=CODE_ROOT, venv_name=".venv", install=True):
    root = Path(root).resolve()
    target = (root / venv_name).resolve()
    if not target.is_relative_to(root) or target == root:
        raise ValueError("O ambiente deve estar dentro da pasta do projeto")
    runtime = inspect_python(python)
    if target.exists():
        raise FileExistsError(f"Ambiente já existe: {target}. Preserve-o e escolha --venv outro-nome; não será sobrescrito.")
    subprocess.run([str(python), "-m", "venv", str(target)], check=True)
    executable = target / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if install:
        subprocess.run([str(executable), "-m", "pip", "install", "-r", str(CODE_ROOT / "Sistema/requirements-lock.txt")], check=True)
        subprocess.run([str(executable), "-m", "pip", "check"], check=True)
    return {"python": str(executable), "base": runtime["base"], "version": runtime["version"], "system_site_packages": False, "installed": install}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--venv", default=".venv")
    args = parser.parse_args()
    print(json.dumps(setup(args.python, venv_name=args.venv), ensure_ascii=False, indent=2))
