"""Native movement interruption must retain the paid Intercept producer."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_move_defense_reactions as FIXTURE
from engine import Rules
import passive_events as PASSIVE
import movement_actions as MOVE
import state_grants as GRANTS
import action_resources as RESOURCES
import stamina as STAMINA


class MoveDefenseMovementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.rules=Rules(ROOT,ruleset='core')
    setUp=FIXTURE.MoveDefenseReactionsTests.setUp
    trainer=FIXTURE.MoveDefenseReactionsTests.trainer
    watch=FIXTURE.MoveDefenseReactionsTests.watch
    waiting=FIXTURE.MoveDefenseReactionsTests.waiting
    choose=FIXTURE.MoveDefenseReactionsTests.choose
    melee=FIXTURE.MoveDefenseReactionsTests.melee
    fresh=FIXTURE.MoveDefenseReactionsTests.fresh

    def test_blocked_paid_prefix_cold_restores_without_rechecking_or_repaying(self):
        self.watch();event=self.waiting();original=MOVE.departure
        def block(e,c,q,height):
            result=original(e,c,q,height)
            if c.entity_id==self.r.entity_id and q==(3,3):e.grid.blocking.add(q)
            return result
        with patch.object(MOVE,'departure',side_effect=block):
            with self.assertRaises(PASSIVE.PassiveEventPending):self.choose(event,options=self.melee())
        self.assertEqual(self.r.pos,(3,4));self.assertEqual(self.r._action_history,['full'])
        self.assertEqual(RESOURCES.pending(self.r),{'standard':1,'shift':1})
        rng=self.e.rng.getstate();self.fresh();self.e.grid.blocking.remove((3,3))
        with patch.object(self.e,'skill_check',side_effect=AssertionError('paid check must not repeat')):
            self.e.deliver_passive_event(event)
        self.assertEqual(self.r.pos,(3,2));self.assertEqual(self.r._action_history,['full'])
        self.assertEqual(self.e.rng.getstate(),rng);self.assertIsNone(self.e._passive_pending)
        self.fresh()

    def test_actual_opportunity_stamina_wait_resumes_intercept_once(self):
        enemy=self.trainer('opportunity foe',(4,5));enemy.side='opponent'
        self.e.gm.add_combatant(enemy)
        def acquire(e,c):
            c.spec.setdefault('edges',[]).append(STAMINA.SOURCE)
            c.spec['skills']={'Athletics':5,'Acrobatics':3,'Combat':6}
        GRANTS.transition(self.e,self.r,acquire)
        # Slash now requires its actual Pass path. Use an ordinary melee hit
        # here so this case observes the interceptor's paid movement.
        self.a.spec['moves'][0]='move/몸통박치기'
        self.a.moves[0]='move/몸통박치기'
        self.watch();event=self.waiting(move='move/몸통박치기');self.e.rng.seed(5)
        options=self.melee(faces=(6,6,6,6,6))
        with self.assertRaises(PASSIVE.PassiveEventPending):self.choose(event,options=options)
        self.assertEqual(self.r.pos,(3,4));self.assertTrue(enemy.aoo_used)
        action=next(row for row in self.e._native_action_resolutions.values()
                    if any(t['actor'] is self.r and t['source']==STAMINA.SOURCE for t in row['triggers']))
        self.fresh();self.e.resolve_stamina(self.r,action['id'],skill='육상')
        uses=len(self.e._move_completions)
        self.e.deliver_passive_event(event)
        self.assertEqual(len(self.e._move_completions),uses)
        self.assertEqual(self.r.pos,(3,2));self.assertEqual(self.r._action_history,['full'])
        self.assertIsNone(self.e._passive_pending)
        self.fresh()


if __name__=='__main__':unittest.main()
