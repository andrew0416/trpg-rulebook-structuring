"""Native Unnerve costs, target scope, stage/food consumers and exact expiry."""
from pathlib import Path
from unittest.mock import patch
import copy,json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from builder import build_trainer,build_pokemon
from grid import Grid
from state_codec import dump_engine,load_engine
import ability_target_limits as L,combat_timing as TIME,turn as TURN


class TargetLimitsTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(ROOT,ruleset='core')
 def setUp(self):
  self.e=Engine(self.r,704);self.e.grid=Grid(24,10)
  self.a=self.actor('source',(2,2),'party',abilities=[L.NAME])
  self.t=self.actor('target',(8,2),'enemy')
  self.other=self.actor('other',(8,4),'enemy')
 def actor(self,name,pos,side,*,abilities=(),pokemon=False):
  extra={'abilities':list(abilities),'pos':pos,'side':side,'size':'중형','items':{'초코바':2}}
  moves=['move/칼춤','move/몸통박치기']
  spec=build_pokemon(self.r,'이상해씨',10,name=name,moves=moves,extra=extra) if pokemon else build_trainer(self.r,name,10,dict.fromkeys(('hp','atk','def','spa','spd','spe'),10),extra=dict(extra,moves=moves))
  actor=Combatant(self.r,spec);self.e.gm.add_combatant(actor);return actor
 def begin(self,*,count=True):
  self.e.start_round(self.e.everyone)
  if count:self.e.start_of_turn(self.a,initiative_count=20)
  else:self.e.start_of_turn(self.a)
 def activate(self):return self.e.activate_ability(self.a,L.NAME,self.t)
 def next_round(self,actor=None):
  self.e.end_of_turn(actor or self.a)
  self.e.end_round();self.e.start_round(self.e.everyone)
 def feed(self):
  self.t.hp=max(1,self.t.max_hp-20)
  return self.e.use_item(self.t,'초코바',duration_minutes=1,duration_reason='actual source food intake')['buff_id']
 def test_native_swift_blocks_actual_swords_dance_but_keeps_loss_and_other_target(self):
  for pokemon in (False,True):
   with self.subTest(pokemon=pokemon):
    self.setUp()
    if pokemon:
     self.t.on_field=False;self.t=self.actor('Pokemon target',(8,2),'enemy',pokemon=True)
    self.begin();self.activate();self.assertEqual(self.a.budget['swift'],0)
    self.e.end_of_turn(self.a);self.e.start_of_turn(self.t,initiative_count=10)
    before=self.t.stages['atk'];self.e.use_move(self.t,self.t,'move/칼춤')
    self.assertEqual(self.t.stages['atk'],before);self.assertEqual(self.t.budget['standard'],0)
    self.e.change_stage(self.t,'def',-1);self.assertEqual(self.t.stages['def'],-1)
    self.e.change_stage(self.other,'atk',1);self.assertEqual(self.other.stages['atk'],1)
 def test_real_food_buff_rejection_is_atomic_until_exact_next_round_count(self):
  buff=self.feed();self.begin();self.activate();before=dump_engine(self.e)
  with self.assertRaisesRegex(ValueError,'Unnerve'):self.e.consume_food_buff(self.t,buff_id=buff,action_kind='free',action_reason='actual attempted consumption')
  self.assertEqual(before,dump_engine(self.e));self.next_round();self.e.at_initiative_count(21)
  self.assertTrue(L.blocked(self.e,self.t,'food_buff'));self.e.start_of_turn(self.t,initiative_count=20)
  self.assertFalse(L.blocked(self.e,self.t,'food_buff'));hp=self.t.hp
  result=self.e.consume_food_buff(self.t,buff_id=buff,action_kind='free',action_reason='actual allowed consumption')
  self.assertEqual(result['healed'],5);self.assertEqual(self.t.hp,hp+5);self.assertFalse(self.t.buffs)
 def test_invalid_source_target_range_and_missing_count_preserve_cost_and_state(self):
  for invalid in ('missing','suppressed','ally','range','self','clone','count','absent_source','absent_target'):
   with self.subTest(invalid=invalid):
    self.setUp()
    if invalid=='missing':self.a.spec['abilities']=[];self.a.abilities=[]
    elif invalid=='suppressed':self.a.abilities_suppressed=True
    elif invalid=='ally':self.t.side='party'
    elif invalid=='range':self.t.pos=(9,2)
    elif invalid=='self':self.t=self.a
    elif invalid=='clone':self.t=copy.copy(self.t)
    elif invalid in ('absent_source','absent_target'):
     unknown=self.a if invalid=='absent_source' else self.t
     del unknown.side;unknown.spec.pop('side',None)
    self.begin(count=invalid!='count');before=dump_engine(self.e)
    with self.assertRaises(ValueError):self.activate()
    self.assertEqual(before,dump_engine(self.e))
 def test_at_will_reuses_next_swift_without_inventing_scene_quota(self):
  self.begin();self.activate()
  self.assertTrue(TURN.spend(self.e,self.a,'standard','actual completed Standard'))
  self.assertTrue(TURN.spend(self.e,self.a,'shift','actual completed Shift'))
  before=dump_engine(self.e)
  with self.assertRaisesRegex(ValueError,'Swift'):self.activate()
  self.assertEqual(before,dump_engine(self.e));self.next_round();self.e.start_of_turn(self.a,initiative_count=20)
  self.assertFalse(L.blocked(self.e,self.t,'positive_stages'));self.activate()
  self.assertTrue(L.blocked(self.e,self.t,'positive_stages'));self.assertEqual(self.a.budget['swift'],0)
 def test_two_casters_keep_independent_full_round_deadlines(self):
  second=self.actor('second source',(3,2),'party',abilities=[L.NAME])
  self.begin();self.activate();self.e.end_of_turn(self.a);self.e.start_of_turn(second,initiative_count=10)
  self.e.activate_ability(second,L.NAME,self.t);self.assertEqual(len([r for r in TIME.records(self.t) if L.KEY in r]),2)
  self.next_round(second);self.e.at_initiative_count(20);self.assertTrue(L.blocked(self.e,self.t,'positive_stages'))
  self.e.at_initiative_count(10);self.assertFalse(L.blocked(self.e,self.t,'positive_stages'))
 def test_effect_survives_source_suppression_recall_and_distance_until_scene_end(self):
  self.begin();self.activate();self.a.abilities_suppressed=True;self.e.gm.recall(self.a,reason='actual source recall')
  self.e.gm.set_position(self.t,(18,2),reason='actual later distant position')
  self.assertTrue(L.blocked(self.e,self.t,'positive_stages'));self.e.end_scene(self.e.everyone)
  self.assertFalse(L.blocked(self.e,self.t,'positive_stages'))
 def test_json_restores_actual_source_alias_spent_swift_and_remaining_deadline(self):
  buff=self.feed();self.begin();self.activate()
  loaded=load_engine(self.r,json.loads(json.dumps(dump_engine(self.e),ensure_ascii=False)))
  actors={a.entity_id:a for a in loaded.everyone};a=actors[self.a.entity_id];t=actors[self.t.entity_id]
  record=next(r for r in TIME.records(t) if L.KEY in r)
  self.assertIs(record['applied_by'],a);self.assertIsNot(a,self.a);self.assertEqual(a.budget['swift'],0)
  before=dump_engine(loaded)
  with self.assertRaisesRegex(ValueError,'Unnerve'):loaded.consume_food_buff(t,buff_id=buff,action_kind='free',action_reason='actual restored attempted consumption')
  self.assertEqual(before,dump_engine(loaded));loaded.end_of_turn(a);loaded.end_round();loaded.start_round(loaded.everyone)
  loaded.at_initiative_count(21);self.assertTrue(L.blocked(loaded,t,'positive_stages'))
  loaded.at_initiative_count(20);self.assertFalse(L.blocked(loaded,t,'positive_stages'))
 def test_late_install_failure_rolls_back_actual_budget_record_and_frequency(self):
  self.begin();before=dump_engine(self.e)
  with patch.object(TIME,'install',side_effect=RuntimeError('late actual install failure')):
   with self.assertRaisesRegex(RuntimeError,'late actual'):self.activate()
  self.assertEqual(before,dump_engine(self.e));self.activate();self.assertTrue(L.blocked(self.e,self.t,'positive_stages'))


if __name__=='__main__':unittest.main()
