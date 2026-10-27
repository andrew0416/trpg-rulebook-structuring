"""Complete Berserker supplement and CSV source-choice native contracts."""
from pathlib import Path
import sys,unittest
from copy import deepcopy
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Engine
from berserker_fixture import BerserkerFixture
import berserker as B,acquired_features as AC,state_grants as G
import trainer_feature_acquisition as T,frequency as F,skill_modifiers as SK
import movement_actions as M,weapon_actions as WA,optional_weapon_framework as OW
import temporary_hp as H,precise_actions as P,items,turn,state_fields as SF


class BerserkerFullTests(BerserkerFixture,unittest.TestCase):
    def test_exact_seven_acquisitions_hp_moves_choice_and_codec(self):
        for edition in ('supplement','local_csv'):
            self.scene(features=tuple(B.FEATURES),edition=edition)
            self.assertEqual(len(B.records(self.a)),7)
            self.assertEqual(len(AC.class_instances(self.a)),1)
            self.assertEqual(self.a.base_max_hp,self.initial_max+21)
            for feature,names in B.MOVE_NAMES.items():
                for name in names:self.assertIn(self.rules.move_id(name),self.a.moves)
            self.assertIn('화이트플레임',self.a.abilities)
            self.assertEqual(len([s for s in G.state(self.a)['sources'].values() if s.get('feature_ability_projection')]),1)
            for feature in B.FEATURES:
                record=B.acquired(self.a,feature)
                self.assertEqual(record['snapshot']['source'],B.source(self.rules,feature,edition))
                before=self.e.export_state();self.acquire(feature);self.assertEqual(self.e.export_state(),before)
            self.valid();self.restore();self.valid()
            self.assertEqual(B.acquired(self.a,B.POWER)['snapshot']['selection']['ability'],'화이트플레임')
            self.rejected(lambda:self.acquire(B.POWER,ability='불굴의격노'),'request|selection|choice|already')

    def test_actual_prerequisites_four_class_slots_and_immutable_source(self):
        self.scene(combat_rank=2)
        self.rejected(lambda:self.acquire(),'Combat')
        SF.base_patch(self.a,{'skills':dict(self.a.spec['skills'],전투=3)},reason='actual Novice Combat')
        self.acquire();self.rejected(lambda:self.acquire(B.FRENZY),'Combat')
        SF.base_patch(self.a,{'skills':dict(self.a.spec['skills'],전투=5)},reason='actual Expert Combat')
        self.acquire(B.FRENZY);self.acquire(B.CRASH)
        SF.base_patch(self.a,{'skills':dict(self.a.spec['skills'],전투=2)},reason='later rank preserves historical receipt')
        self.acquire(B.CRASH);self.valid();self.restore();self.valid()
        self.scene(features=(B.CLASS,))
        for feature,selection in (('class/닌자',None),('class/오컬트마니아',{'ability':'ability/징조'}),
                ('class/멘토',{'source':'local_translation','skills':['직감','협박'],'tutoring_policy':'kr_errata'})):
            T.acquire_static(self.e,self.a,feature,acquisition_request_id='actual-extra/'+feature,selection=selection)
        self.assertEqual(len(AC.class_instances(self.a)),4)
        self.rejected(lambda:T.acquire_static(self.e,self.a,'class/기록자',acquisition_request_id='actual-fifth'),'four slots')
        self.scene();self.a.spec['feats']=[B.CLASS,B.LESSONS,B.FRENZY]
        self.assertIsNone(B.acquired(self.a));self.assertFalse(B.lessons(self.a))
        self.rejected(lambda:B.frenzy(self.e,self.a,request_id='not-acquired'),'actual Frenzy acquisition')

    def test_csv_crash_adept_branch_and_equal_rage_contract(self):
        self.scene(features=(B.FRENZY,),combat_rank=4)
        self.rejected(lambda:self.acquire(B.CRASH),'Combat')
        out=self.acquire(B.CRASH,edition='local_csv')
        self.assertEqual(out['snapshot']['source']['row'],549)
        self.assertEqual(B.source(self.rules,B.CLASS,'local_csv')['row'],544)
        self.assertEqual(B.source(self.rules,B.LIMIT,'local_csv')['row'],550)
        for edition in ('supplement','local_csv'):
            self.scene(features=(B.FRENZY,),edition=edition,combat_rank=4)
            self.rage();self.combat(False,scheduled=True)
            B.frenzy(self.e,self.a,request_id='same-enraged/'+edition)
            self.assertEqual(B.frenzy_bonus(self.a),2)
            self.assertIn('난동',self.a.conditions)

    def test_reviewed_rage_turn_owner_damage_reaction_and_expiry_survive_restore(self):
        import catalog_move_states as CATALOG,combat_timing as TIMING
        for until in ('end of next turn',"end of user's next turn"):
            with self.subTest(until=until):
                self.scene(features=(B.CLASS,))
                declared=deepcopy(self.rules.moves_reviewed[CATALOG.RAGE])
                declared['effects']=[dict(CATALOG.RAGE_STATUS,until=until),deepcopy(CATALOG.RAGE_STAGE)]
                with patch.dict(self.rules.moves_reviewed,{CATALOG.RAGE:declared}):
                    self.combat();stage=self.a.stages['atk']
                    self.assertGreater(self.attack(),0)
                    self.assertIn('난동',self.a.conditions)
                    self.assertEqual(self.a.stages['atk'],stage)
                    records=[r for r in TIMING.records(self.a) if r.get('source')==CATALOG.RAGE]
                    self.assertEqual(len(records),1)
                    self.assertIs(records[0]['turn_owner'],self.a)
                    self.assertEqual(records[0]['turn_deadline'],self.a.custom_conditions['combat_turn_serial']+1)
                    self.restore();self.valid();self.e.end_of_turn(self.a)
                    self.assertIn('난동',self.a.conditions)
                    self.e.start_of_turn(self.b,initiative_count=10)
                    self.assertGreater(self.attack('move/물대포',actor=self.b,target=self.a),0)
                    self.assertEqual(self.a.stages['atk'],stage+1)
                    self.e.end_of_turn(self.b);self.e.end_round()
                    self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a,initiative_count=20)
                    self.assertIn('난동',self.a.conditions)
                    self.restore();self.valid();self.e.end_of_turn(self.a)
                    self.assertNotIn('난동',self.a.conditions)
                    self.assertFalse([r for r in TIMING.records(self.a) if r.get('source')==CATALOG.RAGE])
                    self.assertEqual(self.rules.moves_reviewed[CATALOG.RAGE],declared)
                    self.valid()

    def test_lessons_native_damage_whitelist_hp_ceiling_and_heavy_losses(self):
        self.scene(features=(B.LESSONS,));self.injury(6)
        self.assertEqual(self.a.max_hp,self.a.base_max_hp//2)
        self.hp(1);self.e.heal(self.a,9999,source_kind='feature');self.assertEqual(self.a.hp,self.a.max_hp)
        for name in ('분노','바둥바둥','난동부리기','물대포'):
            move=self.rules.move(self.rules.move_id(name))
            with_lesson=self.e.roll_damage(self.a,self.b,move,set_damage=True)
            with patch.object(B,'lessons',return_value=False):
                without=self.e.roll_damage(self.a,self.b,move,set_damage=True)
            self.assertEqual(with_lesson-without,0 if name=='물대포' else 11)
        original=Engine.roll_damage;five=[]
        def observe(e,a,t,m,*args,**kwargs):
            result=original(e,a,t,m,*args,**kwargs)
            if m['id']=='move/마구할퀴기':
                self.assertIn(m['_five_strike'],a.spec['five_strike_history'])
                with patch.object(B,'lessons',return_value=False):baseline=original(e,a,t,m,*args,**kwargs)
                five.append(result-baseline)
            return result
        self.combat();before=self.a.hp
        with patch.object(Engine,'roll_damage',observe):self.attack('move/마구할퀴기')
        self.assertEqual(five,[11])
        self.assertEqual(self.a.hp,before);self.assertIsNone(self.e._heavy_pending)
        self.e.end_of_turn(self.a);self.e.start_of_turn(self.b,initiative_count=10)
        before=self.a.hp;damage=self.attack('move/물대포',actor=self.b,target=self.a)
        self.assertEqual(self.a.hp,before-damage);self.assertIsNone(self.e._heavy_pending)
        self.valid()

    def test_frenzy_native_priority_cure_all_bonuses_and_turn_end(self):
        self.scene(features=(B.FRENZY,));self.rage()
        for condition in ('둔화','구속'):self.e.apply_status(self.a,condition)
        self.combat(False,scheduled=True)
        result=B.frenzy(self.e,self.a,request_id='actual-priority')
        self.assertEqual(result['source'],B.FRENZY)
        self.assertIs(self.e._active_turn_actor,self.a)
        self.assertEqual(self.a.budget,{'standard':1,'shift':1,'swift':1})
        self.assertEqual(self.a.custom_conditions['combat_turn_serial'],1)
        self.assertFalse({'둔화','구속'}&self.a.conditions)
        self.assertEqual({k:v for k,v in M.capabilities(self.e,self.a).items() if k in ('land','swim','sky')},
                         {'land':8,'swim':5,'sky':0})
        for skill in ('육상','곡예','전투','협박'):
            self.assertEqual(self.e.skill_roll(self.a,skill,fixed=[1]*5).total,7)
        self.assertEqual(self.e.skill_roll(self.a,'은신',fixed=[1]*5).total,5)
        self.assertTrue(self.e.accuracy_check(self.a,self.b,self.rules.move('move/분노'),fixed_roll=18)[2])
        self.assertGreater(self.attack(),0);self.assertEqual(self.a.budget['standard'],0)
        self.e.finish_initiative_reaction()
        self.assertEqual(B.frenzy_bonus(self.a),0)
        self.assertEqual(M.capabilities(self.e,self.a)['land'],6)
        self.assertFalse(self.e.accuracy_check(self.a,self.b,self.rules.move('move/분노'),fixed_roll=18)[2])
        self.valid()

    def test_frenzy_scene_two_uses_and_acted_or_not_enraged_rejections(self):
        self.scene(features=(B.FRENZY,));self.combat(False,scheduled=True)
        self.rejected(lambda:B.frenzy(self.e,self.a,request_id='not-enraged'),'Enraged')
        self.rage()
        for n in range(2):
            B.frenzy(self.e,self.a,request_id='native-priority/'+str(n))
            self.e.finish_initiative_reaction();self.e.settle_borrowed_turn()
            self.e.start_of_turn(self.b);self.e.end_of_turn(self.b);self.e.end_round()
            self.e.prepare_initiative_schedule(self.e.everyone,source='gm/actual-next-berserker-schedule')
            self.e.start_round(self.e.everyone);self.rage()
        self.rejected(lambda:B.frenzy(self.e,self.a,request_id='exhausted'),'frequency')
        self.scene(features=(B.FRENZY,));self.rage();self.combat(scheduled=True)
        self.e.end_of_turn(self.a)
        self.rejected(lambda:B.frenzy(self.e,self.a,request_id='acted'),'unacted')

    def test_fight_on_actual_pre_faint_daily_and_five_injury_exception(self):
        self.scene(features=(B.FIGHT,));self.rage();self.answer('berserker_fight_on',True);self.combat()
        self.hp(1);self.e.lose_hp(self.a,2,source='actual lethal hazard',loss_kind='hp_setting')
        self.assertEqual(self.a.hp,-1);self.assertNotIn('기절',self.a.conditions)
        self.assertTrue(turn.can_act(self.e,self.a));self.assertGreater(self.attack(),0)
        self.assertFalse(F.activation_allowed(self.a,B.FIGHT,{'kind':'daily','uses':1},engine=self.e))
        self.e.heal(self.a,5,source_kind='feature');self.e.lose_hp(self.a,5,source='second actual drop',loss_kind='hp_setting')
        self.assertIn('기절',self.a.conditions)
        self.e.heal(self.a,20,source_kind='feature');self.injury(5);self.rage()
        self.e.lose_hp(self.a,self.a.hp+1,source='five-injury actual drop',loss_kind='hp_setting')
        self.assertTrue(B.conscious(self.a));self.assertNotIn('기절',self.a.conditions)
        self.valid();self.restore();self.valid();self.assertTrue(B.conscious(self.a))

    def test_fight_on_half_true_max_threshold_rage_cure_healing_and_death(self):
        self.scene(features=(B.FIGHT,));self.injury(5);self.rage();self.answer('berserker_fight_on',True)
        self.hp(1);self.e.lose_hp(self.a,2,source='actual threshold crossing',loss_kind='hp_setting')
        self.e.cure_status(self.a,'난동');self.assertTrue(B.conscious(self.a))
        threshold=-(self.a.base_max_hp//2)
        self.e.lose_hp(self.a,self.a.hp-(threshold+1),source='above printed half true maximum',loss_kind='hp_setting')
        self.assertTrue(B.conscious(self.a));self.assertTrue(turn.can_act(self.e,self.a))
        self.e.lose_hp(self.a,2,source='at or below half true maximum',loss_kind='hp_setting')
        self.assertIn('기절',self.a.conditions);self.assertFalse(B.conscious(self.a))
        self.e.heal(self.a,9999,source_kind='feature');self.assertNotIn(B.FIGHT_STATE,self.a.custom_conditions)
        self.rage();self.e.lose_hp(self.a,self.a.hp+1,source='fresh five-injury trigger',loss_kind='hp_setting')
        self.assertTrue(B.conscious(self.a))
        self.e.death_enabled=True;self.injury(10);self.e.check_fainted(self.a)
        self.assertTrue(self.a.dead);self.assertFalse(turn.can_act(self.e,self.a))

    def test_crash_real_melee_weapon_native_hits_and_unequip(self):
        for name in ('분노','바둥바둥','이판사판태클','난동부리기'):
            self.scene(features=(B.CRASH,));key=self.equip();mid=self.rules.move_id(name)
            move=WA.prepare(self.e,self.a,self.rules.move(mid),key)
            self.assertEqual(move['_berserker_weapon'],key);self.assertTrue(move['_weapon_attack'])
            self.combat();self.assertGreater(self.attack(mid,weapon_id=key),0)
            turn.unequip_weapon(self.e,self.a,key)
            self.assertIn(mid,self.a.moves)
            self.rejected(lambda:WA.prepare(self.e,self.a,self.rules.move(mid),key),'equipped')
        self.scene(features=(B.CRASH,));key=self.equip('단거리 사격무기')
        self.rejected(lambda:WA.prepare(self.e,self.a,self.rules.move('move/난동부리기'),key),'melee')
        # The Rage reaction shares its selected Korean status lifetime, not a
        # free-standing Enraged flag or the different original English clock.
        self.scene(features=(B.CRASH,B.POWER));self.combat();self.attack()
        self.assertEqual(self.a.stages['atk'],0);self.restore();self.valid()
        self.e.end_of_turn(self.a);self.e.start_of_turn(self.b,initiative_count=10)
        self.attack('move/물대포',actor=self.b,target=self.a);self.assertEqual(self.a.stages['atk'],1)
        self.e.lose_hp(self.a,1,source='actual nonattack loss');self.assertEqual(self.a.stages['atk'],1)
        with patch.object(Engine,'roll_damage',return_value=0):
            self.e.resolve_attack_damage(self.b,self.a,self.rules.move('move/물대포'),False,True)
        self.assertEqual(self.a.stages['atk'],1)
        H.grant(self.e,self.a,100,provenance={'source':'actual temporary HP grant'})
        self.e.resolve_attack_damage(self.b,self.a,self.rules.move('move/물대포'),False,True)
        self.assertEqual(self.a.stages['atk'],2)
        self.e.end_of_turn(self.b);self.e.end_round();self.combat()
        self.e.end_of_turn(self.a);self.assertNotIn('난동',self.a.conditions)
        self.e.resolve_attack_damage(self.b,self.a,self.rules.move('move/물대포'),False,True)
        self.assertEqual(self.a.stages['atk'],2)
        self.scene(features=(B.CRASH,));self.combat();self.attack();self.e.cure_status(self.a,'난동')
        self.e.resolve_attack_damage(self.b,self.a,self.rules.move('move/물대포'),False,True)
        self.assertEqual(self.a.stages['atk'],0)
        self.scene();self.rage()
        self.e.resolve_attack_damage(self.b,self.a,self.rules.move('move/물대포'),False,True)
        self.assertEqual(self.a.stages['atk'],0)

    def test_push_limit_hit_before_damage_tick_cure_and_double_current_bonus(self):
        self.scene(features=(B.LIMIT,));self.injury(1);self.combat()
        self.e.apply_status(self.a,'마비');self.e.apply_status(self.a,'화상')
        self.answer('berserker_push_limit',{'cure_persistent':'마비'})
        seen=[];original=Engine.roll_damage
        def observe(e,a,t,m,*args,**kwargs):
            if a.name=='actual Berserker':seen.append((a.injuries,a.temp_hp,B.damage_bonus(e,a,t,m),'마비' in a.conditions))
            return original(e,a,t,m,*args,**kwargs)
        with patch.object(Engine,'roll_damage',observe):damage=self.attack()
        self.assertGreater(damage,0);self.assertEqual(seen,[(2,self.e.tick(self.a),14,False)])
        self.assertEqual(self.a.injuries,2);self.assertEqual(self.a.temp_hp,self.e.tick(self.a))
        self.assertNotIn('마비',self.a.conditions)
        self.assertIn('화상',self.a.conditions)
        self.assertTrue(any(row.get('berserker_push') for row in self.e._move_completions.values()))
        self.valid();self.restore();self.valid()
        self.assertEqual(B.damage_bonus(self.e,self.a,self.b,self.rules.move('move/분노')),7)
        self.scene(features=(B.LIMIT,));key=self.equip();self.answer('berserker_push_limit',{'cure_persistent':None})
        self.combat();self.assertGreater(self.attack(key,weapon_id=key),0);self.assertEqual(self.a.injuries,1)

    def test_push_limit_miss_unrelated_attack_and_decline_do_not_trigger(self):
        for move,roll,answer in (('move/분노',1,{'cure_persistent':None}),
                ('move/물대포',10,{'cure_persistent':None}),('move/분노',10,False)):
            self.scene(features=(B.LIMIT,));self.injury(1);self.answer('berserker_push_limit',answer);self.combat()
            self.attack(move,roll=roll);self.assertEqual(self.a.injuries,1);self.assertEqual(self.a.temp_hp,0)
            self.assertFalse(any(row.get('berserker_push') for row in self.e._move_completions.values()))
        self.scene(features=(B.LIMIT,));self.answer('berserker_push_limit',{'cure_persistent':'invalid'});self.combat()
        self.rejected(lambda:self.attack(),'explicit Push Limit')

    def test_late_native_failure_rolls_back_push_and_frenzy(self):
        self.scene(features=(B.LIMIT,));self.answer('berserker_push_limit',{'cure_persistent':None});self.combat()
        with patch.object(Engine,'roll_damage',side_effect=ValueError('late native hit failure')):
            self.rejected(lambda:self.attack(),'late native hit failure')
        self.scene(features=(B.FRENZY,));self.rage();self.e.apply_status(self.a,'구속');self.combat(False,scheduled=True)
        with patch.object(Engine,'start_of_turn',side_effect=ValueError('late native priority failure')):
            self.rejected(lambda:B.frenzy(self.e,self.a,request_id='failed-priority'),'late native priority failure')

    def test_source_withdrawal_removes_owned_effects_only(self):
        self.scene(features=tuple(B.FEATURES));key=self.equip()
        original={r['feature_id']:deepcopy(r) for r in B.records(self.a)}
        self.withdraw(B.CRASH)
        self.assertNotIn('move/이판사판태클',self.a.moves);self.assertNotIn('move/난동부리기',self.a.moves)
        self.assertIn('move/분노',self.a.moves)
        self.assertIn(key,self.a.custom_conditions['equipped_weapons'])
        self.assertEqual(WA.prepare(self.e,self.a,self.rules.move(key),key)['_weapon_attack']['key'],key)
        self.withdraw(B.POWER);self.assertNotIn('화이트플레임',self.a.abilities)
        self.injury(6);self.withdraw(B.LESSONS)
        self.assertEqual(self.a.max_hp,int(self.a.base_max_hp*0.4))
        self.assertFalse(B.lessons(self.a));self.assertEqual(B.damage_bonus(self.e,self.a,self.b,self.rules.move('move/분노')),0)
        self.withdraw(B.LIMIT);self.assertIsNone(B.acquired(self.a,B.LIMIT))
        self.assertEqual({r['feature_id']:r for r in B.records(self.a)},original)
        retired={row['record']['static_acquisition']['feature_id'] for row in G.state(self.a)['ended_sources']
                 if 'static_acquisition' in row['record']}
        self.assertEqual(retired,{B.CRASH,B.POWER,B.LESSONS,B.LIMIT})
        self.restore();self.assertIn(key,self.a.custom_conditions['equipped_weapons']);self.assertIn('move/물대포',self.a.moves)
        self.assertEqual({r['feature_id']:r for r in B.records(self.a)},original)

    def test_nonberserker_native_damage_injuries_and_faint_unchanged(self):
        self.scene();self.combat()
        before=self.a.hp;damage=self.attack('move/물대포')
        self.assertGreater(damage,0);self.assertEqual(self.a.hp,before)
        self.injury(6);self.assertEqual(self.a.max_hp,int(self.a.base_max_hp*0.4))
        self.assertEqual(B.frenzy_bonus(self.a),0);self.assertIsNone(B.acquired(self.a))
        self.e.lose_hp(self.a,self.a.hp+1,source='ordinary actual faint',loss_kind='hp_setting')
        self.assertIn('기절',self.a.conditions);self.assertFalse(turn.can_act(self.e,self.a))
        self.valid()
        self.scene();self.injury(6);self.combat()
        with self.assertRaises(__import__('heavy_injury_adapter').HeavyPending):self.attack('move/물대포')
        self.assertIsNotNone(self.e._heavy_pending)


if __name__=='__main__':unittest.main()
