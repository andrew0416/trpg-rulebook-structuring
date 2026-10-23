"""Encounter driver consumes actual Priority frames and stable original slots."""
from pathlib import Path
from unittest.mock import patch
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
import test_category2_priority_actions as P
import encounter
import combat_state_lifecycle as COMBAT
from state_codec import dump_engine


class PriorityDriverTests(unittest.TestCase):
    setUpClass = classmethod(P.PriorityActionTests.setUpClass.__func__)
    setUp = P.PriorityActionTests.setUp
    actor = P.PriorityActionTests.actor
    close = P.PriorityActionTests.close

    def driver(self, *, rounds=1, chosen=P.QUICK, withdraw=False):
        # Reuse the real actor fixture after closing its initial setup round.
        for actor in (self.t, self.p, self.foe):
            self.close(actor)
        self.e.end_round()
        self.t.spec.setdefault('moves', [])
        self.p.spec['species'] = self.foe.spec['species'] = '이상해씨'
        self.p.spec['moves'] = self.p.moves = [chosen]
        self.foe.spec['moves'] = self.foe.moves = ['move/몸통박치기']
        survivor = self.actor('surviving enemy', 5, 'pokemon', ['노말'], moves=[])
        survivor.side = 'enemy'
        survivor.spec['species'] = '이상해씨'
        party, wild = [self.t, self.p], [self.foe, survivor]
        calls = []

        def choose(e, actor, enemies, allies):
            if actor is self.p:
                return 'move', chosen, self.foe
            if actor is self.foe:
                return 'move', 'move/몸통박치기', self.p
            return None, None, None

        def hook(e, actor, rnd):
            calls.append((actor.entity_id, rnd))
            if withdraw and actor is self.foe:
                COMBAT.recall(e, actor)

        fixture = (self.e, {'name': 'native priority', 'rounds': rounds}, party, wild)
        with patch.object(encounter, 'load_encounter', return_value=fixture), \
                patch.object(encounter, 'choose_action', side_effect=choose):
            result = encounter.run_encounter(ROOT, 'fixture.json', hook=hook, write=False)
        self.assertIs(result[0], self.e)
        return calls, survivor

    def test_driver_two_rounds_uses_actual_move_frames_and_settles_original_slots_once(self):
        hp = self.foe.hp
        calls, _ = self.driver(rounds=2)
        windows = list(self.e._initiative_interrupts['windows'].values())
        self.assertEqual(len(windows), 2)
        self.assertTrue(all(window['requests'][0]['source'] == P.QUICK for window in windows))
        self.assertEqual(self.p.move_uses[P.QUICK], 2)
        self.assertLess(self.foe.hp, hp)
        self.assertEqual(self.p.custom_conditions['combat_turn_serial'], 3)
        self.assertEqual(self.e.initiative_schedule_status()['status'], 'completed')
        self.assertFalse(self.e.initiative_reaction_status()['owed_turns'])
        self.assertEqual(len(calls), len(set(calls)))
        dump_engine(self.e)

    def test_driver_does_not_promote_conditional_pledge_keyword_to_priority(self):
        self.driver(chosen='move/불꽃의맹세')
        self.assertFalse(getattr(self.e, '_initiative_interrupts', {}).get('windows'))
        self.assertEqual(self.p.custom_conditions['combat_turn_serial'], 2)
        self.assertEqual(self.p.move_uses['move/불꽃의맹세'], 1)
        self.assertEqual(self.e.initiative_schedule_status()['status'], 'completed')
        dump_engine(self.e)

    def test_driver_native_withdrawal_skips_only_unavailable_slot_without_owner_clock(self):
        calls, survivor = self.driver(withdraw=True)
        self.assertFalse(self.foe.on_field)
        self.assertTrue(survivor.on_field)
        self.assertEqual(self.foe.custom_conditions['combat_turn_serial'], 1)
        self.assertEqual(self.p.custom_conditions['combat_turn_serial'], 2)
        self.assertEqual(self.e.initiative_schedule_status()['status'], 'completed')
        self.assertFalse(self.e.initiative_reaction_status()['owed_turns'])
        self.assertEqual(len(calls), len(set(calls)))
        dump_engine(self.e)


if __name__ == '__main__':
    unittest.main()
