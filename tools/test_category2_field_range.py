"""C10-208: Field range uses the actual encounter field once."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'engine'),str(ROOT/'tools')]

from builder import build_trainer
from engine import Rules,Engine,Combatant
from grid import Grid
import weapon_actions as WEAPONS

HAZE='move/흑안개'


class FieldRangeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.r=Rules(str(ROOT),ruleset='all')

    def add(self,name,pos,side='party'):
        spec=build_trainer(self.r,name,10,dict.fromkeys(('hp','atk','def','spa','spd','spe'),10),
            moves=[HAZE] if name=='user' else [],pos=pos,side=side)
        actor=Combatant(self.r,spec);self.e.gm.add_combatant(actor);return actor

    def setUp(self):
        self.e=Engine(self.r,seed=10208);self.e.grid=Grid(16,16)
        self.a=self.add('user',(1,1));self.ally=self.add('ally',(14,14))
        self.enemy=self.add('enemy',(1,14),'opponent');self.outside=self.add('outside',(14,1),'opponent')
        self.e.start_round([self.a,self.ally,self.enemy]);self.e.start_of_turn(self.a,initiative_count=20)
        for index,actor in enumerate((self.a,self.ally,self.enemy,self.outside),1):
            actor.stages['atk']=index;actor.accuracy_stage=min(index,6);actor.evasion_mod=min(index,6)

    def state(self):
        return deepcopy((self.a.budget,self.a.move_uses,self.a.pos,
            [(c.stages,c.accuracy_stage,c.evasion_mod,c.on_field) for c in self.e.everyone],self.e.rng.getstate()))

    def test_native_haze_resets_every_present_member_once_at_any_distance(self):
        move=self.r.move(HAZE);rng=WEAPONS.range_spec(self.e,move)
        self.assertTrue(WEAPONS.is_field(rng))
        self.assertEqual(self.e.targets_in_range(self.a,move,self.e.everyone,self.enemy),[self.a])
        with patch.object(self.e,'d20') as roll:
            self.e.use_move_on(self.a,self.enemy,HAZE,self.e.everyone)
        roll.assert_not_called()
        for actor in (self.a,self.ally,self.enemy):
            self.assertEqual((actor.stages['atk'],actor.accuracy_stage,actor.evasion_mod),(0,0,0))
        self.assertEqual((self.outside.stages['atk'],self.outside.accuracy_stage,self.outside.evasion_mod),(4,4,4))
        self.assertEqual(self.a.move_uses[HAZE],1)
        self.assertEqual(self.a.budget['standard'],0)

    def test_recalled_member_and_world_outsider_are_not_field_recipients(self):
        self.e.gm.recall(self.ally,reason='actual recall before Field Move')
        self.ally.stages['atk']=3;self.ally.accuracy_stage=2;self.ally.evasion_mod=1
        self.e.use_move_on(self.a,self.a,HAZE,self.e.everyone)
        self.assertEqual((self.ally.stages['atk'],self.ally.accuracy_stage,self.ally.evasion_mod),(3,2,1))
        self.assertEqual(self.outside.stages['atk'],4)

    def test_direct_foreign_anchor_rejects_before_cost_frequency_or_rng(self):
        before=self.state()
        with patch.object(self.e,'d20') as roll:
            with self.assertRaisesRegex(ValueError,'Field move requires its user'):
                self.e.use_move(self.a,self.enemy,HAZE)
        roll.assert_not_called();self.assertEqual(self.state(),before)

    def test_field_range_is_grid_independent_and_requires_live_encounter(self):
        move=self.r.move(HAZE);self.e.grid=None
        self.assertEqual(self.e.targets_in_range(self.a,move,self.e.everyone,self.enemy),[self.a])
        self.e.end_of_turn(self.a);self.e.end_encounter(round_elapsed_seconds=0)
        with self.assertRaisesRegex(ValueError,'actual encounter'):
            self.e.targets_in_range(self.a,move,self.e.everyone,self.enemy)


if __name__=='__main__':unittest.main()
