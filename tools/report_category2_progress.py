"""Read clause evidence without confusing test counts with completion percentages.

The saved-input scope is frozen by a reviewed clause/source manifest. Any input
or independent-clause change invalidates that freeze until its next revision.
"""
from collections import Counter
from hashlib import sha256
from datetime import datetime, timedelta
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
SOURCES = (
    ("core", "category2-core-clause-status.json", "clause_mappings"),
    ("classes", "category2-class-clause-status.json", "entries"),
    ("optional", "category2-optional-clause-status.json", "rows"),
    ("core-additional", "category2-core-block-status.json", "new_clauses"),
    ("optional-additional", "category2-optional-additional-clause-status.json", "rows"),
    ("csv-abilities-moves", "category2-csv-abilities-moves-status.json", "rows"),
    ("csv-classes", "category2-class-csv-clause-status.json", "rows"),
    ("csv-items", "category2-item-table-status.json", "new_clauses"),
    ("csv-core", "category2-tabular-core-status.json", "entries"),
)


def _case_identity(uid):
    return "tools."+uid if uid.startswith("test_category2_") else uid


def _verified_test_ids(body, cases=None):
    """Read actual unittest successes; a case-scoped proof may retain failures."""
    footer = re.search(r"\nUTC end ([^\r\n]+)\r?\n?\Z", body)
    if footer:
        stamp = footer[1]
        try:
            valid = bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:[+-]00:00|Z)", stamp))
            valid = valid and datetime.fromisoformat(stamp.replace("Z", "+00:00")).utcoffset() == timedelta(0)
        except ValueError:
            valid = False
        if not valid:
            return None
        body = body[:footer.start()]
    summary = re.search(r"\n-{70}\r?\nRan (\d+) tests? in \d+(?:\.\d+)?s\r?\n\r?\n(OK|FAILED)(?: \(([^\r\n]+)\))?\s*\Z", body)
    if summary is None:
        return None
    case_text = body[:summary.start()].split("\n"+"="*70, 1)[0]
    headers = list(re.finditer(r"^(?:(test_\w+) \((\w+(?:\.\w+){2,})\)|"
                              r"(setUpClass|setUpModule|tearDownClass|tearDownModule) \((\w+(?:\.\w+)*)\)) \.\.\.", case_text, re.M))
    results = []
    subtest_parent_results = set()
    outcomes = []
    fixtures = []
    for index, header in enumerate(headers):
        end = headers[index+1].start() if index+1 < len(headers) else summary.start()
        segment = body[header.end():end].split("\n"+"="*70, 1)[0]
        if header[3]:
            if segment.strip() != 'ERROR' or (header[3].endswith('Class') and '.' not in header[4]):
                return None
            fixtures.append(header[3] + ' (' + header[4] + ')')
            outcomes.append('ERROR')
            continue
        statuses = re.findall(r"^[ \t]*(ok|FAIL|ERROR|skipped [^\r\n]+|expected failure|unexpected success)[ \t]*\r?$", segment, re.M)
        subtests = list(re.finditer(r"^[ \t]+(test_\w+) \((\w+(?:\.\w+){2,})\) .+ \.\.\. (FAIL|ERROR)[ \t]*\r?$", segment, re.M))
        if subtests:
            if any(child[1] != header[1] or child[2] != header[2] for child in subtests):
                return None
            if len(statuses) > 1 or any(status not in ('FAIL', 'ERROR') for status in statuses):
                return None
            child_statuses = [child[3] for child in subtests]
            status = 'ERROR' if 'ERROR' in child_statuses + statuses else 'FAIL'
            outcomes.extend(child_statuses)
        else:
            status = statuses[0] if len(statuses) == 1 else None
        outcomes.extend(statuses)
        uid = _case_identity(header[2])
        if header[1] != header[2].rsplit(".", 1)[-1]:
            status = None
        if cases is not None and any(previous_uid == uid for previous_uid, _ in results):
            # unittest reprints a failing subTest parent if the parent then fails.
            # It is one invocation, but all child and parent outcomes still count.
            if not results or results[-1][0] != uid or headers[index-1][2] != header[2] or uid not in subtest_parent_results or subtests or status not in ('FAIL', 'ERROR'):
                return None
            results[-1] = (uid, 'ERROR' if 'ERROR' in (results[-1][1], status) else 'FAIL')
            subtest_parent_results.remove(uid)
        else:
            results.append((uid, status))
            if subtests:
                subtest_parent_results.add(uid)
    fixture_details = re.findall(r"^ERROR: ((?:setUpClass|setUpModule|tearDownClass|tearDownModule) \(\w+(?:\.\w+)*\))\r?$", body, re.M)
    if fixtures != fixture_details:
        return None
    compact = re.search(r"(?:^|\n)(\.+)\r?\n?\Z", case_text)
    if (cases is None and not headers and summary[2] == 'OK' and summary[3] is None
            and compact and len(compact[1]) == int(summary[1])
            and not re.search(r"^(?:FAIL|ERROR):|\.\.\. (?:FAIL|ERROR)[ \t]*\r?$", body, re.M)):
        # Legacy compact proofs carry no named successes.
        return set()
    successes = {uid for uid, status in results if status == "ok"}
    if cases is not None:
        if type(cases) is not list or not cases or any(type(uid) is not str for uid in cases) or len(set(cases)) != len(cases):
            return None
        cases = [_case_identity(uid) for uid in cases]
        if len(set(cases)) != len(cases):
            return None
    if len(results) != int(summary[1]) or (cases is not None and len({uid for uid, _ in results}) != len(results)) or any(status is None for _, status in results):
        return None
    # Count the actual outcomes too, rather than trusting a forged final OK.
    actual = Counter("failures" if status == "FAIL" else "errors" if status == "ERROR" else "skipped" if status.startswith("skipped ") else "unexpected successes" if status == "unexpected success" else "expected failures" for status in outcomes if status != "ok")
    declared = {}
    if summary[3]:
        for item in summary[3].split(", "):
            match = re.fullmatch(r"(failures|errors|skipped|expected failures|unexpected successes)=([1-9]\d*)", item)
            if match is None or match[1] in declared:
                return None
            declared[match[1]] = int(match[2])
    failed = bool(actual["failures"] or actual["errors"] or actual["unexpected successes"])
    if dict(actual) != declared or (summary[2] == "FAILED") != failed:
        return None
    if cases is None:
        return successes if summary[2] == "OK" else None
    if not set(cases) <= successes:
        return None
    return set(cases)


