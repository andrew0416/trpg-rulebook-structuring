"""Actual Drown Out caller impact of CONTROL's mandatory trigger owner."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Rules
from native_scenario_fixture import assert_rejected_unchanged
import ability_control_contracts as CONTROL
import frequency as F
import musician as M
import native_area_hit_effects as AREA_HIT
import test_book_musician_full as MUSIC


class ControlMusicianImpactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(ROOT, ruleset='core')

    def test_actual_sonic_drown_out_respects_dazzling_owner_before_cost_and_allows_decline(self):
        for same_attacker, accept, direct in ((True, True, False), (False, True, False), (True, False, False),
                                            (True, True, True), (False, True, True), (True, False, True)):
            with self.subTest(same_attacker=same_attacker, accept=accept, direct=direct):
                scene = MUSIC.MusicianTests()
                scene.rules = self.rules
                scene.setUp()
                try:
                    scene.musician(ability='소리묻히기')
                    e, recipient = scene.e, scene.t
                    dazzling_user = scene.foe(pos=(4, 3))
                    other = scene.add('Other Sonic attacker', 'trainer', (3, 5), side='enemy')
                    e.gm.set_ability(dazzling_user, '비비드바디', reason='actual Dazzling source owner')
                    # A direct caller needs a single-target Sonic Move, not an omitted area producer.
                    move = 'move/수다' if direct else 'move/하이퍼보이스'
                    for actor in (dazzling_user, other):
                        e.gm.set_move(actor, move, reason='actual complete known Sonic Move')
                        if direct:
                            e.gm.set_move(actor, 'move/하이퍼보이스', reason='actual rejected direct area Move')
                    scene.combat(recipient, count=40)
                    e.end_of_turn(recipient)
                    e.start_of_turn(dazzling_user, initiative_count=30)
                    e.activate_ability(dazzling_user, CONTROL.DAZZLING, recipient)
                    self.assertEqual(recipient.initiative_bonus, -10)
                    attacker = dazzling_user
                    if not same_attacker:
                        e.end_of_turn(dazzling_user)
                        e.start_of_turn(other, initiative_count=20)
                        attacker = other
                    self.assertTrue(M.sonic(attacker, e.r.move(move)))
                    if direct:
                        self.assertFalse(AREA_HIT.manages(e, move))
                        self.assertEqual(e.r.moves_mech[move]['header']['range']['targets'], 1)
                        self.assertIsNotNone(e.r.move(move)['ac'])
                        self.assertGreater(e.r.move(move)['damage_base'], 0)
                        assert_rejected_unchanged(e,
                            lambda: e.use_move(attacker, recipient, 'move/하이퍼보이스', aim=(3, 3)),
                            reason_pattern='complete native target activation')
                    e.rulings.add_answer('drown_out', accept, reason='actual player reaction choice')
                    self.assertTrue(F.activation_allowed(recipient, M.DROWN, '장면', engine=e))
                    history = list(recipient._action_history)
                    frequency = deepcopy(recipient.spec['frequency_state'])
                    hp = recipient.hp

                    def sonic_action():
                        if direct:
                            with patch.object(type(e), 'd20', return_value=2 if accept else 20):
                                return e.use_move(attacker, recipient, move)
                        return scene.use(attacker, recipient, move, face=2 if accept else 20, aim=(3, 3))

                    if same_attacker and accept:
                        assert_rejected_unchanged(e, sonic_action, reason_pattern='Dazzling prohibits this interrupt')
                        self.assertEqual(recipient._action_history, history)
                        self.assertEqual(recipient.spec['frequency_state'], frequency)
                        self.assertTrue(F.activation_allowed(recipient, M.DROWN, '장면', engine=e))
                    else:
                        sonic_action()
                        completions = [row for row in e._move_completions.values()
                                       if row['actor'] is attacker and row['move_id'] == move]
                        self.assertEqual(len(completions), 1)
                        completed = completions[0]
                        self.assertEqual(completed['phase'], 'complete')
                        reaction = completed['drown_out']
                        if accept:
                            self.assertEqual(recipient._action_history, history + ['free'])
                            self.assertFalse(F.activation_allowed(recipient, M.DROWN, '장면', engine=e))
                            self.assertEqual(len(reaction['attempts']), 1)
                            self.assertEqual(reaction['attempts'][0]['owner_id'], recipient.entity_id)
                            self.assertEqual(reaction['attempts'][0]['source'], M.DROWN)
                            self.assertTrue(reaction['cancelled'])
                            self.assertEqual(recipient.hp, hp)
                        else:
                            self.assertEqual(recipient._action_history, history)
                            self.assertEqual(recipient.spec['frequency_state'], frequency)
                            self.assertTrue(F.activation_allowed(recipient, M.DROWN, '장면', engine=e))
                            self.assertEqual(reaction['attempts'], [])
                            self.assertFalse(reaction['cancelled'])
                            self.assertEqual(attacker.last_move, move)
                            self.assertLess(recipient.hp, hp)
                    scene.valid()
                finally:
                    scene.doCleanups()


if __name__ == '__main__':
    unittest.main()
