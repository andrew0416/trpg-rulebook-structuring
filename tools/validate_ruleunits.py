"""Validate PTK RuleUnits against schema/rule-unit.schema.json without dependencies.
Implements only the keywords used by this contract, rejecting unsupported schema keywords.
This is not a general JSON Schema implementation. Missing references are a separate report.
"""
import json
import re
import sys
from pathlib import Path

KEYWORDS = {"$schema", "$id", "title", "description", "$comment", "type", "required", "properties", "items", "enum", "pattern", "minItems", "maxItems", "minimum", "minLength"}
TYPES = {"object": lambda x: isinstance(x, dict), "array": lambda x: isinstance(x, list), "string": lambda x: isinstance(x, str), "integer": lambda x: type(x) is int, "number": lambda x: type(x) in (int, float), "boolean": lambda x: type(x) is bool, "null": lambda x: x is None}

def check_schema(schema):
    unknown = set(schema) - KEYWORDS
    if unknown:
        raise ValueError(f"Unsupported schema keywords: {sorted(unknown)}")
    for child in schema.get("properties", {}).values():
        check_schema(child)
    if "items" in schema:
        check_schema(schema["items"])

def validate(value, schema, path="$"):
    errors = []
    types = schema.get("type", [])
    types = [types] if isinstance(types, str) else types
    if types and not any(TYPES[t](value) for t in types):
        return [f"{path}: expected {types}, got {type(value).__name__}"]
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: unexpected value {value!r}")
    if isinstance(value, dict):
        errors += [f"{path}.{k}: required" for k in schema.get("required", []) if k not in value]
        for k, child in schema.get("properties", {}).items():
            if k in value:
                errors += validate(value[k], child, f"{path}.{k}")
    elif isinstance(value, list):
        if len(value) < schema.get("minItems", 0) or len(value) > schema.get("maxItems", float("inf")):
            errors.append(f"{path}: invalid array length")
        for i, item in enumerate(value):
            errors += validate(item, schema.get("items", {}), f"{path}[{i}]")
    elif isinstance(value, str):
        if "pattern" in schema and not re.search(schema["pattern"], value):
            errors.append(f"{path}: pattern mismatch")
        if len(value) < schema.get("minLength", 0):
            errors.append(f"{path}: string too short")
    elif type(value) in (int, float) and value < schema.get("minimum", -float("inf")):
        errors.append(f"{path}: below minimum")
    return errors

def validate_rows(rows, schema):
    check_schema(schema)
    errors, seen = [], set()
    for n, row in enumerate(rows, 1):
        errors += validate(row, schema, f"line {n}")
        uid = row.get("id") if isinstance(row, dict) else None
        if isinstance(uid, str):
            if uid in seen:
                errors.append(f"line {n}: duplicate id {uid}")
            seen.add(uid)
        if isinstance(row, dict):
            span = row.get("source", {}).get("lines", []) if isinstance(row.get("source"), dict) else []
            if len(span) == 2 and all(type(x) is int for x in span) and span[0] > span[1]:
                errors.append(f"line {n}: reversed source lines")
    return errors

def main(root):
    root = Path(root)
    schema = json.loads((root / "schema/rule-unit.schema.json").read_text(encoding="utf-8"))
    rows = [json.loads(line) for line in (root / "output/ruleunits.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    errors = validate_rows(rows, schema)
    text = f"# PTK RuleUnit schema validation\n\nRecords: {len(rows)}; errors: {len(errors)}\n\n" + "\n".join("- " + e for e in errors)
    (root / "output/schema-validation.md").write_text(text + "\n", encoding="utf-8")
    print(text[:6000])
    return not errors

if __name__ == "__main__":
    sys.exit(0 if main(sys.argv[1] if len(sys.argv) > 1 else ".") else 1)
