"""External JSON declarations use native grouped payment invariants."""
from pathlib import Path
from copy import copy, deepcopy
from hashlib import sha256
import json, sys, unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from engine import Rules, Engine, Combatant
from state_codec import dump_engine, load_engine
import state_grants as G
import world_entities as W

class PolicyGrantTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls): cls.rules=Rules(ROOT,ruleset='core')
 def setUp(self):
  self.r=copy(self.rules);self.r.ruleset=deepcopy(self.rules.ruleset)
  self.r.selection=copy(self.rules.selection);self.r.selection.filter=self.r.ruleset
  self.e=Engine(self.r,716)
  def make(uid,kind): return Combatant(self.r,{'id':uid,'name':uid,'kind':kind,'level':10,
   'stats':{'hp':10,'atk':10,'def':10,'spa':10,'spd':10,'spe':10},'moves':[],'abilities':[],
   'skills':{},'movement':{'land':5},'tutor_points':3})
  self.a=make('trainer/owner','trainer');self.c=make('pokemon/target','pokemon')
  self.c.spec['trainer_id']=self.a.entity_id;self.e.everyone=self.e.gm.everyone=[self.a,self.c]
  source=self.r.selection.units['combat/struggle']['source']['file']
  self.source={'file':'input/'+source,'sha256':sha256((ROOT/'input'/source).read_bytes()).hexdigest()}
  self.op={'type':'acquire','group_id':'group/one','points':1,'reason':'synthetic host ruling',
   'owner_id':self.a.entity_id,'lifetime':'your_pokemon','grants':[
    {'source_id':'child/'+x,'field':'capabilities','value':'cap/'+x} for x in 'ab']}
 def doc(self,op,uid='policy/acquire',inputs=None):
  return {'schema':1,'id':uid,'variants':[{'rule_id':'combat/struggle','source':deepcopy(self.source),
   'values':{'grant_operation':deepcopy(op)},'inputs':inputs or {}}]}
 def load(self,doc):
  self.r.load_source_policy_package(json.dumps({'schema':1,'sources':[],'policies':[doc]}))
  return self.r.source_policy_document(doc['id'])
 def run_policy(self,doc,**kw): return self.e.execute_source_policy_grants(self.a,self.c,doc,**kw)
 def refund(self):return {'type':'refund','sources':['child/a','child/b'],'request_id':'refund/one','reason':'withdraw'}
 def test_json_acquire_refund_replay_and_saved_evidence(self):
  buy=self.load(self.doc(self.op));sell=self.load(self.doc(self.refund(),'policy/refund'))
  result=self.run_policy(buy)
  self.assertEqual(result['status'],'PolicyGrantsCompleted');self.assertFalse(result['effects_executed'])
  self.assertEqual(self.c.spec['tutor_points'],2);self.assertIn('cap/a',G.effective(self.c,'capabilities'))
  self.assertEqual(result['grant_result']['rule_id'],'combat/struggle')
  self.run_policy(buy);self.assertEqual(self.c.spec['tutor_points'],2)
  receipt=self.run_policy(sell);self.assertEqual(receipt['grant_result']['tutor_points_refunded'],1)
  self.run_policy(sell);self.assertEqual(self.c.spec['tutor_points'],3)
  restored=load_engine(self.r,dump_engine(self.e));actors=W.actor_index(restored)
  self.assertEqual(restored.source_policy_execution(result['execution_id']),result)
  restored.execute_source_policy_grants(actors[self.a.entity_id],actors[self.c.entity_id],buy)
  self.assertNotIn('cap/a',G.effective(actors[self.c.entity_id],'capabilities'))
  self.assertEqual(actors[self.c.entity_id].spec['tutor_points'],3)
  receipt['grant_result']['sources'].clear()
  self.assertEqual(len(self.e.source_policy_execution(receipt['execution_id'])['grant_result']['sources']),2)
 def test_acquisition_registers_persistent_withdrawal_data_and_replays_after_removal(self):
  self.op['withdrawal_policies']={key:{'provider_loss':{'allowed':True,'refund_mode':'none'}} for key in ('child/a','child/b')}
  doc=self.load(self.doc(self.op));before=dump_engine(self.e)
  with self.assertRaisesRegex(ValueError,'durable request'):self.run_policy(doc)
  self.assertEqual(dump_engine(self.e),before)
  out=self.run_policy(doc,request_id='policy-bound-acquire')
  self.assertEqual(out['withdrawal_policies'],self.op['withdrawal_policies'])
  e=load_engine(self.r,dump_engine(self.e));a,c=e.everyone
  cleanup=G.revoke_owner(e,c,a.entity_id,'ownership ended')
  self.assertEqual(cleanup['tutor_points_refunded'],0);self.assertEqual(c.spec['tutor_points'],2)
  before=dump_engine(e)
  replay=e.execute_source_policy_grants(a,c,doc,request_id='policy-bound-acquire')
  self.assertTrue(replay['replayed']);self.assertEqual(dump_engine(e),before)
  changed=deepcopy(doc);changed['variants'][0]['values']['grant_operation']['withdrawal_policies']['child/a']['provider_loss']['refund_mode']='actual'
  with self.assertRaises(ValueError):e.execute_source_policy_grants(a,c,changed,request_id='policy-bound-acquire')
  self.assertEqual(dump_engine(e),before)
 def test_invalid_withdrawal_bindings_never_debit_or_publish(self):
  cases=[{}, {'unknown':{'expiry':{'allowed':True,'refund_mode':'none'}}},
   {'child/a':{}}, {'child/a':{'expiry':{'allowed':'yes','refund_mode':'none'}}}]
  for bindings in cases:
   with self.subTest(bindings=bindings):
    op=deepcopy(self.op);op['withdrawal_policies']=bindings;doc=self.doc(op)
    before=dump_engine(self.e)
    with self.assertRaises(ValueError):self.run_policy(doc,request_id='bad-binding')
    self.assertEqual(dump_engine(self.e),before)
    published=deepcopy(getattr(self.r,'_source_policy_documents',{}))
    with self.assertRaises(ValueError):self.load(doc)
    self.assertEqual(getattr(self.r,'_source_policy_documents',{}),published)

 def test_definition_input_checks_candidate_before_actual_payment_and_replay(self):
  from unittest.mock import patch
  uid=next(uid for uid,u in self.r.selection.units.items() if uid.startswith('ability/') and u.get('title')=='급류')
  self.op['grants']=[{'source_id':'child/chosen','field':'abilities','value':{'$input':'choice'}}]
  doc=self.load(self.doc(self.op,inputs={'choice':{'type':'string','authority':'context','definition_kind':'ability','choices':[uid],'question':'Choose the host-approved grant definition'}}))
  before=dump_engine(self.e)
  with self.assertRaises(ValueError):self.run_policy(doc,request_id='chosen-grant',context={'choice':'ability/not-allowed'})
  self.assertEqual(dump_engine(self.e),before)
  source_path=(ROOT/'input'/self.r.selection.units[uid]['source']['file']).resolve()
  native=Path.read_bytes
  def changed(path):return native(path)+(b'changed' if path.resolve()==source_path else b'')
  with patch.object(Path,'read_bytes',changed):
   with self.assertRaisesRegex(ValueError,'changed'):self.run_policy(doc,request_id='chosen-grant',context={'choice':uid})
  self.assertEqual(dump_engine(self.e),before)
  out=self.run_policy(doc,request_id='chosen-grant',context={'choice':uid})
  self.assertEqual(out['status'],'PolicyGrantsCompleted');self.assertEqual(self.c.spec['tutor_points'],2)
  self.assertIn('급류',self.c.abilities)
  restored=load_engine(self.r,dump_engine(self.e));actors=W.actor_index(restored);before=dump_engine(restored)
  replay=restored.execute_source_policy_grants(actors[self.a.entity_id],actors[self.c.entity_id],doc,request_id='chosen-grant',context={'choice':uid})
  self.assertTrue(replay['replayed']);self.assertEqual(dump_engine(restored),before)
  with patch.object(Path,'read_bytes',changed):
   with self.assertRaisesRegex(ValueError,'changed'):restored.execute_source_policy_grants(actors[self.a.entity_id],actors[self.c.entity_id],doc,request_id='chosen-grant',context={'choice':uid})
  self.assertEqual(dump_engine(restored),before)
 def test_pending_and_not_applicable_have_no_payments_or_evidence(self):
  self.op['points']={'$input':'cost'}
  doc=self.load(self.doc(self.op,inputs={'cost':{'type':'integer','authority':'gm','question':'Total cost?'}}))
  before=dump_engine(self.e);self.assertEqual(self.run_policy(doc)['status'],'PolicyInputsRequired')
  self.assertEqual(dump_engine(self.e),before)
  declined=deepcopy(doc);declined['variants'][0]['when']=False
  self.assertEqual(self.run_policy(declined)['status'],'PolicyNotApplicable')
  self.assertEqual(dump_engine(self.e),before)
  self.run_policy(doc,decisions={'cost':{'value':1,'reason':'explicit cost'}})
  self.assertEqual(self.c.spec['tutor_points'],2)
 def test_late_native_failure_rolls_back_all_state_and_policy_evidence(self):
  self.op['grants'].append({'source_id':'child/bad','field':'moves','value':'move/nonexistent','learning_route':'taught'})
  doc=self.load(self.doc(self.op));before=dump_engine(self.e)
  with self.assertRaises(ValueError):self.run_policy(doc)
  self.assertEqual(dump_engine(self.e),before)
 def test_unknown_allocation_cannot_be_invented_by_json_adapter(self):
  self.run_policy(self.load(self.doc(self.op)))
  op=self.refund();op['sources']=['child/a'];doc=self.doc(op,'policy/partial')
  before=dump_engine(self.e)
  from source_policy import PolicyExecutionPending
  with self.assertRaisesRegex(PolicyExecutionPending,'explicit allocation required'):self.run_policy(doc)
  self.assertEqual(dump_engine(self.e),before)
  op['allocations']={'group/one':{'child/a':{'$input':'share'},'child/b':0}}
  doc=self.load(self.doc(op,'policy/allocated',{'share':{'type':'integer','authority':'gm','question':'Chosen share?'}}))
  self.run_policy(doc,decisions={'share':{'value':1,'reason':'explicit allocation'}})
  self.assertEqual(self.c.spec['tutor_points'],3);self.assertIn('cap/b',G.effective(self.c,'capabilities'))
 def test_bad_package_operations_never_publish_a_partial_package(self):
  cases=[]
  for changes in [{'type':'unknown'},{'rule_id':'combat/other'},{'points':True},{'grants':[]},{'owner_id':12}]:
   cases.append(dict(self.op,**changes))
  for op in cases:
   with self.subTest(op=op):
    before=deepcopy(getattr(self.r,'_source_policy_documents',{}))
    package={'schema':1,'sources':[],'policies':[self.doc(self.op,'valid'),self.doc(op,'bad')]}
    with self.assertRaises(ValueError):self.r.load_source_policy_package(json.dumps(package))
    self.assertEqual(getattr(self.r,'_source_policy_documents',{}),before)
  self.op['points']={'$input':'cost'}
  with self.assertRaisesRegex(ValueError,'input type mismatch'):
   self.load(self.doc(self.op,inputs={'cost':{'type':'string','authority':'context','question':'Cost?'}}))
 def test_stale_source_and_profile_cannot_replay_a_payment(self):
  doc=self.load(self.doc(self.op));self.run_policy(doc);before=dump_engine(self.e)
  stale=deepcopy(doc);stale['variants'][0]['source']['sha256']='0'*64
  with self.assertRaisesRegex(ValueError,'source changed'):self.run_policy(stale)
  self.assertEqual(dump_engine(self.e),before)
  self.r.ruleset.exclude_units.add('combat/struggle')
  with self.assertRaises(ValueError):self.run_policy(doc)
  self.r.ruleset.exclude_units.remove('combat/struggle')
  self.assertEqual(dump_engine(self.e),before)
 def test_actual_participants_required_and_effect_entry_cannot_execute_grants(self):
  doc=self.load(self.doc(self.op));before=dump_engine(self.e)
  fake=copy(self.c)
  with self.assertRaises(ValueError):self.e.execute_source_policy_grants(self.a,fake,doc)
  with self.assertRaises(ValueError):self.e.execute_source_policy_effects(self.a,self.c,doc)
  self.assertEqual(dump_engine(self.e),before)

 def test_json_stat_investment_uses_typed_delta_and_native_refund(self):
  self.op['grants']=[{'source_id':'child/stat','field':'stats','stat':'atk','delta':{'$input':'delta'},'minimum':1}]
  doc=self.load(self.doc(self.op,inputs={'delta':{'type':'integer','authority':'gm','question':'Declared stat change?'}}))
  before=dump_engine(self.e);self.assertEqual(self.run_policy(doc)['status'],'PolicyInputsRequired')
  self.assertEqual(dump_engine(self.e),before)
  self.run_policy(doc,decisions={'delta':{'value':-20,'reason':'synthetic bounded contribution'}})
  self.assertEqual(self.c.stats['atk'],1);self.assertEqual(self.c.spec['stats']['atk'],10)
  op=self.refund();op['sources']=['child/stat']
  self.run_policy(self.load(self.doc(op,'policy/stat-refund')))
  self.assertEqual(self.c.stats['atk'],10);self.assertEqual(self.c.spec['tutor_points'],3)

 def test_json_skill_modifier_admission_execution_and_withdrawal(self):
  self.c.spec['skills']={'육상':'3d6+2'}
  self.op['grants']=[{'source_id':'child/skill','field':'skill_modifier','skill':{'$input':'skill'},'delta':{'$input':'delta'}}]
  doc=self.load(self.doc(self.op,inputs={'skill':{'type':'string','authority':'context','question':'Skill?'},
   'delta':{'type':'integer','authority':'gm','question':'Fixed modifier?'}}))
  self.run_policy(doc,context={'skill':'athletics'},decisions={'delta':{'value':3,'reason':'explicit modifier'}})
  self.assertEqual(self.e.skill_roll(self.c,'athletics',fixed=[2,2,2]).total,11)
  op=self.refund();op['sources']=['child/skill']
  self.run_policy(self.load(self.doc(op,'policy/skill-refund')))
  self.assertEqual(self.e.skill_roll(self.c,'athletics',fixed=[2,2,2]).total,8)

if __name__=='__main__':unittest.main()
