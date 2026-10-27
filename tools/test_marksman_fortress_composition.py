"""Coupled source-composition regressions; remote execution still required."""
from collections import UserDict
from unittest.mock import patch
import unittest

import test_book_marksman_full as MARKSMAN_FIXTURE
import test_native_return_continuation as RETURNS
import marksman as M
import fortress as FORTRESS
import acquired_features as ACQUIRED
import trainer_feature_acquisition as ACQUIRE
import state_grants as GRANTS
import optional_state_effect_contracts as OPTIONAL
import frequency as FREQUENCY
import move_completion as COMPLETE
import passive_events as EVENTS
from engine import Engine
from native_scenario_fixture import assert_rejected_unchanged


class MarksmanFortressCompositionTests(unittest.TestCase):
    setUpClass = classmethod(MARKSMAN_FIXTURE.MarksmanFullTests.setUpClass.__func__)
    scene = MARKSMAN_FIXTURE.MarksmanFullTests.scene
    acquire = MARKSMAN_FIXTURE.MarksmanFullTests.acquire
    weapon = MARKSMAN_FIXTURE.MarksmanFullTests.weapon
    combat = MARKSMAN_FIXTURE.MarksmanFullTests.combat
    restore = MARKSMAN_FIXTURE.MarksmanFullTests.restore

    def fortress(self, feature):
        if feature != FORTRESS.CLASS and FORTRESS.acquired(self.a) is None:
            self.fortress(FORTRESS.CLASS)
        return ACQUIRE.acquire_static(self.e, self.a, feature,
            acquisition_request_id='composition/fortress/' + feature,
            selection={'edition': 'supplement'})

    def valid(self):
        state = self.e.validate_state()
        self.assertTrue(state['valid'], state['issues'])

    def test_both_class_routes_survive_fast_fallback_cold_restore_and_one_source_withdrawal(self):
        self.scene(features=(M.CLASS,))
        initial_def = self.a.stats['def']
        self.fortress(FORTRESS.CLASS)
        classes = (ACQUIRED.RUNE_CLASS, ACQUIRED.BERSERKER_CLASS,
                   ACQUIRED.ARCANIST_CLASS, M.CLASS, FORTRESS.CLASS)
        for units in (self.rules.selection.units, UserDict(self.rules.selection.units)):
            with patch.object(self.rules.selection, 'units', units):
                for uid in classes:
                    self.assertEqual(ACQUIRED._names(self.a, 'class/')[uid], [uid])
                    self.assertNotIn(uid, ACQUIRED._names(self.a, 'supp-fantasy/'))
                self.assertEqual((ACQUIRED.owned_rule_count(self.a, M.CLASS),
                                  ACQUIRED.owned_rule_count(self.a, FORTRESS.CLASS)), (1, 1))
                self.assertEqual({r['source_id'] for r in ACQUIRED.class_instances(self.a)},
                                 {M.CLASS, FORTRESS.CLASS})
        self.restore()
        source = next(sid for sid, row in GRANTS.state(self.a)['sources'].items()
                      if row.get('static_acquisition', {}).get('feature_id') == M.CLASS)
        def withdraw(engine, actor):
            GRANTS.revoke(actor, source, engine=engine)
            actor.spec['feats'].remove(M.CLASS)
        GRANTS.transition(self.e, self.a, withdraw)
        self.assertEqual((self.a.stats['atk'], self.a.stats['def']),
                         (self.initial_atk, initial_def + 1))
        self.assertEqual((ACQUIRED.owned_rule_count(self.a, M.CLASS),
                          ACQUIRED.owned_rule_count(self.a, FORTRESS.CLASS)), (0, 1))
        self.assertEqual(self.acquire(M.CLASS)['status'], 'withdrawn')
        self.assertNotIn(M.CORE_SNIPER_NAME, self.a.abilities)
        self.restore()
        self.assertEqual([r['source_id'] for r in ACQUIRED.class_instances(self.a)], [FORTRESS.CLASS])
        self.valid()

    def test_guardian_and_armed_clear_share_real_swift_cost_then_preserve_both_pending_scopes(self):
        self.scene(features=(M.AIM, M.CLEAR))
        self.fortress(FORTRESS.GUARDIAN)
        self.weapon()
        self.combat()
        with patch.object(Engine, 'd20', return_value=1):
            self.e.use_move_on(self.a, self.b, self.mid, self.e.everyone, weapon_id=self.key)
        completion = list(self.e._move_completions)[-1]
        self.e.gm.set_position(self.a, (6, 4), reason='actual owner ends adjacent to its native attack target')
        self.e.end_of_turn(self.a, fortress_mark=completion)
        self.e.end_round()
        self.e.start_round(self.e.everyone)
        self.e.start_of_turn(self.a, initiative_count=20)
        self.e.gm.set_position(self.a, (2, 4), reason='actual clear ranged firing position this turn')
        M.aim(self.e, self.a)
        M.arm_clear(self.e, self.a, self.mid, self.key)
        def attack():
            return self.e.guardian_weapon_attack(self.a, self.b, self.mid,
                                                weapon_id=self.key, skill='집중')
        # Clear and Guardian each need the same single real Swift; no free budget.
        with patch.object(Engine, 'd20', return_value=18):
            assert_rejected_unchanged(self.e, attack, reason_pattern='[Ss]wift')
        self.assertTrue(OPTIONAL.records(self.a, M.AIM))
        self.assertNotIn(M.CLEAR, FREQUENCY.state(self.a)['activations'])
        self.assertNotIn(FORTRESS.GUARDIAN, FREQUENCY.state(self.a)['activations'])
        self.assertEqual(self.a.budget['swift'], 1)
        # A different armed Move still enters Marksman's atomic native wrapper.
        M.arm_clear(self.e, self.a, 'move/불스아이', self.key)
        policy = RETURNS.NativeReturnContinuationTests.policy(self, 'guardian-marksman-composed')
        before_use = self.a.move_uses[self.mid]
        with patch.object(Engine, 'd20', return_value=18), self.assertRaises(EVENTS.PassiveEventPending):
            attack()
        event = self.e._passive_pending
        token = list(self.e._move_completions)[-1]
        self.assertTrue(self.a.custom_conditions['fortress_guardian_attack']['paid'])
        self.assertEqual(self.e._marksman_attack['completion_id'], token)
        self.assertEqual((self.a.budget['swift'], self.a.move_uses[self.mid]), (0, before_use + 1))
        self.assertFalse(OPTIONAL.records(self.a, M.AIM))
        self.assertEqual(FREQUENCY.state(self.a)['activations'][FORTRESS.GUARDIAN]['used'], 1)
        self.valid()
        self.restore()
        hp, rng = self.b.hp, self.e.rng.getstate()
        with patch.object(Engine, 'd20', side_effect=AssertionError('native paid accuracy cannot reroll')):
            RETURNS.NativeReturnContinuationTests.choose(self, event, policy)
        row = self.e._move_completions[token]
        self.assertEqual(row['phase'], 'complete')
        self.assertEqual((self.b.hp, self.e.rng.getstate()), (hp, rng))
        self.assertNotIn('fortress_guardian_attack', self.a.custom_conditions)
        self.assertIsNone(getattr(self.e, '_marksman_attack', None))
        self.assertIn(M.ARM, self.a.spec)
        self.assertEqual(self.a.move_uses[self.mid], before_use + 1)
        self.assertEqual(FREQUENCY.state(self.a)['activations'][FORTRESS.GUARDIAN]['used'], 1)
        COMPLETE.require_returned_event(self.e, event)
        self.restore()
        self.valid()
