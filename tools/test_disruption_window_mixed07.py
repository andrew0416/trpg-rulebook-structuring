"""Distinct native Bug-hit descendants preserve only their original trigger."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Rules, Engine
import action_points as AP
import combat_timing as TIME
import duelist as D
import juggler as J
import state_codec as CODEC
import state_fields as FIELDS
import trainer_feature_acquisition as ACQUIRE
import turn as TURN
import type_ace as TA
import world_entities as WORLD
import test_book_duelist_momentum as DUEL
import test_book_juggler_full as JUGGLE


class DisruptionMixedTests(unittest.TestCase):
    def bug_family(self, case, trainer, pokemon, partner):
        # Declare the same ordinary Type Link configuration as the existing
        # Type Ace fixture; permissions still come from real acquisitions.
        trainer.spec.setdefault('type_link_skills', {})['벌레'] = '명령'
        case.e.gm.set_skill(trainer, '명령', 6, reason='actual Master Bug Type Link')
        for actor in (pokemon, partner):
            case.e.gm.set_types(actor, ['벌레'], reason='actual two owned Bug partners')
        for feature in (TA.CLASS, TA.uid('Insectoid Utility'), TA.uid('Disruption Order')):
            ACQUIRE.acquire_static(case.e, trainer, feature,
                acquisition_request_id='mixed07/' + trainer.entity_id + '/' + feature,
                **({'branch': '벌레'} if feature == TA.CLASS else {}))
        # The Duelist fixture already knows six Moves. Explicitly forget its
        # unused Hyper Beam before learning the actual Bug trigger Move.
        if any(case.e.r.move_id(move) == 'move/파괴광선' for move in pokemon.moves):
            case.e.gm.set_move(pokemon, 'move/파괴광선', add=False,
                reason='explicitly selected unused Move to forget before learning Signal Beam')
            self.assertNotIn('move/파괴광선', [case.e.r.move_id(move) for move in pokemon.moves])
        case.e.gm.set_move(pokemon, 'move/시그널빔', reason='actual known ranged Bug Move')
        self.assertIs(TA.owner(case.e, pokemon, TA.uid('Disruption Order')), trainer)
        self.assertIs(case.e.rulings, case.e.r.rulings)

    def restore_duel(self, case):
        ids = {name: getattr(case, name).entity_id for name in ('a', 'p', 't')}
        case.e = CODEC.load_engine(case.rules, case.e.export_state())
        index = WORLD.actor_index(case.e)
        for name, identity in ids.items():
            setattr(case, name, index[identity])
        self.assertIs(case.e.rulings, case.e.r.rulings)

    def duel_child(self):
        case = DUEL.DuelistMomentumTests()
        case.rules = Rules(ROOT, ruleset='all')
        case.setup(ability=None)
        partner = case.extra_partner()
        self.bug_family(case, case.a, case.p, partner)
        FIELDS.base_patch(case.t, {'stats': dict(case.t.spec['stats'], hp=1000)},
                          reason='actual durable target for two native hits')
        case.e.gm.set_hp(case.t, value=case.t.max_hp, reason='actual healthy tagged target')
        case.rounds(6)
        self.assertEqual(D.momentum(case.p), 6)
        self.assertFalse(case.e.pending_duelist_interrupts(case.a))
        case.start(case.p)
        case.attack(move='move/시그널빔')
        root = next(row for row in reversed(list(case.e._move_completions.values()))
                    if row['actor'] is case.p and row['move_id'] == 'move/시그널빔')
        self.assertEqual(root['phase'], 'complete')
        pending = case.e.pending_duelist_interrupts(case.a)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]['origin'],
                         {'kind': 'tag_hit', 'completion': root['id'], 'target': case.t.entity_id})
        parent_budget = deepcopy(case.p.budget)
        trainer_history = list(getattr(case.a, '_action_history', []))
        case.e.enable_execution_trace()
        with patch.object(Engine, 'd20', return_value=10):
            case.e.seize_the_moment(case.a, case.p, event_id=pending[0]['id'],
                                   move='move/몸통박치기', target=case.t, set_damage=True)
        children = [row for row in case.e._move_completions.values()
                    if row.get('duelist_interrupt') == pending[0]['id']]
        self.assertEqual(len(children), 1)
        self.assertEqual(children[0]['phase'], 'complete')
        self.assertTrue(children[0]['results'][case.t.entity_id]['hit'])
        traces = [row for row in case.e.execution_traces() if row['producer'] == 'resolve_attack_damage']
        self.assertTrue(traces)
        self.assertTrue(traces[-1]['inputs']['crit'])
        self.assertEqual(case.a._action_history, trainer_history + ['free'])
        self.assertEqual(case.p.budget, parent_budget)
        self.assertEqual(case.p.move_uses['move/몸통박치기'], 1)
        self.assertFalse(case.e.pending_duelist_interrupts(case.a))
        self.assertIs(case.e._active_turn_actor, case.p)
        return case, root['id']

    def apply_once(self, case, trainer, pokemon, target, root_id):
        hp, uses = target.hp, deepcopy(pokemon.move_uses)
        self.assertTrue(TA.react(case.e, trainer, pokemon, TA.uid('Disruption Order'), root_id))
        self.assertEqual(target.hp, hp, 'Disruption must not replay either actual hit')
        self.assertEqual(pokemon.move_uses, uses)
        rows = [row for row in TIME.records(target) if row.get('ace_disruption')]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['accuracy_modifier'], -3)
        before = case.e.export_state()
        with self.assertRaises(ValueError):
            TA.react(case.e, trainer, pokemon, TA.uid('Disruption Order'), root_id)
        self.assertEqual(case.e.export_state(), before)
        case.valid()

    def reject_parent(self, case, trainer, pokemon, root_id):
        before = case.e.export_state()
        with self.assertRaises(ValueError):
            TA.react(case.e, trainer, pokemon, TA.uid('Disruption Order'), root_id)
        self.assertEqual(case.e.export_state(), before)

    def test_actual_bug_overflow_seize_child_preserves_parent_disruption_after_return_and_cold_restore(self):
        for cold in (False, True):
            with self.subTest(cold=cold):
                case, root_id = self.duel_child()
                if cold:
                    self.restore_duel(case)
                self.apply_once(case, case.a, case.p, case.t, root_id)

    def test_ordinary_free_after_actual_seize_child_closes_original_bug_hit(self):
        case, root_id = self.duel_child()
        self.assertTrue(TURN.spend(case.e, case.p, 'free', 'ordinary unrelated Free after Seize'))
        self.reject_parent(case, case.a, case.p, root_id)

    def juggler_hit(self, *, face=10):
        case = JUGGLE.JugglerTests()
        case.rules = Rules(ROOT, ruleset='core')
        case.setup()
        case.family(J.ROUND)
        self.bug_family(case, case.a, case.p, case.q)
        case.begin(case.p)
        with patch.object(Engine, 'd20', return_value=face):
            case.e.use_move(case.p, case.t, 'move/시그널빔', set_damage=True)
        root = next(row for row in reversed(list(case.e._move_completions.values()))
                    if row['actor'] is case.p and row['move_id'] == 'move/시그널빔')
        self.assertEqual(root['phase'], 'complete')
        self.assertEqual(bool(root['results'][case.t.entity_id]['hit']), face != 1)
        return case, root['id']

    def test_actual_round_trip_switch_preserves_owned_recalled_bug_hit_after_return_and_cold_restore(self):
        for cold in (False, True):
            with self.subTest(cold=cold):
                case, root_id = self.juggler_hit()
                before_ap = AP.available(case.a)
                before_uses = deepcopy(case.p.move_uses)
                receipt = case.action(J.ROUND, completion_id=root_id, request='mixed07-round-trip')
                self.assertEqual(AP.available(case.a), before_ap - 1)
                self.assertFalse(case.p.on_field)
                self.assertTrue(case.q.on_field)
                self.assertEqual(case.p.move_uses, before_uses)
                self.assertEqual(receipt['payment']['kind'], 'free')
                if cold:
                    case.restore()
                self.assertIs(case.e.rulings, case.e.r.rulings)
                self.apply_once(case, case.a, case.p, case.t, root_id)
                before = case.e.export_state()
                replay = case.action(J.ROUND, completion_id=root_id, request='mixed07-round-trip')
                self.assertEqual(replay, receipt)
                self.assertEqual(case.e.export_state(), before)

    def test_round_trip_does_not_create_hit_authority_and_unrelated_free_closes_real_hit(self):
        case, missed_id = self.juggler_hit(face=1)
        case.action(J.ROUND, completion_id=missed_id, request='mixed07-missed-round-trip')
        self.reject_parent(case, case.a, case.p, missed_id)
        case, hit_id = self.juggler_hit()
        self.assertTrue(TURN.spend(case.e, case.p, 'free', 'ordinary unrelated Free after Bug hit'))
        self.reject_parent(case, case.a, case.p, hit_id)
        before = case.e.export_state()
        with self.assertRaises(ValueError):
            case.action(J.ROUND, completion_id=hit_id, request='mixed07-stale-round-trip')
        self.assertEqual(case.e.export_state(), before)


if __name__ == '__main__':
    unittest.main()