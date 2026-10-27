"""Pure area cures reach a protected pouch body through native selectors."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules
import body_state as BODY
import area_targets as AREA
import marsupial_state as M
import test_core_marsupial as FIXTURE


class MarsupialHealingSelectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.r=Rules(ROOT,ruleset='core')

    setUp=FIXTURE.MarsupialTests.setUp
    policy=FIXTURE.MarsupialTests.policy
    egg=FIXTURE.MarsupialTests.egg
    hatch=FIXTURE.MarsupialTests.hatch
    born=FIXTURE.MarsupialTests.born
    valid=FIXTURE.MarsupialTests.valid

    def test_native_paid_area_cure_reaches_conscious_pouch_in_all_three_selectors(self):
        for selection in ('mapped_legacy','mapped_aim','mapless'):
            with self.subTest(selection=selection):
                self.setUp();baby=self.born();mid='move/치료방울'
                self.e.gm.observe_loyalty(self.mother,6,reason='actual willing maternal Heal Bell command')
                BODY.observe(self.e,self.mother,[(0,0),(1,0)],reason='actual observed maternal occupied cells')
                BODY.observe(self.e,baby,[(0,0)],reason='actual observed body inside maternal pouch')
                self.e.gm.set_move(self.mother,mid,True,reason='actual known Heal Bell area cure')
                self.e.apply_status(baby,'독',source='move/독가루',applied_by=self.enemy)
                self.assertIn('독',baby.conditions)
                birth=deepcopy(baby.spec[M.KEY]);custody=M.custody(self.e,baby)
                if selection=='mapless':
                    self.e.grid=None
                    self.e.gm.observe_mapless_scene(scene_id='pouch-cure-room',places={'room':'actual room'},
                        placements={c.entity_id:'room' for c in (self.a,self.mother,self.father,self.enemy)},
                        contacts=[],reason='observed people and actual maternal pouch custody')
                    self.e.gm.observe_mapless_targets(self.mother,event_id='pouch-cure',move_id=mid,
                        landmark_id='room',target_ids=[baby.entity_id],
                        reason='GM observes actual pouch baby inside Heal Bell area')
                self.e.start_round([self.a,self.mother,self.enemy])
                self.e.start_of_turn(self.mother,initiative_count=20)
                move=self.r.move(mid)
                if selection=='mapped_aim':move=AREA.bind(self.e,self.mother,move,self.mother.pos)
                self.assertTrue(M.protected_from_attacks(baby,engine=self.e))
                self.assertFalse(M.attack_blocked(self.mother,baby,move,engine=self.e))
                self.assertIn(baby,self.e.targets_in_range(self.mother,move,self.e.everyone,baby))
                self.e.use_move_on(self.mother,baby,mid,self.e.everyone,
                    aim=self.mother.pos if selection=='mapped_aim' else None)
                self.assertNotIn('독',baby.conditions)
                self.assertEqual(self.mother.budget['standard'],0)
                self.assertEqual(self.mother.move_uses[mid],1)
                self.assertEqual(baby.spec[M.KEY],birth);self.assertEqual(M.custody(self.e,baby),custody)
                self.assertTrue(M.protected_from_attacks(baby,engine=self.e))
                self.assertFalse(baby.on_field);self.valid()


if __name__=='__main__':unittest.main()
