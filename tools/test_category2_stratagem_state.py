"""Actual Pinpoint native producer, source-owned AP and durable state consumers."""
from copy import deepcopy
from pathlib import Path
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from engine import Rules,Engine,Combatant
import combat_precision_features as CPF
import action_points as AP
import state_codec as CODEC
import items as ITEMS
import pokemon_party as PARTY

class StratagemStateTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(str(ROOT),ruleset='core')
 def setUp(self):
  self.e=Engine(self.rules,seed=96)
  self.a=self.actor('owner');self.p=self.actor('first','pokemon');self.q=self.actor('second','pokemon');self.foe=self.actor('foe')
  self.a.spec['feats']=[CPF.PRECISION]
  self.a.side=self.p.side=self.q.side='party';self.foe.side='wild'
  for p in (self.p,self.q):p.spec['trainer_id']=self.a.entity_id
  self.e.everyone=self.e.gm.everyone=[self.a,self.p,self.q,self.foe]
  ITEMS.register_feats(self.e,self.a)
  for target in (self.p,self.q):
   self.e.gm.observe_sensory_environment(self.a,target,paths={'auditory':True},present=True,reason='actual allied recipient hears the current Pinpoint Order')
 def actor(self,name,kind='trainer'):
  return Combatant(self.rules,dict(name=name,kind=kind,level=20,stats={'hp':80,'atk':20,'def':15,'spa':20,'spd':15,'spe':5},skills={'명령':'전문'},moves=['move/불꽃세례','move/째려보기'],pos=(0,0),movement={'land':6}))
 def begin(self):self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a)
 def next_turn(self):self.e.end_of_turn(self.a);self.e.end_round();self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a)
 def bind(self,p=None):self.assertEqual(self.e.manual_feat(self.a,CPF.PINPOINT,p or self.p),(1,0))
 def load(self):
  e=CODEC.load_engine(self.rules,json.loads(json.dumps(CODEC.dump_engine(self.e),ensure_ascii=False)))
  return e,{c.entity_id:c for c in e.everyone}
 def test_native_durable_bound_identity_releases_exact_source_once(self):
  self.begin();self.bind();self.a.spec['ap_bound']['unrelated-binding']=1
  e,actors=self.load();a,p=actors[self.a.entity_id],actors[self.p.entity_id]
  row=CPF.binding(e,p);self.assertIs(row['owner'],a);self.assertIs(row['target'],p)
  before=AP.available(a);self.assertEqual(e.release_pinpoint_strike(a,p),(1,0));self.assertEqual(AP.available(a),before+2)
  self.assertEqual(a.spec['ap_bound'],{'unrelated-binding':1});self.assertNotIn(CPF.KEY,p.custom_conditions)
  with self.assertRaises(ValueError):e.release_pinpoint_strike(a,p)
  self.assertEqual(AP.available(a),before+2)
 def test_native_durable_damage_accuracy_and_secondary_effect_consume_same_binding(self):
  self.begin();self.bind();e,actors=self.load();a,p,t=actors[self.a.entity_id],actors[self.p.entity_id],actors[self.foe.entity_id]
  e.end_of_turn(a);e.start_of_turn(p)
  # Seed is serialized; fixed accuracy is supplied by the native accuracy API.
  move=e.r.move('move/불꽃세례');self.assertTrue(e.accuracy_check(p,t,move,fixed_roll=3)[0])
  enhanced=e.roll_damage(p,t,move,set_damage=True)
  e.end_of_turn(p);e.end_round();e.start_round(e.everyone);e.start_of_turn(a);e.release_pinpoint_strike(a,p)
  self.assertFalse(e.accuracy_check(p,t,move,fixed_roll=3)[0]);self.assertEqual(e.roll_damage(p,t,move,set_damage=True),enhanced+5)
 def test_two_targets_distinct_binding_cost_and_independent_gm_restore(self):
  self.begin();self.bind();self.next_turn();self.bind(self.q)
  self.assertEqual(sum(self.a.spec['ap_bound'].values()),4);self.assertNotEqual(CPF.binding(self.e,self.p)['instance'],CPF.binding(self.e,self.q)['instance'])
  self.e.gm.snapshot('two-stratagems');self.e.release_pinpoint_strike(self.a,self.p)
  self.assertIsNotNone(CPF.binding(self.e,self.q));self.assertEqual(sum(self.a.spec['ap_bound'].values()),2)
  self.e.gm.restore('two-stratagems');self.assertEqual(sum(self.a.spec['ap_bound'].values()),4)
  self.assertIs(CPF.binding(self.e,self.p)['owner'],self.a);self.assertIs(CPF.binding(self.e,self.q)['owner'],self.a)
  self.e.release_pinpoint_strike(self.a,self.q);self.assertIsNotNone(CPF.binding(self.e,self.p))
 def test_durable_recalled_target_encounter_end_removes_only_all_stratagem_costs(self):
  self.begin();self.bind();self.next_turn();self.bind(self.q);self.p.on_field=False
  self.a.spec.update(ap_spent=1,ap_removed=1);self.a.spec['ap_bound']['unrelated']=1
  e,actors=self.load();a,p,q=actors[self.a.entity_id],actors[self.p.entity_id],actors[self.q.entity_id]
  e.end_encounter(combatants=[a])
  self.assertNotIn(CPF.KEY,p.custom_conditions);self.assertNotIn(CPF.KEY,q.custom_conditions)
  self.assertEqual(a.spec['ap_bound'],{'unrelated':1});self.assertEqual(a.spec['ap_spent'],1);self.assertEqual(a.spec['ap_removed'],1)
  e2=CODEC.load_engine(self.rules,CODEC.dump_engine(e));a2=next(c for c in e2.everyone if c.entity_id==a.entity_id)
  self.assertEqual(a2.spec['ap_bound'],{'unrelated':1});self.assertEqual(AP.available(a2),AP.maximum(a2)-3)
 def test_duplicate_target_and_other_owner_turn_preserve_cost_action_rng(self):
  self.begin();self.bind();before=(deepcopy(self.a.spec),deepcopy(self.a.budget),self.e.rng.getstate())
  with self.assertRaises(ValueError):self.bind()
  self.assertEqual(before,(self.a.spec,self.a.budget,self.e.rng.getstate()))
  self.e.end_of_turn(self.a);self.e.start_of_turn(self.p);before=(deepcopy(self.a.spec),deepcopy(self.a._action_history))
  self.assertEqual(self.e.release_pinpoint_strike(self.a,self.p),(0,1));self.assertEqual(before,(self.a.spec,self.a._action_history))
 def test_active_binding_blocks_native_owner_transfer_until_actual_encounter_end(self):
  receiver=self.actor('receiver');self.e.everyone.append(receiver)
  PARTY.configure(self.e,self.a,mode='unlimited',reason='observed roster',roster=[self.p,self.q])
  PARTY.configure(self.e,receiver,mode='unlimited',reason='empty roster',roster=[])
  self.begin();self.bind();before=(deepcopy(self.a.spec),deepcopy(self.p.spec),deepcopy(receiver.spec))
  with self.assertRaises(ValueError):PARTY.transfer(self.e,self.a,target=self.p,new_owner=receiver,reason='voluntary',request_id='transfer-bound')
  self.assertEqual(before,(self.a.spec,self.p.spec,receiver.spec));self.assertIs(CPF.binding(self.e,self.p)['owner'],self.a)
  self.e.end_encounter();PARTY.transfer(self.e,self.a,target=self.p,new_owner=receiver,reason='voluntary',request_id='transfer-after-encounter')
  self.assertEqual(self.p.spec['trainer_id'],receiver.entity_id);self.assertNotIn(CPF.KEY,self.p.custom_conditions);self.assertEqual(self.a.spec['ap_bound'],{})

if __name__=='__main__':unittest.main()
