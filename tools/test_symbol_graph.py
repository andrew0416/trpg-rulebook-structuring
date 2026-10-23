"""Structural and dependency gating tests, not rule semantics tests."""
import copy,hashlib,json,unittest
from pathlib import Path
from datetime import datetime,timezone
from audit_symbol_graph import validate,rule_blockers,impact
ROOT=Path(__file__).resolve().parents[1]
class GraphTests(unittest.TestCase):
    def fixture(self):
        unit={'id':'rule/a','text':{'body':'original'}};h=hashlib.sha256(json.dumps(unit['text'],ensure_ascii=False,sort_keys=True).encode()).hexdigest()
        nodes=[dict(id='root',kind='root',parent=None,requires=[],status='draft'),dict(id='base',kind='symbol',parent='root',requires=[],status='draft',dependency_review='pending',source_unit_ids=['rule/a'],source_hashes={'rule/a':h}),dict(id='child',kind='symbol',parent='root',requires=['base'],status='reviewed',dependency_review='complete',source_unit_ids=['rule/a'],source_hashes={'rule/a':h})]
        g=dict(root='root',nodes=nodes,rule_bindings=[dict(rule_id='rule/a',symbol_refs=['child'],relation='source_anchor',dependency_review='complete')],contracts=[dict(contract_id='c',symbol_refs=['child'])])
        return g,{'rule/a':unit},[{'id':'c'}]
    def test_draft_parent_blocks_reviewed_child(self):
        g,u,c=self.fixture();self.assertEqual(validate(g,u,c),[])
        self.assertIn('unverified_parent_symbols:base',rule_blockers(g,'rule/a'))
    def test_reviewed_prerequisites_remove_symbol_block_only(self):
        g,u,c=self.fixture();g['nodes'][1].update(status='reviewed',dependency_review='complete')
        self.assertEqual(rule_blockers(g,'rule/a'),[]) # Other completion gates still apply.
    def test_unknown_dependency(self):
        g,u,c=self.fixture();g['nodes'][2]['requires']=['missing']
        self.assertIn('unknown_dependency:child:missing',validate(g,u,c))
    def test_dependency_cycle(self):
        g,u,c=self.fixture();g['nodes'][1]['requires']=['child']
        self.assertTrue(any(x.startswith('cycle:requires:') for x in validate(g,u,c)))
    def test_parent_cycle(self):
        g,u,c=self.fixture();g['nodes'][1]['parent']='child';g['nodes'][2]['parent']='base'
        self.assertTrue(any(x.startswith('cycle:parent:') for x in validate(g,u,c)))
    def test_missing_rule_is_not_covered(self):
        g,u,c=self.fixture();g['rule_bindings']=[]
        self.assertIn('rule_binding_set_mismatch',validate(g,u,c));self.assertEqual(rule_blockers(g,'rule/a'),['symbol_binding_missing'])
    def test_changed_source_invalidates_anchor(self):
        g,u,c=self.fixture();u['rule/a']['text']['body']='different'
        self.assertTrue(any(x.startswith('stale_symbol_source:') for x in validate(g,u,c)))
    def test_candidate_cannot_be_claimed_reviewed(self):
        g,u,c=self.fixture();g['rule_bindings'][0]['relation']='classification_candidate'
        self.assertIn('candidate_marked_reviewed:rule/a',validate(g,u,c))
    def test_reverse_impact_follows_transitive_dependencies(self):
        g,u,c=self.fixture();result=impact(g,'base')
        self.assertEqual(result['affected_symbols'],['base','child']);self.assertEqual(result['rule_ids'],['rule/a']);self.assertEqual(result['contract_ids'],['c'])
    def test_navigation_parent_is_not_semantic_dependency(self):
        g,u,c=self.fixture();self.assertEqual(impact(g,'root')['rule_ids'],[])
    def test_actual_graph_covers_exact_current_inventory(self):
        g=json.loads((ROOT/'data/verification/rule-symbol-graph.json').read_text(encoding='utf-8'))
        u={u['id']:u for u in map(json.loads,(ROOT/'output/ruleunits.jsonl').read_text(encoding='utf-8').splitlines())}
        c=json.loads((ROOT/'data/verification/rule-contracts.json').read_text(encoding='utf-8'))['contracts']
        self.assertEqual(validate(g,u,c),[])
        self.assertIn('feat/깡다구',impact(g,'damage.resistance')['rule_ids'])
    def test_missing_action_lifecycle_blocks_root(self):
        from audit_root_semantics import validate_root
        spec,graph=self.root_fixture();spec["transition_model"].pop("action_lifecycle")
        self.assertIn("root_supporting_spec_missing:action_lifecycle",validate_root(spec,graph,ROOT))
    def test_missing_action_cost_contract_blocks_root(self):
        from audit_root_semantics import validate_root
        spec,graph=self.root_fixture();spec['transition_model'].pop('action_costs')
        self.assertIn('root_supporting_spec_missing:action_costs',validate_root(spec,graph,ROOT))
    def test_missing_mixed_decomposition_blocks_root(self):
        from audit_root_semantics import validate_root
        spec,graph=self.root_fixture();spec['source_inventory'].pop('mixed_decomposition_reviews')
        self.assertIn('mixed_decomposition_reviews_missing',validate_root(spec,graph,ROOT))
    def root_fixture(self):
        return (json.loads((ROOT/'data/verification/root-semantics.json').read_text(encoding='utf-8')),
                json.loads((ROOT/'data/verification/rule-symbol-graph.json').read_text(encoding='utf-8')))
    def test_root_source_anchors_match(self):
        from audit_root_semantics import validate_root
        s,g=self.root_fixture();self.assertEqual(validate_root(s,g,ROOT),[])
    def test_root_missing_combined_authority_scope_rejected(self):
        from audit_root_semantics import validate_root
        s,g=self.root_fixture();s['source_inventory'].pop('authority_scope_inventory_reviews')
        self.assertIn('authority_scope_inventory_reviews_missing',validate_root(s,g,ROOT))
    def test_root_drafts_block_closure(self):
        from audit_root_semantics import closure_blockers
        s,g=self.root_fixture();self.assertIn('common_source_inventory_not_closed',closure_blockers(s))
    def test_root_status_cannot_certify_incomplete_spec(self):
        from audit_root_semantics import validate_root
        s,g=self.root_fixture();s['closure']['current']=True
        self.assertIn('unsupported_root_completion_claim',validate_root(s,g,ROOT))
    def test_root_changed_excerpt_rejected(self):
        from audit_root_semantics import validate_root
        s,g=self.root_fixture();s['clauses'][0]['source']['excerpt']='changed'
        self.assertIn('stale_root_source:ROOT-01',validate_root(s,g,ROOT))
    def test_root_missing_obligations_rejected(self):
        from audit_root_semantics import validate_root
        s,g=self.root_fixture();s['clauses'][0]['proof_obligations']=[]
        self.assertIn('root_obligations_missing:ROOT-01',validate_root(s,g,ROOT))
    def test_root_unknown_symbol_rejected(self):
        from audit_root_semantics import validate_root
        s,g=self.root_fixture();s['clauses'][0]['symbol']='nonexistent'
        self.assertIn('unknown_root_symbol:ROOT-01',validate_root(s,g,ROOT))
    def test_root_precedence_reaches_every_semantic_symbol(self):
        from audit_symbol_graph import closure
        s,g=self.root_fixture()
        for n in g['nodes']:
            if n['kind']=='symbol' and n['id'] not in ('source.authority','rules.applicability'):
                self.assertIn('rules.precedence',closure(g,n['id']),n['id'])
    def test_root_missing_criterion_blocks_closure(self):
        from audit_root_semantics import closure_blockers
        s,g=self.root_fixture();s['completion_criteria']=[]
        self.assertIn('completion_criteria_missing',closure_blockers(s))
    def test_root_missing_physical_inventory_rejected(self):
        from audit_root_semantics import validate_root
        s,g=self.root_fixture();s['source_inventory'].pop('physical_inventory')
        self.assertIn('physical_source_inventory_missing',validate_root(s,g,ROOT))
    def test_root_source_conflict_blocks_closure(self):
        from audit_root_semantics import closure_blockers
        s,g=self.root_fixture()
        self.assertIn('root_finding_unresolved:ROOT-PROB-01',closure_blockers(s))
    def test_root_missing_state_spec_rejected(self):
        from audit_root_semantics import validate_root
        s,g=self.root_fixture();s['state_model'].pop('specification')
        self.assertIn('root_supporting_spec_missing:state_model',validate_root(s,g,ROOT))
    def test_root_wrong_precedence_spec_rejected(self):
        from audit_root_semantics import validate_root
        s,g=self.root_fixture();s['specificity']['specification']='data/verification/root-semantics.json'
        self.assertIn('root_supporting_spec_missing:specificity',validate_root(s,g,ROOT))
    def test_root_missing_authority_atom_spec_rejected(self):
        from audit_root_semantics import validate_root
        s,g=self.root_fixture();s['source_inventory'].pop('authority_atom_draft')
        self.assertIn('authority_atom_draft_missing',validate_root(s,g,ROOT))
    def test_root_missing_arithmetic_spec_rejected(self):
        from audit_root_semantics import validate_root
        s,g=self.root_fixture();s['arithmetic'].pop('specification')
        self.assertIn('root_supporting_spec_missing:arithmetic',validate_root(s,g,ROOT))
    def test_root_missing_authority_scope_review_rejected(self):
        from audit_root_semantics import validate_root
        s,g=self.root_fixture();s['source_inventory'].pop('authority_scope_review')
        self.assertIn('authority_scope_review_missing',validate_root(s,g,ROOT))
