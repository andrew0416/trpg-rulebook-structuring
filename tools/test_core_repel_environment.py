"""Repels cross actual stock, nearby admission, native accuracy and retreat."""
from copy import deepcopy
from pathlib import Path
import json
import unittest
from unittest.mock import patch

import test_category2_body_modes as fixture
import test_category2_medicine_stock as stock_fixture
from engine import Engine,Rules
import common_checks as C
import consumption_execution as PAID
import encounter
import movement_actions as MOVE
import relative_movement as RELATIVE
import repels as R
import campaign_rewards as REWARDS
import state_codec as CODEC

ROOT=Path(__file__).resolve().parents[1]


class RepelEnvironmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.r=Rules(ROOT,ruleset='core')
    add=fixture.Tests.add
    pokemon=fixture.Tests.pokemon
    begin=fixture.Tests.begin
    held=stock_fixture.MedicineStockTests.held

    def setUp(self):
        fixture.Tests.setUp(self)
        self.a.spec['items']={source:5 for source in R.SOURCES}
        self.t.spec.pop('trainer_id',None);self.t.spec['wild']=True;self.t.side='wild'
        MOVE.set_capabilities(self.e,self.t,{'land':4,'swim':0},basis='current',reason_text='GM current land-only movement')
        self.p.on_field=False
        self.a.pos=(1,3);self.t.pos=(7,3)

    def use(self,source='item/벌레회피스프레이',target=None,**options):
        direct=target is not None and target is not self.a
        return self.e.use_item(self.a,source,target,aim={'reason':'GM actual spray use and target exposure',**({'reachable':True} if direct else {})},**options)

    def nearby(self,*targets):return {target.entity_id:True for target in targets}

    def direction(self,target=None):
        target=target or self.t
        self.e.observe_relative_directions(target,directions={'away':(1,0),'toward':(-1,0)},
            quickly_trip_placement='before_entry',reason='GM actual understood direction away from sprayer')

    def retreat(self,identity='actual-retreat',**options):
        self.direction()
        return self.e.observe_repel_flee(self.t,
            movement={'direction':'away','distance':4,'pace':'quickly','movement_id':identity},
            reason='GM fastest feasible actual retreat uses all four available land meters',**options)

    def snapshot(self):
        return deepcopy((self.e.elapsed_seconds,self.e.rng.getstate(),
            [vars(c) for c in self.e.gm.everyone],getattr(self.e,'_physical_objects',{}),self.e.log_lines),{id(self.r):self.r})

    def test_three_prices_stock_thresholds_and_exact_hour_lifetimes_reach_admission(self):
        for source,(duration,maximum,price) in R.SOURCES.items():
            with self.subTest(source=source):
                self.setUp();self.a.spec['items']={};self.a.spec['money']=1000
                bought=REWARDS.purchase(self.e,self.a,event_id='actual-repel-purchase',merchant='local shop',items={source:1},reason='actual printed-price purchase')
                self.assertEqual((bought['price'],self.a.spec['money']),(price,1000-price))
                self.e.gm.set_level(self.t,maximum,reason='actual boundary-level wild candidate')
                before=(deepcopy(getattr(self.a,'budget',None)),self.e.elapsed_seconds,self.e.rng.getstate())
                used=self.use(source)
                self.assertEqual((getattr(self.a,'budget',None),self.e.elapsed_seconds,self.e.rng.getstate()),before)
                self.assertEqual(sum(self.a.spec['items'].values()),0)
                out=self.e.admit_wild_encounter(self.a,[self.t],nearby=self.nearby(self.t),reason='GM actual local wild candidate near sprayed wearer')
                self.assertEqual(out['suppressed'],[self.t.entity_id]);self.assertFalse(self.t.on_field)
                # The unchanged driver's actual start filter consumes admission.
                with patch.object(encounter,'load_encounter',return_value=(self.e,{'name':'repel-admission','rounds':1},[self.a],[self.t])),patch.object(self.e,'prepare_initiative_schedule',wraps=self.e.prepare_initiative_schedule) as initiative:
                    encounter.run_encounter(str(ROOT),'unused.json',write=False)
                initiative.assert_not_called();self.assertEqual(self.t.turns_taken,0)
                self.assertFalse(self.e.encounter_active);self.assertEqual(self.e.elapsed_seconds,0)
                self.e.advance_time(duration-1)
                self.assertFalse(self.t.on_field)
                self.assertTrue(R._live(self.e,self.a.spec[R.KEY][used['id']]))
                self.e.advance_time(1)
                out=self.e.admit_wild_encounter(self.a,[self.t],nearby=self.nearby(self.t),reason='GM new actual encounter after exact expiry')
                self.assertEqual(out['admitted'],[self.t.entity_id]);self.assertTrue(self.t.on_field)
                self.assertFalse(R._live(self.e,self.a.spec[R.KEY][used['id']]))

    def test_admission_neighborhood_high_levels_owned_captured_and_atomic_rejection(self):
        self.use()
        self.e.gm.set_level(self.t,16,reason='actual Pokemon above printed limit')
        out=self.e.admit_wild_encounter(self.a,[self.t],nearby=self.nearby(self.t),reason='actual near high-level encounter')
        self.assertEqual(out['admitted'],[self.t.entity_id]);self.assertTrue(self.t.on_field)
        self.e.gm.set_level(self.t,15,reason='actual level correction')
        out=self.e.admit_wild_encounter(self.a,[self.t],nearby={self.t.entity_id:False},reason='GM target is outside actual nearby neighborhood')
        self.assertFalse(out['suppressed'])
        before=self.snapshot()
        with self.assertRaises(ValueError):self.e.admit_wild_encounter(self.a,[self.t,self.p],nearby=self.nearby(self.t,self.p),reason='owned Pokemon is not a wild candidate')
        self.assertEqual(self.snapshot(),before)
        self.held(self.a,'item/벌레회피스프레이','actual-self-spray')
        before=self.snapshot()
        with patch.object(PAID,'finish',side_effect=RuntimeError('late self-application failure')):
            with self.assertRaises(RuntimeError):self.use(held_selection='actual-self-spray')
        self.assertEqual(self.snapshot(),before)
        self.use(held_selection='actual-self-spray')
        self.assertIn('consumed',self.e._physical_objects['actual-self-spray'])
        self.t.captured=True;before=self.snapshot()
        with self.assertRaises(ValueError):self.e.admit_wild_encounter(self.a,[self.t],nearby=self.nearby(self.t),reason='captured target is ineligible')
        self.assertEqual(self.snapshot(),before)
        self.setUp();self.use()
        self.a.hp=0;self.a.on_field=False
        self.assertEqual(self.e.observe_repel_approach(self.a,self.t,nearby=True,reason='GM actual close exposure to already sprayed unconscious wearer')['status'],'must_flee')
        self.assertIsNotNone(R.intent(self.e,self.t))
        out=self.e.admit_wild_encounter(self.a,[self.t],nearby=self.nearby(self.t),reason='GM nearby odor persists on unconscious off-field wearer')
        self.assertEqual(out['suppressed'],[self.t.entity_id])
        stock=self.a.spec['items'].copy();applications=deepcopy(self.a.spec[R.KEY])
        self.assertEqual(self.use(),(0,0))
        self.assertEqual((self.a.spec['items'],self.a.spec[R.KEY]),(stock,applications))

    def test_direct_native_ac6_owned_target_and_physical_stock_miss_and_high_level(self):
        for source,(_,maximum,_) in R.SOURCES.items():
            for physical,roll,level in ((False,20,maximum),(True,20,maximum),(True,1,maximum),(True,20,maximum+1)):
                with self.subTest(source=source,physical=physical,roll=roll,level=level):
                    self.setUp();self.t.spec['trainer_id']=self.a.entity_id;self.t.spec['wild']=False
                    self.e.gm.set_level(self.t,level,reason='actual directly sprayed Pokemon level')
                    if physical:self.held(self.a,source,'actual-repel-bottle')
                    self.begin(self.a)
                    out=self.use(source,self.t,fixed_accuracy=roll,held_selection='actual-repel-bottle' if physical else None)
                    self.assertEqual(out['hit'],roll==20)
                    self.assertEqual(out['affected'],roll==20 and level<=maximum)
                    self.assertEqual(self.a.budget['standard'],0)
                    receipt=PAID.validate(self.a)[out['payment_id']]
                    self.assertEqual(receipt['outcome'],'applied' if out['affected'] else 'no_effect')
                    self.assertEqual(self.a.spec['items'][source],5 if physical else 4)
                    if physical:self.assertIn('consumed',self.e._physical_objects['actual-repel-bottle'])
                    self.assertEqual(R.intent(self.e,self.t) is not None,out['affected'])
                    R.validate_world(self.e)
        # A real Status evasion changes AC6; owned targets gain no immunity.
        self.setUp();self.begin(self.a)
        with patch.object(self.e,'accuracy_check',wraps=self.e.accuracy_check) as accuracy:
            out=self.use(target=self.t,fixed_accuracy=5)
        self.assertEqual((accuracy.call_args.args[2]['ac'],accuracy.call_args.args[2]['class']),(6,'변화'))
        self.assertFalse(out['hit']);self.assertIsNone(R.intent(self.e,self.t))

    def test_missing_or_invalid_application_and_failed_action_never_spend_stock(self):
        self.held(self.a,'item/벌레회피스프레이','actual-repel-bottle')
        before=self.snapshot()
        out=self.e.use_item(self.a,'item/벌레회피스프레이',self.t,held_selection='actual-repel-bottle')
        self.assertIsInstance(out,C.PendingDecision);self.assertEqual(self.snapshot(),before)
        for options in ({'count':2},{'free':True},{'duration_minutes':1},{'fixed_accuracy':False}):
            before=self.snapshot()
            with self.assertRaises(ValueError):self.use(target=self.t,**options)
            self.assertEqual(self.snapshot(),before)
        self.begin(self.a);self.a.budget['standard']=0;before=self.a.spec['items'].copy()
        self.assertEqual(self.use(target=self.t,fixed_accuracy=20),(0,0));self.assertEqual(self.a.spec['items'],before)

    def test_close_approach_creates_actual_flee_then_native_shift_moves_and_can_end_encounter(self):
        self.use();self.e.approach(self.a,self.t,reach=1)
        out=self.e.observe_repel_approach(self.a,self.t,nearby=True,reason='GM observes actual close approach to sprayed wearer')
        self.assertEqual(out['status'],'must_flee')
        self.assertEqual(encounter.choose_action(self.e,self.t,[self.a],[self.t])[0],'repel')
        self.retreat(departed=True,departure_position=(11,3),departure_reason='GM encounter area ends at actual reached eastern boundary')
        self.begin(self.t);before=self.t.pos
        out=self.e.resolve_repel_flee(self.t)
        self.assertEqual(out['status'],'departed');self.assertEqual(self.t.pos,(before[0]+4,before[1]))
        self.assertEqual(self.t.budget['shift'],0);self.assertFalse(self.t.on_field)
        self.assertFalse(self.t.captured);self.assertFalse(self.t.fainted)
        self.e.end_of_turn(self.t);self.e.end_encounter(self.e.everyone,round_elapsed_seconds=0)
        self.assertFalse(self.e.encounter_active)

    def test_fastest_feasible_route_rejects_zero_short_slow_or_toward_without_limitation(self):
        self.use(target=self.t,fixed_accuracy=20);self.direction()
        for change in ({'distance':0},{'distance':1},{'pace':'slowly'},{'direction':'toward'}):
            options={'direction':'away','distance':4,'pace':'quickly','movement_id':'actual-route',**change}
            before=self.snapshot()
            with self.assertRaises(ValueError):self.e.observe_repel_flee(self.t,movement=options,reason='purported fastest route')
            self.assertEqual(self.snapshot(),before)
        self.e.grid.blocking.add((9,3))
        self.e.observe_repel_flee(self.t,movement={'direction':'away','distance':1,'pace':'quickly','movement_id':'short-actual-route'},reason='GM longest feasible retreat ends before blocked lane',limited_reason='GM actual one-cell corridor is boxed by walls and occupied body cells')
        self.begin(self.t);out=self.e.resolve_repel_flee(self.t)
        self.assertEqual(out['movement']['distance'],1);self.assertTrue(self.t.on_field)
        self.assertIsNotNone(R.intent(self.e,self.t))

    def test_native_obstruction_or_immobility_never_fabricates_departure_or_attack(self):
        self.use(target=self.t,fixed_accuracy=20);self.e.grid.blocking.add((8,3))
        self.retreat(departed=True,departure_position=(11,3),departure_reason='observed exit requires actual full traversal')
        self.begin(self.t);out=self.e.resolve_repel_flee(self.t)
        self.assertEqual(out['movement']['distance'],0);self.assertTrue(self.t.on_field)
        self.assertEqual(encounter.choose_action(self.e,self.t,[self.a],[self.t])[0],'repel')
        self.e.apply_status(self.t,'구속');out=self.e.resolve_repel_flee(self.t)
        self.assertEqual(out['status'],'blocked');self.assertTrue(self.t.on_field)

    def test_live_reapplications_and_far_observation_do_not_add_levels_or_extend_old_sources(self):
        first=self.use()
        self.e.observe_repel_approach(self.a,self.t,nearby=True,reason='GM actual first close exposure')
        self.retreat('unpaid-before-wearer-moved')
        self.e.approach(self.a,self.t,reach=2)
        self.retreat('unpaid-after-wearer-moved')
        self.assertEqual(self.t.spec[R.FLEE]['repeller_position'],self.a.pos)
        self.e.advance_time(3599)
        self.e.observe_repel_approach(self.a,self.t,nearby=True,reason='actual close encounter before expiry')
        second=self.use('item/실버스프레이')
        self.e.advance_time(1)
        self.assertFalse(R._live(self.e,self.a.spec[R.KEY][first['id']]))
        self.assertTrue(R._live(self.e,self.a.spec[R.KEY][second['id']]))
        self.e.observe_repel_approach(self.a,self.t,nearby=True,reason='actual renewed close encounter with stronger spray')
        self.assertEqual(R.intent(self.e,self.t)['application_id'],second['id'])
        self.retreat('unpaid-after-source-replaced')
        self.assertEqual(self.t.spec[R.FLEE]['intent']['application_id'],second['id'])
        self.e.observe_repel_approach(self.a,self.t,nearby=False,reason='GM observes target outside current spray neighborhood')
        self.assertIsNone(R.intent(self.e,self.t))
        self.e.gm.set_level(self.t,26,reason='actual target above both live thresholds')
        out=self.e.admit_wild_encounter(self.a,[self.t],nearby=self.nearby(self.t),reason='actual high-level encounter')
        self.assertFalse(out['suppressed'])

    def test_partial_round_expiry_is_pending_and_admission_failure_is_atomic(self):
        self.use();self.e.advance_time(3595);self.begin(self.a)
        self.e.end_of_turn(self.a);self.e.end_encounter(self.e.everyone)
        before=self.snapshot()
        out=self.e.admit_wild_encounter(self.a,[self.t],nearby=self.nearby(self.t),reason='actual encounter at unresolved expiry boundary')
        self.assertIsInstance(out,C.PendingDecision);self.assertEqual(self.snapshot(),before)
        self.setUp();self.use();before=self.snapshot()
        with patch('gm_state.GMState._rec',side_effect=RuntimeError('late native observation failure')):
            with self.assertRaises(RuntimeError):self.e.admit_wild_encounter(self.a,[self.t],nearby=self.nearby(self.t),reason='actual suppression fails after field update')
        self.assertEqual(self.snapshot(),before)

    def test_native_driver_consumes_retreat_and_missing_route_pauses_open_turn(self):
        for observed in (True,False):
            with self.subTest(observed=observed):
                self.setUp();self.use(target=self.t,fixed_accuracy=20)
                if observed:self.retreat(departed=True,departure_position=(11,3),departure_reason='GM actual eastern encounter exit')
                actors=[self.a,self.t];self.e.everyone=self.e.gm.everyone=actors
                original=encounter.choose_action
                with patch.object(encounter,'load_encounter',return_value=(self.e,{'name':'repel-native','rounds':1},[self.a],[self.t])),patch.object(encounter,'choose_action',side_effect=lambda e,c,enemies,allies:original(e,c,enemies,allies) if c is self.t else (None,None,None)):
                    encounter.run_encounter(str(ROOT),'unused.json',write=False)
                if observed:
                    self.assertFalse(self.t.on_field);self.assertFalse(self.e.encounter_active)
                else:
                    self.assertTrue(self.t.on_field);self.assertIs(self.e._active_turn_actor,self.t)
                    self.assertEqual(self.e.elapsed_seconds,0)

    def test_json_restore_and_world_validation_keep_actual_use_payment_clock_and_retreat(self):
        self.use(target=self.t,fixed_accuracy=20);self.retreat();self.begin(self.t)
        saved=json.loads(json.dumps(self.e.export_state()))
        loaded=Engine.import_state(Rules(ROOT,ruleset='core'),saved)
        target=next(c for c in loaded.gm.everyone if c.entity_id==self.t.entity_id)
        self.assertEqual(loaded.resolve_repel_flee(target)['movement']['distance'],4)
        self.assertEqual(target.budget['shift'],0);self.assertTrue(loaded.validate_state()['valid'])
        row=next(iter(self.a.spec[R.KEY].values()));row['at']+=1
        with self.assertRaises(CODEC.StateCodecError):self.e.export_state()

    def test_actual_paid_retreat_prefix_restores_and_resumes_same_shift_after_native_check_wait(self):
        # Reuse the native relative-movement unresolved-check fixture. Pokemon
        # cannot acquire the trainer-only Stamina Edge used by its sibling case.
        self.e.gm.set_skill(self.t,'곡예',4,reason='actual Pokemon traversal skill')
        used=self.use(target=self.t,fixed_accuracy=20);self.e.advance_time(3599)
        self.e.apply_status(self.t,'실명',parameters={'cause':'external'})
        self.e.grid.rough.add((8,3));self.direction()
        self.e.observe_repel_flee(self.t,movement={'direction':'away','distance':4,'pace':'quickly','movement_id':'actual-check-retreat',
            'blindness_options':{'frequency':'once_per_shift','reason':'GM actual hazardous traversal check frequency','check_options':[{'fixed':[6]*4}]}},
            reason='GM fastest feasible native retreat across actual rough terrain')
        self.begin(self.t)
        with patch.object(self.e,'skill_roll',side_effect=ValueError('observed skill unavailable')):
            with self.assertRaisesRegex(ValueError,'observed skill'):self.e.resolve_repel_flee(self.t)
        self.assertEqual(self.t.pos,(8,3));self.assertEqual(self.t.spec[RELATIVE.KEY]['actual-check-retreat']['state'],'pending')
        self.assertEqual(self.t._action_history,['shift']);self.assertIn(R.FLEE,self.t.spec)
        loaded=Engine.import_state(Rules(ROOT,ruleset='core'),json.loads(json.dumps(self.e.export_state())))
        target=next(c for c in loaded.gm.everyone if c.entity_id==self.t.entity_id)
        loaded.advance_time(1)
        user=next(c for c in loaded.gm.everyone if c.entity_id==self.a.entity_id)
        self.assertFalse(R._live(loaded,user.spec[R.KEY][used['id']]))
        self.assertEqual(encounter.choose_action(loaded,target,[user],[target])[0],'repel')
        with self.assertRaises(ValueError):loaded.observe_repel_flee(target,movement={'direction':'away','distance':4,'pace':'quickly','movement_id':'replacement'},reason='cannot replace paid native movement')
        result=loaded.resolve_repel_flee(target)
        self.assertEqual(result['status'],'attempted');self.assertEqual(target.pos,(11,3))
        self.assertEqual(target._action_history,['shift']);self.assertNotIn(R.FLEE,target.spec)
        self.assertEqual(result['movement']['distance'],4)

    def test_source_change_rejects_before_payment_and_miss_never_gains_later_effect(self):
        before=self.snapshot()
        with patch.dict(R.SOURCE_REF,sha256='0'*64):
            with self.assertRaises(ValueError):self.use(target=self.t,fixed_accuracy=20)
        self.assertEqual(self.snapshot(),before)
        self.e.gm.set_level(self.t,16,reason='actual directly sprayed high-level target')
        out=self.use(target=self.t,fixed_accuracy=20);self.assertFalse(out['affected'])
        self.e.gm.set_level(self.t,15,reason='later corrected level is not a new spray hit')
        self.assertIsNone(R.intent(self.e,self.t))


if __name__=='__main__':unittest.main()
