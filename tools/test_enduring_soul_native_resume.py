"""Actual Heavy Standard suffix and the two outstanding Not Yet boundaries."""
import unittest
from unittest.mock import patch
import tools.test_book_enduring_soul_csv as FIX
from engine import Engine
from grid import Grid
import heavy_standard_adapter as HEAVY
import heavy_injury_adapter as HEAVY_EVENTS
import temporary_hp as TEMP
import state_codec as CODEC
import world_entities as WORLD
from native_scenario_fixture import assert_rejected_unchanged


class NativeResumeTests(unittest.TestCase):
 setUpClass=classmethod(FIX.EnduringSoulCsvTests.setUpClass.__func__)
 setUp=FIX.EnduringSoulCsvTests.setUp
 encounter=FIX.EnduringSoulCsvTests.encounter
 acquire=FIX.EnduringSoulCsvTests.acquire
 begin=FIX.EnduringSoulCsvTests.begin
 answer=FIX.EnduringSoulCsvTests.answer
 not_yet=FIX.EnduringSoulCsvTests.not_yet
 use=FIX.EnduringSoulCsvTests.use
 latest=FIX.EnduringSoulCsvTests.latest
 valid=FIX.EnduringSoulCsvTests.valid

 def ordinary(self):
  self.e,self.a,self.p,self.foreign=self.encounter()
  self.e.gm.observe_loyalty(self.p,6,reason='actual cooperative current-owner Move relationship')
  self.e.grid=Grid(12,8)
  self.e.gm.set_injuries(self.p,5,reason='actual heavily injured native actor')
  self.e.gm.set_hp(self.p,value=self.p.base_max_hp,reason='observed current HP before the actual Standard')
  self.begin(self.p)

 def test_ordinary_native_standard_uses_real_loss_temp_provenance_budget_and_restore(self):
  for move in ('struggle','move/몸통박치기'):
   with self.subTest(move=move):
    self.ordinary();TEMP.grant(self.e,self.p,3,provenance={'source':'actual test protection'})
    before=self.p.hp;target_hp=self.foreign.hp
    try:self.use(self.p,self.foreign,move)
    except HEAVY_EVENTS.HeavyPending:
     self.fail(str([row.get('context_evidence') for row in self.e._heavy_events.values()]))
    events=[row for row in self.e._heavy_events.values() if row['kind']=='action_taken']
    self.assertEqual(len(events),1);event=events[0]
    self.assertEqual((event['status'],event['heavy_consequence']['amount']),('applied',5))
    self.assertTrue(event['continuation_reified']);self.assertIsNone(event['unexecuted_remainder'])
    self.assertEqual((self.p.hp,self.p.temp_hp),(before-2,0));self.assertLess(self.foreign.hp,target_hp)
    self.assertEqual(self.p.budget['standard'],0);self.assertEqual(self.p.move_uses[move],1)
    self.assertEqual(self.latest(self.p,move)['phase'],'complete')
    self.assertFalse(self.e._heavy_standard_receipts)
    saved=CODEC.dump_engine(self.e);restored=CODEC.load_engine(self.r,saved)
    actual=WORLD.actor_index(restored)[self.p.entity_id]
    self.assertEqual((actual.hp,actual.temp_hp),(before-2,0));self.assertTrue(restored.validate_state()['valid'])
    assert_rejected_unchanged(self.e,lambda:HEAVY.finish(self.e,object(),hit=True,dealt=1),reason_pattern='receipt absent')
    self.valid()

 def test_actual_heavy_loss_failure_rolls_back_not_yet_move_damage_cost_injury_and_rng(self):
  self.not_yet();self.e.gm.set_injuries(self.p,2,reason='actual existing injuries before HP-marker crossing')
  original=Engine._lose_hp
  def fail(e,actor,amount,source='damage',**options):
   if source=='heavily_injured_standard':raise ValueError('late actual Heavy native loss failure')
   return original(e,actor,amount,source,**options)
  with patch.object(Engine,'_lose_hp',fail),patch.object(Engine,'d20',return_value=10),FIX.observe_actual_heavy_hold(self):
   assert_rejected_unchanged(self.e,lambda:self.e.lose_hp(self.p,self.p.hp,source='condition/독'),
       reason_pattern='late actual Heavy native loss failure')
  self.valid()

 def test_cold_nonpositive_actor_never_receives_native_heavy_permission(self):
  self.ordinary();self.e.gm.set_hp(self.p,value=0,reason='actual fainted actor without Not Yet')
  before=CODEC.dump_engine(self.e)
  lines=self.e.log_lines[:]
  self.e.use_move_on(self.p,self.foreign,'struggle',self.e.everyone)
  self.assertTrue(any('동작 불가' in line for line in self.e.log_lines[len(lines):]))
  after=CODEC.dump_engine(self.e)
  for saved in (before,after):
   root=saved['nodes'][saved['root']['$ref']]
   attrs=saved['nodes'][root['attrs']['$ref']]
   reference=dict(attrs['items'])['log_lines']['$ref']
   saved['nodes'][reference]['items']=[]
  self.assertEqual(after,before)
  self.assertFalse(self.e._heavy_standard_receipts);self.assertFalse(self.e._heavy_events)


if __name__=='__main__':unittest.main()