if __name__=='__main__':
    class Result(unittest.TextTestResult):
        def __init__(self,*a,**k):super().__init__(*a,**k);self.rows=[]
        def addSuccess(self,t):super().addSuccess(t);self.rows.append(dict(id='SYMBOL-'+t._testMethodName,status='pass'))
        def addFailure(self,t,e):super().addFailure(t,e);self.rows.append(dict(id='SYMBOL-'+t._testMethodName,status='fail'))
        def addError(self,t,e):super().addError(t,e);self.rows.append(dict(id='SYMBOL-'+t._testMethodName,status='error'))
    r=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(GraphTests))
    paths=[ROOT/'tools/audit_common_source_inventory.py',ROOT/'data/verification/common-source-inventory.json',ROOT/'tools/audit_root_semantics.py',ROOT/'data/verification/root-semantics.json',ROOT/'input/ch01-intro.md',ROOT/'input/ch06-gameplay.md',Path(__file__),ROOT/'tools/audit_symbol_graph.py',ROOT/'data/verification/rule-symbol-graph.json',ROOT/'data/verification/rule-contracts.json',ROOT/'output/ruleunits.jsonl']
    paths += [ROOT/p for p in ['data/verification/world-state-semantics.json','data/verification/precedence-semantics.json','tools/audit_world_state_semantics.py','tools/audit_precedence_semantics.py']]
    paths += [ROOT/p for p in ['data/verification/common-check-semantics.json','data/verification/common-precedence-edges.json','tools/audit_common_checks.py','tools/test_common_precedence_edges.py']]
    paths += [ROOT/p for p in ['data/verification/life-state-semantics.json','tools/audit_life_state.py','tools/test_life_state.py']]
    paths += [ROOT/p for p in ['tools/audit_root_mixed_decomposition.py','tools/test_root_mixed_decomposition.py']+['data/verification/root-mixed-'+n+'-decomposition.json' for n in ('base','core','supplement')]]
    paths += [ROOT/p for p in ['data/verification/common-action-lifecycle-semantics.json','data/verification/common-action-lifecycle-runtime-bindings.json','tools/audit_common_action_lifecycle.py','tools/test_common_action_lifecycle_independent.py']]
    paths += [ROOT/p for p in ['data/verification/action-cost-semantics.json','tools/audit_action_cost_semantics.py','tools/test_movement_action_budget.py']]
    paths += [ROOT/p for p in ['data/verification/time-boundary-semantics.json','tools/audit_time_boundaries.py','tools/test_time_boundaries.py']]
    paths += [ROOT/p for p in ['data/verification/recovery-semantics.json','tools/audit_recovery_semantics.py','tools/test_center_recovery.py','tools/test_rest_intervals.py','tools/test_rest_integration.py']]
    paths += [ROOT/'tools/audit_common_numeric_semantics.py',ROOT/'data/verification/common-numeric-semantics.json']
    paths += [ROOT/'tools/audit_root_authority_scope.py',ROOT/'data/verification/root-authority-scope-review.json']
    paths += [ROOT/p for p in ['tools/audit_root_authority_scope_inventory.py','data/verification/root-authority-scope-core-followup.json','data/verification/root-authority-scope-supplement-followup.json','data/verification/session-frequency-source-review.json']]
    paths += [ROOT/'tools/audit_root_authority_atoms.py',ROOT/'data/verification/root-authority-atoms.json']
    paths += [ROOT/'tools/audit_common_scope_inventory.py', *sorted((ROOT/'data/verification/common-source-reviews').glob('*.json'))]
    report=dict(generated_at=datetime.now(timezone.utc).isoformat(),scope='Graph integrity and prerequisite gating; not rule behavior certification.',results=r.rows,input_hashes={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
    (ROOT/'output/symbol-graph-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    raise SystemExit(0 if r.wasSuccessful() else 1)
