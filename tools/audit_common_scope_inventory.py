"""Check draft source-review integrity without claiming a semantic denominator."""
import hashlib
import json
from collections import Counter
from pathlib import Path
import audit_common_source_inventory as PHYSICAL

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = "data/verification/common-source-inventory.json"
GRAPH = "data/verification/rule-symbol-graph.json"
REVIEW_DIR = "data/verification/common-source-reviews"
CLASSES = {"common_normative", "domain_normative", "content_instance", "example", "guidance", "structural", "mixed", "unresolved_visual"}
NORMATIVE = {"common_normative", "domain_normative", "mixed"}
ATOMICITY = {"statement_group", "atomic_candidate"}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def strings(value, nonempty=False):
    return isinstance(value, list) and (bool(value) or not nonempty) and all(isinstance(x, str) and x.strip() for x in value)


def validate(inventory, reviews, graph, root):
    root = Path(root)
    errors = []
    try:
        errors.extend(PHYSICAL.validate(inventory, root))
        actual = PHYSICAL.build(root)
        expected = {b["id"]: b for b in actual["blocks"]}
        for b in inventory["blocks"]:
            # Preserve exact physical partition/flags, including heading bodies.
            current = expected.get(b["id"])
            fields = ("file", "start", "end", "kind", "excerpt_sha256", "flags")
            if current is None or any(b.get(k) != current[k] for k in fields):
                errors.append("physical_block_mismatch:" + str(b.get("id")))
    except (KeyError, TypeError, ValueError, OSError) as exc:
        errors.append("invalid_physical_inventory:" + type(exc).__name__)
        return errors
    if inventory.get("source_clause_total") is not None or inventory.get("semantic_coverage_percent") is not None:
        errors.append("unsupported_physical_semantic_denominator")
    if not isinstance(reviews, list):
        return errors + ["invalid_review_collection"]
    try:
        symbols = [n["id"] for n in graph["nodes"]]
        if len(set(symbols)) != len(symbols):
            errors.append("duplicate_graph_symbol")
        symbols = set(symbols)
    except (KeyError, TypeError):
        return errors + ["invalid_symbol_graph"]
    files = {f["file"]: f for f in inventory["files"]}
    physical = {b["id"]: b for b in inventory["blocks"]}
    seen_files, seen_clause_ids = set(), set()
    for review in reviews:
        if not isinstance(review, dict):
            errors.append("invalid_review_object")
            continue
        file = review.get("file")
        label = str(file)
        if not isinstance(file, str) or file not in files:
            errors.append("unknown_review_file:" + label)
            continue
        if file in seen_files:
            errors.append("duplicate_review_file:" + file)
        seen_files.add(file)
        if not file.endswith(".md"):
            errors.append("unsupported_review_format:" + file)
        if review.get("source_sha256") != files[file]["sha256"]:
            errors.append("stale_review_source:" + file)
        if review.get("whole_source_complete") is not False:
            errors.append("unsupported_source_completion:" + file)
        if not review.get("review_scope"):
            errors.append("missing_review_scope:" + file)
        if not strings(review.get("remaining")):
            errors.append("invalid_review_remaining:" + file)
        blocks, clauses = review.get("blocks"), review.get("clauses")
        if not isinstance(blocks, list) or not isinstance(clauses, list):
            errors.append("invalid_review_rows:" + file)
            continue
        block_ids = [b.get("block_id") for b in blocks if isinstance(b, dict)]
        clause_ids = [c.get("id") for c in clauses if isinstance(c, dict)]
        if len(block_ids) != len(blocks) or any(not isinstance(x, str) for x in block_ids):
            errors.append("invalid_review_block_id:" + file)
            continue
        if len(clause_ids) != len(clauses) or any(not isinstance(x, str) or not x.strip() for x in clause_ids):
            errors.append("invalid_clause_id:" + file)
            continue
        if len(block_ids) != len(set(block_ids)):
            errors.append("duplicate_review_block:" + file)
        required = {b["id"] for b in inventory["blocks"] if b["file"] == file}
        if set(block_ids) != required:
            errors.append("review_block_partition_mismatch:" + file)
        if len(clause_ids) != len(set(clause_ids)) or seen_clause_ids.intersection(clause_ids):
            errors.append("duplicate_clause_id:" + file)
        seen_clause_ids.update(clause_ids)
        block_map, clause_map = {b["block_id"]:b for b in blocks}, {c["id"]:c for c in clauses}
        for b in blocks:
            bid = b["block_id"]
            if bid not in required:
                errors.append("unknown_review_block:" + bid)
            if b.get("classification") not in CLASSES:
                errors.append("invalid_block_classification:" + bid)
            if not isinstance(b.get("reason"), str) or not b["reason"].strip():
                errors.append("missing_block_reason:" + bid)
            if not strings(b.get("unresolved")):
                errors.append("invalid_block_unresolved:" + bid)
            image = "image_candidate" in physical.get(bid, {}).get("flags", [])
            if (image or b.get("classification") == "unresolved_visual") and not b.get("unresolved"):
                errors.append("unresolved_visual_erased:" + bid)
            links = b.get("clause_ids")
            if not strings(links):
                errors.append("invalid_block_clause_links:" + bid)
                continue
            if len(links) != len(set(links)):
                errors.append("duplicate_block_clause_link:" + bid)
            if b.get("classification") in NORMATIVE and not links:
                errors.append("normative_block_without_clause:" + bid)
            for cid in links:
                if cid not in clause_map:
                    errors.append("unknown_clause_link:" + bid + ":" + cid)
                elif bid not in clause_map[cid].get("block_ids", []):
                    errors.append("missing_clause_backlink:" + bid + ":" + cid)
        for c in clauses:
            cid = c["id"]
            if c.get("status") != "draft":
                errors.append("unsupported_clause_status:" + cid)
            if c.get("atomicity") not in ATOMICITY:
                errors.append("invalid_clause_atomicity:" + cid)
            if not isinstance(c.get("statement"), str) or not c["statement"].strip():
                errors.append("missing_clause_statement:" + cid)
            for key in ("conditions", "exceptions", "remaining"):
                if not strings(c.get(key)):
                    errors.append("invalid_clause_" + key + ":" + cid)
            refs = c.get("symbol_refs")
            if not strings(refs, True) or not set(refs or []) <= symbols:
                errors.append("unknown_or_empty_clause_symbols:" + cid)
            links = c.get("block_ids")
            if not strings(links, True):
                errors.append("invalid_clause_block_links:" + cid)
                continue
            if len(links) != len(set(links)):
                errors.append("duplicate_clause_block_link:" + cid)
            for bid in links:
                if bid not in block_map:
                    errors.append("unknown_clause_block:" + cid + ":" + bid)
                elif cid not in block_map[bid].get("clause_ids", []):
                    errors.append("missing_block_backlink:" + cid + ":" + bid)
    return errors


