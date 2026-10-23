"""External JSON teaching uses native qualification, costs and durable replay."""
from pathlib import Path
from hashlib import sha256
from copy import copy,deepcopy
from unittest.mock import patch
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_progression_state as fixtures
from builder import build_pokemon
from state_codec import dump_engine,load_engine
import world_entities as W,pokemon_teaching as T

class PolicyTeachingTests(unittest.TestCase):
 setUpClass=classmethod(fixtures.ProgressionStateTests.setUpClass.__func__)
 add=fixtures.ProgressionStateTests.add
 def setUp(self):
  fixtures.ProgressionStateTests.setUp(self)
  self.e.r=self.r=copy(self.r);self.a.r=self.r
  self.p=self.pokemon()
  self.doc=self.document(T.EDGE,{'safe':True,'kind':'edge','edge':T.EDGE,'skill':{'$input':'skill'}},
    {'skill':{'type':'string','authority':'context','question':'Selected skill'}})
 def pokemon(self,species='근육몬',level=35):
  return self.add(build_pokemon(self.r,species,level,moves=[],abilities=[],extra={'trainer_id':self.a.entity_id,'tutor_points':6}))
 def document(self,uid,op,inputs=None):
  path='input/'+self.r.selection.units[uid]['source']['file']
  return {'schema':1,'id':'teaching-policy','variants':[{'rule_id':uid,'source':{'file':path,'sha256':sha256((ROOT/path).read_bytes()).hexdigest()},'inputs':inputs or {},'values':{'teaching_operation':op}}]}
 def run_policy(self,**options):return self.e.execute_source_policy_teaching(self.a,self.p,self.doc,**options)
 def load(self):
  self.r.load_source_policy_package(json.dumps({'schema':1,'sources':[],'policies':[self.doc]}))
  self.doc=self.r.source_policy_document('teaching-policy')
 def test_native_edge_families_use_completed_common_jobs_and_receipts(self):
  import activity_jobs as J
  cases=[(T.EDGE,{'skill':'육상'}),('poke_edge/공격-충돌',{'stat':'atk'}),
   ('poke_edge/정확도-훈련',{'move_id':'메가톤펀치'}),('poke_edge/재능-훈련',{'capability':'power'}),
   ('poke_edge/고급-이동',{'capability':'land'}),('poke_edge/기본-원거리-공격',{'capability':'불쏘시개'}),
   ('poke_edge/투명-연장',{}),('poke_edge/tk-마스터리',{})]
  for source,choices in cases:
   with self.subTest(source=source):
    self.setUp();self.p.spec['capabilities']=['불쏘시개','투명','염력']
    with patch.object(J,'run_fixed',wraps=J.run_fixed) as shared:
     self.e.pokemon_activity(self.a,'teach_edge',target=self.p,edge=source,safe=True,**choices)
    self.assertEqual(shared.call_count,1)
    job=next(iter(self.e._activity_jobs['jobs'].values()));view=self.e.activity_job_status(job['id'])
    self.assertEqual((view['status'],view['source'],view['worked_seconds']),('complete',source,3600))
    self.assertEqual((view['owner_id'],view['participant_ids']),(self.a.entity_id,[self.p.entity_id]))
    self.assertEqual((self.e.elapsed_seconds,self.p.spec['tutor_points']),(3600,5))
    receipt=next(r for r in self.e.acquisition_receipts(self.p) if r['basis']=='native_learned_edge')
    self.assertEqual((receipt['provider_id'],receipt['debit']['amount']),(self.a.entity_id,1))
    restored=load_engine(self.r,dump_engine(self.e))
    self.assertEqual(restored.activity_job_status(job['id']),view)
 def test_late_common_job_failure_rolls_back_teaching_time_and_all_receipts(self):
  import activity_jobs as J
  before=dump_engine(self.e);rng=self.e.rng.getstate();run=J.run_fixed
  def fail_after_work(*args,**kw):
   run(*args,**kw)
   raise ValueError('failure after actual common work')
  with patch.object(J,'run_fixed',side_effect=fail_after_work):
   with self.assertRaisesRegex(ValueError,'after actual common work'):
    self.e.pokemon_activity(self.a,'teach_edge',target=self.p,edge='poke_edge/공격-충돌',stat='atk',safe=True)
  self.assertEqual(before,dump_engine(self.e));self.assertEqual(rng,self.e.rng.getstate())
 def test_pending_then_edge_cost_and_durable_request_replay(self):
  self.load();before=dump_engine(self.e)
  self.assertEqual(self.run_policy()['status'],'PolicyInputsRequired');self.assertEqual(before,dump_engine(self.e))
  opts={'context':{'skill':'육상'},'request_id':'teach-once'};out=self.run_policy(**opts)
  self.assertEqual(out['status'],'PolicyTeachingCompleted');self.assertFalse(out['effects_executed'])
  self.assertEqual(out['teaching_result']['point_cost'],1);self.assertEqual(self.p.spec['tutor_points'],5);self.assertEqual(self.e.elapsed_seconds,3600)
  restored=load_engine(self.r,dump_engine(self.e));actors=W.actor_index(restored);before=dump_engine(restored)
  replay=restored.execute_source_policy_teaching(actors[self.a.entity_id],actors[self.p.entity_id],self.doc,**opts)
  self.assertTrue(replay['replayed']);self.assertEqual(before,dump_engine(restored))
  with self.assertRaises(ValueError):self.run_policy(context={'skill':'전투'},request_id='teach-once')
  before=dump_engine(self.e)
  with self.assertRaises(ValueError):self.e.execute_source_policy_effects(self.a,self.p,self.doc,**opts)
  self.assertEqual(before,dump_engine(self.e))
 def test_native_machine_inventory_and_move_receipt(self):
  self.p=self.pokemon('브케인',32);self.a.spec['items']['TM35']=1
  T.register_machine(self.e,self.a,instance_id='tm',code='TM35')
  self.doc=self.document(T.MACHINES,{'kind':'machine','instance_id':'tm'});self.load()
  out=self.run_policy(request_id='machine-once')
  self.assertEqual(out['teaching_result']['point_cost'],1);self.assertIn('move/화염방사',self.p.spec['moves'])
  self.assertEqual(self.p.spec['tutor_points'],5);self.assertEqual(self.a.spec['items'].get('TM35',0),0)
  before=dump_engine(self.e);self.assertTrue(self.run_policy(request_id='machine-once')['replayed']);self.assertEqual(before,dump_engine(self.e))
 def test_native_mentor_permission_duration_and_nonowned_target(self):
  self.a.spec.update(feats=[T.MENTOR],skills={'매력':5,'포켓몬학':3});T.select_mentor_skills(self.e,self.a,['매력','포켓몬학'],reason='actual choice')
  self.p=self.pokemon('브케인',32);self.p.spec.pop('trainer_id')
  self.doc=self.document(T.MENTOR,{'kind':'feature','feature':T.MENTOR,'move_id':'화염방사','seconds':{'$input':'duration'},'reason':'observed Extended activity'},
    {'duration':{'type':'integer','authority':'gm','question':'Observed duration'}})
  self.load();before=dump_engine(self.e);self.assertEqual(self.run_policy()['status'],'PolicyInputsRequired');self.assertEqual(before,dump_engine(self.e))
  out=self.run_policy(decisions={'duration':{'value':60,'reason':'GM observed one minute'}},request_id='mentor-once')
  self.assertEqual(out['teaching_result']['classification'],'natural');self.assertEqual(self.e.elapsed_seconds,60);self.assertEqual(self.p.spec['tutor_points'],5)
 def test_qualification_false_condition_and_late_failure_leave_no_records(self):
  self.doc['variants'][0]['when']=False;before=dump_engine(self.e)
  self.assertEqual(self.run_policy(context={'skill':'육상'})['status'],'PolicyNotApplicable');self.assertEqual(before,dump_engine(self.e))
  self.doc['variants'][0]['when']=True;self.p.spec['trainer_id']='unresolved-owner'
  # Invalid owner is rejected by the native consumer; compare raw participant state.
  before=deepcopy((self.p.spec,self.e.elapsed_seconds,self.e.log_lines))
  with self.assertRaises(ValueError):self.run_policy(context={'skill':'육상'},request_id='retry')
  self.assertEqual(before,(self.p.spec,self.e.elapsed_seconds,self.e.log_lines));self.p.spec['trainer_id']=self.a.entity_id
  before=dump_engine(self.e);native=T._teach_edge
  def late(*args,**kwargs):native(*args,**kwargs);raise ValueError('late teaching failure')
  with patch.object(T,'_teach_edge',side_effect=late):
   with self.assertRaisesRegex(ValueError,'late teaching failure'):self.run_policy(context={'skill':'육상'},request_id='retry')
  self.assertEqual(before,dump_engine(self.e));self.assertFalse(self.run_policy(context={'skill':'육상'},request_id='retry')['replayed'])
 def test_declared_grooming_choice_requires_real_completed_credit(self):
  row=self.doc['variants'][0];row['inputs']['credit']={'type':'boolean','authority':'context','question':'Use completed grooming?'}
  row['values']['teaching_operation']['from_grooming']={'$input':'credit'};self.load()
  self.a.spec['edges']=['edge/미용사'];self.a.spec['items']['미용사 킷']=1
  options={'context':{'skill':'육상','credit':True},'request_id':'groomed-edge'};before=dump_engine(self.e)
  with self.assertRaises(ValueError):self.run_policy(**options)
  self.assertEqual(before,dump_engine(self.e))
  self.e.pokemon_activity(self.a,'groom',targets=[self.p],safe=True);self.run_policy(**options)
  self.assertEqual(self.e.elapsed_seconds,3600);self.assertEqual(self.p.spec['tutor_points'],5)
  self.assertEqual(len(self.p.spec['training_credit']['applications']),1)
 def test_cold_and_warm_variant_cache_have_same_save_identity_but_overrides_do_not(self):
  from state_codec import rules_fingerprint
  import poke_edge_variants as V
  for field in ('_poke_edge_variants','_poke_edge_variants_identity'):vars(self.r).pop(field,None)
  before=rules_fingerprint(self.r);V.catalog(self.r);self.assertEqual(before,rules_fingerprint(self.r))
  self.r._poke_edge_variants=deepcopy(self.r._poke_edge_variants);self.r._poke_edge_variants[0]['point_cost']=99
  self.assertNotEqual(before,rules_fingerprint(self.r))
 def test_invalid_static_package_is_not_published(self):
  for op in [{'kind':'unknown'},{'safe':True,'kind':'edge','edge':T.EDGE,'from_grooming':1},{'kind':'machine','instance_id':'tm','points':0},
             {'kind':'feature','feature':T.MENTOR,'move_id':'화염방사','seconds':True,'reason':'x'}]:
   with self.subTest(op=op):
    bad=self.document(T.EDGE,op);before=deepcopy(getattr(self.r,'_source_policy_documents',{}))
    with self.assertRaises(ValueError):self.r.load_source_policy_package(json.dumps({'schema':1,'sources':[],'policies':[bad]}))
    self.assertEqual(before,getattr(self.r,'_source_policy_documents',{}))

if __name__=='__main__':unittest.main()
