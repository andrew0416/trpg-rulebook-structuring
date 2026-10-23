"""C10-195: actual Every Other Turn Moves use the world clock outside combat."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'engine'),str(ROOT/'tools')]

from builder import build_pokemon
from engine import Rules,Engine,Combatant
import frequency as F
import state_codec as CODEC
import world_entities as W

MOVE='move/방어지령'


class OutOfCombatEotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules=Rules(str(ROOT),ruleset='all')

    def setUp(self):
        self.e=Engine(self.rules,seed=4195)
        self.p=Combatant(self.rules,build_pokemon(self.rules,'이브이',20,moves=[MOVE],abilities=[]))
        self.e.everyone=self.e.gm.everyone=[self.p]

    def use(self):
        # The free-action input isolates the frequency contract outside combat;
        # Engine.use_move still owns the actual move producer and usage receipt.
        return self.e.use_move(self.p,self.p,MOVE,free_action=True)

    def test_native_move_rejects_until_ten_world_seconds_then_executes(self):
        self.assertFalse(self.e.encounter_active)
        self.use()
        self.assertEqual((self.p.stages['def'],self.p.stages['spd']), (1,1))
        receipt=deepcopy(F.state(self.p)['moves'][MOVE])
        self.assertEqual(receipt['at_seconds'],0)
        self.assertFalse(F.move_allowed(self.e,self.p,MOVE,outside_combat=True)[0])
        self.e.advance_time(9,[self.p])
        before=(deepcopy(self.p.spec),deepcopy(self.p.stages),self.e.rng.getstate())
        self.use()
        self.assertEqual((self.p.spec,self.p.stages,self.e.rng.getstate()),before)
        self.e.advance_time(1,[self.p])
        self.assertTrue(F.move_allowed(self.e,self.p,MOVE,outside_combat=True)[0])
        self.use()
        self.assertEqual((self.p.stages['def'],self.p.stages['spd']), (2,2))
        self.assertEqual(F.state(self.p)['moves'][MOVE]['at_seconds'],10)

    def test_durable_restore_preserves_interval_and_rejects_future_clock(self):
        self.use();self.e.advance_time(9,[self.p])
        loaded=CODEC.load_engine(self.rules,CODEC.dump_engine(self.e))
        p=W.actor_index(loaded)[self.p.entity_id]
        self.assertFalse(F.move_allowed(loaded,p,MOVE,outside_combat=True)[0])
        loaded.advance_time(1,[p])
        self.assertTrue(F.move_allowed(loaded,p,MOVE,outside_combat=True)[0])
        F.state(p)['moves'][MOVE]['at_seconds']=loaded.elapsed_seconds+1
        with self.assertRaisesRegex(ValueError,'ahead of the world clock'):
            F.move_allowed(loaded,p,MOVE,outside_combat=True)

    def test_legacy_same_scene_without_timestamp_fails_closed(self):
        self.use()
        F.state(self.p)['moves'][MOVE].pop('at_seconds')
        allowed,reason=F.move_allowed(self.e,self.p,MOVE,outside_combat=True)
        self.assertFalse(allowed)
        self.assertIn('마지막 사용 시각 미확인',reason)


if __name__=='__main__':unittest.main()
