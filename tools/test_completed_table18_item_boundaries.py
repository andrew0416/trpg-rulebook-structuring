"""Source exceptions exercised through the current native state consumers."""
from copy import deepcopy
from pathlib import Path
import json,unittest
from unittest.mock import patch
from engine import Rules,Engine,Combatant
from builder import build_pokemon
import test_category2_csv_remaining_item_contracts as FIX
import csv_item_physical_contracts as P
import csv_item_capability_contracts as CAP
import special_entities as SPECIAL
import world_entities as WORLD
import state_codec as CODEC
import items as ITEMS
import field_effects as FIELD
import move_state as MOVES
import effects as FX
import turn as TURN


class Table18ItemBoundaries(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        FIX.RemainingCsvItemContractTests.setUpClass()
        cls.polygon=Rules(Path(__file__).resolve().parents[1],ruleset='polygon')
    def setUp(self):self.f=FIX.RemainingCsvItemContractTests();self.r=self.f.r
    def roundtrip(self,e):return CODEC.load_engine(e.r,json.loads(json.dumps(CODEC.dump_engine(e))))

    def test_booster_chlorophyll_actual_stages_and_weather_move_conditions(self):
        a=self.f.trainer('local-chlorophyll');t=self.f.pokemon('local-solar-target');t.pos=(1,0)
        e=self.f.fixture(a,t)
        e.gm.set_ability(a,'엽록소',reason='actual permanent ability')
        self.assertEqual(a.stages['spe'],0)
        self.f.equip(e,a,'boundary/booster','item/부스트에너지',held=False)
        P.activate_booster(e,a,'쾌청')
        self.assertEqual(a.stages['spe'],4)
        e.gm.set_move(a,'move/솔라빔',reason='actual observed learned Solar Beam')
        e.start_round([a,t]);e.start_of_turn(a,initiative_count=20);before=t.hp
        with patch.object(e,'d20',return_value=18):e.use_move(a,t,'move/솔라빔',set_damage=True)
        self.assertLess(t.hp,before)
        self.assertIsNone(e.weather)
        n=self.roundtrip(e);restored=n.gm.everyone[0]
        self.assertEqual(restored.stages['spe'],4)
        e.gm.set_hp(a,value=0,reason='actual knockout')
        self.assertNotIn('booster_environment',a.spec[P.ACTOR_STATE])
        self.assertEqual(a.stages['spe'],0)
        with self.assertRaisesRegex(ValueError,'spent'):P.activate_booster(e,a,'비')

    def test_booster_four_terrains_reach_existing_damage_and_status_consumers(self):
        # R111 permits activation conditions, not general Terrain damage/immunity.
        for local,name,move_id in [('전기지형','일렉트릭','move/10만볼트'),
                ('그래스필드','그래스','move/에너지볼'),('미스트필드','미스트','move/용의파동'),
                ('사이코필드','사이코','move/사이코키네시스')]:
            with self.subTest(terrain=local):
                a=self.f.trainer('terrain-'+name);t=self.f.pokemon('terrain-target-'+name)
                e=self.f.fixture(a,t);move=self.r.move(move_id)
                base=e.roll_damage(a,t,move,set_damage=True)
                self.f.equip(e,a,'boundary/terrain-'+name,'item/부스트에너지',held=False)
                P.activate_booster(e,a,local)
                self.assertEqual(FIELD.terrain_for(e,a)['name'],name)
                self.assertEqual(e.roll_damage(a,t,move,set_damage=True),base)
                self.assertIsNone(FIELD.terrain_for(e,a,include_virtual=False))
                self.assertIsNone(FIELD.terrain_for(e,t))
                self.assertIsNone(e.weather)
                if local=='전기지형':e.apply_status(a,'잠듦');self.assertIn('잠듦',a.conditions)
                if local=='미스트필드':e.apply_status(a,'독');self.assertIn('독',a.conditions)
                n=self.roundtrip(e)
                self.assertEqual(FIELD.terrain_for(n,n.gm.everyone[0])['name'],name)

    def test_booster_does_not_create_global_weather_or_hazard_and_can_reset_only_new_scene(self):
        a=self.f.trainer('no-local-hazard');e=self.f.fixture(a)
        self.f.equip(e,a,'boundary/no-hazard','item/부스트에너지',held=False)
        P.activate_booster(e,a,'모래바람');before=a.hp
        e.start_round([a]);e.start_of_turn(a,initiative_count=20)
        self.assertEqual(a.hp,before)
        e.end_scene([a]);P.activate_booster(e,a,'비')
        self.assertEqual(P.effective_environment(e,a,e.weather),'rain')

    def test_booster_all_four_weather_conditions_persist_until_actual_recall_after_withdrawal(self):
        for chosen,weather in (('비','rain'),('쾌청','sunny'),('모래바람','sandstorm'),('싸라기눈','hail')):
            with self.subTest(weather=weather):
                a=self.f.trainer('actual-recall-'+weather);e=self.f.fixture(a)
                self.f.equip(e,a,'boundary/recall-'+weather,'item/부스트에너지',held=False)
                e.start_round([a]);e.start_of_turn(a,initiative_count=20)
                P.activate_booster(e,a,chosen)
                self.assertTrue(FX.weather_matches(e,weather,a));self.assertIsNone(e.weather)
                ITEMS.unregister_item(e,a,'item/부스트에너지')
                self.assertTrue(FX.weather_matches(e,weather,a))
                e.gm.recall(a,reason='actual source switch/withdrawal boundary')
                self.assertFalse(a.on_field);self.assertFalse(FX.weather_matches(e,weather,a))
                self.assertNotIn('booster_environment',a.spec[P.ACTOR_STATE])
                self.roundtrip(e)

    def test_umbrella_native_chlorophyll_forecast_and_withdrawal(self):
        import test_category2_ability_state_projection as AF
        AF.AbilityStateProjectionTests.setUpClass();f=AF.AbilityStateProjectionTests()
        e=f.engine();a=f.actor(e,'ability/기분파')
        e.gm.set_weather('rain',reason='actual Rain');self.assertEqual(a.types,['물'])
        self.f.equip(e,a,'boundary/forecast-umbrella','item/만능우산')
        self.assertEqual(a.types,['노말'])
        n=self.roundtrip(e);self.assertEqual(n.gm.everyone[0].types,['노말'])
        ITEMS.unregister_item(e,a,'item/만능우산');self.assertEqual(a.types,['물'])
        b=self.f.pokemon('umbrella-chlorophyll',abilities=('엽록소',))
        eb=self.f.fixture(b);eb.gm.set_weather('sunny',reason='actual Sun')
        self.assertEqual(b.stages['spe'],4)
        self.f.equip(eb,b,'boundary/chlorophyll-umbrella','item/만능우산')
        self.assertEqual(b.stages['spe'],0)
        ITEMS.unregister_item(eb,b,'item/만능우산');self.assertEqual(b.stages['spe'],4)

    def test_umbrella_rain_sun_incoming_damage_is_local_and_other_weather_stays(self):
        a=self.f.trainer('incoming-source');t=self.f.pokemon('incoming-umbrella');other=self.f.pokemon('incoming-other')
        e=self.f.fixture(a,t,other);move=self.r.move('move/화염방사')
        base=e.roll_damage(a,t,move,set_damage=True)
        self.f.equip(e,t,'boundary/target-umbrella','item/만능우산')
        e.gm.set_weather('sunny',reason='actual Sun')
        self.assertEqual(e.roll_damage(a,t,move,set_damage=True),base)
        self.assertEqual(e.roll_damage(a,other,move,set_damage=True),base+5)
        e.gm.set_weather('hail',reason='actual Hail')
        self.assertTrue(FX.weather_matches(e,'hail',t))
        self.assertFalse(FX.weather_matches(e,'sunny',t))

    def test_pack_only_actual_loss_and_controller_replacement_atomic(self):
        owner=self.f.trainer('pack-controller');foreign=self.f.trainer('pack-foreign')
        a=self.f.pokemon('pack-actual');b=self.f.pokemon('pack-own-reserve');x=self.f.pokemon('pack-other-reserve')
        a.spec['trainer_id']=b.spec['trainer_id']=owner.entity_id;x.spec['trainer_id']=foreign.entity_id
        e=self.f.fixture(owner,foreign,a,b,x);a.on_field=True;b.on_field=x.on_field=False
        self.f.equip(e,a,'boundary/pack','item/탈출팩')
        e.change_stage(a,'atk',1);self.assertNotIn('eject_pack',a.spec.get(P.PENDING,{}))
        e.change_stage(a,'atk',-1);self.assertIn('eject_pack',a.spec[P.PENDING])
        saved=CODEC.dump_engine(e)
        with self.assertRaisesRegex(ValueError,'same controller'):P.resolve_pending(e,a,'eject_pack',send=x)
        self.assertEqual(CODEC.dump_engine(e),saved)
        e.start_round([a,b]);e.start_of_turn(a,initiative_count=20)
        budget=deepcopy(a.budget);P.resolve_pending(e,a,'eject_pack',send=b)
        self.assertFalse(a.on_field);self.assertTrue(b.on_field);self.assertEqual(a.budget,budget)

    def test_red_card_native_random_reserve_does_not_offer_optional_controller_choice(self):
        owner=self.f.trainer('red-controller');foreign=self.f.trainer('red-foreign')
        a=self.f.pokemon('red-actual');a.spec['loyalty']=2
        reserve=[self.f.pokemon('red-own-'+str(i)) for i in range(2)]
        x=self.f.pokemon('red-foreign-reserve');holder=self.f.pokemon('red-victim')
        for c in [a,*reserve]:c.spec['trainer_id']=owner.entity_id
        x.spec['trainer_id']=foreign.entity_id
        e=self.f.fixture(owner,foreign,a,*reserve,x,holder)
        a.on_field=holder.on_field=True
        for c in [*reserve,x]:c.on_field=False
        holder.pos=(1,0)
        self.f.equip(e,holder,'boundary/red','item/레드카드')
        e.start_round([a,holder]);e.start_of_turn(a,initiative_count=20)
        with patch.object(e,'d20',return_value=18):e.use_move(a,holder,'move/몸통박치기',set_damage=True)
        self.assertFalse(a.on_field);self.assertEqual(sum(c.on_field for c in reserve),1)
        self.assertFalse(x.on_field);self.assertNotIn('red_card',holder.spec.get(P.PENDING,{}))
        self.assertIn('consumed',e._physical_objects['boundary/red'])
        self.roundtrip(e)

    def test_band_removed_foreign_holder_and_mushroom_authority_are_independent(self):
        owner=self.f.trainer('band-controller');other=self.f.trainer('band-other')
        a=self.f.pokemon('band-venusaur',species='Venusaur');a.spec['trainer_id']=owner.entity_id
        e=self.f.fixture(owner,other,a);e.start_round([owner,other,a]);e.start_of_turn(a,initiative_count=20)
        self.f.equip(e,other,'boundary/wrong-band','item/다이맥스벤드',held=False)
        with self.assertRaisesRegex(ValueError,'Band'):e.enter_gigantamax(a,source_id='item/다이맥스벤드',reason='wrong owner')
        ITEMS.unregister_item(e,other,'item/다이맥스벤드')
        self.f.equip(e,owner,'boundary/own-band','item/다이맥스벤드',held=False)
        ITEMS.unregister_item(e,owner,'item/다이맥스벤드')
        with self.assertRaisesRegex(ValueError,'Band'):e.enter_gigantamax(a,source_id='item/다이맥스벤드',reason='removed Band')
        with self.assertRaises(ValueError):e.enter_gigantamax(a,source_id='item/다이버섯',reason='no actual mushroom intake')
        ITEMS.register_item(e,owner,'item/다이맥스벤드',source_instance_id='boundary/own-band')
        receipt=e.enter_gigantamax(a,source_id='item/다이맥스벤드',reason='actual live owner accessory')
        self.assertEqual(receipt['band_authorization']['instance_id'],'boundary/own-band')
        self.roundtrip(e)

    def test_manual_capture_d20_bonus_rank_prerequisite_type_and_withdrawal(self):
        a=self.f.trainer('manual-capture',items={'몬스터볼':3});t=self.f.pokemon('manual-wild',types=('불꽃',))
        t.side='wild';t.spec['side']='wild';t.spec['wild']=True;t.pos=(1,0)
        e=self.f.fixture(a,t);self.f.physical(e,a,'boundary/manual-capture','item/타입-공부-메뉴얼-1')
        with self.assertRaisesRegex(ValueError,'Education'):P.configure_type_manual(e,a,'boundary/manual-capture','불꽃',1)
        a.spec['skills']['포켓몬학']=3;P.configure_type_manual(e,a,'boundary/manual-capture','불꽃',1)
        with self.assertRaisesRegex(ValueError,'immutable'):P.configure_type_manual(e,a,'boundary/manual-capture','물',1)
        e.start_round([a,t]);e.start_of_turn(a,initiative_count=20)
        e.throw_ball(a,t,fixed_accuracy=18,fixed_capture=1,type_manual_instance_id='boundary/manual-capture')
        row=a.spec['capture_attempts']['capture-1'];self.assertEqual(row['type_manual']['bonus'],1)
        self.assertEqual(row['resolution']['modifiers']['type_manual'],1)
        self.roundtrip(e)

    def test_cannon_sludge_bomb_native_range_accuracy_and_source_withdrawal(self):
        a=self.f.trainer('cannon-sludge',moves=('move/오물폭탄',));t=self.f.pokemon('cannon-sludge-target')
        t.pos=(15,0);e=self.f.fixture(a,t)
        self.f.equip(e,a,'boundary/sludge-cannon','item/몬스터볼-캐논',held=False)
        e.start_round([a,t]);e.start_of_turn(a,initiative_count=20);before=t.hp
        with patch.object(e,'d20',return_value=18):e.use_move(a,t,'move/오물폭탄',weapon_id='boundary/sludge-cannon',set_damage=True)
        self.assertLess(t.hp,before)
        import weapon_actions as WEAPONS
        projected=WEAPONS.prepare(e,a,e.r.move('move/오물폭탄'),'boundary/sludge-cannon')
        self.assertEqual(WEAPONS.accuracy_bonus(projected),1)
        self.assertEqual(WEAPONS.range_spec(e,projected,a)['origin'],15)
        ITEMS.unregister_item(e,a,'item/몬스터볼-캐논')
        with self.assertRaises(ValueError):WEAPONS.prepare(e,a,e.r.move('move/오물폭탄'),'boundary/sludge-cannon')

    def test_manual_native_growth_selects_only_one_matching_actual_participant(self):
        a=self.f.trainer('manual-two');a.spec['skills'].update({'명령':4,'포켓몬학':5})
        one=self.f.pokemon('manual-one',level=10,types=('불꽃',));two=self.f.pokemon('manual-two-target',level=10,types=('불꽃',))
        for c in (one,two):c.spec['trainer_id']=a.entity_id
        e=self.f.fixture(a,one,two);self.f.physical(e,a,'boundary/manual-two','item/타입-공부-메뉴얼-1')
        P.configure_type_manual(e,a,'boundary/manual-two','불꽃',2)
        e.pokemon_activity(a,'experience_training',targets=[one,two],safe=True,
            type_manual={'instance_id':'boundary/manual-two','target_id':one.entity_id})
        self.assertEqual((one.level,two.level),(11,10))
        self.assertEqual(one.spec['experience_training_history'][-1]['extra_level_source']['source'],'C2CSV/inventory:70:1')
        self.assertNotIn('extra_level_source',two.spec['experience_training_history'][-1])
        self.roundtrip(e)

    def test_manual_existing_baby_food_and_champion_exclusions_reach_native_growth(self):
        for exclusion in ('baby_food','champion'):
            with self.subTest(exclusion=exclusion):
                a=self.f.trainer('manual-exclusive-'+exclusion);a.spec['skills'].update({'명령':4,'포켓몬학':5})
                t=self.f.pokemon('manual-exclusive-target',level=10,types=('불꽃',));t.spec['trainer_id']=a.entity_id
                e=self.f.fixture(a,t);self.f.physical(e,a,'boundary/exclusive-manual','item/타입-공부-메뉴얼-1')
                P.configure_type_manual(e,a,'boundary/exclusive-manual','불꽃',2)
                if exclusion=='baby_food':
                    a.spec['items']['이유식']=1
                    e.use_item(a,'이유식',t,duration_minutes=1,duration_reason='actual Baby Food intake',food_policy='homebrew_initial_plus5')
                else:a.spec['feats']=['챔피언 트레이너']
                e.pokemon_activity(a,'experience_training',targets=[t],safe=True,
                    type_manual={'instance_id':'boundary/exclusive-manual','target_id':t.entity_id})
                self.assertNotIn('extra_level_source',t.spec['experience_training_history'][-1])
                self.assertEqual(t.level,11 if exclusion=='baby_food' else 10)
                if exclusion=='baby_food':self.assertTrue(t.spec['baby_food']['consumed'])
                self.roundtrip(e)

    def cannon_fixture(self,suffix):
        a=self.f.trainer('projectile-'+suffix);t=self.f.pokemon('projectile-target-'+suffix)
        t.side='wild';t.spec['side']='wild';t.spec['wild']=True;t.pos=(12,0)
        e=self.f.fixture(a,t)
        self.f.equip(e,a,'boundary/projectile-cannon','item/몬스터볼-캐논',held=False)
        from grid import Grid
        import map_terrain as TERRAIN
        e.grid=Grid(30,10)
        for c in e.gm.everyone:e.gm.set_footprint(c,[(0,0)],reason='actual observed one-cell body')
        TERRAIN.observe(e,[(13,0)],base='regular',reason='GM observes actual behind-target Cannon ground')
        self.f.physical(e,a,'boundary/projectile-ball','item/몬스터볼-2')
        e.start_round([a,t]);e.start_of_turn(a,initiative_count=20)
        P.load_cannon(e,a,'boundary/projectile-cannon','boundary/projectile-ball')
        return e,a,t

    def test_cannon_native_miss_same_physical_recovery_and_hit_fixed_two_d6(self):
        for hit in (False,True):
            with self.subTest(hit=hit):
                e,a,t=self.cannon_fixture(str(hit));before=t.hp
                e.throw_ball(a,t,cannon_instance_id='boundary/projectile-cannon',fixed_accuracy=18 if hit else 1,fixed_capture=1)
                attempt=a.spec['capture_attempts']['capture-1'];ball=e._physical_objects['boundary/projectile-ball']
                self.assertEqual(attempt['hit'],hit);self.assertFalse(attempt['captured'])
                if hit:self.assertEqual(tuple(ball['location']['cell']),tuple(t.pos))
                else:
                    self.assertEqual(ball['location'],{'kind':'unknown'})
                    e.gm.observe_missed_ball_ground(a,attempt_id='capture-1',cell=(13,0),intact=True,reason='actual same Cannon projectile landed behind target')
                self.assertNotIn('carrier_id',ball)
                if hit:
                    damage=attempt['cannon']['damage'];self.assertEqual(damage['expression'],'2d6')
                    self.assertEqual(len(damage['faces']),2);self.assertEqual(damage['requested'],sum(damage['faces']))
                    self.assertEqual(t.hp,before-damage['requested'])
                else:self.assertEqual(t.hp,before)
                e.end_of_turn(a);e.end_round();e.start_round([a,t]);e.start_of_turn(a,initiative_count=20)
                with self.assertRaisesRegex(ValueError,'recovered'):P.load_cannon(e,a,'boundary/projectile-cannon',ball['id'])
                inv=deepcopy(a.spec['items'])
                e.pokemon_activity(a,'observe_ball',attempt_id='capture-1',condition='recovered_intact',reason='actual same projectile recovered')
                self.assertEqual(a.spec['items'],inv);self.assertEqual(tuple(ball['location']['cell']),tuple(a.pos));self.assertEqual(ball['owner_id'],a.entity_id)
                self.assertTrue(P.load_cannon(e,a,'boundary/projectile-cannon',ball['id'])['loaded'])
                self.roundtrip(e)

    def test_cannon_native_failed_capture_existing_ball_repair_returns_same_instance(self):
        for repaired in (True,False):
            with self.subTest(repaired=repaired):
                e,a,t=self.cannon_fixture('repair-'+str(repaired))
                e.throw_ball(a,t,cannon_instance_id='boundary/projectile-cannon',fixed_accuracy=18,fixed_capture=1)
                e.end_encounter([a,t])
                import pokemon_activities as ACTIVITIES
                a.spec['edges']=[ACTIVITIES.FEATURES[name][0] for name in ('repair','basic_balls')]
                a.spec['skills']['기술학']=3;a.spec['items']['몬스터볼 공구함']=1
                e.pokemon_activity(a,'observe_ball',attempt_id='capture-1',condition='broken',reason='actual fired ball inspected broken')
                inv=deepcopy(a.spec['items']);ball=e._physical_objects['boundary/projectile-ball']
                self.assertTrue(ball['disabled'])
                result=e.pokemon_activity(a,'repair_ball',ball_id='capture-1',fixed=[6,6,6] if repaired else [1,1,1])
                self.assertEqual(result['status'],'repaired' if repaired else 'permanently_broken')
                self.assertEqual(a.spec['items'],inv)
                if repaired:self.assertEqual(tuple(ball['location']['cell']),tuple(a.pos));self.assertEqual(ball['owner_id'],a.entity_id);self.assertNotIn('disabled',ball)
                else:self.assertIn('destroyed',ball)
                self.roundtrip(e)

    def test_cannon_success_uses_actual_physical_ball_once(self):
        e,a,t=self.cannon_fixture('captured')
        e.throw_ball(a,t,cannon_instance_id='boundary/projectile-cannon',fixed_accuracy=18,fixed_capture=20)
        self.assertTrue(a.spec['capture_attempts']['capture-1']['captured'])
        self.assertIn('consumed',e._physical_objects['boundary/projectile-ball'])
        with self.assertRaises(ValueError):P.load_cannon(e,a,'boundary/projectile-cannon','boundary/projectile-ball')
        self.roundtrip(e)

    def essence_fixture(self,essence,*,capabilities=()):
        r=self.polygon
        a=Combatant(r,build_pokemon(r,'이브이',20,moves=['move/섀도볼'],abilities=[],extra={'capabilities':list(capabilities)}))
        e=Engine(r,seed=18100);e.gm.add_combatant(a)
        choices={10:[],8:['smart_vision'],7:['wired_reflexes'],5:['smart_vision','wired_reflexes'],
                 4:['smart_vision','synthetic_muscle','medical_nanobots'],2:['smart_vision','embedded_weaponry','wired_reflexes'],
                 0:['smart_vision','synthetic_muscle','medical_nanobots','thermal_optical_camouflage']}
        installs=[]
        for i,choice in enumerate(choices[essence]):
            uid='boundary/essence-implant-'+str(i);WORLD.register_object(e,uid,location={'kind':'unknown'},reason='actual installed augmentation')
            installs.append({'instance_id':uid,'augmentation_id':choice})
        row={'id':'boundary/essence-set','kind':'augmentation_set','location':{'kind':'unknown'},'actor_id':a.entity_id,
            'body_slots':['eyes','limbs','body','skin'],'installations':installs,'allow_added_parts':False,
            'essence_enabled':True,'essence_profile':'C2CSV/inventory:100:17'}
        SPECIAL.observe(e,row,reason='explicit source CSV Essence profile')
        return e,a

    def test_essence_actual_capacity_thresholds_hp_and_death_limit_exclude_real_injuries(self):
        from rulings import calc
        for essence,base in ((8,0),(7,1),(5,1),(4,1),(2,1),(0,3)):
            with self.subTest(essence=essence):
                e,a=self.essence_fixture(essence)
                penalty=calc(e.r.formula('injury_penalty'),{'max_hp':a.base_max_hp,'level':a.level})
                self.assertEqual(a.injuries,0)
                self.assertEqual(CAP.essence_view(a)['essence'],essence)
                self.assertEqual(a.max_hp,int(a.base_max_hp-base*penalty))
                n=self.roundtrip(e);self.assertEqual(n.gm.everyone[0].max_hp,a.max_hp)
        e,a=self.essence_fixture(7);e.death_enabled=True
        e.gm.set_injuries(a,value=9,reason='actual nine injuries plus CSV base injury reaches death limit')
        self.assertTrue(a.dead);self.assertEqual(a.injuries,9)

    def test_essence_ghost_aura_actual_use_and_learning_block_and_capability_loss(self):
        e,a=self.essence_fixture(4,capabilities=('파동 감지','파동술','집중'))
        self.assertNotIn('파동 감지',a.spec['capabilities']);self.assertNotIn('파동술',a.spec['capabilities']);self.assertIn('집중',a.spec['capabilities'])
        t=Combatant(e.r,build_pokemon(e.r,'이브이',20,moves=['move/몸통박치기'],abilities=[]));e.gm.add_combatant(t)
        t.pos=(1,0);e.start_round([a,t]);e.start_of_turn(a,initiative_count=20)
        before=deepcopy(a.budget)
        with self.assertRaisesRegex(ValueError,'Essence'):e.use_move(a,t,'move/섀도볼')
        self.assertEqual(a.budget,before)
        with self.assertRaisesRegex(ValueError,'Essence'):MOVES.observe_learning(e,a,'move/파동탄',method='feature',source='move/파동탄',reason='actual observed learning attempt')
        with self.assertRaisesRegex(ValueError,'Essence'):e.gm.set_move(a,'move/파동탄',reason='actual new permanent Aura Move observation')
        import state_grants as GRANTS
        GRANTS.grant_moves(a,['move/섀도볼'],'move/섀도볼','feature',rule_id='move/섀도볼')
        self.assertFalse(GRANTS.grant_moves(a,['move/섀도볼'],'move/섀도볼','feature',rule_id='move/섀도볼'))
        self.assertEqual(a.moves.count('move/섀도볼'),1)
        e2,a2=self.essence_fixture(5);self.assertTrue(CAP.essence_move_allowed(a2,e2.r.move('move/섀도볼')))

    def test_essence_ghost_effectiveness_immunity_normal_and_dynamic_detachment(self):
        e,a=self.essence_fixture(2)
        self.assertEqual(e.type_multiplier('고스트',a)[0],1.0)
        original=list(e._physical_objects['boundary/essence-set']['installations'])
        FX.h_type_change(e,a,a,{'set_type':'고스트'},{'source_id':'move/핼러윈','attacker':a,'target':a})
        row=e._physical_objects['boundary/essence-set']
        self.assertEqual(row['installations'],[]);self.assertEqual(row['essence_removals'][-1]['installations'],original)
        self.assertEqual(a.spec['csv_essence_projection']['essence'],10)
        forbidden=deepcopy(row);forbidden['installations']=original
        with self.assertRaisesRegex(ValueError,'Ghost'):SPECIAL.observe(e,forbidden,reason='actual Ghost cannot reinstall augmentations')
        self.roundtrip(e)

    def test_essence_csv_projection_corruption_and_missing_receipt_are_rejected(self):
        for mode in ('number','missing'):
            e,a=self.essence_fixture(7)
            if mode=='number':a.spec['csv_essence_projection']['essence']=10
            else:a.spec.pop('csv_essence_projection')
            with self.assertRaises(CODEC.StateCodecError):CODEC.dump_engine(e)

    def test_essence_actual_gm_permanent_type_change_also_detaches_installed_augmentations(self):
        e,a=self.essence_fixture(5)
        self.assertTrue(e._physical_objects['boundary/essence-set']['installations'])
        e.gm.set_types(a,['고스트'],reason='actual permanent type becomes Ghost')
        self.assertEqual(e._physical_objects['boundary/essence-set']['installations'],[])
        self.assertEqual(a.spec['csv_essence_projection']['essence'],10)
        self.roundtrip(e)


if __name__=='__main__':unittest.main(verbosity=2)
