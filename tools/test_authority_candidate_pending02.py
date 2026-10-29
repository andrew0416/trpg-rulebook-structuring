"""Source-audit candidate probes; runtime execution belongs to Root.

Correctness assertions compare real paid producers with uninterrupted controls.
A failing assertion confirms only its named invariant, not every branch in a
candidate family. No production code or native pending exception is patched.
"""
from copy import copy,deepcopy
from pathlib import Path
import json
import os
import sys
import unittest
from unittest.mock import patch

ROOT=Path(os.environ.get('PTK_EXPERIMENT_ROOT') or Path(__file__).resolve().parents[1]).resolve()
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from builder import build_pokemon,build_trainer
from grid import Grid
from native_scenario_fixture import prepare_body
from synthetic_rule_fixture import register_synthetic
from mechanize_feats import parse_frequency
import weapon_actions as WEAPONS
import world_entities as WORLD
import state_codec as CODEC
import frequency as FREQ
import action_points as AP
import turn as TURN
import items as ITEMS
import marksman as MARKSMAN
import taskmaster as TASK
import passive_events as PASSIVE
import move_defense_reactions as DEFENSE
# Existing fixture modules may prepend their own historical roots on import.
# Keep this probe's selected stage paths and supply private Rules to every fixture.
_fixture_paths=list(sys.path)
import test_book_taskmaster_hardened as TASK_FIX
import test_book_marksman_full as MARK_FIX
sys.path[:]=_fixture_paths
TASK_FIX.ROOT=ROOT
MARK_FIX.ROOT=ROOT


