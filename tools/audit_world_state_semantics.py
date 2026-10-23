"""Integrity of the draft shared-state specification and its small abstract model.

This is NOT an engine conformance checker, a complete state validator, or a proof
that all source rules have been formalized. Draft closure remains blocked.
"""
import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
SPEC = "data/verification/world-state-semantics.json"
TYPE_IDS = {"Actor", "World", "Clock", "Resource", "Effect", "PendingEvent"}
STAGE_KEYS = {"attack", "defense", "special_attack", "special_defense", "speed"}

def closure_blockers(spec):
    out = []
    for key, value in spec.get("certification", {}).items():
        if value is not True:
            out.append("uncertified:" + key)
    for group in ("source_facts", "types", "transitions", "proof_obligations"):
        for item in spec.get(group, []):
            if item.get("status") != "reviewed" or item.get("remaining"):
                out.append("pending:" + item["id"])
    for review in spec.get("interpretation_reviews", []):
        if review.get("status") != "resolved_saved_source_interpretation":
            out.append("interpretation_unresolved:" + review["id"])
    return out

def validate(spec, root=ROOT):
    errors = []
    facts = spec.get("source_facts", [])
    fact_ids = {f.get("id") for f in facts}
    if not facts:
        errors.append("source_facts_missing")
    if len(fact_ids) != len(facts):
        errors.append("duplicate_fact_id")
    for f in facts:
        fid = f.get("id", "missing")
        s = f.get("source", {})
        path = root / s.get("file", "")
        try:
            inside = path.resolve().is_relative_to((root / "input").resolve())
        except (OSError, ValueError):
            inside = False
        if not inside or not path.is_file() or type(s.get("start")) is not int or type(s.get("end")) is not int or s["start"] < 1 or s["end"] < s["start"]:
            errors.append("invalid_source:" + fid)
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        text = "\n".join(lines[s["start"]-1:s["end"]])
        if s["end"] > len(lines) or text != s.get("excerpt") or hashlib.sha256(text.encode()).hexdigest() != s.get("excerpt_sha256"):
            errors.append("stale_source:" + fid)
        if not f.get("formal") or f.get("origin") != "source_formalization":
            errors.append("fact_semantics_missing:" + fid)
    types = spec.get("types", [])
    if {t.get("id") for t in types} != TYPE_IDS or len(types) != len(TYPE_IDS):
        errors.append("state_type_set_mismatch")
    for t in types:
        if t.get("origin") != "modeling_convention":
            errors.append("type_origin_misrepresented:" + t["id"])
        if not t.get("fields") or not t.get("invariants"):
            errors.append("type_incomplete:" + t["id"])
        for name, field in t.get("fields", {}).items():
            if not field.get("domain") or not field.get("meaning") or not field.get("origin"):
                errors.append("field_incomplete:" + t["id"] + "." + name)
            for ref in field.get("source_refs", []):
                if ref not in fact_ids:
                    errors.append("unknown_source_ref:" + ref)
    transitions = spec.get("transitions", [])
    if not transitions:
        errors.append("transitions_missing")
    if len({t["id"] for t in transitions}) != len(transitions):
        errors.append("duplicate_transition_id")
    for t in transitions:
        for key in ("preconditions", "postconditions", "frame_conditions", "boundary_cases", "source_refs"):
            if not t.get(key):
                errors.append("transition_contract_missing:" + t["id"] + ":" + key)
        for ref in t.get("source_refs", []):
            if ref not in fact_ids:
                errors.append("unknown_source_ref:" + ref)
    if not spec.get("proof_obligations"):
        errors.append("proof_obligations_missing")
    for o in spec.get("proof_obligations", []):
        if not o.get("requirement") or not o.get("counterexamples"):
            errors.append("proof_obligation_incomplete:" + o["id"])
    # No generic JSON status field can make this draft a semantic certificate.
    if spec.get("closure", {}).get("complete") or spec.get("status") in ("complete", "reviewed") or any(spec.get("certification", {}).values()):
        errors.append("unsupported_completion_claim")
    errors.extend(validate_reviews(spec, root))
    return sorted(set(errors))


