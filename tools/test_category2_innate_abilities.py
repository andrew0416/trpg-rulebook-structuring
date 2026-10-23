"""Whole Innate identity protection through actual selected-ability producers."""
from pathlib import Path
from copy import deepcopy
import sys,json,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_ability_transitions as _fixture_test_category2_ability_transitions
from engine import Engine,Rules
import state_grants as G,ability_transitions as A
INNATE=('초상투영','연대감','테라방망이','가변변속기','마이티체인지')

class Tests(unittest.TestCase):
 setUpClass=classmethod(_fixture_test_category2_ability_transitions.AbilityTransitionTests.setUpClass.__func__)
 setUp=_fixture_test_category2_ability_transitions.AbilityTransitionTests.setUp
 actor=_fixture_test_category2_ability_transitions.AbilityTransitionTests.actor
 select=_fixture_test_category2_ability_transitions.AbilityTransitionTests.select
 use=_fixture_test_category2_ability_transitions.AbilityTransitionTests.use
 live=_fixture_test_category2_ability_transitions.AbilityTransitionTests.live
 def test_all_five_whole_innate_abilities_block_skill_swap_on_either_participant(self):
  for name in INNATE:
   for innate_user in (False,True):
    with self.subTest(ability=name,innate_user=innate_user):
     self.setUp();user=name if innate_user else '인분';target='인분' if innate_user else name
     G.replace_baseline(self.e,self.a,'abilities',[user]);G.replace_baseline(self.e,self.t,'abilities',[target])
     self.select('move/스킬스왑',user);self.use('move/스킬스왑')
     self.assertEqual(self.a.abilities,[user]);self.assertEqual(self.t.abilities,[target]);self.assertFalse(self.live(self.a)+self.live(self.t))
     results=[x['result'] for x in self.e._effect_dispatch_receipts.values() if x.get('result')]
     self.assertTrue(any(x.get('applied') is False for x in results));self.assertEqual(self.a.move_uses['move/스킬스왑'],1)
 def test_all_five_whole_innate_abilities_block_copy_disable_and_replacement(self):
  for name in INNATE:
   for source in ('move/역할','move/위액','move/심플빔'):
    with self.subTest(ability=name,source=source):
     self.setUp();G.replace_baseline(self.e,self.t,'abilities',[name]);self.use(source)
     self.assertEqual(self.t.abilities,[name]);self.assertEqual(self.a.abilities,[]);self.assertFalse(self.live(self.a)+self.live(self.t))
 def test_manual_mask_ability_registration_does_not_activate_or_choose_a_form(self):
  before=deepcopy((self.t.types,getattr(self.t,'form',None)))
  G.replace_baseline(self.e,self.t,'abilities',['초상투영'])
  self.assertEqual((self.t.types,getattr(self.t,'form',None)),before)
  self.assertTrue(self.e.validate_state()['valid']);self.assertFalse(self.e.gm_prompts)
  with self.assertRaises(ValueError):self.e.activate_ability(self.t,'초상투영',self.t)
 def test_protected_identity_and_failure_survive_snapshot_and_durable_restore(self):
  G.replace_baseline(self.e,self.a,'abilities',['인분']);G.replace_baseline(self.e,self.t,'abilities',['연대감'])
  self.select('move/스킬스왑','인분');self.use('move/스킬스왑');self.e.gm.snapshot('innate')
  self.e.end_encounter(self.e.everyone);self.e.gm.restore('innate')
  saved=json.loads(json.dumps(self.e.export_state(),ensure_ascii=False));restored=Engine.import_state(Rules(ROOT,ruleset='core'),saved)
  target=next(c for c in restored.everyone if c.entity_id==self.t.entity_id)
  self.assertEqual(target.abilities,['연대감']);self.assertTrue(restored.validate_state()['valid'])
 def test_parser_innate_labels_alone_do_not_promote_unreviewed_sources(self):
  self.assertTrue(A.wholly_innate(self.r,'ability/연대감'))
  self.assertFalse(A.wholly_innate(self.r,'ability/요술'))
  self.assertFalse(A.wholly_innate(self.r,'ability/뱀무늬-playtest'))
  self.assertTrue(A.protected(self.r,'ability/멀티타입'))

if __name__=='__main__':unittest.main()
