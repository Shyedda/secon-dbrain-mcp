"""Compatibility wrapper: the integration for every agent lives in install_agents.py."""
import argparse
import json
from install_agents import install

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--allow-writes", action="store_true")
    args = parser.parse_args()
    print(json.dumps(install(["codex"], args.apply, allow_writes=args.allow_writes), ensure_ascii=False, indent=2))
