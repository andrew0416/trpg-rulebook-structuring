"""Whole-class Marksman contracts over real acquisitions, equipment and movement."""
from copy import deepcopy
from pathlib import Path
import json,sys,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from builder import build_trainer
from grid import Grid
from native_scenario_fixture import prepare_body,assert_rejected_unchanged
import marksman as M,trainer_feature_acquisition as T,acquired_features as AC
import optional_weapon_framework as OW,weapon_actions as WA,turn
import state_grants as G,world_entities as W,frequency as F,action_points as AP
import optional_state_effect_contracts as O


class MarksmanFullTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules=Rules(ROOT,ruleset='fantasy');cls.base_rulings=deepcopy(cls.rules.rulings)
        import setup_move_state,stellar_tera_blast
        setup_move_state._policy(cls.rules);stellar_tera_blast._policy(cls.rules)

    def scene(self,*,features=(),combat=6,perception=6,edition='supplement',sniper='core_105',aim_scope='korean_ranged',release='korean_shift_attack',trip_policy='korean_optional_trip',positions=((2,4),(7,4),(12,9))):
        if sniper=='feb2016_playtest':
            self.rules=Rules(ROOT,ruleset='all');self.base_rulings=deepcopy(self.rules.rulings)
            import setup_move_state,stellar_tera_blast
            setup_move_state._policy(self.rules);stellar_tera_blast._policy(self.rules)
        self.rules.rulings=deepcopy(self.base_rulings);self.e=Engine(self.rules,seed=102669)
        self.e.grid=Grid(25,16);self.edition=edition;self.sniper=sniper;self.aim_scope=aim_scope;self.release=release
        self.trip_policy=trip_policy
        self.people=[]
        for n,pos in enumerate(positions):
            actor=Combatant(self.rules,build_trainer(self.rules,'Marksman actual '+str(n),40,
                {'hp':300,'atk':20,'def':10,'spa':20,'spd':10,'spe':30-n*5},moves=['move/몸통박치기'],abilities=[],
                pos=pos,side='party' if n==0 else 'foe',skills={'전투':combat,'통찰':perception,'곡예':5,'육상':5,'집중':5,'직감':5},
                extra={'movement':{'land':6},'movement_basis':'current'}))
            self.e.gm.add_combatant(actor);prepare_body(self.e,actor,size='중형',offsets=[(0,0)],reason='actual Marksman complete body')
            self.people.append(actor)
        self.a,self.b,self.c=self.people;self.initial_atk=self.a.stats['atk']
        for feature in features:self.acquire(feature)

    def acquire(self,feature,*,request=None,edition=None):
        if feature!=M.CLASS and M.acquired(self.a,M.CLASS)is None:self.acquire(M.CLASS,edition=edition)
        selection={'edition':edition or self.edition}
        if feature==M.CLASS:selection['sniper']=self.sniper
        if feature==M.AIM:selection['weapon_scope']=self.aim_scope
        if feature==M.CRIPPLE:selection['trip_policy']=self.trip_policy
        if feature==M.DEAD:selection['release_policy']=self.release
        return T.acquire_static(self.e,self.a,feature,acquisition_request_id=request or 'marksman/acquire/'+feature,selection=selection)

    def weapon(self,kind='장거리 사격무기',*,uid='marksman/actual-bow',moves=('move/불스아이',)):
        W.register_object(self.e,uid,location={'kind':'unknown'},reason='actual owned ranged weapon body',owner_id=self.a.entity_id,weight_kg=1,kind='physical_object')
        OW.observe_weapon(self.e,self.a,uid,name=uid,kind=kind,grade='좋음',arcane=False,metal=False,moves=list(moves),reason='observed physical ranged weapon form')
        self.key=OW.equip(self.e,self.a,uid);self.uid=uid
        self.mid=self.a.custom_conditions['equipped_weapons'][self.key]['struggle_id']
        return self.key

    def combat(self,actor=None):
        if self.e._active_turn_actor is not None:self.e.end_of_turn(self.e._active_turn_actor)
        self.e.start_round(self.e.everyone);self.e.start_of_turn(actor or self.a,initiative_count=20)

    def scheduled(self):
        self.e.prepare_initiative_schedule(self.e.everyone,source='gm/marksman-test-schedule')
        self.e.start_round(self.e.everyone)

    def close_schedule(self):
        for a in self.people:self.e.start_of_turn(a);self.e.end_of_turn(a)

    def rejected(self,fn,pattern):return assert_rejected_unchanged(self.e,fn,reason_pattern=pattern)
    def walk(self,actor,path):
        import movement_actions as MOVE
        if not turn.spend(self.e,actor,'shift','actual paid native movement',movement=True):raise ValueError('actual native Shift required')
        return MOVE.follow_paid_path(self.e,actor,path,mode='land',maximum_distance=6)
    def restore(self):
        ids=[a.entity_id for a in self.people]
        self.e=Engine.import_state(self.rules,json.loads(json.dumps(self.e.export_state(),ensure_ascii=False)))
        self.people=[W.actor_index(self.e)[u] for u in ids];self.a,self.b,self.c=self.people

    def test_seven_book_csv_real_acquisitions_slots_attack_tags_replay_codec(self):
        for edition in ('supplement','local_csv'):
            self.scene(edition=edition);self.acquire(M.CLASS)
            self.assertEqual([x['source_id'] for x in AC.class_instances(self.a)],[M.CLASS])
            self.assertEqual(set(self.a.spec['feats']),{M.CLASS});self.assertIn(M.CORE_SNIPER_NAME,self.a.abilities)
            for u in M.FEATURES:
                if u!=M.CLASS:self.acquire(u)
                self.assertEqual(M.acquired(self.a,u)['snapshot']['source']['edition'],edition)
                if edition=='local_csv':self.assertEqual(M.acquired(self.a,u)['snapshot']['source']['row'],M.CSV_ROWS[u])
            self.assertEqual(self.a.stats['atk'],self.initial_atk+7)
            receipt=self.acquire(M.AIM);self.assertEqual(receipt,self.acquire(M.AIM))
            self.rejected(lambda:self.acquire(M.AIM,request='second/aim'),'already|repeat|duplicate|acquired')
            self.restore();self.assertEqual(len(M.records(self.a,active=True)),7)
            self.assertEqual(len(AC.class_instances(self.a)),1)

    def test_exact_prerequisites_parent_no_auto_children_imported_authority_and_four_slots(self):
        self.scene(combat=2,perception=6);self.rejected(lambda:self.acquire(M.CLASS),'skill ranks')
        self.scene(combat=6,perception=2);self.rejected(lambda:self.acquire(M.CLASS),'skill ranks')
        for u,combat,perception in ((M.DOUBLE,3,6),(M.WATCH,3,3),(M.CLEAR,4,4),(M.CRIPPLE,4,4),(M.DEAD,5,5)):
            self.scene(combat=combat,perception=perception);self.acquire(M.CLASS)
            self.rejected(lambda:self.acquire(u),'skill ranks')
        self.scene();self.a.spec['classes']=['class/운동선수','class/멘토','class/지휘관','class/코디네이터']
        self.rejected(lambda:self.acquire(M.CLASS),'four slots')
        self.scene();self.a.spec['feats']=[M.CLASS,M.DOUBLE]
        self.rejected(lambda:M.double_shot(self.e,self.a,self.b,'anything'),'actual acquired')

    def test_aim_existing_lifetime_repeat_replacement_and_s001_weapon_scope(self):
        for scope,eligible in (('korean_ranged',True),('english_long_range',False)):
            self.scene(features=(M.AIM,),aim_scope=scope,positions=((2,4),(6,4),(12,9)));self.weapon('단거리 사격무기',moves=());self.combat()
            M.aim(self.e,self.a);M.aim(self.e,self.a)
            self.assertEqual(len(O.records(self.a,M.AIM)),1)
            self.combat();M.aim(self.e,self.a)
            move=WA.prepare(self.e,self.a,self.rules.move(self.mid),self.key)
            self.assertEqual(O.attack_modifiers(self.a,move),(2,2) if eligible else (0,0))
            with patch.object(Engine,'d20',return_value=18):self.e.use_move(self.a,self.b,self.mid,weapon_id=self.key,set_damage=True)
            self.assertEqual(bool(O.records(self.a,M.AIM)),not eligible)
            self.e.end_of_turn(self.a);self.e.end_round();self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a,initiative_count=20)
            self.assertFalse(O.records(self.a,M.AIM))

    def test_double_shot_repeats_aim_clear_once_and_pays_one_standard_one_ap(self):
        self.scene(features=(M.DOUBLE,M.AIM,M.CLEAR));self.weapon();self.combat();M.aim(self.e,self.a)
        M.arm_clear(self.e,self.a,self.mid,self.key);before=AP.available(self.a);observed=[]
        original=Engine.roll_damage
        def damage(e,a,t,m,crit=False,*args,**kw):
            observed.append((crit,M.scope(e,a,t,m).copy()));return original(e,a,t,m,crit,*args,**kw)
        with patch.object(Engine,'d20',side_effect=[14,14]),patch.object(Engine,'roll_damage',damage):
            result=M.double_shot(self.e,self.a,self.b,self.key)
        self.assertEqual(result,[True,True]);self.assertEqual(len(observed),2)
        self.assertTrue(all(x[0] for x in observed));self.assertTrue(all(x[1]['clear'] for x in observed))
        self.assertEqual(observed[1][1]['repeated_aim'],(2,2));self.assertEqual(AP.available(self.a),before-1)
        self.assertEqual((self.a.budget['standard'],self.a.budget['swift']),(0,0))
        self.assertFalse(O.records(self.a,M.AIM));self.assertEqual(F.state(self.a)['activations'][M.CLEAR]['used'],1)

    def test_clear_real_attack_vulnerable_critical_frequency_and_exact_terrain_distance(self):
        self.scene(features=(M.CLEAR,));self.weapon();self.combat();M.arm_clear(self.e,self.a,self.mid,self.key)
        with patch.object(Engine,'d20',return_value=16):self.assertTrue(self.e.use_move(self.a,self.b,self.mid,weapon_id=self.key,set_damage=True))
        self.assertFalse(self.a.spec.get(M.ARM));self.assertEqual(self.a.budget['swift'],0)
        for obstacle in ('rough','blocking','combatant'):
            self.scene(features=(M.CLEAR,));self.weapon();self.combat()
            if obstacle=='combatant':self.e.gm.set_position(self.c,(9,4),reason='actual combatant exactly two metres from target')
            else:getattr(self.e.grid,obstacle).add((9,4))
            M.arm_clear(self.e,self.a,self.mid,self.key)
            self.rejected(lambda:self.e.use_move(self.a,self.b,self.mid,weapon_id=self.key),'two metres')

    def test_overwatch_native_movement_once_per_foe_and_forced_exit(self):
        self.scene(features=(M.WATCH,),positions=((2,4),(7,6),(12,9)));self.weapon();self.combat()
        M.watch(self.e,self.a,self.key,direction=(1,0),blast_center=(7,4));self.restore()
        self.e.end_of_turn(self.a);self.e.start_of_turn(self.b,initiative_count=15)
        self.e.rulings.add_answer('marksman_overwatch',{'weapon_id':self.key,'move_id':self.mid})
        before=self.b.hp
        with patch.object(Engine,'d20',return_value=20):self.walk(self.b,[(7,5),(7,4),(7,3),(7,2)])
        self.assertLess(self.b.hp,before);self.assertEqual(self.a.spec[M.WATCH_STATE]['targets'],[self.b.entity_id])
        self.assertEqual(self.a.budget['standard'],0)

    def test_overwatch_overlap_owner_moves_full_round_count_and_frequency_guard(self):
        self.scene(features=(M.WATCH,));self.weapon();self.combat()
        self.rejected(lambda:M.watch(self.e,self.a,self.key,direction=(1,0),blast_center=(5,8)),'overlap')
        M.watch(self.e,self.a,self.key,direction=(1,0),blast_center=(7,4))
        self.walk(self.a,[(2,5)]);self.assertIsNone(M.watch_state(self.e,self.a))
        self.combat();M.watch(self.e,self.a,self.key,direction=(1,0),blast_center=(7,5))
        self.e.end_of_turn(self.a);self.e.end_round();self.e.start_round(self.e.everyone)
        self.e.at_initiative_count(21);self.assertIsNotNone(M.watch_state(self.e,self.a))
        self.e.at_initiative_count(20);self.assertIsNone(M.watch_state(self.e,self.a))

    def test_cripple_native_resistance_status_stage_and_remote_perception_trip(self):
        self.scene(features=(M.CRIPPLE,));self.weapon();self.combat();before=AP.available(self.a);seen=[]
        original=Engine.roll_damage
        def damage(e,a,t,m,*args,**kw):seen.append(M.resistance(e,a,t,m));return original(e,a,t,m,*args,**kw)
        with patch.object(Engine,'d20',return_value=20),patch.object(Engine,'roll_damage',damage):
            out=M.crippling_shot(self.e,self.a,self.b,self.key,use_trip=True,challenger_skill='통찰',defender_skill='곡예',fixed_accuracy=20,challenger_options={'fixed':[6]*6},defender_options={'fixed':[1]*5})
        self.assertTrue(out['hit']);self.assertTrue(out['trip']);self.assertEqual(seen,[1])
        self.assertIn('둔화',self.b.conditions);self.assertIn('넘어짐',self.b.conditions);self.assertEqual(self.b.stages['spe'],-1)
        self.assertEqual(AP.available(self.a),before-2);self.assertEqual((self.a.budget['standard'],self.a.budget['shift']),(0,0))

    def test_cripple_miss_no_debuff_and_late_trip_error_rolls_back_full_action(self):
        self.scene(features=(M.CRIPPLE,));self.weapon();self.combat()
        with patch.object(Engine,'d20',return_value=1):out=M.crippling_shot(self.e,self.a,self.b,self.key,use_trip=False)
        self.assertFalse(out['hit']);self.assertNotIn('둔화',self.b.conditions)
        self.combat()
        with patch.object(Engine,'d20',return_value=20):
            self.rejected(lambda:M.crippling_shot(self.e,self.a,self.b,self.key,use_trip=True,challenger_skill='매력'),'skill is not permitted')

    def test_deadeye_actual_priority_declaration_and_lower_result_critical_after_optional_shift(self):
        self.scene(features=(M.DEAD,),release='english_optional_shift');self.weapon();self.scheduled()
        before=self.b.hp;M.declare_deadeye(self.e,self.a,request_id='deadeye/start');self.assertEqual(self.b.hp,before)
        self.close_schedule();self.restore()
        M.deadeye_choice(self.e,self.a,use=True,target=self.b,weapon_id=self.key,move_id=self.mid)
        self.e.rulings.add_answer('marksman_deadeye_accuracy',0)
        with patch.object(Engine,'d20',side_effect=[10,18]):self.e.end_round()
        self.assertLess(self.b.hp,before);self.assertEqual(self.a.spec[M.DEAD_STATE]['phase'],'complete')

    def test_deadeye_start_boundary_late_declaration_decline_and_korean_shift_cost(self):
        self.scene(features=(M.DEAD,));self.weapon();self.scheduled();M.declare_deadeye(self.e,self.a,request_id='deadeye/korean')
        self.close_schedule();M.deadeye_choice(self.e,self.a,use=True,target=self.b,weapon_id=self.key,move_id=self.mid)
        self.e.rulings.add_answer('marksman_deadeye_accuracy',1)
        with patch.object(Engine,'d20',side_effect=[18,10]):self.e.end_round()
        self.assertEqual(self.a.budget['shift'],0)
        self.scene(features=(M.DEAD,));self.weapon();self.scheduled();self.e.start_of_turn(self.a);self.e.end_of_turn(self.a)
        self.rejected(lambda:M.declare_deadeye(self.e,self.a,request_id='late'),'actual round start')

    def test_sniper_selected_core_playtest_and_source_withdrawal_preserve_independent_ability(self):
        for policy in ('core_105','feb2016_playtest'):
            self.scene(features=(M.CLASS,),sniper=policy);self.weapon();self.combat()
            move=WA.prepare(self.e,self.a,self.rules.move(self.mid),self.key)
            self.assertEqual(M.sniper_times(self.a,True),int(policy=='core_105'))
            self.assertEqual(M.sniper_dice(self.e,self.a,move,True,True),16 if policy=='feb2016_playtest' else 0)
            with patch.object(M,'sniper_times',return_value=0),patch.object(M,'sniper_dice',return_value=0):
                base=self.e.roll_damage(self.a,self.b,move,crit=True,set_damage=True)
            entry=self.rules.mech('combat/damage-chart')['by_damage_base'][str(self.e.damage_base(self.a,move,target=self.b))]
            before=self.b.hp
            with patch.object(Engine,'d20',return_value=20):self.e.use_move(self.a,self.b,self.mid,weapon_id=self.key,set_damage=True)
            self.assertEqual(before-self.b.hp,base+(entry['set']['mid'] if policy=='core_105' else 16))
            ability=M.CORE_SNIPER_NAME if policy=='core_105' else '스나이퍼 [Playtest]'
            self.a.spec.setdefault('abilities',[]).append(ability)
            sid=next(s for s,r in G.state(self.a)['sources'].items() if r.get('static_acquisition',{}).get('feature_id')==M.CLASS)
            def withdraw(e,a):G.revoke(a,sid,engine=e);a.spec['feats'].remove(M.CLASS)
            G.transition(self.e,self.a,withdraw);self.assertIn(ability,self.a.abilities)
            self.assertEqual(M.sniper_times(self.a,True),int(policy=='core_105'))

    def test_clear_scene_two_uses_and_third_native_attack_rejects_atomically(self):
        self.scene(features=(M.CLEAR,));self.weapon()
        for _ in range(2):
            self.combat();M.arm_clear(self.e,self.a,self.mid,self.key)
            with patch.object(Engine,'d20',return_value=10):self.e.use_move(self.a,self.b,self.mid,weapon_id=self.key,set_damage=True)
        self.combat();M.arm_clear(self.e,self.a,self.mid,self.key)
        self.rejected(lambda:self.e.use_move(self.a,self.b,self.mid,weapon_id=self.key),'frequency exhausted')

    def test_overwatch_forced_exit_and_source_loss_end_without_free_frequency_bypass(self):
        import forced_movement as FM
        self.scene(features=(M.WATCH,),positions=((2,4),(7,3),(12,9)));self.weapon();self.combat()
        M.watch(self.e,self.a,self.key,direction=(1,0),blast_center=(7,4))
        self.e.rulings.add_answer('marksman_overwatch',{'weapon_id':self.key,'move_id':self.mid})
        before=self.b.hp
        with patch.object(Engine,'d20',return_value=20):FM.displace(self.e,self.c,self.b,direction=(0,-1),distance=1,source='actual native forced movement')
        self.assertLess(self.b.hp,before);self.assertEqual(self.a.spec[M.WATCH_STATE]['targets'],[self.b.entity_id])
        self.a.spec['feats'].remove(M.WATCH);self.assertIsNone(M.watch_state(self.e,self.a))

    def test_deadeye_missing_choice_decline_replay_and_scene_frequency(self):
        self.scene(features=(M.DEAD,));self.weapon();self.scheduled()
        first=M.declare_deadeye(self.e,self.a,request_id='deadeye/replay')
        self.assertEqual(M.declare_deadeye(self.e,self.a,request_id='deadeye/replay'),first)
        self.assertEqual(F.state(self.a)['activations'][M.DEAD]['used'],1)
        self.close_schedule();self.rejected(lambda:self.e.end_round(),'choose actual')
        M.deadeye_choice(self.e,self.a,use=False)
        self.rejected(lambda:M.deadeye_choice(self.e,self.a,use=False),'undecided')
        self.e.end_round();self.assertEqual(self.a.spec[M.DEAD_STATE]['phase'],'declined')
        self.scheduled();M.declare_deadeye(self.e,self.a,request_id='deadeye/second')
        self.close_schedule();M.deadeye_choice(self.e,self.a,use=False);self.e.end_round()
        self.scheduled()
        self.rejected(lambda:M.declare_deadeye(self.e,self.a,request_id='deadeye/third'),'frequency exhausted')

    def test_native_pending_double_cripple_and_clear_restore_resume_without_repayment(self):
        from common_checks import PendingDecision
        import passive_events as EVENTS
        for feature in (M.DOUBLE,M.CRIPPLE,M.CLEAR):
            self.scene(features=(feature,M.AIM,M.CLEAR));self.weapon();self.combat()
            if feature!=M.CRIPPLE:M.aim(self.e,self.a)
            M.arm_clear(self.e,self.a,self.mid,self.key)
            self.e.watch_move_defense(self.b,[{'actor_id':self.c.entity_id,'source':'maneuver/원거리-가로채기'}],reason='actual interrupted Marksman native attack')
            before=AP.available(self.a)
            def call():
                if feature==M.DOUBLE:return M.double_shot(self.e,self.a,self.b,self.key)
                if feature==M.CRIPPLE:return M.crippling_shot(self.e,self.a,self.b,self.key,use_trip=True,challenger_skill='통찰',defender_skill='곡예',fixed_accuracy=20,challenger_options={'fixed':[6]*6},defender_options={'fixed':[1]*5})
                return self.e.use_move(self.a,self.b,self.mid,weapon_id=self.key,set_damage=True)
            with patch.object(Engine,'d20',return_value=14):
                if feature==M.CLEAR:
                    with self.assertRaises(EVENTS.PassiveEventPending):call()
                else:self.assertIsInstance(call(),PendingDecision)
            self.assertIsNotNone(self.e._passive_pending)
            paid=AP.available(self.a);self.assertEqual(paid,before-({M.DOUBLE:1,M.CRIPPLE:2}.get(feature,0)))
            self.assertEqual(F.state(self.a)['activations'][M.CLEAR]['used'],1)
            self.restore();self.assertIsNotNone(self.e._passive_pending)
            with patch.object(Engine,'d20',return_value=14):
                self.e.choose_move_defense(self.e._passive_pending,self.c,use=False,reason='actual native defense decline')
                if feature!=M.CLEAR:
                    while True:
                        result=call()
                        if not isinstance(result,PendingDecision):break
                        self.e.choose_move_defense(self.e._passive_pending,self.c,use=False,reason='actual second native defense decline')
            self.assertEqual(AP.available(self.a),paid)
            self.assertEqual(F.state(self.a)['activations'][M.CLEAR]['used'],1)
            self.assertNotIn(M.WEAPON_ACTION,self.a.spec);self.assertFalse(getattr(self.e,'_marksman_attack',None))
            rows=[r for r in self.e._move_completions.values() if r['actor']is self.a]
            self.assertEqual(len(rows),2 if feature==M.DOUBLE else 1)
            self.assertTrue(all(r['phase']=='complete' and r['marksman_attack']['clear'] for r in rows))
            if feature==M.CRIPPLE:self.assertEqual(self.b.stages['spe'],-1)
            self.restore()

    def test_cripple_optional_trip_decline_keeps_native_hit_slow_stage_without_trip_roll_or_cost(self):
        import maneuver_opposed as OPPOSED
        self.scene(features=(M.CRIPPLE,));self.weapon();self.combat()
        before_ap=AP.available(self.a);before_hp=self.b.hp
        with patch.object(Engine,'d20',return_value=20) as accuracy,patch.object(OPPOSED,'_prepare',side_effect=AssertionError('declined Trip must not prepare or roll')):
            result=M.crippling_shot(self.e,self.a,self.b,self.key,use_trip=False,challenger_skill='매력',defender_skill='매력',fixed_accuracy=1)
        self.assertEqual(result,{'hit':True,'trip':None});self.assertEqual(accuracy.call_count,1)
        self.assertLess(self.b.hp,before_hp);self.assertIn('둔화',self.b.conditions);self.assertEqual(self.b.stages['spe'],-1)
        self.assertNotIn('넘어짐',self.b.conditions);self.assertEqual(AP.available(self.a),before_ap-2)
        self.assertEqual(self.a._action_history,['full','free']);self.assertNotIn(M.WEAPON_ACTION,self.a.spec);self.restore()

    def test_cripple_accepted_trip_actual_jump_pending_keeps_hit_effects_once_and_choice_fixed(self):
        from common_checks import PendingDecision
        from tumbler_fixture import TumblerScene
        import tumbler as TUMBLER,jump_actions as JUMP
        self.scene(features=(M.CRIPPLE,));self.weapon()
        self.b.spec.setdefault('edges',[]).append(TUMBLER.ACROBAT)
        self.b.spec['movement'].update(high_jump=1,long_jump=2,power=4);self.b.spec['weight_kg']=30
        fixture=TumblerScene();fixture.e=self.e;fixture.rules=self.rules;fixture.a=self.b;fixture.family(TUMBLER.FLIP)
        self.combat();self.e.watch_move_defense(self.b,[{'actor_id':self.b.entity_id,'source':TUMBLER.SPLASH}],reason='actual Trip hit permits actual Splash reaction')
        self.e.rulings.add_answer('native_attack_splash',{'jump':{'destination':(7,3),'difficult':True,'difficulty_skill':'곡예','difficulty_dc':100,'difficulty_options':{'fixed':[1]*5},'clear_path':True}})
        def call(use_trip=True):return M.crippling_shot(self.e,self.a,self.b,self.key,use_trip=use_trip,challenger_skill='통찰',defender_skill='곡예',fixed_accuracy=20,challenger_options={'fixed':[6]*6},defender_options={'fixed':[1]*5})
        with patch.object(Engine,'d20',return_value=20):self.assertIsInstance(call(),PendingDecision)
        self.e.choose_move_defense(self.e._passive_pending,self.b,use=False,reason='decline first weapon hit Splash, reserve actual Trip reaction')
        self.e.watch_move_defense(self.b,[{'actor_id':self.b.entity_id,'source':TUMBLER.SPLASH}],reason='new actual watch for the distinct Trip attack')
        with patch.object(Engine,'d20',return_value=20):self.assertIsInstance(call(),PendingDecision)
        self.assertIn('_jump_pending',self.b.spec);self.assertEqual(self.b.stages['spe'],-1)
        self.assertTrue(self.a.spec[M.WEAPON_ACTION]['hit_effects_applied']);hp=self.b.hp;ap=AP.available(self.a)
        self.restore();self.rejected(lambda:call(False),'resume the existing')
        jump_id=self.b.spec['_jump_pending'];JUMP.resolve_failure(self.e,self.b,decision='land',reason_text='actual failed Trip reaction Jump lands')
        self.e.resume_jump_move(self.b,event_id=jump_id)
        with patch.object(Engine,'accuracy_check',side_effect=AssertionError('actual weapon and Trip hits must not roll again')):result=call()
        self.assertTrue(result['trip']);self.assertEqual((self.b.hp,self.b.stages['spe'],AP.available(self.a)),(hp,-1,ap))
        self.assertEqual(self.a._action_history,['full','free']);self.assertEqual(self.b.move_uses[TUMBLER.SPLASH],1)
        self.assertNotIn(M.WEAPON_ACTION,self.a.spec);self.restore()

    def test_cripple_s001_english_required_trip_selected_at_acquisition_rejects_decline_before_cost(self):
        for edition in ('supplement','local_csv'):
            self.scene(features=(M.CRIPPLE,),edition=edition,trip_policy='english_required_trip');self.weapon();self.combat()
            self.assertEqual(M.acquired(self.a,M.CRIPPLE)['snapshot']['selection']['trip_policy'],'english_required_trip')
            self.rejected(lambda:M.crippling_shot(self.e,self.a,self.b,self.key,use_trip=False),'English Crippling Shot requires')
            with patch.object(Engine,'d20',return_value=20):
                result=M.crippling_shot(self.e,self.a,self.b,self.key,use_trip=True,challenger_skill='통찰',defender_skill='곡예',fixed_accuracy=20,challenger_options={'fixed':[6]*6},defender_options={'fixed':[1]*5})
            self.assertTrue(result['trip']);self.assertEqual(self.b.stages['spe'],-1);self.restore()

    def accept_ranged_intercept(self):
        import move_completion as MC
        self.e.choose_move_defense(self.e._passive_pending,self.c,use=True,options={
            'path':[(6,7),(6,6),(6,5),(6,4)],'skill':'육상','mode':'land','roll_options':{'fixed':[6]*5}},
            reason='actual successful ranged Intercept of the declared Marksman attack')
        row=next(r for r in self.e._move_completions.values() if r['actor']is self.a)
        self.assertEqual(row['targets'],[self.b]);self.assertIsNone(MC.recipient_result(row,self.b))
        receipt=MC.recipient_result(row,self.c)
        self.assertTrue(receipt['intercepted']);self.assertTrue(receipt['hit'])
        self.assertEqual(MC.require_hit_return(self.e,receipt['child_event'],self.c)['recipient_id'],self.c.entity_id)
        self.assertEqual(self.c.pos,(6,4));return row

    def test_successful_intercept_cripple_resistance_slow_stage_and_optional_trip_use_actual_recipient(self):
        from common_checks import PendingDecision
        import maneuver_opposed as OPPOSED
        for use_trip in (False,True):
            self.scene(features=(M.CRIPPLE,),positions=((2,4),(8,4),(6,7)));self.weapon();self.combat()
            self.e.watch_move_defense(self.b,[{'actor_id':self.c.entity_id,'source':'maneuver/원거리-가로채기'}],reason='actual Cripple interception')
            hp=(self.b.hp,self.c.hp);ap=AP.available(self.a);seen=[];original=Engine.roll_damage
            def damage(e,a,t,m,crit=False,*args,**kw):
                seen.append((t.entity_id,M.resistance(e,a,t,m),crit))
                return original(e,a,t,m,crit,*args,**kw)
            def call():return M.crippling_shot(self.e,self.a,self.b,self.key,use_trip=use_trip,challenger_skill='통찰',defender_skill='곡예',fixed_accuracy=20,challenger_options={'fixed':[6]*6},defender_options={'fixed':[1]*5})
            with patch.object(Engine,'d20',return_value=20):self.assertIsInstance(call(),PendingDecision)
            self.restore()
            with patch.object(Engine,'roll_damage',damage):row=self.accept_ranged_intercept()
            with patch.object(OPPOSED,'_prepare',wraps=OPPOSED._prepare) as prepare:
                result=call()
            self.assertEqual(result,{'hit':True,'trip':True if use_trip else None})
            self.assertEqual(prepare.call_count,int(use_trip));self.assertEqual(seen,[(self.c.entity_id,1,True)])
            self.assertEqual(self.b.hp,hp[0]);self.assertLess(self.c.hp,hp[1])
            self.assertFalse({'둔화','넘어짐'}&self.b.conditions);self.assertEqual(self.b.stages['spe'],0)
            self.assertIn('둔화',self.c.conditions);self.assertEqual(self.c.stages['spe'],-1)
            self.assertEqual('넘어짐'in self.c.conditions,use_trip);self.assertEqual(AP.available(self.a),ap-2)
            self.assertEqual(self.a._action_history,['full','free']);self.assertNotIn(M.WEAPON_ACTION,self.a.spec)
            self.assertEqual(row['targets'],[self.b]);self.restore()

    def test_successful_intercept_cripple_rejects_unpayable_extra_splash_atomically_then_trips_actual_recipient(self):
        """Full-next Intercept leaves no second next-Shift; do not invent a loan."""
        from common_checks import PendingDecision
        from tumbler_fixture import TumblerScene
        import tumbler as TUMBLER,action_resources as RESOURCES
        self.scene(features=(M.CRIPPLE,),positions=((2,4),(8,4),(6,7)));self.weapon()
        self.c.spec.setdefault('edges',[]).append(TUMBLER.ACROBAT)
        self.c.spec['movement'].update(high_jump=1,long_jump=2,power=4);self.c.spec['weight_kg']=30
        fixture=TumblerScene();fixture.e=self.e;fixture.rules=self.rules;fixture.a=self.c;fixture.family(TUMBLER.FLIP)
        self.combat();self.e.watch_move_defense(self.b,[{'actor_id':self.c.entity_id,'source':'maneuver/원거리-가로채기'}],reason='actual routed Cripple before Trip')
        def call(use_trip=True):return M.crippling_shot(self.e,self.a,self.b,self.key,use_trip=use_trip,challenger_skill='통찰',defender_skill='곡예',fixed_accuracy=20,challenger_options={'fixed':[6]*6},defender_options={'fixed':[1]*5})
        with patch.object(Engine,'d20',return_value=20):self.assertIsInstance(call(),PendingDecision)
        self.accept_ranged_intercept()
        self.e.watch_move_defense(self.c,[{'actor_id':self.c.entity_id,'source':TUMBLER.SPLASH}],reason='actual recipient reacts to its distinct Trip')
        self.e.rulings.add_answer('native_attack_splash',{'jump':{'destination':(6,3),'difficult':True,'difficulty_skill':'곡예','difficulty_dc':100,'difficulty_options':{'fixed':[1]*5},'clear_path':True}})
        hp=self.c.hp;ap=AP.available(self.a);original_hp=self.b.hp
        self.assertEqual(RESOURCES.pending(self.c),{'standard':1,'shift':1})
        self.rejected(call,'distinct next-action reaction costs')
        self.assertNotIn('_jump_pending',self.c.spec);self.assertNotIn('둔화',self.c.conditions)
        self.assertEqual(self.c.stages['spe'],0);self.restore()
        self.rejected(lambda:call(False),'resume the existing')
        self.e.rulings.answers=[r for r in self.e.rulings.answers if r['key']!='native_attack_splash']
        result=call()
        self.assertTrue(result['trip']);self.assertEqual((self.c.hp,self.c.stages['spe'],AP.available(self.a)),(hp,-1,ap))
        self.assertEqual(self.b.hp,original_hp);self.assertFalse({'둔화','넘어짐'}&self.b.conditions)
        self.assertEqual(self.c.move_uses.get(TUMBLER.SPLASH,0),0)
        self.assertEqual(RESOURCES.pending(self.c),{'standard':1,'shift':1})
        self.assertNotIn(M.WEAPON_ACTION,self.a.spec);self.restore()

    def test_successful_intercept_double_preserves_declared_foe_and_shared_clear_aim_critical(self):
        from common_checks import PendingDecision
        self.scene(features=(M.DOUBLE,M.AIM,M.CLEAR),positions=((2,4),(8,4),(6,7)));self.weapon();self.combat()
        M.aim(self.e,self.a);M.arm_clear(self.e,self.a,self.mid,self.key)
        self.e.watch_move_defense(self.b,[{'actor_id':self.c.entity_id,'source':'maneuver/원거리-가로채기'}],reason='actual first Double Shot interception')
        hp=(self.b.hp,self.c.hp);ap=AP.available(self.a);seen=[];original=Engine.roll_damage
        def damage(e,a,t,m,crit=False,*args,**kw):
            row=e._marksman_attack
            seen.append((t.entity_id,crit,row['target'].entity_id,row['clear'],row.get('repeated_aim'),M.resistance(e,a,t,m)))
            return original(e,a,t,m,crit,*args,**kw)
        with patch.object(Engine,'d20',return_value=14):self.assertIsInstance(M.double_shot(self.e,self.a,self.b,self.key),PendingDecision)
        self.restore()
        with patch.object(Engine,'roll_damage',damage),patch.object(Engine,'d20',return_value=14):
            self.accept_ranged_intercept();result=M.double_shot(self.e,self.a,self.b,self.key)
        self.assertEqual(result,[True,True]);self.assertEqual([x[0] for x in seen],[self.c.entity_id,self.b.entity_id])
        self.assertTrue(all(x[1] and x[2]==self.b.entity_id and x[3] and x[5]==0 for x in seen))
        self.assertEqual(seen[1][4],(2,2));self.assertLess(self.b.hp,hp[0]);self.assertLess(self.c.hp,hp[1])
        self.assertEqual(AP.available(self.a),ap-1);self.assertEqual(F.state(self.a)['activations'][M.CLEAR]['used'],1)
        self.assertEqual((self.a.budget['standard'],self.a.budget['swift']),(0,0));self.assertFalse(O.records(self.a,M.AIM))
        self.assertTrue(all(r['targets']==[self.b] for r in self.e._move_completions.values() if r['actor']is self.a));self.restore()

    def test_successful_intercept_regular_clear_aim_native_damage_uses_original_accuracy_witness(self):
        import passive_events as EVENTS
        self.scene(features=(M.AIM,M.CLEAR),positions=((2,4),(8,4),(6,7)));self.weapon();self.combat()
        M.aim(self.e,self.a);M.arm_clear(self.e,self.a,self.mid,self.key)
        self.e.watch_move_defense(self.b,[{'actor_id':self.c.entity_id,'source':'maneuver/원거리-가로채기'}],reason='actual ordinary Clear Shot interception')
        hp=self.b.hp;seen=[];original=Engine.roll_damage
        def damage(e,a,t,m,crit=False,*args,**kw):
            seen.append((t.entity_id,crit,M.resistance(e,a,t,m)));return original(e,a,t,m,crit,*args,**kw)
        with patch.object(Engine,'d20',return_value=14):
            with self.assertRaises(EVENTS.PassiveEventPending):self.e.use_move(self.a,self.b,self.mid,weapon_id=self.key,set_damage=True)
        self.restore()
        with patch.object(Engine,'roll_damage',damage),patch.object(Engine,'accuracy_check',side_effect=AssertionError('Intercept must keep original accuracy')):self.accept_ranged_intercept()
        self.assertEqual(seen,[(self.c.entity_id,True,0)]);self.assertEqual(self.b.hp,hp)
        self.assertFalse(O.records(self.a,M.AIM));self.assertEqual(F.state(self.a)['activations'][M.CLEAR]['used'],1);self.restore()

    def test_successful_intercept_overwatch_tracks_moving_foe_not_actual_damage_recipient(self):
        self.scene(features=(M.WATCH,),positions=((2,4),(8,5),(6,7)));self.weapon();self.combat()
        M.watch(self.e,self.a,self.key,direction=(1,0),blast_center=(8,4))
        self.e.end_of_turn(self.a);self.e.start_of_turn(self.b,initiative_count=15)
        self.e.watch_move_defense(self.b,[{'actor_id':self.c.entity_id,'source':'maneuver/원거리-가로채기'}],reason='actual moving-foe Overwatch interception')
        self.e.rulings.add_answer('marksman_overwatch',{'weapon_id':self.key,'move_id':self.mid})
        hp=(self.b.hp,self.c.hp)
        with patch.object(Engine,'d20',return_value=20):self.walk(self.b,[(8,4)])
        self.assertIsNotNone(self.e._passive_pending)
        self.restore();self.assertIs(self.e._active_turn_actor,self.b)
        self.e.rulings.answers=[r for r in self.e.rulings.answers if r['key']!='marksman_overwatch']
        proof=next(iter(self.e._move_completions.values()))['marksman_attack']['watch_reaction']
        with patch.dict(proof,{'fingerprint':'0'*64}):
            self.rejected(lambda:self.accept_ranged_intercept(),'actual Overwatch native attack origin changed')
        self.accept_ranged_intercept()
        self.assertEqual(self.b.hp,hp[0]);self.assertLess(self.c.hp,hp[1])
        self.assertEqual(self.a.spec[M.WATCH_STATE]['targets'],[self.b.entity_id])
        self.e.rulings.add_answer('marksman_overwatch',{'weapon_id':self.key,'move_id':self.mid})
        import forced_movement as FM
        FM.displace(self.e,self.c,self.b,direction=(0,-1),distance=1,source='same actual watched foe moves again')
        self.assertEqual(self.b.hp,hp[0]);self.assertEqual(len(self.e._move_completions),1);self.restore()

    def test_successful_intercept_deadeye_lower_choice_critical_uses_actual_recipient_at_round_end(self):
        from common_checks import PendingDecision
        self.scene(features=(M.DEAD,),release='english_optional_shift',positions=((2,4),(8,4),(6,7)));self.weapon();self.scheduled()
        M.declare_deadeye(self.e,self.a,request_id='deadeye/successful-intercept');self.close_schedule()
        self.e.watch_move_defense(self.b,[{'actor_id':self.c.entity_id,'source':'maneuver/원거리-가로채기'}],reason='actual round-end Intercept after paid Priority')
        M.deadeye_choice(self.e,self.a,use=True,target=self.b,weapon_id=self.key,move_id=self.mid)
        self.e.rulings.add_answer('marksman_deadeye_accuracy',0);hp=self.b.hp;seen=[];original=Engine.roll_damage
        def damage(e,a,t,m,crit=False,*args,**kw):
            seen.append((t.entity_id,crit,M.resistance(e,a,t,m)));return original(e,a,t,m,crit,*args,**kw)
        with patch.object(Engine,'d20',side_effect=[10,18]):self.assertIsInstance(self.e.end_round(),PendingDecision)
        self.restore();self.assertIsNone(self.e._active_turn_actor)
        with patch.object(Engine,'roll_damage',damage),patch.object(Engine,'accuracy_check',side_effect=AssertionError('actual round-end accuracy must not repeat')):row=self.accept_ranged_intercept()
        self.e.end_round();self.assertEqual(seen,[(self.c.entity_id,True,0)]);self.assertEqual(self.b.hp,hp)
        self.assertEqual(row['marksman_attack']['rolls'],[10,18]);self.assertTrue(row['marksman_attack']['lower'])
        self.assertEqual(self.a.spec[M.DEAD_STATE]['phase'],'complete');self.assertEqual(F.state(self.a)['activations'][M.DEAD]['used'],1);self.restore()

    def test_native_pending_watch_paid_forced_frequency_and_deadeye_round_end_resume(self):
        from common_checks import PendingDecision
        import forced_movement as FM
        for forced in (False,True):
            self.scene(features=(M.WATCH,),positions=((2,4),(7,3),(12,9)));self.weapon();self.combat()
            M.watch(self.e,self.a,self.key,direction=(1,0),blast_center=(7,4))
            self.e.end_of_turn(self.a);self.e.start_of_turn(self.b,initiative_count=15)
            self.e.watch_move_defense(self.b,[{'actor_id':self.c.entity_id,'source':'maneuver/원거리-가로채기'}],reason='actual native Overwatch defense')
            self.e.rulings.add_answer('marksman_overwatch',{'weapon_id':self.key,'move_id':self.mid})
            with patch.object(Engine,'d20',return_value=10):
                if forced:
                    out=FM.displace(self.e,self.c,self.b,direction=(0,-1),distance=2,source='actual forced exit with pending reaction')
                    self.assertEqual(out['stopped_by'],'pending')
                else:self.walk(self.b,[(7,2),(7,1)])
            self.assertEqual(self.b.pos,(7,2));self.assertIsNotNone(self.e._passive_pending)
            self.restore()
            with patch.object(Engine,'d20',return_value=10):self.e.choose_move_defense(self.e._passive_pending,self.c,use=False,reason='actual Overwatch defense decline')
            self.assertFalse(getattr(self.e,'_marksman_attack',None));self.assertEqual(self.a.spec[M.WATCH_STATE]['targets'],[self.b.entity_id])
        self.scene(features=(M.WATCH,),positions=((2,4),(7,3),(8,3)));self.weapon();self.combat()
        M.watch(self.e,self.a,self.key,direction=(1,0),blast_center=(7,4))
        self.e.rulings.add_answer('marksman_overwatch',{'weapon_id':self.key,'move_id':'move/불스아이'})
        with patch.object(Engine,'d20',return_value=10):FM.displace(self.e,self.c,self.b,direction=(0,-1),distance=1,source='first actual Overwatch frequency use')
        before=self.c.hp
        FM.displace(self.e,self.b,self.c,direction=(0,-1),distance=1,source='second actual foe with exhausted move')
        self.assertEqual(self.c.hp,before);self.assertNotIn(self.c.entity_id,self.a.spec[M.WATCH_STATE]['targets'])
        self.scene(features=(M.DEAD,),release='english_optional_shift');self.weapon();self.scheduled()
        M.declare_deadeye(self.e,self.a,request_id='deadeye/actual-pending');self.close_schedule()
        self.e.watch_move_defense(self.b,[{'actor_id':self.c.entity_id,'source':'maneuver/원거리-가로채기'}],reason='actual no-owner round-end defense')
        M.deadeye_choice(self.e,self.a,use=True,target=self.b,weapon_id=self.key,move_id=self.mid)
        self.e.rulings.add_answer('marksman_deadeye_accuracy',0);before=self.e.elapsed_seconds
        with patch.object(Engine,'d20',side_effect=[10,18]):self.assertIsInstance(self.e.end_round(),PendingDecision)
        self.assertEqual(self.e.elapsed_seconds,before);self.assertIsNotNone(self.e._passive_pending)
        self.restore()
        self.e.choose_move_defense(self.e._passive_pending,self.c,use=False,reason='actual round-end native defense decline')
        token=self.a.spec[M.DEAD_STATE]['completion_id'];self.assertEqual(self.e._move_completions[token]['phase'],'complete')
        self.e.end_round();self.assertEqual(self.a.spec[M.DEAD_STATE]['phase'],'complete')
        self.assertEqual(F.state(self.a)['activations'][M.DEAD]['used'],1);self.restore()

    def test_modern_aim_receipt_preserves_selected_short_range_scope_through_native_wait(self):
        import passive_events as EVENTS,move_completion as COMPLETE
        for selected,eligible in (('korean_ranged',True),('english_long_range',False)):
            self.scene(features=(M.AIM,),aim_scope=selected,positions=((2,4),(6,4),(12,9)))
            self.weapon('단거리 사격무기',moves=());self.combat();M.aim(self.e,self.a)
            self.e.watch_move_defense(self.b,[{'actor_id':self.c.entity_id,'source':'maneuver/원거리-가로채기'}],reason='actual selected-scope native accuracy wait')
            with patch.object(Engine,'d20',return_value=18),self.assertRaises(EVENTS.PassiveEventPending):
                self.e.use_move(self.a,self.b,self.mid,weapon_id=self.key,set_damage=True)
            event=self.e._passive_pending;row=list(self.e._move_completions.values())[-1]
            self.assertEqual(len(row['optional_aiming']),int(eligible))
            self.assertEqual(bool(O.records(self.a,M.AIM)),not eligible)
            self.restore();hp=self.b.hp
            with patch.object(Engine,'accuracy_check',side_effect=AssertionError('actual saved accuracy cannot reroll')):
                self.e.choose_move_defense(event,self.c,use=False,reason='actual selected-scope defense decline')
            self.assertLess(self.b.hp,hp);COMPLETE.require_returned_event(self.e,event)
            self.assertEqual(self.a.move_uses[self.mid],1)
            self.assertTrue(self.e.validate_state()['valid']);self.restore()

    def test_armed_clear_grouped_weapon_return_restores_activation_aliases_and_aim_once(self):
        import passive_events as EVENTS,move_completion as COMPLETE,fast_combat as FAST
        from test_native_return_continuation import NativeReturnContinuationTests as RETURNS
        self.scene(features=(M.AIM,M.CLEAR),positions=((2,4),(7,4),(8,4)))
        mid='move/3중공격';self.weapon(moves=(mid,));self.combat();M.aim(self.e,self.a)
        # Clear is armed for Struggle, not this distinct multi-target Move.
        # Its actual atomic wrapper must still preserve the issued group aliases.
        M.arm_clear(self.e,self.a,self.mid,self.key)
        policy=RETURNS.policy(self,'marksman-grouped-return');hp=[a.hp for a in (self.b,self.c)]
        before=AP.available(self.a)
        with patch.object(FAST,'roll',return_value=18),self.assertRaises(EVENTS.PassiveEventPending):
            self.e.use_move_on(self.a,self.b,mid,self.e.everyone,weapon_id=self.key,set_damage=True)
        event=self.e._passive_pending;token=list(self.e._move_completions)[-1]
        self.assertLess(self.b.hp,hp[0]);self.assertEqual(self.c.hp,hp[1])
        self.assertEqual(len(self.e._move_completions[token]['optional_aiming']),1)
        self.assertFalse(O.records(self.a,M.AIM));self.assertIn(M.ARM,self.a.spec)
        self.restore();first_hp=self.b.hp
        with patch.object(FAST,'roll',return_value=18),self.assertRaises(EVENTS.PassiveEventPending):
            RETURNS.choose(self,event,policy)
        later=self.e._passive_pending;self.assertNotEqual(event,later)
        self.assertEqual(self.b.hp,first_hp);self.assertLess(self.c.hp,hp[1])
        self.restore();hp=[a.hp for a in (self.b,self.c)];rng=self.e.rng.getstate()
        with patch.object(FAST,'roll',side_effect=AssertionError('saved native accuracy cannot reroll')):
            RETURNS.choose(self,later,policy)
        row=self.e._move_completions[token]
        self.assertEqual((row['phase'],len(row['native_returns']),len(row['optional_aiming'])),('complete',2,1))
        self.assertEqual(([a.hp for a in (self.b,self.c)],self.e.rng.getstate(),AP.available(self.a)),(hp,rng,before))
        self.assertEqual((self.a.move_uses[mid],self.a._action_history.count('standard'),self.a.stages['atk']),(1,1,2))
        self.assertIn(M.ARM,self.a.spec);self.assertNotIn(M.CLEAR,F.state(self.a)['activations'])
        for identity in (event,later):COMPLETE.require_returned_event(self.e,identity)
        saved=self.e.export_state();self.assertEqual(self.e.deliver_passive_event(later),'already_delivered')
        self.assertEqual(self.e.export_state(),saved);self.restore();self.assertTrue(self.e.validate_state()['valid'])

    def test_paid_overwatch_path_waits_for_actual_return_before_resuming_saved_prefix(self):
        import movement_actions as MOVE
        self.scene(features=(M.WATCH,),positions=((2,4),(7,3),(12,9)));self.weapon();self.combat()
        M.watch(self.e,self.a,self.key,direction=(1,0),blast_center=(7,4))
        self.e.end_of_turn(self.a);self.e.start_of_turn(self.b,initiative_count=15)
        self.e.watch_move_defense(self.b,[{'actor_id':self.c.entity_id,'source':'maneuver/원거리-가로채기'}],reason='actual paid path Overwatch wait')
        self.e.rulings.add_answer('marksman_overwatch',{'weapon_id':self.key,'move_id':self.mid})
        self.assertTrue(turn.spend(self.e,self.b,'shift','actual paid Overwatch path',movement=True))
        self.b.spec['marksman_test_paid_path']={};path=[(7,2),(7,1)]
        def follow():return MOVE.follow_paid_path(self.e,self.b,path,mode='land',maximum_distance=6,progress=self.b.spec['marksman_test_paid_path'])
        with patch.object(Engine,'d20',return_value=10):follow()
        event=self.e._passive_pending;self.assertEqual(self.b.pos,(7,2))
        self.assertEqual(self.b.spec['marksman_test_paid_path']['marksman_events'],[event])
        self.rejected(follow,'return|resolved|complete|producer|native')
        self.restore()
        with patch.object(Engine,'d20',return_value=10):
            self.e.choose_move_defense(event,self.c,use=False,reason='actual paid path defense decline')
        follow();self.assertEqual(self.b.pos,(7,1))
        self.assertEqual(self.b.spec['marksman_test_paid_path']['phase'],'complete')
        self.assertEqual(self.b._action_history.count('shift'),1)
        self.assertEqual(self.a.spec[M.WATCH_STATE]['targets'],[self.b.entity_id]);self.restore()

    def test_all_seven_withdrawals_archive_real_sources_stats_slots_and_replay_without_reacquiring(self):
        self.scene(features=tuple(M.FEATURES));before=self.initial_atk
        sources={row['static_acquisition']['feature_id']:sid for sid,row in G.state(self.a)['sources'].items() if row.get('static_acquisition',{}).get('feature_id') in M.FEATURES}
        def withdraw(e,a):
            for feature in reversed(tuple(M.FEATURES)):
                G.revoke(a,sources[feature],engine=e);a.spec['feats'].remove(feature)
        G.transition(self.e,self.a,withdraw)
        self.assertEqual((self.a.stats['atk'],len(AC.class_instances(self.a))),(before,0))
        self.assertNotIn(M.CORE_SNIPER_NAME,self.a.abilities);self.restore()
        self.assertEqual(len(M.records(self.a)),7);self.assertFalse(M.records(self.a,active=True))
        for feature in M.FEATURES:
            selection={'edition':'supplement'}
            if feature==M.CLASS:selection['sniper']='core_105'
            if feature==M.AIM:selection['weapon_scope']='korean_ranged'
            if feature==M.CRIPPLE:selection['trip_policy']='korean_optional_trip'
            if feature==M.DEAD:selection['release_policy']='korean_shift_attack'
            receipt=T.acquire_static(self.e,self.a,feature,acquisition_request_id='marksman/acquire/'+feature,selection=selection)
            self.assertEqual(receipt['status'],'withdrawn')
        self.assertEqual((self.a.stats['atk'],len(AC.class_instances(self.a))),(before,0));self.restore()

    def test_marksman_class_alias_has_one_slot_in_fast_and_callback_fallback_indexes(self):
        from collections import UserDict
        self.scene(features=(M.CLASS,))
        for units in (self.rules.selection.units,UserDict(self.rules.selection.units)):
            with patch.object(self.rules.selection,'units',units):
                self.assertEqual(AC._names(self.a,'class/')[M.CLASS],[M.CLASS])
                self.assertNotIn(M.CLASS,AC._names(self.a,'supp-fantasy/'))
                self.assertEqual((AC.owned_rule_count(self.a,M.CLASS),len(AC.class_instances(self.a))),(1,1))
        self.restore();self.assertTrue(self.e.validate_state()['valid'])


if __name__=='__main__':unittest.main(verbosity=2)
