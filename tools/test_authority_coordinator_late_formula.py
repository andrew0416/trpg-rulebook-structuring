"""One post-RNG rollback control for the frozen Coordinator accepted branch.

Uses real Free, frequency, random pools and damage formula; only the failure
AFTER the first actual scale calculation is injected. No runtime edits.
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
import combat_damage as DAMAGE
import frequency as F
import world_entities as W
import csv_item_physical_contracts as PHYSICAL


class CoordinatorLateFormula(unittest.TestCase):
    setUpClass=classmethod(PRE.PreflightEjectWindowTests.setUpClass.__func__)
    fixture=PRE.PreflightEjectWindowTests.fixture
    equip=PRE.PreflightEjectWindowTests.equip
    window=PRE.PreflightEjectWindowTests.window
    open_pack=PRE.PreflightEjectWindowTests.open_pack

    def test_after_real_reroll_formula_failure_restores_pending_rng_quota_and_world(self):
        case=self.fixture();self.equip(case,'eject_pack')
        C.arm_damage(case.e,case.t,case.p,decision=lambda preview:'wait')
        case.combat(case.p,count=25);hp=case.foe.hp
        with self.assertRaises(P.PassiveEventPending) as paused:
            case.use(case.p,case.foe,'move/몸통박치기',face=12)
        event_id=paused.exception.event_id
        first=case.e._passive_events[event_id]['coordinator_damage']
        observed=(first['first_damage'],deepcopy(first['pools']),first['sha256'])
        window=self.open_pack(case)
        before_rng=case.e.rng.getstate();before_frequency=deepcopy(F.state(case.t))
        before_history=list(getattr(case.t,'_action_history',[]))
        uses=case.p.move_uses['move/몸통박치기']
        def quota(state):
            return sum(row.get('used',0) for key,row in state.get('activations',{}).items()
                       if key==C.CLASS or key.startswith(C.CLASS+':'))
        native_free=CF.trigger_free_action;native_pool=POOLS.pool;native_scale=DAMAGE.scale
        paid=[];drawn=[];calculated=[]
        def observe_actual_free(engine,trainer,source):
            result=native_free(engine,trainer,source)
            if source==C.CLASS:paid.append((engine,trainer))
            return result
        def observe_random_pool(rng,count,**options):
            result=native_pool(rng,count,**options)
            drawn.append((options.get('fixed'),deepcopy(result)))
            return result
        def fail_after_actual_formula(**options):
            result=native_scale(**options)
            if paid:
                staged,trainer=paid[-1]
                other=W.actor_index(staged)[case.q.entity_id]
                calculated.append({'damage':result,'rng':staged.rng.getstate(),
                    'frequency':deepcopy(F.state(trainer)),
                    'history':list(trainer._action_history),
                    'window':deepcopy(other.spec.get(PHYSICAL.PENDING,{}).get('eject_pack'))})
            raise ValueError('controlled failure after actual reroll pools and native damage scaling')
        with patch.object(CF,'trigger_free_action',side_effect=observe_actual_free), \
                patch.object(POOLS,'pool',side_effect=observe_random_pool), \
                patch.object(DAMAGE,'scale',side_effect=fail_after_actual_formula):
            with self.assertRaises(P.PassiveEventPending) as pending:
                C.restore_damage_choice(case.e,case.t,decision=lambda preview:True)
        self.assertEqual(pending.exception.event_id,event_id)
        self.assertEqual(len(paid),1);self.assertEqual(len(calculated),1)
        self.assertEqual(len(drawn),len(observed[1]))
        self.assertTrue(all(fixed is None for fixed,_ in drawn),'real random pools, never fixed faces')
        self.assertGreater(sum(row['count'] for _,row in drawn),0)
        private=calculated[0]
        self.assertNotEqual(private['rng'],before_rng,'random reroll really advanced its private RNG')
        self.assertEqual(quota(private['frequency']),quota(before_frequency)+1)
        self.assertEqual(private['history'],before_history+['free'])
        self.assertIsNone(private['window'],'actual accepted Free expired the staged native window')
        self.assertGreaterEqual(private['damage'],0,'real native scaling returned before injected failure')
        self.assertEqual(case.e.rng.getstate(),before_rng)
        self.assertEqual(F.state(case.t),before_frequency)
        self.assertEqual(getattr(case.t,'_action_history',[]),before_history)
        self.assertEqual(self.window(case,'eject_pack'),window)
        self.assertEqual(case.foe.hp,hp);self.assertEqual(case.p.move_uses['move/몸통박치기'],uses)
        self.assertEqual(case.e._passive_pending,event_id)
        current=case.e._passive_events[event_id]['coordinator_damage']
        self.assertEqual((current['first_damage'],current['pools'],current['sha256']),observed)
        self.assertNotIn('decision',current);self.assertNotIn('rerolled_pools',current)
        C.restore_damage_choice(case.e,case.t,decision=lambda preview:True)
        selected=case.e._passive_events[event_id]['coordinator_damage']
        self.assertEqual(selected['rerolled_pools'],[row for _,row in drawn],
            'retry must use the restored RNG stream, not consume another hidden reroll')
        self.assertIsNone(case.e._passive_pending);self.assertIsNone(self.window(case,'eject_pack'))
        self.assertEqual(quota(F.state(case.t)),quota(before_frequency)+1)
        self.assertEqual(case.t._action_history,before_history+['free'])
        self.assertEqual(case.p.move_uses['move/몸통박치기'],uses);self.assertLess(case.foe.hp,hp)
        fresh=self.open_pack(case)
        with self.assertRaisesRegex(ValueError,'actual pending Coordinator'):
            C.restore_damage_choice(case.e,case.t,decision=lambda preview:True)
        self.assertEqual(self.window(case,'eject_pack'),fresh)
        self.assertEqual(quota(F.state(case.t)),quota(before_frequency)+1)
        self.assertEqual(case.t._action_history,before_history+['free'])

if __name__=='__main__':unittest.main()