def collect_edge_reuse(root=ROOT, plan=None):
    """Count named inspected clauses independently of implementation progress."""
    path = root / "data/verification/category2-edge-work-plan.json"
    if plan is None:
        if not path.exists():
            return None
        plan = json.loads(path.read_text(encoding="utf-8"))
    audit = plan.get("post_foundation_reuse", {}).get("itemized_audit")
    if audit is None:
        return None
    errors = []
    baseline = audit["baseline_clause_ids"]
    added = audit.get("added_clause_ids", [])
    identities = baseline + added
    if len(set(identities)) != len(identities):
        errors.append("Duplicate inspection scope identity")
    if sha256("\n".join(baseline).encode("utf-8")).hexdigest() != audit["baseline_sha256"]:
        errors.append("Inspection baseline changed")
    records = audit["items"]
    occurrences = Counter(row["id"] for row in records)
    expected = set(identities)
    if set(occurrences) != expected:
        errors.append("Inspection rows differ from fixed scope")
    for identity, count in occurrences.items():
        if count != 1:
            errors.append("Duplicate inspection row: " + identity)
    units = {row["id"] for row in plan["foundation_discovery"]["foundation_execution_plan"]["units"]}
    routes = audit["routes"]
    proof_cache = {}
    def proof_text(proof):
        key = (proof["log"], proof["sha256"], json.dumps(proof.get("cases"), sort_keys=True))
        if key not in proof_cache:
            candidate = root / proof["log"]
            raw = candidate.read_bytes() if candidate.is_file() else b""
            body = raw.decode("utf-8-sig", errors="replace")
            ids = _verified_test_ids(body, proof.get("cases")) if sha256(raw).hexdigest() == proof["sha256"] else None
            if "cases" in proof and proof["cases"] is None:
                ids = None
            proof_cache[key] = (ids is not None, ids or set())
        return proof_cache[key]
    done = set()
    counts = Counter()
    for row in records:
        identity = row["id"]
        if identity not in expected or occurrences[identity] != 1:
            continue
        status = row["status"]
        counts[status] += 1
        if status != "verified":
            continue
        route = routes.get(row["route"], {})
        issues = []
        if row.get("entrypoint_reviewed") is not True or not route.get("native_paths"):
            issues.append("missing actual entrypoint review")
        if not route.get("foundation_ids") or not set(route["foundation_ids"]) <= units:
            issues.append("missing or unknown original foundation")
        proofs = route.get("evidence", [])
        checked = [proof_text(proof) for proof in proofs]
        if not checked or not all(valid for valid, _ in checked):
            issues.append("missing, changed or unsuccessful verification log")
        successful_ids = {uid for valid, ids in checked if valid for uid in ids}
        successful_modules = {uid.rsplit(".", 2)[0].removeprefix("tools.") for uid in successful_ids}
        if not route.get("required_test_modules") or any(name.removeprefix("tools.") not in successful_modules for name in route["required_test_modules"]):
            issues.append("actual consumer test absent from evidence")
        if issues:
            errors.append(identity + ": " + "; ".join(issues))
        else:
            done.add(identity)
    denominator = len(expected)
    return {"unit": "original clause ID", "baseline_denominator": len(set(baseline)),
            "denominator": denominator, "completed": len(done), "remaining": denominator-len(done),
            "percent": round(100*len(done)/denominator, 8) if denominator else 0,
            "status_counts": dict(counts), "pending_clause_ids": sorted(expected-done),
            "validation_errors": sorted(set(errors)),
            "ledger": "data/verification/category2-edge-work-plan.json#post_foundation_reuse.itemized_audit",
            "scope": audit["scope"], "category2_completion_credit": 0}


