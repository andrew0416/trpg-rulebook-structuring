"""Paired contest saved state must preserve the actual participation model."""
import unittest
import test_category2_state_codec as _fixture_test_category2_state_codec
from state_codec import dump_contest,StateCodecError
class Pause(Exception):pass
class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  _fixture_test_category2_state_codec.ContestStateCodecTests.setUpClass()
  cls.nr=_fixture_test_category2_state_codec.ContestStateCodecTests.nr;cls.cr=_fixture_test_category2_state_codec.ContestStateCodecTests.cr
 fixture=_fixture_test_category2_state_codec.ContestStateCodecTests.fixture
 save_load=_fixture_test_category2_state_codec.ContestStateCodecTests.save_load
 def start(self,mode):
  e,cs,*_=self.fixture(paired=True)
  order=lambda c,t,r:([c,t] if mode=='simultaneous' else [c if r%2 else t])
  with self.assertRaises(Pause):e.run(cs,'근사함',lambda *a:(_ for _ in ()).throw(Pause()),trainer_model=mode,trainer_order=order)
  return e,cs,order
 def test_round_selection_rejects_missing_duplicate_and_wrong_pair_performers(self):
  for mode in ('simultaneous','alternating'):
   e,cs,_=self.start(mode);state=e._paired_run;c=cs[0];original=state['selections'][c]
   for invalid in ((),(c,c),(cs[1],)):
    state['selections'][c]=invalid
    with self.assertRaises(StateCodecError):dump_contest(e,cs)
   state['selections'][c]=original;del state['selections'][cs[1]]
   with self.assertRaises(StateCodecError):dump_contest(e,cs)
 def test_separate_pairs_and_simultaneous_voltage_cannot_alias_after_load(self):
  e,cs,_=self.start('simultaneous');p=e._trainer_partners[cs[0]]
  cs[0]._paired_state=p._paired_state={'excitement':0,'double_next':False,'immune_fumble':False}
  with self.assertRaises(StateCodecError):dump_contest(e,cs)
  del cs[0]._paired_state;del p._paired_state
  cs[1].stat_dice=e._trainer_partners[cs[1]].stat_dice=cs[0].stat_dice
  with self.assertRaises(StateCodecError):dump_contest(e,cs)
 def test_both_modes_resume_round_two_and_preserve_pools_and_turn_history(self):
  for mode in ('simultaneous','alternating'):
   e,cs,order=self.start(mode)
   def choose(c,r,a,k):
    if r==2:raise Pause()
    return '연속자르기',1
   with self.assertRaises(Pause):e.run(cs,'근사함',choose,trainer_model=mode,trainer_order=order)
   n,parts=self.save_load(e,cs);state=n._paired_run
   for c in parts:
    partner=n._trainer_partners[c];self.assertIs(c.stat_dice,partner.stat_dice)
    if mode=='alternating':self.assertIs(c._paired_state,partner._paired_state)
    else:self.assertNotIn('_paired_state',vars(c));self.assertNotIn('_paired_state',vars(partner))
   if mode=='alternating':
    c=parts[0];saved=state['previous'][c];state['previous'][c]=state['selections'][c][0]
    with self.assertRaises(StateCodecError):dump_contest(n,parts)
    state['previous'][c]=saved
   n.run(parts,'근사함',lambda *a:('연속자르기',0),trainer_model=mode,trainer_order=order)
   self.assertEqual(state['phase'],'complete');self.save_load(n,parts)
