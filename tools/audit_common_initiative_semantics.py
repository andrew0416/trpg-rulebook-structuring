"""Supporting initiative spec integrity; no whole semantic certification."""
import argparse
import hashlib
import json
from pathlib import Path

STATUSES = {"INIT-01": "source_resolved_local", "INIT-02": "source_resolved_local",
            "INIT-03": "source_resolved_local", "INIT-04": "explicit_gm_policy",
            "INIT-05": "explicit_gm_policy", "INIT-06": "pending_source_interpretation",
            "INIT-07": "pending_runtime_integration", "INIT-08": "implementation_boundary"}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate(spec, root):
    root = Path(root).resolve(); errors = []
    if not isinstance(spec, dict): return ["spec must be object"]
    for field in ("whole_semantic_complete", "implementation_conformance_proved", "semantic_coverage_proved"):
        if spec.get(field) is not False: errors.append(field + " must be false")
    if spec.get("root_contract") != "time.order": errors.append("root_contract must be time.order")
    if spec.get("kind") != "source_grounded_supporting_spec": errors.append("kind must identify supporting spec")
    nodes = {x["id"] for x in json.loads((root / "data/verification/rule-symbol-graph.json").read_text(encoding="utf-8"))["nodes"]}
    refs = spec.get("symbol_refs", [])
    if not refs or any(ref not in nodes for ref in refs): errors.append("invalid symbol refs")
    anchors = {}
    for a in spec.get("source_anchors", []):
        uid = a.get("id")
        if uid in anchors: errors.append("duplicate anchor " + str(uid))
        anchors[uid] = a
        try:
            name = a["file"]; path = (root / name).resolve()
            if Path(name).is_absolute() or not path.is_relative_to(root): raise ValueError("source path")
            if sha(path) != a["source_sha256"]: errors.append("stale source " + str(uid))
            ls = path.read_text(encoding="utf-8").splitlines(); start, end = a["start"], a["end"]
            if type(start) is not int or type(end) is not int or not 1 <= start <= end <= len(ls): raise ValueError("line range")
            excerpt = "\n".join(ls[start - 1:end])
            if excerpt != a["excerpt"]: errors.append("excerpt mismatch " + str(uid))
            if hashlib.sha256(excerpt.encode()).hexdigest() != a["excerpt_sha256"]: errors.append("excerpt hash mismatch " + str(uid))
        except (KeyError, ValueError, TypeError, OSError) as exc: errors.append("invalid anchor " + str(uid) + ": " + str(exc))
    if set(anchors) != {f"INIT-A{i:02d}" for i in range(1, 7)}: errors.append("anchor set mismatch")
    clauses = {}
    test_path = root / "tools/test_common_initiative.py"
    test_text = test_path.read_text(encoding="utf-8")
    for c in spec.get("clauses", []):
        uid = c.get("id")
        if uid in clauses: errors.append("duplicate clause " + str(uid))
        clauses[uid] = c
        if c.get("status") != STATUSES.get(uid): errors.append("wrong clause status " + str(uid))
        for field in ("statement", "formal_relation"):
            if not isinstance(c.get(field), str) or not c[field].strip(): errors.append("missing " + field + " " + str(uid))
        for field in ("conditions", "remaining"):
            if not isinstance(c.get(field), list) or not c[field] or any(not isinstance(v, str) or not v for v in c[field]): errors.append("missing " + field + " " + str(uid))
        source_refs = c.get("source_anchor_ids", [])
        if any(ref not in anchors for ref in source_refs): errors.append("unknown source anchor " + str(uid))
        if c.get("status") == "source_resolved_local" and not source_refs: errors.append("source clause lacks anchor " + str(uid))
        for test in c.get("test_ids", []):
            if not isinstance(test, str) or not test.startswith("INIT-test_") or "def " + test[5:] + "(" not in test_text: errors.append("unknown test " + str(test))
    if set(clauses) != set(STATUSES): errors.append("clause set mismatch")
    if not spec.get("remaining"): errors.append("remaining obligations required")
    for path in spec.get("runtime_files", []):
        p = (root / path).resolve()
        if not p.is_relative_to(root) or not p.is_file(): errors.append("invalid runtime file " + str(path))
    return errors


def audit(root, spec=None):
    root = Path(root)
    path = Path(spec) if spec is not None else root / "data/verification/common-initiative-semantics.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    errors = validate(data, root)
    try:
        spec_key = path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        spec_key = str(path.resolve())
    inputs = {spec_key, "tools/audit_common_initiative_semantics.py", "tools/test_common_initiative.py", "data/verification/rule-symbol-graph.json"}
    inputs.update(a["file"] for a in data["source_anchors"])
    inputs.update(data["runtime_files"])
    return {"scope": "supporting source/contract integrity, not executable completion", "whole_semantic_complete": False,
            "errors": errors, "status": "failed" if errors else "checks_passed_with_pending_semantics",
            "results": [{"id": "COMMON-INITIATIVE-SPEC-INTEGRITY", "status": "fail" if errors else "pass"}],
            "input_hashes": {name: sha(root / name) for name in sorted(inputs)}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1]); parser.add_argument("--spec", type=Path); parser.add_argument("--output", type=Path)
    args = parser.parse_args(); report = audit(args.root, args.spec)
    output = args.output or args.root / "output/common-initiative-semantics-audit.json"
    output.parent.mkdir(parents=True, exist_ok=True); output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"errors": report["errors"], "status": report["status"]}, ensure_ascii=False))
    raise SystemExit(bool(report["errors"]))
