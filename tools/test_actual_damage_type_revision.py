"""Native actual-type consumers; Korean-source producers and separate scene lifetime."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import math
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from builder import build_pokemon
from grid import Grid
import alternate_move_modes as ALTERNATE
import coat_effects as COATS
import declarative_move_contracts as DECLARATIVE
import effects_ext as EXT
import homebrew_state as HOME
import items as ITEMS
import world_entities as WORLD
import csv_item_physical_contracts as PHYSICAL
import test_category2_class_passive_combat_bulk as FLAME_FIXTURE


class ActualDamageTypeRevisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules=Rules(ROOT,ruleset='homebrew')
        FLAME_FIXTURE.ClassPassiveCombatBulkTests.setUpClass()

    def world(self,moves,*,types=('노말',),target_types=('노말',),target_moves=('move/몸통박치기',)):
        e=Engine(self.rules,seed=49214);e.grid=Grid(20,20)
        a=Combatant(self.rules,build_pokemon(self.rules,'이브이',30,name='Actual producer',
            moves=list(moves),abilities=[],extra={'types':list(types)}))
        t=Combatant(self.rules,build_pokemon(self.rules,'이상해꽃',60,name='Actual recipient',
            moves=list(target_moves),abilities=[],side='foe',extra={'types':list(target_types)}))
        e.gm.add_combatant(a,pos=(1,1),side='party',reason='observed source-bounded attacker')
        e.gm.add_combatant(t,pos=(2,1),side='foe',reason='observed actual recipient')
        e.begin_encounter(e.everyone);e.start_round(e.everyone);e.start_of_turn(a,initiative_count=20)
        return e,a,t

    def next_turn(self,e,a):
        e.end_of_turn(a);e.start_round(e.everyone);e.start_of_turn(a,initiative_count=20)

    def hit(self,e,a,t,uid,face=12,**options):
        with patch.object(Engine,'d20',return_value=face):
            return e.use_move(a,t,uid,set_damage=True,situational=100,**options)

    def restore(self,e,*actors):
        ids=[a.entity_id for a in actors]
        restored=Engine.import_state(e.r,json.loads(json.dumps(e.export_state(),ensure_ascii=False)))
        index=WORLD.actor_index(restored)
        return (restored,*(index[uid] for uid in ids))

    def tera(self,e,a,value):
        HOME.observe_type(e,a,value,reason='observed permanent ordinary Tera choice')
        HOME.observe_active(e,a,True,reason='observed source-bound active form')

    def expected(self,e,a,t,uid,db,bonus=0,selected=None):
        move=e.r.move(uid);stats=e.r.mech('combat/damage-formula')
        cls=('물리' if selected=='atk' else '특수') if move['class']=='가변' else move['class']
        attack=selected or stats['attack_stat_by_class'][cls]
        defense=stats['defense_stat_by_class'][cls]
        mid=e.r.mech('combat/damage-chart')['by_damage_base'][str(db)]['set']['mid']
        return max(1,mid+a.staged(attack)+bonus-t.staged(defense))

    def test_alternate_stab_membership_matrix_preview_and_final_damage(self):
        for uid,printed,actual in (('move/타오르는분노','악','불꽃'),('move/천둥차기','격투','전기')):
            for types in ((printed,),(actual,),(printed,actual),('물',)):
                for chosen in (False,True):
                    with self.subTest(move=uid,types=types,alternate=chosen):
                        e,a,t=self.world([uid],types=types)
                        if chosen:e.gm.choose_alternate_move_type(a,uid,actual,reason='source-authorized alternate choice')
                        source=deepcopy(e.r.move(uid));selected=actual if chosen else printed
                        db=source['damage_base']+(math.floor(e.formula('stab')) if selected in types else 0)
                        before=deepcopy(a.spec)
                        self.assertEqual(e.damage_base(a,source,target=t),db)
                        self.assertEqual(a.spec,before)
                        expected=math.floor(self.expected(e,a,t,uid,db)*e.type_multiplier(selected,t)[0])
                        damage=self.hit(e,a,t,uid)
                        self.assertEqual(damage,expected)
                        self.assertEqual(e.r.move(uid),source)
                        if chosen:self.assertEqual(ALTERNATE.status(a,uid)[0]['use']['actual_type'],actual)
                        self.assertTrue(e.validate_state()['valid'])

    def test_ordinary_tera_main_and_both_variants_exact_stab_plus_ten(self):
        for uid in ('move/테라버스트','move/테라버스트-물리','move/테라버스트-특수'):
            for types in (('불꽃',),('노말',)):
                with self.subTest(move=uid,original_types=types):
                    e,a,t=self.world([uid],types=types);self.tera(e,a,'불꽃')
                    move=deepcopy(e.r.move(uid));force=uid=='move/테라버스트'
                    db=move['damage_base']+(math.floor(e.formula('stab')) if force or '불꽃' in types else 0)
                    selected='spa' if uid=='move/테라버스트' else None
                    self.assertEqual(e.damage_base(a,move,target=t,versatile_stat=selected),db)
                    self.assertEqual(self.hit(e,a,t,uid,versatile_stat=selected),self.expected(e,a,t,uid,db,10,selected=selected))
                    self.assertEqual(HOME.stab_types(a),list(types));self.assertEqual(e.r.move(uid),move)
                    self.assertTrue(e.validate_state()['valid'])

    def test_plasma_fists_retains_activation_type_after_consuming_printed_normal_choice(self):
        for types in (('노말',),('전기',),('노말','전기'),('물',)):
            with self.subTest(types=types):
                e,a,t=self.world(['move/몸통박치기'],types=types,target_moves=['move/플라스마피스트'])
                e.end_of_turn(a);e.start_of_turn(t,initiative_count=19)
                self.hit(e,t,a,'move/플라스마피스트')
                self.assertEqual(len(DECLARATIVE.live(a,'next_normal_attack_type')),1)
                e.end_of_turn(t);e.start_round(e.everyone);e.start_of_turn(a,initiative_count=20)
                # Its printed type still selects the next Normal attack.
                move=deepcopy(e.r.move('move/몸통박치기'))
                db=move['damage_base']+(math.floor(e.formula('stab')) if '전기' in types else 0)
                self.assertEqual(e.damage_base(a,move,target=t),db)
                self.assertEqual(len(DECLARATIVE.live(a,'next_normal_attack_type')),1)
                self.assertEqual(self.hit(e,a,t,move['id']),self.expected(e,a,t,move['id'],db))
                self.assertFalse(DECLARATIVE.live(a,'next_normal_attack_type'))
                self.assertEqual(e.r.move(move['id']),move)
                self.assertTrue(e.validate_state()['valid'])

    def coat(self,e,a,t,source):
        e.gm.set_move(a,source,reason='observed learned source Coat move')
        with patch.object(Engine,'d20',return_value=12):
            e.use_move_on(a,t,source,e.everyone,set_damage=True)
        self.assertTrue(any(row['source']==source for row in COATS.live(t)),e.log_lines[-15:])
        self.next_turn(e,a)

    def test_native_matching_coats_use_actual_type_and_consume_once(self):
        for source,uid,actual in (('move/흙놀이','move/천둥차기','전기'),
                                  ('move/물놀이','move/타오르는분노','불꽃'),
                                  ('move/타르샷','move/타오르는분노','불꽃')):
            for restored in (False,True):
                with self.subTest(source=source,restored=restored):
                    e,a,t=self.world([uid]);self.coat(e,a,t,source)
                    e.gm.choose_alternate_move_type(a,uid,actual,reason='actual matching alternate mode')
                    if restored:e,a,t=self.restore(e,a,t)
                    record=deepcopy(next(row for row in COATS.live(t) if row['source']==source))
                    move=e.r.move(uid);mm=e.r.move_mech(uid)[0];before=e.export_state()
                    multiplier=EXT.effectiveness_hook(e,a,t,move,mm,1,{'actual_damage_type':actual})
                    self.assertEqual(multiplier,1.5 if source=='move/타르샷' else .5)
                    self.assertEqual(e.export_state(),before)
                    dealt=self.hit(e,a,t,uid);self.assertGreater(dealt,0)
                    self.assertFalse(any(row['id']==record['id'] for row in COATS.live(t)))
                    history=[row for row in t.spec[COATS.HISTORY] if row['id']==record['id']]
                    self.assertEqual(len(history),1)
                    self.assertEqual(history[0]['effect_instance']['end_event']['move_type'],actual)
                    self.assertEqual(history[0]['effect_instance']['applied_by_actor_id'],a.entity_id)
                    self.assertTrue(e.validate_state()['valid'])
                    self.assertTrue(self.restore(e,a,t)[0].validate_state()['valid'])

    def test_tar_zero_hit_consumes_water_zero_does_not_and_temp_hp_counts(self):
        for source in ('move/타르샷','move/물놀이'):
            for zero in (False,True):
                with self.subTest(source=source,zero=zero):
                    uid='move/테라버스트-특수';e,a,t=self.world([uid]);self.coat(e,a,t,source);self.tera(e,a,'불꽃')
                    e.gm.set_temp_hp(t,1000,reason='actual temporary HP absorption')
                    before=t.hp;original=e.rulings.run_hooks
                    def hooks(kind,value,context,engine):
                        return 0 if zero and kind=='before_damage' else original(kind,value,context,engine)
                    with patch.object(e.rulings,'run_hooks',side_effect=hooks):dealt=self.hit(e,a,t,uid)
                    self.assertEqual(t.hp,before)
                    self.assertEqual(bool(COATS.live(t)),zero and source=='move/물놀이')
                    if zero:self.assertEqual(dealt,0)
                    else:self.assertGreater(dealt,0);self.assertLess(t.temp_hp,1000)
                    self.assertTrue(e.validate_state()['valid'])

    def test_wrong_type_miss_status_and_hp_loss_preserve_typed_coats(self):
        for mode in ('printed_dark','miss','status','hp_loss'):
            with self.subTest(mode=mode):
                uid='move/타오르는분노';e,a,t=self.world([uid,'move/울음소리']);self.coat(e,a,t,'move/물놀이')
                identity=COATS.live(t)[0]['id']
                if mode=='hp_loss':e.lose_hp(t,1,source='observed nonattack loss')
                elif mode=='status':self.hit(e,a,t,'move/울음소리')
                else:
                    if mode=='miss':e.gm.choose_alternate_move_type(a,uid,'불꽃',reason='miss still uses selected mode')
                    self.hit(e,a,t,uid,1 if mode=='miss' else 12)
                self.assertEqual(COATS.live(t)[0]['id'],identity)
                self.assertTrue(e.validate_state()['valid'])

    def test_all_four_actual_thaw_types_and_non_thaw_control(self):
        uid='move/테라버스트-물리'
        for actual in ('불꽃','격투','바위','강철','전기'):
            with self.subTest(actual=actual):
                e,a,t=self.world([uid]);self.tera(e,a,actual);e.apply_status(t,'얼음',source='observed Frozen')
                self.assertIn('얼음',t.conditions);self.assertGreater(self.hit(e,a,t,uid),0)
                self.assertEqual('얼음' in t.conditions,actual=='전기')
                self.assertTrue(self.restore(e,a,t)[0].validate_state()['valid'])

    def test_frozen_miss_status_hp_loss_and_zero_resolved_hit_boundaries(self):
        uid='move/테라버스트-물리'
        for mode in ('miss','status','hp_loss','immune_zero'):
            with self.subTest(mode=mode):
                e,a,t=self.world([uid,'move/울음소리'],target_types=('고스트',) if mode=='immune_zero' else ('노말',))
                self.tera(e,a,'격투');e.apply_status(t,'얼음',source='observed Frozen')
                if mode=='hp_loss':e.lose_hp(t,1,source='unrelated loss')
                elif mode=='status':self.hit(e,a,t,'move/울음소리')
                else:self.assertEqual(self.hit(e,a,t,uid,1 if mode=='miss' else 12),0)
                self.assertEqual('얼음' in t.conditions,mode!='immune_zero')

    def equip_policy(self,e,t):
        WORLD.register_object(e,'actual-type/weakness',location={'kind':'unknown'},
            reason='actual held instance',kind='item_instance',item_rule_id='item/약점보험',owner_id=t.entity_id)
        ITEMS.register_item(e,t,'item/약점보험',source_instance_id='actual-type/weakness',as_held=True)

    def test_weakness_policy_uses_post_coat_effectiveness_and_pre_damage_target_types(self):
        uid='move/타오르는분노'
        for water in (False,True):
            for changed_after in (False,True):
                with self.subTest(water=water,changed_after=changed_after):
                    e,a,t=self.world([uid],target_types=('풀',));self.equip_policy(e,t)
                    if water:self.coat(e,a,t,'move/물놀이')
                    e.gm.choose_alternate_move_type(a,uid,'불꽃',reason='source actual Fire attack')
                    original=Engine._take_damage
                    def damage(engine,recipient,amount):
                        result=original(engine,recipient,amount)
                        if changed_after and recipient.entity_id==t.entity_id:
                            engine.gm.set_types(recipient,['불꽃'],reason='post-hit observed form change')
                        return result
                    with patch.object(Engine,'_take_damage',damage):self.hit(e,a,t,uid)
                    self.assertEqual('weakness_policy' in t.spec.get(PHYSICAL.PENDING,{}),not water)
                    self.assertTrue(e.validate_state()['valid'])
                    self.assertTrue(self.restore(e,a,t)[0].validate_state()['valid'])

    def test_shining_flame_actual_type_threshold_and_owner_scope(self):
        import class_passive_combat as CLASS
        for face,feat,expected in ((17,True,False),(18,True,True),(18,False,False)):
            fixture=FLAME_FIXTURE.ClassPassiveCombatBulkTests()
            e,trainer,a,t=fixture.fixture(feats=[CLASS.SHINING_FLAME] if feat else [],pokemon_moves=['move/타오르는분노'])
            e.gm.observe_loyalty(a,6,reason='actual willing owned Pokemon')
            e.begin_encounter(e.everyone);e.start_round(e.everyone);e.start_of_turn(a,initiative_count=20)
            e.gm.choose_alternate_move_type(a,'move/타오르는분노','불꽃',reason='source Fire mode')
            self.assertGreater(self.hit(e,a,t,'move/타오르는분노',face),0)
            self.assertEqual('화상' in t.conditions,expected)
            self.assertTrue(e.validate_state()['valid'])

    def test_burning_brand_printed_fire_native_18_19_baseline(self):
        import class_passive_combat as CLASS
        for face in (18,19):
            fixture=FLAME_FIXTURE.ClassPassiveCombatBulkTests()
            e,trainer,a,t=fixture.fixture(feats=[CLASS.BURNING_BRAND],trainer_moves=['니트로차지'])
            e.gm.set_position(t,(0,1),reason='actual melee target')
            e.begin_encounter(e.everyone);e.start_round(e.everyone);e.start_of_turn(trainer,initiative_count=20)
            self.assertGreater(self.hit(e,trainer,t,'move/니트로차지',face),0)
            self.assertEqual('화상' in t.conditions,face==19)

    def test_terastal_survives_encounter_restart_then_scene_end_once(self):
        for open_encounter in (False,True):
            with self.subTest(open_encounter=open_encounter):
                e,a,t=self.world(['move/테라버스트'],types=('풀',));self.tera(e,a,'불꽃')
                receipt=deepcopy(a.spec[HOME.KEY]);e.end_of_turn(a)
                e.end_encounter(e.everyone,round_elapsed_seconds=0)
                self.assertEqual(a.spec[HOME.KEY],receipt);self.assertTrue(HOME.tera_active(a))
                if open_encounter:e.begin_encounter(e.everyone)
                e,a,t=self.restore(e,a,t)
                self.assertEqual(a.spec[HOME.KEY],receipt)
                e.end_scene(e.everyone,round_elapsed_seconds=0)
                self.assertFalse(HOME.tera_active(a));self.assertEqual(a.spec[HOME.KEY]['ended_reason'],'scene_end')
                self.assertEqual(a.spec[HOME.KEY]['episode_id'],receipt['episode_id'])
                ended=deepcopy(a.spec[HOME.KEY]);e.end_scene(e.everyone,round_elapsed_seconds=0)
                self.assertEqual(a.spec[HOME.KEY],ended);self.assertEqual(a.spec['tera_type'],'불꽃')
                self.assertEqual(a.types,['풀']);self.assertTrue(e.validate_state()['valid'])

    def test_terastal_faint_is_independent_and_restore_does_not_resurrect(self):
        e,a,t=self.world(['move/테라버스트'],types=('풀',));self.tera(e,a,'불꽃')
        receipt=deepcopy(a.spec[HOME.KEY]);e.take_damage(a,a.hp)
        self.assertFalse(HOME.tera_active(a));self.assertEqual(a.spec[HOME.KEY]['ended_reason'],'fainted')
        e,a,t=self.restore(e,a,t)
        self.assertEqual(a.spec[HOME.KEY]['episode_id'],receipt['episode_id'])
        e.heal(a,a.max_hp);self.assertFalse(HOME.tera_active(a));self.assertEqual(a.spec['tera_type'],'불꽃')
        self.assertTrue(e.validate_state()['valid'])


    def test_plasma_mud_coat_and_multiple_strikes_retain_one_activation(self):
        import damage_coats as DAMAGE_COATS
        for uid in ('move/몸통박치기','move/더블어택'):
            with self.subTest(move=uid):
                e,a,t=self.world([uid,'move/흙놀이'],types=('전기',),target_moves=['move/플라스마피스트'])
                self.coat(e,a,t,'move/흙놀이')
                e.end_of_turn(a);e.start_of_turn(t,initiative_count=19);self.hit(e,t,a,'move/플라스마피스트')
                e.end_of_turn(t);e.start_round(e.everyone);e.start_of_turn(a,initiative_count=20)
                identity=next(row['id'] for row in COATS.live(t) if row['source']=='move/흙놀이')
                seen=[];original=DAMAGE_COATS.after_damage
                def observe(engine,attacker,target,move,receipt,**kwargs):
                    seen.append((target.entity_id,move['type'],receipt['requested']))
                    return original(engine,attacker,target,move,receipt,**kwargs)
                with patch.object(DAMAGE_COATS,'after_damage',side_effect=observe):self.hit(e,a,t,uid)
                self.assertEqual(len(seen),1)
                if uid=='move/더블어택':
                    import multi_strike as STRIKES
                    self.assertEqual(len(a.spec[STRIKES.KEY][-1]['rolls']),2)
                self.assertTrue(all(row[0]==t.entity_id and row[1]=='전기' for row in seen))
                self.assertEqual(sum(row['id']==identity for row in t.spec[COATS.HISTORY]),1)
                self.assertFalse(DECLARATIVE.live(a,'next_normal_attack_type'))
                self.assertTrue(e.validate_state()['valid'])
                self.assertTrue(self.restore(e,a,t)[0].validate_state()['valid'])

    def test_plasma_area_targets_keep_same_actual_type_with_distinct_matchups(self):
        import damage_coats as DAMAGE_COATS
        uid='move/스피드스타';e,a,t=self.world([uid],types=('전기',),target_moves=['move/플라스마피스트'])
        other=Combatant(self.rules,build_pokemon(self.rules,'이상해꽃',60,name='Second target',
            moves=['move/몸통박치기'],abilities=[],side='foe',extra={'types':['물']}))
        e.gm.add_combatant(other,pos=(3,1),side='foe',reason='actual second area recipient')
        e.end_of_turn(a);e.start_of_turn(t,initiative_count=19);self.hit(e,t,a,'move/플라스마피스트')
        e.end_of_turn(t);e.start_round(e.everyone);e.start_of_turn(a,initiative_count=20)
        seen={};original=DAMAGE_COATS.after_damage
        def observe(engine,attacker,target,move,receipt,**kwargs):
            seen[target.entity_id]=(move['type'],kwargs['type_multiplier'])
            return original(engine,attacker,target,move,receipt,**kwargs)
        with patch.object(DAMAGE_COATS,'after_damage',side_effect=observe),patch.object(Engine,'d20',return_value=12):
            e.use_move_on(a,t,uid,e.everyone,aim=t.pos,set_damage=True)
        self.assertEqual(seen[t.entity_id],('전기',1))
        self.assertEqual(seen[other.entity_id],('전기',1.5))
        self.assertFalse(DECLARATIVE.live(a,'next_normal_attack_type'))
        self.assertTrue(e.validate_state()['valid'])

    def test_fighting_changed_to_electric_does_not_thaw_and_tera_printed_match_gives_no_ten(self):
        uid='move/천둥차기';e,a,t=self.world([uid],types=('물',))
        self.tera(e,a,'격투');e.apply_status(t,'얼음',source='observed Frozen')
        e.gm.choose_alternate_move_type(a,uid,'전기',reason='source chosen Electric mode')
        expected=self.expected(e,a,t,uid,e.r.move(uid)['damage_base'])
        self.assertEqual(self.hit(e,a,t,uid),expected)
        self.assertIn('얼음',t.conditions)
        self.assertTrue(e.validate_state()['valid'])

    def test_taskmaster_paired_hits_keep_each_actual_type_and_actor(self):
        import test_book_taskmaster_hardened as FIXTURE
        import state_grants as GRANTS
        import persistent_conditions as PERSISTENT
        FIXTURE.TaskmasterTests.setUpClass();f=FIXTURE.TaskmasterTests()
        f.setup();f.gambit_features()
        GRANTS.set_baseline(f.p,'moves',list(f.p.spec['moves'])[:5]+['move/천둥차기'])
        f.e.gm.choose_alternate_move_type(f.p,'move/천둥차기','전기',reason='Pokemon counter uses actual Electric mode')
        f.combat(f.b);f.answer('deadly_gambit',{'move':'move/천둥차기','roll_effects':False,'options':{'set_damage':True}})
        seen=[];original=PERSISTENT.attack_hit
        def observe(engine,target,move):
            seen.append((target.entity_id,move['id'],move['type']))
            return original(engine,target,move)
        with patch.object(PERSISTENT,'attack_hit',side_effect=observe):f.attack(f.b,f.p,'move/몸통박치기')
        self.assertEqual(seen,[(f.p.entity_id,'move/몸통박치기','노말'),(f.b.entity_id,'move/천둥차기','전기')])
        self.assertEqual(ALTERNATE.status(f.p,'move/천둥차기')[0]['use']['actual_type'],'전기')
        f.restore();f.valid()

    def test_delayed_native_hit_thaws_only_for_its_own_type(self):
        import test_category2_delayed_attacks as FIXTURE
        FIXTURE.DelayedAttackTests.setUpClass();f=FIXTURE.DelayedAttackTests()
        for uid,thaws in (('move/파멸의소원',True),('move/미래예지',False)):
            with self.subTest(move=uid):
                e,a,t=f.world(uid);e.use_move(a,t,uid);e.apply_status(t,'얼음',source='observed Frozen')
                e,a,t=self.restore(e,a,t)
                e.end_of_turn(a);e.start_of_turn(t,initiative_count=20)
                import persistent_conditions as PERSISTENT
                seen=[];original=PERSISTENT.attack_hit
                def observe(engine,target,move):
                    result=original(engine,target,move)
                    seen.append((target.entity_id,move['type'],'얼음' in target.conditions))
                    return result
                with patch.object(PERSISTENT,'attack_hit',side_effect=observe):e.end_of_turn(t)
                self.assertEqual(seen,[(t.entity_id,e.r.move(uid)['type'],not thaws)])
                self.assertFalse(e.delayed);self.assertTrue(e.validate_state()['valid'])

    def test_typing_history_and_coat_end_tampering_remain_rejected(self):
        import attack_damage_history as HISTORY
        uid='move/타오르는분노';e,a,t=self.world([uid]);self.coat(e,a,t,'move/물놀이')
        e.gm.choose_alternate_move_type(a,uid,'불꽃',reason='actual Fire type')
        self.hit(e,a,t,uid)
        self.assertEqual(HISTORY.last_damage(t)['move_type'],'불꽃')
        e.gm.snapshot('actual-type-hit');before=deepcopy(t.spec)
        e.gm.restore('actual-type-hit');self.assertEqual(t.spec,before)
        e,a,t=self.restore(e,a,t)
        record=next(row for row in t.spec[COATS.HISTORY] if row['source']=='move/물놀이')
        record['effect_instance']['end_event']['move_type']='악'
        self.assertFalse(e.validate_state()['valid'])
        with self.assertRaises(ValueError):e.export_state()


    def test_versatile_main_explicit_lower_stat_and_typed_variant_class_are_distinct(self):
        cases=(('move/테라버스트','atk','물리'),('move/테라버스트','spa','특수'),
               ('move/테라버스트-물리','spa','물리'),('move/테라버스트-특수','atk','특수'))
        for uid,selected,cls in cases:
            for area_entry in (False,True):
                with self.subTest(move=uid,selected=selected,area_entry=area_entry):
                    e,a,t=self.world([uid],types=('불꽃',));self.tera(e,a,'불꽃')
                    e.change_stage(a,'atk',3)
                    self.assertGreater(a.staged('atk'),a.staged('spa'))
                    move=deepcopy(e.r.move(uid));db=move['damage_base']+math.floor(e.formula('stab'))
                    expected=self.expected(e,a,t,uid,db,10,selected=selected)
                    observed=[];original=Engine.roll_damage
                    def damage(engine,attacker,target,prepared,*args,**kwargs):
                        observed.append((prepared['class'],prepared.get('_versatile_attack_stat')))
                        return original(engine,attacker,target,prepared,*args,**kwargs)
                    with patch.object(Engine,'roll_damage',damage),patch.object(Engine,'d20',return_value=12):
                        dealt=(e.use_move_on(a,t,uid,e.everyone,set_damage=True,versatile_stat=selected) if area_entry
                               else e.use_move(a,t,uid,set_damage=True,versatile_stat=selected))
                    self.assertEqual((dealt,observed),(expected,[(cls,selected)]))
                    self.assertEqual(e.r.move(uid),move)
                    self.assertTrue(self.restore(e,a,t)[0].validate_state()['valid'])

    def test_versatile_missing_wrong_and_unrelated_choice_reject_before_cost_rng_or_movement(self):
        for uid,selected in (('move/테라버스트',None),('move/테라버스트','def'),
                             ('move/테라버스트',True),('move/몸통박치기','atk')):
            for area_entry in (False,True):
                with self.subTest(move=uid,selected=selected,area_entry=area_entry):
                    e,a,t=self.world([uid]);before=e.export_state()
                    with self.assertRaisesRegex(ValueError,'Versatile'):
                        if area_entry:e.use_move_on(a,t,uid,e.everyone,versatile_stat=selected)
                        else:e.use_move(a,t,uid,versatile_stat=selected)
                    self.assertEqual(e.export_state(),before)

    def test_versatile_choice_survives_real_defense_pending_json_and_resume_once(self):
        import test_category2_move_defense_reactions as FIXTURE
        import passive_events as PASSIVE
        import state_grants as GRANTS
        FIXTURE.MoveDefenseReactionsTests.setUpClass()
        for selected,cls in (('atk','물리'),('spa','특수')):
            with self.subTest(selected=selected):
                f=FIXTURE.MoveDefenseReactionsTests();f.setUp()
                GRANTS.set_baseline(f.a,'moves',list(f.a.spec['moves'])[:5]+['move/테라버스트'])
                f.t.pos=(6,2);f.r.pos=(4,4);f.watch('maneuver/원거리-가로채기')
                with patch.object(Engine,'d20',return_value=12),self.assertRaises(PASSIVE.PassiveEventPending):
                    f.e.use_move_on(f.a,f.t,'move/테라버스트',f.e.everyone,set_damage=True,versatile_stat=selected)
                event=f.e._passive_pending;f.fresh()
                seen=[];original=Engine.roll_damage
                def damage(engine,attacker,target,move,*args,**kwargs):
                    seen.append((target.entity_id,move['class'],move.get('_versatile_attack_stat')))
                    return original(engine,attacker,target,move,*args,**kwargs)
                with patch.object(Engine,'roll_damage',damage):f.choose(event,options=f.ranged())
                self.assertEqual(seen,[(f.r.entity_id,cls,selected)])
                self.assertEqual(f.a.move_uses['move/테라버스트'],1)
                self.assertTrue(f.e.validate_state()['valid'])

    def test_versatile_gambit_counter_retains_explicit_choice(self):
        import test_book_taskmaster_hardened as FIXTURE
        import state_grants as GRANTS
        import persistent_conditions as PERSISTENT
        FIXTURE.TaskmasterTests.setUpClass();f=FIXTURE.TaskmasterTests();f.setup();f.gambit_features()
        GRANTS.set_baseline(f.p,'moves',list(f.p.spec['moves'])[:5]+['move/테라버스트'])
        f.combat(f.b);f.answer('deadly_gambit',{'move':'move/테라버스트','roll_effects':False,
                                             'options':{'set_damage':True,'versatile_stat':'spa'}})
        seen=[];original=PERSISTENT.attack_hit
        def observe(engine,target,move):
            seen.append((target.entity_id,move['class'],move.get('_versatile_attack_stat')))
            return original(engine,target,move)
        with patch.object(PERSISTENT,'attack_hit',side_effect=observe):f.attack(f.b,f.p,'move/몸통박치기')
        self.assertEqual(seen[-1],(f.b.entity_id,'특수','spa'))
        f.restore();f.valid()

    def test_versatile_keyword_scope_preserves_gmax_and_original_move(self):
        uid='move/브레이크스루';move=deepcopy(self.rules.move(uid));e=Engine(self.rules)
        for selected,cls in (('atk','물리'),('spa','특수')):
            result=EXT.prepare_versatile_move(e,move,selected)
            self.assertEqual((result['class'],result['_versatile_attack_stat']),(cls,selected))
        self.assertEqual(self.rules.move(uid),move)
        z=deepcopy(self.rules.moves['move/울트라대시어택'])
        self.assertIs(EXT.prepare_versatile_move(e,z),z)
        with self.assertRaises(ValueError):EXT.prepare_versatile_move(e,z,'atk')


    def test_actual_electric_immunity_keeps_positive_damage_coat_and_declines_weakness(self):
        uid='move/천둥차기';e,a,t=self.world([uid],target_types=('땅',))
        self.equip_policy(e,t);self.coat(e,a,t,'move/흙놀이')
        e.gm.choose_alternate_move_type(a,uid,'전기',reason='actual source Electric attack')
        self.assertEqual(self.hit(e,a,t,uid),0)
        self.assertTrue(any(row['source']=='move/흙놀이' for row in COATS.live(t)))
        self.assertNotIn('weakness_policy',t.spec.get(PHYSICAL.PENDING,{}))
        self.assertTrue(e.validate_state()['valid'])

    def test_actual_weakness_policy_keeps_item_presence_optional_use_and_encounter_expiry(self):
        import equipment_suppression as SUPPRESSION
        for mode in ('decline','accept','dropped','destroyed','suppressed'):
            with self.subTest(mode=mode):
                uid='move/타오르는분노';e,a,t=self.world([uid],target_types=('풀',));self.equip_policy(e,t)
                if mode=='dropped':ITEMS.drop_item(e,t,selection='actual-type/weakness')
                elif mode=='destroyed':ITEMS.destroy_equipment(e,t,'actual-type/weakness',reason='actual destruction')
                elif mode=='suppressed':e.gm.set_ability(t,SUPPRESSION.KLUTZ_NAME,reason='actual item-suppressing ability')
                e.gm.choose_alternate_move_type(a,uid,'불꽃',reason='actual source Fire attack')
                self.hit(e,a,t,uid)
                if mode in ('dropped','destroyed','suppressed'):
                    self.assertNotIn('weakness_policy',t.spec.get(PHYSICAL.PENDING,{}));continue
                self.assertIn('weakness_policy',t.spec[PHYSICAL.PENDING])
                e,a,t=self.restore(e,a,t)
                PHYSICAL.resolve_pending(e,t,'weakness_policy',accept=mode=='accept')
                move=e.r.move('move/몸통박치기')
                self.assertEqual(PHYSICAL.damage_roll_bonus(e,t,move),10 if mode=='accept' else 0)
                e.end_of_turn(a);e.end_encounter(e.everyone,round_elapsed_seconds=0)
                self.assertEqual(PHYSICAL.damage_roll_bonus(e,t,move),0)
                self.assertTrue(e.validate_state()['valid'])

    def test_scene_expiry_removes_ordinary_tera_type_bonus_without_rewriting_choice(self):
        uid='move/테라버스트-특수';e,a,t=self.world([uid],types=('불꽃',));self.tera(e,a,'불꽃')
        e.end_of_turn(a);e.end_scene(e.everyone,round_elapsed_seconds=0)
        e.begin_encounter(e.everyone);e.start_round(e.everyone);e.start_of_turn(a,initiative_count=20)
        db=e.r.move(uid)['damage_base'];expected=self.expected(e,a,t,uid,db)
        self.assertEqual(self.hit(e,a,t,uid),expected)
        self.assertEqual(a.spec['tera_type'],'불꽃');self.assertFalse(HOME.tera_active(a))
        self.assertTrue(e.validate_state()['valid'])


if __name__=='__main__':unittest.main()
