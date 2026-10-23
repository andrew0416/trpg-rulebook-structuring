"""Completion gate for source -> clauses -> implementation -> independent tests.
Tests passing alone cannot certify a rule. Drafts, missing branches and stale evidence block it.
"""
import argparse
import ast
import hashlib
import json
from collections import Counter
from pathlib import Path


EXPR_OPS={"eq","ne","and","or","not","ge","gt","le","lt","add","mul","div","floor","clamp"}

def expression_errors(value,path="when"):
    if not isinstance(value,dict):return []
    if set(value)=={"var"}:return [] if isinstance(value["var"],str) else [path+": variable must be text"]
    if value.get("op") not in EXPR_OPS:return [path+": unresolved expression operator"]
    if not isinstance(value.get("args"),list):return [path+": missing args"]
    arity={"eq":2,"ne":2,"not":1,"ge":2,"gt":2,"le":2,"lt":2,"div":2,"floor":1,"clamp":3}
    if value["op"] in arity and len(value["args"])!=arity[value["op"]]:return [path+": invalid operator arity"]
    if value["op"] in {"and","or","add","mul"} and len(value["args"])<2:return [path+": too few operands"]
    out=[]
    for i,arg in enumerate(value["args"]):out+=expression_errors(arg,f"{path}.args[{i}]")
    return out


def assess_contract(contract,results):
    blockers=[]
    if contract.get("status")!="reviewed":blockers.append("contract_not_reviewed")
    if contract.get("source_coverage_review")!="complete":blockers.append("source_clause_coverage_incomplete")
    if contract.get("implementation_review")!="complete":blockers.append("implementation_paths_not_reviewed")
    if contract.get("remaining_source_obligations"):blockers.append("unresolved_source_obligations")
    if not contract.get("sources"):blockers.append("source_missing")
    if not contract.get("implementation_paths"):blockers.append("implementation_missing")
    if not contract.get("clauses"):blockers.append("clauses_missing")
    clauses=[]
    for clause in contract.get("clauses",[]):
        cb=[]
        if not clause.get("effects"):cb.append("effects_missing")
        if clause.get("unresolved"):cb.append("unresolved_symbolization")
        if not isinstance(clause.get("when"),(bool,dict)):cb.append("unparsed_condition")
        cb+=expression_errors(clause.get("when"))
        for effect in clause.get("effects",[]):
            if "formula" in effect:cb.append("unparsed_formula")
            if "value" in effect:cb+=expression_errors(effect["value"],"effect.value")
        tests=clause.get("tests",[])
        if not tests:cb.append("no_test")
        roles={t.get("role") for t in tests}
        required=set(clause.get("required_test_roles") or [])
        if not required:cb.append("test_obligations_not_defined")
        cb.extend("missing_test_role:"+x for x in sorted(required-roles))
        # A conditional clause must have a non-applying path; 'positive' alone is insufficient.
        if clause.get("when") is not True and not any(x in roles for x in ["negative","negative_exception","negative_target","negative_type","below_boundary","positive_hp"]):
            cb.append("condition_complement_untested")
        for t in tests:
            row=results.get(t["id"])
            if row is None:cb.append("unknown_test:"+t["id"])
            elif row["status"]!="pass":cb.append("test_not_passed:"+t["id"])
        clauses.append(dict(id=clause["id"],status="blocked" if cb else "checks_passed",blockers=cb,test_ids=[t["id"] for t in tests]))
    if any(x["blockers"] for x in clauses):blockers.append("clause_checks_incomplete")
    return dict(id=contract["id"],status="blocked" if blockers else "verified",blockers=blockers,clauses=clauses)


def component_errors(rec, results, source_cases):
    """A component test cannot certify its entire rule, but its link must be real."""
    blocks=[]
    for component, evidence in rec.get('tested_components', {}).items():
        tid=evidence.get('test_id')
        if not tid or tid not in results:
            blocks.append('unknown_component_test:'+component)
        elif results[tid].get('status')!='pass':
            blocks.append('component_test_not_passed:'+component)
        if component in ('frequency','ap_header','source_boundary') and source_cases.get(tid)!=rec['rule_id']:
            blocks.append('component_test_wrong_source_rule:'+component)
        if not evidence.get('scope'):
            blocks.append('component_scope_missing:'+component)
    return blocks


