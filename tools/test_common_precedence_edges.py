"""Saved-source common exception mappings, checked separately from runtime behavior."""
import copy,hashlib,json,unittest
from datetime import datetime,timezone
from pathlib import Path
from audit_precedence_semantics import ROOT,model_errors,resolve

PATH=ROOT/'data/verification/common-precedence-edges.json'

def load():
    return json.loads(PATH.read_text(encoding='utf-8'))

def anchor_errors(anchor,root):
    try:
        lines=(root/anchor['file']).read_text(encoding='utf-8').splitlines()
        text='\n'.join(lines[anchor['start']-1:anchor['end']])
        if text != anchor['excerpt'] or hashlib.sha256(text.encode()).hexdigest()!=anchor['excerpt_sha256']:
            return ['stale_source']
        if not text.strip():
            return ['empty_source']
    except (KeyError,OSError,TypeError):
        return ['invalid_source']
    return []

def validate(spec,root=ROOT):
    errors=anchor_errors(spec.get('authority',{}),root)
    ids=[edge['id'] for edge in spec['edges']]
    if len(ids)!=len(set(ids)):
        errors.append('duplicate_edge_id')
    if spec.get('whole_rule_certified') is not False:
        errors.append('unsupported_whole_rule_claim')
    for edge in spec['edges']:
        tag=edge['id']
        if edge.get('kind')!='scoped_override':
            errors.append(tag+':not_override')
        if not edge.get('scope') or not edge.get('mapping_reason') or not edge.get('remaining'):
            errors.append(tag+':missing_mapping_obligation')
        for endpoint in ['general','specific']:
            errors += [tag+':'+endpoint+':'+e for e in anchor_errors(edge[endpoint].get('source',{}),root)]
        model=edge['finite_abstraction']['model']
        errors += [tag+':'+e for e in model_errors(model)]
        if len(model['rules'])!=2 or len(model['overrides'])!=1:
            errors.append(tag+':invalid_two_clause_mapping')
            continue
        relation=model['overrides'][0]
        if relation['general']!=edge['general']['id'] or relation['specific']!=edge['specific']['id']:
            errors.append(tag+':wrong_endpoints')
        if {r['aspect'] for r in model['rules']}!={edge['aspect']}:
            errors.append(tag+':wrong_aspect')
        if relation.get('evidence',{}).get('anchor')!=tag or relation.get('evidence',{}).get('kind')!='source_review':
            errors.append(tag+':missing_source_mapping')
        if not model_errors(model):
            for context,fixture in edge['finite_abstraction']['contexts'].items():
                result=resolve(model,context)[edge['aspect']]
                if result['status']!=fixture['expected_status'] or result['value']!=fixture['expected_value']:
                    errors.append(tag+':fixture_mismatch:'+context)
    for item in spec['non_edges']:
        if item.get('classification') not in {
            'stat_percentage_increase_not_rounding_override','applicability_partition_not_check_result_override',
            'distinct_operation_domains_not_proven_override','different_governed_aspects','distinct_typed_domains',
            'explicit_composition_law_not_override_of_unstated_rule','composition_order_unresolved'}:
            errors.append(item['id']+':unsupported_nonedge_classification')
        for source in item['sources']:
            errors += [item['id']+':'+e for e in anchor_errors(source,root)]
    return errors

def solve(edge_id,context):
    edge=next(e for e in load()['edges'] if e['id']==edge_id)
    return resolve(edge['finite_abstraction']['model'],context)[edge['aspect']]

