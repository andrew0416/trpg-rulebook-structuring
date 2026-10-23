"""Direct native producers and consumers for the five crafted Fashion rows."""
from copy import deepcopy
from pathlib import Path
import json
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]

from contest import ContestEngine,ContestRules
from engine import Rules
from grid import Grid
import condition_recovery as RECOVERY
import effect_lifetimes as LIFETIMES
import fashion_items as FASHION
import items as ITEMS
import state_codec as CODEC
import turn as TURN
import vortex_state as VORTEX
import test_foundation_crafting_product as fixture


class FashionItemContractTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.rules=Rules(str(ROOT),ruleset='homebrew')
  cls.contest_rules=ContestRules(str(ROOT),ruleset='homebrew')
 setUp=fixture.ProductTests.setUp
 actor=fixture.ProductTests.actor
 own=fixture.ProductTests.own
 recipe=fixture.ProductTests.recipe
 ready=fixture.ProductTests.ready
 craft=fixture.ProductTests.craft

 def prepare(self):
  self.p.spec.update(trainer_id=self.a.entity_id,wild=False);self.p.side=self.a.side='party'
  self.q.side='wild';self.a.pos=(0,0);self.p.pos=(1,1);self.q.pos=(2,1)
  for actor in (self.a,self.p,self.q):
   actor.spec['footprint']={'kind':'observed_cells','offsets':[(0,0)],'reason':'fashion native-path fixture'}
  self.e.grid=Grid(12,12)

 def make(self,item_id,wearer=None,suffix=None):
  self.prepare();wearer=wearer or self.p;suffix=suffix or item_id.rsplit('/',1)[-1]
  recipe=self.ready();recipe['output']={'item_id':item_id,'key':item_id}
  identity='fashion:'+suffix
  policy={'mode':'create','instance_ids':[identity],'owner_id':wearer.entity_id,
          'state':'intact','attachments':[]}
  result=self.craft(recipe,product_policy=policy,event_id='make:'+suffix)
  ITEMS.register_item(self.e,wearer,item_id,source_instance_id=identity,as_held=wearer.kind=='pokemon')
  self.assertEqual(result['product_instance_ids'],[identity])
  return identity

 def combat(self,*actors):
  actors=actors or (self.a,self.p,self.q)
  self.e.start_round(actors);self.e.start_of_turn(actors[0],initiative_count=20)

 def restored(self):
  return CODEC.load_engine(self.rules,json.loads(json.dumps(CODEC.dump_engine(self.e),ensure_ascii=False)))

 def test_policy_pins_exact_five_csv_rows(self):
  rows=FASHION.policy(self.rules)['rows']
  self.assertEqual({row['clause_id'] for row in rows.values()},
   {f'C2CSV/inventory:{number}:10' for number in range(97,102)})

 def test_cute_one_round_evasion_is_scene_once_and_survives_unequip_restore(self):
  item='item/귀여운-패션-1';self.make(item);self.combat(self.p,self.a,self.q)
  self.e.activate_fashion_item(self.p,item)
  self.assertEqual(LIFETIMES.numeric(self.p,'evasion_modifier'),2)
  ITEMS.unregister_item(self.e,self.p,item)
  self.assertEqual(LIFETIMES.numeric(self.p,'evasion_modifier'),2)
  loaded=self.restored();pokemon=next(c for c in loaded.gm.everyone if c.entity_id==self.p.entity_id)
  self.assertEqual(LIFETIMES.numeric(pokemon,'evasion_modifier'),2)

 def test_beauty_reacts_to_enemy_stage_loss_once_but_not_ally_or_second_effect(self):
  item='item/아름다운-패션-1';identity=self.make(item);self.combat(self.p,self.a,self.q)
  effect={'type':'stage_change','stat':'atk','delta':-1,'on':'target'}
  self.e.apply_effect(self.a,self.p,effect,2,True,0,'move/울음소리')
  self.assertEqual(self.p.stages['atk'],-1)
  actions=len(self.p._action_history)
  # No explicit acceptance: the actual enemy trigger proceeds unchanged.
  self.e.apply_effect(self.q,self.p,effect,2,True,0,'move/울음소리')
  self.assertEqual(self.p.stages['atk'],-2)
  self.assertEqual(len(self.p._action_history),actions)
  self.assertNotIn(FASHION.STATE,self.e._physical_objects[identity])
  self.e.arm_fashion_reaction(self.p,item,instance_id=identity)
  self.e.apply_effect(self.q,self.p,effect,2,True,0,'move/울음소리')
  self.assertEqual(self.p.stages['atk'],-2)
  self.assertEqual(len(self.p._action_history),actions+1)
  self.e.apply_effect(self.q,self.p,effect,2,True,0,'move/울음소리')
  self.assertEqual(self.p.stages['atk'],-3)

 def test_cool_next_save_plus_four_consumes_once_after_restore(self):
  item='item/근사한-패션-1';self.make(item);self.combat(self.p,self.a,self.q)
  self.e.activate_fashion_item(self.p,item)
  loaded=self.restored();pokemon=next(c for c in loaded.gm.everyone if c.entity_id==self.p.entity_id)
  first=RECOVERY.saving_check(loaded,pokemon,None,8,fixed=5)
  second=RECOVERY.saving_check(loaded,pokemon,None,8,fixed=5)
  self.assertEqual((first['fashion_bonus'],first['passed']),(4,True))
  self.assertEqual((second['fashion_bonus'],second['passed']),(0,False))

 def test_tough_targets_observed_enemy_within_five_and_penalizes_native_skill_roll(self):
  item='item/강인한-패션-1';self.make(item);self.combat(self.p,self.a,self.q)
  count=self.e._prepare_skill_roll(self.q,'육상')[5]['dice_count']
  before=self.e.skill_roll(self.q,'육상',fixed=[3]*count)
  move=self.rules.move('move/몸통박치기')
  hit_face=next(face for face in range(2,18) if self.e.accuracy_check(self.q,self.p,move,fixed_roll=face)[0])
  damage_before=self.e.roll_damage(self.q,self.p,move,set_damage=True)
  self.e.activate_fashion_item(self.p,item,target=self.q)
  after=self.e.skill_roll(self.q,'육상',fixed=[3]*count)
  self.assertEqual(after.total,before.total-2)
  self.assertFalse(self.e.accuracy_check(self.q,self.p,move,fixed_roll=hit_face)[0])
  self.assertTrue(self.e.accuracy_check(self.q,self.p,move,fixed_roll=hit_face+2)[0])
  self.assertEqual(self.e.roll_damage(self.q,self.p,move,set_damage=True),damage_before-2)
  self.assertFalse(RECOVERY.saving_check(self.e,self.q,None,8,fixed=9)['passed'])
  self.e.apply_status(self.q,'조이기');self.q.custom_conditions['vortex']['ends']=1
  original_d20=self.e.d20;self.e.d20=lambda:15
  try:VORTEX.turn_end(self.e,self.q)
  finally:self.e.d20=original_d20
  self.assertIn('조이기',self.q.conditions)
  self.a.pos=(11,11)
  with self.assertRaises(ValueError):
   self.e.activate_fashion_item(self.p,item,target=self.a)

 def test_smart_actual_opportunity_trigger_is_prevented_once(self):
  item='item/슬기로운-패션-1';identity=self.make(item);self.combat(self.p,self.a,self.q)
  actions=len(self.p._action_history)
  # Declining by leaving the optional reaction unarmed changes no quota/action.
  TURN.trigger_aoo(self.e,self.p,'인접 칸 밖으로 이동',[self.q])
  self.assertTrue(self.q.aoo_used)
  self.assertEqual(len(self.p._action_history),actions)
  self.assertNotIn(FASHION.STATE,self.e._physical_objects[identity])
  self.q.aoo_used=False
  self.e.arm_fashion_reaction(self.p,item,instance_id=identity)
  TURN.trigger_aoo(self.e,self.p,'인접 칸 밖으로 이동',[self.q])
  self.assertFalse(self.q.aoo_used)
  self.assertEqual(len(self.p._action_history),actions+1)
  self.assertFalse(FASHION.prevents_opportunity(self.e,self.p,'second trigger',[self.q]))

 def test_pokemon_held_capacity_prevents_duplicate_fashion_occurrences(self):
  item='item/귀여운-패션-1'
  first=self.make(item,suffix='cute-one')
  with self.assertRaisesRegex(ValueError,'no available actual held-item slot'):
   self.make(item,suffix='cute-two')
  key,_=FASHION.contest_plan(self.e,self.p,'귀여움',set(),instance_id=first)
  self.assertEqual(key[1],first)

 def test_contest_pokemon_matching_stat_rerolls_ones_once_and_restores_receipt(self):
  item='item/귀여운-패션-1';self.make(item);self.p.moves=['move/벌레의야단법석']
  contest=ContestEngine(self.contest_rules,seed=7)
  stats={name:0 for name in ('근사함','아름다움','귀여움','슬기로움','강인함')}
  actor=contest.contestant_from_combatants(self.e,self.p,self.a,'매력',stat_dice=stats)
  contest.perform(actor,'move/벌레의야단법석','귀여움',[],False,fixed_rolls=[1,2,3,4],
                  fashion_decision=lambda preview: preview['ones']==1,attempt_id='fashion-1')
  self.assertEqual(len(contest._fashion_used),1)
  payload=CODEC.dump_contest(contest,[actor])
  loaded,participants=CODEC.load_contest(self.contest_rules,json.loads(json.dumps(payload,ensure_ascii=False)),native_rules=self.rules)
  self.assertEqual(loaded._fashion_used,contest._fashion_used)
  with self.assertRaises(ValueError):
   FASHION.contest_plan(next(iter(loaded._native_intro_bindings.values()))[0],
                        next(iter(loaded._native_intro_bindings.values()))[1],'귀여움',loaded._fashion_used)

 def test_nonmaker_current_owner_cannot_use_battle_branch_but_pokemon_keeps_contest_branch(self):
  item='item/귀여운-패션-1';identity=self.make(item)
  self.p.spec['trainer_id']='trainer/someone-else'
  self.e.encounter_active=True
  with self.assertRaises(ValueError):self.e.activate_fashion_item(self.p,item)
  self.assertEqual(FASHION.contest_plan(self.e,self.p,'귀여움',set())[1]['item_id'],item)
  self.assertEqual(self.e._physical_objects[identity]['crafting_origin']['maker_id'],self.a.entity_id)


if __name__=='__main__':unittest.main()
