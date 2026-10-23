"""Current region -> native Environ selection, with no numeric baseline tax."""
from copy import deepcopy
from unittest.mock import patch
import json,unittest
import test_foundation_environment_derive as FIX
import test_mapless_space as MAP
import environ_moves as ENV
import environment_derive as ED
import environment_change as EC
import state_codec as CODEC
import turn as TURN
import world_entities as W
import weather_state as WEATHER


class EnvironStateTests(unittest.TestCase):
    setUpClass=classmethod(FIX.EnvironmentTests.setUpClass.__func__)
    setUp=FIX.EnvironmentTests.setUp
    add=FIX.EnvironmentTests.add
    pokemon=FIX.EnvironmentTests.pokemon
    restored=FIX.EnvironmentTests.restored
    begin=FIX.EnvironmentTests.begin
    snap=FIX.EnvironmentTests.snap

    def observe(self,environ='산',*,uid='actual',cells=None,**facts):
        values=dict(gravity=1,pressure=1,air_available=True,medium='air')
        values.update(facts)
        if environ is not ...:values['environ']=environ
        return self.e.observe_environment(uid,values,cells=cells,source=ENV.NATURE,reason='GM observes the actual present environment')

    def known(self,actor,mid):
        self.e.gm.set_move(actor,mid,reason='actual learned Environ Move')
        self.e.gm.set_stat(self.t,'hp',value=100,reason='actual robust target for secondary-state observation')
        self.e.gm.set_hp(self.t,self.t.max_hp,reason='observed healthy target')

    def project(self,mid=ENV.NATURE,actor=None):
        move=ENV.prepare(self.e,actor or self.a,self.r.move(mid))
        return move,ENV.mechanics(self.e,move,self.r.move_mech(mid)[0])

    def test_all_nine_source_rows_select_current_native_move_and_secondary_state(self):
        expected=[('초원','풀묶기','잠듦'),('숲','에너지볼','잠듦'),
            ('늪지','진흙폭탄',('spe',-1)),('바다','거품광선',('atk',-1)),
            ('설원','오로라빔','얼음'),('산','파워젬','풀죽음'),
            ('동굴','원시의힘','풀죽음'),('도시','트라이어택','마비'),('사막','대지의힘',('acc',-1))]
        self.observe('초원')
        for number,(biome,name,secondary) in enumerate(expected):
            with self.subTest(environ=biome):
                if number:self.e.change_environment('actual',{'environ':biome},source=ENV.NATURE,request_id='table/'+str(number),reason='actual changed environment')
                move,mm=self.project();chosen=self.r.move('move/'+name)
                self.assertEqual(move['_environ_selection']['selected_move'],'move/'+name)
                self.assertEqual(move['_environ_selection']['environ'],biome)
                self.assertEqual(move['id'],ENV.NATURE)
                for key in ('type','class','damage_base','ac','range'):self.assertEqual(move[key],chosen[key])
                self.assertEqual(mm,self.r.move_mech('move/'+name)[0])
                secret,sm=self.project(ENV.SECRET);effect=sm['effects_exec'][0]
                self.assertEqual(effect['on_natural_roll_min'],17)
                self.assertEqual(effect.get('status') if isinstance(secondary,str) else (effect['stat'],effect['delta']),secondary)
        self.assertFalse(ED.bound(self.e,self.a));self.assertNotIn('environ',ED.facts(dict(gravity=1,pressure=1,air_available=True,medium='air')))

    def test_actual_nature_power_native_direct_and_area_use_selected_attack_once(self):
        for entry,biome in (('direct','산'),('area','산'),('direct','숲'),('area','숲')):
            with self.subTest(entry=entry,environ=biome):
                self.setUp();self.observe(biome);self.t.pos=(4,3);self.known(self.a,ENV.NATURE);self.begin(self.a)
                original=deepcopy(self.r.move(ENV.NATURE));before=self.t.hp
                with patch.object(self.e,'d20',return_value=17):
                    if entry=='direct':self.e.use_move(self.a,self.t,ENV.NATURE,set_damage=True)
                    else:self.e.use_move_on(self.a,self.t,ENV.NATURE,self.e.everyone)
                self.assertLess(self.t.hp,before);self.assertEqual(self.a.move_uses[ENV.NATURE],1)
                self.assertNotIn('move/파워젬',self.a.move_uses)
                if biome=='숲':self.assertEqual(self.t.stages['spd'],-1)
                self.assertEqual(self.a.budget['standard'],0);self.assertEqual(self.r.move(ENV.NATURE),original)
                self.assertFalse(ED.bound(self.e,self.a))
        # The chosen Move's conditional accuracy effects must survive native
        # re-reads by the original Nature Power identity. This is a routing
        # fixture, not a new source rule or a table-ruling completion claim.
        self.setUp();self.observe('숲');self.t.pos=(4,3);self.known(self.a,ENV.NATURE);self.begin(self.a)
        WEATHER.observe_natural(self.e,description='actual observed rain',treat_as='rain',reason='native conditional accuracy routing fixture')
        actual=self.r.move_mech
        def selected(mid):
            mm,confidence=actual(mid)
            if mid=='move/에너지볼':mm=dict(mm,effects_exec=[*mm.get('effects_exec',[]),{'type':'accuracy_override','ac':20,'if_weather':'rain'}])
            return mm,confidence
        before=self.t.hp
        with patch.object(self.r,'move_mech',side_effect=selected),patch.object(self.e,'d20',return_value=12):
            self.e.use_move(self.a,self.t,ENV.NATURE,set_damage=True)
        self.assertEqual(self.t.hp,before);self.assertEqual(self.t.stages['spd'],0)
        self.assertEqual(self.a.move_uses[ENV.NATURE],1)

    def test_actual_secret_power_applies_each_selected_status_and_stage(self):
        for biome,(_,secondary) in ENV.TABLE.items():
            with self.subTest(environ=biome):
                self.setUp();self.observe(biome);self.t.pos=(4,3);self.known(self.a,ENV.SECRET);self.begin(self.a)
                before=self.t.hp
                with patch.object(self.e,'d20',return_value=17):self.e.use_move(self.a,self.t,ENV.SECRET,set_damage=True)
                self.assertLess(self.t.hp,before);self.assertEqual(self.a.move_uses[ENV.SECRET],1)
                if secondary['type']=='apply_status':self.assertIn(secondary['status'],self.t.conditions)
                else:self.assertEqual(self.t.accuracy_stage if secondary['stat']=='acc' else self.t.stages[secondary['stat']],-1)

    def test_secret_power_natural_threshold_and_miss_preserve_secondary_state(self):
        for natural in (1,16,17):
            with self.subTest(natural=natural):
                self.setUp();self.observe('사막');self.t.pos=(4,3);self.known(self.a,ENV.SECRET);self.begin(self.a)
                with patch.object(self.e,'d20',return_value=natural):self.e.use_move(self.a,self.t,ENV.SECRET,set_damage=True)
                self.assertEqual(self.t.accuracy_stage,-1 if natural==17 else 0)
                self.assertEqual(self.a.move_uses[ENV.SECRET],1)

    def test_missing_unknown_and_ambiguous_actual_environment_refuse_before_cost_rng(self):
        for kind in ('missing','legacy','unknown','ambiguous'):
            with self.subTest(kind=kind):
                self.setUp();self.t.pos=(4,3);self.known(self.a,ENV.NATURE);self.begin(self.a)
                if kind!='missing':self.observe(None if kind=='unknown' else ... if kind=='legacy' else '산')
                if kind=='ambiguous':self.observe('숲',uid='overlap')
                self.e.weather='rain';self.e.grid.rough.add(self.a.pos);before=self.snap()
                with self.assertRaises(ValueError):self.e.use_move(self.a,self.t,ENV.NATURE)
                self.assertEqual(self.snap(),before)

    def test_actual_full_body_location_changes_current_selection_without_baseline(self):
        self.a.pos=(1,3);self.observe('산',cells=[[1,3]])
        self.observe('숲',uid='forest',cells=[[2,3]])
        self.assertEqual(self.project()[0]['_environ_selection']['selected_move'],'move/파워젬')
        self.e.gm.set_position(self.a,(2,3),reason='actual current body enters forest')
        self.assertEqual(self.project()[0]['_environ_selection']['selected_move'],'move/에너지볼')
        self.a.spec['size']='Large'
        with self.assertRaisesRegex(ValueError,'full body'):self.project()

    def test_environment_change_source_lifetime_and_durable_restore_keep_current_choice(self):
        self.observe('산');self.e.change_environment('actual',{'environ':'도시'},source=ENV.NATURE,
            request_id='brief-city',reason='observed temporary environment',duration_seconds=10)
        self.assertEqual(self.project()[0]['_environ_selection']['selected_move'],'move/트라이어택')
        prepared,mechanics=self.project();secret,secret_mechanics=self.project(ENV.SECRET)
        self.assertEqual(len(prepared['_environ_selection']['change_snapshots']),1)
        self.e.gm.snapshot('environ');restored=self.restored();a=W.actor_index(restored)[self.a.entity_id]
        self.assertEqual(ENV.prepare(restored,a,restored.r.move(ENV.NATURE))['_environ_selection']['environ'],'도시')
        restored.advance_time(10)
        self.assertEqual(ENV.prepare(restored,a,restored.r.move(ENV.NATURE))['_environ_selection']['environ'],'산')
        self.e.advance_time(10);self.assertEqual(self.project()[0]['_environ_selection']['environ'],'산')
        self.assertEqual(ENV.read(self.e,prepared,self.a)[0],mechanics)
        self.assertEqual(ENV.read(self.e,secret,self.a)[0],secret_mechanics)
        bad=deepcopy(prepared);value=bad['_environ_selection'];value.pop('sha256')
        value['change_snapshots'][0]['changes']['environ']='숲'
        value['change_snapshots'][0]=ED._sign({k:v for k,v in value['change_snapshots'][0].items() if k!='sha256'})
        bad['_environ_selection']=ED._sign(value)
        with self.assertRaisesRegex(ValueError,'^prepared Environ active change witnesses changed$'):ENV.read(self.e,bad,self.a)
        self.e.gm.restore('environ');self.assertEqual(self.project()[0]['_environ_selection']['environ'],'도시')
        self.e.change_environment('actual',{'environ':'숲'},source=ENV.NATURE,request_id='permanent-forest',reason='actual permanent region change')
        with self.assertRaisesRegex(ValueError,'region changed'):ENV.read(self.e,prepared,self.a)

    def test_invalid_environ_tamper_and_source_change_are_rejected(self):
        before=self.snap()
        with self.assertRaises(ValueError):self.observe('rain')
        self.assertEqual(self.snap(),before);self.observe()
        self.e._environment_derive['regions']['actual']['facts']['environ']='숲'
        with self.assertRaisesRegex(ValueError,'changed'):self.project()
        with self.assertRaises(CODEC.StateCodecError):self.e.export_state()
        self.setUp();self.observe();before=self.snap();bad=dict(ENV.SOURCE,sha256='0'*64)
        with patch.object(ENV,'SOURCE',bad):
            with self.assertRaisesRegex(ValueError,'source'):self.project()
        self.assertEqual(self.snap(),before)
        move=self.r.move(ENV.NATURE);selected=self.r._selected_rule
        with patch.object(self.r,'_selected_rule',side_effect=lambda uid: 'variant/unsupported' if uid==ENV.NATURE else selected(uid)):
            with self.assertRaisesRegex(ValueError,'selected Environ'):ENV.prepare(self.e,self.a,move)
        prepared,_=self.project()
        for mutate in (lambda m:m['_environ_selection'].update(selected_move='move/파괴광선'),
                       lambda m:m['_environ_selection'].update(secondary_effect={'type':'hp_loss','value':999}),
                       lambda m:m['_environ_selection'].update(region_id='invented')):
            bad=deepcopy(prepared);mutate(bad)
            with self.assertRaises(ValueError):self.e.accuracy_check(self.a,self.t,bad,fixed_roll=17)
        # Even a re-fingerprinted marker cannot select a Move outside the table.
        bad=deepcopy(prepared);value=bad['_environ_selection'];value.pop('sha256');value['selected_move']='move/파괴광선'
        bad['_environ_selection']=ED._sign(value)
        with self.assertRaisesRegex(ValueError,'source table'):self.e.damage_base(self.a,bad,target=self.t)
        for mid in (ENV.NATURE,ENV.SECRET):
            normal,_=self.project(mid)
            self.assertTrue(self.e.accuracy_check(self.a,self.t,normal,fixed_roll=17)[0])
            bad=deepcopy(normal);value=bad['_environ_selection'];value.pop('sha256')
            value.update(environ='숲',selected_move=ENV.TABLE['숲'][0],secondary_effect=deepcopy(ENV.TABLE['숲'][1]))
            bad['_environ_selection']=ED._sign(value)
            with self.assertRaisesRegex(ValueError,'effective facts'):self.e.accuracy_check(self.a,self.t,bad,fixed_roll=17)
        for mid in (ENV.NATURE,ENV.SECRET):
            with self.assertRaisesRegex(ValueError,'prepared environment'):self.e.accuracy_check(self.a,self.t,self.r.move(mid),fixed_roll=17)
        self.e.change_environment('actual',{'environ':'숲'},source=ENV.NATURE,request_id='temporary-forest',reason='actual first temporary source',duration_seconds=20)
        self.e.change_environment('actual',{'environ':'도시'},source=ENV.SECRET,request_id='temporary-city',reason='actual second temporary source',duration_seconds=10)
        for mid in (ENV.NATURE,ENV.SECRET):
            normal,_=self.project(mid)
            self.assertTrue(self.e.accuracy_check(self.a,self.t,normal,fixed_roll=17)[0])
            self.assertEqual([r['request_id'] for r in normal['_environ_selection']['change_snapshots']],['temporary-forest','temporary-city'])
            omitted=deepcopy(normal);value=omitted['_environ_selection'];value.pop('sha256')
            value.update(change_snapshots=[],effective_facts=deepcopy(value['region_snapshot']['facts']),
                environ='산',selected_move=ENV.TABLE['산'][0],secondary_effect=deepcopy(ENV.TABLE['산'][1]))
            omitted['_environ_selection']=ED._sign(value)
            reversed_rows=deepcopy(normal);value=reversed_rows['_environ_selection'];value.pop('sha256');value['change_snapshots'].reverse()
            reversed_rows['_environ_selection']=ED._sign(value)
            for bad in (omitted,reversed_rows):
                with self.assertRaisesRegex(ValueError,'active change witnesses changed'):self.e.accuracy_check(self.a,self.t,bad,fixed_roll=17)


