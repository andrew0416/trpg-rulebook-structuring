"""Whole capacity-source contracts through shared native food and learned-move consumers."""
from copy import deepcopy
from pathlib import Path
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from builder import build_pokemon,build_trainer
import food_effects as F,effect_instances as I,move_state as M,state_grants as G,world_entities as W

class CapacityAbilityTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules={p:Rules(str(ROOT),ruleset=p) for p in ('core','playtest')}
 def world(self,profile='core',kind='pokemon',abilities=(),moves=()):
  r=self.rules[profile];e=Engine(r,seed=554)
  spec=(build_pokemon(r,'이상해씨',50,moves=list(moves),abilities=list(abilities)) if kind=='pokemon' else build_trainer(r,'actual trainer',20,{'hp':10,'atk':10,'def':10,'spa':10,'spd':10,'spe':10},moves=list(moves),abilities=list(abilities)))
  c=Combatant(r,spec);e.gm.add_combatant(c,pos=(1,1),side='party',reason='observed actual current actor and abilities')
  return e,c
 def feed(self,e,c,item='초코바'):
  stock=c.spec.setdefault('items',{});stock[item]=stock.get(item,0)+1
  return e.use_item(c,item,duration_minutes=1,duration_reason='actual one-minute food intake')
 def eat(self,e,c,uid):return e.consume_food_buff(c,buff_id=uid,action_kind='free',action_reason='explicit actual food activation')
 def saved(self,e,c):
  snap=e.gm.snapshot();e.gm.restore(snap)
  loaded=Engine.import_state(Rules(str(ROOT),ruleset=e.r.ruleset.name),json.loads(json.dumps(e.export_state(),ensure_ascii=False)))
  self.assertTrue(loaded.validate_state()['valid'],loaded.validate_state())
  return loaded,W.actor_index(loaded)[c.entity_id]
 def state(self,e,c):return deepcopy((c.spec,c.buffs,c.hp,c.abilities,c.moves,c.counters,e.elapsed_seconds,e.rng.getstate()))
 def test_honey_both_source_versions_and_actor_kinds_keep_independent_limit_and_lifetime(self):
  for profile,name in [('core','꿀파기'),('playtest','꿀파기 [Playtest]')]:
   for kind in ('trainer','pokemon'):
    with self.subTest(profile=profile,kind=kind):
     e,c=self.world(profile,kind,[name]);normal=self.feed(e,c);honey=self.feed(e,c,'꿀');extra=self.feed(e,c,'꿀')
     self.assertEqual((F.slots(c),len(c.buffs)),(1,3));row=F.get_buff(c,honey['buff_id'])
     self.assertEqual(row['effect'],{'kind':'turn_heal','denominator':16});self.assertEqual(row[I.KEY]['capacity']['bucket'],'source_exempt')
     e.gm.set_ability(c,name,add=False,reason='actual ability removed after food acquisition');e,c=self.saved(e,c)
     e.start_round([c]);e.start_of_turn(c);self.eat(e,c,honey['buff_id']);self.assertEqual(c.counters.get('lim:food_buff_consumed',0),0)
     self.assertEqual({b['id'] for b in c.buffs},{normal['buff_id'],extra['buff_id']});c.hp=1;e.end_of_turn(c);e.start_round([c]);e.start_of_turn(c)
     self.assertEqual(c.hp,1+c.base_max_hp//16);e.end_encounter([c]);self.assertNotIn('food_turn_healing',c.spec)
     self.assertEqual(F.slots(c),1);self.assertTrue(e.validate_state()['valid'],e.validate_state())
 def test_gluttony_native_acquisition_three_slots_scene_limit_and_honey_exception(self):
  for kind in ('trainer','pokemon'):
   with self.subTest(kind=kind):
    e,c=self.world('playtest',kind,['먹보 [Playtest]','꿀파기 [Playtest]'])
    for _ in range(3):self.feed(e,c)
    c.spec['items']['초코바']=1;before=self.state(e,c)
    with self.assertRaises(ValueError):e.use_item(c,'초코바',duration_minutes=1,duration_reason='fourth stored ordinary food')
    self.assertEqual(self.state(e,c),before);honey=self.feed(e,c,'꿀');e,c=self.saved(e,c)
    for row in list(c.buffs):
     if row['id']!=honey['buff_id']:self.eat(e,c,row['id'])
    self.assertEqual(c.counters['lim:food_buff_consumed'],3);fourth=self.feed(e,c);before=self.state(e,c)
    with self.assertRaises(ValueError):self.eat(e,c,fourth['buff_id'])
    self.assertEqual(self.state(e,c),before);self.eat(e,c,honey['buff_id']);self.assertEqual(c.counters['lim:food_buff_consumed'],3)
    e.end_encounter([c])
    with self.assertRaises(ValueError):self.eat(e,c,fourth['buff_id'])
    e.end_scene([c]);self.eat(e,c,fourth['buff_id']);self.assertEqual(c.counters['lim:food_buff_consumed'],1)
    self.assertTrue(e.validate_state()['valid'],e.validate_state())
 def test_gluttony_saved_drink_history_uses_exact_half_hour_and_suppression(self):
  for kind in ('trainer','pokemon'):
   with self.subTest(kind=kind):
    e,c=self.world('playtest',kind,['ability/먹보-playtest']);c.spec.setdefault('items',{})['맛있는물']=5
    def drink():return e.use_item(c,'맛있는물',duration_minutes=1,duration_reason='actual completed drink')
    drink();drink();e,c=self.saved(e,c);before=self.state(e,c)
    with self.assertRaises(ValueError):drink()
    self.assertEqual(self.state(e,c),before);e.advance_time(1679,[c]);before=self.state(e,c)
    with self.assertRaises(ValueError):drink()
    self.assertEqual(self.state(e,c),before);e.advance_time(1,[c]);drink();self.assertEqual(c.spec['items']['맛있는물'],2)
    c.abilities_suppressed=True;before=self.state(e,c)
    with self.assertRaises(ValueError):drink()
    self.assertEqual(self.state(e,c),before);c.abilities_suppressed=False;self.assertTrue(e.validate_state()['valid'],e.validate_state())
 def test_unselected_food_variant_and_suppressed_honey_do_not_create_free_slots(self):
  e,c=self.world('core');before=self.state(e,c)
  with self.assertRaises(ValueError):e.gm.set_ability(c,'먹보 [Playtest]',reason='unselected profile cannot grant an exception')
  self.assertEqual(self.state(e,c),before)
  for profile,name in [('core','꿀파기'),('playtest','꿀파기 [Playtest]')]:
   e,c=self.world(profile,abilities=[name]);c.abilities_suppressed=True;out=self.feed(e,c,'꿀');row=F.get_buff(c,out['buff_id']);self.assertEqual(row['effect'],{'kind':'heal','amount':5});self.assertEqual(F.slots(c),1)

if __name__=='__main__':unittest.main()
