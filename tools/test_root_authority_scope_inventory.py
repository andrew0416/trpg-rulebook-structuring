"""Adversarial integrity tests; synthetic fixtures do not prove any game rule."""
from __future__ import annotations
import argparse, copy, json, tempfile, unittest
from pathlib import Path
from datetime import datetime, timezone
import audit_root_authority_scope_inventory as A

def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def fixture(root):
    """Explicit synthetic review inventory, using real schema but invented source text."""
    write(root/A.GRAPH,{'nodes':[{'id':s} for s in sorted(A.TARGETS)]})
    documents=sorted(A.DOCUMENTS)
    reports=[]
    for group in (documents[:5],documents[5:12],documents[12:]):
        report=dict(scope=dict(documents=group,selection_symbols=sorted(A.TARGETS),candidate_count=len(group),
            all_source_text_reread=True,source_condition_denominator_complete=False,whole_rulebook_semantics_complete=False,coverage_percent=None),
            classification_criteria={c:'synthetic classification enum' for c in A.CATEGORIES},
            source_and_review_snapshots=[],candidate_dispositions=[],validation={})
        for ch in group:
            source=f'input/{ch}.md';rp=f'{A.REVIEWS}/{ch}.json'
            p=root/source;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('synthetic title\nsynthetic condition\nsynthetic exception\n',encoding='utf-8')
            cid='SYNTHETIC-'+ch
            c=dict(id=cid,block_ids=[source+':2-3'],statement='synthetic statement, not a source rule',
                conditions=['condition'],exceptions=['exception'],symbol_refs=['source.authority'],status='draft',atomicity='statement_group',remaining=['meaning unproved'])
            write(root/rp,dict(file=source,source_sha256=A.digest(p),whole_source_complete=False,clauses=[c]))
            report['source_and_review_snapshots'].append(dict(review_file=rp,review_sha256=A.digest(root/rp),source_file=source,source_sha256=A.digest(p),
                source_line_count=3,candidate_ids=[cid],direct_source_read_ranges=[[1,3]],whole_source_text_reread_this_turn=True,visuals_complete=False,whole_semantics_complete=False))
            text='synthetic condition\nsynthetic exception'
            report['candidate_dispositions'].append(dict(candidate_id=cid,review_file=rp,original_candidate=copy.deepcopy(c),
                anchors=[dict(file=source,start=2,end=3,excerpt=text,excerpt_sha256=A.text_digest(text))],
                category='scoped_domain_rule',reason='synthetic classification rationale',review_method='synthetic schema fixture',
                parent_symbols=['source.authority'],scope_guard=['condition'],exceptions_preserved=['exception'],atomic_coverage_complete=False,
                status='scope_reviewed_atomic_semantics_incomplete'))
        reports.append(report)
    return reports