def validate_reviews(spec, root=ROOT):
    errors=[]; readers={}
    for review in spec.get("interpretation_reviews", []):
        rid=review["id"]
        if not review.get("evidence") or not review.get("finding"):
            errors.append("review_evidence_missing:"+rid)
        if review.get("status")=="unresolved_source_conflict" and review.get("resolution") is not None:
            errors.append("unresolved_review_has_resolution:"+rid)
        if review.get("status")=="resolved_saved_source_interpretation" and not review.get("resolution"):
            errors.append("resolved_review_missing_resolution:"+rid)
        for evidence in review.get("evidence", []):
            path=root/evidence.get("file", "")
            if not path.is_file() or not path.resolve().is_relative_to(root.resolve()):
                errors.append("invalid_review_source:"+rid);continue
            try:
                if evidence.get("kind")=="markdown":
                    lines=path.read_text(encoding="utf-8").splitlines()
                    if type(evidence.get("start")) is not int or type(evidence.get("end")) is not int or not 1<=evidence["start"]<=evidence["end"]<=len(lines):
                        raise ValueError("invalid source range")
                    text="\n".join(lines[evidence["start"]-1:evidence["end"]])
                elif evidence.get("kind")=="pdf_text":
                    from pypdf import PdfReader
                    if hashlib.sha256(path.read_bytes()).hexdigest()!=evidence.get("file_sha256"):
                        errors.append("stale_review_pdf:"+rid)
                    if path not in readers: readers[path]=PdfReader(path)
                    page=readers[path].pages[evidence["page_index"]].extract_text()
                    start=page.index(evidence["start_marker"]);end=page.index(evidence["end_marker"],start)
                    text=page[start:end]
                else: raise ValueError("unsupported source kind")
                if text!=evidence.get("excerpt") or hashlib.sha256(text.encode()).hexdigest()!=evidence.get("excerpt_sha256"):
                    errors.append("stale_review_excerpt:"+rid)
            except (ValueError,IndexError,KeyError,TypeError):
                errors.append("invalid_review_source:"+rid)
    return errors

def baseline_death(hp, real_max_hp, injuries, friendly):
    """Source-derived boundary model; no engine call and no exception support."""
    if type(hp) is not int or type(real_max_hp) is not int or real_max_hp<=0 or type(injuries) is not int or injuries<0 or type(friendly) is not bool:
        raise ValueError("Requires known baseline integer state and friendly boolean")
    return injuries>=10 or (not friendly and hp<=min(-50,-2*real_max_hp))

def actor_fragment_errors(a):
    """Executable subset of STATE-02/03/05/06; not all Actor validity."""
    out = []
    if type(a.get("hp")) is not int:
        out.append("hp_not_integer")
    if type(a.get("temp_hp")) is not int or a["temp_hp"] < 0:
        out.append("invalid_temp_hp")
    stages = a.get("stages", {})
    if set(stages) != STAGE_KEYS:
        out.append("invalid_stage_keys")
    if any(type(v) is not int or not -6 <= v <= 6 for v in stages.values()):
        out.append("invalid_stage_value")
    if type(a.get("hp")) is int and a["hp"] <= 0 and a.get("consciousness") == "Conscious":
        out.append("nonpositive_hp_conscious")
    return out

def ap_fragment_errors(ap):
    """Disjoint AP allocation invariant; maximum-change exceptions not modeled."""
    fields = [ap.get(k) for k in ("capacity", "spent", "drained", "available")]
    bound = ap.get("bound", {})
    if not isinstance(bound, dict):
        return ["invalid_bound_map"]
    fields += list(bound.values())
    if any(type(v) is not int or v < 0 for v in fields):
        return ["ap_not_nonnegative_integer"]
    expected = ap["capacity"] - ap["spent"] - ap["drained"] - sum(bound.values())
    return [] if expected == ap["available"] and expected >= 0 else ["ap_conservation_violation"]

def hashes(root=ROOT):
    spec = json.loads((root / SPEC).read_text(encoding="utf-8"))
    paths = {SPEC, "tools/audit_world_state_semantics.py", "tools/test_world_state_semantics.py"}
    paths.update(f["source"]["file"] for f in spec["source_facts"])
    paths.update(e["file"] for review in spec.get("interpretation_reviews",[]) for e in review.get("evidence",[]))
    return {p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in sorted(paths) if (root / p).is_file()}

def main():
    spec = json.loads((ROOT / SPEC).read_text(encoding="utf-8"))
    errors = validate(spec)
    report = dict(generated_at=datetime.now(timezone.utc).isoformat(), status="passed" if not errors else "failed", verification_kind="specification_integrity_only", engine_conformance=False, whole_rule_certified=False, errors=errors, source_fact_count=len(spec["source_facts"]), type_count=len(spec["types"]), transition_count=len(spec["transitions"]), proof_obligation_count=len(spec["proof_obligations"]), closure_blockers=closure_blockers(spec), input_hashes=hashes(), results=[dict(id="world-state-specification-integrity",status="pass" if not errors else "fail")])
    target = ROOT / "output/whole-rulebook-audit/world-state-semantics-audit.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({k:report[k] for k in ("status","verification_kind","errors","source_fact_count","type_count","transition_count","proof_obligation_count")},ensure_ascii=False))
    return 0 if not errors else 1

if __name__ == "__main__":
    raise SystemExit(main())