class CandidatePending02Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bases={name:Rules(ROOT,ruleset=name) for name in ('core','fantasy','all')}

    def private_rules(self,name):
        base=self.bases[name]
        rules=WEAPONS.private_restore_rules(base)
        rules.rulings=deepcopy(base.rulings)
        rules.feats_mech=dict(base.feats_mech)
        return rules

    def note(self,candidate,scenario,**facts):
        print('CANDIDATE_PROBE '+json.dumps(
            dict(candidate=candidate,scenario=scenario,**facts),ensure_ascii=False,sort_keys=True))

    def restore_actors(self,engine,*actors):
        identities=[actor.entity_id for actor in actors];rng=engine.rng.getstate()
        saved=json.loads(json.dumps(CODEC.dump_engine(engine),ensure_ascii=False))
        restored=CODEC.load_engine(engine.r,saved)
        self.assertEqual(restored.rng.getstate(),rng)
        self.assertIs(restored.rulings,restored.r.rulings)
        index=WORLD.actor_index(restored)
        return (restored,*(index[uid] for uid in identities))

    def known_detect(self,engine,actor):
        if DEFENSE.DETECT in actor.moves:return
        if len(actor.moves)>=6:
            removable=next(mid for mid in actor.moves if mid not in ('struggle','move/몸통박치기'))
            engine.gm.set_move(actor,removable,add=False,reason='observed known-Move sheet replaces an unused entry')
        engine.gm.set_move(actor,DEFENSE.DETECT,reason='actual known Detect for the native defense choice')

    def gambit(self,watch=None):
        f=TASK_FIX.TaskmasterTests('runTest');f.rules=self.private_rules('core')
        f.setup();f.gambit_features();f.e.death_enabled=False
        self.known_detect(f.e,f.p);self.known_detect(f.e,f.b)
        f.combat(f.b)
        f.answer('deadly_gambit',{'move':'struggle','roll_effects':False,'options':{'set_damage':True}})
        if watch is not None:
            reactor=f.p if watch=='incoming' else f.b
            f.e.watch_move_defense(reactor,[{'actor_id':reactor.entity_id,'source':DEFENSE.DETECT}],
                                  reason='actual optional Detect waits before native damage')
        return f

    def gambit_result(self,f):
        return {'pokemon_hp':f.p.hp,'foe_hp':f.b.hp,
                'incoming_uses':f.b.move_uses.get('move/몸통박치기',0),
                'counter_uses':f.p.move_uses.get('struggle',0),
                'gambit_uses':FREQ.state(f.a)['activations'].get(TASK.GAMBIT,{}).get('used',0),
                'incoming_standard':getattr(f.b,'_action_history',[]).count('standard')}

    def gambit_control(self):
        f=self.gambit();before=(f.p.hp,f.b.hp)
        with patch.object(Engine,'d20',side_effect=AssertionError('Gambit selected no effect roll')):
            f.e.use_move(f.b,f.p,'move/몸통박치기',set_damage=True)
        result=self.gambit_result(f)
        self.assertLess(f.p.hp,before[0]);self.assertLess(f.b.hp,before[1])
        self.assertEqual((result['incoming_uses'],result['counter_uses'],result['gambit_uses']),(1,1,1))
        return result

    def test_c02_gambit_uninterrupted_native_control(self):
        self.note('C02-001','uninterrupted',**self.gambit_control())

    def test_c02_gambit_incoming_defense_wait_matches_uninterrupted_paid_counter(self):
        expected=self.gambit_control()
        for cold in (False,True):
            with self.subTest(cold=cold):
                f=self.gambit('incoming')
                with patch.object(Engine,'d20',side_effect=AssertionError('Gambit accuracy is already automatic')):
                    with self.assertRaises(PASSIVE.PassiveEventPending):
                        f.e.use_move(f.b,f.p,'move/몸통박치기',set_damage=True)
                event=f.e._passive_pending
                self.assertIn(event,f.e._passive_events)
                self.assertEqual(FREQ.state(f.a)['activations'][TASK.GAMBIT]['used'],1)
                self.note('C02-001','incoming_wait_before_resume',cold=cold,event_id=event,
                          transient_gambit=getattr(f.e,'_taskmaster_gambit',None) is not None,
                          phase=f.e._passive_events[event]['phase'],paid=self.gambit_result(f))
                if cold:
                    f.e,f.a,f.p,f.q,f.b=self.restore_actors(f.e,f.a,f.p,f.q,f.b)
                with patch.object(Engine,'d20',side_effect=AssertionError('paid incoming accuracy must not reroll')):
                    f.e.choose_move_defense(event,f.p,use=False,reason='actual Detect declined')
                observed=self.gambit_result(f)
                self.note('C02-001','incoming_wait',cold=cold,expected=expected,observed=observed)
                self.assertEqual(observed,expected,'paid Gambit counter must survive an unrelated native defense wait')

    def test_c02_gambit_counter_defense_wait_keeps_both_parent_and_counter_hits(self):
        expected=self.gambit_control()
        for cold in (False,True):
            with self.subTest(cold=cold):
                f=self.gambit('counter')
                with patch.object(Engine,'d20',side_effect=AssertionError('Gambit accuracy is automatic')):
                    with self.assertRaises(PASSIVE.PassiveEventPending):
                        f.e.use_move(f.b,f.p,'move/몸통박치기',set_damage=True)
                event=f.e._passive_pending
                self.assertIs(f.e._passive_events[event]['actor'],f.p)
                self.assertIs(f.e._passive_events[event]['target'],f.b)
                self.note('C02-001','counter_wait_before_resume',cold=cold,event_id=event,
                          transient_gambit=getattr(f.e,'_taskmaster_gambit',None) is not None,
                          phase=f.e._passive_events[event]['phase'],paid=self.gambit_result(f))
                if cold:
                    f.e,f.a,f.p,f.q,f.b=self.restore_actors(f.e,f.a,f.p,f.q,f.b)
                with patch.object(Engine,'d20',side_effect=AssertionError('paid counter accuracy must not reroll')):
                    f.e.choose_move_defense(event,f.b,use=False,reason='actual counter-target Detect declined')
                observed=self.gambit_result(f)
                self.note('C02-001','counter_wait',cold=cold,expected=expected,observed=observed)
                self.assertEqual(observed,expected,'native counter wait must retain the already-paid incoming hit')

    def movement_world(self,*,overwatch):
        f=MARK_FIX.MarksmanFullTests('runTest');f.rules=self.private_rules('fantasy')
        f.base_rulings=deepcopy(f.rules.rulings)
        positions=((2,4),(12,9),(13,9)) if overwatch else ((6,3),(12,9),(13,9))
        f.scene(features=(MARKSMAN.WATCH,) if overwatch else (),positions=positions)
        mover=Combatant(f.rules,build_pokemon(f.rules,'화강돌',20,moves=[],abilities=[],
            extra={'trainer_id':f.b.entity_id,'tutor_points':6}))
        f.e.gm.add_combatant(mover,pos=(7,3),side='foe',reason='actual Spiritomb movement participant')
        prepare_body(f.e,mover,size=mover.spec['size'],offsets=[(0,0)],reason='actual complete Spiritomb body')
        f.e.gm.observe_loyalty(mover,6,reason='actual willing Pokemon')
        f.e.gm.set_movement_capabilities(mover,
            {'land':6,'sky':6,'levitate':6,'burrow':6,'teleport':6},basis='current',
            reason='explicit GM current capability observation for independent movement adapters')
        self.known_detect(f.e,mover)
        destination=(7,2) if overwatch else (7,1)
        WORLD.register_object(f.e,'candidate/stone',location={'kind':'grid','cell':destination},
                              reason='actual grounded Keystone')
        f.e.gm.observe_collected_keystone(f.b,'candidate/stone',reason='actual collected Keystone')
        f.e.link_keystone(mover,'candidate/stone',collector=f.b,reason='actual paid synchronization')
        if overwatch:
            f.weapon();f.combat()
            MARKSMAN.watch(f.e,f.a,f.key,direction=(1,0),blast_center=(7,4))
            f.e.end_of_turn(f.a);f.e.start_of_turn(mover,initiative_count=15)
            f.e.watch_move_defense(mover,[{'actor_id':f.c.entity_id,'source':DEFENSE.RANGED}],
                                  reason='actual Overwatch recipient defense wait')
            f.e.rulings.add_answer('marksman_overwatch',{'weapon_id':f.key,'move_id':f.mid},
                                  reason='actual equipped Overwatch attack selection')
        else:
            f.combat(mover)
            f.e.watch_move_defense(mover,[{'actor_id':mover.entity_id,'source':DEFENSE.DETECT}],
                                  reason='actual AoO recipient Detect wait')
        return f,mover,destination

    def transfer(self,engine,mover,destination,kind):
        if kind=='keystone':
            return engine.keystone_warp(mover,'candidate/stone',reason='actual selected linked destination')
        if kind=='aerial':
            return engine.aerial_move(mover,destination,mode='sky',altitude=1,
                gm_distance=3 if destination==(7,1) else 2,reason_text='GM measures actual mapped aerial distance')
        if kind=='teleport':
            return engine.teleport(mover,destination,surface_contact=True,reason_text='actual mapped surface transfer')
        path=[mover.pos]
        while path[-1]!=destination:path.append((path[-1][0],path[-1][1]-1))
        return engine.burrow_move(mover,path,diggable=True,surface=True,
                                  reason_text='GM confirms this actual continuous diggable path')

    def movement_payment(self,mover):
        return {'budget':deepcopy(mover.budget),'history':deepcopy(getattr(mover,'_action_history',[])),
                'tutor_points':mover.spec['tutor_points']}

    def test_c1_entry_overwatch_wait_survives_single_transfer_and_cold_attack_resume(self):
        for kind in ('keystone','aerial','teleport','burrow'):
            with self.subTest(kind=kind):
                f,mover,destination=self.movement_world(overwatch=True)
                points=mover.spec['tutor_points']
                with patch.object(Engine,'d20',return_value=18):
                    result=self.transfer(f.e,mover,destination,kind)
                event=f.e._passive_pending
                self.assertIsNotNone(event,'real entry Overwatch wait is required')
                self.assertIn(event,f.e._passive_events)
                self.assertEqual(mover.pos,destination)
                paid=self.movement_payment(mover)
                self.assertEqual(mover.spec['tutor_points'],points)
                self.note('03-C1','entry_wait',kind=kind,returned=repr(result),position=list(mover.pos),
                          registered_pending=True,history=paid['history'])
                f.e,f.a,f.b,f.c,mover=self.restore_actors(f.e,f.a,f.b,f.c,mover)
                with patch.object(Engine,'d20',side_effect=AssertionError('entry attack accuracy must not reroll')):
                    f.e.choose_move_defense(event,f.c,use=False,reason='actual entry-defense decline')
                self.assertIsNone(f.e._passive_pending)
                self.assertEqual(mover.pos,destination)
                self.assertEqual(self.movement_payment(mover),paid,
                    'a completed one-transfer prefix must not require a second movement payment')

    def test_c1_burrow_departure_retains_its_real_native_pending_event(self):
        f,mover,destination=self.movement_world(overwatch=False)
        before=self.movement_payment(mover);origin=mover.pos
        with patch.object(Engine,'d20',return_value=18):
            with self.assertRaises(PASSIVE.PassiveEventPending) as caught:
                self.transfer(f.e,mover,destination,'burrow')
        event=caught.exception.event_id
        self.note('03-C1','burrow_departure',event_id=event,pending=f.e._passive_pending,
                  event_exists=event in f.e._passive_events,origin=list(origin),position=list(mover.pos),
                  payment_before=before,payment_after=self.movement_payment(mover))
        self.assertEqual(f.e._passive_pending,event,'recognized native wait must remain live after outer movement transaction')
        self.assertIn(event,f.e._passive_events,'caller must never receive an orphan native event ID')
        self.assertEqual(mover.pos,origin)

    def test_c1_keystone_and_aerial_departure_have_a_paid_resume_after_defense_return(self):
        for kind in ('keystone','aerial'):
            with self.subTest(kind=kind):
                f,mover,destination=self.movement_world(overwatch=False)
                with patch.object(Engine,'d20',return_value=18):
                    with self.assertRaises(PASSIVE.PassiveEventPending) as caught:
                        self.transfer(f.e,mover,destination,kind)
                event=caught.exception.event_id
                self.assertIn(event,f.e._passive_events)
                paid=self.movement_payment(mover);origin=mover.pos
                self.note('03-C1','departure_before_resume',kind=kind,event_id=event,
                          position=list(origin),destination=list(destination),payment=paid)
                f.e,f.a,f.b,f.c,mover=self.restore_actors(f.e,f.a,f.b,f.c,mover)
                with patch.object(Engine,'d20',side_effect=AssertionError('departure accuracy is already paid')):
                    f.e.choose_move_defense(event,mover,use=False,reason='actual departure Detect decline')
                # Accept automatic continuation if implemented; otherwise re-enter
                # the same public command. A new source-specific resume API would
                # require this probe to be adapted, not declared a new game rule.
                retry=None
                if mover.pos!=destination:retry=self.transfer(f.e,mover,destination,kind)
                self.note('03-C1','departure_resume',kind=kind,origin=list(origin),position=list(mover.pos),
                          destination=list(destination),retry=repr(retry),payment=self.movement_payment(mover))
                self.assertEqual(mover.pos,destination,'paid movement has no retained public continuation after its actual reaction')
                self.assertEqual(self.movement_payment(mover),paid,'resuming a paid movement must not charge a second action')

    def test_c1_burrow_paid_departure_roundtrip_resumes_without_second_shift_or_accuracy(self):
        import movement_actions as MOVE
        f,mover,destination=self.movement_world(overwatch=False)
        with patch.object(Engine,'d20',return_value=18):
            with self.assertRaises(PASSIVE.PassiveEventPending) as caught:
                self.transfer(f.e,mover,destination,'burrow')
        event=caught.exception.event_id;paid=self.movement_payment(mover)
        self.assertIn(MOVE.COMMAND,mover.spec)
        f.e,f.a,f.b,f.c,mover=self.restore_actors(f.e,f.a,f.b,f.c,mover)
        with patch.object(Engine,'d20',side_effect=AssertionError('paid departure must not reroll')):
            f.e.choose_move_defense(event,mover,use=False,reason='finish actual departure defense')
            result=self.transfer(f.e,mover,destination,'burrow')
        self.assertTrue(result);self.assertEqual(mover.pos,destination)
        self.assertEqual(self.movement_payment(mover),paid)
        self.assertNotIn(MOVE.COMMAND,mover.spec)
        self.assertEqual(mover._action_history.count('shift'),1)
        self.assertTrue(f.e.validate_state()['valid'])

    def test_c1_pending_paid_command_rejects_changed_intent_then_other_action_and_time(self):
        f,mover,destination=self.movement_world(overwatch=False)
        with patch.object(Engine,'d20',return_value=18):
            with self.assertRaises(PASSIVE.PassiveEventPending) as caught:
                self.transfer(f.e,mover,destination,'aerial')
        event=caught.exception.event_id;before=f.e.export_state()
        with self.assertRaisesRegex(ValueError,'original paid'):
            self.transfer(f.e,mover,(8,1),'aerial')
        self.assertEqual(f.e.export_state(),before)
        with patch.object(Engine,'d20',side_effect=AssertionError('paid attack must not reroll')):
            f.e.choose_move_defense(event,mover,use=False,reason='finish actual departure defense')
        before=f.e.export_state()
        with self.assertRaisesRegex(ValueError,'paid movement'):
            TURN.spend(f.e,mover,'swift','unrelated action while movement unfinished')
        self.assertEqual(f.e.export_state(),before)
        with self.assertRaisesRegex(ValueError,'paid movement'):
            f.e.advance_time(1,[mover])
        self.assertEqual(f.e.export_state(),before)
        self.transfer(f.e,mover,destination,'aerial')
        self.assertEqual(mover.pos,destination)

    def test_c1_two_departure_opponents_resume_only_the_unfinished_opportunity_prefix(self):
        import hunter as HUNTER,movement_actions as MOVE
        f,mover,destination=self.movement_world(overwatch=False)
        extra=Combatant(f.rules,build_trainer(f.rules,'second actual opportunity attacker',20,
            dict.fromkeys(('hp','atk','def','spa','spd','spe'),20),moves=[],abilities=[]))
        f.e.gm.add_combatant(extra,pos=(8,3),side=f.a.side,reason='second actual adjacent departure opponent')
        prepare_body(f.e,extra,size='중형',offsets=[(0,0)],reason='actual second opportunity attacker body')
        with patch.object(Engine,'d20',return_value=18):
            with self.assertRaises(PASSIVE.PassiveEventPending) as caught:
                self.transfer(f.e,mover,destination,'aerial')
        event=caught.exception.event_id;paid=self.movement_payment(mover)
        prefix=mover.spec[MOVE.COMMAND]['progress']['opportunities']
        self.assertEqual(prefix['next'],1);self.assertEqual(len(prefix['actors']),2)
        f.e,f.a,f.b,f.c,mover,extra=self.restore_actors(f.e,f.a,f.b,f.c,mover,extra)
        with patch.object(Engine,'d20',side_effect=AssertionError('first opportunity already rolled')):
            f.e.choose_move_defense(event,mover,use=False,reason='finish first actual opportunity')
        with patch.object(Engine,'d20',return_value=18) as rolls:
            self.transfer(f.e,mover,destination,'aerial')
        self.assertEqual(rolls.call_count,1)
        self.assertEqual(HUNTER._opportunity_row(f.e,f.a)['used'],1)
        self.assertEqual(HUNTER._opportunity_row(f.e,extra)['used'],1)
        self.assertEqual(self.movement_payment(mover),paid)
        self.assertEqual(mover.pos,destination);self.assertNotIn(MOVE.COMMAND,mover.spec)

    def test_c1_saved_pending_movement_rejects_changed_plan_and_missing_native_event(self):
        import movement_actions as MOVE
        f,mover,destination=self.movement_world(overwatch=False)
        with patch.object(Engine,'d20',return_value=18):
            with self.assertRaises(PASSIVE.PassiveEventPending) as caught:
                self.transfer(f.e,mover,destination,'keystone')
        actual=deepcopy(mover.spec[MOVE.COMMAND])
        try:
            mover.spec[MOVE.COMMAND]['plan']['destination']=(8,1)
            with self.assertRaisesRegex(ValueError,'source, owner or boundary'):
                MOVE.validate_commands(f.e)
        finally:mover.spec[MOVE.COMMAND]=deepcopy(actual)
        event=f.e._passive_events.pop(caught.exception.event_id)
        try:
            with self.assertRaisesRegex(ValueError,'actual native event'):
                MOVE.validate_commands(f.e)
        finally:f.e._passive_events[event['id']]=event
        self.assertTrue(f.e.validate_state()['valid'])

    def completed_departure_wait(self,kind):
        f,mover,destination=self.movement_world(overwatch=False)
        with patch.object(Engine,'d20',return_value=18):
            with self.assertRaises(PASSIVE.PassiveEventPending) as caught:
                self.transfer(f.e,mover,destination,kind)
        with patch.object(Engine,'d20',side_effect=AssertionError('departure accuracy already observed')):
            f.e.choose_move_defense(caught.exception.event_id,mover,use=False,
                                   reason='complete actual defense before separate GM state change')
        self.assertIsNone(f.e._passive_pending)
        return f,mover,destination

    def test_c1_paid_resume_after_native_recall_cancels_without_refund_or_return_to_field(self):
        import movement_actions as MOVE
        for kind in ('burrow','aerial','keystone'):
            with self.subTest(kind=kind):
                f,mover,destination=self.completed_departure_wait(kind)
                origin=mover.pos;paid=self.movement_payment(mover)
                f.e.gm.recall(mover,reason='independent authorized recall after actual departure attack')
                self.assertFalse(mover.on_field)
                recalls=deepcopy(mover.spec.get('native_recall_history',[]))
                f.e,f.a,f.b,f.c,mover=self.restore_actors(f.e,f.a,f.b,f.c,mover)
                with patch.object(Engine,'d20',side_effect=AssertionError('cancelled movement must not roll')):
                    result=self.transfer(f.e,mover,destination,kind)
                self.assertIs(result,False)
                self.assertFalse(mover.on_field);self.assertEqual(mover.pos,origin)
                self.assertEqual(mover.spec.get('native_recall_history',[]),recalls)
                self.assertEqual(self.movement_payment(mover),paid)
                self.assertNotIn(MOVE.COMMAND,mover.spec)
                self.assertTrue(f.e.validate_state()['valid'])

    def test_c1_paid_resume_after_native_removal_cancels_without_reregistering_actor(self):
        import movement_actions as MOVE
        for kind in ('burrow','aerial','keystone'):
            with self.subTest(kind=kind):
                f,mover,destination=self.completed_departure_wait(kind)
                origin=mover.pos;paid=self.movement_payment(mover)
                f.e.gm.remove_combatant(mover,reason='independent authorized removal after actual departure attack')
                self.assertNotIn(mover,f.e.everyone);self.assertNotIn(mover,f.e.gm.everyone)
                # Completed attack/history references retain identity, not field availability.
                self.assertIs(WORLD.actor_index(f.e)[mover.entity_id],mover)
                with patch.object(Engine,'d20',side_effect=AssertionError('removed actor must not move')):
                    result=self.transfer(f.e,mover,destination,kind)
                self.assertIs(result,False);self.assertFalse(mover.on_field)
                self.assertNotIn(mover,f.e.everyone);self.assertNotIn(mover,f.e.gm.everyone)
                self.assertEqual(mover.pos,origin);self.assertEqual(self.movement_payment(mover),paid)
                self.assertNotIn(MOVE.COMMAND,mover.spec)
                self.assertTrue(f.e.validate_state()['valid'])

    def test_c1_paid_resume_captured_state_boundary_cancels_and_preserves_external_state(self):
        """Trusted completed-state observation; this is not capture-flow certification."""
        import state_grants as G,movement_actions as MOVE
        for kind in ('burrow','aerial','keystone'):
            with self.subTest(kind=kind):
                f,mover,destination=self.completed_departure_wait(kind)
                origin=deepcopy(mover.location);paid=self.movement_payment(mover)
                def observe_capture(staged,actor):
                    before={'captured':actor.captured,'on_field':actor.on_field}
                    actor.captured=True;actor.on_field=False
                    staged.gm._rec('captured state observation',before,
                        {'captured':True,'on_field':False},
                        'trusted completed captured-state boundary; no capture payment or success asserted',actor)
                G.transition(f.e,mover,observe_capture)
                f.e,f.a,f.b,f.c,mover=self.restore_actors(f.e,f.a,f.b,f.c,mover)
                with patch.object(Engine,'d20',side_effect=AssertionError('captured actor must not move')):
                    result=self.transfer(f.e,mover,destination,kind)
                self.assertIs(result,False);self.assertTrue(mover.captured);self.assertFalse(mover.on_field)
                self.assertEqual(mover.location,origin);self.assertEqual(self.movement_payment(mover),paid)
                self.assertNotIn(MOVE.COMMAND,mover.spec)
                self.assertTrue(f.e.validate_state()['valid'])

    def test_c1_removed_actor_copy_cannot_present_another_objects_paid_command(self):
        import movement_actions as MOVE
        f,mover,destination=self.completed_departure_wait('aerial')
        f.e.gm.remove_combatant(mover,reason='actual actor removed before stale-copy request')
        stale=copy(mover);stale.spec=deepcopy(mover.spec)
        before=f.e.export_state();paid=self.movement_payment(mover)
        with self.assertRaisesRegex(ValueError,'actual registered'):
            self.transfer(f.e,stale,destination,'aerial')
        self.assertEqual(f.e.export_state(),before)
        self.assertEqual(self.movement_payment(mover),paid)
        self.assertIn(MOVE.COMMAND,mover.spec)
        self.assertIs(self.transfer(f.e,mover,destination,'aerial'),False)
        self.assertNotIn(MOVE.COMMAND,mover.spec);self.assertNotIn(mover,f.e.everyone)

    def compound_world(self):
        rules=self.private_rules('all');uid='feat/ap-audit'
        register_synthetic(rules,uid,name='Synthetic AP state fixture',kind='test_fixture')
        rules.feats_mech[uid]={'name':'ap-audit','coverage':'full',
            'header':{'frequency':parse_frequency('2 AP - 기본 행동 + 신속 행동')},
            'effects':[{'type':'cost','ap':2},{'type':'injury','value':1,'target':'target'}]}
        engine=Engine(rules,17)
        actors=[]
        for name in ('compound owner','compound target'):
            spec=build_trainer(rules,name,20,dict.fromkeys(('hp','atk','def','spa','spd','spe'),20),
                moves=[],abilities=[],extra={'classes':[],'edges':[],'feats':[uid] if not actors else []})
            actor=Combatant(rules,spec);engine.gm.add_combatant(actor,reason='actual authored feature participant')
            actors.append(actor)
        actor,target=actors;ITEMS.register_feats(engine,actor)
        engine.start_round(actors);engine.start_of_turn(actor,initiative_count=20)
        return engine,actor,target,uid

    def close_compound_combat(self,engine,actor):
        engine.end_of_turn(actor)
        engine.end_encounter(round_elapsed_seconds=10)
        self.assertFalse(engine.encounter_active)
        self.assertIsNone(engine._active_turn_actor)

    def test_c2_scalar_outside_action_ignores_actual_exhausted_combat_budget_control(self):
        engine,actor,target,uid=self.compound_world()
        result=engine.manual_feat(actor,uid,target)
        self.assertGreater(result[0],0)
        self.close_compound_combat(engine,actor)
        budget=deepcopy(actor.budget)
        self.assertEqual((budget['standard'],budget['swift']),(0,0))
        self.assertTrue(TURN.spend(engine,actor,'standard','outside scalar action control'))
        self.assertEqual(actor.budget,budget)

    def test_c2_registered_compound_outside_effect_is_independent_of_stale_combat_tokens(self):
        for spent in (False,True):
            with self.subTest(combat_compound_spent=spent):
                engine,actor,target,uid=self.compound_world()
                if spent:self.assertGreater(engine.manual_feat(actor,uid,target)[0],0)
                self.close_compound_combat(engine,actor)
                before=(target.injuries,AP.available(actor),engine.rng.getstate())
                result=engine.manual_feat(actor,uid,target)
                self.note('03-C2','outside_compound',spent=spent,result=list(result),
                          injuries_before=before[0],injuries_after=target.injuries,
                          ap_before=before[1],ap_after=AP.available(actor),budget=actor.budget)
                self.assertEqual(target.injuries,before[0]+1,
                    'outside compound admission must not depend on leftover per-turn combat tokens')
                self.assertEqual(AP.available(actor),before[1]-2)
                self.assertEqual(engine.rng.getstate(),before[2])


if __name__=='__main__':
    unittest.main()
