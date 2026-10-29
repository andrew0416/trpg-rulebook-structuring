"""Native remaining Gambit frontier probes; no runtime patch or synthetic pending.

Root runs these against a composed stage. Authored listener is an explicit host
extension, not a claim that printed Detect grants an extra Stat stage.
"""
from hashlib import sha256
from pathlib import Path
import os
import sys
import unittest
from unittest.mock import patch
ROOT=Path(os.environ.get('PTK_EXPERIMENT_ROOT') or Path(__file__).resolve().parents[1]).resolve()
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_authority_candidate_pending02 as PROBE
from engine import Engine
import passive_events as P
import move_defense_reactions as D
import heavy_injury_adapter as H
import frequency as F
import taskmaster as T
import taskmaster_gambit as G


class GambitNativeFrontiers(unittest.TestCase):
    setUpClass=classmethod(PROBE.CandidatePending02Tests.setUpClass.__func__)
    private_rules=PROBE.CandidatePending02Tests.private_rules
    known_detect=PROBE.CandidatePending02Tests.known_detect
    gambit=PROBE.CandidatePending02Tests.gambit
    gambit_result=PROBE.CandidatePending02Tests.gambit_result
    gambit_control=PROBE.CandidatePending02Tests.gambit_control
    restore_actors=PROBE.CandidatePending02Tests.restore_actors

    def cold(self,f):
        f.e,f.a,f.p,f.q,f.b=self.restore_actors(f.e,f.a,f.p,f.q,f.b)

    def pause_counter(self,f):
        with patch.object(Engine,'d20',side_effect=AssertionError('Gambit selected automatic accuracy')):
            with self.assertRaises(P.PassiveEventPending):
                f.e.use_move(f.b,f.p,'move/몸통박치기',set_damage=True)
        event=f.e._passive_pending
        self.assertIs(f.e._passive_events[event]['actor'],f.p)
        return event

    def detect_listener(self,f):
        source='input/'+f.e.r.selection.units['combat/struggle']['source']['file']
        document={'schema':1,'id':'event/gambit-foreign-detect','variants':[{
            'rule_id':'combat/struggle',
            'source':{'file':source,'sha256':sha256((Path(f.e.r.root)/source).read_bytes()).hexdigest()},
            'inputs':{'move':{'authority':'context','type':'string','question':'Actual native Move'},
                      'choice':{'authority':'gm','type':'boolean','question':'Explicit host-authored Detect return choice'}},
            'when':{'op':'eq','left':{'$input':'move'},'right':D.DETECT},
            'values':{'effects':[{'type':'stage_change','stat':'spd','delta':1,'target':'self'}]}}]}
        return f.e.subscribe_source_policy(f.b,'gambit-foreign-detect',document,
            event='move_resolved',inputs={'move':'move_id'})

    def choose_detect_listener(self,f,event,listener):
        return f.e.choose_passive_event(event,f.b,listener,
            {'decisions':{'choice':{'value':True,'reason':'actual host-authored Detect completion decision'}}})

    def test_foreign_native_detect_listener_returns_to_both_paid_attacks(self):
        # Positive control: the exact selected native Detect listener can finish.
        f=self.gambit();listener=self.detect_listener(f)
        with self.assertRaises(P.PassiveEventPending):
            f.e.use_move_on(f.b,f.b,D.DETECT,f.e.everyone)
        event=f.e._passive_pending
        self.assertEqual(f.e._passive_events[event]['move_id'],D.DETECT)
        self.choose_detect_listener(f,event,listener)
        self.assertIsNone(f.e._passive_pending);self.assertEqual(f.b.stages['spd'],1)
        expected=self.gambit_control()
        for cold in (False,True):
            with self.subTest(cold=cold):
                f=self.gambit('counter');listener=self.detect_listener(f)
                before=(f.p.hp,f.b.hp);counter=self.pause_counter(f)
                with self.assertRaises(P.PassiveEventPending):
                    f.e.choose_move_defense(counter,f.b,use=True,reason='actual native Detect with its own completion listener')
                event=f.e._passive_pending;actual=f.e._passive_events[event]
                self.assertEqual(actual['move_id'],D.DETECT)
                self.assertIs(actual['actor'],f.b);self.assertIs(actual['target'],f.b)
                self.assertNotEqual(actual['completion_id'],f.e._passive_events[counter]['completion_id'])
                self.assertEqual((f.p.hp,f.b.hp),before)
                if cold:self.cold(f)
                paid=(f.b.move_uses['move/몸통박치기'],f.p.move_uses['struggle'],
                      f.b.move_uses[D.DETECT],F.state(f.a)['activations'][T.GAMBIT]['used'],f.e.rng.getstate())
                with patch.object(Engine,'d20',side_effect=AssertionError('paid nested attacks cannot reroll')):
                    try:self.choose_detect_listener(f,event,listener)
                    except P.PassiveEventPending as pending:
                        self.assertEqual(pending.event_id,counter)
                    # Publicly drive the actual known caller if it was retained;
                    # completed native delivery must be inert if auto-finished.
                    f.e.deliver_passive_event(counter)
                self.assertIsNone(f.e._passive_pending)
                self.assertEqual(f.p.hp,expected['pokemon_hp']);self.assertEqual(f.b.hp,before[1])
                self.assertEqual(f.b.stages['spd'],1)
                self.assertEqual((f.b.move_uses['move/몸통박치기'],f.p.move_uses['struggle'],
                    f.b.move_uses[D.DETECT],F.state(f.a)['activations'][T.GAMBIT]['used'],f.e.rng.getstate()),paid)

    def test_late_gm_faint_cancels_parent_but_does_not_orphan_paid_counter(self):
        # Existing native control: GM-fainting a target does not cancel the
        # conscious attacker's already-paid attack waiting for that target.
        f=self.gambit();f.e.end_of_turn(f.b);f.e.start_of_turn(f.p,initiative_count=10)
        f.e.watch_move_defense(f.b,[{'actor_id':f.b.entity_id,'source':D.DETECT}],reason='actual target defense boundary')
        with patch.object(Engine,'d20',return_value=20):
            with self.assertRaises(P.PassiveEventPending):f.e.use_move(f.p,f.b,'struggle',set_damage=True)
        event=f.e._passive_pending;f.e.gm.faint(f.b,reason='independent GM target faint during paid attack')
        f.e.choose_move_defense(event,f.b,use=False,
            reason='explicitly decline the queued defense after independent GM target faint')
        self.assertIsNone(f.e._passive_pending);self.assertLess(f.b.hp,0)
        self.assertEqual(f.p.move_uses['struggle'],1)
        for cold in (False,True):
            with self.subTest(cold=cold):
                f=self.gambit('counter');before=f.p.hp;counter=self.pause_counter(f)
                if cold:self.cold(f)
                f.e.gm.faint(f.b,reason='independent GM faint of original attacker after counter was paid')
                paid=(f.b.move_uses['move/몸통박치기'],f.p.move_uses['struggle'],F.state(f.a)['activations'][T.GAMBIT]['used'])
                with patch.object(Engine,'d20',side_effect=AssertionError('both attacks already paid their accuracy')):
                    f.e.choose_move_defense(counter,f.b,use=False,
                        reason='same explicit queued-defense decline after independent GM faint')
                self.assertIsNone(f.e._passive_pending)
                self.assertEqual(f.p.hp,before,'cancelled original attack cannot apply incoming HP loss')
                original=f.e._passive_events[f.e._passive_events[counter][G.LINK]]
                observations=P.observations(f.e,original['id'])
                self.assertEqual([row['stage'] for row in observations],
                                 ['attempt','accuracy','damage_request','cancelled','resolved'])
                self.assertEqual(observations[-2]['facts'],{
                    'reason':'actor_no_longer_eligible',
                    'damage_request':observations[-3]['facts']['amount']})
                self.assertGreater(observations[-2]['facts']['damage_request'],0)
                self.assertIsNone(original['attack_observation'])
                self.assertIsNone(original['real_hp_loss']);self.assertIsNone(original['temp_hp_loss'])
                self.assertLess(f.b.hp,0,'actual still-eligible paid counter follows the native control')
                self.assertEqual((f.b.move_uses['move/몸통박치기'],f.p.move_uses['struggle'],F.state(f.a)['activations'][T.GAMBIT]['used']),paid)

    def test_cancelled_parent_does_not_force_its_now_ineligible_paid_counter(self):
        for cold in (False,True):
            with self.subTest(cold=cold):
                f=self.gambit('counter');counter=self.pause_counter(f)
                f.e.gm.faint(f.b,reason='original attacker independently faints after counter payment')
                f.e.gm.faint(f.p,reason='paid counter attacker independently faints too')
                if cold:self.cold(f)
                paid=(f.b.move_uses['move/몸통박치기'],f.p.move_uses['struggle'],
                      F.state(f.a)['activations'][T.GAMBIT]['used'],f.e.rng.getstate())
                with patch.object(Engine,'d20',side_effect=AssertionError('cancelled paid attacks cannot reroll')):
                    f.e.choose_move_defense(counter,f.b,use=False,reason='decline actual queued defense')
                self.assertIsNone(f.e._passive_pending)
                self.assertEqual((f.p.hp,f.b.hp),(0,0))
                original=f.e._passive_events[f.e._passive_events[counter][G.LINK]]
                for event in (original,f.e._passive_events[counter]):
                    result=f.e._move_completions[event['completion_id']]['results'][event['target'].entity_id]
                    self.assertTrue(result['cancelled']);self.assertEqual(result['dealt'],0)
                self.assertTrue(original[G.KEY]['done']);self.assertIsNone(original[G.KEY]['wait'])
                self.assertEqual((f.b.move_uses['move/몸통박치기'],f.p.move_uses['struggle'],
                    F.state(f.a)['activations'][T.GAMBIT]['used'],f.e.rng.getstate()),paid)

    def test_actual_legacy_cancelled_parent_wait_resumes_paid_counter_once_after_restore(self):
        # Reproduce the former cancellation adapter only after real native
        # cancellation. No event, paid counter, target result or receipt is invented.
        def retain_old_wait(e,original):
            row=G.checked(e,original)
            self.assertTrue(G._native_cancelled(e,original))
            identity=row['wait']['event_id']
            row['wait']={'event_id':identity,'phase':'external'};G._seal(row)
            e._passive_pending=identity
            raise P.PassiveEventPending(identity)
        for cold in (False,True):
            with self.subTest(cold=cold):
                f=self.gambit('counter');before=f.p.hp;counter=self.pause_counter(f)
                f.e.gm.faint(f.b,reason='actual original attacker faint after counter payment')
                with patch.object(G,'_resume_cancelled_counter',side_effect=retain_old_wait):
                    with self.assertRaises(P.PassiveEventPending):
                        f.e.choose_move_defense(counter,f.b,use=False,reason='decline before old adapter retains counter')
                original_id=f.e._passive_events[counter][G.LINK]
                self.assertEqual(f.e._passive_events[original_id][G.KEY]['wait']['phase'],'external')
                if cold:self.cold(f)
                self.assertEqual(f.e._passive_events[original_id][G.KEY]['wait']['phase'],'external')
                paid=(f.b.move_uses['move/몸통박치기'],f.p.move_uses['struggle'],
                      F.state(f.a)['activations'][T.GAMBIT]['used'],f.e.rng.getstate())
                with patch.object(Engine,'d20',side_effect=AssertionError('legacy paid counter cannot reroll')):
                    f.e.deliver_passive_event(counter)
                self.assertIsNone(f.e._passive_pending)
                self.assertEqual(f.p.hp,before);self.assertLess(f.b.hp,0)
                original=f.e._passive_events[original_id]
                self.assertTrue(original[G.KEY]['done']);self.assertIsNone(original[G.KEY]['wait'])
                self.assertEqual((f.b.move_uses['move/몸통박치기'],f.p.move_uses['struggle'],
                    F.state(f.a)['activations'][T.GAMBIT]['used'],f.e.rng.getstate()),paid)
                observed=(f.p.hp,f.b.hp,dict(f.p.move_uses),dict(f.b.move_uses),
                          F.state(f.a)['activations'][T.GAMBIT]['used'],f.e.rng.getstate())
                f.e.deliver_passive_event(counter)
                self.assertEqual((f.p.hp,f.b.hp,f.p.move_uses,f.b.move_uses,
                    F.state(f.a)['activations'][T.GAMBIT]['used'],f.e.rng.getstate()),observed)

    def test_cancelled_parent_counter_heavy_preserves_actual_observation_and_unfinished_wait(self):
        f=self.gambit('counter');before=f.p.hp;counter=self.pause_counter(f)
        self.assertIsNone(T.active(f.b))
        f.e.gm.set_injuries(f.b,value=5,reason='actual paid counter recipient has unresolved Heavy injury order')
        f.e.gm.faint(f.b,reason='original attacker faints before actual counter continuation')
        paid=(f.b.move_uses['move/몸통박치기'],f.p.move_uses['struggle'],
              F.state(f.a)['activations'][T.GAMBIT]['used'],f.e.rng.getstate())
        with patch.object(Engine,'d20',side_effect=AssertionError('paid counter accuracy cannot reroll')):
            with self.assertRaises(H.HeavyPending):
                f.e.choose_move_defense(counter,f.b,use=False,reason='decline actual queued defense')
        event=f.e._heavy_events[f.e._heavy_pending]
        self.assertIs(event['attacker'],f.p);self.assertIs(event['target'],f.b)
        self.assertFalse(event['continuation_reified']);self.assertEqual(event['status'],'pending')
        self.assertEqual(f.p.hp,before);self.assertLess(f.b.hp,0)
        original=f.e._passive_events[f.e._passive_events[counter][G.LINK]]
        self.assertTrue(G._native_cancelled(f.e,original));self.assertFalse(original[G.KEY]['done'])
        self.assertEqual(original[G.KEY]['wait'],{'event_id':counter,'phase':'parent_cancelled'})
        self.assertEqual((f.b.move_uses['move/몸통박치기'],f.p.move_uses['struggle'],
            F.state(f.a)['activations'][T.GAMBIT]['used'],f.e.rng.getstate()),paid)

    def test_cancelled_parent_moxie_listener_keeps_real_counter_and_cold_pending_tail(self):
        for cold in (False,True):
            with self.subTest(cold=cold):
                f=PROBE.TASK_FIX.TaskmasterTests('runTest');f.rules=self.private_rules('core')
                f.setup();f.gambit_features();f.e.death_enabled=False
                f.e.gm.remove_combatant(f.b,reason='use a distinct actual Pokemon Moxie source fixture')
                f.b=PROBE.Combatant(f.rules,dict(name='actual Moxie Pokemon',kind='pokemon',level=20,
                    stats={'hp':60,'atk':10,'def':5,'spa':10,'spd':5,'spe':10},
                    moves=['move/몸통박치기',D.DETECT],abilities=['자기과신'],
                    types=['땅','악'],movement={'land':6,'swim':0,'sky':0},size='중형'))
                f.e.gm.add_combatant(f.b,pos=(2,1),side='foe',reason='actual native Pokemon listener owner')
                PROBE.prepare_body(f.e,f.b,size='중형',offsets=[(0,0)],reason='observed complete listener body')
                self.known_detect(f.e,f.p);f.combat(f.b)
                f.answer('deadly_gambit',{'move':'struggle','roll_effects':False,'options':{'set_damage':True}})
                f.e.watch_move_defense(f.b,[{'actor_id':f.b.entity_id,'source':D.DETECT}],
                    reason='actual counter defense before native damage')
                counter=self.pause_counter(f);original_id=f.e._passive_events[counter][G.LINK]
                self.assertIn('ability/자기과신',f.e._passive_events[original_id]['source_ids'])
                before=f.p.hp
                f.e.gm.faint(f.b,reason='independent original Pokemon faint after actual counter payment')
                paid=(f.b.move_uses['move/몸통박치기'],f.p.move_uses['struggle'],
                      F.state(f.a)['activations'][T.GAMBIT]['used'],f.e.rng.getstate())
                with self.assertRaises(P.PassiveEventPending) as stopped:
                    f.e.choose_move_defense(counter,f.b,use=False,reason='actual queued defense decline')
                self.assertEqual(stopped.exception.event_id,original_id)
                original=f.e._passive_events[original_id]
                self.assertEqual(original['reason'],'owner_state_changed_during_move_order_unresolved')
                self.assertEqual(original['continuation']['kind'],'recipient_return')
                self.assertTrue(original['continuation']['result']['cancelled'])
                completion=f.e._move_completions[original['completion_id']]
                self.assertTrue(completion['results'][f.p.entity_id]['cancelled'])
                self.assertEqual(completion['results'][f.p.entity_id]['dealt'],0)
                self.assertNotEqual(completion['phase'],'complete')
                self.assertNotIn(original_id,completion.get('native_returns',{}))
                self.assertFalse(original[G.KEY]['done'])
                self.assertEqual(original[G.KEY]['counter_event'],counter)
                self.assertEqual((f.p.hp,f.b.hp,f.b.stages['atk']),(before,0,0))
                report=f.e.validate_state();self.assertTrue(report['valid'],report)
                if cold:self.cold(f)
                with self.assertRaises(P.PassiveEventPending) as repeated:
                    f.e.deliver_passive_event(original_id)
                self.assertEqual(repeated.exception.event_id,original_id)
                original=f.e._passive_events[original_id]
                self.assertTrue(original['continuation']['result']['cancelled'])
                self.assertFalse(original[G.KEY]['done'])
                self.assertEqual((f.p.hp,f.b.hp,f.b.stages['atk']),(before,0,0))
                self.assertEqual((f.b.move_uses['move/몸통박치기'],f.p.move_uses['struggle'],
                    F.state(f.a)['activations'][T.GAMBIT]['used'],f.e.rng.getstate()),paid)
                report=f.e.validate_state();self.assertTrue(report['valid'],report)

    def test_heavy_pair_preserves_original_hit_and_explicit_external_disposition(self):
        for cold in (False,True):
            with self.subTest(cold=cold):
                f=self.gambit();self.assertIsNone(T.active(f.p))
                f.e.gm.set_injuries(f.p,value=5,reason='actual unhardened recipient has five injuries')
                before=(f.p.hp,f.b.hp)
                with patch.object(Engine,'d20',side_effect=AssertionError('Gambit accuracy remains automatic')):
                    with self.assertRaises(H.HeavyPending):f.e.use_move(f.b,f.p,'move/몸통박치기',set_damage=True)
                event=f.e._heavy_pending;packet=f.e._heavy_events[event]
                self.assertIs(packet['attacker'],f.b);self.assertIs(packet['target'],f.p)
                self.assertLess(f.p.hp,before[0]);self.assertEqual(f.b.hp,before[1])
                self.assertFalse(packet['continuation_reified'])
                self.assertIn('paired hit',packet['unexecuted_remainder'])
                self.assertIn('production_effect_interactions_not_proven',packet['issues'])
                paid=(f.b.move_uses['move/몸통박치기'],f.p.move_uses['struggle'],F.state(f.a)['activations'][T.GAMBIT]['used'])
                self.assertEqual(paid,(1,1,1))
                if cold:self.cold(f)
                observed=(f.p.hp,f.b.hp,f.e.rng.getstate())
                receipt=H.acknowledge_ruling(f.e,event,f.p,expected_current_state=H.observe(f.p),
                    ruling='explicit external Heavy adjudication preserves observed attack HP',
                    disposition=H.ContinuationDisposition.CANCELLED_BY_RULING,
                    continuation_reason='GM explicitly cancels the unexecuted counter hit and both caller tails; no automatic replay')
                self.assertFalse(receipt['source_conformance_proven']);self.assertIsNone(f.e._heavy_pending)
                self.assertEqual((f.p.hp,f.b.hp,f.e.rng.getstate()),observed)
                self.assertEqual((f.b.move_uses['move/몸통박치기'],f.p.move_uses['struggle'],F.state(f.a)['activations'][T.GAMBIT]['used']),paid)

if __name__=='__main__':unittest.main()