class MaplessEnvironTests(unittest.TestCase):
    setUpClass=classmethod(MAP.MaplessFixture.setUpClass.__func__)
    setUp=MAP.MaplessFixture.setUp
    actor=MAP.MaplessFixture.actor
    configure=MAP.MaplessFixture.configure
    snap=MAP.MaplessFixture.snap

    def regions(self,*,bind=False):
        for uid,biome in [('mountain','산'),('forest','숲')]:
            self.e.observe_environment(uid,dict(gravity=1,pressure=1,air_available=True,medium='air',environ=biome),
                source=ENV.NATURE,reason='actual observed mapless region')
        self.regions_by_place={'stairs':'mountain','fountain':'forest','corridor':'forest'}
        self.e.gm.observe_mapless_scene(scene_id='lobby',places=self.places,placements=self.placements,
            contacts=[],reason='actual place region bindings',environment_regions=self.regions_by_place)
        if bind:
            self.e.bind_environment(self.a,dict(id='observed-physical-policy',source=ENV.NATURE,home_gravity=1,rules=[]),
                region_id='mountain',reason='independent physical baseline for actual travel')

    def selected(self):return ENV.prepare(self.e,self.a,self.r.move(ENV.NATURE))['_environ_selection']

    def test_actual_current_mapless_place_selects_without_numeric_baseline_and_preserves_guard(self):
        self.regions();self.assertEqual(self.selected()['environ'],'산');self.assertFalse(ED.bound(self.e,self.a))
        placements=dict(self.placements);placements[self.a.entity_id]='fountain'
        self.e.gm.observe_mapless_scene(scene_id='lobby',places=self.places,placements=placements,contacts=[],
            reason='GM observes actual current place',environment_regions=self.regions_by_place)
        self.assertEqual(self.selected()['environ'],'숲')
        self.e.gm.observe_mapless_movement(self.a,event_id='guard',destination='stairs',movement_cost=1,
            contacts_after=[],reason='physical baseline remains required for environment travel')
        before=self.snap()
        with self.assertRaisesRegex(ValueError,'actual actor baseline'):self.e.move_abstract(self.a,event_id='guard')
        self.assertEqual(self.snap(),before)

    def test_native_mapless_travel_changes_selection_through_existing_region_owner(self):
        self.regions(bind=True);self.assertEqual(self.selected()['environ'],'산')
        self.e.gm.observe_mapless_movement(self.a,event_id='walk',destination='fountain',movement_cost=1,
            contacts_after=[],reason='actual paid region travel')
        self.e.move_abstract(self.a,event_id='walk')
        self.assertEqual(self.selected()['environ'],'숲');self.assertEqual(ED.context(self.e,self.a)['region_id'],'forest')
        restored=CODEC.load_engine(self.r,json.loads(json.dumps(self.snap(),ensure_ascii=False)))
        actor=W.actor_index(restored)[self.a.entity_id]
        self.assertEqual(ENV.prepare(restored,actor,self.r.move(ENV.NATURE))['_environ_selection']['environ'],'숲')


if __name__=='__main__':unittest.main()
