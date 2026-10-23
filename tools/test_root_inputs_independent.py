"""Independent TR03/TR04/I11 boundary tests, not natural-language authority proof."""
import sys,json,hashlib,unittest,copy
from pathlib import Path
from dataclasses import replace
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from engine import root_inputs as I
H=lambda s:hashlib.sha256(s.encode()).hexdigest()
def binding(**kw):
 d=dict(event_id='e',event_hash=H('event'),profile_hash=H('profile'),revision=2,context_hash=H('context'));d.update(kw);return I.Binding(**d)
def choice(**kw):
 d=dict(id='choice-1',binding=binding(),purpose='select allowed target',source_refs=('model-request-not-source-proof',),mode='synthetic',chooser_ids=('owner',),domain=('left','right'));d.update(kw);return I.ChoiceRequest(**d)
def roll(**kw):
 d=dict(id='roll-1',binding=binding(),purpose='skill check',source_refs=('model-roll-not-source-proof',),mode='synthetic',supplier_ids=('owner',),count=2,sides=6,distribution='independent_uniform_faces');d.update(kw);return I.RollRequest(**d)
def fixture(*requests):
 requests=requests or (choice(),);owner=I.Principal('owner');other=I.Principal('other');policy=I.TrustedPolicy('test-policy',requests[0].mode,{q.id:I.request_fingerprint(q)for q in requests});b=I.Broker(policy,(owner,other));return b,owner,other,[b.register(q)for q in requests]
