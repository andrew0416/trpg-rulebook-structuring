"""Native Minimize and learned Shrinkable own distinct state and lifetimes."""
from copy import deepcopy
import unittest
import test_category2_body_modes as _fixture_test_category2_body_modes
import body_modes as MODE,body_state as BODY,state_grants as G,effect_lifetimes as LIFE
class Tests(unittest.TestCase):
 setUpClass=classmethod(_fixture_test_category2_body_modes.Tests.setUpClass.__func__)
 setUp=_fixture_test_category2_body_modes.Tests.setUp
 add=_fixture_test_category2_body_modes.Tests.add
 pokemon=_fixture_test_category2_body_modes.Tests.pokemon
 restored=_fixture_test_category2_body_modes.Tests.restored
 begin=_fixture_test_category2_body_modes.Tests.begin
 known=_fixture_test_category2_body_modes.Tests.known
 normal=_fixture_test_category2_body_modes.Tests.normal
 def learn(self):
  self.p.spec['size']='Medium';self.known(self.p,'작아지기')
 def use(self):return self.e.use_move(self.p,self.p,'move/작아지기')
 def test_learning_does_not_activate_move_or_capability_and_move_keeps_standards(self):
  self.learn();self.assertIn('수축성',G.effective_capabilities(self.p));self.assertNotIn(MODE.KEY,self.p.spec)
  self.assertEqual(LIFE.numeric(self.p,'evasion_modifier'),0)
  self.begin(self.p);self.use()
  self.assertEqual(self.p.spec['size'],'Small');self.assertNotIn(MODE.KEY,self.p.spec)
  self.assertEqual(LIFE.numeric(self.p,'evasion_modifier'),4)
  self.begin(self.p)
  import turn as TURN
  self.assertTrue(TURN.spend(self.e,self.p,'standard','ordinary Standard still allowed after Minimize'))
 def test_capability_does_not_consume_move_quota_or_end_with_encounter(self):
  self.learn();self.begin(self.p);before=deepcopy(self.p.move_uses)
  self.e.change_body_mode(self.p,'shrink',size_ratio=0.5,offsets=[(0,0)],reason='capability geometry')
  self.assertEqual(self.p.move_uses,before);self.assertEqual(LIFE.numeric(self.p,'evasion_modifier'),0)
  self.e.end_of_turn(self.p);self.e.end_encounter(self.e.everyone)
  self.assertEqual(self.p.spec[MODE.KEY]['mode'],'shrink');self.assertEqual(self.p.spec['size'],'Medium')
 def test_move_state_restores_and_expires_without_removing_learned_capability(self):
  self.learn();self.begin(self.p);self.use();self.e.gm.snapshot('minimize')
  loaded=self.restored();p=next(c for c in loaded.everyone if c.entity_id==self.p.entity_id)
  self.assertEqual((p.spec['size'],LIFE.numeric(p,'evasion_modifier')),('Small',4))
  loaded.end_encounter(loaded.everyone);self.assertEqual((p.spec['size'],LIFE.numeric(p,'evasion_modifier')),('Medium',0))
  self.e.end_encounter(self.e.everyone);self.assertEqual(self.p.spec['size'],'Medium')
  self.assertIn('수축성',G.effective_capabilities(self.p))
  self.e.gm.restore('minimize');self.assertEqual((self.p.spec['size'],LIFE.numeric(self.p,'evasion_modifier')),('Small',4))
 def test_capability_after_move_has_independent_modifier_and_lifetime(self):
  self.learn();self.begin(self.p);self.use();self.begin(self.p)
  self.e.change_body_mode(self.p,'shrink',size_ratio=0.5,offsets=[(0,0)],reason='capability after Move')
  self.assertEqual((MODE.evasion(self.p),LIFE.numeric(self.p,'evasion_modifier')),(4,4))
  self.e.end_encounter(self.e.everyone)
  self.assertEqual((MODE.evasion(self.p),LIFE.numeric(self.p,'evasion_modifier')),(4,0))
  self.assertEqual(self.p.spec['size'],'Medium')
if __name__=='__main__':unittest.main()
