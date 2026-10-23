"""Source-defined Static/At-Will and shared multiclass AP/action state."""
from copy import deepcopy
from pathlib import Path
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from engine import Rules,Engine,Combatant
from contest import ContestEngine,ContestRules
import action_points as AP
import contest_features as F
import items as ITEMS
import state_codec as CODEC

class ClassResourceTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(str(ROOT),ruleset='core');cls.cr=ContestRules(str(ROOT),ruleset='core')
 def setUp(self):
  self.e=Engine(self.rules,seed=39);self.ce=ContestEngine(self.cr,seed=17)
  common=dict(level=25,stats={'hp':40,'atk':20,'def':10,'spa':20,'spd':10,'spe':10},movement={'land':6},pos=(0,0))
  self.t=Combatant(self.rules,dict(common,name='multiclass',kind='trainer',moves=[],classes=['class/코디네이터',F.STYLE,'class/로그','class/파동술사'],edges=['edge/우아함','edge/원소-교감','edge/몬스터볼'],edge_choices={'edge/원소-교감':'격투'},feats=[F.NUANCED,F.RELIABLE,'feat/근사한-행위',F.FLOURISH],feat_ranks={'feat/근사한-행위':2},feature_choices={F.STYLE:['근사함'],F.FLOURISH:['근사함'],'class/파동술사':['진공파','발경']},skills={'명령':6,'매력':6,'곡예':6,'육상':6,'은신':6,'기술학':4},items={'몬스터볼 공구함':1},money=500))
  self.p=Combatant(self.rules,dict(common,name='owned',kind='pokemon',trainer_id=self.t.entity_id,skills={'육상':3},moves=['move/연속자르기'],poffins=['근사함']*3))
  self.foe=Combatant(self.rules,dict(common,name='enemy',kind='pokemon',moves=[],pos=(1,0)))
  self.t.side=self.p.side='party';self.foe.side='enemy';self.e.everyone=self.e.gm.everyone=[self.t,self.p,self.foe]
  ITEMS.register_feats(self.e,self.t)
 def reliable(self,e=None,t=None,p=None):return (e or self.e).contest_skill_feature(t or self.t,p or self.p,F.RELIABLE,'육상',10)
 def load(self):
  e=CODEC.load_engine(self.rules,json.loads(json.dumps(CODEC.dump_engine(self.e),ensure_ascii=False)))
  return e,{c.entity_id:c for c in e.everyone}
 def test_static_acquired_sources_have_no_activation_cost_or_use_counter(self):
  expected={'move/속여때리기','move/도둑질','move/진공파','move/발경'}
  self.assertTrue(expected.issubset(self.t.moves));self.assertEqual(AP.available(self.t),AP.maximum(self.t))
  self.assertFalse(getattr(self.t,'_action_history',[]));self.assertFalse(self.t.spec.get('frequency_state',{}).get('activations',{}))
  ITEMS.register_feats(self.e,self.t);self.assertTrue(all(self.t.moves.count(mid)==1 for mid in expected))
  e,actors=self.load();t=actors[self.t.entity_id];self.assertTrue(expected.issubset(t.moves));self.assertFalse(getattr(t,'_action_history',[]))
  t.spec['classes'].remove('class/로그');ITEMS.register_feats(e,t)
  self.assertFalse({'move/속여때리기','move/도둑질'}&set(t.moves));self.assertTrue({'move/진공파','move/발경'}.issubset(t.moves))
 def test_actual_atwill_crafting_repeats_then_durable_repeats_until_material_constraint(self):
  def craft(e,t):return e.pokemon_activity(t,'craft_item',item='몬스터볼',minutes=5,reason='observed five minute craft')
  craft(self.e,self.t);craft(self.e,self.t)
  self.assertEqual(self.t.spec['money'],300);self.assertEqual(self.t.spec['items']['item/몬스터볼-2'],2)
  e,actors=self.load();t=actors[self.t.entity_id];craft(e,t)
  self.assertEqual(t.spec['money'],200);self.assertEqual(t.spec['items']['item/몬스터볼-2'],3);self.assertEqual(e.elapsed_seconds,900)
  self.assertEqual(t._action_history,['extended']*3);self.assertEqual(AP.available(t),AP.maximum(t))
  t.spec['money']=0;before=(deepcopy(t.spec),e.elapsed_seconds,e.rng.getstate())
  with self.assertRaises(ValueError):craft(e,t)
  self.assertEqual(before,(t.spec,e.elapsed_seconds,e.rng.getstate()))
 def test_actual_ap_feature_repeats_cost_each_time_and_durable_never_refills(self):
  self.reliable();self.reliable();self.assertEqual(self.t.spec['ap_spent'],4)
  self.e.gm.snapshot('ap4');self.reliable();self.e.gm.restore('ap4');self.assertEqual(self.t.spec['ap_spent'],4)
  e,actors=self.load();t,p=actors[self.t.entity_id],actors[self.p.entity_id]
  for _ in range(3):self.reliable(e,t,p)
  self.assertEqual(t.spec['ap_spent'],10);self.assertEqual(AP.available(t),0)
  before=(deepcopy(t.spec),e.rng.getstate())
  with self.assertRaises(ValueError):self.reliable(e,t,p)
  self.assertEqual(before,(t.spec,e.rng.getstate()))
  e.end_scene();self.assertEqual(AP.available(t),10);self.reliable(e,t,p);self.assertEqual(t.spec['ap_spent'],2)
 def test_two_actual_classes_consume_one_shared_ap_account(self):
  self.reliable();self.assertEqual(self.t.spec['ap_spent'],2)
  c=self.ce.contestant_from_combatants(self.e,self.p,self.t,'매력',{'근사함':4})
  self.ce.perform(c,'연속자르기','근사함',[],False,fixed_rolls=[1,2,3,4],flourish_decision=lambda observed:True)
  self.assertEqual(self.t.spec['ap_spent'],3);self.assertEqual(AP.available(self.t),7)
  self.reliable();self.assertEqual(self.t.spec['ap_spent'],5)
  payload=json.loads(json.dumps(CODEC.dump_contest(self.ce,[c]),ensure_ascii=False))
  ce,contestants=CODEC.load_contest(self.cr,payload,native_rules=self.rules);e,p,t,_,_=ce._native_intro_bindings[contestants[0]]
  self.assertEqual(t.spec['ap_spent'],5);self.reliable(e,t,p);self.assertEqual(t.spec['ap_spent'],7)
 def test_two_class_granted_attacks_share_one_standard_action(self):
  self.e.start_round(self.e.everyone);self.e.start_of_turn(self.t)
  self.e.use_move(self.t,self.foe,'move/속여때리기',set_damage=True)
  self.assertEqual(self.t.budget['standard'],0);self.assertEqual(self.t.move_uses['move/속여때리기'],1)
  before=(self.foe.hp,deepcopy(self.t.move_uses),self.e.rng.getstate())
  self.assertEqual(self.e.use_move(self.t,self.foe,'move/발경',set_damage=True),0)
  self.assertEqual(before,(self.foe.hp,self.t.move_uses,self.e.rng.getstate()))
  self.assertNotIn('move/발경',self.t.move_uses)
  e,actors=self.load();t=actors[self.t.entity_id];foe=actors[self.foe.entity_id]
  self.assertEqual(t.budget['standard'],0);self.assertEqual(e.use_move(t,foe,'move/발경',set_damage=True),0)
  e.end_of_turn(t);e.end_round();e.start_round(e.everyone);e.start_of_turn(t);e.use_move(t,foe,'move/발경',set_damage=True)
  self.assertEqual(t.move_uses['move/발경'],1);self.assertEqual(t.budget['standard'],0)

if __name__=='__main__':unittest.main()
