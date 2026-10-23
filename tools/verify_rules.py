"""Run regressions, source audits and the rule completion gate together.
Exit 0 means every stage passed; nonzero includes incomplete verification.
"""
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def main():
    root=Path(__file__).resolve().parents[1]
    out=root/"output/whole-rulebook-audit/run-logs"
    out.mkdir(parents=True,exist_ok=True)
    jobs=[(p.stem,[str(p),str(root)]) for p in sorted((root/"engine").glob("test_*.py"))]
    jobs += [("test_rule_completion",["tools/test_rule_completion.py"]),
             ("source-repair-tests",["-W","ignore::ResourceWarning","tools/test_source_repair.py"]),
             ("reference-rule-tests",["-W","ignore::ResourceWarning","tools/test_reference_rules.py"]),
             ("frequency-tests",["-W","ignore::ResourceWarning","tools/test_frequencies.py"]),
             ("weather-source-tests",["-W","ignore::ResourceWarning","tools/test_weather_sources.py"]),
             ("feat-cost-source-tests",["-W","ignore::ResourceWarning","tools/test_feat_cost_sources.py"]),
             ("source-boundary-tests",["-W","ignore::ResourceWarning","tools/test_source_boundaries.py"]),
             ("mettle-tests",["-W","ignore::ResourceWarning","tools/test_mettle.py"]),
             ("ap-drain-tests",["-W","ignore::ResourceWarning","tools/test_ap_drain.py"]),
             ("action-point-tests",["-W","ignore::ResourceWarning","tools/test_action_points.py"]),
             ("action-metadata-tests",["tools/test_action_metadata.py"]),
             ("action-metadata-independent-tests",["tools/test_action_metadata_independent.py"]),
             ("passive-event-runtime-tests",["tools/test_passive_event_runtime.py"]),
             ("passive-event-independent-tests",["tools/test_passive_event_independent.py"]),
             ("compound-action-cost-tests",["tools/test_compound_action_costs.py"]),
             ("compound-action-independent-tests",["tools/test_compound_action_independent.py"]),
             ("bound-ap-release-tests",["tools/test_bound_ap_release.py"]),
             ("bound-ap-release-independent-tests",["tools/test_bound_ap_release_independent.py"]),
             ("bound-ap-author-recheck-tests",["tools/test_bound_ap_author_recheck.py"]),
             ("common-source-tests",["tools/test_common_sources.py"]),
             ("common-source-inventory",["tools/audit_common_source_inventory.py"]),
             ("common-scope-inventory-tests",["tools/test_common_scope_inventory.py"]),
             ("common-scope-inventory",["tools/audit_common_scope_inventory.py"]),
             ("root-authority-scope-tests",["tools/test_root_authority_scope.py"]),
             ("root-authority-scope-audit",["tools/audit_root_authority_scope.py"]),
             ("root-authority-scope-inventory-tests",["tools/test_root_authority_scope_inventory.py"]),
             ("root-authority-scope-inventory-audit",["tools/audit_root_authority_scope_inventory.py"]),
             ("root-mixed-decomposition-tests",["tools/test_root_mixed_decomposition.py"]),
             ("root-mixed-decomposition-audit",["tools/audit_root_mixed_decomposition.py"]),
             ("root-authority-atoms-tests",["tools/test_root_authority_atoms.py"]),
             ("root-authority-atoms-audit",["tools/audit_root_authority_atoms.py"]),
             ("common-numeric-semantics-tests",["tools/test_common_numeric_semantics.py"]),
             ("common-numeric-semantics-audit",["tools/audit_common_numeric_semantics.py"]),
             ("common-probability-repair-tests",["tools/test_common_probability_repairs.py"]),
             ("common-probability-independent-tests",["tools/test_common_probability_independent.py"]),
             ("common-probability-audit",["tools/audit_common_probabilities.py"]),
             ("rule-selection-tests",["-W","ignore::ResourceWarning","tools/test_rule_selection.py"]),
             ("variant-marker-tests",["-W","ignore::ResourceWarning","tools/test_variant_markers.py"]),
             ("contest-rule-selection-tests",["-W","ignore::ResourceWarning","tools/test_contest_rule_selection.py"]),
             ("rule-selection-audit",["tools/audit_rule_selection.py"]),
             ("world-state-semantics-tests",["tools/test_world_state_semantics.py"]),
             ("world-state-semantics-audit",["tools/audit_world_state_semantics.py"]),
             ("precedence-semantics-tests",["tools/test_precedence_semantics.py"]),
             ("precedence-semantics-audit",["tools/audit_precedence_semantics.py"]),
             ("common-check-tests",["-W","ignore::ResourceWarning","tools/test_common_checks.py"]),
             ("common-check-audit",["tools/audit_common_checks.py"]),
             ("common-precedence-edge-tests",["tools/test_common_precedence_edges.py"]),
             ("league-runtime-tests",["tests/test_league_runtime.py"]),
             ("league-runtime-independent-tests",["tests/test_league_runtime_independent.py"]),
             ("heavy-production-tests",["tests/test_heavy_production.py"]),
             ("heavy-standard-tests",["tests/test_heavy_standard.py"]),
             ("heavy-native-type-tests",["tests/test_heavy_native_types.py"]),
             ("heavy-encounter-contract-tests",["tests/test_encounter_boundary_contracts.py"]),
             ("heavy-injury-kernel-tests",["tools/test_heavy_injury_kernel.py"]),
             ("hp-loss-resource-tests",["tools/test_hp_loss_resources.py"]),
             ("life-state-tests",["-W","ignore::ResourceWarning","tools/test_life_state.py"]),
             ("life-source-boundary-tests",["tools/test_life_source_boundary.py"]),
             ("life-state-audit",["tools/audit_life_state.py"]),
             ("time-boundary-tests",["tools/test_time_boundaries.py"]),
             ("session-frequency-tests",["tools/test_session_frequency.py"]),
             ("movement-action-budget-tests",["tools/test_movement_action_budget.py"]),
             ("movement-action-budget-independent-tests",["tools/test_movement_action_budget_independent.py"]),
             ("condition-save-timing-tests",["tools/test_condition_save_timing.py"]),
             ("common-action-lifecycle-independent-tests",["tools/test_common_action_lifecycle_independent.py"]),
             ("common-action-lifecycle-integrity-tests",["tools/test_common_action_lifecycle_integrity.py"]),
             ("common-action-lifecycle-audit",["tools/audit_common_action_lifecycle.py"]),
             ("common-initiative-tests",["tools/test_common_initiative.py"]),
             ("common-initiative-integration-tests",["tools/test_common_initiative_integration.py"]),
             ("common-initiative-semantics-audit",["tools/audit_common_initiative_semantics.py"]),
             ("action-cost-semantics-audit",["tools/audit_action_cost_semantics.py"]),
             ("rest-and-status-boundary-tests",["tools/test_rest_and_status_boundaries.py"]),
             ("snapshot-time-identity-tests",["tools/test_snapshot_time_identity.py"]),
             ("encounter-time-exit-tests",["tools/test_encounter_time_exit.py"]),
             ("time-boundary-audit",["tools/audit_time_boundaries.py"]),
             ("rest-interval-tests",["tools/test_rest_intervals.py"]),
             ("rest-integration-tests",["tools/test_rest_integration.py"]),
             ("center-recovery-tests",["tools/test_center_recovery.py"]),
             ("recovery-semantics-tests",["tools/test_recovery_semantics.py"]),
             ("real-max-hp-tests",["tools/test_real_max_hp.py"]),
             ("common-xp-arithmetic-tests",["tools/test_common_xp_arithmetic.py"]),
             ("recovery-semantics-audit",["tools/audit_recovery_semantics.py"]),
             ("symbol-graph-tests",["tools/test_symbol_graph.py"]),
             ("logical-proof-tests",["tools/test_logical_proof.py"]),
             ("logical-coverage-proof",["tools/prove_logical_coverage.py"]),
             ("symbol-graph",["tools/audit_symbol_graph.py","--impact","rules.precedence"]),
             ("rule-obligations",["tools/audit_rule_obligations.py"]),
             ("range-source-tests",["-W","ignore::ResourceWarning","tools/test_range_sources.py"]),
             ("state-lifecycle-tests",["-W","ignore::ResourceWarning","tools/test_state_lifecycle.py"]),
             ("provenance-tests",["-W","ignore::ResourceWarning","tools/test_source_locations.py"]),
             ("execution-core",["-I","tools/audit_execution_accuracy.py","--ruleset","core"]),
             ("execution-all",["-I","tools/audit_execution_accuracy.py","--ruleset","all"]),
             ("schema",["tools/validate_ruleunits.py"]),
             ("draft-validation",["tools/validate_drafts.py"]),
             ("crosscheck",["tools/crosscheck_drafts.py"]),
             ("source-audit",["-I","tools/audit_rulebook_all.py"]),
             ("completion-gate",["tools/check_rule_completion.py"])]
    stages=[]
    for name,args in jobs:
        p=subprocess.run([sys.executable,"-X","utf8","-B",*args],cwd=root,capture_output=True,text=True,encoding="utf-8")
        log=p.stdout+p.stderr
        (out/(name+".txt")).write_text(log,encoding="utf-8")
        table_fail=bool(re.search(r"^\|\s*\d+\s*\|.*?\|\s*FAIL\s*\|",log,re.M))
        issue_count=0
        if name=="crosscheck":
            issue_count=sum(bool(line.strip()) for line in (root/"output/draft-crosscheck.jsonl").read_text(encoding="utf-8").splitlines())
        elif name=="draft-validation":
            count=re.search(r"건수 (\d+)개",log)
            issue_count=int(count.group(1)) if count else -1
        status="pass" if p.returncode==0 and not table_fail and issue_count==0 else "not_passed"
        stages.append(dict(name=name,exit_code=p.returncode,status=status,table_failure=table_fail,issue_count=issue_count,log=str((out/(name+".txt")).relative_to(root))))
        print(name+": "+status,flush=True)
    result=dict(generated_at=datetime.now(timezone.utc).isoformat(),status="pass" if all(s["status"]=="pass" for s in stages) else "not_complete",stages=stages,
                meaning="Passing regressions do not override source discrepancies or unverified rule clauses.")
    (out.parent/"verification-run.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return 0 if result["status"]=="pass" else 1


if __name__=="__main__":
    raise SystemExit(main())
