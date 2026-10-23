"""Adversarial integrity fixtures. These tests do not certify rule semantics."""
from __future__ import annotations
import argparse,copy,json,shutil,tempfile,unittest
from pathlib import Path
from datetime import datetime,timezone
import audit_root_mixed_decomposition as audit

REAL_ROOT=audit.ROOT
REAL_PATHS=None
class MixedTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.paths=REAL_PATHS or [REAL_ROOT/p for p in audit.SPECS]
  cls.real=[audit.load(p) for p in cls.paths]
  cls.tmp=tempfile.TemporaryDirectory(prefix='mixed-integrity-')
  cls.root=Path(cls.tmp.name)
  for rel in audit.input_files(cls.real,REAL_ROOT):
   out=cls.root/rel;out.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(REAL_ROOT/rel,out)
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def setUp(self):self.specs=copy.deepcopy(self.real)
 def errors(self):return audit.validate(self.specs,self.root)
 def reject(self,prefix):
  errors=self.errors()
  self.assertTrue(any(e.startswith(prefix) for e in errors),(prefix,errors))
 def component(self,ident):
  return next(x for s in self.specs for x in s['components'] if x['id']==ident)
 def test_real_data(self):self.assertEqual(audit.validate(self.real,REAL_ROOT),[])
 def test_isolated_copy(self):self.assertEqual(self.errors(),[])
 def test_missing_report(self):
  self.specs.pop();self.reject('mixed_schema_error:')
 def test_missing_candidate(self):
  self.specs[1]['candidates'].pop();self.reject('mixed_candidate_set')
 def test_duplicate_candidate(self):
  self.specs[1]['candidates'].append(copy.deepcopy(self.specs[1]['candidates'][0]));self.reject('mixed_candidate_set')
 def test_nonmixed_candidate_laundering(self):
  self.specs[1]['candidates'][0]['candidate_id']='C03-083';self.reject('mixed_candidate_set')
 def test_component_duplicate(self):
  self.specs[1]['components'].append(copy.deepcopy(self.specs[1]['components'][0]));self.reject('mixed_component_duplicate:')
 def test_component_orphan(self):
  self.specs[1]['components'][0]['candidate_id']='C03-083';self.reject('mixed_component_owner:')
 def test_component_missing_from_parent(self):
  self.specs[1]['candidates'][0]['component_ids'].pop();self.reject('mixed_component_crosslink:')
 def test_deleted_component(self):
  self.specs[1]['components'].pop();self.reject('mixed_component_crosslink:')
 def test_candidate_current_conditions_mutation(self):
  self.specs[1]['candidates'][0]['current_candidate']['conditions'].append('invented');self.reject('mixed_candidate_snapshot:')
 def test_candidate_wrong_review_hash(self):
  self.specs[1]['candidates'][0]['review_sha256']='0'*64;self.reject('mixed_file_hash:')
 def test_candidate_wrong_source_hash(self):
  self.specs[1]['candidates'][0]['source_sha256']='0'*64;self.reject('mixed_file_hash:')
 def test_candidate_exact_but_unrelated_excerpt(self):
  c=self.specs[1]['candidates'][0];c['anchors']=[audit.anchor(self.root,c['source_file'],1,1)]
  self.reject('mixed_candidate_anchor_relation:')
  self.assertFalse(any(e.startswith('mixed_anchor:') for e in self.errors()))
 def test_component_exact_but_unrelated_excerpt(self):
  x=self.specs[1]['components'][0];a=x['source_anchors'][0]
  x['source_anchors']=[audit.anchor(self.root,a['file'],1,1)]
  x['source_spans']=[{'anchor_index':0,'text':x['source_anchors'][0]['excerpt']}]
  self.reject('mixed_component_parent_range:')
 def test_unrelated_clause_cannot_be_laundered_with_unused_parent_anchor(self):
  x=self.specs[1]['components'][0];parent=x['source_anchors'][0]
  x['source_anchors']=[audit.anchor(self.root,parent['file'],1,1),parent]
  x['source_spans']=[{'anchor_index':0,'text':x['source_anchors'][0]['excerpt']}]
  self.reject('mixed_focused_parent_range:')
 def test_atom_ref_and_reuse_ref_must_agree(self):
  x=self.component('RMC-C05-160-01');x['existing_atom_refs']=[]
  self.reject('mixed_atom_crosslink:')
 def test_context_exception_cannot_move_to_arbitrary_line(self):
  x=self.component('RMB-C11-053-04');f=x['source_anchors'][0]['file']
  x['source_anchors']=[audit.anchor(self.root,f,1,1)];x['source_span']=[x['source_anchors'][0]['excerpt']]
  self.reject('mixed_component_parent_range:')
 def test_internal_inference_as_source_quote(self):
  x=self.specs[1]['components'][0];a=x['source_anchors'][0];a['excerpt']='GM can ignore all rules.'
  a['excerpt_sha256']=audit.text_hash(a['excerpt']);self.reject('mixed_anchor:')
 def test_internal_inference_as_clause_substring(self):
  x=self.specs[2]['components'][0];x['source_span'][0]['text']='Selection is unnecessary; apply to every campaign.'
  self.reject('mixed_source_span:')
 def test_source_span_offset_changed(self):
  x=self.specs[1]['components'][0];x['source_spans'][0]['start_offset']+=1
  self.reject('mixed_source_span_offset:')
 def test_source_span_hash_changed(self):
  x=self.specs[1]['components'][0];x['source_spans'][0]['excerpt_sha256']='f'*64
  self.reject('mixed_source_span_hash:')
 def test_missing_clause_span(self):
  self.specs[1]['components'][0]['source_spans']=[];self.reject('mixed_source_span_missing:')
 def test_unknown_symbol(self):
  self.specs[1]['components'][0]['parent_symbols']=['invented.root'];self.reject('mixed_symbol:')
 def test_unknown_atom(self):
  self.specs[1]['components'][0]['existing_atom_refs']=['RA-999'];self.reject('mixed_atom_reference:')
 def test_unknown_candidate_ref(self):
  self.specs[1]['components'][0]['reuse_refs']=[{'type':'candidate','id':'CXX-999','relationship':'invented'}]
  self.reject('mixed_reuse_reference:')
 def test_unknown_ref_type(self):
  self.specs[1]['components'][0]['reuse_refs']=[{'type':'approval','id':'RA-001','relationship':'invented'}]
  self.reject('mixed_reuse_reference:')
 def test_unknown_context_component(self):
  self.specs[1]['components'][0]['context_component_refs']=['missing'];self.reject('mixed_context_reference:')
 def test_self_context_cycle(self):
  x=self.specs[1]['components'][0];x['context_component_refs']=[x['id']]
  self.reject('mixed_context_reference:')
 def test_base_optional_guard_removed(self):
  x=self.component('RMB-C11-007-02');x['context_component_refs']=[]
  self.reject('mixed_optional_guard:')
 def test_core_optional_guard_removed_but_other_condition_retained(self):
  x=self.component('RMC-C07-185-02');x['conditions']=['새 부상을 입음']
  self.reject('mixed_optional_guard:')
 def test_supplement_optional_guard_removed_and_case_consistent(self):
  x=self.specs[2]['components'][0];x['conditions']=['기절한 포켓몬']
  x['positive_case']['given']['selected_module_and_conditions']=x['conditions'][:]
  self.reject('mixed_optional_guard:')
 def test_supplement_guard_case_unbound(self):
  x=self.specs[2]['components'][0];x['positive_case']['given']['selected_module_and_conditions']=[]
  self.reject('mixed_guard_case_binding:')
 def test_false_completion_top(self):
  self.specs[1]['semantic_closure']=True;self.reject('mixed_false_closure:')
 def test_false_completion_component(self):
  self.specs[1]['components'][0]['semantic_closure']=True;self.reject('mixed_false_closure:')
 def test_false_completion_accounting(self):
  self.specs[0]['candidates'][0]['source_line_accounting'][0]['meaning_coverage_proved']=True
  self.reject('mixed_false_closure:')
 def test_false_runtime_claim(self):
  self.specs[0]['scope']['runtime_implemented']=True;self.reject('mixed_false_closure:')
 def test_claimed_coverage_percent(self):
  self.specs[0]['scope']['coverage_percent']=100;self.reject('mixed_coverage_claim:')
 def test_non_draft_status(self):
  self.specs[1]['components'][0]['status']='proved';self.reject('mixed_component_status:')
 def test_root_without_reuse_atom(self):
  x=self.specs[1]['components'][0];x['hierarchy']='root_authority_contract';x['existing_atom_refs']=[]
  self.reject('mixed_unbacked_root_contract:')
 def test_invalid_modality(self):
  self.specs[1]['components'][0]['modality']='verified';self.reject('mixed_modality:')
 def test_missing_boundary_case(self):
  del self.specs[1]['components'][0]['boundary_case'];self.reject('mixed_case:')
 def test_missing_interpretation_limit(self):
  self.specs[1]['components'][0]['formal_relation'].pop('interpretation_limit');self.reject('mixed_formal_relation:')
 def test_line_accounting_omission(self):
  self.specs[1]['candidates'][0]['source_line_accounting'].pop();self.reject('mixed_line_accounting:')
 def test_line_accounting_foreign_component(self):
  self.specs[1]['candidates'][0]['source_line_accounting'][1]['component_ids']=['RMB-C00-001-01']
  self.reject('mixed_line_reference:')
 def test_structural_label_cannot_hide_prose_line(self):
  x=self.specs[1]['candidates'][0]['source_line_accounting'][1]
  x['component_ids']=[];x['disposition']='structural_table_markup';self.reject('mixed_line_unaccounted:')
 def test_residual_quote_tampering(self):
  x=self.specs[1]['candidates'][0]['source_text_accounting'][0]['residual_segments'][0]
  x['excerpt']='forged';x['excerpt_sha256']=audit.text_hash('forged');self.reject('mixed_residual_excerpt:')
 def test_pdf_quote_forgery_even_with_matching_quote_hash(self):
  x=self.specs[0]['supporting_pdf_anchors'][0];x['excerpt']='The winner never receives a wager.'
  x['excerpt_sha256']=audit.text_hash(x['excerpt']);self.reject('mixed_pdf_excerpt:')
 def test_invalid_read_range(self):
  s=next(s for s in self.specs[1]['source_snapshots'] if s['file'].startswith('input/'))
  s['direct_source_read_ranges']=[[0,1]];self.reject('mixed_read_range:')
 def test_path_escape_rejected(self):
  self.specs[1]['source_snapshots'][0]['file']='../../outside.json';self.reject('mixed_schema_error:')
 def test_source_file_change_without_new_snapshot(self):
  p=self.root/self.specs[1]['candidates'][0]['source_file'];original=p.read_bytes()
  try:
   p.write_bytes(original+b'\nsource changed\n');self.reject('mixed_file_hash:')
  finally:p.write_bytes(original)
 def test_scope_denominator_change(self):
  p=self.root/audit.SCOPES[1];original=p.read_bytes()
  try:
   s=audit.load(p);next(x for x in s['candidate_dispositions'] if x['category']=='mixed')['category']='guidance'
   p.write_text(json.dumps(s,ensure_ascii=False),encoding='utf-8');self.reject('mixed_scope_denominator')
  finally:p.write_bytes(original)
 def test_current_review_change(self):
  p=self.root/self.specs[1]['candidates'][0]['review_file'];original=p.read_bytes()
  try:
   s=audit.load(p);next(x for x in s['clauses'] if x['id']==self.specs[1]['candidates'][0]['candidate_id'])['statement']+=' changed'
   p.write_text(json.dumps(s,ensure_ascii=False),encoding='utf-8');self.reject('mixed_candidate_snapshot:')
  finally:p.write_bytes(original)
 def test_draft_paraphrase_is_not_frozen_as_semantic_oracle(self):
  # Intentional boundary: integrity allows a revised interpretation. It must be
  # independently reviewed; passing cannot certify that this paraphrase is true.
  self.specs[1]['components'][0]['statement']+=' (독립 검토용 설명 정리)'
  self.assertEqual(self.errors(),[])
 def test_legal_modality_edit_is_not_misrepresented_as_proof(self):
  self.specs[2]['components'][0]['modality']='permission'
  self.assertEqual(self.errors(),[])

