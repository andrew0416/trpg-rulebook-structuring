"""Bounded old-save provenance contracts, preserving real already-paid effects.

Projection removes only fields introduced by the Disruption window packet.
It does not fabricate a completion, action, source, participant or paid receipt.
"""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Engine, Rules
import action_points as AP
import class_actor_state_reactions as REACTIONS
import duelist as D
import move_completion as MC
import state_codec as CODEC
import state_fields as FIELDS
import type_ace as TA
import world_entities as WORLD
import test_book_duelist_momentum as DUEL
import test_disruption_window_core01 as CORE
import test_disruption_window_mixed07 as MIXED7
import test_disruption_window_mixed08 as MIXED8


class LegacyDisruptionTests(unittest.TestCase):
    def projection(self, saved, *, old_bloom=False):
        saved = CORE.DisruptionWindowCoreTests.legacy_projection(self, saved)
        if old_bloom:
            for node in saved['nodes'].values():
                if node['kind'] != 'dict':
                    continue
                if ['source', REACTIONS.ENDURING_BLOOM] in node['items'] and any(
                        pair[0] == 'damage_receipt' for pair in node['items']):
                    self.assertTrue({'native_event_id','completion_id','native_origin_version'}.isdisjoint(
                        pair[0] for pair in node['items'] if isinstance(pair[0],str)),
                        'legacy fixture must come from actual former admission, not stripped modern proof')
        return saved

    def restore_old(self, case, *, old_bloom=False):
        saved = self.projection(case.e.export_state(), old_bloom=old_bloom)
        untouched = deepcopy(saved)
        identities = {name: value.entity_id for name, value in vars(case).items()
                      if hasattr(value, 'entity_id')}
        case.e = CODEC.load_engine(case.rules, saved)
        index = WORLD.actor_index(case.e)
        for name, identity in identities.items():
            setattr(case, name, index[identity])
        self.assertEqual(saved, untouched, 'old save input must remain read-only')
        before = case.e.export_state()
        case.valid()
        self.assertEqual(case.e.export_state(), before, 'validation must not invent provenance')
        self.assertFalse(any('disruption_window' in row for row in case.e._move_completions.values()))
        self.assertTrue(all(MC.DISRUPTION_WINDOWS not in actor.custom_conditions for actor in index.values()))

    def duel_hit(self):
        helper = MIXED7.DisruptionMixedTests()
        case = DUEL.DuelistMomentumTests()
        case.rules = Rules(ROOT, ruleset='all')
        case.setup(ability=None)
        helper.bug_family(case, case.a, case.p, case.extra_partner())
        FIELDS.base_patch(case.t, {'stats': dict(case.t.spec['stats'], hp=1000)},
                          reason='durable actual target for original and Seize hit')
        case.e.gm.set_hp(case.t, value=case.t.max_hp, reason='actual healthy tagged target')
        case.rounds(6)
        self.assertEqual(D.momentum(case.p), 6)
        case.start(case.p)
        case.attack(move='move/시그널빔')
        parent = next(row for row in reversed(list(case.e._move_completions.values()))
                      if row['actor'] is case.p and row['move_id'] == 'move/시그널빔')
        pending = case.e.pending_duelist_interrupts(case.a)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]['origin'],
                         {'kind': 'tag_hit', 'completion': parent['id'], 'target': case.t.entity_id})
        return helper, case, parent['id'], pending[0]['id']

    def seize(self, case, identity):
        with patch.object(Engine, 'd20', return_value=10):
            case.e.seize_the_moment(case.a, case.p, event_id=identity,
                                   move='move/몸통박치기', target=case.t, set_damage=True)
        children = [row for row in case.e._move_completions.values()
                    if row.get('duelist_interrupt') == identity]
        self.assertEqual(len(children), 1)
        self.assertEqual(children[0]['phase'], 'complete')
        return children[0]['id']

    def paid_duel_state(self, case):
        return (case.p.hp, case.t.hp, deepcopy(case.p.move_uses), deepcopy(case.p.budget),
                list(case.p._action_history), list(case.a._action_history),
                AP.available(case.a), deepcopy(case.a.spec.get('frequency_state')),
                deepcopy(case.p.spec.get('frequency_state')))

    def bloom(self):
        case = MIXED8.DisruptionMixedReactionTests()
        case.setUp()
        case.grass_defender()
        # The former passive producer did not admit class-reaction interest.
        # Run the actual hit with only that new admission disabled, rather than
        # deleting modern sealed evidence or manufacturing a replacement ID.
        case.combat(case.p)
        with patch.object(REACTIONS,'interested',return_value=False):
            case.native(case.p,case.v,'move/시그널빔',face=18)
        parent=case.completed(case.p,'move/시그널빔')['id']
        offer=case.bloom_offer()
        for field in ('native_event_id','completion_id','native_origin_version'):
            self.assertNotIn(field,offer)
        self.assertFalse(any(offer['id'] in native.get('class_actor_reaction_offers',{})
                             for native in case.e._passive_events.values()))
        return case, parent, offer['id']

    def bloom_state(self, case):
        return (case.p.hp, case.v.hp, case.v.temp_hp, dict(case.v.stages),
                list(case.p._action_history), list(getattr(case.u, '_action_history', [])),
                deepcopy(case.p.move_uses), deepcopy(case.u.spec.get('frequency_state')))

    def reject_unproved(self, case, parent):
        before = case.e.export_state()
        with self.assertRaisesRegex(ValueError, 'current native hit trigger window'):
            TA.react(case.e, case.t, case.p, TA.uid('Disruption Order'), parent)
        self.assertEqual(case.e.export_state(), before)
        case.valid()

    def test_old_duelist_current_hit_before_payment_loads_read_only_then_new_seize_preserves_parent(self):
        helper, case, parent, pending = self.duel_hit()
        before = self.paid_duel_state(case)
        self.restore_old(case)
        self.assertEqual(self.paid_duel_state(case), before)
        self.assertEqual(case.e._trickster_trigger, parent)
        self.seize(case, pending)
        self.assertFalse(case.e.pending_duelist_interrupts(case.a))
        helper.apply_once(case, case.a, case.p, case.t, parent)

    def test_old_paid_duelist_preserves_proven_ancestry_and_payment_but_not_unknown_parent_freshness(self):
        helper, case, parent, pending = self.duel_hit()
        child = self.seize(case, pending)
        before = self.paid_duel_state(case)
        self.restore_old(case)
        self.assertEqual(self.paid_duel_state(case), before)
        pokemon, gain = D.overflow_trigger(case.e, pending, allow_completed=True)
        self.assertIs(pokemon, case.p)
        self.assertEqual(gain['origin']['completion'], parent)
        self.assertEqual(gain['status'], 'completed')
        self.assertEqual(case.e._move_completions[child]['duelist_interrupt'], pending)
        requests = [request for window in case.e._initiative_interrupts['windows'].values()
                    for request in window['requests'] if request['id'] == pending]
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0]['receipt']['move_completion'], child)
        self.assertEqual(requests[0]['receipt']['actions'], ['standard'])
        self.assertEqual(case.e._trickster_trigger, child)
        # The old receipt proves child ancestry, but never recorded whether
        # another actor acted between parent completion and Seize admission.
        state = case.e.export_state()
        with self.assertRaisesRegex(ValueError, 'current native hit trigger window'):
            TA.react(case.e, case.a, case.p, TA.uid('Disruption Order'), parent)
        self.assertEqual(case.e.export_state(), state)
        self.assertEqual(self.paid_duel_state(case), before)
        case.valid()

    def test_old_pending_bloom_decline_keeps_current_parent_without_fabricating_a_native_pair(self):
        case, parent, identity = self.bloom()
        self.restore_old(case, old_bloom=True)
        offer = case.bloom_offer()
        self.assertNotIn('native_event_id', offer)
        self.assertNotIn('completion_id', offer)
        history = list(getattr(case.u, '_action_history', []))
        self.assertFalse(case.e.resolve_class_actor_state_reaction(case.u, identity, use=False)['used'])
        self.assertEqual(list(getattr(case.u, '_action_history', [])), history)
        self.assertEqual(case.e._trickster_trigger, parent)
        case.use_disruption(parent, case.v)
        case.valid()

    def test_old_pending_bloom_accept_pays_real_feature_without_inventing_unrecorded_parent_link(self):
        case, parent, identity = self.bloom()
        self.restore_old(case, old_bloom=True)
        history = list(getattr(case.u, '_action_history', []))
        self.assertTrue(case.e.resolve_class_actor_state_reaction(case.u, identity, use=True, stats=('def',))['used'])
        self.assertEqual(case.u._action_history, history + ['free'])
        self.assertEqual(case.v.temp_hp, 12)
        self.assertEqual(case.v.stages['def'], 1)
        paid = self.bloom_state(case)
        self.reject_unproved(case, parent)
        self.assertEqual(self.bloom_state(case), paid)

    def test_old_completed_bloom_preserves_paid_effects_on_load_but_lacks_native_pair_for_reopening(self):
        case, parent, identity = self.bloom()
        self.assertTrue(case.e.resolve_class_actor_state_reaction(case.u, identity, use=True, stats=('def',))['used'])
        paid = self.bloom_state(case)
        self.restore_old(case, old_bloom=True)
        self.assertEqual(self.bloom_state(case), paid)
        rows = [row for row in REACTIONS._state(case.u)['events'] if row['id'] == identity]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['status'], 'completed')
        self.assertTrue(rows[0]['result']['used'])
        self.assertNotIn('native_event_id', rows[0])
        self.assertNotIn('completion_id', rows[0])
        self.assertIsNone(case.e._trickster_trigger)
        self.reject_unproved(case, parent)
        self.assertEqual(self.bloom_state(case), paid)


if __name__ == '__main__':
    unittest.main()