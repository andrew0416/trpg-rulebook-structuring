from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_container_contents as _fixture_test_category2_container_contents
import effect_instances as E,food_effects as F,state_codec as CODEC

class FoodInstanceTests(unittest.TestCase):
 setUpClass=classmethod(_fixture_test_category2_container_contents.ContainerContentsTests.setUpClass.__func__)
 setUp=_fixture_test_category2_container_contents.ContainerContentsTests.setUp
 add=_fixture_test_category2_container_contents.ContainerContentsTests.add
 held=_fixture_test_category2_container_contents.ContainerContentsTests.held
 restored=_fixture_test_category2_container_contents.ContainerContentsTests.restored
 row=_fixture_test_category2_container_contents.ContainerContentsTests.row
 snap=_fixture_test_category2_container_contents.ContainerContentsTests.snap
 valid=_fixture_test_category2_container_contents.ContainerContentsTests.valid
 def feed(self,actor,item='초코바'):
  items=actor.spec.setdefault('items',{});items[item]=items.get(item,0)+1
  return self.e.use_item(actor,item,duration_minutes=1,duration_reason='actual sourced food intake')
 def eat(self,actor,uid):return self.e.consume_food_buff(actor,buff_id=uid,action_kind='free',action_reason='actual food activation')
 def test_global_ids_keep_origin_across_actor_kinds_and_restore(self):
  a=self.feed(self.a);p=self.feed(self.p);self.assertNotEqual(a['buff_id'],p['buff_id'])
  for actor in (self.a,self.p):
   m=actor.buffs[0][E.KEY];self.assertEqual((m['origin_actor_id'],m['holder_id']),(actor.entity_id,actor.entity_id));self.assertEqual(m['lifetime'],{'boundary':'consumption'});self.assertEqual(F.slots(actor),1)
  self.eat(self.a,a['buff_id']);later=self.feed(self.a);self.assertNotEqual(a['buff_id'],later['buff_id']);self.assertEqual(len(self.p.buffs),1)
  self.valid();self.assertTrue(self.restored().validate_state()['valid'])
 def test_native_type_berry_choice_survives_json_until_actual_hit_for_both_actor_kinds(self):
  import random
  from builder import build_pokemon
  import world_entities as W
  for kind in ('trainer','pokemon'):
   with self.subTest(kind=kind):
    self.setUp()
    target=self.a if kind=='trainer' else self.add(build_pokemon(self.r,'이브이',20,moves=[],abilities=[]))
    attacker=self.add(build_pokemon(self.r,'이브이',20,moves=['move/몸통박치기'],abilities=[]))
    self.e.gm.set_position(attacker,(1,0),reason='actual neighboring attacker')
    acquired=self.feed(target,'카리열매')
    baseline=self.e.roll_damage(attacker,target,self.r.move('move/몸통박치기'),set_damage=True)
    self.assertGreater(baseline,0)
    self.e.consume_food_buff(target,buff_id=acquired['buff_id'])
    self.e.gm.restore(self.e.gm.snapshot())
    loaded=self.restored();actors=W.actor_index(loaded)
    saved_attacker=actors[attacker.entity_id];saved_target=actors[target.entity_id]
    self.assertEqual(saved_target.spec['food_hit_choice'],{'buff_id':acquired['buff_id']})
    self.assertEqual(F.get_buff(saved_target,acquired['buff_id'])[E.KEY]['holder_id'],saved_target.entity_id)
    loaded.start_round([saved_attacker,saved_target]);loaded.start_of_turn(saved_attacker)
    for seed in range(500):
     if random.Random(seed).randint(1,20)==10:loaded.rng.seed(seed);break
    else:self.fail('actual noncritical hit seed missing')
    before=saved_target.hp;loaded.use_move(saved_attacker,saved_target,'move/몸통박치기',set_damage=True)
    damage=before-saved_target.hp
    self.assertGreater(damage,0);self.assertLess(damage,baseline)
    self.assertFalse(saved_target.buffs);self.assertNotIn('food_hit_choice',saved_target.spec)
    receipt=saved_target.spec['food_consumption_receipts'][-1]
    self.assertEqual(receipt['buff_id'],acquired['buff_id']);self.assertEqual(receipt['producer'],'actual_hit')
    self.assertEqual(receipt['benefit']['resistance_steps'],1);self.assertEqual(saved_attacker.budget['standard'],0)
    self.assertTrue(loaded.validate_state()['valid'],loaded.validate_state())
 def test_live_transfer_preserves_both_instances_and_exempts_transferred_capacity(self):
  own=self.feed(self.other);foreign=self.feed(self.p)
  self.e.apply_effect(self.other,self.p,{'type':'steal_buff'},20,True,0,'move/벌레먹기')
  self.assertEqual(len(self.other.buffs),2);self.assertEqual(F.slots(self.other),1)
  row=F.get_buff(self.other,foreign['buff_id']);self.assertEqual(row[E.KEY]['origin_actor_id'],self.p.entity_id);self.assertEqual(row[E.KEY]['holder_id'],self.other.entity_id)
  self.eat(self.other,foreign['buff_id']);self.assertEqual(self.other.counters.get('lim:food_buff_consumed',0),0);self.assertEqual(self.other.counters['food_buff_consumed'],1)
  self.assertEqual(self.other.buffs[0]['id'],own['buff_id']);self.valid()
 def test_honey_paws_has_separate_slot_and_active_healing_lifetime(self):
  normal=self.feed(self.p);before=deepcopy(self.p.buffs);self.e.gm.set_ability(self.p,'꿀파기',reason='observed acquired ability');self.assertEqual(self.p.buffs,before);honey=self.feed(self.p,'꿀')
  row=F.get_buff(self.p,honey['buff_id']);self.assertEqual(row['effect'],{'kind':'turn_heal','denominator':16});self.assertEqual(F.slots(self.p),1);self.assertEqual(len(self.p.buffs),2)
  self.e.gm.set_ability(self.p,'꿀파기',add=False,reason='ability removed after independent food acquisition')
  self.e.start_round([self.p,self.other]);self.e.start_of_turn(self.p);self.eat(self.p,honey['buff_id']);active=self.p.spec['food_turn_healing'][0]
  self.assertNotEqual(active['id'],honey['buff_id']);self.assertEqual(active[E.KEY]['kind'],'food_turn_healing');self.assertEqual(active[E.KEY]['lifetime'],{'boundary':'encounter_end'});self.assertEqual(active['buff_id'],honey['buff_id']);self.assertEqual(F.slots(self.p),1)
  self.assertEqual(self.p.counters.get('lim:food_buff_consumed',0),0);self.p.hp=1;self.e.end_of_turn(self.p);self.e.start_round([self.p,self.other]);self.e.start_of_turn(self.p);self.assertEqual(self.p.hp,1+self.p.base_max_hp//16)
  self.valid();self.e.gm.restore(self.e.gm.snapshot());self.assertTrue(self.restored().validate_state()['valid']);self.e.end_encounter([self.p,self.other]);self.assertNotIn('food_turn_healing',self.p.spec);self.assertEqual(self.p.buffs[0]['id'],normal['buff_id']);self.valid()
 def test_suppressed_honey_paws_uses_normal_honey_effect_and_slot(self):
  self.e.gm.set_ability(self.p,'꿀파기',reason='observed acquired ability');self.p.abilities_suppressed=True
  out=self.feed(self.p,'꿀');row=F.get_buff(self.p,out['buff_id']);self.assertEqual(row['effect'],{'kind':'heal','amount':5});self.assertEqual(F.slots(self.p),1);self.assertEqual(row[E.KEY]['capacity'],F.ordinary_capacity());self.valid()
 def test_four_original_snacks_keep_prices_conditions_native_effects_and_restore(self):
  examples=[('초코바',75,'heal',5),('꿀',100,'heal',5),('먹다남은음식',350,'turn_heal',16),('검은오물',500,'turn_heal',8)]
  for item,price,kind,value,actor_kind in [(*row,k) for row in examples for k in ('trainer','pokemon') if row[0]!='검은오물' or k=='pokemon']:
   with self.subTest(item=item,actor_kind=actor_kind):
    self.setUp();actor=self.a if actor_kind=='trainer' else self.p
    if item=='검은오물':self.e.gm.set_types(actor,['독'],reason='actual Poison-type consumer')
    self.assertEqual(self.r.item_effects(item)[1]['price'],price);out=self.feed(actor,item);row=F.get_buff(actor,out['buff_id']);self.assertEqual(row['effect'],{'kind':kind,'amount' if kind=='heal' else 'denominator':value})
    self.e.gm.restore(self.e.gm.snapshot());self.assertTrue(self.restored().validate_state()['valid'])
    if kind=='heal':
     actor.hp=1;self.eat(actor,out['buff_id']);self.assertEqual(actor.hp,6)
    else:
     self.e.start_round([actor]);self.e.start_of_turn(actor);self.eat(actor,out['buff_id']);actor.hp=1;self.e.end_of_turn(actor);self.e.start_round([actor]);self.e.start_of_turn(actor);self.assertEqual(actor.hp,1+actor.base_max_hp//value)
     self.e.gm.restore(self.e.gm.snapshot());self.assertTrue(self.restored().validate_state()['valid']);self.e.end_encounter([actor]);self.assertNotIn('food_turn_healing',actor.spec)
    self.valid()
 def test_corruption_and_duplicate_gm_records_reject_before_live_mutation(self):
  out=self.feed(self.p);good=deepcopy(self.p.buffs[0])
  for key,value in [('sequence',True),('holder_id',self.a.entity_id),('lifetime',{'boundary':'day_end'})]:
   self.p.buffs[0]=deepcopy(good);self.p.buffs[0][E.KEY][key]=value;before=self.snap()
   with self.assertRaises(ValueError):self.eat(self.p,out['buff_id'])
   self.assertEqual(before,self.snap())
   with self.assertRaises(ValueError):self.e.gm.snapshot()
   with self.assertRaises(ValueError):CODEC.dump_engine(self.e)
  self.p.buffs[0]=deepcopy(good);self.p.buffs[0]['effect']['amount']=999;before=self.snap()
  with self.assertRaises(ValueError):self.eat(self.p,out['buff_id'])
  self.assertEqual(before,self.snap())
  with self.assertRaises(ValueError):self.e.gm.snapshot()
  with patch.object(E,'validate_actor',return_value=True),patch.object(E,'validate_world',return_value=True):
   payload=json.loads(json.dumps(CODEC.dump_engine(self.e)));bad=self.e.gm.snapshot('bad-effect')
  self.p.buffs[0]=good;before=self.snap()
  with self.assertRaises(ValueError):CODEC.load_engine(self.r,payload)
  with self.assertRaises(ValueError):self.e.gm.restore(bad)
  self.assertEqual(before,self.snap())
  with self.assertRaises(ValueError):self.e.gm.add_buff(self.p,deepcopy(good),reason='duplicate')
  with self.assertRaises(ValueError):self.e.gm.add_buff(self.other,deepcopy(good),reason='foreign holder')
  self.assertEqual(before,self.snap())
 def test_ongoing_healing_cannot_invent_a_different_consumed_parent(self):
  out=self.feed(self.p,'먹다남은음식');self.e.start_round([self.p]);self.e.start_of_turn(self.p);self.eat(self.p,out['buff_id'])
  self.p.spec['food_turn_healing'][0]['effect']['denominator']=1;before=self.snap()
  with self.assertRaises(ValueError):F.turn_start(self.e,self.p)
  self.assertEqual(before,self.snap())
  with self.assertRaises(ValueError):self.e.gm.snapshot()
  with self.assertRaises(ValueError):CODEC.dump_engine(self.e)
 def test_failed_native_creation_does_not_spend_inventory_clock_or_sequence(self):
  self.p.spec['items']['초코바']=1;before=self.snap();native=F.grant_buff
  def broken(*args,**kw):native(*args,**kw);raise ValueError('after effect creation')
  with patch.object(F,'grant_buff',side_effect=broken):
   with self.assertRaises(ValueError):self.e.use_item(self.p,'초코바',duration_minutes=1,duration_reason='actual intake')
  self.assertEqual(before,self.snap());self.assertNotIn(E.SEQUENCE,self.p.spec);self.feed(self.p);self.valid()

if __name__=='__main__':unittest.main()