class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='synthetic-scope-inventory-')
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.reports=fixture(self.root)
    @property
    def first(self):return self.reports[0]['candidate_dispositions'][0]
    @property
    def snapshot(self):return self.reports[0]['source_and_review_snapshots'][0]
    def errors(self):return A.validate(self.reports,self.root)[0]
    def reject(self,code):self.assertTrue(any(e.startswith(code) for e in self.errors()),self.errors())
    def test_valid_partition_preserves_no_semantic_claim(self):
        errors,s=A.validate(self.reports,self.root);self.assertEqual([],errors)
        self.assertEqual(20,s['selected_candidate_count']);self.assertEqual(20,len(s['declared_full_text_reread_documents']))
        self.assertFalse(s['source_condition_denominator_complete']);self.assertFalse(s['whole_rulebook_semantics_complete'])
        self.assertFalse(s['read_declarations_independently_proven']);self.assertIsNone(s['coverage_percent'])
    def test_missing_candidate(self):
        self.reports[0]['candidate_dispositions'].pop();self.reject('candidate_partition')
    def test_duplicate_candidate(self):
        self.reports[0]['candidate_dispositions'].append(copy.deepcopy(self.first));self.reject('candidate_partition')
    def test_invented_candidate(self):
        self.first['candidate_id']='SYNTHETIC-INVENTED';self.reject('unknown_candidate')
    def test_candidate_moved_to_other_document(self):
        self.first['review_file']=self.reports[1]['candidate_dispositions'][0]['review_file'];self.reject('candidate_document')
    def test_report_document_overlap(self):
        self.reports.append(copy.deepcopy(self.reports[0]));self.reject('combined_document_partition')
    def test_report_document_omission(self):
        self.reports.pop();self.reject('combined_document_partition')
    def test_unknown_classification(self):
        self.first['category']='proven_global_axiom';self.reject('candidate_category')
    def test_enum_expansion_does_not_authorize_category(self):
        self.reports[0]['classification_criteria']['proven_global_axiom']='bad';self.reject('classification_enum')
    def test_source_hash_stale(self):
        self.snapshot['source_sha256']='0'*64;self.reject('snapshot_hash')
    def test_review_hash_stale(self):
        self.snapshot['review_sha256']='0'*64;self.reject('snapshot_hash')
    def test_live_source_changed(self):
        (self.root/self.snapshot['source_file']).write_text('changed\nsecond\nthird\n',encoding='utf-8');self.reject('live_review_source_hash')
    def test_excerpt_changed(self):
        self.first['anchors'][0]['excerpt']='invented';self.reject('anchor_content')
    def test_excerpt_hash_changed(self):
        self.first['anchors'][0]['excerpt_sha256']='0'*64;self.reject('anchor_content')
    def test_valid_but_unrelated_source_anchor(self):
        a=self.first['anchors'][0];a.update(start=1,end=1,excerpt='synthetic title',excerpt_sha256=A.text_digest('synthetic title'))
        self.reject('candidate_anchor_relation')
    def test_anchor_out_of_range(self):
        self.first['anchors'][0]['end']=4;self.reject('anchor_range')
    def test_false_completion_nested(self):
        self.first['atomic_coverage_complete']=True;self.reject('unsupported_semantic_completion')
    def test_false_source_denominator(self):
        self.reports[0]['scope']['source_condition_denominator_complete']=True;self.reject('scope_required_incomplete')
    def test_false_percent_from_candidate_count(self):
        self.reports[0]['scope']['coverage_percent']=100;self.reject('unsupported_coverage_percent')
    def test_false_visual_completion(self):
        self.snapshot['visuals_complete']=True;self.reject('unsupported_semantic_completion')
    def test_false_full_read_for_partial_ranges(self):
        self.snapshot['direct_source_read_ranges']=[[2,3]];self.reject('unsupported_full_text_read')
    def test_targeted_ranges_count_separately_without_semantic_claim(self):
        self.snapshot['direct_source_read_ranges']=[[2,3]]
        self.snapshot['whole_source_text_reread_this_turn']=False;self.reports[0]['scope']['all_source_text_reread']=False
        errors,s=A.validate(self.reports,self.root);self.assertEqual([],errors)
        self.assertEqual(19,len(s['declared_full_text_reread_documents']));self.assertEqual(1,len(s['declared_targeted_context_documents']))
        self.assertFalse(s['whole_rulebook_semantics_complete'])
    def test_candidate_outside_declared_read_range(self):
        self.snapshot['direct_source_read_ranges']=[[1,2]];self.snapshot['whole_source_text_reread_this_turn']=False
        self.reports[0]['scope']['all_source_text_reread']=False;self.reject('candidate_outside_declared_read_scope')
    def test_read_ranges_union_accepts_adjacent_ranges(self):
        self.snapshot['direct_source_read_ranges']=[[1,1],[2,3]];self.assertEqual([],self.errors())
    def test_read_range_repetition_cannot_fill_missing_line(self):
        self.snapshot['direct_source_read_ranges']=[[2,3],[2,3]];self.reject('unsupported_full_text_read')
    def test_aggregate_full_read_claim_contradicts_snapshot(self):
        self.snapshot['whole_source_text_reread_this_turn']=False;self.reject('aggregate_read_scope')
    def test_changed_candidate_text_without_current_snapshot(self):
        self.first['original_candidate']['statement']='wrong';self.reject('candidate_snapshot_content')
    def test_explicit_current_candidate_preserves_original_history(self):
        self.first['current_candidate']=copy.deepcopy(self.first['original_candidate'])
        self.first['original_candidate']['statement']='historical draft before correction'
        self.assertEqual([],self.errors())
    def test_wrong_current_candidate_is_not_bypassed_by_valid_original(self):
        self.first['current_candidate']=copy.deepcopy(self.first['original_candidate']);self.first['current_candidate']['statement']='wrong'
        self.reject('candidate_snapshot_content')
    def test_original_history_identity_required_with_current(self):
        self.first['current_candidate']=copy.deepcopy(self.first['original_candidate']);self.first.pop('original_candidate')
        self.reject('missing_original_candidate_history')
    def test_condition_loss(self):
        self.first['scope_guard']=[];self.reject('candidate_condition_loss')
    def test_exception_loss(self):
        self.first['exceptions_preserved']=[];self.reject('candidate_exception_loss')
    def test_additional_local_scope_guard_is_not_condition_loss(self):
        self.first['scope_guard'].append('module selected');self.assertEqual([],self.errors())
    def test_unknown_parent_symbol(self):
        self.first['parent_symbols']=['rules.invented'];self.reject('candidate_parent_symbol')
    def test_snapshot_candidate_count_is_not_trusted(self):
        self.snapshot['candidate_ids']=[];self.reject('snapshot_candidate_set')
    def test_report_count_is_not_trusted(self):
        self.reports[0]['scope']['candidate_count']=578;self.reject('declared_candidate_count')
    def test_hash_ledger_traversal(self):
        self.reports[0]['input_hashes']={'../outside.json':'0'*64};self.reject('hash_ledger_path')
    def test_hash_ledger_staleness(self):
        self.reports[0]['input_hashes']={A.GRAPH:'0'*64};self.reject('hash_ledger_stale')
    def test_live_duplicate_candidate_detected(self):
        p=self.root/self.reports[1]['candidate_dispositions'][0]['review_file'];r=A.load(p)
        r['clauses'][0]['id']=self.first['candidate_id'];write(p,r);self.reject('live_candidate_duplicate')
    def test_missing_live_review_document(self):
        (self.root/self.snapshot['review_file']).unlink();self.reject('live_document_inventory')
    def test_required_scope_false_field_missing(self):
        del self.reports[0]['scope']['whole_rulebook_semantics_complete'];self.reject('scope_required_incomplete')
    def test_new_root_axiom_count_rejected(self):
        self.reports[0]['scope']['root_axioms_added']=1;self.reject('unsupported_new_root_axioms')
    def test_invalid_read_boolean_not_truthy_coerced(self):
        self.snapshot['whole_source_text_reread_this_turn']='true';self.reject('missing_read_scope_declaration')
    def attach_index_ledger(self):
        ledger={p.relative_to(self.root).as_posix():A.digest(p) for p in sorted((self.root/A.REVIEWS).glob('*.json'))}
        self.reports[0]['authority_index_snapshot']=dict(review_count=20,indexed_candidate_count=20,review_hashes=ledger)
        return self.reports[0]['authority_index_snapshot']
    def test_current_global_index_map_is_valid(self):
        self.attach_index_ledger();self.assertEqual([],self.errors())
    def test_index_map_drift_is_not_hidden_by_valid_input_hashes(self):
        index=self.attach_index_ledger();self.reports[0]['input_hashes']=dict(index['review_hashes'])
        index['review_hashes'][self.snapshot['review_file']]='0'*64;self.reject('hash_ledger_stale')
    def test_index_map_missing_review_detected(self):
        index=self.attach_index_ledger();index['review_hashes'].pop(self.snapshot['review_file']);self.reject('index_review_partition')
    def test_index_map_extra_non_review_detected(self):
        index=self.attach_index_ledger();index['review_hashes'][A.GRAPH]=A.digest(self.root/A.GRAPH);self.reject('index_review_partition')
    def test_index_map_wrong_type_detected(self):
        self.attach_index_ledger()['review_hashes']=[];self.reject('index_review_partition')
    def test_index_review_count_is_recomputed(self):
        self.attach_index_ledger()['review_count']=19;self.reject('index_snapshot_count')
    def test_index_candidate_count_is_recomputed(self):
        self.attach_index_ledger()['indexed_candidate_count']=578;self.reject('index_snapshot_count')
    def test_index_float_count_is_not_integer_declaration(self):
        self.attach_index_ledger()['review_count']=20.0;self.reject('index_snapshot_count')
    def test_index_list_partition_is_also_checked(self):
        index=self.attach_index_ledger();index['reviews']=[dict(file=k,sha256=v) for k,v in index['review_hashes'].items()]
        del index['review_hashes'];self.assertEqual([],self.errors())
        index['reviews'].pop();self.reject('index_review_partition')
    def test_index_dual_ledger_one_stale_is_detected(self):
        index=self.attach_index_ledger();index['reviews']=[dict(file=k,sha256=v) for k,v in index['review_hashes'].items()]
        index['reviews'][0]['sha256']='0'*64;self.reject('hash_ledger_stale')
    def test_index_without_recognized_ledger_is_not_accepted(self):
        self.reports[0]['authority_index_snapshot']={'review_count':20};self.reject('index_snapshot_schema')
    def test_malformed_report_returns_errors(self):
        self.assertEqual(['invalid_report_list'],A.validate(None,self.root)[0])

