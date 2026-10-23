"""Independent source-derived boundaries for common time and scene lifetimes."""
import copy, hashlib, json, sys, unittest
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from engine import Rules,Engine,Combatant
import frequency as FREQ
import downtime as DT

class TimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.rules=Rules(str(ROOT),ruleset='core')
    def fixture(self,n=2):
        e=Engine(self.rules)
        cs=[Combatant(self.rules,dict(name='Clock'+str(i),level=3,kind='trainer',stats={'hp':9,'atk':5,'def':5,'spa':5,'spd':5,'spe':5},types=['노말'],moves=[])) for i in range(n)]
        e.everyone=e.gm.everyone=cs
        return e,cs
    def healing_timer(self,e,c):
        c.hp=-1;e.check_fainted(c);e.heal(c,10,source_kind='ordinary_item')
    def test_failed_time_registration_preserves_members_and_earlier_actor(self):
        from native_scenario_fixture import assert_rejected_unchanged
        import injury_recovery as INJURY
        for failure in ('injury','policy'):
            with self.subTest(failure=failure):
                e,cs=self.fixture();late=cs.pop()
                if failure=='injury':
                    late.spec[INJURY.CLOCK]={'source':'invalid'}
                    reason='injury recovery clock source required'
                else:
                    FREQ.state(late).update(daily_basis='session',session=0)
                    reason='session frequency state requires its selected campaign policy'
                before=copy.deepcopy(late.spec);members=e._time_actors
                assert_rejected_unchanged(e,lambda:e.time_actors([late]),reason_pattern=reason)
                self.assertEqual(late.spec,before);self.assertIs(e._time_actors,members)
                self.assertNotIn(INJURY.CLOCK,cs[0].spec)
                self.assertFalse(hasattr(cs[0],'budget'))
                e.advance_time(1,cs)
                self.assertEqual(e.time_actors(),cs)

    def registration_frequency_fixture(self):
        # Native quota observations, not additional source-certified item rules.
        from native_scenario_fixture import prepare_object
        e,cs=self.fixture();objects=[]
        for index,c in enumerate(cs):
            FREQ.consume_activation(c,'test_fixture/registration','하루')
            uid='registration-tool-'+str(index)
            obj=prepare_object(e,uid,
                location={'kind':'unknown'},reason='observed quota test tool')
            FREQ.bind_physical(e,obj,c,'test_fixture/registration','하루',used=1)
            objects.append(obj)
        # Reconstruct with the explicitly selected policy; admission is not a refresh.
        selected=Engine(self.rules,session_frequency=True,defer_session_refresh=False)
        selected.everyone=selected.gm.everyone=cs
        selected._physical_objects=e._physical_objects
        return selected,cs,objects

    def test_late_session_registration_failure_preserves_actor_and_physical_quotas(self):
        import injury_recovery as INJURY
        for failure in ('frequency','injury','physical','signed_physical'):
            with self.subTest(failure=failure):
                e,cs,objects=self.registration_frequency_fixture()
                if failure=='frequency':
                    cs[-1].spec['frequency_state']['day']=-1
                    reason='frequency day must be a nonnegative whole number'
                elif failure=='injury':
                    cs[-1].spec[INJURY.CLOCK]={'source':'invalid'}
                    reason='injury recovery clock source required'
                elif failure=='physical':
                    objects[-1]['frequency_state']['sha256']='changed'
                    reason='physical frequency state changed before session adoption'
                else:
                    row=objects[-1]['frequency_state'];row['activations']=None
                    FREQ._sign_physical(row)
                    reason='activation ledger must be a mapping'
                members=e._time_actors;first=cs[0].spec['frequency_state']
                # The codec rejects malformed starting worlds: inspect the entire
                # admission-owned graph directly, without repairing that input.
                before=copy.deepcopy(([id(c) for c in e._time_actors],
                    [vars(c) for c in cs],e._physical_objects,e.rng.getstate()),{id(e.r):e.r})
                operations=[lambda:e.time_actors(cs)]
                if failure in ('frequency','physical','signed_physical'):
                    operations.append(lambda:FREQ.bind_session(e,cs[-1]))
                for operation in operations:
                    with self.assertRaisesRegex(ValueError,reason):operation()
                    self.assertEqual(([id(c) for c in e._time_actors],
                        [vars(c) for c in cs],e._physical_objects,e.rng.getstate()),before)
                self.assertIs(e._time_actors,members)
                self.assertIs(cs[0].spec['frequency_state'],first)

    def test_successful_time_registration_preserves_identity_order_and_spent_quotas(self):
        import injury_recovery as INJURY
        e,cs,objects=self.registration_frequency_fixture()
        e.gm.everyone=list(reversed(cs))
        states=[c.spec['frequency_state'] for c in cs]
        physical=[obj['frequency_state'] for obj in objects]
        self.assertEqual(e.time_actors([cs[1],cs[0]]),cs)
        for c,st,obj,row in zip(cs,states,objects,physical):
            self.assertIs(c.spec['frequency_state'],st)
            self.assertIs(obj['frequency_state'],row)
            self.assertEqual(st['daily_basis'],'session')
            for ledger in (st,row):
                self.assertEqual(ledger['activations']['test_fixture/registration'],
                                 {'kind':'daily','period':['session',0],'used':1})
            self.assertIn(INJURY.CLOCK,c.spec)
            self.assertFalse(hasattr(c,'budget'))
            self.assertFalse(FREQ.physical_activation_allowed(e,obj,'test_fixture/registration','하루'))
        before=e.export_state();self.assertEqual(e.time_actors(cs),cs)
        self.assertEqual(e.export_state(),before)

    def test_native_setup_and_gmax_reject_late_registration_without_state_change(self):
        from native_scenario_fixture import assert_rejected_unchanged,prepare_setup_move_scene,prepare_gmax_scene
        import gmax_moves as GMAX
        import injury_recovery as INJURY
        rules=Rules(str(ROOT),ruleset='all')
        setup,setup_actor,setup_target=prepare_setup_move_scene(rules)
        declaration=next(row for row in GMAX.declarations(rules) if row['clause_id']=='C2CSV-MOVE-R1016')
        world,actor,target,base,move=prepare_gmax_scene(rules,declaration)
        for e,user,primary,operation in (
            (setup,setup_actor,setup_target,lambda late:setup.use_setup_move_on(
                setup_actor,late,'move/공중날기',setup.everyone,setup_options={})),
            (world,actor,target,lambda late:world.use_gmax_move_on(actor,late,base,move,[actor,target])),
        ):
            with self.subTest(engine=e,actor=user.name):
                spec=copy.deepcopy(primary.spec);spec['id']='test_fixture/late-target'
                late=Combatant(e.r,spec)
                late.spec[INJURY.CLOCK]={'source':'invalid'}
                before=copy.deepcopy(late.spec);members=e._time_actors
                assert_rejected_unchanged(e,lambda:operation(late),
                                         reason_pattern='injury recovery clock source required')
                self.assertEqual(late.spec,before);self.assertIs(e._time_actors,members)

    def test_late_time_effect_failure_preserves_all_clocks_and_rng(self):
        from unittest.mock import patch
        import environmental_effects as ENV
        e,cs=self.fixture();before=e.export_state()
        original=ENV.advance
        def fail(engine,actor):
            original(engine,actor)
            engine.rng.random()
            actor.hp-=1
            if actor.entity_id==cs[-1].entity_id:
                raise ValueError('late timed consequence failed')
        with patch.object(ENV,'advance',side_effect=fail):
            with self.assertRaisesRegex(ValueError,'late timed consequence'):
                e.advance_time(60)
        self.assertEqual(e.export_state(),before)

    def test_round_consequences_and_clock_roll_back_together(self):
        from unittest.mock import patch
        import combat_timing as TIMING
        import environmental_effects as ENV
        e,cs=self.fixture();e.start_round(cs);before=e.export_state()
        original=TIMING.finish_round
        def consequence(engine):
            original(engine)
            engine.everyone[0].hp-=1
            engine.rng.random()
        with patch.object(TIMING,'finish_round',side_effect=consequence):
            with patch.object(ENV,'advance',side_effect=ValueError('late round clock failure')):
                with self.assertRaisesRegex(ValueError,'late round clock failure'):e.end_round()
        self.assertEqual(e.export_state(),before)
        self.assertIs(e.everyone[0],cs[0])
        e.end_round()
        self.assertEqual(e.elapsed_seconds,10)
        self.assertIsNone(e.round_start_seconds)

    def test_late_rest_benefit_failure_preserves_clock_all_actors_and_log(self):
        from unittest.mock import patch
        e,cs=self.fixture()
        for c in cs:c.hp-=5
        before=e.export_state();messages=['existing'];original=Engine.heal
        def fail(engine,actor,*args,**kwargs):
            result=original(engine,actor,*args,**kwargs)
            if actor.entity_id==cs[-1].entity_id:raise ValueError('late rest benefit failure')
            return result
        with patch.object(Engine,'heal',fail):
            with self.assertRaisesRegex(ValueError,'late rest benefit failure'):
                DT.rest_many(e,cs,30,messages,rest_id='atomic-rest')
        self.assertEqual(e.export_state(),before)
        self.assertEqual(messages,['existing'])
        DT.rest_many(e,cs,30,messages,rest_id='atomic-rest')
        self.assertEqual(e.elapsed_seconds,1800)
        self.assertEqual([c.spec['rested_minutes_today'] for c in cs],[30,30])
        self.assertEqual(len(messages),3)

    def test_complete_boundaries_reject_late_failure_without_partial_commit(self):
        from unittest.mock import patch
        import effects as FX
        import homebrew_state as HOME
        import condition_recovery as RECOVERY
        cases=[('start_round',FX,'fire_event'),('end_encounter',HOME,'end_encounter'),('end_scene',RECOVERY,'end_scene')]
        for boundary,module,symbol in cases:
            with self.subTest(boundary=boundary):
                e,cs=self.fixture()
                e.r=copy.copy(e.r);e.rulings=copy.deepcopy(e.rulings);e.r.rulings=e.rulings
                for c in cs:c.r=e.r
                e.rulings.set_formula('tick','2','test scene','scene')
                e.rulings.set_formula('stab','3','test campaign','campaign')
                if boundary!='start_round':e.start_round(cs)
                before=e.export_state();rulings=copy.deepcopy(vars(e.rulings));identity=e.rulings
                original=getattr(module,symbol)
                def fail(*args,**kwargs):
                    original(*args,**kwargs)
                    raise ValueError('late boundary failure')
                with patch.object(module,symbol,side_effect=fail):
                    with self.assertRaisesRegex(ValueError,'late boundary failure'):
                        getattr(e,boundary)(cs)
                self.assertEqual(e.export_state(),before)
                self.assertEqual(vars(e.rulings),rulings)
                getattr(e,boundary)(cs)
                self.assertIs(e.rulings,identity);self.assertIs(e.r.rulings,identity)
                self.assertIs(cs[0].r,e.r);self.assertIs(e.everyone[0],cs[0])
                if boundary=='end_scene':
                    self.assertNotIn('tick',e.rulings.formulas)
                    self.assertIn('stab',e.rulings.formulas)
                else:self.assertIn('tick',e.rulings.formulas)

    def test_repeated_generator_participants_advance_only_once(self):
        e,cs=self.fixture()
        e.advance_time(17,(actor for actor in [cs[0],cs[1],cs[0]]))
        self.assertEqual(e.elapsed_seconds,17)
        self.assertEqual([c.life_elapsed_seconds for c in cs],[17,17])
        self.assertIs(e.everyone[0],cs[0]);self.assertIs(e.gm.everyone[1],cs[1])

    def test_empty_world_clock_uses_the_same_atomic_boundary(self):
        e,cs=self.fixture(0)
        e.advance_time(23)
        self.assertEqual(e.elapsed_seconds,23)
        self.assertEqual(e.round_no,0)
        with self.assertRaises(ValueError):e.advance_time(-1)
        self.assertEqual(e.elapsed_seconds,23)

    def test_first_start_has_no_elapsed_time(self):
        e,cs=self.fixture();e.start_round(cs)
        self.assertEqual(e.elapsed_seconds,0);self.assertEqual([c.life_elapsed_seconds for c in cs],[0,0])
    def test_round_duration_independent_of_actor_count(self):
        for n in (1,2,10):
            e,cs=self.fixture(n);e.start_round(cs);e.end_round()
            self.assertEqual(e.elapsed_seconds,10);self.assertTrue(all(c.life_elapsed_seconds==10 for c in cs))
    def test_turn_boundaries_do_not_multiply_shared_time(self):
        e,cs=self.fixture();e.start_round(cs)
        for c in cs:e.start_of_turn(c);e.end_of_turn(c)
        self.assertEqual(e.elapsed_seconds,0);e.end_round();self.assertEqual(e.elapsed_seconds,10)
    def test_duplicate_completion_rejected(self):
        e,cs=self.fixture();e.start_round(cs);e.end_round()
        with self.assertRaises(ValueError):e.end_round()
        self.assertEqual(e.elapsed_seconds,10)
    def test_successor_start_declares_previous_completed_once(self):
        e,cs=self.fixture();e.start_round(cs);e.start_round(cs);e.end_round();e.start_round(cs)
        self.assertEqual((e.round_no,e.elapsed_seconds),(3,20))
    def test_fainted_off_field_actor_gets_sixty_shared_rounds(self):
        e,cs=self.fixture();c=cs[1];self.healing_timer(e,c);c.on_field=False
        e.everyone=e.gm.everyone=[cs[0]]
        for _ in range(59):e.start_round([cs[0]]);e.end_round()
        self.assertTrue(c.fainted);self.assertEqual(c.faint_recovery_seconds,10)
        e.start_round([cs[0]]);e.end_round();self.assertFalse(c.fainted)
        self.assertEqual((e.elapsed_seconds,c.life_elapsed_seconds),(600,600))
    def test_split_known_intervals_preserve_recovery_result(self):
        for parts in ([600],[200,399,1],[10]*60):
            e,cs=self.fixture();self.healing_timer(e,cs[0])
            for s in parts:e.advance_time(s)
            self.assertFalse(cs[0].fainted);self.assertEqual(e.elapsed_seconds,600)
    def test_partial_round_offset_does_not_double_count(self):
        e,cs=self.fixture();e.start_round(cs);e.at_round_offset(7);e.end_round()
        self.assertEqual(e.elapsed_seconds,10);self.assertEqual(cs[0].life_elapsed_seconds,10)
    def test_ordinary_healing_unknown_initiative_time_stays_pending(self):
        e,cs=self.fixture();e.start_round(cs);self.healing_timer(e,cs[0]);e.end_round()
        self.assertEqual(cs[0].faint_recovery_pending,'within_round_healing_timestamp_unresolved')
        e.advance_time(599);self.assertTrue(cs[0].fainted)
        e.advance_time(1);self.assertFalse(cs[0].fainted)
    def test_explicit_healing_timestamp_cannot_recover_early(self):
        e,cs=self.fixture();c=cs[0];c.hp=-1;e.check_fainted(c);e.start_round(cs)
        e.heal(c,10,source_kind='ordinary_item',round_offset_seconds=8);e.end_round()
        self.assertEqual(c.faint_recovery_seconds,598)
        e.advance_time(597);self.assertTrue(c.fainted)
        e.advance_time(1);self.assertFalse(c.fainted);self.assertEqual(e.elapsed_seconds,608)
    def test_invalid_offsets_rejected_without_time_change(self):
        e,cs=self.fixture();e.start_round(cs);e.at_round_offset(5)
        for x in (-1,4,11,True,1.5):
            with self.assertRaises(ValueError):e.at_round_offset(x)
            self.assertEqual(e.elapsed_seconds,5)
        with self.assertRaises(ValueError):e.advance_time(6)
        self.assertEqual(e.elapsed_seconds,5)
    def test_known_partial_final_round_adds_only_recorded_time(self):
        e,cs=self.fixture();self.healing_timer(e,cs[0]);e.start_round(cs)
        e.end_encounter(round_elapsed_seconds=3)
        self.assertEqual(e.elapsed_seconds,3);self.assertEqual(cs[0].faint_recovery_seconds,597)
        self.assertEqual(e.unresolved_time_intervals,[])
    def test_unknown_final_round_records_gap_and_holds_existing_timer(self):
        e,cs=self.fixture();self.healing_timer(e,cs[0]);e.start_round(cs);e.end_encounter()
        self.assertEqual(e.elapsed_seconds,0);self.assertEqual(len(e.unresolved_time_intervals),1)
        self.assertEqual(cs[0].faint_recovery_pending,'partial_round_elapsed_unresolved')
        e.advance_time(599);self.assertTrue(cs[0].fainted)
        e.advance_time(1);self.assertFalse(cs[0].fainted)
    def test_encounter_does_not_restore_scene_resources(self):
        e,cs=self.fixture();c=cs[0];c.spec.update(ap_spent=3,ap_removed=1)
        FREQ.consume_activation(c,'x',{'kind':'scene','uses':1});c.stages['atk']=2;e.apply_status(c,'혼란')
        e.end_encounter(cs)
        self.assertEqual(c.stages['atk'],0);self.assertNotIn('혼란',c.conditions)
        self.assertEqual(c.spec['ap_spent'],3);self.assertEqual(FREQ.state(c)['scene'],0)
        self.assertFalse(FREQ.activation_allowed(c,'x',{'kind':'scene','uses':1}))
        e.end_scene(cs)
        self.assertEqual((c.spec['ap_spent'],c.spec['ap_removed']),(0,1));self.assertEqual(FREQ.state(c)['scene'],1)
        self.assertTrue(FREQ.activation_allowed(c,'x',{'kind':'scene','uses':1}))
    def test_scene_duplicate_actor_once_and_no_implicit_duration(self):
        e,cs=self.fixture();e.end_scene([cs[0],cs[0],cs[1]])
        self.assertEqual([FREQ.state(c)['scene'] for c in cs],[1,1]);self.assertEqual(e.elapsed_seconds,0)
    def test_encounter_preserves_persistent_faint_and_temp_hp(self):
        e,cs=self.fixture();c=cs[0];c.conditions.update(['독','기절']);c.temp_hp=7
        e.end_encounter(cs)
        self.assertTrue({'독','기절'}<=c.conditions);self.assertEqual(c.temp_hp,7)
    def test_parallel_rest_advances_world_once_sequential_rest_twice(self):
        e,cs=self.fixture();DT.rest_many(e,[*cs,cs[0]],30)
        self.assertEqual(e.elapsed_seconds,1800);self.assertEqual([c.life_elapsed_seconds for c in cs],[1800,1800])
        DT.rest(e,cs[0],30);DT.rest(e,cs[1],30);self.assertEqual(e.elapsed_seconds,5400)
    def test_clock_and_actor_timer_rewind_together(self):
        e,cs=self.fixture();self.healing_timer(e,cs[0]);e.start_round(cs);e.gm.snapshot('clock')
        e.end_round();e.advance_time(100);e.gm.restore('clock')
        self.assertEqual((e.elapsed_seconds,e.round_start_seconds,cs[0].faint_recovery_seconds),(0,0,600))
        self.assertIs(e._time_actors[0],cs[0]);e.end_round();self.assertEqual(cs[0].faint_recovery_seconds,590)
    def test_boundary_scope_does_not_reset_other_registered_actors(self):
        # Combat stages follow encounter membership; AP refresh covers known scene actors.
        e,cs=self.fixture();e.begin_encounter([cs[0]]);cs[1].stages['atk']=2;cs[1].spec['ap_spent']=2
        e.end_scene([cs[0]])
        self.assertEqual((cs[1].stages['atk'],cs[1].spec['ap_spent'],FREQ.state(cs[1])['scene']),(2,0,0))
    def test_fully_recorded_final_round_does_not_invent_unknown_gap(self):
        e,cs=self.fixture();self.healing_timer(e,cs[0]);e.start_round(cs);e.at_round_offset(10);e.end_encounter()
        self.assertEqual(e.unresolved_time_intervals,[]);self.assertIsNone(cs[0].faint_recovery_pending)

    def test_unknown_birth_gets_no_birth_round_credit_but_later_rounds_count(self):
        e,cs=self.fixture();e.start_round(cs);self.healing_timer(e,cs[0]);e.end_round()
        self.assertEqual(cs[0].faint_recovery_seconds,600)
        for _ in range(59):e.start_round(cs);e.end_round()
        self.assertTrue(cs[0].fainted);self.assertEqual(cs[0].faint_recovery_seconds,10)
        e.start_round(cs);e.end_round();self.assertFalse(cs[0].fainted)
    def test_unknown_birth_round_identity_survives_rewind(self):
        e,cs=self.fixture();e.start_round(cs);self.healing_timer(e,cs[0]);e.gm.snapshot('birth')
        e.start_round(cs);e.end_round();e.gm.restore('birth')
        self.assertEqual(cs[0].faint_recovery_birth_round,1);e.end_round()
        self.assertEqual(cs[0].faint_recovery_seconds,600)

    def test_scenario_partial_victory_closes_clock_for_following_rest(self):
        from engine import scenario
        def stop(e,c,rnd):
            for actor in e.gm.everyone:
                if actor.side=='wild':actor.hp=0;e.check_fainted(actor)
        # Explicit simulation policy lets the first turn reach the clock-exit oracle.
        e=scenario(str(ROOT),1,hook=stop,ruleset='core',rulings_path=str(ROOT/'tools/fixtures/initiative-gm-policy.json'))
        self.assertIsNone(e.round_start_seconds);self.assertEqual(e.elapsed_seconds,0)
        self.assertEqual(len(e.unresolved_time_intervals),1)
        DT.rest(e,e.gm.everyone[0],30);self.assertEqual(e.elapsed_seconds,1800)

    def test_spec_integrity_and_false_closure_rejected(self):
        from audit_time_boundaries import validate
        s=json.loads((ROOT/'data/verification/time-boundary-semantics.json').read_text(encoding='utf-8'))
        self.assertEqual(validate(s,ROOT),[])
        bad=copy.deepcopy(s);bad['certification']['engine_conformance']=True
        self.assertIn('unsupported_time_certification',validate(bad,ROOT))
        bad=copy.deepcopy(s);bad['clauses'][0]['source']['excerpt']='invented'
        self.assertIn('stale_time_source:TIME-01',validate(bad,ROOT))

