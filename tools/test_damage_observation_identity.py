"""Damage-floor authority comes from actual arguments, not an output collector.

Collector/None numeric equality below is scoped to the hook-free basic fixture;
other event-bound feature consumers retain their separate existing contracts.
"""
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import earned_status_choices as CHOICE
import test_category2_delayed_attacks as DELAYED


class DamageObservationIdentityTests(unittest.TestCase):
    setUpClass=classmethod(DELAYED.DelayedAttackTests.setUpClass.__func__)
    world=DELAYED.DelayedAttackTests.world

    def test_resistance_floors_use_actual_move_for_none_empty_and_stale_output(self):
        engine,actor,target=self.world(DELAYED.MOVES[0])
        move=engine.r.move(DELAYED.MOVES[0])
        self.assertFalse(engine.rulings.hooks.get('before_damage'))
        baseline=engine.roll_damage(actor,target,move,set_damage=True)
        self.assertGreater(baseline,0)
        collectors=[{}, {'attacker':target,'target':actor,
                         'move':dict(move,**{CHOICE.MARKER:'not-an-issued-occurrence'}),
                         'client_note':'retain unrelated output metadata'}]
        for collector in collectors:
            with self.subTest(collector='stale' if 'attacker' in collector else 'empty'):
                actual=engine.roll_damage(actor,target,move,set_damage=True,_reaction_event=collector)
                self.assertEqual(actual,baseline)
                self.assertEqual(collector['damage'],baseline)
                self.assertLess(collector['resisted_damage'],baseline)
                self.assertIs(collector['context']['attacker'],actor)
                self.assertIs(collector['context']['target'],target)
                self.assertEqual(collector['context']['move']['id'],move['id'])
        self.assertEqual(collectors[1]['client_note'],'retain unrelated output metadata')
        self.assertIs(collectors[1]['attacker'],target)
        # A bad marker on the actual Move still fails its native occurrence
        # guard; an empty or misleading collector cannot make it legitimate.
        forged=dict(move,**{CHOICE.MARKER:'not-an-issued-occurrence'})
        for collector in (None,*collectors):
            with self.subTest(actual_move_marker=True,collector_none=collector is None):
                with self.assertRaisesRegex(ValueError,'actual earned-choice Move occurrence required'):
                    engine.roll_damage(actor,target,forged,set_damage=True,_reaction_event=collector)


if __name__=='__main__':
    unittest.main()
