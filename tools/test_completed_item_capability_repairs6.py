"""Exact CSV capability obligations through actual material/source consumers."""
from copy import deepcopy, copy
from unittest.mock import patch
import unittest
import test_category2_csv_remaining_item_contracts as _fixture_test_category2_csv_remaining_item_contracts
from engine import Engine, Rules
import csv_item_capability_contracts as CAP
import state_grants as G
import item_maturation as M
import world_entities as W


class ItemCapabilityRepairs6(unittest.TestCase):
    setUpClass=classmethod(_fixture_test_category2_csv_remaining_item_contracts.RemainingCsvItemContractTests.setUpClass.__func__)
    pokemon=_fixture_test_category2_csv_remaining_item_contracts.RemainingCsvItemContractTests.pokemon
    trainer=_fixture_test_category2_csv_remaining_item_contracts.RemainingCsvItemContractTests.trainer
    fixture=_fixture_test_category2_csv_remaining_item_contracts.RemainingCsvItemContractTests.fixture
    physical=_fixture_test_category2_csv_remaining_item_contracts.RemainingCsvItemContractTests.physical
    equip=_fixture_test_category2_csv_remaining_item_contracts.RemainingCsvItemContractTests.equip

    def sessions(self,*actors):
        e=Engine(self.r,seed=831785,session_frequency=True,defer_session_refresh=False)
        for actor in sorted(actors,key=lambda c:c.kind!='trainer'):e.gm.add_combatant(actor)
        e.begin_session('session/0',actors)
        return e

    def actual(self,e,uid):return W.actor_index(e)[uid]

    def test_juicer_real_sessions_physical_candy_and_single_collection_restore(self):
        actor=self.pokemon('session-shuckle',species='단단지',capabilities=('과즙기',))
        owner=self.trainer('shuckle-owner');actor.spec['trainer_id']=owner.entity_id
        e=self.sessions(actor,owner)
        berry=self.equip(e,actor,'berry/session','item/오랭열매')
        started=CAP.juicer_begin(e,actor,berry['id'])
        before=e.export_state()
        with self.assertRaises(ValueError):CAP.juicer_session(e,actor)
        self.assertEqual(e.export_state(),before)
        e.advance_time(2592000,[actor])
        self.assertEqual(actor.spec[M.KEY][started['id']]['stage'],'held')
        e.start_round([actor,owner]);e.end_encounter()
        self.assertTrue(e.unresolved_time_intervals)
        e.begin_session('session/1',[actor,owner])
        out=CAP.juicer_session(e,actor)
        self.assertEqual(out['phase'],'juice')
        self.assertTrue(e._physical_objects[berry['id']]['consumed'])
        self.assertEqual(e._physical_objects[berry['id']]['consumed']['source'],'item/오랭열매')
        with self.assertRaises(ValueError):CAP.juicer_session(e,actor)
        saved=Engine.import_state(self.r,e.export_state())
        actor,owner=self.actual(saved,actor.entity_id),self.actual(saved,owner.entity_id);e=saved
        for number in (2,3,4):
            e.begin_session('session/'+str(number),[actor,owner])
            self.assertEqual(CAP.juicer_session(e,actor)['phase'],'juice')
        e.begin_session('session/5',[actor,owner])
        self.assertEqual(CAP.juicer_session(e,actor)['phase'],'candy')
        e.pokemon_activity(owner,'collect_matured_item',target=actor,batch_id=started['id'],reason='one real session Candy')
        self.assertEqual(owner.spec['items'][M.policy(self.r)['output_item']],1)
        before=e.export_state()
        with self.assertRaises(ValueError):e.pokemon_activity(owner,'collect_matured_item',target=actor,batch_id=started['id'],reason='duplicate collection')
        self.assertEqual(e.export_state(),before)
        self.assertTrue(e.validate_state()['valid'])

    def test_juicer_actual_bottle_and_drink_use_shared_material_owner(self):
        actor=self.pokemon('bottle-shuckle',species='단단지',capabilities=('과즙기',))
        owner=self.trainer('bottle-owner');actor.spec['trainer_id']=owner.entity_id
        e=self.sessions(actor,owner)
        self.equip(e,actor,'berry/bottle','item/오랭열매')
        key=CAP.juicer_begin(e,actor,'berry/bottle')['id']
        self.equip(e,owner,'bottle/actual','item/빈병')
        e.gm.observe_empty_container(owner,container_selection='bottle/actual',reason='actual empty glass bottle')
        e.begin_session('session/1',[actor,owner]);CAP.juicer_session(e,actor)
        out=CAP.juicer_session(e,actor,bottled=True,container_selection='bottle/actual',recipient=owner,reason='actual shell Juice into actual bottle')
        self.assertEqual(out['stage'],'bottled')
        self.assertNotIn('item/나무열매쥬스',actor.spec['items'])
        import item_stock as STOCK,item_containers as CONTAINERS
        with self.assertRaises(ValueError):STOCK.prepare(e,owner,'item/빈병',held_selection='bottle/actual')
        self.assertEqual(CONTAINERS.body(e,owner,'bottle/actual')['id'],'bottle/actual')
        with self.assertRaises(ValueError):CONTAINERS.body(e,actor,'bottle/actual')
        obj=e._physical_objects['bottle/actual'];valid=deepcopy(obj)
        for field,value in (('telekinetic_holder_id',owner.entity_id),('equipped_by',actor.entity_id),('carrier_id',actor.entity_id)):
            obj[field]=value;before=deepcopy(obj)
            with self.assertRaises(ValueError):CONTAINERS.body(e,owner,'bottle/actual')
            self.assertEqual(obj,before);obj.clear();obj.update(deepcopy(valid))
        obj['carrier_id']=owner.entity_id
        for flag in ('blocked_actions','failure_pending'):
            owner.spec['_carried_load']={'objects':[{'id':'bottle/actual'}],flag:True}
            with self.assertRaises(ValueError):CONTAINERS.body(e,owner,'bottle/actual')
        owner.spec.pop('_carried_load');obj.clear();obj.update(deepcopy(valid))
        e._physical_objects.pop('bottle/actual')
        with self.assertRaises(ValueError):CONTAINERS.body(e,owner,'bottle/actual')
        e._physical_objects['bottle/actual']=obj
        owner.hp=1
        result=e.use_item(owner,'item/나무열매쥬스',owner,container_selection='bottle/actual',duration_minutes=1,duration_reason='actual bottled Juice drunk')
        self.assertIsInstance(result,dict,str(result))
        self.assertEqual(result['status'],'consumed')
        self.assertGreater(owner.hp,1)
        self.assertNotIn('consumed',e._physical_objects['bottle/actual'])
        self.assertIsNone(e._physical_objects['bottle/actual'][CONTAINERS.KEY]['current'])
        before=e.export_state()
        with self.assertRaises(ValueError):e.use_item(owner,'item/나무열매쥬스',container_selection='bottle/actual',duration_minutes=1,duration_reason='duplicate Juice intake')
        self.assertEqual(e.export_state(),before)
        self.assertEqual(actor.spec[M.KEY][key]['product']['location'],'container')
        self.assertTrue(e.validate_state()['valid'])

    def test_juicer_actual_berry_snack_cancels_and_source_access_is_live(self):
        actor=self.pokemon('snack-shuckle',species='단단지',capabilities=('과즙기',))
        e=self.sessions(actor)
        self.equip(e,actor,'berry/snack','item/오랭열매')
        key=CAP.juicer_begin(e,actor,'berry/snack')['id']
        e.use_item(actor,'item/오랭열매',actor,held_selection='berry/snack',duration_minutes=1,duration_reason='actual held Berry eaten as Snack')
        self.assertEqual(CAP.juicer_session(e,actor,berry_consumed=True)['cancelled'],True)
        self.assertEqual(actor.spec[M.KEY][key]['stage'],'cancelled')
        e.begin_session('session/1',[actor]);self.assertEqual(actor.spec[M.KEY][key]['stage'],'cancelled')
        self.equip(e,actor,'berry/lost','item/오랭열매');CAP.juicer_begin(e,actor,'berry/lost')
        G.set_baseline(actor,'capabilities',[])
        before=e.export_state()
        with self.assertRaises(ValueError):CAP.juicer_session(e,actor)
        self.assertEqual(e.export_state(),before)
        G.set_baseline(actor,'capabilities',['과즙기'])
        e.begin_session('session/2',[actor])
        before=e.export_state()
        with self.assertRaises(ValueError):CAP.juicer_session(e,actor)
        self.assertEqual(e.export_state(),before)
        e._physical_objects['berry/lost']['telekinetic_holder_id']=actor.entity_id
        with self.assertRaises(ValueError):CAP.juicer_begin(e,actor,'berry/lost')

    def test_navigation_actual_five_minute_steps_cooperation_duplicates_and_restore(self):
        actor=self.pokemon('navigator',capabilities=('에스퍼 네비게이터',))
        partner=self.pokemon('navigator-partner',capabilities=('에스퍼 네비게이터',))
        e=self.fixture(actor,partner)
        CAP.start_navigation(e,actor,'route/star',lightyears=3)
        self.assertTrue(CAP.navigation_jump(actor,'route/star')['gm_consequence_required'])
        for who,total,key in ((actor,20,'first'),(partner,21,'second')):
            CAP.navigation_contribute(e,actor,who,'route/star',skill='집중',total=total,check_id=key)
        self.assertEqual(e.elapsed_seconds,600)
        self.assertEqual(CAP.navigation_jump(actor,'route/star')['total'],41)
        saved=Engine.import_state(self.r,e.export_state())
        actor,partner=self.actual(saved,actor.entity_id),self.actual(saved,partner.entity_id);e=saved
        CAP.navigation_contribute(e,actor,partner,'route/star',skill='집중',total=21,check_id='second')
        self.assertEqual(e.elapsed_seconds,600)
        CAP.navigation_check(e,actor,'route/star',skill='지각',total=18,check_id='third')
        self.assertEqual(e.elapsed_seconds,900)
        self.assertEqual(CAP.navigation_jump(actor,'route/star'),{'safe':True,'total':59,'dc':45,'gm_consequence_required':False})
        CAP.navigation_check(e,actor,'route/star',skill='지각',total=18,check_id='third')
        self.assertEqual(e.elapsed_seconds,900)
        before=e.export_state()
        with self.assertRaises(ValueError):CAP.navigation_check(e,actor,'route/star',skill='지각',total=19,check_id='third')
        self.assertEqual(e.export_state(),before)
        for distance in (float('nan'),float('inf'),-1):
            with self.assertRaises(ValueError):CAP.start_navigation(e,actor,'route/invalid',lightyears=distance)
        with self.assertRaises(ValueError):CAP.navigation_contribute(e,actor,copy(partner),'route/star',skill='집중',total=1)
        self.assertTrue(e.validate_state()['valid'])

    def test_all_eleven_printed_poison_moves_derive_and_withdraw_live_learning(self):
        import struggle_capabilities as STRUGGLE
        for name in sorted(CAP.POISON_MOVES):
            with self.subTest(name=name):
                mid=self.r.move_id(name)
                actor=self.pokemon('learned-poison',moves=(mid,))
                target=self.pokemon('poison-target');target.pos=(1,0)
                e=self.fixture(actor,target)
                self.assertTrue(CAP.has(actor,'독샘'))
                self.assertNotIn('독샘',actor.spec['capabilities'])
                for special in (False,True):
                    move=STRUGGLE.prepare(e,actor,self.r.move('struggle'),{'capability':'독샘','special':special})
                    self.assertEqual((move['type'],move['class']),('독','특수' if special else '물리'))
                if name=='독침천발':
                    e.start_round([actor,target]);e.start_of_turn(actor)
                    observed=[];original=e.damage_base
                    def damage(c,m,**kw):observed.append((m['type'],m['class']));return original(c,m,**kw)
                    with patch.object(e,'damage_base',side_effect=damage),patch.object(e,'d20',return_value=20):
                        e.use_move(actor,target,'struggle',set_damage=True,struggle_choice={'capability':'독샘','special':True})
                    self.assertIn(('독','특수'),observed)
                G.set_baseline(actor,'moves',[])
                self.assertFalse(CAP.has(actor,'독샘'))
                with self.assertRaises(ValueError):STRUGGLE.prepare(e,actor,self.r.move('struggle'),{'capability':'독샘','special':False})
                G.grant_moves(actor,[mid],'borrowed/poison','effect',mode='permission')
                self.assertFalse(CAP.has(actor,'독샘'))
                G.revoke(actor,'borrowed/poison',engine=e)
                G.grant_moves(actor,[mid],'learned/poison','effect',mode='learned')
                self.assertTrue(CAP.has(actor,'독샘'))
                G.revoke(actor,'learned/poison',engine=e)
                self.assertFalse(CAP.has(actor,'독샘'))

    def test_homebrew_poison_frequency_and_single_target_are_actual_learned_sources(self):
        r=Rules(self.r.root,ruleset='all');self.r=r
        cases=(
            ('At-Will','근접, 대상 1','',True),('EOT','4, 대상 1','',True),
            ('Scene','근접, 대상 1','',False),('At-Will','폭발 2','',False),
            ('EOT','4, 대상 2','',False),('EOT','4, 대상 1','통과',False),
            ('EOT','4, 대상 1, 지면통과','',True),('EOT','4, 대상 1, 통과','',False),
            ('EOT','4, targets 12','',False),('EOT','line 3, target 1','',False),
            ('At-Will','근접, target 1','지면통과',True),
            ('턴1회','4, 대상 1','',True),('임의','파열 2','',False),
            ('EOT','직선 3','',False),('EOT','4, 대상 1',['통과'],False),
            ('EOT','4, 대상 1',['지면통과'],True))
        for number,(frequency,rng,keywords,expected) in enumerate(cases):
            mid='move/custom/toxin-'+str(number)
            definition={'id':mid,'name':'GM toxin '+str(number),'type':'독','class':'물리','frequency':frequency,'range':rng,'keywords':keywords,'source':'custom','homebrew':True,'effect':''}
            r.moves[mid]=definition
        r._apply_ruleset()
        for number,(_,_,_,expected) in enumerate(cases):
            actor=self.pokemon('homebrew-poison',moves=('move/custom/toxin-'+str(number),))
            e=self.fixture(actor)
            self.assertEqual(CAP.has(actor,'독샘'),expected)
            G.set_baseline(actor,'moves',[])
            self.assertFalse(CAP.has(actor,'독샘'))

    def test_life_sense_actual_geometry_gm_basis_exclusions_and_source_revoke(self):
        actor=self.pokemon('life-observer',capabilities=('생명감지',));actor.pos=(0,0)
        target=self.pokemon('life-body');target.pos=(5,0)
        e=self.fixture(actor,target)
        self.assertTrue(CAP.sense_life(e,actor,target)['located'])
        target.pos=(6,0);self.assertFalse(CAP.sense_life(e,actor,target)['located'])
        self.assertTrue(CAP.sense_life(e,actor,target,distance_m=5,gm_basis='GM measured bodies in separate mapless rooms')['located'])
        for bad in (float('nan'),float('inf'),-1):
            with self.assertRaises(ValueError):CAP.sense_life(e,actor,target,distance_m=bad,gm_basis='bad measurement')
        with self.assertRaises(ValueError):CAP.sense_life(e,actor,target,distance_m=5)
        with self.assertRaises(ValueError):CAP.sense_life(e,actor,copy(target),distance_m=5,gm_basis='forged target')
        target.pos=(5,0)
        for kind in ('ghost','silent','dead'):
            target.types=['고스트'] if kind=='ghost' else ['노말']
            G.set_baseline(target,'capabilities',['숨죽이기'] if kind=='silent' else [])
            target.dead=kind=='dead'
            self.assertFalse(CAP.sense_life(e,actor,target)['located'])
        trainer=self.trainer('living-trainer',capabilities=('숨죽이기',));trainer.types=['고스트']
        e.gm.add_combatant(trainer)
        self.assertTrue(CAP.sense_life(e,actor,trainer,distance_m=5,gm_basis='actual living Trainer within five metres')['located'])
        G.set_baseline(actor,'capabilities',[])
        with self.assertRaises(ValueError):CAP.sense_life(e,actor,target)

    def test_tinkerer_legal_intrinsic_permission_steel_no_stab_and_replacement(self):
        import move_state as MOVES,weapon_actions as WEAPONS,held_equipment as HELD,frequency as F
        actor=self.pokemon('tinkerer',capabilities=('땜장이',),moves=(),types=('강철',))
        target=self.pokemon('scrap-target');actor.pos=(0,0);target.pos=(1,0)
        e=self.fixture(actor,target)
        for opts in ({'weapon_class':'small_melee','proficient_move':'move/강타'},
                     {'weapon_class':'large_melee','proficient_move':'move/몸통박치기'},
                     {'weapon_class':'large_melee','proficient_move':'move/일제사격'},
                     {'weapon_class':'large_melee','proficient_move':'move/출혈'}):
            before=e.export_state()
            with self.assertRaises(ValueError):CAP.configure_tinkerer(e,actor,**opts)
            self.assertEqual(e.export_state(),before)
        row=CAP.configure_tinkerer(e,actor,weapon_class='large_melee',proficient_move='move/강타',steel=True)
        self.assertNotIn('move/강타',actor.spec['moves'])
        self.assertIn('move/강타',G.effective(actor,'moves'))
        self.assertNotIn('move/강타',MOVES.owned_list(actor.spec,'moves',actor.moves,rules=actor.r))
        self.assertTrue(row['intrinsic']);self.assertTrue(row['unstealable']);self.assertFalse(HELD.any_held(actor))
        import items as ITEMS,turn as TURN
        before=e.export_state()
        with self.assertRaises(ValueError):ITEMS.transfer_equipment(e,actor,target,row['weapon_id'])
        with self.assertRaises(ValueError):TURN.unequip_weapon(e,actor,row['weapon_id'])
        self.assertEqual(e.export_state(),before)
        move=WEAPONS.prepare(e,actor,self.r.move('move/강타'),row['weapon_id'])
        self.assertEqual(move['type'],'강철');self.assertTrue(WEAPONS.excludes_stab(move))
        before=e.export_state()
        with self.assertRaises(ValueError):CAP.configure_tinkerer(e,actor,weapon_class='large_melee',proficient_move='move/백스윙')
        self.assertEqual(e.export_state(),before)
        e.start_round([actor,target]);e.start_of_turn(actor,initiative_count=20)
        observed=[];original=e.damage_base
        def damage(c,m,**kw):observed.append(deepcopy(m));return original(c,m,**kw)
        with patch.object(e,'damage_base',side_effect=damage),patch.object(e,'d20',return_value=20):e.use_move(actor,target,'move/강타',set_damage=True)
        self.assertTrue(any(m.get('_exclude_stab') and m['type']=='강철' for m in observed))
        e.end_of_turn(actor);e.end_encounter(round_elapsed_seconds=0);F.new_day(actor)
        CAP.configure_tinkerer(e,actor,weapon_class='large_melee',proficient_move='move/백스윙',master_move='move/출혈')
        self.assertNotIn('move/강타',G.effective(actor,'moves'));self.assertIn('move/백스윙',G.effective(actor,'moves'))
        with self.assertRaises(ValueError):self.equip(e,actor,'forbidden/held','item/오랭열매')
        saved=Engine.import_state(self.r,e.export_state());actor=self.actual(saved,actor.entity_id);e=saved
        self.assertEqual(HELD.capacity(actor)['maximum'],0)
        G.set_baseline(actor,'capabilities',[])
        self.assertIsNone(CAP.tinkerer_weapon(actor));self.assertNotIn('move/백스윙',G.effective(actor,'moves'))
        self.assertNotIn('move/백스윙',MOVES.effective_list(actor.spec,'moves',rules=actor.r))
        self.assertNotIn('move/백스윙',MOVES.owned_list(actor.spec,'moves',actor.moves,rules=actor.r))
        with self.assertRaises(ValueError):WEAPONS.prepare(e,actor,self.r.move('move/백스윙'))

    def test_tinkerer_level_held_slot_and_predicate_cannot_self_activate(self):
        import held_equipment as HELD,move_state as MOVES
        actor=self.pokemon('young-tinkerer',level=29,capabilities=('땜장이',),moves=())
        e=self.fixture(actor)
        with self.assertRaises(ValueError):CAP.configure_tinkerer(e,actor,weapon_class='large_melee',proficient_move='move/강타',master_move='move/출혈')
        actor.level=30
        self.equip(e,actor,'already/held','item/오랭열매')
        with self.assertRaises(ValueError):CAP.configure_tinkerer(e,actor,weapon_class='large_melee',proficient_move='move/강타',master_move='move/출혈')
        self.assertTrue(HELD.any_held(actor))
        forged={'required_capability':'A','grants':{'capabilities':['A'],'moves':['move/강타']}}
        spec={'capabilities':[],'moves':[],'state_grants':{'sources':{'self':forged}}}
        self.assertFalse(MOVES.source_active(spec,forged));self.assertEqual(MOVES.effective_list(spec,'moves',rules=self.r),[])
        spec['state_grants']['sources']['other']={'required_capability':'B','grants':{'capabilities':['A']}}
        spec['state_grants']['sources']['self']['grants']['capabilities']=['B']
        self.assertFalse(MOVES.source_active(spec,forged))
        self.assertEqual(MOVES.owned_list(spec,'moves',['move/강타'],rules=self.r),[])
        actor.spec['state_grants']['sources']['condition/self']=forged
        self.assertNotIn('B',G.effective(actor,'capabilities'))
        self.assertNotIn('move/강타',G.effective(actor,'moves'))

    def install_muscle(self):
        import special_entities as S,augmentation_moves as A
        self.r=Rules(self.r.root,ruleset='polygon')
        owner=self.trainer('muscle-creator');owner.spec['feats']=['feat/프로토-디자인']
        actor=self.pokemon('muscle-user');actor.spec['trainer_id']=owner.entity_id
        e=self.fixture(owner,actor)
        W.register_object(e,'implant/muscle',location={'kind':'unknown'},reason='actual installed limb augmentation')
        row={'id':'augmentation/muscle','kind':'augmentation_set','location':{'kind':'unknown'},'actor_id':actor.entity_id,
             'body_slots':['limbs'],'installations':[{'instance_id':'implant/muscle','augmentation_id':'synthetic_muscle'}],
             'allow_added_parts':False,'essence_enabled':False}
        S.observe(e,row,reason='actual installed Synthetic Muscle')
        self.assertFalse(CAP.has(actor,'개선된 인조 근육'))
        A.observe_upgrade(e,owner,actor,augmentation_set_id=row['id'],instance_id='implant/muscle',application_id='upgrade/muscle',
                          active=True,reason='actual CSV Improved Synthetic Muscle upgrade',choice='synthetic_muscle')
        self.assertNotIn('개선된 인조 근육',actor.spec['capabilities'])
        self.assertTrue(CAP.has(actor,'개선된 인조 근육'))
        return e,owner,actor

    def test_actual_installed_improved_muscle_power_jump_recovery_and_removal(self):
        import capability_actions as LOAD,jump_actions as JUMP,special_entities as S,injury_recovery as I
        from grid import Grid
        e,owner,actor=self.install_muscle()
        self.assertEqual(LOAD.power(actor),6);self.assertEqual(JUMP.limits(actor),{'high_jump':2,'long_jump':2})
        self.assertEqual(e.gm.set_carried_objects(actor,[{'id':'load/muscle','weight_kg':30}],reason='real installed muscle load')['band'],'normal')
        e.grid=Grid(10,10);actor.pos=(1,1);owner.pos=(8,8)
        e.start_round([actor,owner]);e.start_of_turn(actor)
        self.assertTrue(e.jump(actor,(3,1),jump_id='jump/muscle',apex_height=2,landing_altitude=2,gm_distance=3,difficult=False,clear_path=True,reason_text='actual two-high two-long installed muscle jump')['landed'])
        e.end_of_turn(actor);e.end_encounter(round_elapsed_seconds=0)
        e.gm.set_injuries(actor,value=5,reason='actual injuries after jump')
        e.advance_time(43199,[actor]);self.assertEqual(e.recover_injury(actor),0)
        saved=Engine.import_state(self.r,e.export_state());actor=self.actual(saved,actor.entity_id);e=saved
        e.advance_time(1,[actor]);self.assertEqual(e.recover_injury(actor),1)
        self.assertEqual(I.heal(e,actor,10,source='pokemon_center'),3)
        self.assertEqual(I.healed_today(actor),4)
        row=deepcopy(e._physical_objects['augmentation/muscle']);row['installations']=[]
        S.observe(e,row,reason='actual installed improved muscle removed')
        self.assertFalse(CAP.has(actor,'개선된 인조 근육'))
        self.assertEqual(LOAD.power(actor),4);self.assertEqual(JUMP.limits(actor),{'high_jump':1,'long_jump':1})
        self.assertEqual(I.heal(e,actor,10,source='pokemon_center'),0)
        self.assertTrue(e.validate_state()['valid'])

    def test_improved_muscle_acceleration_credits_only_live_installed_intervals(self):
        import special_entities as S,injury_recovery as I
        e,owner,actor=self.install_muscle()
        e.gm.set_injuries(actor,value=2,reason='actual injury recovery onset')
        e.advance_time(21600,[actor])
        self.assertEqual(actor.spec[I.CLOCK]['accelerated_seconds'],21600)
        row=deepcopy(e._physical_objects['augmentation/muscle']);row['augmentation_active']=False
        S.observe(e,row,reason='actual augmentation deactivated')
        e.advance_time(43199,[actor]);self.assertEqual(e.recover_injury(actor),0)
        self.assertEqual(actor.spec[I.CLOCK]['accelerated_seconds'],21600)
        e.advance_time(1,[actor]);self.assertEqual(e.recover_injury(actor),1)
        self.assertTrue(e.validate_state()['valid'])


if __name__=='__main__':unittest.main()
