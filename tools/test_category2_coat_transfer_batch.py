"""Direct contract checks for typed Coat consumption and Baton Pass transfer."""
from copy import deepcopy
from pathlib import Path
import json,sys,unittest

STAGE=Path(__file__).resolve().parents[1]
ROOT=Path(r"D:\trpg-rulebook-structuring\ptk-structure-experiment")
sys.path[:0]=[str(STAGE/'engine'),str(ROOT/'engine'),str(ROOT/'tools')]

import coat_effects as COATS
import damage_coats
import effect_contracts
import effects_ext
import test_category2_coat_effects as _fixture_test_category2_coat_effects
import effect_instances as INSTANCES
import state_codec as CODEC


class CoatTransferBatchTests(unittest.TestCase):
 setUpClass=classmethod(_fixture_test_category2_coat_effects.CoatEffectTests.setUpClass.__func__)
 add=_fixture_test_category2_coat_effects.CoatEffectTests.add

 def setUp(self):
  _fixture_test_category2_coat_effects.CoatEffectTests.setUp(self)
  self.e.gm.set_move(self.p,'move/아쿠아링',reason='actual learned Coat Move')
  self.e.gm.set_move(self.p,COATS.BATON,reason='actual learned Baton Pass')
  self.e.start_round(self.e.everyone);self.e.start_of_turn(self.p,initiative_count=20)

 def choose(self):
  self.other.on_field=False
  return COATS.select_transfer(self.e,self.p,self.other,reason='actual owner selected reserve Pokemon')

 def test_actual_baton_pass_moves_same_instance_and_continues_on_new_holder_turn(self):
  self.p.hp=1;self.e.use_move(self.p,self.p,'move/아쿠아링')
  record=COATS.live(self.p)[0];uid=record['id'];origin=record[INSTANCES.KEY]['origin_actor_id'];position=self.p.pos
  self.choose();self.e.end_of_turn(self.p);self.e.start_round(self.e.everyone);self.e.start_of_turn(self.p,initiative_count=20)
  self.e.use_move(self.p,self.p,COATS.BATON)
  self.assertFalse(self.p.on_field);self.assertTrue(self.other.on_field);self.assertEqual(self.other.pos,position)
  self.assertFalse(COATS.live(self.p));moved=COATS.live(self.other)[0]
  self.assertEqual((moved['id'],moved[INSTANCES.KEY]['origin_actor_id']),(uid,origin))
  self.assertEqual(moved[INSTANCES.KEY]['ownership'][-1],{'kind':'transfer','from_holder_id':self.p.entity_id,'holder_id':self.other.entity_id,'at':self.e.elapsed_seconds,'source':COATS.BATON})
  self.other.hp=1;self.e.end_of_turn(self.p);self.e.start_round(self.e.everyone);self.e.start_of_turn(self.other,initiative_count=20)
  self.assertEqual(self.other.hp,1+self.e.tick(self.other));self.assertEqual(moved['applications'][-1]['holder_id'],self.other.entity_id)
  self.assertTrue(self.e.validate_state()['valid'])

 def test_selection_and_same_source_collision_fail_before_move_cost_or_mutation(self):
  self.e.use_move(self.p,self.p,'move/아쿠아링');before=deepcopy((self.p.spec,self.p.budget,self.p.coats,self.other.coats,self.e.rng.getstate()))
  with self.assertRaises(ValueError):COATS.select_transfer(self.e,self.p,self.a,reason='not an owned Pokemon')
  self.assertEqual((self.p.spec,self.p.budget,self.p.coats,self.other.coats,self.e.rng.getstate()),before)
  self.choose();raw=COATS.definition(self.r,'move/아쿠아링')['raw'];COATS.grant(self.e,self.other,raw,'move/아쿠아링')
  before=deepcopy((self.p.spec,self.p.budget,self.p.coats,self.other.coats,self.e.rng.getstate()))
  with self.assertRaisesRegex(ValueError,'composition'):self.e.use_move(self.p,self.p,COATS.BATON)
  self.assertEqual((self.p.spec,self.p.budget,self.p.coats,self.other.coats,self.e.rng.getstate()),before)

 def test_pending_choice_and_transferred_owner_roundtrip_durably(self):
  self.e.use_move(self.p,self.p,'move/아쿠아링');self.choose()
  pending=json.loads(json.dumps(CODEC.dump_engine(self.e),ensure_ascii=False))
  restored=CODEC.load_engine(self.r,pending)
  p=next(x for x in restored.everyone if x.entity_id==self.p.entity_id)
  other=next(x for x in restored.everyone if x.entity_id==self.other.entity_id)
  self.assertEqual(p.spec[COATS.TRANSFER_CHOICES][COATS.BATON]['replacement_id'],other.entity_id)
  restored.end_of_turn(p);restored.start_round(restored.everyone);restored.start_of_turn(p,initiative_count=20)
  restored.use_move(p,p,COATS.BATON)
  saved=json.loads(json.dumps(CODEC.dump_engine(restored),ensure_ascii=False));again=CODEC.load_engine(self.r,saved)
  holder=next(x for x in again.everyone if x.entity_id==other.entity_id)
  self.assertEqual(COATS.live(holder)[0][INSTANCES.KEY]['ownership'][-1]['source'],COATS.BATON)
  self.assertTrue(again.validate_state()['valid'])


if __name__=='__main__':unittest.main()
