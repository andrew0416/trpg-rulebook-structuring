"""Assign sheet item IDs before mechanization, matching existing export IDs."""
import json
from pathlib import Path

def sheet_items(root):
    root = Path(root)
    used = set()
    for name in ("item", "crafted_item"):
        for row in json.loads((root / f"output/entities/{name}.json").read_text(encoding="utf-8")):
            uid = row["id"]
            if uid in used:
                uid += "-" + str(sum(k.startswith(uid) for k in used))
            used.add(uid)
    rows = json.loads((root / "output/entities/items_sheet.json").read_text(encoding="utf-8"))
    first = {}
    result = []
    for row in rows:
        row = dict(row)
        uid = row["id"]
        initial = first.setdefault(uid, row)
        if uid in used:
            row["id"] = uid + "-" + str(sum(k.startswith(uid) for k in used))
            row["_source_id"] = uid
            row["_same_source_effect"] = row.get("desc") == initial.get("desc")
        used.add(row["id"])
        result.append(row)
    return result
