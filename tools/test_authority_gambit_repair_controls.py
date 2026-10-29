"""Public native controls for the retained Gambit continuation repair.

Requires candidate-repair02 runtime plus the original candidate-review02 probe
module. No test creates Gambit state, receipts or synthetic pending exceptions.
"""
from copy import deepcopy
from pathlib import Path
import json
import os
import sys
import unittest
from unittest.mock import patch

ROOT=Path(os.environ.get('PTK_EXPERIMENT_ROOT') or Path(__file__).resolve().parents[1]).resolve()
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_authority_candidate_pending02 as PROBE
from engine import Engine
import passive_events as PASSIVE
import move_defense_reactions as DEFENSE
import frequency as FREQ
import state_codec as CODEC
import taskmaster as TASK


class GambitRepairControls(unittest.TestCase):
    # Reuse the exact acquired/registered native fixture without inheriting its
    # original red tests a second time under a new class name.
    setUpClass=classmethod(PROBE.CandidatePending02Tests.setUpClass.__func__)
    private_rules=PROBE.CandidatePending02Tests.private_rules
    known_detect=PROBE.CandidatePending02Tests.known_detect
    gambit=PROBE.CandidatePending02Tests.gambit
    gambit_result=PROBE.CandidatePending02Tests.gambit_result
    gambit_control=PROBE.CandidatePending02Tests.gambit_control
    restore_actors=PROBE.CandidatePending02Tests.restore_actors

    def cold(self,f):
        f.e,f.a,f.p,f.q,f.b=self.restore_actors(f.e,f.a,f.p,f.q,f.b)

    def pause(self,f,*,random_damage=False):
        if random_damage:
            f.answer('deadly_gambit',{'move':'struggle','roll_effects':False,'options':{'set_damage':False}})
        with patch.object(Engine,'d20',side_effect=AssertionError('selected Gambit accuracy is automatic')):
            with self.assertRaises(PASSIVE.PassiveEventPending) as caught:
                f.e.use_move(f.b,f.p,'move/몸통박치기',set_damage=not random_damage)
        event=caught.exception.event_id
        self.assertEqual(f.e._passive_pending,event)
        self.assertIn(event,f.e._passive_events)
        return event

    def resources(self,f):
        return deepcopy((self.gambit_result(f),f.e.rng.getstate(),f.a.spec.get('ap_spent',0),
            f.a._action_history,f.p._action_history,f.b._action_history,
            f.p.move_uses,f.b.move_uses))

    def test_incoming_attacker_faint_cancels_counter_without_refunding_paid_gambit(self):
        for cold in (False,True):
            with self.subTest(cold=cold):
                f=self.gambit('incoming');pokemon_hp=f.p.hp
                event=self.pause(f)
                paid=(FREQ.state(f.a)['activations'][TASK.GAMBIT]['used'],
                      f.b.move_uses['move/몸통박치기'],f.b._action_history.count('standard'))
                if cold:self.cold(f)
                f.e.gm.faint(f.b,reason='actual incoming attacker faints before the retained hit resumes')
                with patch.object(Engine,'d20',side_effect=AssertionError('cancelled paid accuracy cannot reroll')):
                    f.e.deliver_passive_event(event)
                self.assertIsNone(f.e._passive_pending)
                self.assertEqual(f.p.hp,pokemon_hp)
                self.assertEqual(f.p.move_uses.get('struggle',0),0)
                self.assertEqual((FREQ.state(f.a)['activations'][TASK.GAMBIT]['used'],
                    f.b.move_uses['move/몸통박치기'],f.b._action_history.count('standard')),paid)
                self.assertEqual(paid,(1,1,1))

    def test_actual_detect_cancels_only_counter_and_parent_hit_finishes_once(self):
        expected=self.gambit_control()
        for cold in (False,True):
            with self.subTest(cold=cold):
                f=self.gambit('counter');foe_hp=f.b.hp
                event=self.pause(f)
                self.assertIs(f.e._passive_events[event]['actor'],f.p)
                self.assertIn(DEFENSE.DETECT,f.b.moves)
                if cold:self.cold(f)
                with patch.object(Engine,'d20',side_effect=AssertionError('paid counter accuracy cannot reroll')):
                    f.e.choose_move_defense(event,f.b,use=True,reason='actual learned Detect avoids the counter')
                self.assertIsNone(f.e._passive_pending)
                self.assertEqual(f.p.hp,expected['pokemon_hp'])
                self.assertEqual(f.b.hp,foe_hp)
                self.assertEqual(f.p.move_uses.get('struggle',0),1)
                self.assertEqual(f.b.move_uses.get(DEFENSE.DETECT,0),1)
                self.assertEqual(f.b.move_uses.get('move/몸통박치기',0),1)
                self.assertEqual(FREQ.state(f.a)['activations'][TASK.GAMBIT]['used'],1)

    def test_removed_known_counter_move_is_rechecked_before_fresh_counter_execution(self):
        expected=self.gambit_control()
        for cold in (False,True):
            with self.subTest(cold=cold):
                f=self.gambit('incoming');foe_hp=f.b.hp
                self.assertIn('move/물대포',f.p.moves)
                f.answer('deadly_gambit',{'move':'move/물대포','roll_effects':False,'options':{'set_damage':True}})
                event=self.pause(f)
                if cold:self.cold(f)
                f.e.gm.set_move(f.p,'move/물대포',add=False,reason='actual known Move withdrawn before counter starts')
                self.assertNotIn('move/물대포',f.p.moves)
                with patch.object(Engine,'d20',side_effect=AssertionError('paid incoming accuracy cannot reroll')):
                    f.e.choose_move_defense(event,f.p,use=False,reason='actual Detect declined')
                self.assertIsNone(f.e._passive_pending)
                self.assertEqual(f.p.hp,expected['pokemon_hp'])
                self.assertEqual(f.b.hp,foe_hp)
                self.assertEqual(f.p.move_uses.get('move/물대포',0),0)
                self.assertEqual(f.p.move_uses.get('struggle',0),0)
                self.assertEqual(f.b.move_uses.get('move/몸통박치기',0),1)
                self.assertEqual(FREQ.state(f.a)['activations'][TASK.GAMBIT]['used'],1)

    def test_counter_knockout_cannot_cancel_the_committed_simultaneous_incoming_hit(self):
        for mutual in (False,True):
            with self.subTest(mutual_knockout=mutual):
                f=self.gambit('counter')
                f.e.gm.set_hp(f.b,value=1,reason='actual opponent is conscious at one HP before both attacks')
                if mutual:
                    f.e.gm.set_hp(f.p,value=1,reason='actual partner is conscious at one HP before both attacks')
                pokemon_hp=f.p.hp;foe_hp=f.b.hp
                event=self.pause(f)
                self.assertEqual((f.p.hp,f.b.hp),(pokemon_hp,foe_hp),
                    'neither simultaneous damage may commit while the counter is still choosing its defense')
                with patch.object(Engine,'d20',side_effect=AssertionError('committed accuracy must not reroll')):
                    f.e.choose_move_defense(event,f.b,use=False,reason='actual Detect declined; both Gambit damages settle')
                self.assertIsNone(f.e._passive_pending)
                self.assertTrue(f.b.fainted)
                self.assertLess(f.p.hp,pokemon_hp,
                    'the actual counter knockout cannot revoke the already-committed incoming hit')
                if mutual:self.assertTrue(f.p.fainted)
                self.assertEqual((f.b.move_uses.get('move/몸통박치기',0),f.p.move_uses.get('struggle',0),
                    FREQ.state(f.a)['activations'][TASK.GAMBIT]['used']),(1,1,1))

    def random_control(self,hook=None):
        f=self.gambit()
        f.answer('deadly_gambit',{'move':'struggle','roll_effects':False,'options':{'set_damage':False}})
        if hook is not None:f.e.rule_hook('before_damage',hook,reason='record actual finalized damage boundary',scope='scene')
        before=f.e.rng.getstate()
        with patch.object(Engine,'d20',side_effect=AssertionError('selected automatic accuracy has no d20')):
            f.e.use_move(f.b,f.p,'move/몸통박치기',set_damage=False)
        self.assertNotEqual(f.e.rng.getstate(),before,'control must use actual random damage pools')
        return f

    def test_cold_counter_resume_preserves_random_parent_prefix_and_final_rng(self):
        control=self.random_control();expected=self.gambit_result(control);rng=control.e.rng.getstate()
        f=self.gambit('counter');initial_rng=f.e.rng.getstate()
        event=self.pause(f,random_damage=True)
        self.assertNotEqual(f.e.rng.getstate(),initial_rng,'parent damage must already have consumed actual dice')
        pending_rng=f.e.rng.getstate()
        self.cold(f);self.assertEqual(f.e.rng.getstate(),pending_rng)
        with patch.object(Engine,'d20',side_effect=AssertionError('paid native accuracy cannot reroll')):
            f.e.choose_move_defense(event,f.b,use=False,reason='actual counter Detect declined after cold restore')
        self.assertEqual(self.gambit_result(f),expected)
        self.assertEqual(f.e.rng.getstate(),rng,'resumed counter must not reroll the cached parent damage')
        self.assertIsNone(f.e._passive_pending)
        before=self.resources(f)
        try:f.e.deliver_passive_event(event)
        except ValueError:pass  # A completed delivery may reject or return its existing result.
        self.assertEqual(self.resources(f),before,'completed delivery cannot repay, redamage or draw dice')

    def test_warm_counter_resume_runs_actual_damage_hook_once_and_replay_is_inert(self):
        expected_hooks=[]
        def observe_control(value,context):
            expected_hooks.append((context['attacker'].name,context['target'].name,context['move']['id'],value))
            return value
        control=self.random_control(observe_control)
        self.assertEqual(len(expected_hooks),2)
        actual_hooks=[]
        def observe(value,context):
            actual_hooks.append((context['attacker'].name,context['target'].name,context['move']['id'],value))
            return value
        f=self.gambit('counter')
        f.e.rule_hook('before_damage',observe,reason='observe actual Gambit damage prefix exactly once',scope='scene')
        event=self.pause(f,random_damage=True)
        self.assertEqual(actual_hooks,expected_hooks[:1])
        with patch.object(Engine,'d20',side_effect=AssertionError('paid native accuracy cannot reroll')):
            f.e.choose_move_defense(event,f.b,use=False,reason='actual counter Detect declined')
        self.assertEqual(actual_hooks,expected_hooks)
        self.assertEqual(self.gambit_result(f),self.gambit_result(control))
        self.assertEqual(f.e.rng.getstate(),control.e.rng.getstate())
        before=self.resources(f)
        try:f.e.deliver_passive_event(event)
        except ValueError:pass
        self.assertEqual(self.resources(f),before)
        self.assertEqual(actual_hooks,expected_hooks,'completed replay cannot invoke the parent hook again')

    def test_saved_actual_counter_links_and_boundary_cannot_be_retargeted(self):
        f=self.gambit('counter');counter_event=self.pause(f)
        native=f.e._passive_events[counter_event]
        parent_event=native['taskmaster_gambit_parent']
        parent=f.e._passive_events[parent_event]
        parent_completion=parent['completion_id']
        baseline=json.loads(json.dumps(CODEC.dump_engine(f.e),ensure_ascii=False))
        CODEC.load_engine(f.e.r,deepcopy(baseline))  # Clean native pending graph is valid first.
        for field in ('counter_event','counter_completion','boundary'):
            with self.subTest(field=field):
                saved=deepcopy(baseline)
                rows=[node for node in saved['nodes'].values() if node['kind']=='dict'
                      and ['counter_event',counter_event] in node['items']
                      and any(pair[0]=='counter_completion' for pair in node['items'])]
                self.assertEqual(len(rows),1)
                if field=='boundary':
                    facts_ref=next(pair[1] for pair in rows[0]['items'] if pair[0]=='facts')
                    facts=saved['nodes'][facts_ref['$ref']]
                    boundary_ref=next(pair[1] for pair in facts['items'] if pair[0]=='boundary')
                    boundary=saved['nodes'][boundary_ref['$ref']]
                    self.assertEqual(boundary['kind'],'tuple')
                    boundary['items'][1]+=1  # Change only the retained native round scalar.
                else:
                    pair=next(pair for pair in rows[0]['items'] if pair[0]==field)
                    pair[1]=parent_event if field=='counter_event' else parent_completion
                with self.assertRaises(ValueError):Engine.import_state(f.e.r,saved)
                self.assertEqual(json.loads(json.dumps(CODEC.dump_engine(f.e),ensure_ascii=False)),baseline)


if __name__=='__main__':
    unittest.main()