if __name__=='__main__':
    class Result(unittest.TextTestResult):
        def __init__(self,*a,**k):super().__init__(*a,**k);self.rows=[]
        def addSuccess(self,t):super().addSuccess(t);self.rows.append(dict(id='TIME-'+t._testMethodName,status='pass'))
        def addFailure(self,t,e):super().addFailure(t,e);self.rows.append(dict(id='TIME-'+t._testMethodName,status='fail'))
        def addError(self,t,e):super().addError(t,e);self.rows.append(dict(id='TIME-'+t._testMethodName,status='error'))
    r=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(TimeTests))
    paths=['tools/test_time_boundaries.py','tools/audit_time_boundaries.py','data/verification/time-boundary-semantics.json','engine/engine.py','engine/life.py','engine/gm_state.py','engine/downtime.py','engine/frequency.py','engine/action_points.py','data/conditions.json']
    paths.append('tools/fixtures/initiative-gm-policy.json')
    paths+=sorted({c['source']['file'] for c in json.loads((ROOT/paths[2]).read_text(encoding='utf-8'))['clauses']})
    report=dict(generated_at=datetime.now(timezone.utc).isoformat(),scope='Partial shared time and boundary conformance; no whole-rule certification.',results=r.rows,input_hashes={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths})
    (ROOT/'output/time-boundary-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    raise SystemExit(0 if r.wasSuccessful() else 1)