def summarize(inventory, reviews, errors=()):
    known_files = {f["file"] for f in inventory["files"]}
    known_blocks = {b["id"] for b in inventory["blocks"]}
    review_files = {r.get("file") for r in reviews if isinstance(r, dict)} & known_files
    reviewed_blocks = {b.get("block_id") for r in reviews if isinstance(r, dict)
                       for b in r.get("blocks", []) if isinstance(b, dict)} & known_blocks
    rows = []
    for r in reviews:
        if not isinstance(r, dict):
            continue
        counts = Counter(b.get("classification", "invalid") for b in r.get("blocks", []) if isinstance(b, dict))
        rows.append(dict(file=r.get("file"), classified_blocks=sum(counts.values()),
                         classifications=dict(counts), candidate_clauses=len(r.get("clauses", [])),
                         unresolved_blocks=sum(bool(b.get("unresolved")) for b in r.get("blocks", []) if isinstance(b, dict)),
                         whole_source_complete=False))
    totals = Counter()
    atomicity = Counter(c.get("atomicity", "invalid") for r in reviews if isinstance(r, dict) for c in r.get("clauses", []) if isinstance(c, dict))
    markdown_files = {f["file"] for f in inventory["files"] if f["file"].endswith(".md")}
    for r in rows:
        totals.update(r["classifications"])
    return dict(status="draft_integrity_pass" if not errors else "invalid", errors=list(errors),
                source_files=len(known_files), source_blocks=len(known_blocks),
                reviewed_files=len(review_files), reviewed_blocks=len(reviewed_blocks),
                unreviewed_files=len(known_files-review_files), unreviewed_blocks=len(known_blocks-reviewed_blocks),
                unreviewed_file_paths=sorted(known_files-review_files),
                markdown_files=len(markdown_files), reviewed_markdown_files=len(review_files & markdown_files),
                unreviewed_markdown_files=len(markdown_files-review_files),
                nonmarkdown_files=len(known_files-markdown_files), candidate_atomicity=dict(atomicity),
                saved_markdown_partition_complete=bool(markdown_files) and not errors and markdown_files <= review_files and known_blocks <= reviewed_blocks,
                partition_meaning="Every saved Markdown block has a draft classification; no atomic denominator, original fidelity or semantic certification follows.",
                classifications=dict(totals), candidate_clauses=sum(r["candidate_clauses"] for r in rows),
                files=rows, common_clause_total=None, semantic_coverage_percent=None,
                whole_source_complete=False, whole_rule_certified=False,
                meaning="Reviewed counts mean draft classifications, not certified clauses; groups and candidates are not a rule denominator.")


