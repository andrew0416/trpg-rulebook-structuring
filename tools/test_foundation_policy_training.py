"""Source-bound group training reuses native admission, rewards and replay."""
from pathlib import Path
from hashlib import sha256
from copy import copy,deepcopy
from unittest.mock import patch
import sys,json,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_progression_state as fixtures
from builder import build_pokemon
from state_codec import dump_engine,load_engine
import pokemon_progression as P,downtime as D,world_entities as W

class PolicyTrainingTests(unittest.TestCase):
 setUpClass=classmethod(fixtures.ProgressionStateTests.setUpClass.__func__)
 add=fixtures.ProgressionStateTests.add
 def setUp(self):
  fixtures.ProgressionStateTests.setUp(self);self.e.r=self.r=copy(self.r);self.a.r=self.r
  self.ps=[self.add(build_pokemon(self.r,'이상해씨',5,moves=[],abilities=[],extra={'trainer_id':self.a.entity_id})) for _ in range(2)]
  self.op={'safe':True,'kind':'experience','targets':[{'$input':'first'},{'$input':'second'}]}
  path='input/'+self.r.selection.units[P.TRAINING]['source']['file']
  self.doc={'schema':1,'id':'group-training','variants':[{'rule_id':P.TRAINING,'source':{'file':path,'sha256':sha256((ROOT/path).read_bytes()).hexdigest()},
    'inputs':{k:{'type':'string','authority':'context','question':'Actual target identity'} for k in ('first','second')},'values':{'training_operation':self.op}}]}
  self.context=dict(zip(('first','second'),[p.entity_id for p in self.ps]))
 def run_policy(self,**kwargs):return self.e.execute_source_policy_training(self.a,self.doc,context=self.context,**kwargs)
 def load(self):
  self.r.load_source_policy_package(json.dumps({'schema':1,'sources':[],'policies':[self.doc]}))
  self.doc=self.r.source_policy_document('group-training');self.op=self.doc['variants'][0]['values']['training_operation']
 def test_pending_then_group_xp_replays_after_save_without_second_hour(self):
  self.load();before=dump_engine(self.e)
  self.assertEqual(self.e.execute_source_policy_training(self.a,self.doc)['status'],'PolicyInputsRequired');self.assertEqual(before,dump_engine(self.e))
  out=self.run_policy(request_id='group/one');self.assertEqual(out['status'],'PolicyTrainingCompleted');self.assertFalse(out['effects_executed'])
  self.assertEqual(out['training_target_ids'],[p.entity_id for p in self.ps]);self.assertEqual(out['training_result']['awards'],[7,7])
  self.assertEqual([p.spec['exp'] for p in self.ps],[47,47]);self.assertEqual(self.e.elapsed_seconds,3600)
  restored=load_engine(self.r,dump_engine(self.e));actor=W.actor_index(restored)[self.a.entity_id];before=dump_engine(restored)
  result=restored.execute_source_policy_training(actor,self.doc,context=self.context,request_id='group/one')
  self.assertTrue(result['replayed']);self.assertEqual(before,dump_engine(restored))
  before=dump_engine(self.e)
  with self.assertRaises(ValueError):self.run_policy(request_id='group/two')
  self.assertEqual(before,dump_engine(self.e))
 def test_groom_then_xp_reuses_shared_hour_and_records_each_consumption(self):
  self.a.spec['edges']=['edge/미용사'];self.a.spec['items']['미용사 킷']=1
  self.op['kind']='groom';self.load();self.run_policy(request_id='groom')
  self.op.update(kind='experience',from_grooming=True,bonus_skill='포켓몬학')
  self.run_policy(request_id='groomed-xp');self.assertEqual(self.e.elapsed_seconds,3600)
  for p in self.ps:self.assertEqual(p.spec['training_credit']['applications'],['experience_training'])
  self.op['use_reserves']=True;self.a.spec['edges'].append('edge/예비-훈련');before=dump_engine(self.e)
  with self.assertRaisesRegex(ValueError,'cannot replace'):self.run_policy(request_id='bad-combination')
  self.assertEqual(before,dump_engine(self.e))
 def test_late_second_target_failure_rolls_back_whole_group_and_request(self):
  self.load();before=dump_engine(self.e);native=D.gain_exp_combatant
  def fail(e,c,amount):
   out=native(e,c,amount)
   if c.entity_id==self.ps[1].entity_id:raise ValueError('late second award')
   return out
  with patch.object(D,'gain_exp_combatant',side_effect=fail):
   with self.assertRaisesRegex(ValueError,'late second award'):self.run_policy(request_id='retry')
  self.assertEqual(before,dump_engine(self.e));self.assertFalse(self.run_policy(request_id='retry')['replayed'])
 def test_missing_duplicate_other_owner_and_unconscious_trainer_reject(self):
  self.load();original=deepcopy(self.context)
  for bad in ('missing',self.ps[0].entity_id):
   self.context['second']=bad;before=dump_engine(self.e)
   with self.assertRaises(ValueError):self.run_policy()
   self.assertEqual(before,dump_engine(self.e))
  self.context=original;self.ps[1].spec['trainer_id']='not-owner';before=deepcopy((self.ps[0].spec,self.ps[1].spec,self.e.elapsed_seconds))
  with self.assertRaises(ValueError):self.run_policy()
  self.assertEqual(before,(self.ps[0].spec,self.ps[1].spec,self.e.elapsed_seconds))
  self.ps[1].spec['trainer_id']=self.a.entity_id;self.a.hp=0;before=dump_engine(self.e)
  with self.assertRaisesRegex(ValueError,'conscious'):self.run_policy()
  self.assertEqual(before,dump_engine(self.e))
 def test_false_condition_and_changed_request_do_not_train(self):
  self.doc['variants'][0]['when']=False;before=dump_engine(self.e)
  self.assertEqual(self.run_policy()['status'],'PolicyNotApplicable');self.assertEqual(before,dump_engine(self.e))
  self.doc['variants'][0]['when']=True;self.run_policy(request_id='fixed')
  self.op['targets'].reverse();before=dump_engine(self.e)
  with self.assertRaisesRegex(ValueError,'changed input'):self.run_policy(request_id='fixed')
  self.assertEqual(before,dump_engine(self.e))
 def test_pushed_skill_choices_cover_actual_group_and_use_native_effect(self):
  import researcher_features as RF
  self.a.spec.update(classes=[RF.RESEARCHER],feats=[RF.PUSHER,RF.SKILL_TRAINER],feature_choices={RF.RESEARCHER:[['pokemon_caretaking','paleontology']]})
  self.op['pushed_skills']={self.ps[0].entity_id:'육상'};self.load();before=dump_engine(self.e)
  with self.assertRaisesRegex(ValueError,'match every actual'):self.run_policy(request_id='push')
  self.assertEqual(before,dump_engine(self.e));self.op['pushed_skills'][self.ps[1].entity_id]='육상'
  original=[deepcopy(p.spec['skills']) for p in self.ps];self.run_policy(request_id='push')
  self.assertEqual(self.a._action_history,['free'])
  for p,skills in zip(self.ps,original):
   self.assertEqual(p.spec['skills'],skills);self.assertEqual(p.spec['pushed_skill']['skill'],'athletics')
   self.assertEqual(p.spec['pushed_skill']['training_source'],'experience_training')
 def test_regime_choices_consume_grooming_time_and_native_session_replay(self):
  import training_features as T
  self.a.spec['feats']=[T.FOCUSED];self.a.spec['edges']=['edge/미용사'];self.a.spec['items']['미용사 킷']=1
  self.e.pokemon_activity(self.a,'groom',targets=self.ps,safe=True)
  self.op.update(kind='regime',features={p.entity_id:[T.FOCUSED] for p in self.ps},minutes=30,reason='completed hour regime',request_id='native-regime',from_grooming=True)
  self.load();out=self.run_policy(request_id='outer-regime');self.assertEqual(self.e.elapsed_seconds,3600)
  self.assertEqual(out['training_result']['time_cost_seconds'],0);self.assertTrue(all(T.bonus(p,'skill')==2 for p in self.ps))
  # A new outer delivery still cannot duplicate the native session.
  self.run_policy(request_id='second-delivery');self.assertEqual(self.e.elapsed_seconds,3600)
  self.assertTrue(all(p.spec['training_credit']['applications']==['training_regime'] for p in self.ps))
 def test_package_rejects_unknown_fields_shapes_and_types(self):
  for op in [{'safe':True,'kind':'groom','targets':[]},{'safe':True,'kind':'groom','targets':['x','x']},{'safe':True,'kind':'groom','targets':['x'],'from_grooming':True},
             {'safe':True,'kind':'experience','targets':['x'],'amount':100},{'safe':True,'kind':'experience','targets':['x'],'use_reserves':1},
             {'safe':True,'kind':'experience','targets':[{'$input':'first'}],'pushed_skills':[]}]:
   bad=deepcopy(self.doc);bad['variants'][0]['values']['training_operation']=op;before=deepcopy(getattr(self.r,'_source_policy_documents',{}))
   with self.subTest(op=op),self.assertRaises(ValueError):self.r.load_source_policy_package(json.dumps({'schema':1,'sources':[],'policies':[bad]}))
   self.assertEqual(before,getattr(self.r,'_source_policy_documents',{}))

if __name__=='__main__':unittest.main()
