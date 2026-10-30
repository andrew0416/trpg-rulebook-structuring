"""Authored source-only actual Intercept awareness continuation cases; not executed."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Engine, Rules, Combatant
import test_natural_fighter_class_routes as ROUTES
import book_survivalist_fixture as FIX
import natural_fighter as NF
import natural_fighter_moves as MOVES
import action_points as AP
import frequency as F
import state_grants as G
import passive_events as PASSIVE
import heavy_injury_adapter as HEAVY


class NaturalFighterAwarenessTests(unittest.TestCase):
    scene = ROUTES.NaturalFighterClassRouteTests.scene
    cast = ROUTES.NaturalFighterClassRouteTests.cast
    next_round = ROUTES.NaturalFighterClassRouteTests.next_round
    snap = ROUTES.NaturalFighterClassRouteTests.snap
    reject_unchanged = ROUTES.NaturalFighterClassRouteTests.reject_unchanged
    observe = ROUTES.NaturalFighterClassRouteTests.observe
    cave_target = ROUTES.NaturalFighterClassRouteTests.cave_target
    setUp = ROUTES.NaturalFighterClassRouteTests.setUp

    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(str(ROOT), ruleset='all')

    def setup_intercept(self, original=True, *, injuries=0, range_bonus=0):
        self.scene(terrain='cave')
        self.cave_target()
        self.e.rulings.answers = [r for r in self.e.rulings.answers
                                  if not str(r['key']).startswith(MOVES.QUOTA)]
        self.defender = Combatant(self.rules, FIX.trainer_spec(self.rules, 'actual defending trainer'))
        self.e.gm.add_combatant(self.defender, pos=(4, 3), side=self.foe.side,
                               reason='actual ally intercepting the declared attack')
        self.e.gm.set_types(self.defender, ['물'], reason='actual recipient without Ghost immunity')
        self.defender.injuries = injuries
        self.next_round()
        if range_bonus:
            G.apply_owned(self.e, self.actor, 'fixture:actual-effect-range',
                lambda: self.actor.modifiers.append({'type': 'effect_range_mod', 'value': range_bonus}))
        self.original_key = self.observe(original)
        self.e.watch_move_defense(self.foe,
            [{'actor_id': self.defender.entity_id, 'source': 'maneuver/근접-가로채기'}],
            reason='actual optional native Intercept')
        self.initial_ap = AP.available(self.t)
        self.initial_hp = self.defender.hp
        self.original_hp = self.foe.hp

    def first_wait(self, natural=14):
        with patch.object(Engine, 'd20', return_value=natural):
            with self.assertRaises(PASSIVE.PassiveEventPending):
                self.cast('cave', target=self.foe)
        self.parent = self.e._passive_pending
        self.identity = NF.current(self.actor)['id']
        self.completion_id = NF.current(self.actor)['completion_id']

    def choose(self):
        return self.e.choose_move_defense(self.parent, self.defender, use=True,
            options={'path': [(4, 3), (3, 3)], 'skill': '육상', 'mode': 'land',
                     'shove_destination': [3, 4], 'roll_options': {'fixed': [6] * 4}},
            reason='actual successful Intercept with completed paid movement')

    def wait(self, original=True, **options):
        self.setup_intercept(original, **options)
        self.first_wait()
        with self.assertRaises(PASSIVE.PassiveEventPending):self.choose()
        self.assertEqual(self.e._passive_pending, self.parent)
        self.assertEqual(self.e._passive_events[self.parent]['reason'], MOVES.AWARENESS_WAIT)
        self.assertEqual(self.defender.hp, self.initial_hp)
        self.assertEqual(self.foe.hp, self.original_hp)
        self.assertEqual(tuple(self.defender.pos), (3, 3))
        self.assertEqual(tuple(self.foe.pos), (3, 4))
        self.assertEqual(AP.available(self.t), self.initial_ap - 1)
        self.assertEqual(self.actor.move_uses[MOVES.ASTONISH], 1)
        self.assertEqual(self.actor.budget['standard'], 0)
        self.assertIsNone(self.record()['answer'])
        self.assertNotEqual(self.record()['facts']['observation_key'], self.original_key)
        self.assertEqual(self.record()['facts']['original']['next_use'], 1)
        return self.costs()

    def record(self):
        return self.e._move_completions[self.completion_id][MOVES.AWARENESS][self.parent][self.defender.entity_id]

    def costs(self):
        return deepcopy((AP.available(self.t), self.actor.budget, self.actor.move_uses,
                         self.actor._action_history, self.defender.budget, self.defender.move_uses,
                         self.defender._action_history, self.defender.pos, self.foe.pos))

    def restore(self):
        self.e, index = FIX.restore(self.rules, self.e)
        self.t, self.p, self.foe, self.actor, self.defender = [index[a.entity_id] for a in
            (self.t, self.p, self.foe, self.actor, self.defender)]
        self.assertIs(self.record(), self.e._passive_events[self.parent][MOVES.AWARENESS][self.defender.entity_id])

    def answer(self, unaware):
        key = self.record()['facts']['observation_key']
        FIX.ruling(self.e, key, {'observation_key': key, 'unaware': unaware},
                   reason='GM observed this actual recipient before the same attack')

    def test_actual_recipient_answer_controls_flinch_and_restore_resume_pays_once(self):
        for original, actual in ((True, False), (False, True)):
            with self.subTest(original=original, actual=actual):
                paid = self.wait(original)
                self.restore()
                self.answer(actual)
                with patch.object(Engine, 'd20', side_effect=AssertionError('must not reroll accuracy')):
                    self.e.deliver_passive_event(self.parent)
                self.assertEqual(self.costs(), paid)
                self.assertLess(self.defender.hp, self.initial_hp)
                self.assertEqual(self.foe.hp, self.original_hp)
                self.assertEqual('풀죽음' in self.defender.conditions, actual)
                self.assertEqual(F.activation_allowed(self.actor, MOVES.QUOTA, MOVES.ONCE, engine=self.e), not actual)
                self.assertEqual(self.e._move_completions[self.completion_id]['phase'], 'complete')
                self.assertIsNone(NF.current(self.actor))
                self.assertNotIn(self.identity, self.actor.spec[G.KEY]['sources'])
                self.restore()
                finished = self.snap()
                self.e.deliver_passive_event(self.parent)
                self.assertEqual(self.snap(), finished)

    def test_missing_answer_repeats_same_wait_without_children_damage_or_repayment(self):
        paid = self.wait()
        self.restore()
        before = deepcopy(self.record())
        for _ in range(2):
            with self.assertRaises(PASSIVE.PassiveEventPending):
                self.e.deliver_passive_event(self.parent)
            self.assertEqual(self.e._passive_pending, self.parent)
            self.assertEqual(self.record(), before)
            self.assertEqual(self.costs(), paid)
            self.assertEqual(self.defender.hp, self.initial_hp)
            state = self.e._move_completions[self.completion_id]['defense'][self.foe.entity_id]
            self.assertEqual(state['children'], {})
            self.assertEqual(state['total'], 0)
        self.answer(True)
        self.e.deliver_passive_event(self.parent)
        self.assertEqual(self.costs(), paid)

    def test_foreign_stale_untyped_and_extra_field_answers_reject_atomically(self):
        for kind in ('original', 'foreign', 'stale', 'untyped', 'non_boolean', 'extra'):
            with self.subTest(kind=kind):
                paid = self.wait()
                self.restore()
                key = self.record()['facts']['observation_key']
                bad = {'observation_key': key, 'unaware': True}
                if kind == 'original':bad['observation_key'] = self.original_key
                elif kind == 'foreign':bad['observation_key'] = key + ':another-recipient'
                elif kind == 'stale':bad['observation_key'] = key + ':previous-use'
                elif kind == 'untyped':bad = True
                elif kind == 'non_boolean':bad['unaware'] = 1
                else:bad['allow'] = True
                FIX.ruling(self.e, key, bad)
                self.reject_unchanged('typed current actual-recipient',
                                      lambda: self.e.deliver_passive_event(self.parent))
                self.assertEqual(self.costs(), paid)
                self.assertEqual(self.defender.hp, self.initial_hp)
                self.answer(True)
                self.e.deliver_passive_event(self.parent)

    def test_attacker_faint_cancels_only_unstarted_recipient_and_retains_paid_prefix(self):
        paid = self.wait()
        self.restore()
        self.e.gm.set_hp(self.actor, 0, reason='actual knockout while waiting for recipient awareness')
        self.e.deliver_passive_event(self.parent)
        self.assertEqual(self.costs(), paid)
        self.assertEqual(self.defender.hp, self.initial_hp)
        self.assertNotIn('풀죽음', self.defender.conditions)
        self.assertTrue(F.activation_allowed(self.actor, MOVES.QUOTA, MOVES.ONCE, engine=self.e))
        self.assertTrue(self.record()['cancelled'])
        self.assertEqual(self.actor.spec[NF.KEY][self.identity]['phase'], 'cancelled')
        self.assertNotIn(self.identity, self.actor.spec[G.KEY]['sources'])
        self.assertIsNone(NF.current(self.actor))
        self.restore()

    def test_source_receipt_loss_and_recipient_tampering_reject_restore(self):
        for kind in ('completion_map', 'parent_alias', 'both_maps', 'recipient', 'answer', 'route'):
            with self.subTest(kind=kind):
                self.wait()
                row = self.e._move_completions[self.completion_id]
                event = self.e._passive_events[self.parent]
                if kind == 'completion_map':row.pop(MOVES.AWARENESS)
                elif kind == 'parent_alias':event.pop(MOVES.AWARENESS)
                elif kind == 'both_maps':
                    row.pop(MOVES.AWARENESS)
                    event.pop(MOVES.AWARENESS)
                elif kind == 'recipient':self.record()['facts']['recipient_id'] = self.foe.entity_id
                elif kind == 'answer':
                    self.record()['answer'] = {'observation_key': self.record()['facts']['observation_key'], 'unaware': True}
                else:row['defense'][self.foe.entity_id]['recipients'][0]['actor_id'] = self.foe.entity_id
                with self.assertRaises(ValueError):FIX.restore(self.rules, self.e)

    def test_resealed_foreign_recipient_still_requires_actual_native_route(self):
        self.wait()
        record = self.record()
        record['facts']['recipient_id'] = self.foe.entity_id
        record['fingerprint'] = MOVES._awareness_proof(record)
        with self.assertRaisesRegex(ValueError, 'receipt changed'):
            FIX.restore(self.rules, self.e)

    def test_answered_resume_can_hit_heavy_without_repaying_or_replaying_damage(self):
        paid = self.wait(False, injuries=5)
        self.restore()
        self.answer(True)
        with self.assertRaises(HEAVY.HeavyPending):self.e.deliver_passive_event(self.parent)
        heavy_id = self.e._heavy_pending
        self.assertIsNotNone(heavy_id)
        self.assertEqual(self.costs(), paid)
        self.assertLess(self.defender.hp, self.initial_hp)
        self.assertTrue(self.record()['answer']['unaware'])
        self.assertFalse(self.e._heavy_events[heavy_id]['continuation_reified'])
        self.assertTrue(F.activation_allowed(self.actor, MOVES.QUOTA, MOVES.ONCE, engine=self.e))
        self.restore()
        damage_hp = self.defender.hp
        with self.assertRaises(HEAVY.HeavyPending):self.e.deliver_passive_event(self.parent)
        self.assertEqual(self.defender.hp, damage_hp)
        self.assertEqual(self.costs(), paid)
        packet = self.e._heavy_events[heavy_id]
        HEAVY.acknowledge_ruling(self.e, heavy_id, packet['target'],
            expected_current_state=HEAVY.observe(packet['target']),
            ruling='GM adjudicates the actual redirected Heavy hit without replay',
            disposition=HEAVY.ContinuationDisposition.CANCELLED_BY_RULING,
            continuation_reason='native caller suffix remains unavailable and is abandoned')
        result = self.e.survivalist_activity(self.t, 'natural_fighter_finish_heavy', subject=self.actor)
        self.assertFalse(result['native_resume'])
        self.assertEqual(self.costs(), paid)
        self.assertEqual(self.defender.hp, damage_hp)
        self.assertNotIn(self.identity, self.actor.spec[G.KEY]['sources'])
        self.restore()

    def test_native_high_roll_and_modified_effect_range_need_no_redirect_answer(self):
        for natural, bonus in ((18, 0), (14, 1)):
            with self.subTest(natural=natural, bonus=bonus):
                self.setup_intercept(False, range_bonus=bonus)
                self.first_wait(natural)
                self.choose()
                row = self.e._move_completions[self.completion_id]
                self.assertNotIn(MOVES.AWARENESS, row)
                self.assertIn('풀죽음', self.defender.conditions)
                self.assertTrue(F.activation_allowed(self.actor, MOVES.QUOTA, MOVES.ONCE, engine=self.e))
                self.assertEqual(AP.available(self.t), self.initial_ap - 1)
                self.assertIsNone(NF.current(self.actor))
                FIX.restore(self.rules, self.e)

    def test_native_miss_needs_no_redirect_answer_or_unaware_quota(self):
        self.setup_intercept(True)
        with patch.object(Engine, 'd20', return_value=1):
            result = self.cast('cave', target=self.foe)
        self.assertNotIn(MOVES.AWARENESS, self.e._move_completions[result['completion_id']])
        self.assertEqual(self.defender.hp, self.initial_hp)
        self.assertEqual(self.foe.hp, self.original_hp)
        self.assertNotIn('풀죽음', self.defender.conditions)
        self.assertTrue(F.activation_allowed(self.actor, MOVES.QUOTA, MOVES.ONCE, engine=self.e))
        self.assertEqual(AP.available(self.t), self.initial_ap - 1)
        self.assertIsNone(NF.current(self.actor))


    def test_ordinary_learned_astonish_uses_same_redirect_receipt_without_class_ap(self):
        self.setup_intercept(False)
        self.e.gm.set_move(self.actor, MOVES.ASTONISH, reason='actual ordinary learned Astonish')
        with patch.object(Engine, 'd20', return_value=14):
            with self.assertRaises(PASSIVE.PassiveEventPending):
                self.e.use_move_on(self.actor, self.foe, MOVES.ASTONISH, self.e.everyone, set_damage=True)
        self.parent = self.e._passive_pending
        self.completion_id = self.e._passive_events[self.parent]['completion_id']
        with self.assertRaises(PASSIVE.PassiveEventPending):self.choose()
        self.assertIsNone(NF.current(self.actor))
        self.assertEqual(AP.available(self.t), self.initial_ap)
        paid = self.costs()
        self.restore()
        self.answer(True)
        self.e.deliver_passive_event(self.parent)
        self.assertEqual(self.costs(), paid)
        self.assertIn(MOVES.ASTONISH, self.actor.moves)
        self.assertIn('풀죽음', self.defender.conditions)
        self.assertLess(self.defender.hp, self.initial_hp)
        self.restore()

    def test_other_resolving_reason_does_not_gain_awareness_cancellation_permission(self):
        self.wait()
        self.e.gm.set_hp(self.actor, 0, reason='actual knockout during adversarial cancellation check')
        event = self.e._passive_events[self.parent]
        event['reason'] = 'recipient_effects_unresolved'
        import move_defense_reactions as DEFENSE
        before = self.snap()
        self.assertFalse(DEFENSE.cancel_waiting(self.e, event))
        self.assertEqual(self.snap(), before)
        event['reason'] = MOVES.AWARENESS_WAIT
        self.e.deliver_passive_event(self.parent)
        self.assertTrue(self.record()['cancelled'])

if __name__ == '__main__':
    unittest.main()