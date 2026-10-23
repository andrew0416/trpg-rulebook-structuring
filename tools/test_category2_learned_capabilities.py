"""Shared learned Special ownership, source loss and durable restoration."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_progression_state as _fixture_test_category2_progression_state
import state_grants as G,move_capabilities as CAP,movement_actions as M

class Tests(unittest.TestCase):
 setUpClass=classmethod(_fixture_test_category2_progression_state.ProgressionStateTests.setUpClass.__func__)
 setUp=_fixture_test_category2_progression_state.ProgressionStateTests.setUp
 add=_fixture_test_category2_progression_state.ProgressionStateTests.add
 pokemon=_fixture_test_category2_progression_state.ProgressionStateTests.pokemon
 restored=_fixture_test_category2_progression_state.ProgressionStateTests.restored
 def test_all_reviewed_sources_both_actor_kinds_project_without_casting_and_forget(self):
  self.assertEqual(len(CAP.policy(self.r)['sources']),38)
  for actor in (self.a,self.pokemon()):
   original=G.effective_capabilities(actor)
   for mid,row in CAP.policy(self.r)['sources'].items():
    with self.subTest(kind=actor.kind,move=mid):
     self.e.gm.set_move(actor,mid,reason='observed learning')
     self.assertTrue(set(row['capabilities']).issubset(G.effective_capabilities(actor)))
     self.assertEqual([v['source'] for v in CAP.contributions(actor)],[mid])
     self.assertFalse(actor.move_uses)
     self.e.gm.set_move(actor,mid,add=False,reason='observed forgetting')
     self.assertEqual(G.effective_capabilities(actor),original)
 def test_permission_and_display_overlay_are_not_learning_or_forgetting(self):
  actor=self.pokemon();G.grant_moves(actor,['move/물대포'],'copy','temporary',mode='permission')
  self.assertIn('move/물대포',actor.moves);self.assertNotIn('물줄기',G.effective_capabilities(actor))
  self.e.gm.set_move(actor,'move/불꽃세례',reason='actually learned')
  G.overlay(actor,'display',moves=['move/순풍'])
  self.assertEqual(actor.moves,['move/순풍'])
  self.assertIn('불쏘시개',G.effective_capabilities(actor));self.assertNotIn('세찬바람',G.effective_capabilities(actor))
  self.e.gm.set_move(actor,'move/불꽃세례',add=False,reason='forget hidden owned move')
  self.assertNotIn('불쏘시개',G.effective_capabilities(actor))
 def test_same_capability_sources_and_independent_baseline_end_separately(self):
  actor=self.pokemon()
  G.grant_moves(actor,['move/물대포'],'first','feature',lifetime='while_owned')
  G.grant_moves(actor,['move/물놀이'],'second','feature',lifetime='while_owned')
  G.grant_moves(actor,['move/물놀이'],'third','feature',lifetime='while_owned')
  self.assertEqual(G.effective_capabilities(actor).count('물줄기'),1)
  self.assertEqual(len(CAP.contributions(actor)),2)
  G.revoke(actor,'second');G.revoke(actor,'first')
  self.assertIn('물줄기',G.effective_capabilities(actor))
  G.set_baseline(actor,'capabilities',['물줄기']);G.revoke(actor,'third')
  self.assertEqual(CAP.contributions(actor),());self.assertIn('물줄기',G.effective_capabilities(actor))
 def test_snapshot_and_json_restore_retain_permissions_and_source_removal(self):
  actor=self.pokemon();uid=actor.entity_id
  G.grant_moves(actor,['move/물대포'],'learned','feature',lifetime='while_owned')
  G.grant_moves(actor,['move/순풍'],'permission','temporary',mode='permission')
  self.e.gm.snapshot('ownership');G.revoke(actor,'learned');self.e.gm.restore('ownership')
  restored=self.restored();actor=next(c for c in restored.gm.everyone if c.entity_id==uid)
  self.assertIn('물줄기',G.effective_capabilities(actor));self.assertNotIn('세찬바람',G.effective_capabilities(actor))
  G.revoke(actor,'learned');self.assertNotIn('물줄기',G.effective_capabilities(actor))
  self.assertTrue(restored.validate_state()['valid'])
 def test_numeric_movement_uses_same_learning_ownership_without_casting(self):
  actor=self.pokemon();actor.spec.update(movement={'land':6},movement_basis='base')
  self.e.gm.choose_learned_capability_policy(actor,'move/공중날기','capability_entry',reason='explicit capability paragraph policy')
  for mid,(mode,amount) in {'move/구멍파기':('burrow',3),'move/공중날기':('sky',4),'move/다이빙':('swim',3),'move/순간이동':('teleport',4)}.items():
   with self.subTest(move=mid):
    G.grant_moves(actor,[mid],'permission','temporary',mode='permission')
    self.assertNotIn(mode,M.capabilities(self.e,actor))
    G.grant_moves(actor,[mid],'learned','feature',lifetime='while_owned')
    self.assertEqual(M.capabilities(self.e,actor)[mode],amount)
    G.overlay(actor,'display',moves=[])
    self.assertEqual(M.capabilities(self.e,actor)[mode],amount)
    G.revoke(actor,'learned');self.assertNotIn(mode,M.capabilities(self.e,actor))
    G.revoke(actor,'permission');G.revoke(actor,'display')
 def test_read_only_projection_and_changed_extraction_reject(self):
  self.e.gm.set_move(self.a,'move/바람일으키기',reason='actual known move')
  before=deepcopy(self.a.spec);rng=self.e.rng.getstate()
  self.assertIn('세찬바람',G.effective_capabilities(self.a))
  self.assertEqual(self.a.spec,before);self.assertEqual(self.e.rng.getstate(),rng)
  with patch.object(self.r,'move_mech',return_value=({'effects_exec':[{'type':'grant_capability','capability':'wrong'}]},'test')):
   with self.assertRaisesRegex(ValueError,'extraction'):CAP.contributions(self.a)
  self.assertEqual(self.a.spec,before)
 def test_passive_grants_omitted_by_action_adapters_still_follow_original_source(self):
  for name,cap in [('불꽃세례','불쏘시개'),('달콤한향기','매혹')]:
   self.e.gm.set_move(self.a,'move/'+name,reason='actual learning')
   self.assertIn(cap,G.effective_capabilities(self.a))
   self.e.gm.set_move(self.a,'move/'+name,add=False,reason='actual forgetting')
   self.assertNotIn(cap,G.effective_capabilities(self.a))

if __name__=='__main__':unittest.main()
