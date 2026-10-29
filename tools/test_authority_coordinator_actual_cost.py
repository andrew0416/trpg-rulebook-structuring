"""Actual Coordinator cost failure preserves first observation and world windows.

Requires candidate-repair07-v3 pure quote and candidate-preflight-controls08
fixture. Only a late failure is injected; the real native Free action executes.
"""
from copy import deepcopy
from pathlib import Path
import os
import sys
import unittest
from unittest.mock import patch
ROOT=Path(os.environ.get('PTK_EXPERIMENT_ROOT') or Path(__file__).resolve().parents[1]).resolve()
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_preflight_eject_windows08 as PRE
import coordinator as C
import contest_features as CF
import passive_events as P
import roll_pools as POOLS
import frequency as F
import world_entities as W
import csv_item_physical_contracts as PHYSICAL


class CoordinatorActualCost(unittest.TestCase):
    setUpClass=classmethod(PRE.PreflightEjectWindowTests.setUpClass.__func__)
    fixture=PRE.PreflightEjectWindowTests.fixture
    equip=PRE.PreflightEjectWindowTests.equip
    window=PRE.PreflightEjectWindowTests.window
    open_pack=PRE.PreflightEjectWindowTests.open_pack

    def test_late_actual_free_failure_rolls_back_world_cost_and_keeps_observed_roll(self):
        case=self.fixture();self.equip(case,'eject_pack')
        C.arm_damage(case.e,case.t,case.p,decision=lambda preview:'wait')
        case.combat(case.p,count=25);hp=case.foe.hp
        with self.assertRaises(P.PassiveEventPending) as paused:
            case.use(case.p,case.foe,'move/몸통박치기',face=12)
        event_id=paused.exception.event_id
        first=case.e._passive_events[event_id]['coordinator_damage']
        observed=(first['first_damage'],deepcopy(first['pools']),first['sha256'])
        window=self.open_pack(case)
        before=(case.e.rng.getstate(),deepcopy(F.state(case.t)),
                list(getattr(case.t,'_action_history',[])),case.p.move_uses['move/몸통박치기'])
        actual_free=CF.trigger_free_action;executed=[]
        def fail_after_actual_free(engine,trainer,source):
            actual_free(engine,trainer,source)
            other=W.actor_index(engine)[case.q.entity_id]
            executed.append((source,trainer._action_history[-1],other.spec.get(PHYSICAL.PENDING,{}).get('eject_pack')))
            raise ValueError('controlled failure after the real native Free action')
        with patch.object(CF,'trigger_free_action',side_effect=fail_after_actual_free), \
                patch.object(POOLS,'pool',side_effect=AssertionError('actual cost must succeed before reroll dice')):
            with self.assertRaises(P.PassiveEventPending) as pending:
                C.restore_damage_choice(case.e,case.t,decision=lambda preview:True)
        self.assertEqual(pending.exception.event_id,event_id)
        self.assertEqual(executed,[(C.CLASS,'free',None)],'real action happened only inside the rolled-back branch')
        self.assertEqual(self.window(case,'eject_pack'),window)
        self.assertEqual((case.e.rng.getstate(),F.state(case.t),getattr(case.t,'_action_history',[]),
                          case.p.move_uses['move/몸통박치기']),before)
        current=case.e._passive_events[event_id]['coordinator_damage']
        self.assertEqual((current['first_damage'],current['pools'],current['sha256']),observed)
        self.assertNotIn('decision',current);self.assertNotIn('rerolled_pools',current)
        self.assertEqual(case.foe.hp,hp);self.assertEqual(case.e._passive_pending,event_id)
        C.restore_damage_choice(case.e,case.t,decision=lambda preview:True)
        self.assertIsNone(case.e._passive_pending);self.assertIsNone(self.window(case,'eject_pack'))
        self.assertEqual(case.t._action_history,before[2]+['free'])
        self.assertEqual(case.p.move_uses['move/몸통박치기'],1);self.assertLess(case.foe.hp,hp)
        fresh=self.open_pack(case)
        with self.assertRaisesRegex(ValueError,'actual pending Coordinator'):
            C.restore_damage_choice(case.e,case.t,decision=lambda preview:True)
        self.assertEqual(self.window(case,'eject_pack'),fresh)
        self.assertEqual(case.t._action_history,before[2]+['free'])

if __name__=='__main__':unittest.main()