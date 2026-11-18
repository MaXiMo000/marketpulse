"""Validate render.yaml against Render's published Blueprint schema (the one editors get from SchemaStore)."""
import json
import sys
import urllib.request

import yaml
from jsonschema import validators

SCHEMA_URL = "https://render.com/schema/render.yaml.json"


def main(path: str = "render.yaml") -> int:
    with urllib.request.urlopen(SCHEMA_URL, timeout=30) as resp:
        schema = json.load(resp)
    with open(path, encoding="utf-8") as f:
        doc = yaml.safe_load(f)
    errors = sorted(validators.validator_for(schema)(schema).iter_errors(doc), key=lambda e: list(e.path))
    for e in errors:
        print(f"{'/'.join(map(str, e.path))}: {e.message}")
    print(f"{path}: {len(errors)} schema error(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