def collect(root=ROOT):
    entries = []
    groups = {}
    errors = []
    seen = set()
    source_hashes = {}
    def source_matches(file, digest):
        if file not in source_hashes:
            path = root / file
            source_hashes[file] = sha256(path.read_bytes()).hexdigest() if path.is_file() else None
        return source_hashes[file] == digest
    for name, filename, key in SOURCES:
        path = root / "data" / "verification" / filename
        doc = json.loads(path.read_text(encoding="utf-8"))
        rows = doc[key]
        counts = Counter()
        for row in rows:
            if name in ("core", "core-additional"):
                identity = row["clause_id"]
                included = row["category2_included"]
                status = row["category2_status"]
                refs = [(row["source_file"], row["source_sha256"])]
            elif name == "classes":
                identity = row.get("source_clause_id") or row["id"]
                included = row["include_category2"]
                status = row["status"]
                refs = [(row["source_file"], row["source_sha256"])]
            elif name == "csv-abilities-moves":
                identity = row["row_id"]
                included = row["category2_included"] and row["denominator_contribution"] == 1
                status = row["category2_status"]
                refs = [(row["source_file"], row["source_sha256"])]
            elif name == "csv-classes":
                identity = row["id"]
                included = row["include_category2"] and row["dedupe_target"] is None
                status = row["status"]
                refs = [(row["file"], row["file_sha256"])]
            elif name == "csv-core":
                identity = row["id"]
                included = row["include_category2"] and row["denominator_contribution"] == 1
                status = row["status"]
                refs = [(row["source_file"], row["source_sha256"])]
            else:
                identity = row["clause_id"]
                included = row["category2_in_scope"]
                status = row["status"]
                refs = [(r["file"], r["file_sha256"]) for r in row["source"]]
            if identity in seen:
                errors.append("Duplicate clause identity: " + identity)
            seen.add(identity)
            if type(included) is not bool:
                errors.append("Unresolved classification: " + identity)
            if not refs:
                errors.append("Missing source evidence: " + identity)
            current = bool(refs) and all(source_matches(file, digest) for file, digest in refs)
            if not current:
                errors.append("Stale source evidence: " + identity)
            if included:
                if status not in ("implemented", "incomplete", "known-rule-choice"):
                    errors.append("Unsupported included status: " + identity + " " + status)
                counts[status if current else "stale-evidence"] += 1
            else:
                counts["outside-category2"] += 1
            entries.append({"id": identity, "group": name, "included": included,
                            "status": status, "source_evidence_current": current})
        groups[name] = {"registered": len(rows), "included": sum(r["included"] is True for r in entries if r["group"] == name),
                        "status_counts": dict(counts), "registry": str(path.relative_to(root)).replace("\\", "/"),
                        "registry_sha256": sha256(path.read_bytes()).hexdigest()}
    totals = Counter(r["status"] if r["source_evidence_current"] else "stale-evidence" for r in entries if r["included"] is True)
    included_ids = sorted(r["id"] for r in entries if r["included"] is True)
    freeze_path = root / "data" / "verification" / "category2-scope-freeze.json"
    freeze = json.loads(freeze_path.read_text(encoding="utf-8")) if freeze_path.exists() else None
    if freeze:
        references = freeze.get("reference_only_sources", [])
        for ref in references:
            if ref.get("counts_for_category2") is not False or not ref.get("reason"):
                errors.append("Unclassified reference-only input: " + ref["file"])
        for ref in [*freeze["source_manifest"], *references]:
            if not source_matches(ref["file"], ref["sha256"]):
                errors.append("Frozen input changed: " + ref["file"])
        expected_files = {ref["file"] for ref in [*freeze["source_manifest"], *references]}
        actual_files = {str(p.relative_to(root)).replace("\\", "/") for p in (root / "input").rglob("*") if p.is_file()}
        if actual_files != expected_files:
            errors.append("Saved input file inventory changed")
    frozen = bool(freeze and freeze.get("included_clause_ids") == included_ids and not errors)
    if freeze and not frozen:
        errors.append("Current clause/source set differs from the frozen scope; publish a reviewed scope revision.")
    denominator = len(included_ids) if frozen else None
    completed = totals["implemented"] if frozen else None
    return {"schema_version": 2, "category": 2,
            "whole_category_complete": bool(frozen and completed == denominator), "denominator_frozen": frozen,
            "scope_revision": freeze.get("revision") if frozen else None,
            "denominator": denominator, "completed_clause_count": completed,
            "completion_percent": round(100 * completed / denominator, 8) if frozen and denominator else None,
            "included_clause_ids": included_ids,
            "classified_subset": {"registered": len(entries), "included": sum(r["included"] is True for r in entries),
                                  "evidence_status_counts": dict(totals)},
            "groups": groups, "validation_errors": sorted(set(errors)),
            "edge_reuse_inspection": collect_edge_reuse(root),
            "remaining_scope": (["Frozen saved-input scope; any newly discovered independent clauses require a reviewed scope revision."] if frozen else
                                ["Reconcile full saved-input coverage and source-condition child evidence."]),
            "counting_policy": "Clause IDs are units. Tests, fields, files, and candidate rows are not completion units. A parent is implemented only when every included state child is evidenced.",
            "category3_ledger": "unchanged; historical category3 certification is not counted in category2"}

if __name__ == "__main__":
    report = collect()
    path = ROOT / "data" / "verification" / "category2-progress.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k != "included_clause_ids"}, ensure_ascii=False, indent=2))
    raise SystemExit(bool(report["validation_errors"] or (report.get("edge_reuse_inspection") or {}).get("validation_errors")))