class Independent(unittest.TestCase):
 def accepted(self,r):self.assertIs(type(r),I.AcceptedReceipt);return r
 def finding(self,r,code=None):
  self.assertIs(type(r),I.Finding)
  if code:self.assertEqual(r.code,code)
 def test_01_choice_positive_receipt(self):
  q=choice();b,p,_,hs=fixture(q);r=self.accepted(b.accept(hs[0],p,'left',q.binding));self.assertEqual(r.evidence_kind,'source_choice');self.assertEqual(b.validate_receipt(hs[0],r,q.binding),'left')
 def test_02_exact_numeric_finite_domain_boundaries(self):
  for v in [1,3]:
   q=choice(domain=(1,2,3));b,p,_,hs=fixture(q);self.accepted(b.accept(hs[0],p,v,q.binding))
  for v in [0,4]:
   q=choice(domain=(1,2,3));b,p,_,hs=fixture(q);self.finding(b.accept(hs[0],p,v,q.binding),'OutsideDomain')
 def test_03_bool_is_not_integer_choice(self):
  for domain,value in [((1,),True),((True,),1),((0,),False),((False,),0),((1,),1.0)]:
   q=choice(domain=domain);b,p,_,hs=fixture(q);self.finding(b.accept(hs[0],p,value,q.binding),'OutsideDomain')
 def test_04_nested_exact_json_types(self):
  for domain,value in [(([1],),[True]),(({'x':1},),{'x':True}),(({'x':[True]},),{'x':[1]})]:
   q=choice(domain=domain);b,p,_,hs=fixture(q);self.finding(b.accept(hs[0],p,value,q.binding),'OutsideDomain')
 def test_05_object_key_order_and_array_order(self):
  q=choice(domain=({'a':1,'b':[2,3]},));b,p,_,hs=fixture(q);r=self.accepted(b.accept(hs[0],p,{'b':[2,3],'a':1},q.binding));self.assertEqual(I.plain(r.value),{'a':1,'b':[2,3]})
  q=choice(domain=([1,2],));b,p,_,hs=fixture(q);self.finding(b.accept(hs[0],p,[2,1],q.binding),'OutsideDomain')
 def test_06_object_extra_key_rejected(self):
  q=choice(domain=({'a':1},));b,p,_,hs=fixture(q);self.finding(b.accept(hs[0],p,{'a':1,'extra':0},q.binding),'OutsideDomain')
 def test_07_null_false_zero_are_valid_distinct_choices(self):
  for v in [None,False,0]:
   q=choice(domain=(None,False,0));b,p,_,hs=fixture(q);r=self.accepted(b.accept(hs[0],p,v,q.binding));self.assertIs(type(r.value),type(v))
 def test_08_wrong_scoped_principal(self):
  q=choice();b,p,other,hs=fixture(q);self.finding(b.accept(hs[0],other,'left',q.binding),'RejectedAuthority');self.accepted(b.accept(hs[0],p,'left',q.binding))
 def test_09_same_name_uninstalled_principal_rejected(self):
  q=choice();b,p,_,hs=fixture(q);self.finding(b.accept(hs[0],I.Principal(p.id),'left',q.binding),'RejectedAuthority')
 def test_10_unpinned_request_and_label_do_not_admit(self):
  q=choice(mode='source',source_refs=('source_reviewed:true','approved-namespace'));p=I.Principal('owner');b=I.Broker(I.TrustedPolicy('source-label','source',{}),(p,));self.finding(b.register(q),'PendingAuthority')
 def test_11_mode_mismatch_rejected(self):
  q=choice(mode='source');b=I.Broker(I.TrustedPolicy('p','synthetic',{q.id:I.request_fingerprint(q)}),(I.Principal('owner'),));self.finding(b.register(q),'PendingAuthority')
 def test_12_uninstalled_request_actor_pending(self):
  q=choice();b=I.Broker(I.TrustedPolicy('p','synthetic',{q.id:I.request_fingerprint(q)}),());self.finding(b.register(q),'PendingAuthority')
 def test_13_changed_request_purpose_domain_authority_not_pinned(self):
  q=choice();b,_,_,_=fixture(q)
  for changed in [replace(q,purpose='other purpose'),replace(q,domain=('third',)),replace(q,chooser_ids=('other',)),replace(q,source_refs=('other-source',))]:self.finding(b.register(changed),'PendingAuthority')
 def test_14_each_context_field_binding(self):
  q=choice();b,p,_,hs=fixture(q)
  for key,value in [('event_id','other'),('event_hash',H('other-event')),('profile_hash',H('other-profile')),('revision',3),('context_hash',H('other-context'))]:self.finding(b.accept(hs[0],p,'left',replace(q.binding,**{key:value})),'StaleOrMismatchedContext')
  self.accepted(b.accept(hs[0],p,'left',q.binding))
 def test_15_revision_exact_type(self):
  for v in [True,False,2.0,-1]:
   with self.assertRaises(ValueError):binding(revision=v)
 def test_16_same_replay_identity_no_new_receipt(self):
  q=choice();b,p,_,hs=fixture(q);r=self.accepted(b.accept(hs[0],p,'left',q.binding));self.assertIs(b.accept(hs[0],p,'left',q.binding),r);self.assertIs(b.register(q),hs[0])
 def test_17_conflicting_replay_preserves_accepted(self):
  q=choice();b,p,_,hs=fixture(q);r=self.accepted(b.accept(hs[0],p,'left',q.binding));self.finding(b.accept(hs[0],p,'right',q.binding),'ConflictingReplay');self.assertEqual(b.validate_receipt(hs[0],r,q.binding),'left')
 def test_18_new_request_same_value_allowed(self):
  a=choice();z=choice(id='choice-2');b,p,_,hs=fixture(a,z);x=self.accepted(b.accept(hs[0],p,'left',a.binding));y=self.accepted(b.accept(hs[1],p,'left',z.binding));self.assertIsNot(x,y);self.assertNotEqual(x.request_id,y.request_id)
 def test_19_invalid_then_valid_not_consumed(self):
  q=choice();b,p,_,hs=fixture(q);self.finding(b.accept(hs[0],p,'invalid',q.binding),'OutsideDomain');self.accepted(b.accept(hs[0],p,'right',q.binding))
 def test_20_roll_positive_count_faces_and_order(self):
  q=roll();b,p,_,hs=fixture(q);r=self.accepted(b.accept(hs[0],p,[1,6],q.binding));self.assertEqual(r.value,(1,6));self.assertEqual(r.evidence_kind,'randomness');self.assertEqual(b.validate_receipt(hs[0],r,q.binding),(1,6))
 def test_21_wrong_face_count_no_padding(self):
  for value in [[],[1],[1,2,3],1,'12']:
   q=roll();b,p,_,hs=fixture(q);self.finding(b.accept(hs[0],p,value,q.binding),'InvalidFaces');self.accepted(b.accept(hs[0],p,[1,6],q.binding))
 def test_22_faces_exact_integer_no_coercion(self):
  for face in [True,False,1.0,'1',None]:
   q=roll();b,p,_,hs=fixture(q);self.finding(b.accept(hs[0],p,[face,2],q.binding),'InvalidFaces')
 def test_23_face_range_no_clamping(self):
  for face in [0,-1,7]:
   q=roll();b,p,_,hs=fixture(q);self.finding(b.accept(hs[0],p,[face,2],q.binding),'InvalidFaces')
 def test_24_unknown_distribution_and_missing_purpose_no_default(self):
  for distribution in ['', 'unknown','advantage','weighted']:
   with self.assertRaises(ValueError):roll(distribution=distribution)
  with self.assertRaises(ValueError):roll(purpose='')
  for kw in [{'count':True},{'count':0},{'count':1.0},{'sides':True},{'sides':1}]:
   with self.assertRaises(ValueError):roll(**kw)
 def test_25_roll_fingerprint_binds_distribution_purpose_count_sides(self):
  q=roll();b,_,_,_=fixture(q)
  for altered in [replace(q,purpose='damage'),replace(q,count=3),replace(q,sides=20),replace(q,supplier_ids=('other',))]:self.finding(b.register(altered),'PendingAuthority')
 def test_26_roll_replay_no_reroll(self):
  q=roll();b,p,_,hs=fixture(q);r=self.accepted(b.accept(hs[0],p,[1,6],q.binding));self.assertIs(b.accept(hs[0],p,(1,6),q.binding),r);self.finding(b.accept(hs[0],p,[6,1],q.binding),'ConflictingReplay');self.assertEqual(b.validate_receipt(hs[0],r,q.binding),(1,6))
 def test_27_receipt_exact_issued_identity_and_handle(self):
  q=choice();b,p,_,hs=fixture(q);r=self.accepted(b.accept(hs[0],p,'left',q.binding));self.finding(b.validate_receipt(hs[0],replace(r),q.binding),'RejectedReceipt');self.finding(b.validate_receipt(I.Handle(q.id),r,q.binding),'RejectedHandle')
 def test_28_cross_broker_receipt_and_request_not_portable(self):
  q=choice();b,p,_,hs=fixture(q);z,zp,_,zs=fixture(q);r=self.accepted(b.accept(hs[0],p,'left',q.binding));self.finding(z.validate_receipt(zs[0],r,q.binding),'RejectedReceipt');self.finding(z.accept(hs[0],zp,'left',q.binding),'RejectedHandle')
 def test_29_receipt_stale_after_acceptance(self):
  q=choice();b,p,_,hs=fixture(q);r=self.accepted(b.accept(hs[0],p,'left',q.binding));self.finding(b.validate_receipt(hs[0],r,replace(q.binding,revision=3)),'StaleOrMismatchedContext')
 def test_30_source_mode_pin_is_not_certificate(self):
  q=choice(mode='source');b,p,_,hs=fixture(q);r=self.accepted(b.accept(hs[0],p,'left',q.binding));self.assertEqual(r.mode,'source');self.assertFalse(hasattr(r,'source_certified'));self.assertFalse(hasattr(r,'source_ready'))
 def test_31_json_values_detached_from_caller_and_immutable(self):
  original={'v':[1,2]};q=choice(domain=(original,));original['v'][0]=99;b,p,_,hs=fixture(q);payload={'v':[1,2]};r=self.accepted(b.accept(hs[0],p,payload,q.binding));payload['v'][0]=77;self.assertEqual(I.plain(r.value),{'v':[1,2]})
  with self.assertRaises(TypeError):r.value['other']=1
 def test_32_unsupported_json_no_fallback(self):
  for value in [float('nan'),float('inf'),object(),{1:'not-string'}]:
   q=choice();b,p,_,hs=fixture(q);self.finding(b.accept(hs[0],p,value,q.binding),'OutsideDomain');self.accepted(b.accept(hs[0],p,'left',q.binding))
 def test_33_empty_or_ambiguous_domain_no_default(self):
  for domain in [(),(1,1),({'a':1,'b':2},{'b':2,'a':1})]:
   with self.assertRaises(ValueError):choice(domain=domain)
 def test_34_scoped_two_choosers_conflicting_delivery(self):
  q=choice(chooser_ids=('owner','other'));b,p,o,hs=fixture(q);r=self.accepted(b.accept(hs[0],p,'left',q.binding));self.finding(b.accept(hs[0],o,'left',q.binding),'ConflictingReplay');self.assertEqual(b.validate_receipt(hs[0],r,q.binding),'left')
 def test_35_shared_kernel_json_subset(self):
  for alternative in [1.5,{"":1},{"x":[1.5]}]:
   with self.assertRaises(TypeError):choice(domain=(alternative,))
  q=choice(domain=({"numerator":1,"denominator":2},));b,p,_,hs=fixture(q);self.accepted(b.accept(hs[0],p,{"numerator":1,"denominator":2},q.binding))
