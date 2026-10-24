"""Bug Bite replays one real same-scene food receipt as a new effect instance."""
from copy import deepcopy
from pathlib import Path
import csv,json,sys,unittest

STAGE=Path(__file__).resolve().parents[1]
ROOT = STAGE
sys.path[:0]=[str(STAGE/'engine'),str(ROOT/'engine'),str(ROOT/'tools')]

import effect_instances as INSTANCES
import food_effects as FOOD
import gm_state as _STAGED_GM_STATE
import temporary_hp as TEMP
from engine import Rules,Engine,Combatant
from state_codec import dump_engine,load_engine


class BugBiteConsumedHistoryTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(str(ROOT),ruleset='core')

 def actor(self,name,kind='pokemon'):
  return Combatant(self.rules,{'id':kind+'/'+name,'name':name,'kind':kind,'level':20,'pos':(0,0),
   'stats':{'hp':10,'atk':5,'def':5,'spa':5,'spd':5,'spe':5},
   'skills':{k:'숙련' for k in ['기술학','포켓몬학','매력','교활','협박','직감','육상','곡예','생존','명령']},
   'items':{},'edges':[],'feats':[]})

 def setUp(self):
  self.e=Engine(self.rules,seed=181)
  self.owner=self.actor('owner','trainer');self.attacker=self.actor('attacker');self.target=self.actor('target')
  for actor in (self.owner,self.attacker,self.target):self.e.gm.add_combatant(actor)

 def feed(self,actor,item='초코바'):
  self.owner.spec['items'][item]=self.owner.spec['items'].get(item,0)+1
  self.e.use_item(self.owner,item,actor,duration_minutes=1,duration_reason='actual sourced food intake')
  return actor.buffs[-1]['id']

 def consume(self,actor,item='초코바'):
  uid=self.feed(actor,item)
  self.e.consume_food_buff(actor,buff_id=uid,action_kind='free',action_reason='actual food exchange')
  return deepcopy(actor.spec['food_consumption_receipts'][-1])

 def direct_transfer(self,buff_id=None):
  if buff_id is not None:self.e.gm.choose_food_transfer(self.attacker,self.target,buff_id,reason='choose reviewed target food effect')
  self.e.apply_effect(self.attacker,self.target,{'type':'steal_buff'},20,True,0,'move/벌레먹기')
  return self.attacker.buffs[-1]

 def begin_attack(self):
  self.e.gm.set_move(self.attacker,'move/벌레먹기',True,reason='observed native move')
  self.e.gm.set_position(self.attacker,(1,1),reason='actual adjacent attacker')
  self.e.gm.set_position(self.target,(2,1),reason='actual adjacent target')
  self.e.start_round([self.attacker,self.target]);self.e.start_of_turn(self.attacker)

 def test_exact_source_row_and_runtime_contract_are_bound(self):
  with (ROOT/'input/db/moves.csv').open(encoding='utf-8-sig',newline='') as fh:row=list(csv.reader(fh))[3]
  self.assertEqual(row[0],'벌레먹기')
  self.assertEqual(row[7],'대상이 만복버프/음식버프를 가지고 있거나 이번 장면에서 만복버프/음식버프를 소모 했을 경우, 사용자는 해당 만복버프/음식버프의 효과를 가져갈 수 있습니다. 이러한 만복버프/음식버프는 사용자의 만복버프/음식버프의 제한에 영향받지 않습니다.')
  mechanics,confidence=self.rules.move_mech('move/벌레먹기')
  self.assertEqual(confidence,'llm')
  self.assertIn({'type':'steal_buff','buff':'만복/음식버프','if':'target has or consumed one this scene'},mechanics['effects_exec'])
  policy=json.loads((STAGE/'data/food-buff-policy.json').read_text(encoding='utf-8'))['capacity_exceptions']['move/벌레먹기']
  self.assertEqual((policy['slot_bucket'],policy['scene_usage_exempt'],policy['source_anchor']),('source_exempt',True,'input/db/moves.csv record4'))

 def test_native_hit_copies_consumed_receipt_with_new_identity_and_exempt_capacity(self):
  receipt=self.consume(self.target);original_history=deepcopy(self.target.spec['food_consumption_receipts'])
  own=self.feed(self.attacker)
  self.begin_attack();self.e.rng.seed(6);hp=self.target.hp
  self.e.use_move(self.attacker,self.target,'move/벌레먹기',set_damage=True)
  self.assertLess(self.target.hp,hp);self.assertEqual(self.attacker.move_uses['move/벌레먹기'],1)
  self.assertEqual(self.target.spec['food_consumption_receipts'],original_history)
  self.assertEqual(len(self.attacker.buffs),2);copied=self.attacker.buffs[-1]
  self.assertNotEqual(copied['id'],receipt['buff_id']);self.assertEqual(FOOD.slots(self.attacker),1)
  self.assertEqual((copied['source'],copied['item'],copied['effect_source'],copied['effect']),(receipt['source'],receipt['item'],receipt['effect_source'],receipt['effect']))
  self.assertEqual(copied[INSTANCES.KEY]['capacity'],FOOD.capacity_from_source(self.rules,'move/벌레먹기'))
  self.assertEqual(copied['food_transfer_origin']['holder_id'],self.target.entity_id)
  self.assertEqual(copied['food_transfer_origin']['buff_id'],receipt['buff_id'])
  self.assertEqual(self.attacker.buffs[0]['id'],own);self.assertTrue(self.e.validate_state()['valid'],self.e.validate_state())

 def test_explicit_choice_selects_one_of_live_and_consumed_candidates(self):
  spent=self.consume(self.target,'꿀');live=self.feed(self.target,'초코바')
  before_live=deepcopy(self.target.buffs)
  with self.assertRaises(ValueError):self.e.apply_effect(self.attacker,self.target,{'type':'steal_buff'},20,True,0,'move/벌레먹기')
  self.assertFalse(self.attacker.buffs);self.assertEqual(self.target.buffs,before_live)
  choice=self.e.gm.choose_food_transfer(self.attacker,self.target,spent['buff_id'],reason='take the already consumed Honey effect')
  self.assertEqual((choice['kind'],choice['buff_id']),('consumed',spent['buff_id']))
  copied=self.direct_transfer();self.assertEqual(copied['item'],'item/꿀')
  self.assertEqual(self.target.buffs[0]['id'],live);self.assertNotIn('food_theft_choice',self.attacker.spec)
  self.assertTrue(self.e.validate_state()['valid'],self.e.validate_state())

 def test_old_scene_receipt_and_miss_do_not_copy_effect(self):
  receipt=self.consume(self.target);self.e.end_scene([self.owner,self.attacker,self.target]);self.begin_attack()
  self.e.rng.seed(6);self.e.use_move(self.attacker,self.target,'move/벌레먹기',set_damage=True)
  self.assertFalse(self.attacker.buffs);self.assertEqual(self.target.spec['food_consumption_receipts'][0]['buff_id'],receipt['buff_id'])
  self.setUp();receipt=self.consume(self.target);self.begin_attack();self.e.accuracy_check=lambda *a,**k:(False,1,False)
  self.e.use_move(self.attacker,self.target,'move/벌레먹기',set_damage=True)
  self.assertFalse(self.attacker.buffs);self.assertEqual(self.target.spec['food_consumption_receipts'][0]['buff_id'],receipt['buff_id'])

 def test_copy_survives_snapshot_json_and_its_own_consumption(self):
  source=self.consume(self.target);copied=self.direct_transfer()
  self.e.gm.restore(self.e.gm.snapshot('consumed Bug Bite replay'))
  payload=json.loads(json.dumps(dump_engine(self.e),ensure_ascii=False));loaded=load_engine(self.rules,payload)
  actors={row.entity_id:row for row in loaded.everyone};attacker=actors[self.attacker.entity_id]
  loaded.consume_food_buff(attacker,buff_id=copied['id'],action_kind='free',action_reason='consume stolen food effect')
  self.assertFalse(attacker.buffs);receipt=attacker.spec['food_consumption_receipts'][-1]
  self.assertEqual(receipt['food_transfer_origin']['buff_id'],source['buff_id'])
  self.assertEqual(attacker.counters.get('lim:food_buff_consumed',0),0)
  self.assertTrue(loaded.validate_state()['valid'],loaded.validate_state())
  self.assertTrue(load_engine(self.rules,json.loads(json.dumps(dump_engine(loaded),ensure_ascii=False))).validate_state()['valid'])

 def test_honey_thief_triggers_only_after_real_consumed_receipt_copy(self):
  self.consume(self.target);self.e.gm.set_ability(self.attacker,'꿀도둑',True,reason='observed native ability')
  self.assertEqual(self.attacker.temp_hp,0);copied=self.direct_transfer()
  self.assertEqual(self.attacker.temp_hp,self.e.tick(self.attacker))
  event=self.attacker.custom_conditions[TEMP.STATE]['grant_event']
  self.assertEqual((event['kind'],event['effect_id'],event['from_actor_id']),('food_effect_transfer',copied['id'],self.target.entity_id))

 def test_tampered_source_receipt_or_copy_provenance_fails_world_and_persistence(self):
  self.consume(self.target);copied=self.direct_transfer();good=deepcopy(copied['food_transfer_origin'])
  for mutate in ('origin','receipt'):
   with self.subTest(mutate=mutate):
    copied['food_transfer_origin']=deepcopy(good);self.target.spec['food_consumption_receipts'][0]['effect']['amount']=5
    if mutate=='origin':copied['food_transfer_origin']['receipt_fingerprint']='0'*64
    else:self.target.spec['food_consumption_receipts'][0]['effect']['amount']=6
    result=self.e.validate_state();self.assertFalse(result['valid'],result)
    with self.assertRaises(Exception):dump_engine(self.e)
    self.target.spec['food_consumption_receipts'][0]['effect']['amount']=5
  copied['food_transfer_origin']=good;self.assertTrue(self.e.validate_state()['valid'],self.e.validate_state())


if __name__=='__main__':unittest.main(verbosity=2)
