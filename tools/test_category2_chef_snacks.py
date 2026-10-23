"""Exact Chef recipe Snacks: physical intake -> Digestion Buff -> native consumers."""
from copy import deepcopy
from pathlib import Path
import json,sys,unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from builder import build_pokemon
import combat_modifiers as MODIFIERS
import food_effects as FOOD
import nature_state as NATURE
import state_codec as CODEC


ROWS={
 'item/짠맛-서프라이즈':('짠맛','received_attack',None,'temporary_hp'),
 'item/매운맛-랩':('매운맛','attack','물리','bonus_damage'),
 'item/신맛-캔디':('신맛','received_attack','물리','damage_reduction'),
 'item/떫은맛-웨이퍼':('떫은맛','attack','특수','bonus_damage'),
 'item/쓴맛-트리트':('쓴맛','received_attack','특수','damage_reduction'),
 'item/단맛-과자':('단맛','self_activation',None,'timed_modifiers'),
}
MOVES={'물리':'move/기가임팩트','특수':'move/파괴광선'}


class ChefSnackTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.r=Rules(str(ROOT),ruleset='core')

 def nature(self,flavor,disposition):
  clean=lambda value:None if value is None else value.replace(' ','')
  for name in self.r.mech('pokemon/natures')['by_name']:
   row=NATURE.describe(self.r,name)
   if clean(row['likes' if disposition=='liked' else 'dislikes'])==clean(flavor):return name
  self.fail('missing exact Nature for '+flavor)

 def world(self,*,actor_nature=None,target_nature=None,item=None):
  e=Engine(self.r,seed=741)
  attacker=Combatant(self.r,build_pokemon(self.r,'이브이',20,nature=actor_nature,
   moves=list(MOVES.values()),abilities=[],extra={'items':{item:1} if item else {}}))
  target=Combatant(self.r,build_pokemon(self.r,'이브이',20,nature=target_nature,
   moves=list(MOVES.values()),abilities=[],extra={'items':{item:1} if item else {}}))
  e.gm.add_combatant(attacker,pos=(0,0),side='party',reason='actual attacker')
  e.gm.add_combatant(target,pos=(1,0),side='enemy',reason='actual target')
  return e,attacker,target

 def feed(self,e,actor,item,*,accepted=True):
  actor.spec.setdefault('items',{})[item]=actor.spec.get('items',{}).get(item,0)+1
  return e.use_item(actor,item,accepted=accepted,duration_minutes=1,duration_reason='actual physical Chef Snack intake')

 def attack_case(self,item,disposition):
  flavor,trigger,attack_class,benefit=ROWS[item]
  nature=self.nature(flavor,disposition) if disposition!='neutral' else None
  e,a,t=self.world(actor_nature=nature if trigger=='attack' else None,
                   target_nature=nature if trigger=='received_attack' else None)
  actor=a if trigger=='attack' else t
  move=self.r.move(MOVES[attack_class] if attack_class else MOVES['물리'])
  baseline=e.roll_damage(a,t,move,set_damage=True)
  out=self.feed(e,actor,item);buff=FOOD.get_buff(actor,out['buff_id'])
  self.assertEqual((buff['effect']['kind'],buff['effect']['trigger'],buff['effect'].get('attack_class')),
                   ('chef_snack',trigger,attack_class))
  prep=e.consume_food_buff(actor,buff_id=out['buff_id'])
  self.assertEqual(prep['status'],'prepared_for_actual_'+trigger)
  before_temp=actor.temp_hp
  damage=e.roll_damage(a,t,move,set_damage=True)
  receipt=actor.spec['food_consumption_receipts'][-1]
  self.assertEqual((receipt['buff_id'],receipt['producer']),(out['buff_id'],'actual_attack'))
  self.assertEqual(receipt['benefit']['disposition'],disposition)
  self.assertEqual(receipt['benefit']['amount'],10 if disposition=='liked' else 5)
  self.assertFalse(actor.buffs);self.assertTrue(e.validate_state()['valid'])
  if benefit=='temporary_hp':self.assertEqual(actor.temp_hp-before_temp,10 if disposition=='liked' else 5)
  if disposition=='disliked':self.assertIn('난동',actor.conditions)
  if benefit=='bonus_damage':return damage-baseline
  if benefit=='damage_reduction':return baseline-damage
  return receipt['benefit']['amount']

 def assert_attack_recipe(self,item):
  self.assertEqual(self.attack_case(item,'neutral'),5)
  self.assertEqual(self.attack_case(item,'liked'),10)
  self.assertEqual(self.attack_case(item,'disliked'),5)

 def test_r4_salty_surprise(self):self.assert_attack_recipe('item/짠맛-서프라이즈')
 def test_r5_spicy_wrap(self):self.assert_attack_recipe('item/매운맛-랩')
 def test_r6_sour_candy(self):self.assert_attack_recipe('item/신맛-캔디')
 def test_r7_dry_wafer(self):self.assert_attack_recipe('item/떫은맛-웨이퍼')
 def test_r8_bitter_treat(self):self.assert_attack_recipe('item/쓴맛-트리트')

 def test_r9_sweet_confection(self):
  item='item/단맛-과자';flavor=ROWS[item][0]
  for disposition in ('neutral','liked','disliked'):
   with self.subTest(disposition=disposition):
    nature=self.nature(flavor,disposition) if disposition!='neutral' else None
    e,a,t=self.world(actor_nature=nature);out=self.feed(e,a,item)
    e.start_round([a,t]);e.start_of_turn(a)
    baseline_evasion=a.evasion('물리');baseline_accuracy=MODIFIERS.accuracy_stage(a)
    result=e.consume_food_buff(a,buff_id=out['buff_id'])
    self.assertEqual((result['evasion'],result['accuracy']),(4,4 if disposition=='liked' else 0))
    self.assertEqual(a.evasion('물리'),baseline_evasion+4)
    self.assertEqual(MODIFIERS.accuracy_stage(a),baseline_accuracy+(4 if disposition=='liked' else 0))
    if disposition=='disliked':self.assertIn('난동',a.conditions)
    payload=json.loads(json.dumps(CODEC.dump_engine(e),ensure_ascii=False));loaded=CODEC.load_engine(self.r,payload)
    saved=next(x for x in loaded.gm.everyone if x.entity_id==a.entity_id)
    self.assertEqual(saved.evasion('물리'),baseline_evasion+4);self.assertTrue(loaded.validate_state()['valid'])
    e.end_of_turn(a);self.assertEqual(a.evasion('물리'),baseline_evasion+4)
    e.end_round();e.start_round([a,t]);e.start_of_turn(a);self.assertEqual(a.evasion('물리'),baseline_evasion+4)
    e.end_of_turn(a);self.assertEqual(a.evasion('물리'),baseline_evasion)

 def test_decline_wrong_class_restore_and_invalid_choice_are_atomic(self):
  item='item/매운맛-랩';e,a,t=self.world()
  a.spec.setdefault('items',{})[item]=1;before=deepcopy((a.spec,e.elapsed_seconds))
  e.use_item(a,item,accepted=False,duration_minutes=1,duration_reason='declined physical Chef Snack intake')
  # Refusal did not spend the physical item or the intake clock.
  self.assertEqual((a.spec,e.elapsed_seconds),before);self.assertFalse(a.buffs)
  out=self.feed(e,a,item);e.consume_food_buff(a,buff_id=out['buff_id'])
  payload=json.loads(json.dumps(CODEC.dump_engine(e),ensure_ascii=False));loaded=CODEC.load_engine(self.r,payload)
  saved=next(x for x in loaded.gm.everyone if x.entity_id==a.entity_id)
  self.assertEqual(saved.spec[FOOD.CHEF_ATTACK_CHOICE]['buff_id'],out['buff_id'])
  # Special attack is not the selected physical consumer and leaves it armed.
  e.roll_damage(a,t,self.r.move(MOVES['특수']),set_damage=True)
  self.assertTrue(a.buffs);self.assertIn(FOOD.CHEF_ATTACK_CHOICE,a.spec)
  a.spec[FOOD.CHEF_ATTACK_CHOICE]['item']='item/신맛-캔디';bad=deepcopy((a.spec,t.spec,e.rng.getstate(),e.log_lines))
  with self.assertRaises(ValueError):e.roll_damage(a,t,self.r.move(MOVES['물리']),set_damage=True)
  self.assertEqual(bad,(a.spec,t.spec,e.rng.getstate(),e.log_lines))


if __name__=='__main__':unittest.main()