class Results(unittest.TextTestResult):
 def __init__(self,*a,**kw):super().__init__(*a,**kw);self.records=[]
 def addSuccess(self,t):super().addSuccess(t);self.records.append({'id':'ROOTINPUT-INDEPENDENT-'+t._testMethodName,'status':'pass'})
 def addFailure(self,t,e):super().addFailure(t,e);self.records.append({'id':'ROOTINPUT-INDEPENDENT-'+t._testMethodName,'status':'fail','detail':self._exc_info_to_string(e,t)})
 def addError(self,t,e):super().addError(t,e);self.records.append({'id':'ROOTINPUT-INDEPENDENT-'+t._testMethodName,'status':'error','detail':self._exc_info_to_string(e,t)})
if __name__=='__main__':
 result=unittest.TextTestRunner(verbosity=1,resultclass=Results).run(unittest.defaultTestLoader.loadTestsFromTestCase(Independent))
 paths=['engine/root_inputs.py','tools/test_root_inputs_independent.py','data/verification/topdown-root-contract.json']
 report={'results':result.records,'input_hashes':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest()for p in paths},'summary':{'run':result.testsRun,'pass':sum(x['status']=='pass'for x in result.records),'fail':len(result.failures),'error':len(result.errors)},'scope':'Pure scoped input validation and in-process receipt ledger; no kernel gameplay consumer, source authority certification, native RNG fairness or durable snapshot restoration claimed.','kernel_integration_tested':False,'source_truth_proven':False,'whole_engine_complete':False}
 (ROOT/'output/root-input-independent-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8');sys.exit(not result.wasSuccessful())