class RecordingResult(unittest.TextTestResult):
 def __init__(self,*a,**k):super().__init__(*a,**k);self.rows=[]
 def addSuccess(self,t):super().addSuccess(t);self.rows.append({'test':t.id(),'passed':True})
 def addFailure(self,t,e):super().addFailure(t,e);self.rows.append({'test':t.id(),'passed':False,'kind':'failure','detail':self._exc_info_to_string(e,t)})
 def addError(self,t,e):super().addError(t,e);self.rows.append({'test':t.id(),'passed':False,'kind':'error','detail':self._exc_info_to_string(e,t)})
def main():
 global REAL_ROOT,REAL_PATHS
 ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,default=audit.ROOT);ap.add_argument('--spec',action='append',type=Path);ap.add_argument('--output',type=Path);a=ap.parse_args()
 REAL_ROOT=a.root.resolve();REAL_PATHS=a.spec
 paths=a.spec or [REAL_ROOT/p for p in audit.SPECS];specs=[audit.load(p) for p in paths]
 suite=unittest.defaultTestLoader.loadTestsFromTestCase(MixedTests)
 result=unittest.TextTestRunner(verbosity=1,resultclass=RecordingResult).run(suite)
 hashes=audit.input_hashes(specs,REAL_ROOT,paths);hashes['tools/test_root_mixed_decomposition.py']=audit.digest(__file__)
 report={'generated_at':datetime.now(timezone.utc).isoformat(),'kind':'adversarial_integrity_not_semantic_proof','input_hashes':hashes,'summary':{'passed':result.wasSuccessful(),'tests_run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors)},'results':[{'id':'MIXED-INTEGRITY-'+row['test'].rsplit('.',1)[-1],'status':'pass' if row['passed'] else 'error' if row.get('kind')=='error' else 'fail',**({'detail':row['detail']} if 'detail' in row else {})} for row in result.rows],'semantic_closure':False,'limitations':['Draft statement and legal modality edits are not semantic assertions by this checker.','Optional guard checks protect explicitly reviewed adoption metadata, not every possible source condition.']}
 out=a.output or REAL_ROOT/'output/root-mixed-decomposition-tests.json';out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 return 0 if result.wasSuccessful() else 1
if __name__=='__main__':raise SystemExit(main())

