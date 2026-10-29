"""Native optional Eject windows must not expire in discarded feature cost quotes."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules
from contest import ContestRules,ContestEngine
import coordinator as COORD
import csv_item_physical_contracts as PHYSICAL
import passive_events as PASSIVE
import test_book_coordinator_full as COORD_FIX
import test_category2_csv_remaining_item_contracts as ITEM_FIX


class PreflightEjectWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules=Rules(ROOT,ruleset='core')
        cls.contest_rules=ContestRules(ROOT,ruleset='core')

    def fixture(self):
        case=COORD_FIX.CoordinatorFullTests()
        case.rules=self.rules;case.cr=self.contest_rules
        case.setUp();self.addCleanup(case.doCleanups)
        case.own()
        return case

    def equip(self,case,kind):
        fixture=ITEM_FIX.RemainingCsvItemContractTests();fixture.r=case.e.r
        item='item/탈출팩' if kind=='eject_pack' else 'item/탈출버튼'
        uid='preflight08/'+kind
        fixture.equip(case.e,case.q,uid,item)
        return uid

    def window(self,case,kind):
        return deepcopy(case.q.spec.get(PHYSICAL.PENDING,{}).get(kind))

    def open_pack(self,case):
        before=case.q.stages['atk']
        case.e.change_stage(case.q,'atk',-1)
        self.assertLess(case.q.stages['atk'],before)
        row=self.window(case,'eject_pack')
        self.assertIsNotNone(row,'actual native stage loss must issue the window')
        return row

    def open_window(self,case,kind):
        uid=self.equip(case,kind)
        if kind=='eject_pack':row=self.open_pack(case)
        else:
            case.combat(case.foe,count=10)
            hp=case.q.hp
            case.use(case.foe,case.q,'move/몸통박치기',face=12)
            self.assertLess(case.q.hp,hp,'Eject Button must originate from an actual native hit')
            row=self.window(case,kind)
            self.assertIsNotNone(row)
        self.assertEqual(row['instance_id'],uid)
        return uid,row

    def test_contest_decline_or_invalid_choice_preserves_actual_eject_window(self):
        for kind in ('eject_pack','eject_button'):
            for choice in (False,'wait'):
                with self.subTest(item=kind,choice=choice):
                    case=self.fixture();contest,contestants=case.contest()
                    uid,before=self.open_window(case,kind)
                    history=list(getattr(case.t,'_action_history',[]));seen=[]
                    def decision(preview):
                        seen.append(self.window(case,kind))
                        return choice
                    options=dict(reroll_decision=decision,attempt_id='preflight08-contest')
                    if choice=='wait':
                        with self.assertRaises(ValueError):
                            contest.perform(contestants[0],'move/몸통박치기','근사함',[],False,**options)
                    else:contest.perform(contestants[0],'move/몸통박치기','근사함',[],False,**options)
                    self.assertEqual(seen,[before],'discarded pre-choice quote cannot close the window')
                    self.assertEqual(self.window(case,kind),before)
                    self.assertEqual(list(getattr(case.t,'_action_history',[])),history)
                    self.assertNotIn('consumed',case.e._physical_objects[uid])
                    self.assertTrue(case.q.on_field)
                    if choice=='wait':
                        contest.perform(contestants[0],'move/몸통박치기','근사함',[],False,
                            reroll_decision=lambda preview:False,attempt_id='preflight08-contest')
                        self.assertEqual(self.window(case,kind),before)
                        self.assertEqual(list(getattr(case.t,'_action_history',[])),history)

    def test_contest_accepted_cost_expires_window_once_and_replay_preserves_new_window(self):
        for kind in ('eject_pack','eject_button'):
            with self.subTest(item=kind):
                case=self.fixture();contest,contestants=case.contest()
                uid,before=self.open_window(case,kind)
                history=list(getattr(case.t,'_action_history',[]));seen=[]
                def decision(preview):
                    seen.append(self.window(case,kind))
                    return True
                contest.perform(contestants[0],'move/몸통박치기','근사함',[],False,
                    reroll_decision=decision,attempt_id='preflight08-accepted')
                self.assertEqual(seen,[before],'window must remain live until actual accepted cost')
                self.assertIsNone(self.window(case,kind))
                self.assertEqual(case.t._action_history,history+['free'])
                self.assertNotIn('consumed',case.e._physical_objects[uid])
                if kind=='eject_pack':fresh=self.open_pack(case)
                else:
                    case.next_turn(case.foe,count=10)
                    hp=case.q.hp
                    case.use(case.foe,case.q,'move/몸통박치기',face=12)
                    self.assertLess(case.q.hp,hp)
                    fresh=self.window(case,kind);self.assertIsNotNone(fresh)
                with self.assertRaises(ValueError):
                    contest.perform(contestants[0],'move/몸통박치기','근사함',[],False,
                        reroll_decision=lambda preview:True,attempt_id='preflight08-accepted')
                self.assertEqual(self.window(case,kind),fresh)
                self.assertEqual(case.t._action_history,history+['free'])

    def test_damage_postquote_pending_preserves_window_then_actual_cost_expires_once(self):
        case=self.fixture();uid=self.equip(case,'eject_pack')
        COORD.arm_damage(case.e,case.t,case.p,decision=lambda preview:'wait')
        case.combat(case.p,count=25);hp=case.foe.hp
        with self.assertRaises(PASSIVE.PassiveEventPending) as paused:
            case.use(case.p,case.foe,'move/몸통박치기',face=12)
        event_id=paused.exception.event_id
        self.assertEqual(case.e._passive_pending,event_id)
        observed=case.e._passive_events[event_id]['coordinator_damage']
        first=(observed['first_damage'],deepcopy(observed['pools']))
        self.assertEqual(case.foe.hp,hp)
        self.assertEqual(case.p.move_uses['move/몸통박치기'],1)
        before=self.open_pack(case)
        history=list(getattr(case.t,'_action_history',[]));quoted=[]
        actual_quote=ContestEngine._stage_feature_cost
        def wait_after_quote(engine,trainer,amount,source):
            actual_quote(engine,trainer,amount,source)
            quoted.append(source)
            raise ValueError('controlled post-quote admission remains unresolved')
        # Keep the real native quote and the real pending-event catcher.
        with patch.object(ContestEngine,'_stage_feature_cost',staticmethod(wait_after_quote)):
            with self.assertRaises(PASSIVE.PassiveEventPending) as still_pending:
                COORD.restore_damage_choice(case.e,case.t,decision=lambda preview:True)
        self.assertEqual(still_pending.exception.event_id,event_id)
        self.assertEqual(quoted,[COORD.CLASS])
        self.assertEqual(case.e._passive_pending,event_id)
        self.assertEqual(self.window(case,'eject_pack'),before,
            'accepted choice is not payment: failed native quote must preserve other actors')
        self.assertEqual(list(getattr(case.t,'_action_history',[])),history)
        current=case.e._passive_events[event_id]['coordinator_damage']
        self.assertEqual((current['first_damage'],current['pools']),first)
        self.assertEqual(case.foe.hp,hp)
        self.assertEqual(case.p.move_uses['move/몸통박치기'],1)
        self.assertNotIn('consumed',case.e._physical_objects[uid])
        COORD.restore_damage_choice(case.e,case.t,decision=lambda preview:True)
        self.assertIsNone(self.window(case,'eject_pack'))
        self.assertEqual(case.t._action_history,history+['free'])
        self.assertEqual(case.p.move_uses['move/몸통박치기'],1)
        self.assertLess(case.foe.hp,hp)
        fresh=self.open_pack(case)
        with self.assertRaisesRegex(ValueError,'actual pending Coordinator'):
            COORD.restore_damage_choice(case.e,case.t,decision=lambda preview:True)
        self.assertEqual(self.window(case,'eject_pack'),fresh)
        self.assertEqual(case.t._action_history,history+['free'])