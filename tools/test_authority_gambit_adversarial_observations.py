"""One additional native counterexample beyond gambit-controls01.

The source snapshot being reviewed is preserved in adversarial-review01.
Root supplies the composed runtime for execution; no gameplay producer is mocked.
"""
from pathlib import Path
from hashlib import sha256
import os
import sys
import unittest
from unittest.mock import patch

ROOT=Path(os.environ.get('PTK_EXPERIMENT_ROOT') or Path(__file__).resolve().parents[1]).resolve()
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_authority_candidate_pending02 as PROBE
from engine import Engine
import attack_damage_history as DAMAGE_HISTORY
import passive_events as PASSIVE
import frequency as FREQ
import taskmaster as TASK


class GambitAdversarialObservations(unittest.TestCase):
    setUpClass=classmethod(PROBE.CandidatePending02Tests.setUpClass.__func__)
    private_rules=PROBE.CandidatePending02Tests.private_rules
    known_detect=PROBE.CandidatePending02Tests.known_detect
    gambit=PROBE.CandidatePending02Tests.gambit
    restore_actors=PROBE.CandidatePending02Tests.restore_actors

    def test_draining_counter_cannot_relabel_original_attack_hp_loss_as_damage_minus_heal(self):
        for counter in ('struggle','move/흡수'):
            with self.subTest(counter=counter):
                f=self.gambit()
                if counter!='struggle':
                    f.e.gm.set_move(f.p,'move/자폭',add=False,reason='replace an unused known Move in the actual sheet')
                    f.e.gm.set_move(f.p,counter,reason='actual learned single-target draining counter')
                    self.assertIn(counter,f.p.moves)
                f.e.gm.set_hp(f.p,value=120,reason='actual injured HP leaves room for the native draining counter')
                f.answer('deadly_gambit',{'move':counter,'roll_effects':False,'options':{'set_damage':True}})
                first=len(DAMAGE_HISTORY.records(f.p))
                with patch.object(Engine,'d20',side_effect=AssertionError('selected automatic accuracy does not draw a d20')):
                    f.e.use_move(f.b,f.p,'move/몸통박치기',set_damage=True)
                rows=[row for row in DAMAGE_HISTORY.records(f.p)[first:]
                      if row['attacker_id']==f.b.entity_id and row['receipt']['source']=='move/몸통박치기']
                self.assertEqual(len(rows),1)
                receipt=rows[0]['receipt']
                events=[event_id for event_id,event in f.e._passive_events.items()
                        if event['actor'] is f.b and event['target'] is f.p
                        and event['move_id']=='move/몸통박치기' and event['producer']=='Engine.use_move']
                self.assertEqual(len(events),1)
                trace=f.e.event_trace(events[0])
                facts=[row['facts'] for row in trace['observations'] if row['stage']=='hp_loss']
                self.assertEqual(len(facts),1)
                self.assertEqual(facts[0]['damage_basis'],'direct_attack_primitive_resource_delta')
                if counter!='struggle':
                    self.assertGreater(f.p.hp,receipt['after']['hp'],
                        'fixture must actually heal from the native counter after both hit receipts')
                self.assertEqual(facts[0]['real_hp_loss'],receipt['net_hp_loss'],
                    'parent attack event must expose its native hit loss, excluding later counter healing')
                self.assertEqual(facts[0]['temp_hp_loss'],receipt['net_temporary_hp_loss'])

    def miss_listener(self,f):
        source='input/'+f.e.r.selection.units['combat/struggle']['source']['file']
        document={'schema':1,'id':'event/gambit-adversarial-missed-counter','variants':[{
            'rule_id':'combat/struggle',
            'source':{'file':source,'sha256':sha256((Path(f.e.r.root)/source).read_bytes()).hexdigest()},
            'inputs':{'hit':{'authority':'context','type':'boolean','question':'Actual native accuracy'},
                      'choice':{'authority':'gm','type':'boolean','question':'Explicit authored missed-action decision'}},
            'when':{'op':'eq','left':{'$input':'hit'},'right':False},
            'values':{'effects':[{'type':'stage_change','stat':'atk','delta':1,'target':'self'}]}}]}
        return f.e.subscribe_source_policy(f.p,'gambit-adversarial-miss',document,
            event='move_resolved',inputs={'hit':'hit'})

    def test_avoided_counter_listener_wait_uses_actual_return_phase_without_replaying_paid_prefix(self):
        # Supported normal control: an actual ordinary miss with this same
        # explicit host-authored listener. This is not a new printed PTU rule.
        f=self.gambit();listener=self.miss_listener(f)
        f.e.end_of_turn(f.b);f.e.start_of_turn(f.p,initiative_count=10)
        before=(f.p.hp,f.b.hp)
        with patch.object(Engine,'d20',return_value=1):
            with self.assertRaises(PASSIVE.PassiveEventPending):
                f.e.use_move(f.p,f.b,'struggle',set_damage=True)
        event=f.e._passive_pending
        self.assertEqual(f.e._passive_events[event]['phase'],'producer_return_boundary')
        f.e.choose_passive_event(event,f.p,listener,
            {'decisions':{'choice':{'value':True,'reason':'actual authored missed-action choice'}}})
        self.assertEqual((f.p.hp,f.b.hp),before)
        self.assertEqual(f.p.stages['atk'],1);self.assertEqual(f.p.move_uses['struggle'],1)
        self.assertIsNone(f.e._passive_pending)

        f=self.gambit('counter');listener=self.miss_listener(f)
        before=(f.p.hp,f.b.hp)
        with patch.object(Engine,'d20',side_effect=AssertionError('Gambit accuracy is automatic')):
            with self.assertRaises(PASSIVE.PassiveEventPending):
                f.e.use_move(f.b,f.p,'move/몸통박치기',set_damage=True)
        counter=f.e._passive_pending
        with patch.object(Engine,'d20',side_effect=AssertionError('native Detect uses its real automatic accuracy')):
            with self.assertRaises(PASSIVE.PassiveEventPending):
                f.e.choose_move_defense(counter,f.b,use=True,reason='actual learned Detect avoids counter')
        event=f.e._passive_pending
        self.assertIs(f.e._passive_events[event]['actor'],f.p)
        self.assertEqual(f.e._passive_events[event]['phase'],'producer_return_boundary')
        self.assertEqual((f.p.hp,f.b.hp),before)
        trace=f.e.event_trace(event)
        self.assertTrue(any(row['stage']=='accuracy' and row['facts']['hit'] is False for row in trace['observations']))
        f.e,f.a,f.p,f.q,f.b=self.restore_actors(f.e,f.a,f.p,f.q,f.b)
        paid=(f.b.move_uses['move/몸통박치기'],f.p.move_uses['struggle'],
              FREQ.state(f.a)['activations'][TASK.GAMBIT]['used'],len(f.b._action_history),f.e.rng.getstate())
        with patch.object(Engine,'d20',side_effect=AssertionError('retained counter listener must not reroll either attack')):
            f.e.choose_passive_event(event,f.p,listener,
                {'decisions':{'choice':{'value':True,'reason':'actual retained missed-counter listener decision'}}})
        self.assertIsNone(f.e._passive_pending)
        self.assertLess(f.p.hp,before[0]);self.assertEqual(f.b.hp,before[1])
        self.assertEqual(f.p.stages['atk'],1)
        self.assertEqual((f.b.move_uses['move/몸통박치기'],f.p.move_uses['struggle'],
            FREQ.state(f.a)['activations'][TASK.GAMBIT]['used'],len(f.b._action_history),f.e.rng.getstate()),paid)

if __name__=='__main__':
    unittest.main()