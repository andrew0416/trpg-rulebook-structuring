"""Source oracles kept failing until the corresponding follow-up is repaired."""
import unittest
import csv_item_capability_contracts as CAP
import csv_item_form_contracts as FORMS
import state_grants as GRANTS
from copy import deepcopy
import movement_actions as MOVE
import skill_modifiers as SKILLS
from engine import Engine, Rules
from unittest.mock import patch
import test_category2_csv_remaining_item_contracts as _fixture_test_category2_csv_remaining_item_contracts


class CompletedCsvKnownGaps(unittest.TestCase):
    setUpClass = classmethod(_fixture_test_category2_csv_remaining_item_contracts.RemainingCsvItemContractTests.setUpClass.__func__)
    pokemon = _fixture_test_category2_csv_remaining_item_contracts.RemainingCsvItemContractTests.pokemon
    trainer = _fixture_test_category2_csv_remaining_item_contracts.RemainingCsvItemContractTests.trainer
    fixture = _fixture_test_category2_csv_remaining_item_contracts.RemainingCsvItemContractTests.fixture
    physical = _fixture_test_category2_csv_remaining_item_contracts.RemainingCsvItemContractTests.physical
    equip = _fixture_test_category2_csv_remaining_item_contracts.RemainingCsvItemContractTests.equip
    egg = _fixture_test_category2_csv_remaining_item_contracts.RemainingCsvItemContractTests.egg

    def test_navigator_five_minute_step_advances_actual_route_clock(self):
        actor=self.pokemon('navigator-clock',capabilities=('에스퍼 네비게이터',))
        e=self.fixture(actor)
        CAP.start_navigation(e,actor,'route/to-star',lightyears=3)
        before=e.elapsed_seconds
        CAP.navigation_check(e,actor,'route/to-star',skill='집중',total=20)
        self.assertEqual(e.elapsed_seconds-before,300)

    def test_juicer_cannot_mature_before_an_actual_session_boundary(self):
        actor=self.pokemon('juicer-clock',capabilities=('과즙기',),species='단단지')
        e=self.fixture(actor)
        self.equip(e,actor,'csv/actual-berry','item/오랭열매')
        CAP.juicer_begin(e,actor,'csv/actual-berry')
        with self.assertRaises(ValueError):
            CAP.juicer_session(e,actor)

    def test_egg_hatcher_twenty_four_actual_hours_refreshes_printed_frequency(self):
        actor=self.pokemon('hatcher-clock',capabilities=('알부화기',))
        owner=self.trainer('egg-owner')
        e=self.fixture(actor,owner)
        egg=self.egg(e,owner,remaining=259200)
        CAP.heat_egg(e,actor,egg['entity_id'],fixed_d2=1)
        e.advance_time(86400,[actor])
        result=CAP.heat_egg(e,actor,egg['entity_id'],fixed_d2=2)
        self.assertEqual(result['reduced_seconds'],86400)

    def test_expanded_poison_move_derives_live_poison_glands(self):
        actor=self.pokemon('poison-expanded',moves=('move/독침천발',))
        e=self.fixture(actor)
        self.assertTrue(CAP.has(actor,'독샘'))

    def test_tera_change_cannot_exit_during_actual_encounter(self):
        self.r=Rules(self.r.root,ruleset='homebrew')
        actor=self.pokemon('tera-battle',capabilities=('테라체인지',))
        other=self.pokemon('tera-other')
        e=self.fixture(actor,other)
        import homebrew_state as HOME
        HOME.observe_type(e,actor,'불꽃',reason='existing independent generic source')
        HOME.observe_active(e,actor,True,reason='observed generic Terastallization')
        generic=deepcopy(actor.spec[HOME.KEY])
        FORMS.tera_exit(actor,engine=e)
        self.assertEqual(actor.form,'일반')
        self.assertEqual(actor.spec[HOME.KEY],generic)
        with self.assertRaisesRegex(ValueError,'actual engine'):
            FORMS.tera_exit(actor)
        e.start_round([other])
        FORMS.tera_exit(actor,engine=e)  # another actor's encounter does not invent membership
        e.start_round([actor])
        self.assertTrue(e.encounter_active)
        self.assertEqual(actor.form,'테라스탈')
        before=deepcopy(actor.spec)
        with self.assertRaisesRegex(ValueError,'outside combat'):
            FORMS.tera_exit(actor,engine=e)
        self.assertEqual(actor.spec,before)
        self.assertEqual(actor.form,'테라스탈')
        e.end_encounter(round_elapsed_seconds=0)
        generic=deepcopy(actor.spec[HOME.KEY])  # the generic source owns its own encounter-end lifetime
        FORMS.tera_exit(actor,engine=e)
        restored=Engine.import_state(self.r,e.export_state())
        actual=next(a for a in restored.time_actors() if a.entity_id==actor.entity_id)
        restored.start_round([actual])
        self.assertEqual(actual.form,'테라스탈')
        self.assertEqual(actual.spec[FORMS.STATE]['tera_change']['action'],'free')
        self.assertEqual(actual.spec[HOME.KEY],generic)

    def test_zygarde_actual_owned_object_must_be_a_cube(self):
        actor=self.pokemon('zygarde-wrong-object',species='지가르데',capabilities=('지가르데 세포',))
        e=self.fixture(actor)
        obj=self.physical(e,actor,'csv/not-a-cube','item/녹슨검',kind='physical_object')
        obj['zygarde_cells']={'available':100,'assemblies':[]}
        before=e.export_state()
        with self.assertRaises(ValueError):
            FORMS.configure_zygarde(e,actor,obj['id'],cells=10,form_percent=10)
        self.assertEqual(e.export_state(),before)

    def test_zygarde_cube_actual_forms_cells_learning_and_irreversible_ability(self):
        actor=self.pokemon('cube-owner',species='지가르데',capabilities=('지가르데 세포',))
        actor.spec['tutor_points']=6
        target=self.pokemon('cube-native-target')
        e=self.fixture(actor,target)
        cube=self.physical(e,actor,'csv/real-cube','item/지가르데큐브',kind='physical_object')
        cube['zygarde_cells']={'available':160,'assemblies':[]}
        old_form=actor.form
        before=e.export_state()
        with self.assertRaises(ValueError):FORMS.configure_zygarde(e,actor,cube['id'],cells=50,form_percent=10)
        self.assertEqual(e.export_state(),before)
        for count in (10,50):
            FORMS.configure_zygarde(e,actor,cube['id'],cells=count,form_percent=count)
            self.assertEqual(actor.form,str(count)+'%폼')
            self.assertEqual(e._physical_objects[cube['id']]['zygarde_cells']['available'],160-count)
            FORMS.configure_zygarde(e,actor,cube['id'],cells=count,form_percent=count,decompose=True)
            self.assertEqual(actor.form,old_form)
            self.assertEqual(e._physical_objects[cube['id']]['zygarde_cells']['available'],160)
        FORMS.configure_zygarde(e,actor,cube['id'],cells=100,form_percent=10,power_construct=True)
        self.assertEqual(actor.form,'10%폼')
        self.assertIn('스웜체인지',actor.abilities)
        self.assertNotIn('오라브레이크 [Playtest]',actor.abilities)
        self.assertEqual(actor.spec[FORMS.STATE]['zygarde']['source_correction']['original'],'스윔페인지')
        for move,cost in (('move/화염방사',1),('move/코어퍼니셔',2),('move/코어퍼니셔',0)):
            before=e.export_state()
            with self.assertRaises(ValueError):FORMS.teach_zygarde_move(e,actor,move,tutor_points=cost)
            self.assertEqual(e.export_state(),before)
        for move in ('move/코어퍼니셔','move/용의춤','move/신속'):
            FORMS.teach_zygarde_move(e,actor,move,tutor_points=1)
            self.assertIn(move,GRANTS.effective(actor,'moves'))
        self.assertEqual(actor.spec['tutor_points'],3)
        before=e.export_state()
        with self.assertRaises(ValueError):FORMS.teach_zygarde_move(e,actor,'move/코어퍼니셔',tutor_points=1)
        self.assertEqual(e.export_state(),before)
        extra=self.pokemon('other-cube-owner',species='지가르데',capabilities=('지가르데 세포',))
        extra.spec['tutor_points']=2
        other=self.fixture(extra)
        other_cube=self.physical(other,extra,'csv/other-cube','item/지가르데큐브',kind='physical_object')
        other_cube['zygarde_cells']={'available':10,'assemblies':[]}
        FORMS.configure_zygarde(other,extra,other_cube['id'],cells=10,form_percent=10)
        for move in ('move/사우전드애로','move/사우전드웨이브'):
            FORMS.teach_zygarde_move(other,extra,move,tutor_points=1)
            self.assertIn(move,extra.moves)
        self.assertEqual(extra.spec['tutor_points'],0)
        before=other.export_state()
        with self.assertRaisesRegex(ValueError,'Tutor Points'):
            FORMS.teach_zygarde_move(other,extra,'move/용의춤',tutor_points=1)
        self.assertEqual(other.export_state(),before)
        restored=Engine.import_state(self.r,e.export_state())
        actual=next(a for a in restored.time_actors() if a.entity_id==actor.entity_id)
        FORMS.configure_zygarde(restored,actual,cube['id'],cells=100,form_percent=50,power_construct=True)
        self.assertEqual(actual.form,'50%폼')
        self.assertEqual(restored._physical_objects[cube['id']]['zygarde_cells']['available'],60)
        before=restored.export_state()
        with self.assertRaisesRegex(ValueError,'cannot be decomposed'):
            FORMS.configure_zygarde(restored,actual,cube['id'],cells=100,form_percent=50,power_construct=True,decompose=True)
        self.assertEqual(restored.export_state(),before)
        self.assertIn('스웜체인지',actual.abilities)
        target=next(a for a in restored.time_actors() if a.entity_id==target.entity_id)
        restored.start_round([actual,target]);restored.start_of_turn(actual,initiative_count=20)
        with patch.object(restored,'d20',return_value=20):
            restored.use_move(actual,target,'move/코어퍼니셔',set_damage=True)
        restored.end_of_turn(actual)
        restored._physical_objects[cube['id']]['owner_id']=target.entity_id
        before=restored.export_state()
        with self.assertRaises(ValueError):FORMS.teach_zygarde_move(restored,actual,'move/사우전드애로',tutor_points=1)
        self.assertEqual(restored.export_state(),before)

    def test_necrozma_actual_species_full_projection_and_save_release(self):
        for species,signature,form in (('루나아라','move/섀도레이','네크로즈마 새벽의 날개'),
                                      ('솔가레오','move/메테오드라이브','네크로즈마 황혼의 갈기')):
            with self.subTest(species=species):
                actor=self.pokemon('merge-user',species='네크로즈마',level=80,capabilities=('바이러스 합체',),types=('에스퍼',))
                partner=self.pokemon('별이',species=species,types=('에스퍼','고스트'),capabilities=('바이러스 합체','혼연일체'))
                target=self.pokemon('merge-target')
                actor.spec['movement'].update(sky=2,swim=7,high_jump=1,long_jump=5,power=3)
                partner.spec['movement'].update(sky=8,swim=3,burrow=4,high_jump=3,long_jump=2,power=9)
                partner.movement=9
                partner.spec['skills']={'육상':'4d6+2','곡예':'expert','전투':3,'은신':6,'통찰':2}
                e=self.fixture(actor,partner,target)
                before=(list(actor.types),deepcopy(actor.spec['skills']),actor.movement,actor.form)
                FORMS.merge_necrozma(e,actor,partner,willing=True)
                self.assertEqual(actor.form,form)
                self.assertIn(signature,actor.moves)
                values=MOVE.capabilities(e,actor,environment=False)
                for field,value in dict(land=9,sky=8,swim=7,burrow=4).items():
                    self.assertEqual(values[field],value)
                for skill,dice in (('육상',5),('곡예',6),('전투',4),('은신',6),('통찰',3)):
                    self.assertEqual(SKILLS.rank(self.r,actor,skill)[2],dice)
                roll=e.skill_roll(actor,'육상',fixed=[1]*5)
                self.assertEqual(roll.total,7)
                import state_fields as FIELDS
                permanent=deepcopy(actor.spec['skills'])
                permanent.update({'육상':'2d6+3','지도읽기':5})
                FIELDS.base_patch(actor,{'skills':permanent},reason='actual GM edit during merge',source='gm/merge-skill-edit')
                self.assertEqual(SKILLS.rank(self.r,actor,'육상')[2],5)
                before=(before[0],permanent,before[2],before[3])
                for operation in (lambda:FORMS.merge_necrozma(e,partner,target,willing=True),
                                  lambda:FORMS.mount_as_one(e,partner,target,ability='정전기',gm_mount_reason='GM suitable mount')):
                    snapshot=e.export_state()
                    with self.assertRaisesRegex(ValueError,'independently'):operation()
                    self.assertEqual(e.export_state(),snapshot)
                e.start_round([actor,target]);e.start_of_turn(actor,initiative_count=20)
                snapshot=e.export_state()
                with self.assertRaisesRegex(ValueError,'independently'):e.use_move(partner,target,'move/몸통박치기')
                self.assertEqual(e.export_state(),snapshot)
                with patch.object(e,'d20',return_value=20):e.use_move(actor,target,signature,set_damage=True)
                e.end_of_turn(actor)
                restored=Engine.import_state(self.r,e.export_state())
                current={a.entity_id:a for a in restored.time_actors()}
                actual,other=current[actor.entity_id],current[partner.entity_id]
                self.assertFalse(other.on_field)
                GRANTS.numeric(actual,'movement',2,'independent-movement')
                FORMS.release_necrozma(restored,actual)
                self.assertTrue(other.on_field)
                self.assertEqual((actual.types,actual.spec['skills'],actual.movement,actual.form),(before[0],before[1],before[2]+2,before[3]))
                self.assertEqual(SKILLS.rank(restored.r,actual,'육상')[2],2)
                self.assertEqual(SKILLS.rank(restored.r,actual,'지도읽기')[2],5)
                self.assertNotIn(signature,actual.moves)

    def test_necrozma_nickname_does_not_grant_species_rights_and_slots_apply(self):
        actor=self.pokemon('arbitrary-merge',species='네크로즈마',capabilities=('바이러스 합체',),level=30)
        partner=self.pokemon('루나아라',species='피카츄')
        e=self.fixture(actor,partner)
        row=FORMS.merge_necrozma(e,actor,partner,willing=True,signature_move='move/전광석화')
        self.assertEqual(row['signature_move'],'move/전광석화')
        self.assertNotIn('move/섀도레이',actor.moves)
        FORMS.release_necrozma(e,actor)
        before=e.export_state()
        with self.assertRaises(ValueError):FORMS.merge_necrozma(e,actor,partner,willing=True,signature_move='move/화염방사')
        self.assertEqual(e.export_state(),before)
        full=self.pokemon('full-merge',species='네크로즈마',capabilities=('바이러스 합체',),moves=tuple(list(self.r.moves)[:6]))
        moon=self.pokemon('moon',species='루나아라')
        e=self.fixture(full,moon)
        before=e.export_state()
        with self.assertRaisesRegex(ValueError,'capacity'):FORMS.merge_necrozma(e,full,moon,willing=True)
        self.assertEqual(e.export_state(),before)

    def test_necrozma_power_jump_real_actions_live_partner_and_restore(self):
        import capability_actions as LOAD
        import jump_actions as JUMP
        from grid import Grid
        from copy import copy
        actor=self.pokemon('physical-merger',species='네크로즈마',capabilities=('바이러스 합체',),types=('에스퍼',))
        partner=self.pokemon('physical-partner',species='루나아라',types=('에스퍼','고스트'))
        target=self.pokemon('physical-observer')
        actor.spec['size']='소형'
        actor.spec['movement'].update(power=3,high_jump=1,long_jump=1)
        partner.spec['movement'].update(power=9,high_jump=3,long_jump=4)
        e=self.fixture(actor,partner,target)
        e.grid=Grid(20,20);actor.pos=(1,1);target.pos=(10,10)
        self.assertEqual(LOAD.power(actor),3)
        self.assertEqual(JUMP.limits(actor),{'high_jump':1,'long_jump':1})
        FORMS.merge_necrozma(e,actor,partner,willing=True)
        self.assertEqual(LOAD.power(actor),9)
        self.assertEqual(JUMP.limits(actor),{'high_jump':3,'long_jump':4})
        self.assertEqual(e.gm.set_carried_objects(actor,[{'id':'csv/merged-load','weight_kg':40}],reason='actual forty kg load')['band'],'normal')
        e.start_round([actor,target]);e.start_of_turn(actor,initiative_count=20)
        result=e.jump(actor,(5,1),jump_id='csv/merged-jump',apex_height=3,landing_altitude=3,gm_distance=5,difficult=False,clear_path=True,reason_text='actual copied high and long jump to GM-confirmed raised surface')
        self.assertTrue(result['landed']);self.assertEqual(actor.pos,(5,1))
        e.end_of_turn(actor)
        values=dict(partner.spec['movement'],power=10,high_jump=4,long_jump=6)
        MOVE.set_capabilities(e,partner,values,basis='current',reason_text='GM observes actual partner capabilities during merge')
        self.assertEqual(LOAD.power(actor),10)
        self.assertEqual(JUMP.limits(actor),{'high_jump':4,'long_jump':6})
        import state_fields as FIELDS
        skills=dict(partner.spec['skills'],육상='3d6+4')
        FIELDS.base_patch(partner,{'skills':skills},reason='GM updates actual partner skill during merge',source='gm/current-partner-skill')
        self.assertEqual(SKILLS.rank(e.r,actor,'육상')[2],4)
        self.assertEqual(e.skill_roll(actor,'육상',fixed=[1]*4).total,8)
        restored=Engine.import_state(self.r,e.export_state())
        current={a.entity_id:a for a in restored.time_actors()}
        actual,other=current[actor.entity_id],current[partner.entity_id]
        self.assertIs(getattr(actual,FORMS.MERGE_WORLD),restored)
        self.assertIs(getattr(actual,FORMS.MERGE_PARTNER),other)
        self.assertEqual(LOAD.power(actual),10)
        self.assertEqual(JUMP.limits(actual),{'high_jump':4,'long_jump':6})
        self.assertEqual(SKILLS.rank(restored.r,actual,'육상')[2],4)
        setattr(actual,FORMS.MERGE_PARTNER,copy(other))
        try:
            with self.assertRaises(ValueError):LOAD.power(actual)
        finally:setattr(actual,FORMS.MERGE_PARTNER,other)
        FORMS.release_necrozma(restored,actual)
        self.assertFalse(hasattr(actual,FORMS.MERGE_PARTNER));self.assertFalse(hasattr(actual,FORMS.MERGE_WORLD))
        self.assertEqual(LOAD.power(actual),3)
        self.assertEqual(JUMP.limits(actual),{'high_jump':1,'long_jump':1})
        self.assertEqual(LOAD.load(actual)['band'],'staggering')

    def test_as_one_native_command_target_ability_ball_body_and_naturewalk(self):
        rider=self.pokemon('rider',species='버드렉스',types=('에스퍼','풀'),capabilities=('혼연일체',))
        rider.spec['naturewalk']='숲'
        mount=self.pokemon('눈송이',species='블리자포스',types=('얼음',),capabilities=('탑승 2','바이러스 합체','혼연일체'),abilities=('백의울음',))
        mount.spec['naturewalk']='바다'
        mount.spec['size']='대형';mount.spec['weight_class']=6;mount.movement=9
        target=self.pokemon('mount-target')
        e=self.fixture(rider,mount,target)
        old=(rider.spec['size'],rider.weight_class,list(rider.types),rider.movement)
        row=FORMS.mount_as_one(e,rider,mount,ability='백의울음')
        self.assertEqual(row['ball_owner_id'],rider.entity_id)
        self.assertEqual((rider.spec['size'],rider.weight_class,rider.types),('대형',6,['에스퍼','얼음']))
        self.assertEqual(MOVE.capabilities(e,rider)['land'],old[3])
        self.assertEqual(MOVE.naturewalk_terrains(e,rider),frozenset((MOVE.terrain_type('바다'),)))
        self.assertIn('백의울음',rider.abilities);self.assertEqual(mount.abilities,[])
        self.assertIn('move/블리자드랜스',rider.moves)
        e.start_round([rider,target]);e.start_of_turn(rider,initiative_count=20)
        for actor,victim in ((mount,target),(target,mount)):
            before=e.export_state()
            with self.assertRaisesRegex(ValueError,'independently'):e.use_move(actor,victim,'move/몸통박치기')
            self.assertEqual(e.export_state(),before)
        with self.assertRaisesRegex(ValueError,'independently'):e.activate_ability(mount,'백의울음',target)
        with self.assertRaisesRegex(ValueError,'independently'):e.activate_ability(target,'통찰',mount)
        import action_lifecycle as ACTION
        with self.assertRaisesRegex(ValueError,'independently'):ACTION.status_permission(e,mount,'shift')
        # This clause grants use permission. Admission is its native consumer;
        # each Move's own area/effect implementation remains a separate clause.
        import frequency as FREQ
        from encounter import usable_moves
        self.assertEqual(e._ruleset_move(rider,'move/블리자드랜스'),'move/블리자드랜스')
        self.assertTrue(FREQ.move_allowed(e,rider,'move/블리자드랜스')[0])
        self.assertIn('move/블리자드랜스',usable_moves(e,rider))
        for operation in (lambda:FORMS.merge_necrozma(e,mount,target,willing=True),
                          lambda:FORMS.mount_as_one(e,mount,target,ability='정전기',gm_mount_reason='GM suitable mount')):
            snapshot=e.export_state()
            with self.assertRaisesRegex(ValueError,'independently'):operation()
            self.assertEqual(e.export_state(),snapshot)
        e.end_of_turn(rider)
        e.gm.recall(rider,reason='actual combined ball recall')
        self.assertFalse(rider.on_field);self.assertFalse(mount.on_field)
        restored=Engine.import_state(self.r,e.export_state())
        current={a.entity_id:a for a in restored.time_actors()}
        rider,mount=current[rider.entity_id],current[mount.entity_id]
        e=restored
        self.assertFalse(rider.on_field);self.assertFalse(mount.on_field)
        self.assertEqual(rider.spec[FORMS.STATE]['as_one']['mount_id'],mount.entity_id)
        self.assertEqual(mount.spec['off_field_reason'],{'kind':'as_one_mount','owner_id':rider.entity_id})
        before=e.export_state()
        with self.assertRaisesRegex(ValueError,'independently'):e.gm.recall(mount,reason='invalid independent ball')
        self.assertEqual(e.export_state(),before)
        with self.assertRaisesRegex(ValueError,'independently'):e.gm.send_out(mount,reason='invalid independent send')
        self.assertEqual(e.export_state(),before)
        e.gm.send_out(rider,reason='same combined Pokemon returns')
        self.assertTrue(rider.on_field);self.assertFalse(mount.on_field)
        actual,other=rider,mount
        FORMS.dismount_as_one(e,actual)
        self.assertTrue(other.on_field)
        self.assertEqual((actual.spec['size'],actual.weight_class,actual.types,actual.movement),old)
        self.assertEqual(MOVE.naturewalk_terrains(e,actual),frozenset((MOVE.terrain_type('숲'),)))
        self.assertEqual(other.abilities,['백의울음'])
        self.assertNotIn('move/블리자드랜스',actual.moves)

    def test_as_one_both_native_faint_directions_and_source_rejections(self):
        for faint_mount in (False,True):
            rider=self.pokemon('paired-rider',species='버드렉스',capabilities=('혼연일체',))
            mount=self.pokemon('밤',species='레이스포스',capabilities=('탑승 2',),abilities=('ability/흑의울음-2',))
            e=self.fixture(rider,mount)
            row=FORMS.mount_as_one(e,rider,mount,ability='ability/흑의울음-2')
            self.assertIn('ability/흑의울음-2',rider.abilities)
            self.assertEqual(row['ability_source_id'],'ability/흑의울음-2')
            self.assertIn('move/아스트랄비트',rider.moves)
            self.assertEqual(e._ruleset_move(rider,'move/아스트랄비트'),'move/아스트랄비트')
            victim=mount if faint_mount else rider
            e.lose_hp(victim,victim.hp,source='condition/paired-faint',unpreventable=True)
            self.assertTrue(rider.fainted);self.assertTrue(mount.fainted)
            self.assertEqual((rider.hp,mount.hp),(0,0))
            import life
            self.assertFalse(life.faint(e,rider));self.assertFalse(life.faint(e,mount))
            self.assertIn('as_one',rider.spec[FORMS.STATE])

    def test_as_one_gm_mount_exception_preserves_actual_species_and_basic_source(self):
        rider=self.pokemon('gm-rider',species='버드렉스',capabilities=('혼연일체',))
        mount=self.pokemon('레이스포스',species='피카츄',abilities=('정전기','불가사의부적','긴장감'))
        e=self.fixture(rider,mount)
        before=e.export_state()
        with self.assertRaises(ValueError):FORMS.mount_as_one(e,rider,mount,ability='정전기')
        self.assertEqual(e.export_state(),before)
        for ability in ('불가사의부적','긴장감'):
            with self.assertRaises(ValueError):FORMS.mount_as_one(e,rider,mount,ability=ability,gm_mount_reason='GM accepts this mount')
            self.assertEqual(e.export_state(),before)
        FORMS.mount_as_one(e,rider,mount,ability='정전기',gm_mount_reason='GM accepts this mount')
        self.assertIn('정전기',rider.abilities)
        self.assertNotIn('move/아스트랄비트',rider.moves)
        before=e.export_state()
        with self.assertRaisesRegex(ValueError,'independently'):e.gm.send_out(mount,reason='removed GM mount has no independent body')
        self.assertEqual(e.export_state(),before)

    def test_weapon_union_two_actual_items_permissions_faint_and_exit(self):
        for species,item,form,move in (('자시안','item/녹슨검','검왕','move/거수참'),
                                     ('자마젠타','item/녹슨방패','방패왕','move/거수탄')):
            with self.subTest(species=species):
                actor=self.pokemon('union-'+species,species=species,capabilities=('무기합일',))
                target=self.pokemon('union-target')
                target.stats['def'] = 1000
                e=self.fixture(actor,target)
                self.physical(e,actor,'csv/union-'+species,item,kind='physical_object')
                FORMS.weapon_union(e,actor,'csv/union-'+species)
                self.assertEqual(actor.form,form)
                self.assertIn(move, GRANTS.effective(actor, 'moves'))
                e.start_round([actor,target]);e.start_of_turn(actor,initiative_count=20)
                with patch.object(e,'d20',return_value=20):
                    e.use_move(actor,target,move,set_damage=True)
                e.end_of_turn(actor)
                self.assertTrue(FORMS.end_weapon_union(e,actor))
                self.assertNotIn(move, GRANTS.effective(actor, 'moves'))
                FORMS.weapon_union(e,actor,'csv/union-'+species)
                e.lose_hp(actor,actor.hp,source='condition/test-faint',unpreventable=True)
                self.assertNotEqual(actor.form,form)
                self.assertNotIn(move, GRANTS.effective(actor, 'moves'))
        for species,item,form in (('자시안 검왕','item/녹슨검','검왕'),('자시안 역전의 용사','item/녹슨검','검왕'),
                                  ('자마젠타 방패왕','item/녹슨방패','방패왕'),('자마젠타 역전의 용사','item/녹슨방패','방패왕')):
            with self.subTest(actual_stock_form=species):
                actor=self.pokemon('stock-form',species=species,capabilities=('무기합일',))
                e=self.fixture(actor);self.physical(e,actor,'csv/stock-form',item,kind='physical_object')
                FORMS.weapon_union(e,actor,'csv/stock-form')
                self.assertEqual(actor.form,form)
                self.assertTrue(FORMS.end_weapon_union(e,actor))
        for name,item in (('자시안','item/녹슨검'),('자마젠타','item/녹슨방패')):
            custom=deepcopy(self.r.species['pokemon/피카츄'])
            custom.update(id='custom/모방-'+name,name=name,source='custom',_source={'file':'custom/source-bound-weapon-test'})
            with self.subTest(custom_species=name),patch.dict(self.r.species,{custom['id']:custom}):
                actor=self.pokemon('real-custom-body',species=custom['id'],capabilities=('무기합일',))
                e=self.fixture(actor);self.physical(e,actor,'csv/custom-weapon',item,kind='physical_object')
                before=e.export_state()
                with self.assertRaisesRegex(ValueError,'limited'):FORMS.weapon_union(e,actor,'csv/custom-weapon')
                self.assertEqual(e.export_state(),before)
