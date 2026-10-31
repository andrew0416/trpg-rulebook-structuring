"""The operation-scoped actor index equals the full state-graph walk.

Roster order comes first (actor-to-actor references do not reorder it), a memo hit
inside a verification scope returns the same mapping as a fresh walk in a fresh dict,
declared roster changes invalidate the memo, and an undeclared registry change is
caught by PTK_ACTOR_INDEX_CHECK=1 (the full-regression safety net)."""
import copy
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Rules, Engine, Combatant
import source_selection as SOURCES
import world_entities as WORLD

CHECK = {'PTK_ACTOR_INDEX_CHECK': '1'}


class ActorIndexMemoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(str(ROOT), ruleset='core')

    def actor(self, name):
        r = self.rules
        return Combatant(r, dict(copy.deepcopy(r.creatures['pokemon/archie']), id='pokemon/memo-' + name))

    def fixture(self):
        e = Engine(self.rules, seed=5)
        actors = [self.actor(k) for k in 'abc']
        e.everyone = e.gm.everyone = list(actors)
        return e, actors

    def test_roster_order_does_not_follow_actor_references(self):
        e, (a, b, c) = self.fixture()
        a.last_target = c                      # the walk reaches c through a before it reaches b
        self.assertEqual(list(WORLD.actor_index(e)), [a.entity_id, b.entity_id, c.entity_id])
        self.assertEqual(list(WORLD._actor_index(e)), [a.entity_id, b.entity_id, c.entity_id])

    def test_memo_hit_inside_scope_equals_walk_and_is_a_fresh_dict(self):
        e, (a, b, c) = self.fixture()
        with mock.patch.dict(os.environ, CHECK), SOURCES.verification_scope():
            first = WORLD.actor_index(e)
            a.last_target = b                  # a reference change is not a roster change
            second = WORLD.actor_index(e)
            self.assertEqual(list(first.items()), list(second.items()))
            self.assertIsNot(first, second)
            second['extra'] = None             # callers may edit their copy
            self.assertNotIn('extra', WORLD.actor_index(e))
            self.assertEqual(list(WORLD.actor_index(e).items()), list(WORLD._actor_index(e).items()))

    def test_declared_roster_changes_invalidate_inside_scope(self):
        e, (a, b, c) = self.fixture()
        d = self.actor('d')
        with mock.patch.dict(os.environ, CHECK), SOURCES.verification_scope():
            WORLD.actor_index(e)
            e.gm.add_combatant(d, side='party')
            self.assertIn(d.entity_id, WORLD.actor_index(e))
            e.gm.remove_combatant(d)
            self.assertNotIn(d.entity_id, WORLD.actor_index(e))
            e.everyone.append(d)               # a direct roster edit changes the memo key itself
            self.assertIn(d.entity_id, WORLD.actor_index(e))

    def test_undeclared_registry_change_is_caught_in_check_mode(self):
        e, (a, b, c) = self.fixture()
        d = self.actor('d')
        with mock.patch.dict(os.environ, CHECK), SOURCES.verification_scope():
            WORLD.actor_index(e)
            e._memo_test_registry = [d]        # reachable only through an engine registry
            with self.assertRaisesRegex(ValueError, 'actor index memo stale'):
                WORLD.actor_index(e)
            WORLD.roster_changed(e)
            self.assertIn(d.entity_id, WORLD.actor_index(e))
        del e._memo_test_registry
        self.assertNotIn(d.entity_id, WORLD.actor_index(e))   # outside a scope every call walks


if __name__ == '__main__':
    unittest.main()
