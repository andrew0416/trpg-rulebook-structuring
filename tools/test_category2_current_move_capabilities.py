"""Imported current totals change only by independently owned learned deltas."""
from pathlib import Path
from copy import deepcopy
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_progression_state as _fixture_test_category2_progression_state
import move_capabilities as CAP,state_grants as G,movement_actions as M,jump_actions as J,capability_actions as P,state_codec as CODEC,state_fields as F

class Tests(unittest.TestCase):
 setUpClass=classmethod(_fixture_test_category2_progression_state.ProgressionStateTests.setUpClass.__func__)
 setUp=_fixture_test_category2_progression_state.ProgressionStateTests.setUp
 add=_fixture_test_category2_progression_state.ProgressionStateTests.add
 pokemon=_fixture_test_category2_progression_state.ProgressionStateTests.pokemon
 restored=_fixture_test_category2_progression_state.ProgressionStateTests.restored
 def imported(self,c,names=()):
  # Explicit legacy import: values already include the supplied known moves.
  c.spec['moves']=['move/'+n for n in names];c.moves=list(c.spec['moves'])
  c.spec.pop(CAP.TOTALS_KEY,None);c.spec['power_basis']='current'
  self.e.gm.choose_learned_capability_policy(c,'move/공중날기','move_entry',reason='import resolves Fly source conflict')
  self.e.gm.set_movement_capabilities(c,{'land':8,'power':6,'sky':7,'high_jump':3,'long_jump':5},basis='current',reason='actual current imported totals include supplied known Moves')
  return c
 def learn(self,c,name):self.e.gm.set_move(c,'move/'+name,reason='new learning after observation')
 def forget(self,c,name):self.e.gm.set_move(c,'move/'+name,add=False,reason='forgotten after observation')
 def test_imported_totals_forget_relearn_and_repeat_reads_both_actor_kinds(self):
  for c in (self.a,self.pokemon()):
   self.imported(c,['괴력','튀어오르기','달려들기','공중날기'])
   before=deepcopy(c.spec['movement'])
   self.assertEqual(P.power(c),6);self.assertEqual(J.limits(c)['long_jump'],5)
   self.forget(c,'괴력');self.forget(c,'튀어오르기');self.forget(c,'달려들기');self.forget(c,'공중날기')
   self.assertEqual(P.power(c),5);self.assertEqual(J.limits(c)['long_jump'],3)
   self.assertEqual((M.capabilities(self.e,c)['land'],M.capabilities(self.e,c)['sky']),(7,4))
   for name in ['괴력','튀어오르기','달려들기','공중날기']:self.learn(c,name)
   for unused in range(3):self.assertEqual((P.power(c),J.limits(c)['long_jump'],M.capabilities(self.e,c)['sky']),(6,5,7))
   self.assertEqual(c.spec['movement'],before)
 def test_new_learning_stacks_different_moves_not_duplicate_ownership_or_permission(self):
  c=self.imported(self.pokemon())
  G.grant_moves(c,['move/괴력'],'permission','temporary',mode='permission');self.assertEqual(P.power(c),6)
  G.grant_moves(c,['move/괴력'],'one','feature',lifetime='while_owned');G.grant_moves(c,['move/괴력'],'two','feature',lifetime='while_owned')
  self.assertEqual(P.power(c),7);G.revoke(c,'one');self.assertEqual(P.power(c),7)
  G.overlay(c,'display',moves=['move/튀어오르기']);self.assertEqual(J.limits(c)['long_jump'],5)
  G.revoke(c,'two');self.assertEqual(P.power(c),6)
  self.learn(c,'튀어오르기');self.learn(c,'달려들기');self.assertEqual(J.limits(c)['long_jump'],7)
 def test_legacy_without_receipt_captures_before_first_forgetting(self):
  c=self.imported(self.pokemon(),['괴력','구멍파기']);c.spec['movement']['burrow']=5;c.spec.pop(CAP.TOTALS_KEY,None)
  self.forget(c,'괴력');self.forget(c,'구멍파기')
  self.assertEqual(P.power(c),5);self.assertEqual(M.capabilities(self.e,c)['burrow'],2)
 def test_new_mode_disappears_when_last_learning_source_is_lost(self):
  c=self.imported(self.pokemon());c.spec['movement'].pop('sky');c.spec.pop(CAP.TOTALS_KEY,None)
  self.learn(c,'공중날기');self.assertEqual(M.capabilities(self.e,c)['sky'],3)
  self.forget(c,'공중날기');self.assertNotIn('sky',M.capabilities(self.e,c))
 def test_reobservation_and_base_patch_rebase_included_grants_without_old_delta(self):
  c=self.imported(self.pokemon());self.learn(c,'괴력');self.assertEqual(P.power(c),7)
  self.e.gm.set_movement_capabilities(c,dict(c.spec['movement'],power=9),basis='current',reason='fresh current total observation')
  self.assertEqual(P.power(c),9);self.forget(c,'괴력');self.assertEqual(P.power(c),8)
  self.learn(c,'괴력');F.base_patch(c,{'movement':dict(c.spec['movement'],power=10)},reason='new imported current field values')
  self.assertEqual(P.power(c),10);self.forget(c,'괴력');self.assertEqual(P.power(c),9)
 def test_source_choice_changes_only_fly_contribution_and_survives_json(self):
  c=self.imported(self.pokemon(),['공중날기']);uid=c.entity_id
  self.e.gm.choose_learned_capability_policy(c,'move/공중날기','capability_entry',reason='GM now uses capability paragraph')
  self.assertEqual(M.capabilities(self.e,c)['sky'],8)
  restored=self.restored();c=next(a for a in restored.gm.everyone if a.entity_id==uid)
  restored.gm.set_move(c,'move/공중날기',add=False,reason='forget after durable load')
  self.assertEqual(M.capabilities(restored,c)['sky'],4);self.assertTrue(restored.validate_state()['valid'])
 def test_invalid_current_total_and_missing_source_choice_reject_atomically(self):
  c=self.imported(self.pokemon(),['괴력']);c.spec['movement']['power']=0;c.spec.pop(CAP.TOTALS_KEY,None);before=deepcopy(c.spec)
  with self.assertRaises(ValueError):self.forget(c,'괴력')
  self.assertEqual(c.spec,before)
  c=self.imported(self.pokemon());c.spec.pop(CAP.CHOICES_KEY,None);before=deepcopy(c.spec)
  with self.assertRaisesRegex(ValueError,'source choice'):self.learn(c,'공중날기')
  self.assertEqual(c.spec,before)
 def test_native_alias_learning_is_canonicalized_and_current_jump_loses_real_reach(self):
  from grid import Grid
  c=self.imported(self.pokemon());self.e.grid=Grid(20,10);c.pos=(1,1)
  self.e.gm.set_move(c,'튀어오르기',reason='resolved native Korean alias')
  self.assertEqual(J.limits(c)['long_jump'],6)
  self.e.gm.set_move(c,'move/튀어오르기',add=False,reason='forget by canonical ID after alias learning')
  self.e.start_round([c]);self.e.start_of_turn(c)
  before=(c.pos,dict(c.budget),self.e.rng.getstate())
  with self.assertRaises(ValueError):self.e.jump(c,(7,1),jump_id='lost',difficult=False,clear_path=True,reason_text='observed6m gap beyond5m')
  self.assertEqual((c.pos,c.budget,self.e.rng.getstate()),before)
  out=self.e.jump(c,(6,1),jump_id='within',difficult=False,clear_path=True,reason_text='observed5m clear gap')
  self.assertEqual(out['effective_limits']['long_jump'],5);self.assertEqual(c.pos,(6,1));self.assertEqual(c.budget['shift'],0)
 def test_snapshot_restores_included_sources_and_corrupt_record_rejects(self):
  c=self.imported(self.pokemon(),['괴력']);self.e.gm.snapshot('current');self.forget(c,'괴력');self.e.gm.restore('current')
  self.assertEqual(P.power(c),6);self.forget(c,'괴력');self.assertEqual(P.power(c),5)
  c.spec[CAP.TOTALS_KEY]['power']['included'][0]['amount']=2
  with self.assertRaises(CODEC.StateCodecError):CODEC.dump_engine(self.e)

if __name__=='__main__':unittest.main()
