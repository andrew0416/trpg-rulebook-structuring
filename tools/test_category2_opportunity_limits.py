"""Actual source moves, costs, opportunity consumers and shared lifetime state."""
from pathlib import Path
from unittest.mock import patch
import copy,json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from builder import build_trainer
from grid import Grid
from state_codec import dump_engine,load_engine
from ruleset import ExcludedRuleSelection
import combat_timing as TIME,effect_lifetimes as LIFE,turn as TURN

MOVES=('move/찬물끼얹기','move/하이볼티지','move/반짝반짝')

class OpportunityLimitTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(ROOT,ruleset='all');cls.core=Rules(ROOT,ruleset='core')
 def setUp(self):
  self.e=Engine(self.r,705);self.e.grid=Grid(20,10)
  self.a=self.actor('source',(2,2),'party')
  self.t=self.actor('target',(3,2),'enemy')
  self.mover=self.actor('actual mover',(3,3),'party')
  self.other=self.actor('other enemy',(9,2),'enemy')
 def actor(self,name,pos,side):
  spec=build_trainer(self.r,name,30,dict.fromkeys(('hp','atk','def','spa','spd','spe'),20),extra={'moves':list(MOVES),'pos':pos,'side':side,'size':'중형'})
  actor=Combatant(self.r,spec);self.e.gm.add_combatant(actor);return actor
 def begin(self,count=20):
  self.e.start_round(self.e.everyone)
  if count is None:self.e.start_of_turn(self.a)
  else:self.e.start_of_turn(self.a,initiative_count=count)
 def hit(self,mid=MOVES[0],actor=None):
  with patch.object(self.e,'d20',return_value=10):return self.e.use_move(actor or self.a,self.t,mid)
 def next_round(self,owner=None):
  self.e.end_of_turn(owner or self.a);self.e.end_round();self.e.start_round(self.e.everyone)
 def test_three_actual_sources_pay_native_cost_and_only_block_the_hit_target(self):
  for mid in MOVES:
   with self.subTest(move=mid):
    self.setUp();self.begin();hp=self.t.hp
    self.assertTrue(TURN.can_aoo(self.e,self.t));self.hit(mid)
    self.assertLess(self.t.hp,hp);self.assertEqual(self.a.move_uses[mid],1)
    self.assertEqual(self.a.budget['standard'],0)
    records=TIME.records(self.t);self.assertEqual(len(records),1)
    self.assertEqual(records[0]['source'],mid);self.assertEqual(tuple(records[0]['count_deadline']),(1+self.e.round_no,20))
    self.assertFalse(TURN.can_aoo(self.e,self.t));self.assertTrue(TURN.can_aoo(self.e,self.other))
    self.assertFalse(LIFE.forbids(self.a,'attack_of_opportunity'))
    self.assertEqual(self.t.stages['atk'],0 if mid==MOVES[1] else -1)
 def test_miss_spends_the_move_without_installing_prohibition_or_stage_loss(self):
  for mid in MOVES:
   with self.subTest(move=mid):
    self.setUp();self.begin();hp=self.t.hp
    with patch.object(self.e,'d20',return_value=1):self.e.use_move(self.a,self.t,mid)
    self.assertEqual(self.t.hp,hp);self.assertFalse(TIME.records(self.t));self.assertEqual(self.t.stages['atk'],0)
    self.assertTrue(TURN.can_aoo(self.e,self.t));self.assertEqual(self.a.move_uses[mid],1)
    self.assertEqual(self.a.budget['standard'],0)
 def test_missing_initiative_count_rejects_before_cost_rng_or_state(self):
  self.begin(count=None);before=dump_engine(self.e)
  with self.assertRaisesRegex(ValueError,'initiative count'):self.e.use_move(self.a,self.t,MOVES[0])
  self.assertEqual(before,dump_engine(self.e))
 def test_actual_opportunity_attempt_is_unspent_until_full_round_count_expires(self):
  self.begin();self.hit();hp=self.mover.hp
  TURN.trigger_aoo(self.e,self.mover,'actual adjacent departure',enemies=[self.t])
  self.assertEqual(self.mover.hp,hp);self.assertFalse(self.t.aoo_used)
  self.next_round();self.assertTrue(LIFE.forbids(self.t,'attack_of_opportunity'))
  self.e.at_initiative_count(21);self.assertFalse(TURN.can_aoo(self.e,self.t))
  self.e.at_initiative_count(20);self.assertTrue(TURN.can_aoo(self.e,self.t))
  with patch.object(self.e,'d20',return_value=10):TURN.trigger_aoo(self.e,self.mover,'actual later departure',enemies=[self.t])
  self.assertTrue(self.t.aoo_used);self.assertLess(self.mover.hp,hp)
 def test_overlapping_sources_expire_independently_at_their_actual_counts(self):
  second=self.actor('second source',(4,2),'party');self.begin();self.hit()
  self.e.end_of_turn(self.a);self.e.start_of_turn(second,initiative_count=10);self.hit(MOVES[2],second)
  self.assertEqual(len(TIME.records(self.t)),2);self.next_round(second)
  self.e.at_initiative_count(20);self.assertEqual([r['source'] for r in TIME.records(self.t)],[MOVES[2]])
  self.assertFalse(TURN.can_aoo(self.e,self.t));self.e.at_initiative_count(10)
  self.assertTrue(TURN.can_aoo(self.e,self.t));self.assertEqual(self.t.stages['atk'],-2)
 def test_json_restore_keeps_receipt_target_source_and_exact_remaining_lifetime(self):
  self.begin();self.hit(MOVES[2]);saved=json.loads(json.dumps(dump_engine(self.e),ensure_ascii=False))
  restored=load_engine(self.r,saved);a=next(c for c in restored.everyone if c.entity_id==self.a.entity_id);t=next(c for c in restored.everyone if c.entity_id==self.t.entity_id)
  self.assertFalse(TURN.can_aoo(restored,t));self.assertEqual(TIME.records(t)[0]['source'],MOVES[2])
  token=TIME.records(t)[0]['effect_receipt'];receipt=restored._effect_dispatch_receipts[token]
  self.assertIs(receipt['receipt'],token);self.assertIs(receipt['actor'],a);self.assertIs(receipt['target'],t)
  self.assertEqual(receipt['source_id'],MOVES[2])
  self.assertEqual(receipt['effect'],self.e._effect_dispatch_receipts[TIME.records(self.t)[0]['effect_receipt']]['effect'])
  restored.end_of_turn(a);restored.end_round();restored.start_round(restored.everyone)
  restored.at_initiative_count(21);self.assertFalse(TURN.can_aoo(restored,t))
  restored.at_initiative_count(20);self.assertTrue(TURN.can_aoo(restored,t));self.assertEqual(t.stages['atk'],-1)
 def test_structured_prohibition_reuses_validated_shared_seconds_and_restore(self):
  effect={'type':'forbid','actions':['attack_of_opportunity'],'target':'target','duration':{'seconds':10}}
  self.assertEqual(self.e.apply_effect(self.a,self.t,effect,None,True,0,'gm/opportunity-limit'),(1,0))
  restored=load_engine(self.r,json.loads(json.dumps(dump_engine(self.e))))
  target=next(c for c in restored.everyone if c.entity_id==self.t.entity_id)
  restored.advance_time(9);self.assertFalse(TURN.can_aoo(restored,target))
  restored.advance_time(1);self.assertTrue(TURN.can_aoo(restored,target))
 def test_native_scene_and_encounter_end_clear_the_timed_limit(self):
  for boundary in ('end_scene','end_encounter'):
   with self.subTest(boundary=boundary):
    self.setUp();self.begin();self.hit();getattr(self.e,boundary)(self.e.everyone)
    self.assertFalse(LIFE.forbids(self.t,'attack_of_opportunity'));self.assertEqual(self.t.stages['atk'],0)
 def test_unreviewed_action_prohibition_and_excluded_variants_fail_before_payment(self):
  self.begin();bad=copy.deepcopy(self.r.moves_reviewed[MOVES[0]]);bad['effects'][0]['actions']=['standard']
  before=dump_engine(self.e)
  with patch.dict(self.r.moves_reviewed,{MOVES[0]:bad}):
   with self.assertRaisesRegex(ValueError,'native action consumer'):self.e.use_move(self.a,self.t,MOVES[0])
  self.assertEqual(before,dump_engine(self.e))
  for mid in MOVES[1:]:
   with self.assertRaises(ExcludedRuleSelection):self.core.move_mech(mid)

if __name__=='__main__':unittest.main()
