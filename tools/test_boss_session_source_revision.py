"""Q25 actual source-selected slots and explicitly ruled session Move composition."""
from copy import deepcopy
from pathlib import Path
import json,sys,unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools'),str(ROOT/'examples')]
from engine import Rules,Engine
from grid import Grid
from state_codec import StateCodecError
import actor_templates as T,boss_transitions as B,frequency as F,downtime as DT
import test_category2_boss_transitions as BOSS_FIXTURE
import test_core_nicolette_weather as WEATHER_FIXTURE
import declared_skill_ranks


class BossSessionSourceRevisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.r=Rules(str(ROOT),ruleset='core')

    def boss(self):
        fixture=BOSS_FIXTURE.BossTransitionTests();fixture.r=self.r;fixture.setUp()
        return fixture.e,fixture.a,fixture.p

    def configure(self,e,p,choice=None):
        return e.gm.set_encounter_template(p,kind='boss',reason='actual six-action boss observed',
            action_basis={'pokemon_turns':5,'combat_trainers':1,'focused_command_extra':0},
            base_initiative=21,initiative_source_choice=choice)

    def decision(self,p,value):
        return {'value':value,'reason':'GM selects the complete printed '+value+' derivation',
                'scope':B.initiative_choices(p)['decision_scope']}

    def session(self,choices=None,*,defer=False,label=True):
        e=Engine(self.r,419,session_frequency=True,defer_session_refresh=defer,session_move_policy=choices)
        e.grid=Grid(24,24)
        fixture=WEATHER_FIXTURE.NicoletteWeatherTests();fixture.r=self.r
        c=fixture.pokemon(e,'q25/actual-daily-user',moves=('move/안개제거','move/기충전'))
        if label:self.assertEqual(e.begin_session('s1',[c]),'initialized')
        return e,c

    def ruling(self,*,boundary=None,rest=None):
        choices={}
        if boundary is not None:choices['boundary_daily_moves']={'value':boundary,'reason':'Campaign explicitly adjudicates Daily Move quota at real new session commit'}
        if rest is not None:choices['extended_rest_previous_day']={'value':rest,'reason':'Campaign explicitly interprets previous-day eligibility for physical four-hour rest'}
        return choices

    def use_daily(self,e,c):
        e.start_round(e.everyone);e.start_of_turn(c,initiative_count=10)
        before=c.move_uses.get('move/안개제거',0)
        e.use_move(c,c,'move/안개제거')
        self.assertEqual(c.move_uses['move/안개제거'],before+1)
        self.assertTrue(c.took_standard)
        self.assertEqual(F.state(c)['moves']['move/안개제거']['session'],F.state(c)['session'])
        e.end_of_turn(c);e.end_round()

    def restore(self,e):
        fresh=Rules(str(ROOT),ruleset='core')
        return Engine.import_state(fresh,json.loads(json.dumps(e.export_state(),ensure_ascii=False)))

    def find(self,e,c):return next(x for x in e.everyone if x.entity_id==c.entity_id)

    def test_complete_boss_variants_drive_real_slot_turns_and_default_stays_english(self):
        for variant,expected,extra,absent in (
            ('korean_greater_than_one',[21,16,11,6,26,31],31,1),
            ('english_at_least_one',[21,16,11,6,1,26],1,31),
            (None,[21,16,11,6,1,26],1,31)):
            with self.subTest(variant=variant):
                e,a,p=self.boss();choice=None if variant is None else self.decision(p,variant)
                view=self.configure(e,p,choice)
                self.assertEqual([x['initiative'] for x in view['action_slots']],expected)
                self.assertEqual(len(view['action_slots']),6)
                e.gm.set_move(p,'move/기충전',reason='observed legal imported boss Move')
                e.start_round([a,p])
                with self.assertRaises(ValueError):e.start_of_turn(p,initiative_count=absent)
                e.start_of_turn(p,initiative_count=extra);e.use_move(p,p,'move/기충전')
                self.assertTrue(p.took_standard);self.assertEqual(p.move_uses['move/기충전'],1)
                e.end_of_turn(p)
                with self.assertRaises(ValueError):e.start_of_turn(p,initiative_count=extra)
                record=p.spec['encounter_template']['boss_runtime']['action_basis']['initiative_derivation']
                self.assertEqual(record['choice'],choice)
                self.assertEqual(B.initiative_slots(1,2,downward_minimum=2)[0]['initiative'],1)

    def test_boss_choice_scope_failure_and_legacy_fixed_slots_survive_native_restore(self):
        e,a,p=self.boss();choice=self.decision(p,'korean_greater_than_one')
        bad=deepcopy(choice);bad['scope']['definition_hash']='0'*64
        before=deepcopy(p.spec)
        with self.assertRaises(ValueError):self.configure(e,p,bad)
        self.assertEqual(p.spec,before)
        self.configure(e,p,choice);e.start_round([a,p]);e.start_of_turn(p,initiative_count=31);e.end_of_turn(p)
        original=deepcopy(p.spec['encounter_template'])
        # New source selection affects a new producer; it cannot rederive this pair of slot/history owners.
        self.assertEqual(self.decision(p,'english_at_least_one')['value'],'english_at_least_one')
        e.gm.snapshot('chosen');e.gm.restore('chosen')
        n=self.restore(e);np=self.find(n,p)
        self.assertEqual(np.spec['encounter_template'],original)
        with self.assertRaises(ValueError):n.start_of_turn(np,initiative_count=31)
        # A real legacy record has no new producing-source claim; its exact selected slots stay authoritative.
        old,a,p=self.boss();self.configure(old,p)
        p.spec['encounter_template']['boss_runtime']['action_basis'].pop('initiative_derivation')
        old.gm.snapshot('legacy');old.gm.restore('legacy');again=self.restore(old)
        self.assertNotIn('initiative_derivation',self.find(again,p).spec['encounter_template']['boss_runtime']['action_basis'])
        self.assertEqual([x['initiative'] for x in T.projection(self.find(again,p))['action_slots']],[21,16,11,6,1,26])

    def test_real_new_session_refills_daily_quota_but_not_scene_or_physical_state(self):
        e,c=self.session(self.ruling(boundary=True));self.use_daily(e,c)
        e.start_round(e.everyone);e.start_of_turn(c,initiative_count=10)
        e.use_move(c,c,'move/기충전');e.end_of_turn(c);e.end_round()
        non_daily=(c.move_uses['move/기충전'],deepcopy(F.state(c)['moves']['move/기충전']))
        occurrence=deepcopy(F.state(c)['moves']['move/안개제거'])
        e.gm.set_hp(c,max(1,c.hp-3),reason='observed nonfrequency state before narrative boundary')
        before=(c.hp,c.injuries,c.spec.get('ap_spent'),c.spec.get('ap_removed'),e.elapsed_seconds,F.state(c)['day'],F.state(c)['scene'])
        self.assertEqual(e.begin_session('s1'),'unchanged');self.assertEqual(c.move_uses['move/안개제거'],1)
        self.assertEqual(e.begin_session('s2'),'refreshed');self.assertEqual(c.move_uses.get('move/안개제거',0),0)
        self.assertEqual(F.state(c)['moves']['move/안개제거'],occurrence)
        self.assertEqual((c.move_uses['move/기충전'],F.state(c)['moves']['move/기충전']),non_daily)
        self.assertEqual((c.hp,c.injuries,c.spec.get('ap_spent'),c.spec.get('ap_removed'),e.elapsed_seconds,F.state(c)['day'],F.state(c)['scene']),before)
        self.assertEqual(F.move_allowed(e,c,'move/안개제거')[1],'일일 기술은 한 장면에 한 번')
        e.end_scene([c]);self.use_daily(e,c)
        self.assertEqual(e.begin_session('s2'),'unchanged');self.assertEqual(c.move_uses['move/안개제거'],1)
        self.assertEqual(F.state(c)['moves']['move/안개제거']['session'],1)

    def test_current_ruling_admission_and_first_label_preserve_spent_legacy_and_default_guard(self):
        actual,user=self.session(self.ruling(boundary=True),label=False)
        self.use_daily(actual,user)
        self.assertEqual(actual.begin_session('first',[user]),'initialized')
        self.assertEqual(actual.begin_session('first'),'unchanged')
        self.assertEqual(user.move_uses['move/안개제거'],1)
        e,c=self.session(label=False)
        mid='move/안개제거';cap=F.move_frequency(e,mid,c)[1]
        c.move_uses[mid]=cap;c.spec['move_uses']=dict(c.move_uses)
        F.state(c)['moves'][mid]={'day':0,'scene':0,'turn':0,'at_seconds':0}
        original=deepcopy(F.state(c)['moves'][mid])
        e.begin_session('s1',[c]);self.assertEqual(c.move_uses[mid],cap)
        e.begin_session('s2');self.assertIn('미해석',F.move_allowed(e,c,mid)[1])
        before=deepcopy(c.move_uses)
        F.choose_session_move_policy(e,self.ruling(boundary=False,rest='previous_session'))
        self.assertEqual(c.move_uses,before);self.assertEqual(F.state(c)['moves'][mid],original)
        self.assertEqual(F.move_allowed(e,c,mid)[1],'사용 횟수 소진')
        DT.extended_rest(e,c,4,rest_id='legacy-session-unknown')
        self.assertEqual(c.move_uses[mid],cap)
        DT.pokemon_center(e,c);self.assertEqual(c.move_uses.get(mid,0),0)
        self.assertEqual(F.move_allowed(e,c,mid)[1],'일일 기술은 한 장면에 한 번')
        choices=self.ruling(boundary=True)
        F.choose_session_move_policy(e,choices)
        self.assertEqual(F.state(c)['moves'][mid],original)
        with self.assertRaises(ValueError):F.choose_session_move_policy(e,choices)
        self.assertGreaterEqual(len(e._session_move_policy['history']),2)
        self.assertTrue(any('Daily Move session composition' in str(row) for row in e.rulings.log))

    def test_separate_previous_day_choices_gate_actual_four_hour_rest(self):
        for interpretation in ('game_day','previous_session'):
            with self.subTest(interpretation=interpretation):
                e,c=self.session(self.ruling(rest=interpretation));self.use_daily(e,c)
                e.begin_session('s2');self.assertEqual(c.move_uses['move/안개제거'],1)
                DT.extended_rest(e,c,3,rest_id='physical-rest');self.assertEqual(c.move_uses['move/안개제거'],1)
                DT.extended_rest(e,c,1,rest_id='physical-rest')
                self.assertEqual(e.elapsed_seconds,10+4*3600)
                self.assertEqual(c.move_uses.get('move/안개제거',0),0 if interpretation=='previous_session' else 1)
                self.assertEqual(F.state(c)['day'],0)
                receipts=[row for row in c.spec['resource_recovery_receipts'].values() if row['intent']['resource']=='daily_move_uses']
                self.assertEqual(receipts[-1]['intent']['policy']['previous_day_ruling']['value'],interpretation)
                if interpretation=='game_day':
                    DT.new_day(c);DT.extended_rest(e,c,4,rest_id='following-game-day')
                    self.assertEqual(c.move_uses.get('move/안개제거',0),0)

    def test_deferred_commit_gm_and_fresh_json_preserve_choices_scene_and_declared_seven_plus(self):
        declared_skill_ranks.configure(self.r)
        e,c=self.session(self.ruling(boundary=True,rest='previous_session'),defer=True)
        e.gm.set_skill(c,'Athletics',9,reason='actual ordinary declared rank nine control')
        self.use_daily(e,c)
        self.assertTrue(e.encounter_active)
        self.assertEqual(e.begin_session('s2'),'deferred');self.assertEqual(c.move_uses['move/안개제거'],1)
        e.gm.snapshot('deferred');e.end_encounter();self.assertEqual(c.move_uses.get('move/안개제거',0),0)
        e.gm.restore('deferred');self.assertEqual(c.move_uses['move/안개제거'],1)
        n=self.restore(e);nc=self.find(n,c)
        self.assertEqual(n._session_move_policy,e._session_move_policy);self.assertEqual(n.pending_session_id,'s2')
        self.assertEqual(nc.spec['skills'],c.spec['skills'])
        n.end_encounter();self.assertEqual(nc.move_uses.get('move/안개제거',0),0)
        self.assertEqual(n.begin_session('s2'),'unchanged');self.assertEqual(n.session_epoch,1)
        self.assertEqual(F.move_allowed(n,nc,'move/안개제거')[1],'일일 기술은 한 장면에 한 번')
        self.assertEqual(nc.spec['skills']['athletics'],9)

    def test_policy_admission_and_restore_reject_tampering_without_quota_or_rng_change(self):
        e,c=self.session(self.ruling(boundary=False,rest='game_day'));self.use_daily(e,c)
        before=(deepcopy(e._session_move_policy),deepcopy(c.move_uses),deepcopy(F.state(c)),e.rng.getstate())
        for bad in ({'boundary_daily_moves':{'value':1,'reason':'not a boolean'}},
                    {'extended_rest_previous_day':{'value':'previous_session','reason':''}},
                    {'invented_edition':{'value':True,'reason':'unsupported source'}}):
            with self.assertRaises(ValueError):F.choose_session_move_policy(e,bad)
            self.assertEqual((e._session_move_policy,c.move_uses,F.state(c),e.rng.getstate()),before)
        original=deepcopy(e._session_move_policy)
        e._session_move_policy['history'][0]['decisions']['boundary_daily_moves']['reason']=''
        with self.assertRaises(StateCodecError):e.export_state()
        e._session_move_policy=deepcopy(original)
        e._session_move_policy['references'][0]['sha256']='0'*64
        with self.assertRaises(StateCodecError):e.export_state()
        e._session_move_policy=deepcopy(original)
        e._session_move_policy['history'][0]['session_epoch']=e.session_epoch+1
        with self.assertRaises(StateCodecError):e.export_state()
        e._session_move_policy=original
        n=self.restore(e);self.assertEqual(n._session_move_policy,e._session_move_policy)
        plain=Engine(self.r)
        with self.assertRaises(ValueError):F.choose_session_move_policy(plain,self.ruling(boundary=True))


if __name__=='__main__':unittest.main()
