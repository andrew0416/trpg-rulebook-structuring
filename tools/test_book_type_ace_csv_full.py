"""Only explicit CSV differences and demonstrated gaps in the existing Book proof."""
from copy import copy, deepcopy
import csv
import hashlib
import json
import unittest
from unittest.mock import patch

import test_book_type_ace_acquisition as FIX
import test_book_type_ace_actions as ACTIONS
from engine import Engine
import action_points as AP
import class_passive_combat as PASSIVE
import combat_timing as TIME
import blessing_effects as BLESSINGS
import capability_actions as CAPABILITIES
import hazard_state as HAZARDS
import movement_actions as MOVEMENT
import move_state as MOVES
import physics_maneuvers as PHYSICS
import state_fields as FIELDS
import state_grants as GRANTS
import trainer_feature_acquisition as ACQUIRE
import turn as TURN
import type_ace as TA
import event_trace as TRACE


class TypeAceCsvTests(unittest.TestCase):
    setUpClass = classmethod(FIX.TypeAceAcquisitionTests.setUpClass.__func__)
    setUp = FIX.TypeAceAcquisitionTests.setUp
    setup = FIX.TypeAceAcquisitionTests.setup
    add = FIX.TypeAceAcquisitionTests.add
    rejected = FIX.TypeAceAcquisitionTests.rejected
    valid = FIX.TypeAceAcquisitionTests.valid
    restore = FIX.TypeAceAcquisitionTests.restore
    combat = FIX.TypeAceAcquisitionTests.combat
    next_turn = FIX.TypeAceAcquisitionTests.next_turn
    communication = FIX.TypeAceAcquisitionTests.communication
    known = ACTIONS.TypeAceActionsTests.known
    native = ACTIONS.TypeAceActionsTests.native
    answer = ACTIONS.TypeAceActionsTests.answer
    completed = ACTIONS.TypeAceActionsTests.completed
    sustain = ACTIONS.TypeAceActionsTests.sustain

    def acquire(self, feature=None, branch='불꽃', *, edition=None):
        feature = TA.CLASS if feature is None else TA.uid(feature)
        options = {'branch':branch} if feature in (TA.CLASS, TA.REFRESH, TA.SYNC) else {}
        if edition is not None:options['selection'] = {'edition':edition}
        return ACQUIRE.acquire_static(self.e, self.t, feature,
            acquisition_request_id='type-ace/' + self.t.entity_id + '/' + feature + '/' + branch, **options)

    def family(self, branch, *features, rank=6):
        self.setup()
        skill = TA.SKILLS[branch][0]
        self.t.spec['type_link_skills'][branch] = skill
        self.e.gm.set_skill(self.t, skill, rank, reason='actual selected Type-linked skill')
        for pokemon in (self.p, self.q):
            self.e.gm.set_types(pokemon, [branch], reason='actual distinct owned matching pair')
        self.acquire(branch=branch)
        for feature in features:self.acquire(feature, branch)

    def test_all_seventy_five_source_rows_keep_existing_owner_and_exact_raw_cells(self):
        root = FIX.ROOT
        review = json.loads((root/'data/verification/book-type-ace-csv-full-source-review.json').read_text(encoding='utf8'))
        registry = json.loads((root/'data/verification/category2-class-csv-clause-status.json').read_text(encoding='utf8'))
        registered = {row['csv_record']:row for row in registry['rows'] if 226 <= row.get('csv_record',0) <= 300}
        with (root/'input/db/feats.csv').open(encoding='utf-8-sig', newline='') as handle:
            raw = list(csv.reader(handle))
        self.assertEqual([row[0] for row in review['rows']], list(range(226,301)))
        self.assertEqual({row[1] for row in review['rows']}, set(TA.FEATURES))
        for number, feature, relation in review['rows']:
            with self.subTest(record=number):
                self.assertEqual(registered[number]['cells'], raw[number-1])
                self.assertTrue(relation)
                self.assertIn(feature, TA.DEFINITIONS)
        for name, expected in review['source_sha256'].items():
            self.assertEqual(hashlib.sha256((root/name).read_bytes()).hexdigest(), expected)
        self.assertEqual(len(review['mandatory_unanswered_questions']), 1)
        self.assertEqual(review['mandatory_unanswered_questions'][0]['clause_id'], 'C2CSV/input/db/feats.csv:R285:main')

    def test_csv_desert_and_fountain_require_their_explicit_higher_historical_ranks(self):
        cases = [('땅','Mold the Earth','Desert Heart',4,5), ('물','Flood!','Fountain of Life',5,6)]
        for branch, parent, feature, book_rank, csv_rank in cases:
            for edition in (None, 'local_csv'):
                with self.subTest(feature=feature, edition=edition):
                    self.family(branch,parent,rank=book_rank)
                    if edition:
                        self.rejected(lambda:self.acquire(feature,branch,edition=edition), 'rank')
                        self.e.gm.set_skill(self.t,TA.SKILLS[branch][0],csv_rank,reason='actual CSV prerequisite reached')
                    record = self.acquire(feature,branch,edition=edition)
                    self.assertEqual(record['snapshot']['rank'], csv_rank if edition else book_rank)
                    self.e.gm.set_skill(self.t,TA.SKILLS[branch][0],3,reason='later skill change does not rewrite historical eligibility')
                    self.restore()
                    self.assertEqual(TA.local_csv(self.t,TA.uid(feature)), bool(edition))
                    self.valid()

    def test_csv_two_standard_stratagems_keep_book_free_and_same_bound_owner_and_release(self):
        for branch,parent,feature in [('페어리','Fairy Lights','Fey Trance'),('땅','Mold the Earth','Desert Heart')]:
            for edition in (None,'local_csv'):
                with self.subTest(feature=feature,edition=edition):
                    self.family(branch,parent)
                    self.acquire(feature,branch,edition=edition)
                    self.communication();self.combat(self.t)
                    before = AP.available(self.t)
                    row = TA.activate(self.e,self.t,self.p,feature)
                    self.assertEqual(self.t.budget['standard'],0 if edition else 1)
                    self.assertEqual(AP.available(self.t),before-2)
                    self.assertEqual(row['acquisition_source'],TA.acquired(self.t,TA.uid(feature))['request_id'])
                    self.restore()
                    self.assertTrue(TA.sustained(self.e,self.p,TA.uid(feature)))
                    PASSIVE.release(self.e,self.t,self.p,TA.uid(feature))
                    self.assertFalse(TA.sustained(self.e,self.p,TA.uid(feature)))
                    self.assertEqual(AP.available(self.t),before)
                    self.valid()

    def test_csv_standard_shortfall_rejects_before_binding_while_book_free_still_works(self):
        for edition in (None,'local_csv'):
            with self.subTest(edition=edition):
                self.family('페어리','Fairy Lights')
                self.acquire('Fey Trance','페어리',edition=edition)
                self.communication();self.combat(self.t)
                self.assertTrue(TURN.spend(self.e,self.t,'standard','actual prior Standard'))
                use = lambda:TA.activate(self.e,self.t,self.p,'Fey Trance')
                if edition:self.rejected(use,'Standard unavailable')
                else:self.assertTrue(use())

    def test_csv_selection_source_replay_and_json_integrity_use_existing_acquisition_receipt(self):
        self.family('땅','Mold the Earth')
        self.rejected(lambda:self.acquire('Desert Heart','땅',edition='unknown'),'exact Type Ace CSV')
        with patch.object(TA,'CSV_SHA256','0'*64):
            self.rejected(lambda:self.acquire('Desert Heart','땅',edition='local_csv'),'source changed')
        first = self.acquire('Desert Heart','땅',edition='local_csv')
        self.assertEqual(self.acquire('Desert Heart','땅',edition='local_csv')['request_id'],first['request_id'])
        self.rejected(lambda:self.acquire('Desert Heart','땅'),'optional selection')
        self.restore();self.assertTrue(TA.local_csv(self.t,TA.uid('Desert Heart')))
        sid = next(k for k,v in self.t.spec[GRANTS.KEY]['sources'].items()
            if v.get('static_acquisition',{}).get('feature_id')==TA.uid('Desert Heart'))
        self.t.spec[GRANTS.KEY]['sources'][sid]['static_acquisition']['snapshot']['source']['record'] = 299
        with self.assertRaisesRegex(ValueError,'integrity|receipt'):
            ACQUIRE.validate_actor(self.t)

    def test_fountain_selected_csv_receipt_reaches_unchanged_native_damage_temp_hp_and_cure(self):
        for edition in (None,'local_csv'):
            with self.subTest(edition=edition):
                self.family('물','Flood!')
                self.acquire('Fountain of Life','물',edition=edition)
                self.known(self.p,'move/물대포')
                self.e.apply_status(self.p,'화상',source='actual preexisting burn')
                self.combat(self.p)
                with patch.object(Engine,'d20',return_value=10):
                    TA.use_move(self.e,self.t,self.p,self.b,'move/물대포',feature=TA.uid('Fountain of Life'),
                        choice={'penalty':1,'status':'화상'},set_damage=True)
                self.assertEqual(self.p.temp_hp,2)
                self.assertNotIn('화상',self.p.conditions)
                self.assertLess(self.b.hp,self.b.max_hp)
                self.next_turn(self.p)
                self.rejected(lambda:TA.use_move(self.e,self.t,self.p,self.b,'move/물대포',feature=TA.uid('Fountain of Life'),
                    choice={'penalty':1,'status':None},set_damage=True),'frequency')
                self.valid()

    def test_book_sponge_permission_expires_at_current_user_turn_end_not_ally_or_future_turn(self):
        self.family('에스퍼','Psionic Sponge')
        self.known(self.q,'move/염동력')
        self.combat(self.p)
        TA.special(self.e,self.t,self.p,TA.uid('Psionic Sponge'),target=self.q,move='move/염동력')
        self.assertIn('move/염동력',self.p.moves)
        self.assertEqual(self.p.budget['shift'],0)
        self.restore()
        self.e.end_of_turn(self.p)
        self.assertNotIn('move/염동력',self.p.moves)
        self.assertIn('move/염동력',self.q.moves)
        self.valid()

    def test_insectoid_threaded_four_native_maneuvers_ignore_weight_and_keep_actual_shift_cost(self):
        for maneuver in ('trip','push','grapple','disarm'):
            with self.subTest(maneuver=maneuver):
                self.family('벌레','Insectoid Utility')
                if maneuver=='disarm':
                    self.e.gm.set_position(self.b,(11,10),reason='actual Pokemon is not the armed trainer')
                    self.b=self.add('actual remote armed trainer','trainer',(4,2),side='foe')
                GRANTS.replace_baseline(self.e,self.p,'capabilities',['실 날리기'])
                FIELDS.base_patch(self.b,{'weight_kg':CAPABILITIES.limits(self.p)['heavy'][1]+100},reason='measured target heavier than actual Heavy Lifting')
                self.e.gm.set_skill(self.b,'은신',6,reason='actual native Disarm resistance')
                if maneuver=='disarm':TURN.equip_weapon(self.e,self.b,{'name':'검','kind':'소형 근접무기','grade':'조잡'})
                self.combat(self.p)
                options={'fixed_accuracy':20,'challenger_options':{'fixed':[6]*6},'defender_options':{'fixed':[1]*6}}
                if maneuver=='disarm':options.update(attacker_skill='전투',defender_skill='은신')
                else:options.update(challenger_skill='전투',defender_skill='전투')
                result=TA.threaded_maneuver(self.e,self.t,self.p,self.b,maneuver,**options)
                self.assertTrue(result)
                self.assertEqual((self.p.budget['standard'],self.p.budget['shift']),(1,0))
                if maneuver=='trip':self.assertIn('넘어짐',self.b.conditions)
                if maneuver=='push':self.assertEqual(self.b.pos,(5,2))
                if maneuver=='grapple':
                    relation=__import__('grapple_state').relation(self.e,self.p)
                    self.assertEqual(relation['policy']['initiation']['geometry']['range'],__import__('threaded').parameters(self.p)['range'])
                    self.assertEqual(relation['status'],'active')
                self.assertFalse(hasattr(self.e,'_type_ace_threaded'))
                self.valid()
                self.restore();self.valid()

    def test_rock_native_miss_producer_schist_preservation_and_super_effective_hit_consumption(self):
        self.family('바위','Gravel Before Me','Tough as Schist')
        self.answer('type_ace_choice',True);self.answer('type_ace_stealth_rock_cell',(2,1))
        self.sustain('Tough as Schist')
        self.native(self.p,self.b,'move/돌떨구기',face=1)
        rocks=[i for env in HAZARDS.ensure(self.e).values() for i in env['instances'] if i['kind']=='stealth_rock']
        self.assertEqual(len(rocks),1)
        self.assertTrue(TA.preserve_rock(self.e,rocks[0]))
        self.restore()
        self.e.end_of_turn(self.p);self.e.start_of_turn(self.b,initiative_count=20)
        TRACE.enable(self.e)
        self.answer('type_ace_tough_rock',rocks[0]['id'])
        hp=self.p.hp;self.native(self.b,self.p,'move/물대포')
        calculation=next(c for r in TRACE.records(self.e) for c in r['calculations'] if c.get('source')=='move/물대포')
        self.assertEqual(calculation['damage_reduction'],6)
        self.assertEqual(hp-self.p.hp,calculation['result'])
        self.assertGreater(calculation['type_multiplier'],1)
        self.assertFalse(any(i['kind']=='stealth_rock' for env in HAZARDS.ensure(self.e).values() for i in env['instances']))
        self.assertTrue(any(row.get('ace_dr')==6 for row in TIME.records(self.p)))
        self.valid()

    def test_boulder_native_hit_push_vulnerability_rock_and_corrosive_native_hit_refresh(self):
        self.family('바위','Gravel Before Me','Bigger and Boulder')
        self.combat(self.p);self.native(self.p,self.b,'move/돌떨구기')
        TA.react(self.e,self.t,self.p,'Bigger and Boulder',self.completed(self.p)['id'],
            pushes={self.b.entity_id:{'direction':(1,0),'distance':2}},rocks={self.b.entity_id:(6,1)})
        self.assertEqual(self.b.pos,(6,2));self.assertIn('취약',self.b.conditions)
        self.assertTrue(any(i['kind']=='stealth_rock' for i in HAZARDS.ensure(self.e)[(6,1)]['instances']))
        self.restore();self.valid()
        self.family('독','Potent Venom','Corrosive Blight')
        self.combat(self.p);self.native(self.p,self.b,'move/독침')
        TA.react(self.e,self.t,self.p,'Corrosive Blight',self.completed(self.p)['id'])
        self.assertTrue(any(row.get('ace_blight') for row in TIME.records(self.b)))
        self.e.end_of_turn(self.p);self.e.start_of_turn(self.q,initiative_count=20);hp=self.b.hp
        self.native(self.q,self.b,'move/독침')
        self.assertGreaterEqual(hp-self.b.hp,self.e.tick(self.b))
        blight=next(row for row in TIME.records(self.b) if row.get('ace_blight'))
        self.assertEqual(tuple(blight['count_deadline']),(self.e.round_no+1,20))
        self.e.end_of_turn(self.q);self.e.end_round();self.combat(self.p)
        self.assertTrue(any(row.get('ace_blight') for row in TIME.records(self.b)))
        self.e.end_of_turn(self.p);self.e.start_of_turn(self.q,initiative_count=20)
        self.assertFalse(any(row.get('ace_blight') for row in TIME.records(self.b)))
        self.restore();self.valid()

    def test_insectoid_wallclimber_and_observed_naturewalk_reach_native_immunity_consumers(self):
        self.family('벌레','Insectoid Utility')
        GRANTS.replace_baseline(self.e,self.p,'capabilities',['벽타기','자연걸음(숲)'])
        MOVEMENT.observe_cell_terrain(self.e,[self.p.pos],['forest'],'actual forest under Naturewalk user')
        self.combat(self.b)
        self.e.apply_status(self.p,'넘어짐',source='actual Trip',applied_by=self.b)
        self.e.apply_status(self.p,'둔화',source='actual Slowed',applied_by=self.b)
        self.e.apply_status(self.p,'구속',source='actual Stuck',applied_by=self.b)
        self.assertFalse(self.p.conditions.intersection({'넘어짐','둔화','구속'}))
        self.e.gm.set_position(self.b,(3,2),reason='actual adjacent pusher')
        prevented=PHYSICS.push(self.e,self.b,self.p,challenger_skill='전투',defender_skill='전투',fixed_accuracy=20,
            challenger_options={'fixed':[6]*6},defender_options={'fixed':[1]*6})
        self.assertEqual(prevented['pushed_metres'],0)
        self.assertEqual(self.p.pos,(2,2))
        MOVEMENT.observe_cell_terrain(self.e,[self.p.pos],['wetland'],'actual terrain outside the selected Naturewalk')
        self.e.apply_status(self.p,'구속',source='actual Stuck on nonmatching terrain',applied_by=self.b)
        self.assertIn('구속',self.p.conditions)
        self.restore();self.valid()

    def test_mold_actual_ground_move_shapes_only_its_geometry_and_installs_native_spikes_for_upheaval(self):
        for geometry in ('around_target','move_area'):
            with self.subTest(geometry=geometry):
                parents=('Mold the Earth','Upheaval') if geometry=='around_target' else ('Mold the Earth','Earthroil','Upheaval')
                self.family('땅',*parents)
                self.known(self.p,'move/진흙뿌리기');self.combat(self.p)
                with patch.object(Engine,'d20',return_value=10):
                    if geometry=='move_area':TA.use_move(self.e,self.t,self.p,self.b,'move/진흙뿌리기',feature=TA.uid('Earthroil'),choice='line',aim=(4,2),set_damage=True)
                    else:self.native(self.p,self.b,'move/진흙뿌리기')
                row=self.completed(self.p)
                allowed=row['move'].get('_effect_area_cells') if geometry=='move_area' else [list(self.b.pos)]
                cell=tuple(self.b.pos)
                self.assertIn(list(cell),[list(point) for point in allowed])
                self.rejected(lambda:TA.react(self.e,self.t,self.p,'Mold the Earth',row['id'],changes=[{'cell':cell,'terrain':'both'}],geometry=geometry,reason='missing required actual capability'),'Groundshaper')
                GRANTS.replace_baseline(self.e,self.p,'capabilities',['지형변화'])
                self.rejected(lambda:TA.react(self.e,self.t,self.p,'Mold the Earth',row['id'],changes=[{'cell':(12,10),'terrain':'both'}],geometry=geometry,reason='outside actual Move scope'),'outside')
                TA.react(self.e,self.t,self.p,'Mold the Earth',row['id'],changes=[{'cell':cell,'terrain':'both'}],geometry=geometry,reason='actual Ground Move shapes observed ground')
                self.assertIn(cell,self.e.grid.rough);self.assertIn(cell,self.e.grid.slow)
                self.assertTrue(any(i['kind']=='spikes' for i in HAZARDS.ensure(self.e)[cell]['instances']))
                TA.up_execution(self.e,self.t,self.p,row['id'],[self.b],options={self.b.entity_id:{'defender_skill':'전투','fixed_accuracy':20,
                    'challenger_options':{'fixed':[6]*6},'defender_options':{'fixed':[1]*6}}})
                self.assertIn('넘어짐',self.b.conditions)
                self.restore();self.valid()

    def arctic_pool(self):
        self.family('얼음','Glacial Ice','Arctic Zeal')
        # Reuse the existing native Glacial passive registration boundary.
        for pokemon in (self.p,self.q):self.e.register_abilities(pokemon)
        self.combat(self.p);self.native(self.p,self.b,'move/얼음뭉치')
        TA.react(self.e,self.t,self.p,'Arctic Zeal',self.completed(self.p)['id'])
        self.assertNotIn('move/흰안개',self.p.moves)
        pool=next(row for row in BLESSINGS.live(self.p) if row['source']=='move/흰안개')
        self.assertEqual(BLESSINGS.remaining(pool),3)
        self.assertEqual(pool['arctic_zeal']['acquisition'],TA.acquired(self.t,TA.uid('Arctic Zeal'))['request_id'])
        return pool['id']

    def test_arctic_native_free_mist_pool_weaken_stage_and_shared_capacity_survive_json(self):
        pool=self.arctic_pool()
        self.rejected(lambda:TA.arctic(self.e,self.t,self.p,pool,mode='weaken',target=self.q),'foe')
        TA.arctic(self.e,self.t,self.p,pool,mode='weaken',target=self.b)
        self.assertIn('둔화',self.b.conditions)
        self.assertTrue(any(row.get('ace_damage')==-5 for row in TIME.records(self.b)))
        self.assertEqual(self.p.budget['swift'],0)
        self.restore();self.next_turn(self.q)
        # The other actual Ice beneficiary shares the creator's three-use pool.
        TA.arctic(self.e,self.t,self.q,pool,mode='stage',stat='def')
        self.assertEqual(self.q.stages['def'],1)
        self.assertEqual(BLESSINGS.remaining(BLESSINGS.live(self.p)[0]),1)
        self.next_turn(self.p)
        TA.arctic(self.e,self.t,self.p,pool,mode='stage',stat='spd')
        self.assertEqual(self.p.stages['spd'],1)
        self.assertFalse(BLESSINGS.live(self.p))
        self.rejected(lambda:TA.arctic(self.e,self.t,self.q,pool,mode='stage',stat='spd'),'Swift unavailable|pool')
        self.valid()

    def test_arctic_actual_super_effective_native_hit_spends_shared_mist_for_one_tick_reduction(self):
        pool=self.arctic_pool()
        self.e.end_of_turn(self.p);self.e.start_of_turn(self.b,initiative_count=20)
        TRACE.enable(self.e)
        self.answer('type_ace_arctic_guard',pool)
        before=self.p.hp;self.native(self.b,self.p,'move/불꽃세례')
        calculation=next(c for r in TRACE.records(self.e) for c in r['calculations'] if c.get('source')=='move/불꽃세례')
        self.assertEqual(calculation['damage_reduction'],6+self.e.tick(self.p))
        self.assertEqual(before-self.p.hp,calculation['result'])
        self.assertGreater(calculation['type_multiplier'],1)
        self.assertEqual(BLESSINGS.remaining(BLESSINGS.live(self.p)[0]),2)
        self.restore();self.valid()

    def test_foiling_acquired_extended_owner_reuses_selected_grass_status_slot_and_replacement(self):
        self.family('풀','Foiling Foliage')
        self.known(self.p,'move/씨뿌리기','move/수면가루')
        elapsed=self.e.elapsed_seconds
        TA.foiling(self.e,self.t,self.p,'move/씨뿌리기',seconds=60,reason='actual Extended selection')
        self.assertEqual(self.e.elapsed_seconds,elapsed+60)
        self.assertEqual(set(MOVES.describe(self.rules,self.p.spec)['exempt']),{'move/씨뿌리기'})
        TA.foiling(self.e,self.t,self.p,'move/수면가루',seconds=60,reason='actual Extended replacement')
        self.assertEqual(set(MOVES.describe(self.rules,self.p.spec)['exempt']),{'move/수면가루'})
        self.rejected(lambda:TA.foiling(self.e,self.t,self.p,'move/몸통박치기',seconds=60,reason='not Grass Status'),'Grass|풀|선택|qualif|Foiling')
        self.restore();self.valid()

    def test_trail_actual_paid_movement_installs_fire_burns_native_entry_and_water_clears(self):
        self.family('불꽃','Brightest Flame','Trail Blazer')
        self.e.gm.set_position(self.p,(1,5),reason='actual clear fire-trail start')
        self.e.gm.set_movement_capabilities(self.p,{'land':12},basis='base',reason='actual measured long Shift for eight-cell cap')
        self.combat(self.p)
        TA.trail(self.e,self.t,self.p,[(x,5) for x in range(2,12)],mode='land')
        self.assertEqual(self.p.budget['shift'],0)
        self.assertEqual(TA._fire_cells(self.e),{(x,5) for x in range(2,10)})
        self.e.end_of_turn(self.p);self.e.start_of_turn(self.b,initiative_count=20)
        self.assertTrue(TURN.spend(self.e,self.b,'shift','actual entry into fire',movement=True))
        before=self.b.hp
        MOVEMENT.follow_paid_path(self.e,self.b,[(4,3),(4,4),(4,5)],mode='land',maximum_distance=6)
        # Preserve the original method ID, but distinguish all printed boundaries.
        self.assertEqual(before-self.b.hp,self.e.tick(self.b))
        self.assertNotIn('화상',self.b.conditions)
        self.e.end_of_turn(self.b)
        self.assertIn('화상',self.b.conditions)
        self.e.start_of_turn(self.q,initiative_count=10)
        self.native(self.q,self.b,'move/물대포')
        water=self.completed(self.q,'move/물대포')
        self.assertIn(self.b,water['targets'])
        self.assertNotIn((4,5),TA._fire_cells(self.e))
        self.e.end_of_turn(self.q)
        self.u=self.add('actual start-turn fire occupant','pokemon',(6,5),side='foe')
        self.assertNotIn('화상',self.u.conditions)
        self.e.start_of_turn(self.u,initiative_count=5)
        self.assertIn('화상',self.u.conditions)
        self.restore();self.next_turn(self.p)
        self.rejected(lambda:TA.trail(self.e,self.t,self.p,[(12,5)],mode='land'),'frequency')
        self.valid()

    def test_native_potent_venom_selected_stat_extra_tick_and_lockdown_existing_paralysis(self):
        self.family('독','Potent Venom')
        self.answer('type_ace_choice',True);self.answer('type_ace_potent_venom_stat','atk')
        self.combat(self.p)
        self.native(self.p,self.b,'move/독침',face=20)
        self.assertIn('독',self.b.conditions)
        self.assertEqual(self.b.stages['atk'],-2)
        self.assertEqual(self.b.stages['spd'],0)
        self.assertEqual(TA.poison_loss(self.b),6)
        self.restore();self.valid()
        self.family('전기','Lockdown')
        self.e.apply_status(self.b,'마비',source='actual preexisting Paralysis')
        self.answer('type_ace_choice',True)
        self.combat(self.p);self.native(self.p,self.b,'move/전기쇼크',face=20)
        self.assertIn('구속',self.b.conditions)
        self.assertTrue(any(row.get('at_will_moves_only') for row in TIME.records(self.b)))
        self.restore();self.valid()

    def test_native_overload_debilitate_and_mindbreak_use_acquired_sustained_owner_not_names(self):
        cases=[('전기','Lockdown','Overload','move/전기쇼크'),('독','Potent Venom','Debilitate','move/독침'),('에스퍼','Psionic Sponge','Mindbreak','move/염동력')]
        for branch,parent,feature,move in cases:
            with self.subTest(feature=feature):
                self.family(branch,parent,feature)
                if feature=='Debilitate':self.e.apply_status(self.b,'독',source='actual previously poisoned foe')
                self.sustain(feature)
                if feature=='Mindbreak':
                    self.e.apply_status(self.p,'혼란',source='actual Volatile Affliction')
                    self.e.apply_status(self.p,'억압',source='actual second Volatile Affliction')
                if feature=='Overload':self.answer('type_ace_overload',True)
                hp=self.p.hp
                self.native(self.p,self.b,move)
                if feature=='Overload':self.assertEqual(self.p.hp,hp-self.e.tick(self.p))
                elif feature=='Debilitate':self.assertTrue(any(row.get('accuracy_modifier')==-2 and row.get('ace_evasion')==-2 for row in TIME.records(self.b)))
                else:
                    actual=self.completed(self.p)['move']
                    self.assertEqual(TA.damage_bonus(self.e,self.p,self.b,actual,1),6)
                    self.assertEqual(TA.effect_range(self.e,self.p,actual),2)
                self.restore();self.valid()

    def test_new_normal_assault_armor_and_gneiss_actual_move_variants_use_same_native_owner(self):
        cases=[('노말','Extra Ordinary','New Normal','move/원수갚기'),('강철','Polished Shine','Assault Armor','move/메탈클로'),('바위','Gravel Before Me','Gneiss Aim','move/돌떨구기')]
        for branch,parent,feature,move in cases:
            with self.subTest(feature=feature):
                self.family(branch,parent,feature)
                self.e.gm.set_position(self.b,(3,2),reason='actual adjacent target for printed melee variants')
                self.known(self.p,move)
                self.e.gm.set_stat(self.p,'def',value=40,reason='actual Defense exceeds Attack for Assault Armor')
                self.combat(self.p);hp=self.b.hp
                with patch.object(Engine,'d20',return_value=1 if feature=='Gneiss Aim' else 10):
                    TA.use_move(self.e,self.t,self.p,self.b,move,feature=TA.uid(feature),set_damage=True)
                self.assertLess(self.b.hp,hp)
                actual=self.completed(self.p)['move']
                self.assertEqual(self.p.budget['standard'],0)
                if feature=='New Normal':self.assertTrue(actual['_type_ace_new_normal'])
                if feature=='Gneiss Aim':self.assertIn('강타',actual['keywords'])
                self.assertFalse(hasattr(self.e,'_type_ace_scope'))
                self.restore();self.valid()

    def test_simple_improvements_actual_initiative_boundary_and_chitin_native_status_block(self):
        self.family('노말','Extra Ordinary','Simple Improvements')
        self.answer('type_ace_choice',True)
        self.combat(self.p)
        self.assertEqual((TA.all_rolls(self.p),self.p.temp_hp),(6,12))
        self.e.end_of_turn(self.p)
        self.assertEqual(TA.all_rolls(self.p),0)
        self.restore();self.valid()
        self.family('벌레','Insectoid Utility','Chitin Shield')
        self.answer('type_ace_choice',True)
        self.combat(self.b)
        self.native(self.b,self.p,'move/거짓울음')
        self.assertEqual(self.p.stages['spd'],0)
        self.assertTrue(any(row.get('ace_chitin_move')=='move/거짓울음' for row in TIME.records(self.p)))
        self.next_turn(self.b)
        self.native(self.b,self.p,'move/거짓울음')
        self.assertEqual(self.p.stages['spd'],0)
        self.restore();self.valid()

    def test_true_steel_actual_super_effective_hit_recalculates_actual_steel_only_and_reduces_rank(self):
        self.family('강철','Polished Shine','True Steel')
        self.e.gm.set_types(self.p,['강철','풀'],reason='actual dual type with fourfold Fire weakness')
        self.combat(self.b)
        self.answer('type_ace_choice',True)
        steel_view=copy(self.p);steel_view.spec=deepcopy(self.p.spec);steel_view.types=['강철']
        expected_multiplier=self.e.type_multiplier('불꽃',steel_view)[0]
        TRACE.enable(self.e)
        hp=self.p.hp;self.native(self.b,self.p,'move/불꽃세례')
        self.assertLess(self.p.hp,hp)
        self.assertEqual(self.p.types,['강철','풀'])
        self.assertEqual(__import__('frequency').state(self.t)['activations'][TA.uid('True Steel')]['used'],1)
        calculation=next(c for r in TRACE.records(self.e) for c in r['calculations'] if c.get('source')=='move/불꽃세례')
        self.assertEqual(calculation['damage_reduction'],6)
        self.assertEqual(calculation['type_multiplier'],expected_multiplier)
        self.assertEqual(hp-self.p.hp,calculation['result'])
        self.restore();self.valid()


if __name__ == '__main__':unittest.main()