def main(root):
    units={u["id"]:u for u in (json.loads(s) for s in (root/"output/ruleunits.jsonl").read_text(encoding="utf-8").splitlines())}
    catalog=[json.loads(s) for s in (root/"data/verification/rule-coverage-catalog.jsonl").read_text(encoding="utf-8").splitlines()]
    contracts=json.loads((root/"data/verification/rule-contracts.json").read_text(encoding="utf-8"))["contracts"]
    report=json.loads((root/"output/execution-accuracy-audit-core.json").read_text(encoding="utf-8"))
    results={r["id"]:r for r in report["results"]}
    global_blocks=[]
    source_cases={}
    actual_ids=[x["rule_id"] for x in catalog]
    if len(set(actual_ids))!=len(actual_ids):global_blocks.append("duplicate_catalog_ids")
    if set(actual_ids)!=set(units):global_blocks.append("catalog_does_not_cover_exact_rule_set")
    if len({c['id'] for c in contracts})!=len(contracts):global_blocks.append("duplicate_contract_ids")
    # Old passing results become invalid when their source oracle, runner or runtime inputs change.
    expected_hashes=dict(report.get("input_hashes",{}))
    expected_hashes["data/execution-accuracy-oracles.json"]=report["oracle_sha256"]
    expected_hashes["tools/audit_execution_accuracy.py"]=report["runner_sha256"]
    for extra_name in ['source-repair-tests.json','reference-rule-tests.json','frequency-tests.json','provenance-tests.json','state-lifecycle-tests.json','range-source-tests.json','weather-source-tests.json','action-point-tests.json','action-metadata-tests.json','action-metadata-independent-tests.json','passive-event-runtime-tests.json','passive-event-independent-tests.json','compound-action-cost-tests.json','compound-action-independent-tests.json','bound-ap-release-tests.json','bound-ap-release-independent-tests.json','bound-ap-author-recheck-tests.json','ap-drain-tests.json','feat-cost-source-tests.json','source-boundary-tests.json','mettle-tests.json','symbol-graph-tests.json','logical-proof-tests.json','common-source-tests.json','common-probability-repair-tests.json','common-probability-independent-tests.json','rule-selection-tests.json','variant-marker-tests.json','contest-rule-selection-tests.json','world-state-semantics-tests.json','precedence-semantics-tests.json','common-check-tests.json','common-precedence-edge-tests.json','league-runtime-tests.json','league-runtime-independent-tests.json','heavy-production-tests.json','heavy-standard-tests.json','heavy-native-type-tests.json','heavy-encounter-contract-tests.json','heavy-injury-kernel-tests.json','hp-loss-resource-tests.json','life-state-tests.json','life-source-boundary-tests.json','time-boundary-tests.json','session-frequency-tests.json','condition-save-timing-tests.json','common-action-lifecycle-independent-tests.json','common-action-lifecycle-integrity-tests.json','common-initiative-tests.json','common-initiative-integration-tests.json','common-initiative-semantics-audit.json','movement-action-budget-tests.json','movement-action-budget-independent-tests.json','root-mixed-decomposition-tests.json','rest-and-status-boundary-tests.json','snapshot-time-identity-tests.json','encounter-time-exit-tests.json','rest-interval-tests.json','rest-integration-tests.json','center-recovery-tests.json','recovery-semantics-tests.json','real-max-hp-tests.json','common-xp-arithmetic-tests.json','common-numeric-semantics-tests.json','root-authority-atoms-tests.json','root-authority-scope-tests.json','root-authority-scope-inventory-tests.json','common-scope-inventory-tests.json']:
        extra_path=root/'output'/extra_name
        if extra_path.is_file():
            extra=json.loads(extra_path.read_text(encoding='utf-8'))
            source_cases.update(extra.get('source_cases',{}))
            for row in extra['results']:
                if row['id'] in results:global_blocks.append('duplicate_test_id:'+row['id'])
                results[row['id']]=row
            for file,expected in extra['input_hashes'].items():
                if file in expected_hashes and expected_hashes[file]!=expected:global_blocks.append('inconsistent_test_evidence:'+file)
                expected_hashes[file]=expected
    for file,expected in expected_hashes.items():
        p=root/file
        if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=expected:global_blocks.append("stale_test_evidence:"+file)
    from audit_symbol_graph import validate as validate_symbols, rule_blockers as symbol_blockers
    symbol_graph=json.loads((root/'data/verification/rule-symbol-graph.json').read_text(encoding='utf-8'))
    global_blocks += ['symbol_graph:'+b for b in validate_symbols(symbol_graph,units,contracts)]
    from audit_root_semantics import validate_root,closure_blockers
    root_spec=json.loads((root/'data/verification/root-semantics.json').read_text(encoding='utf-8'))
    global_blocks += ['root_semantics:'+b for b in validate_root(root_spec,symbol_graph,root)]
    root_pending=closure_blockers(root_spec)
    assessments={c["id"]:assess_contract(c,results) for c in contracts}
    for contract in contracts:
        if set(contract["source_unit_ids"])-set(units):global_blocks.append("unknown_contract_rule:"+contract['id'])
        for source in contract.get("sources",[]):
            p=root/source["file"]
            if source.get("cell"):
                book=json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
                current=book.get(source["sheet"],{}).get("cells",{}).get(source["cell"],"")
            else:
                current="\n".join(p.read_text(encoding="utf-8").splitlines()[source["start"]-1:source["end"]]) if p.is_file() else ""
            if hashlib.sha256(current.encode()).hexdigest()!=source["excerpt_sha256"]:global_blocks.append("source_changed:"+contract['id'])
        for path in contract.get("implementation_paths",[]):
            file,function=path.split(":",1);p=root/file
            if not p.is_file() or function not in {x.name for x in ast.walk(ast.parse(p.read_text(encoding="utf-8"))) if isinstance(x,(ast.FunctionDef,ast.AsyncFunctionDef))}:
                global_blocks.append("implementation_link_broken:"+path)
    rows=[]
    for rec in catalog:
        blocks=component_errors(rec,results,source_cases)+symbol_blockers(symbol_graph,rec['rule_id']);unit=units.get(rec['rule_id'])
        if root_pending:blocks.append('top_level_semantics_not_closed')
        if not unit:blocks.append("rule_missing")
        elif hashlib.sha256(json.dumps(unit['text'],ensure_ascii=False,sort_keys=True).encode()).hexdigest()!=rec['text_sha256']:blocks.append("rule_text_changed")
        if rec.get('source_review')!='complete':blocks.append('source_review_incomplete')
        if rec.get('disposition') not in ('executable','data_definition','reference_only'):blocks.append('disposition_not_reviewed')
        if rec.get('disposition')=='reference_only':
            if not rec.get('exclusion_reason'):blocks.append('reference_exclusion_reason_missing')
            if not rec.get('source_fidelity_evidence'):blocks.append('reference_source_evidence_missing')
        else:
            if not rec.get('contract_ids'):blocks.append('no_rule_contract')
            for cid in rec.get('contract_ids',[]):
                if cid not in assessments or assessments[cid]['status']!='verified':blocks.append('contract_not_verified:'+cid)
        rows.append(dict(rule_id=rec['rule_id'],status='blocked' if blocks or global_blocks else 'verified',blockers=blocks))
    target=root/'output/whole-rulebook-audit';target.mkdir(exist_ok=True)
    result=dict(root_semantics_blockers=root_pending,total_rules=len(rows),verified_rules=sum(x['status']=='verified' for x in rows),blocked_rules=sum(x['status']=='blocked' for x in rows),global_blockers=global_blocks,
                test_results=dict(Counter(row['status'] for row in results.values())),contracts=list(assessments.values()),rules=rows,
                meaning='Blocked includes missing verification, not only known bugs. No expected-failure or skipped test counts as pass.')
    (target/'completion-gate.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:result[k] for k in ['total_rules','verified_rules','blocked_rules','global_blockers','test_results']},ensure_ascii=False))
    return 1 if global_blocks or result['blocked_rules'] else 0


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('root',nargs='?',type=Path,default=Path(__file__).resolve().parents[1]);args=ap.parse_args()
    raise SystemExit(main(args.root.resolve()))