class RecordingResult(unittest.TextTestResult):
    def __init__(self,*args,**kwargs):super().__init__(*args,**kwargs);self.records=[]
    def addSuccess(self,test):super().addSuccess(test);self.records.append(dict(id='AUTHORITY-INVENTORY-'+test.id().split('.')[-1],status='pass'))
    def addFailure(self,test,err):super().addFailure(test,err);self.records.append(dict(id='AUTHORITY-INVENTORY-'+test.id().split('.')[-1],status='fail'))
    def addError(self,test,err):super().addError(test,err);self.records.append(dict(id='AUTHORITY-INVENTORY-'+test.id().split('.')[-1],status='error'))

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path);a=p.parse_args()
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(InventoryTests)
    result=unittest.TextTestRunner(verbosity=1,resultclass=RecordingResult).run(suite)
    report=dict(generated_at=datetime.now(timezone.utc).isoformat(),status='pass' if result.wasSuccessful() else 'fail',
        tests_run=result.testsRun,results=result.records,input_hashes={
            'tools/audit_root_authority_scope_inventory.py':A.digest(A.__file__),'tools/test_root_authority_scope_inventory.py':A.digest(__file__)},
        synthetic_fixture=True,whole_rule_certified=False,semantic_completeness_proved=False,
        limitation='Adversarial metadata-integrity tests only. Synthetic candidates are not source records or meaning proofs.')
    output=a.output or Path(__file__).resolve().parents[1]/'output/root-authority-scope-inventory-tests.json'
    write(output,report)
    return not result.wasSuccessful()
if __name__=='__main__':raise SystemExit(main())

