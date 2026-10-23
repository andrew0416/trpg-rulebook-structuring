"""Native Dietician ownership, permanent doses and current VM admission."""
from pathlib import Path
from copy import deepcopy
import sys,json,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from engine import Rules,Engine,Combatant
from builder import build_trainer,build_pokemon
import items as I,move_state as M,vitamin_capacity as V,vitamin_moves as SPECIAL
import pokemon_party as PARTY,state_grants as G,state_codec as C
from encounter import usable_moves

class DieticianStateTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(str(ROOT),ruleset='all')
 def setUp(self):
  self.e=Engine(self.r,seed=419)
  self.owner=self.trainer('chef',True)
  self.other=self.trainer('other',False)
  self.p=self.add(build_pokemon(self.r,'브케인',5,moves=[],abilities=[],extra={'trainer_id':self.owner.entity_id,'tutor_points':4}))
  self.q=self.add(build_pokemon(self.r,'브케인',5,moves=[],abilities=[],extra={'trainer_id':self.other.entity_id,'tutor_points':4}))
  PARTY.configure(self.e,self.owner,mode='unlimited',reason='actual full roster',roster=[self.p])
  PARTY.configure(self.e,self.other,mode='unlimited',reason='actual full roster',roster=[self.q])
 def add(self,spec):
  a=Combatant(self.r,spec);self.e.gm.add_combatant(a,pos=(0,0),side='party',reason='actual current sheet');return a
 def trainer(self,name,chef):
  return self.add(build_trainer(self.r,name,20,dict.fromkeys(('hp','atk','def','spa','spd','spe'),10),extra={'classes':[V.CHEF] if chef else [],'feats':[V.DIETICIAN] if chef else [],'skills':{'직감':5},'items':{'타우린':20,SPECIAL.HEART:3,SPECIAL.PP:3}}))
 def register(self):I.register_feats(self.e,self.owner)
 def dose(self,n,target=None):
  for _ in range(n):self.e.use_item(self.owner,'타우린',target or self.p)
 def vm(self,identity='actual-vm'):return M.observe_vm_learning(self.e,self.p,'냉동빔',application_id=identity,reason='GM observed completed actual VM application')
 def view(self):return M.vitamin_state(self.r,self.p.spec)
 def state(self):return deepcopy((self.e.rng.getstate(),[(a.spec,a._action_history if hasattr(a,'_action_history') else None) for a in self.e.everyone]))
 def transfer(self,target=None,new=None,old=None,identity='actual-transfer'):
  return PARTY.transfer(self.e,old or self.owner,target=target or self.p,new_owner=new or self.other,reason='observed voluntary actual ownership transfer',request_id=identity)
 def test_native_new_pokemon_registration_receives_only_its_actual_owner_source(self):
  self.assertEqual(self.view()['capacity'],7)
  self.assertEqual(M.vitamin_state(self.r,self.q.spec)['capacity'],5)
  self.assertEqual(self.view()['capacity_sources'][0]['owner_id'],self.owner.entity_id)
  self.assertEqual(self.r._selected_rule(V.CHEF),V.CHEF)
 def test_seven_actual_doses_eighth_no_effect_foreign_pokemon_stays_five(self):
  self.register();self.assertEqual(self.view()['capacity'],7)
  attack=self.p.spec['stats']['atk'];self.dose(8)
  self.assertEqual((len(self.p.spec['vitamins']),self.p.spec['stats']['atk']),(7,attack+7))
  self.assertEqual(len(self.p.spec[V.HISTORY]),7)
  other_attack=self.q.spec['stats']['atk'];self.dose(6,self.q)
  self.assertEqual((len(self.q.spec['vitamins']),self.q.spec['stats']['atk']),(5,other_attack+5))
  self.assertNotIn(V.HISTORY,self.q.spec)
 def test_actual_acquisition_and_multi_target_checks_precede_all_mutation(self):
  for field,value in [('classes',[]),('skills',{'직감':4})]:
   self.owner.spec.pop('dietician_acquisition',None)
   previous=deepcopy(self.owner.spec[field]);self.owner.spec[field]=value;before=self.state()
   with self.assertRaises(ValueError):self.register()
   self.assertEqual(self.state(),before);self.owner.spec[field]=previous
  before=self.state()
  with self.assertRaises(ValueError):I.register_feats(self.e,self.owner,[self.p,self.q])
  self.assertEqual(self.state(),before)
  self.register();self.assertEqual(self.owner.spec['dietician_acquisition']['intuition_rank'],5)
 def test_vm_ordinary_and_both_special_vitamins_share_seven_and_once_limits(self):
  self.register();self.vm();self.dose(4)
  self.e.use_item(self.owner,SPECIAL.HEART,self.p)
  self.e.use_item(self.owner,SPECIAL.PP,self.p,selected_move='냉동빔')
  self.assertEqual((self.view()['occupied'],self.view()['reserved'],self.p.spec['tutor_points']),(7,1,6))
  self.assertEqual((M.describe(self.r,self.p.spec)['slot_count'],M.describe(self.r,self.p.spec)['taught_count']),(2,2))
  before=deepcopy((self.p.spec['vitamins'],self.p.spec['stats'],self.p.spec[V.HISTORY]))
  self.dose(1);self.e.use_item(self.owner,SPECIAL.HEART,self.p)
  self.assertEqual((self.p.spec['vitamins'],self.p.spec['stats'],self.p.spec[V.HISTORY]),before)
 def test_transfer_retains_permanent_history_but_old_capacity_cannot_admit_new_vm(self):
  self.register();self.vm();self.dose(6);history=deepcopy(self.p.spec[V.HISTORY]);stats=deepcopy(self.p.spec['stats'])
  self.transfer();self.assertEqual((self.view()['capacity'],self.view()['historical_capacity'],self.view()['occupied']),(5,7,7))
  self.assertEqual(self.p.spec[V.HISTORY],history);self.assertEqual(self.p.spec['stats'],stats);self.assertIn('move/냉동빔',usable_moves(self.e,self.p))
  self.dose(1);self.assertEqual(len(self.p.spec['vitamins']),6)
  self.e.gm.set_move(self.p,'move/냉동빔',add=False,reason='explicit actual forgetting');before=self.state()
  with self.assertRaisesRegex(ValueError,'current Vitamin'):self.vm('new-application')
  self.assertEqual(self.state(),before)
  self.transfer(old=self.other,new=self.owner,identity='actual-return')
  self.assertEqual(self.view()['capacity'],7)
  self.vm('new-application');self.assertEqual(self.view()['occupied'],7)
 def test_native_owner_feature_end_preserves_doses_and_only_removes_its_current_capacity(self):
  self.register();self.vm();self.dose(6);before=deepcopy((self.p.spec['stats'],self.p.spec['vitamins'],self.p.spec[V.HISTORY]))
  self.owner.spec['feats']=[];I.register_feats(self.e,self.owner)
  self.assertEqual(self.view()['capacity'],5);self.assertEqual((self.p.spec['stats'],self.p.spec['vitamins'],self.p.spec[V.HISTORY]),before)
  self.owner.spec['feats']=[V.DIETICIAN];self.register();self.register()
  self.assertEqual(len(self.view()['capacity_sources']),1);self.assertEqual(self.p.spec[V.HISTORY],before[2])
 def test_gm_and_durable_restore_keep_actual_new_owner_and_permanent_application_source(self):
  self.register();self.dose(6);self.vm();self.e.gm.snapshot('dietician-before')
  self.transfer();self.e.gm.restore('dietician-before',reason='actual rewind');self.assertEqual(self.view()['capacity'],7)
  self.transfer();payload=json.loads(json.dumps(C.dump_engine(self.e),ensure_ascii=False));e=C.load_engine(self.r,payload)
  p=next(a for a in e.everyone if a.entity_id==self.p.entity_id)
  self.assertEqual(p.spec['trainer_id'],self.other.entity_id);self.assertEqual(M.vitamin_state(e.r,p.spec)['capacity'],5)
  self.assertEqual(M.vitamin_state(e.r,p.spec)['occupied'],7);self.assertEqual(p.spec[V.HISTORY],self.p.spec[V.HISTORY]);self.assertEqual(p.spec['stats'],self.p.spec['stats'])
 def test_bad_new_owner_prerequisite_does_not_partially_transfer_and_valid_source_applies_immediately(self):
  self.register();self.other.spec.update(feats=[V.DIETICIAN],classes=[V.CHEF],skills={'직감':4});before=self.state()
  with self.assertRaises(ValueError):self.transfer()
  self.assertEqual(self.state(),before)
  self.other.spec['skills']={'직감':5};self.transfer()
  source=self.view()['capacity_sources'];self.assertEqual(len(source),1);self.assertEqual(source[0]['owner_id'],self.other.entity_id)
  self.assertEqual(self.view()['capacity'],7)
 def test_tampered_historical_or_current_source_is_rejected_without_rewriting_history(self):
  self.register();self.vm();self.dose(1)
  original=deepcopy(self.p.spec)
  for field,value in [('maximum',7.0),('pokemon_id','someone-else'),('application_id','nonexistent')]:
   self.p.spec=deepcopy(original);self.p.spec[V.HISTORY][0][field]=value
   with self.assertRaises(ValueError):M.validate_actor(self.p)
  self.p.spec=deepcopy(original);key='feature:'+self.owner.entity_id+':'+V.DIETICIAN;self.p.spec[G.KEY]['sources'][key]['owner_id']=self.other.entity_id
  with self.assertRaises(ValueError):M.validate_actor(self.p)
  self.p.spec=original;M.validate_actor(self.p)

if __name__=='__main__':unittest.main()