class CommonPrecedenceTests(unittest.TestCase):
    def test_source_inventory_and_mapping_integrity(self):
        self.assertEqual(validate(load()),[])

    def test_ap_bound_and_drained_do_not_restore_at_scene_boundary(self):
        for edge_id in ['COMMON-PREC-01','COMMON-PREC-02']:
            self.assertEqual(solve(edge_id,'ordinary')['value'],1)
            self.assertEqual(solve(edge_id,'exception')['value'],0)

    def test_combat_start_weapon_and_first_release_have_no_action_cost(self):
        self.assertEqual(solve('COMMON-PREC-03','ordinary')['value'],1)
        self.assertEqual(solve('COMMON-PREC-04','ordinary')['value'],2)
        for edge_id in ['COMMON-PREC-03','COMMON-PREC-04']:
            self.assertEqual(solve(edge_id,'exception')['value'],0)
            source=next(e for e in load()['edges'] if e['id']==edge_id)
            self.assertFalse(source['finite_abstraction']['contexts']['exception']['facts']['ambushed_or_surprised'])

    def test_limited_priority_preserves_remaining_turn(self):
        self.assertEqual(solve('COMMON-PREC-05','ordinary')['value'],1)
        self.assertEqual(solve('COMMON-PREC-05','exception')['value'],0)

    def test_advanced_priority_lifts_only_prior_action_bar_and_retains_debt_obligation(self):
        self.assertEqual(solve('COMMON-PREC-06','ordinary')['value'],1)
        self.assertEqual(solve('COMMON-PREC-06','exception')['value'],0)
        e=next(e for e in load()['edges'] if e['id']=='COMMON-PREC-06')
        self.assertEqual(e['finite_abstraction']['contexts']['exception']['facts']['next_round_turn_debt'],'required')
        self.assertIn('not other timing rules or next-turn debt',e['scope'])

    def test_five_injuries_prevents_otherwise_qualifying_rest_hp_recovery(self):
        self.assertEqual(solve('COMMON-PREC-07','ordinary')['value'],1)
        self.assertEqual(solve('COMMON-PREC-07','exception')['value'],0)

    def test_conscious_vulnerable_target_cannot_apply_evasion(self):
        self.assertEqual(solve('COMMON-PREC-08','ordinary')['value'],1)
        self.assertEqual(solve('COMMON-PREC-08','exception')['value'],0)

    def test_total_blindness_accuracy_is_minus_ten_not_minus_sixteen(self):
        self.assertEqual(solve('COMMON-PREC-09','ordinary')['value'],-6)
        self.assertEqual(solve('COMMON-PREC-09','exception')['value'],-10)
        self.assertNotEqual(solve('COMMON-PREC-09','exception')['value'],-16)

    def test_contest_defeated_half_count_explicitly_uses_ceiling_mode(self):
        self.assertEqual(solve('COMMON-PREC-10','ordinary')['value'],0)
        self.assertEqual(solve('COMMON-PREC-10','exception')['value'],1)
        edge=next(e for e in load()['edges'] if e['id']=='COMMON-PREC-10')
        self.assertIn('일반적인 내림 규칙에 대한 예외',edge['specific']['source']['excerpt'])
        self.assertIn('half-count',edge['specific']['meaning'])
        self.assertIn('mode only',edge['finite_abstraction']['value_encoding']['1'])

    def test_exceptions_do_not_leak_outside_parent_event_domain(self):
        for e in load()['edges']:
            self.assertEqual(solve(e['id'],'outside')['status'],'not_applicable')

    def test_no_selection_no_override_for_every_mapped_edge(self):
        for e in load()['edges']:
            m=copy.deepcopy(e['finite_abstraction']['model'])
            m['rules'][1]['selected']=False
            result=resolve(m,'exception')[e['aspect']]
            self.assertEqual(result['value'],e['finite_abstraction']['contexts']['ordinary']['expected_value'])

    def test_removing_each_evidence_backed_edge_is_detected(self):
        for e in load()['edges']:
            m=copy.deepcopy(e['finite_abstraction']['model'])
            m['overrides']=[]
            self.assertEqual(resolve(m,'exception')[e['aspect']]['status'],'unresolved')

    def test_source_text_mutation_is_detected(self):
        s=load();s['edges'][0]['specific']['source']['excerpt']='invented'
        self.assertTrue(any('stale_source' in e for e in validate(s)))

    def test_cross_aspect_mutation_is_detected(self):
        s=load();s['edges'][0]['finite_abstraction']['model']['rules'][1]['aspect']='unrelated'
        errors=validate(s)
        self.assertTrue(any('wrong_aspect' in e for e in errors))

    def test_missing_mapping_not_inferred_from_subset(self):
        s=load();s['edges'][0]['mapping_reason']=''
        self.assertTrue(any('missing_mapping_obligation' in e for e in validate(s)))

    def test_twenty_percent_raise_is_not_a_ceiling_exception(self):
        item=next(e for e in load()['non_edges'] if e['id']=='COMMON-NONEDGE-01')
        self.assertEqual(item['classification'],'stat_percentage_increase_not_rounding_override')
        self.assertIn('220%',item['sources'][1]['excerpt'])

    def test_no_roll_and_costly_success_do_not_override_numeric_check_result(self):
        items={i['id']:i for i in load()['non_edges']}
        self.assertEqual(items['COMMON-NONEDGE-02']['classification'],'applicability_partition_not_check_result_override')
        self.assertEqual(items['COMMON-NONEDGE-04']['classification'],'different_governed_aspects')

    def test_unsourced_movement_composition_stays_unresolved(self):
        item=next(e for e in load()['non_edges'] if e['id']=='COMMON-NONEDGE-07')
        self.assertEqual(item['classification'],'composition_order_unresolved')

    def test_partial_mapping_cannot_claim_rulebook_completion(self):
        s=load();self.assertFalse(s['whole_rule_certified']);s['whole_rule_certified']=True
        self.assertIn('unsupported_whole_rule_claim',validate(s))

if __name__=='__main__':
    class Result(unittest.TextTestResult):
        def __init__(self,*a,**k):super().__init__(*a,**k);self.rows=[]
        def addSuccess(self,t):super().addSuccess(t);self.rows.append(dict(id='COMMON-PRECEDENCE-'+t._testMethodName,status='pass'))
        def addFailure(self,t,e):super().addFailure(t,e);self.rows.append(dict(id='COMMON-PRECEDENCE-'+t._testMethodName,status='fail'))
        def addError(self,t,e):super().addError(t,e);self.rows.append(dict(id='COMMON-PRECEDENCE-'+t._testMethodName,status='error'))
    result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(CommonPrecedenceTests))
    paths=['tools/test_common_precedence_edges.py','tools/audit_precedence_semantics.py',
           'data/verification/common-precedence-edges.json','input/ch01-intro.md','input/ch06-gameplay.md','input/ch07-combat.md','input/ch08-contests.md']
    report=dict(generated_at=datetime.now(timezone.utc).isoformat(),scope='Ten common saved-source override mappings and excluded inferences; not runtime conformance.',
        results=result.rows,input_hashes={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths},whole_rule_certified=False)
    (ROOT/'output/common-precedence-edge-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    raise SystemExit(0 if result.wasSuccessful() else 1)