def audit(root=ROOT):
    root = Path(root)
    inventory = json.loads((root / INVENTORY).read_text(encoding="utf-8"))
    graph = json.loads((root / GRAPH).read_text(encoding="utf-8"))
    review_paths = sorted((root / REVIEW_DIR).glob("*.json"))
    reviews, parse_errors = [], []
    for path in review_paths:
        try:
            reviews.append(json.loads(path.read_text(encoding="utf-8")))
        except (ValueError, OSError) as exc:
            parse_errors.append("unreadable_review:" + path.name + ":" + type(exc).__name__)
    errors = parse_errors + validate(inventory, reviews, graph, root)
    report = summarize(inventory, reviews, errors)
    # Top-down navigation to evidence only: a link is not semantic discharge.
    by_symbol = {}
    for review in reviews:
        if not isinstance(review, dict):
            continue
        for clause in review.get("clauses", []):
            if not isinstance(clause, dict):
                continue
            refs = clause.get("symbol_refs", [])
            if not strings(refs):
                continue
            for symbol in refs:
                by_symbol.setdefault(symbol, []).append(dict(
                    clause_id=clause.get("id"), source_file=review.get("file"),
                    block_ids=clause.get("block_ids", []), atomicity=clause.get("atomicity"), status="draft"))
    report["symbol_candidate_index"] = by_symbol
    report["symbol_candidate_index_meaning"] = "Navigation links from existing symbols to source candidates; no symbol is certified by these links."
    inputs = [root / INVENTORY, root / GRAPH, root / "tools/audit_common_scope_inventory.py",
              root / "tools/audit_common_source_inventory.py", *review_paths,
              *sorted(p for p in (root / "input").rglob("*") if p.is_file())]
    report["input_hashes"] = {p.relative_to(root).as_posix(): sha(p) for p in inputs}
    report["results"] = [dict(id="COMMON-SCOPE-integrity", status="pass" if not errors else "fail")]
    return report


if __name__ == "__main__":
    report = audit()
    dest = ROOT / "output/whole-rulebook-audit/common-scope-inventory.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k not in ("input_hashes", "unreviewed_file_paths", "files", "symbol_candidate_index")}, ensure_ascii=False))
    raise SystemExit(bool(report["errors"]))
