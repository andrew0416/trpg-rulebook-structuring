"""Actual generic consumers of the remaining three named Mindlock exceptions."""
from copy import copy, deepcopy
from pathlib import Path
from unittest.mock import patch
import unittest

import test_category2_body_modes as fixture
from engine import Rules
import mindlock as M
import state_grants as G
import state_codec as CODEC
import common_checks as C
import effect_contracts as CONTRACTS

ROOT = Path(__file__).resolve().parents[1]


class CoreMindlockTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = Rules(str(ROOT), ruleset='core')

    add = fixture.Tests.add
    pokemon = fixture.Tests.pokemon
    restored = fixture.Tests.restored
    begin = fixture.Tests.begin
    known = fixture.Tests.known
    setUp = fixture.Tests.setUp

    def mindlock(self, actor):
        G.grant(actor, 'capabilities', 'Mindlock', 'fixture:mindlock', 'fixture')

    def warning_owner(self):
        self.a.spec['feats'] = [M.WARNING]
        G.grant(self.a, 'capabilities', 'Telepathy', 'fixture:telepathy', 'fixture')

    def resources(self, actor):
        return deepcopy((actor.spec.get('ap_spent'), actor.spec.get('ap_removed'),
                         getattr(actor, 'budget', None),
                         list(getattr(actor, '_action_history', [])), actor.move_uses))

    def attack(self, attacker=None):
        attacker = self.p if attacker is None else attacker
        attacker.pos = (6, 3)
        self.t.pos = (7, 3)
        self.begin(attacker)
        self.e.use_move(attacker, self.t, 'struggle', set_damage=True)
        return next(reversed(self.e._passive_events))

    def test_mind_reader_native_miss_and_live_loss_preserve_positive_route(self):
        self.known(self.a, '마음의눈')
        self.a.pos = (3, 3)
        self.mindlock(self.t)
        self.begin(self.a)
        before = deepcopy((self.t.conditions, self.t.stages, self.t.registry))
        rng = self.e.rng.getstate()
        self.e.use_move(self.a, self.t, M.MIND_READER)
        row = next(reversed(self.e._move_completions.values()))
        self.assertFalse(row['results'][self.t.entity_id]['hit'])
        self.assertEqual((self.t.conditions, self.t.stages, self.t.registry), before)
        self.assertEqual((self.a.budget['standard'], self.a.move_uses[M.MIND_READER]), (0, 1))
        self.assertEqual(self.e.rng.getstate(), rng)
        self.assertTrue(any(M.SOURCE in str(line) for line in self.e.log_lines))
        # A later activation rechecks current ownership and creates real Read.
        G.revoke(self.t, 'fixture:mindlock')
        self.e.end_of_turn(self.a)
        self.e.end_scene(self.e.everyone)
        self.begin(self.a)
        self.e.use_move(self.a, self.t, M.MIND_READER)
        self.assertTrue(__import__('telepath').live(self.t, 'read'))

    def test_gentle_actual_owned_ability_blocks_only_mindlock_recipient(self):
        G.replace_baseline(self.e, self.p, 'abilities', ['다정한분위기'])
        self.mindlock(self.t)
        self.p.pos = (6, 3)
        self.e.change_stage(self.t, 'atk', 2)
        self.e.gm.add_condition(self.t, '혼란', force=True, reason='observed agitation')
        self.begin(self.p)
        before = deepcopy((self.t.conditions, self.t.stages))
        resources = self.resources(self.p)
        out = self.e.activate_ability(self.p, 'Gentle Vibe', self.t)
        recipient = next(x for x in out['targets'] if x['target_id'] == self.t.entity_id)
        self.assertEqual((recipient['status'], recipient['immunity_source']), ('immune', M.SOURCE))
        self.assertEqual((self.t.conditions, self.t.stages), before)
        self.assertEqual(self.p.budget['standard'], 0)
        with self.assertRaises(ValueError):
            self.e.activate_ability(self.p, M.GENTLE_VIBE, copy(self.t))
        with self.assertRaisesRegex(ValueError, 'actual unsuppressed'):
            self.e.activate_ability(self.a, M.GENTLE_VIBE, self.t)
        self.p.abilities_suppressed = True
        with self.assertRaisesRegex(ValueError, 'actual unsuppressed'):
            self.e.activate_ability(self.p, M.GENTLE_VIBE, self.t)
        self.p.abilities_suppressed = False
        G.revoke(self.t, 'fixture:mindlock')
        self.begin(self.p)
        with self.assertRaisesRegex(ValueError, 'frequency'):
            self.e.activate_ability(self.p, M.GENTLE_VIBE, self.t)
        self.assertEqual((self.t.conditions, self.t.stages), before)

    def test_warning_consumes_actual_attacker_snapshot_not_warning_owner_or_target(self):
        self.warning_owner()
        self.mindlock(self.p)
        event_id = self.attack()
        event = self.e._passive_events[event_id]
        self.assertEqual((event['actor'], event[M.ATTACK_FACT]), (self.p, M.SOURCE))
        self.assertTrue(event['observations'])
        before = (self.resources(self.a), self.resources(self.t), deepcopy(self.a.spec))
        out = self.e.manual_feat(self.a, M.WARNING, event_id)
        self.assertEqual((out['status'], out['attacker_id']), ('not_triggered', self.p.entity_id))
        self.assertEqual((self.resources(self.a), self.resources(self.t), self.a.spec), before)
        G.revoke(self.p, 'fixture:mindlock')
        self.assertEqual(self.e.manual_feat(self.a, M.WARNING, event_id), out)
        # Owner/recipient Mindlock is the opposite direction and cannot block
        # an ordinary ally's attack. Its positive Warning stays pending.
        self.mindlock(self.a)
        self.mindlock(self.t)
        event2 = self.attack()
        before = (self.resources(self.a), self.resources(self.t), deepcopy(self.a.spec))
        pending = self.e.manual_feat(self.a, 'Telepathic Warning', event2)
        self.assertEqual(pending['status'], 'returned_attack')
        self.assertIsNone(self.e._passive_events[event2][M.ATTACK_FACT])
        self.assertEqual((self.resources(self.a), self.resources(self.t), self.a.spec), before)

    def test_warning_real_event_restore_tamper_and_source_selection_boundaries(self):
        self.warning_owner()
        self.mindlock(self.p)
        event_id = self.attack()
        self.e.end_of_turn(self.p)
        expected = self.e.manual_feat(self.a, M.WARNING, event_id)
        restored = self.restored()
        owner = next(c for c in restored.everyone if c.entity_id == self.a.entity_id)
        self.assertEqual(restored.manual_feat(owner, M.WARNING, event_id), expected)
        with self.assertRaises(ValueError):
            self.e.manual_feat(copy(self.a), M.WARNING, event_id)
        for forged in ('never-produced', {'event_id': event_id, 'attacker_id': self.p.entity_id}, self.p):
            with self.assertRaises(ValueError):
                self.e.manual_feat(self.a, M.WARNING, forged)
        self.e._passive_events[event_id][M.ATTACK_FACT] = None
        with self.assertRaises(ValueError):
            self.e.manual_feat(self.a, M.WARNING, event_id)
        self.e._passive_events[event_id][M.ATTACK_FACT] = M.SOURCE
        self.assertEqual(self.e.manual_feat(self.a, M.WARNING, event_id), expected)
        selected = self.r._selected_rule
        with patch.object(self.r, '_selected_rule', side_effect=lambda uid, *a, **k: 'other-source' if uid == M.SOURCE else selected(uid, *a, **k)):
            with self.assertRaisesRegex(ValueError, 'selected recipe source'):
                self.e.manual_feat(self.a, M.WARNING, event_id)
        G.revoke(self.a, 'fixture:telepathy')
        with self.assertRaisesRegex(ValueError, 'current Telepathy'):
            self.e.manual_feat(self.a, M.WARNING, event_id)


if __name__ == '__main__':
    unittest.main()
