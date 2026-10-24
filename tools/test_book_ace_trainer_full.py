"""Ace Trainer: actual acquisitions, training, injury and twelve Move consumers."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import hashlib
import json
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from grid import Grid
from native_scenario_fixture import prepare_body,assert_rejected_unchanged
import test_category2_training_state as FIX
import ace_trainer as A
import trainer_feature_acquisition as ACQ
import training_features as TRAIN
import state_grants as G
import state_codec as CODEC
import world_entities as W
import action_points as AP
import combat_stage_sources as CS
import combat_timing as TIME
import frequency as F


class AceTrainerFullTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.rules=Rules(ROOT,ruleset='core')

    def setUp(self):
        previous=self.rules.rulings;self.rules.rulings=deepcopy(previous)
        self.addCleanup(setattr,self.rules,'rulings',previous)
        self.setup()

    def setup(self,rank=6):
        helper=FIX.TrainingStateTests();helper.r=self.rules;helper.setUp()
        self.e,self.t,self.ps,self.foe=helper.e,helper.t,helper.ps,helper.enemy
        self.p,self.q=self.ps[:2]
        self.t.spec['feats']=[];self.t.spec['classes']=[]
        self.t.spec['skills']={'명령':rank,'육상':3,'협박':3,'매력':3}
        self.e.grid=Grid(24,16)
        positions=[(2,2),(3,2),(3,3),(4,3),(5,3),(4,2)]
        for a,pos in zip([self.t,*self.ps,self.foe],positions):
            self.e.gm.set_position(a,pos,reason='actual Ace scene geometry')
            prepare_body(self.e,a,size='중형',offsets=[(0,0)],reason='actual Ace participant body')
        for p in self.ps:p.spec['tutor_points']=20
        self.serial=0

    def acquire(self,feature=A.CLASS,*,selection=None,request=None):
        return ACQ.acquire_static(self.e,self.t,feature,selection=selection,
            acquisition_request_id=request or self.t.entity_id+'/'+feature)

    def family(self,feature,*,gift=TRAIN.AGILITY):
        if feature==A.CHAMP:
            for u in (A.CLASS,A.PERSEVERANCE,A.ELITE,A.TOP):self.family(u,gift=gift)
        else:
            for parent in A.PARENTS[feature]:self.family(parent,gift=gift)
        if not A.acquired(self.t,feature):
            if feature==A.ELITE and all(A.acquired(self.t,u) for u in TRAIN.RULES):
                gift=next(u for u in (A.PERSEVERANCE,A.TOP,A.CRITICAL,A.SIGNATURE) if not A.acquired(self.t,u))
            self.acquire(feature,selection={'feature':gift,'options':{}} if feature==A.ELITE else None)

    def all_training(self):
        for u in TRAIN.RULES:
            if not A.acquired(self.t,u):self.acquire(u)

    def teach(self,mod,move,*,pokemon=None,contract='core_1.05',clause='C04-011',request=None):
        self.family(A.SIGNATURE);self.all_training();p=pokemon or self.p
        self.e.gm.set_move(p,move,reason='actual learned Technique candidate')
        self.serial+=1
        return self.e.teach_signature_technique(self.t,p,move_id=move,modification=mod,
            request_id=request or 'technique-'+str(self.serial),source_contract=contract,source_clause_id=clause)

    def close(self):
        if self.e._active_turn_actor is not None:self.e.end_of_turn(self.e._active_turn_actor)

    def begin(self,actor=None,count=60):
        self.close();self.e.start_round(self.e.everyone);self.e.start_of_turn(actor or self.p,initiative_count=count)

    def turn(self,actor,count=50):self.close();self.e.start_of_turn(actor,initiative_count=count)

    def completion(self,actor=None):
        actor=actor or self.p
        return [r for r in self.e._move_completions.values() if r['actor'] is actor][-1]

    def attack(self,move,*,actor=None,target=None,face=18,targets=None):
        p=actor or self.p;t=target or self.foe;self.begin(p)
        with patch.object(Engine,'d20',return_value=face):
            self.e.use_move_on(p,t,move,[t] if targets is None else targets,set_damage=True)
        row=self.completion(p);self.assertEqual(row['phase'],'complete');return row

    def train(self,regimes,*,stats=None,request='actual-training',source='C04-009'):
        options={} if stats is None else {'trained_stats':stats,'source_clause_id':source}
        return self.e.train_pokemon(self.t,[(p,regimes) for p in self.ps],minutes=30,
            reason='observed actual Ace training session',request_id=request,safe=True,**options)

    def reject(self,operation,reason):return assert_rejected_unchanged(self.e,operation,reason_pattern=reason)

    def restore(self):
        ids=[a.entity_id for a in [self.t,*self.ps,self.foe]]
        self.e=CODEC.load_engine(self.rules,json.loads(json.dumps(self.e.export_state(),ensure_ascii=False)))
        actors=W.actor_index(self.e);self.t=actors[ids[0]];self.ps=[actors[u] for u in ids[1:-1]]
        self.p=self.ps[0];self.q=self.ps[1] if len(self.ps)>1 else self.p;self.foe=actors[ids[-1]]

    def valid(self):
        result=self.e.validate_state();self.assertTrue(result['valid'],result['issues'])

    def retrain(self,feature):
        import trainer_retraining as R
        owned=R._owned(self.t);sources={u:R.owned_source(self.e,self.t,u) for u in owned}
        required=R._native_dependencies(self.e,self.t,owned)
        deps={sid:[sources[p] for p in required.get(u,[])] for u,sid in sources.items() if u!=feature}
        return self.e.retrain_trainer_source(self.t,feature,request_id='retrain:'+feature,
            reason='actual consultation',gm_decision={'allowed':True,'reason':'approved'},retained_dependencies=deps)

    def test_seven_actual_acquisitions_no_auto_siblings_and_parent_rank_gates(self):
        self.acquire();self.assertEqual([r['feature_id'] for r in A.records(self.t,active=True)],[A.CLASS])
        self.assertNotIn(A.ELITE,self.t.spec['feats'])
        self.reject(lambda:self.acquire(A.SIGNATURE),'parent')
        for u in A.FEATURES:self.family(u)
        self.assertEqual({r['feature_id'] for r in A.records(self.t,active=True)}&set(A.FEATURES),set(A.FEATURES))
        self.restore();self.valid()
        self.setup(rank=3);self.family(A.ELITE)
        self.reject(lambda:self.acquire(A.CRITICAL),'Command|command')
        self.reject(lambda:self.acquire(A.TOP),'Command|command')
        self.reject(lambda:self.acquire(A.CHAMP),'four|Command|command')

    def test_elite_actual_gift_waiver_and_two_real_training_regimes(self):
        self.t.spec['skills']['육상']=1;self.acquire()
        self.reject(lambda:self.acquire(TRAIN.AGILITY),'Training prerequisite')
        self.family(A.ELITE)
        gift=A.acquired(self.t,TRAIN.AGILITY)
        self.assertEqual(gift['snapshot']['gift'],{'elite_parent':A.acquired(self.t,A.ELITE)['request_id']})
        self.assertTrue(any(c['state']=='waived' and c['id']=='training_skills' for c in gift['qualification']['checks']))
        self.acquire(TRAIN.FOCUSED);self.train([TRAIN.AGILITY,TRAIN.FOCUSED])
        self.assertEqual((TRAIN.bonus(self.p,'movement'),TRAIN.bonus(self.p,'accuracy')),(1,1))
        self.reject(lambda:self.train([TRAIN.AGILITY,TRAIN.FOCUSED,TRAIN.INSPIRED],request='three-regimes'),'regime limit')
        self.restore();self.valid()

    def test_elite_all_four_owned_gets_one_other_qualified_feature_atomically(self):
        self.acquire();self.all_training()
        self.reject(lambda:self.acquire(A.ELITE,selection={'feature':TRAIN.FOCUSED,'options':{}}),'another qualified')
        self.acquire(A.ELITE,selection={'feature':A.PERSEVERANCE,'options':{}})
        self.assertTrue(A.acquired(self.t,A.PERSEVERANCE))
        self.assertEqual(A.acquired(self.t,A.PERSEVERANCE)['request_id'],A.acquired(self.t,A.ELITE)['request_id']+'/gift')
        self.restore();self.valid()

    def test_elite_unqualified_alternate_and_changed_replay_do_not_leave_parent(self):
        self.setup(rank=3);self.acquire();self.all_training()
        self.reject(lambda:self.acquire(A.ELITE,selection={'feature':A.SIGNATURE,'options':{}}),'Command|command')
        self.assertFalse(A.acquired(self.t,A.ELITE))
        self.family(A.ELITE,gift=TRAIN.AGILITY) if not all(A.acquired(self.t,u) for u in TRAIN.RULES) else self.acquire(A.ELITE,selection={'feature':A.PERSEVERANCE,'options':{}})
        self.reject(lambda:self.acquire(A.ELITE,selection={'feature':A.TOP,'options':{}}),'selection|intent')

    def test_champ_two_different_stats_one_extra_session_drain_and_rest(self):
        self.family(A.CHAMP);self.all_training();before=AP.available(self.t)
        stats={p.entity_id:['atk','spe'] for p in self.ps}
        row=self.train([TRAIN.FOCUSED,TRAIN.AGILITY],stats=stats)
        self.assertEqual(AP.available(self.t),before-2);self.assertEqual(row['ap_removed'],2)
        self.assertEqual(len(row['trained_stat_sources']),2*len(self.ps))
        for p in self.ps:
            self.assertEqual((p.stages['atk'],p.stages['spe']),(1,1));self.assertEqual(len(TRAIN.validate_trained(p)),2)
        self.assertEqual(self.train([TRAIN.FOCUSED,TRAIN.AGILITY],stats=stats),row)
        self.restore();self.valid()
        __import__('downtime').extended_rest(self.e,self.p,4)
        self.assertFalse(TRAIN.stat_records(self.p));self.assertEqual(len(TRAIN.stat_records(self.q)),2)

    def test_two_stats_require_actual_champ_distinct_nonhp_and_extra_ap(self):
        self.acquire();self.all_training()
        self.reject(lambda:self.train([TRAIN.FOCUSED],stats={p.entity_id:['atk','spe'] for p in self.ps}),'Champ')
        self.family(A.CHAMP)
        for values in (['atk','atk'],['atk','hp'],['atk','def','spe']):
            self.reject(lambda:self.train([TRAIN.FOCUSED],stats={p.entity_id:values for p in self.ps}),'non-HP|different')
        self.t.spec['ap_removed']=AP.maximum(self.t)-1
        self.reject(lambda:self.train([TRAIN.FOCUSED],stats={p.entity_id:['atk','spe'] for p in self.ps}),'AP')

    def test_csv55_actual_session_source_and_normal_single_stat_remain_distinct(self):
        self.acquire();stats={p.entity_id:'atk' for p in self.ps}
        row=self.train([],stats=stats,source='C2CSV/input/db/feats.csv:R55:main')
        self.assertEqual(row['ap_removed'],1)
        self.assertTrue(all(r['source_clause_id']=='C2CSV/input/db/feats.csv:R55:main' for r in row['trained_stat_sources']))
        self.assertTrue(all(len(TRAIN.validate_trained(p))==1 for p in self.ps));self.restore();self.valid()

    def test_critical_all_eight_actual_bonus_fields_two_regimes_and_issuer_expiry(self):
        self.family(A.CRITICAL);self.all_training()
        self.e.train_pokemon(self.t,[(self.p,[TRAIN.AGILITY,TRAIN.BRUTAL]),(self.q,[TRAIN.FOCUSED,TRAIN.INSPIRED])],
            minutes=30,reason='actual two regimes per recipient',request_id='critical-training',safe=True)
        for p in self.ps:self.e.gm.observe_sensory_environment(self.t,p,paths={'auditory':True},present=True,reason='actual audible Critical Moment Order')
        self.e.start_round(self.e.everyone);self.e.critical_moment(self.t,[self.p,self.q])
        self.assertEqual([TRAIN.bonus(self.p,f) for f in ('movement','initiative','critical','effect')],[3,12,3,3])
        self.assertEqual([TRAIN.bonus(self.q,f) for f in ('accuracy','skill','evasion','save')],[3,6,3,6])
        self.assertEqual(self.e.move_profile(self.p,'land')[0],9)
        self.assertEqual(self.e.skill_roll(self.q,'육상',fixed=[1,1]).total,9)
        self.assertEqual(__import__('effects_ext').save_dc(self.e,self.q,'마비',11),5)
        self.e.start_of_turn(self.p,initiative_count=60);self.close()
        self.e.start_of_turn(self.t,initiative_count=50);self.assertEqual(TRAIN.bonus(self.p,'movement'),3)
        self.close();self.assertEqual(TRAIN.bonus(self.p,'movement'),1);self.restore();self.valid()

    def test_critical_same_training_and_orders_contributions_stack_three_plus_one(self):
        self.family(A.CRITICAL);self.all_training()
        import taskmaster as TASK
        self.t.spec['skills']['협박']=6;self.acquire(TASK.CLASS)
        self.t.spec['feats'].append(TASK.PRESS_ACTION)  # Existing Press owner accepts observed ownership.
        self.acquire(TASK.WHIP)
        self.e.rulings.add_answer('taskmaster',1,reason='actual one-injury Hardened choice',scope='permanent')
        self.train([TRAIN.FOCUSED,TRAIN.BRUTAL]);self.begin(self.t)
        self.e.gm.observe_sensory_environment(self.t,self.p,paths={'auditory':True},present=True,reason='actual audible Whip Free Order before Press')
        self.e.manual_feat(self.t,TASK.PRESS_ACTION,self.p,adjustment={'stats':['atk','spe'],'whip':{'order':A.CRITICAL}})
        self.close()
        for p in self.ps:self.e.gm.observe_sensory_environment(self.t,p,paths={'auditory':True},present=True,reason='actual audible Critical Moment Order')
        self.e.start_round(self.e.everyone);self.e.manual_feat(self.t,TRAIN.FOCUSED,self.p)
        # Critical still lives until end of issuer's next actual turn, Orders
        # p60 contribution has its separate next-turn-start lifetime.
        self.assertEqual((TRAIN.bonus(self.p,'accuracy'),TRAIN.bonus(self.p,'skill')),(4,8))
        self.e.start_of_turn(self.t,initiative_count=60);self.assertEqual(TRAIN.bonus(self.p,'accuracy'),3)
        self.close();self.assertEqual(TRAIN.bonus(self.p,'accuracy'),1)

    def test_critical_requires_actual_training_and_scene_two_delivery(self):
        self.family(A.CRITICAL);self.e.start_round(self.e.everyone)
        self.reject(lambda:self.e.critical_moment(self.t,[self.p]),'Training Feature')
        self.e.end_encounter(self.e.everyone);self.all_training();self.train([TRAIN.FOCUSED])
        for _ in range(2):
            for p in self.ps:self.e.gm.observe_sensory_environment(self.t,p,paths={'auditory':True},present=True,reason='actual audible Critical Moment Order')
            self.e.start_round(self.e.everyone);self.e.critical_moment(self.t,[self.p]);self.e.start_of_turn(self.t,initiative_count=60);self.close()
        self.e.start_round(self.e.everyone)
        self.reject(lambda:self.e.critical_moment(self.t,[self.p]),'frequency')

    def test_perseverance_prevents_before_marker_consumers_per_target_scene(self):
        self.family(A.PERSEVERANCE);self.begin(self.foe);before=AP.available(self.t)
        self.e.arm_perseverance(self.t,self.p,source='combat/hit-point-markers',ordinal=1,request_id='prevent-p')
        self.e.lose_hp(self.p,self.p.hp-self.p.base_max_hp//2,source='actual loss crossing marker',loss_kind='loss')
        self.assertEqual(self.p.injuries,0);self.assertEqual(AP.available(self.t),before-1)
        self.assertFalse(__import__('precise_actions').evidence(self.e,self.p)['injuries'])
        self.e.arm_perseverance(self.t,self.q,source='combat/hit-point-markers',ordinal=1,request_id='prevent-q')
        self.e.lose_hp(self.q,self.q.hp-self.q.base_max_hp//2,source='actual independent target marker',loss_kind='loss')
        self.assertEqual(self.q.injuries,0);self.assertEqual(AP.available(self.t),before-2)
        self.restore();self.valid()

    def test_perseverance_one_of_simultaneous_injuries_exact_source_and_no_healing(self):
        self.family(A.PERSEVERANCE);self.begin(self.foe)
        self.e.arm_perseverance(self.t,self.p,source='combat/hit-point-markers',ordinal=2,request_id='select-second')
        before=AP.available(self.t);self.e.take_damage(self.p,self.p.base_max_hp)
        # One massive injury plus two crossed half-HP markers; only one of
        # the explicitly selected marker gains is prevented before consumers.
        self.assertEqual(self.p.injuries,2);self.assertEqual(AP.available(self.t),before-1)
        self.assertEqual(self.t.spec['perseverance_preventions'][-1]['source'],'combat/hit-point-markers')
        self.assertEqual(self.t.spec['perseverance_preventions'][-1]['ordinal'],2)
        self.e.arm_perseverance(self.t,self.p,source=None,request_id='decline')
        self.assertEqual(self.p.injuries,2)

    def test_perseverance_gm_correction_and_restore_never_retrigger_prevention(self):
        self.family(A.PERSEVERANCE);self.begin(self.foe);before=AP.available(self.t)
        self.e.arm_perseverance(self.t,self.p,source='combat/hit-point-markers',request_id='pending-real-gain')
        self.e.gm.set_injuries(self.p,value=1,reason='administrative current-count correction')
        self.assertEqual(AP.available(self.t),before);self.assertFalse(self.t.spec.get('perseverance_preventions'))
        self.restore();self.assertEqual(AP.available(self.t),before)
        self.e.lose_hp(self.p,self.p.hp-self.p.base_max_hp//2,source='actual loss after restored choice',loss_kind='loss')
        self.assertEqual(self.p.injuries,1);self.assertEqual(AP.available(self.t),before-1)
        self.assertEqual(len(self.t.spec['perseverance_preventions']),1);self.valid()

    def test_signature_two_tp_precondition_one_active_replace_forget_refund_once(self):
        first=self.teach('alternative_energy','move/할퀴기',request='first');self.assertEqual(self.p.spec['tutor_points'],18)
        self.p.spec['tutor_points']=1
        self.reject(lambda:self.e.teach_signature_technique(self.t,self.p,move_id='move/할퀴기',modification='bloodied_speed',request_id='replacement'),'two Tutor Points')
        self.p.spec['tutor_points']=2
        second=self.teach('bloodied_speed','move/할퀴기',request='replacement')
        self.assertEqual(self.p.spec['tutor_points'],1);self.assertEqual(len([r for r in self.p.spec[A.KEY] if r['status']=='active']),1)
        self.assertEqual(self.p.spec[A.KEY][0]['refund'],1)
        self.assertEqual(self.e.teach_signature_technique(self.t,self.p,move_id='move/할퀴기',modification='bloodied_speed',request_id='replacement'),second)
        self.e.gm.set_move(self.p,'move/할퀴기',add=False,reason='actual forgotten Signature Move')
        self.assertEqual(self.p.spec['tutor_points'],2);self.assertIsNone(A.active(self.rules,self.p.spec))
        self.e.gm.set_move(self.p,'move/할퀴기',add=False,reason='already forgotten Move cannot refund twice')
        self.assertEqual(self.p.spec['tutor_points'],2)
        self.restore();self.valid()

    def test_signature_actual_training_move_category_and_double_down_exceptions(self):
        self.family(A.SIGNATURE);self.e.gm.set_move(self.p,'move/할퀴기',reason='actual candidate')
        self.reject(lambda:self.e.teach_signature_technique(self.t,self.p,move_id='move/할퀴기',modification='alternative_energy',request_id='no-training'),'Training Feature')
        self.all_training()
        cases=[('scattershot','move/할퀴기'),('vicious_storm','move/달콤한향기'),('double_curse','move/꼬리흔들기'),
               ('double_down','move/연속자르기'),('double_down','move/아이스볼'),('double_down','move/나이트헤드')]
        for i,(mod,mid) in enumerate(cases):
            self.e.gm.set_move(self.p,mid,reason='actual ineligible candidate')
            self.reject(lambda:self.e.teach_signature_technique(self.t,self.p,move_id=mid,modification=mod,request_id='ineligible-'+str(i)),
                'category|Damaging|one-Target|DB|conditional|special-case')
            self.e.gm.set_move(self.p,mid,add=False,reason='actual rejected candidate no longer retained on Move list')

    def test_investment_uses_existing_permanent_teaching_retraining_boundary(self):
        self.teach('alternative_energy','move/할퀴기');before=self.p.spec['tutor_points']
        self.reject(lambda:self.retrain(A.SIGNATURE),'permanent|irreversible')
        self.assertEqual(self.p.spec['tutor_points'],before)
        source='temporary-technique-display'
        G.overlay(self.p,source,moves=['move/불꽃세례'])
        self.assertIsNotNone(A.active(self.rules,self.p.spec));self.assertEqual(self.p.spec['tutor_points'],before)
        G.revoke(self.p,source,engine=self.e)
        self.restore();self.valid();self.assertEqual(self.p.spec['tutor_points'],before)

    def test_scattershot_core_three_and_adopted_two_actual_targets_catalog_unchanged(self):
        base=deepcopy(self.rules.move('move/파도타기'))
        for contract,count in (('core_1.05',3),('dataninja_class_errata',2)):
            self.setup();self.teach('scattershot','move/파도타기',contract=contract)
            projected=A.prepare(self.e,self.p,self.rules.move('move/파도타기'))
            self.assertEqual(projected['range'],'4m, 대상'+str(count));self.assertEqual(A.prepare(self.e,self.p,projected),projected)
            self.assertEqual(self.rules.move('move/파도타기'),base)
            self.e.gm.set_position(self.foe,(6,2),reason='within actual four-metre range')
            row=self.attack('move/파도타기',targets=[self.foe,self.q]);self.assertEqual(len(row['targets']),2)
            self.assertNotIn(A.MARKER,A.prepare(self.e,self.q,base));self.restore();self.valid()

    def test_shock_and_awe_on_miss_foes_only_evasion_save_user_next_turn(self):
        self.teach('shock_and_awe','move/파도타기');ev=self.foe.evasion('특수');save=__import__('effects_ext').save_dc(self.e,self.foe,'마비',11)
        row=self.attack('move/파도타기',face=1,targets=[self.foe,self.q])
        self.assertFalse(row['results'][self.foe.entity_id]['hit']);self.assertEqual(self.foe.evasion('특수'),ev-1)
        self.assertEqual(__import__('effects_ext').save_dc(self.e,self.foe,'마비',11),save+2)
        self.assertFalse(A.timed(self.q,'shock_and_awe'));self.close();self.e.start_round(self.e.everyone);self.e.start_of_turn(self.p,initiative_count=60)
        self.assertTrue(A.timed(self.foe,'shock_and_awe'));self.close();self.assertFalse(A.timed(self.foe,'shock_and_awe'))

    def test_vicious_storm_actual_smite_miss_damage(self):
        self.teach('vicious_storm','move/파도타기');hp=self.foe.hp
        catalog=deepcopy(self.rules.move('move/파도타기'))
        prepared=A.prepare(self.e,self.p,catalog)
        self.assertIn('강타',__import__('effects_ext').keywords_for(self.p,prepared))
        self.assertEqual(prepared['keywords'].count('강타'),1)
        self.assertEqual(A.prepare(self.e,self.p,prepared),prepared)
        self.assertEqual(self.rules.move('move/파도타기'),catalog)
        row=self.attack('move/파도타기',face=1);self.assertFalse(row['results'][self.foe.entity_id]['hit'])
        self.assertGreater(row['results'][self.foe.entity_id]['dealt'],0)
        self.assertLess(self.foe.hp,hp);self.assertIn('강타',row['move']['range']);self.valid()

    def test_guarding_strike_hit_only_target_specific_dr_and_expiry(self):
        self.e.gm.set_move(self.q,'move/막치기',reason='actual other attacker learned Move')
        self.e.gm.set_move(self.foe,'move/막치기',reason='actual incoming attack')
        self.teach('guarding_strike','move/막치기');row=self.attack('move/막치기',face=1)
        self.assertFalse(A.timed(self.p,'guarding_strike'))
        row=self.attack('move/막치기');self.assertEqual(A.damage_reduction(self.p,self.foe),5);self.assertEqual(A.damage_reduction(self.p,self.q),0)
        import effects_ext as EXT
        original=EXT.defense_hook;observed=[]
        def defense(e,a,t,*args,**kwargs):
            result=original(e,a,t,*args,**kwargs)
            if t is self.p:observed.append((a.entity_id,result[1]))
            return result
        self.turn(self.foe,50)
        with patch.object(EXT,'defense_hook',defense),patch.object(Engine,'d20',return_value=18):
            self.e.use_move_on(self.foe,self.p,'move/막치기',[self.p],set_damage=True)
        self.assertIn((self.foe.entity_id,5),observed)
        self.turn(self.q,40)
        with patch.object(EXT,'defense_hook',defense),patch.object(Engine,'d20',return_value=18):
            self.e.use_move_on(self.q,self.p,'move/막치기',[self.p],set_damage=True)
        self.assertIn((self.q.entity_id,0),observed)
        self.restore();self.valid();self.close();self.e.start_round(self.e.everyone);self.e.start_of_turn(self.p,initiative_count=60);self.close()
        self.assertEqual(A.damage_reduction(self.p,self.foe),0)

    def test_unbalancing_hit_or_miss_ends_only_next_damaging_hit_or_full_round(self):
        self.e.gm.set_move(self.ps[2],'move/막치기',reason='actual next damaging attacker learned Move')
        self.e.gm.set_move(self.q,'move/울음소리',reason='actual non-damaging target hit')
        self.teach('unbalancing_blow','move/막치기');self.attack('move/막치기',face=1)
        self.assertEqual(self.foe.evasion('물리'),0);self.assertTrue(A.timed(self.foe,'unbalancing_blow'))
        self.turn(self.q,50)
        with patch.object(Engine,'d20',return_value=18):self.e.use_move_on(self.q,self.foe,'move/울음소리',[self.foe])
        self.assertTrue(A.timed(self.foe,'unbalancing_blow'))
        self.turn(self.ps[2],40)
        with patch.object(Engine,'d20',return_value=18):self.e.use_move_on(self.ps[2],self.foe,'move/막치기',[self.foe])
        self.assertFalse(A.timed(self.foe,'unbalancing_blow'));self.valid()

    def test_reliable_miss_preserves_frequency_costs_standard_actual_free_struggle_once(self):
        self.teach('reliable_attack','move/불꽃세례');row=self.attack('move/불꽃세례',face=1)
        self.assertEqual(self.p.budget['standard'],0);self.assertEqual(self.p.move_uses.get('move/불꽃세례',0),0)
        with patch.object(Engine,'d20',return_value=18):self.e.reliable_attack_struggle(self.p,self.foe,row['id'])
        self.assertEqual(self.p.budget['standard'],0);self.assertEqual(self.p._action_history[-1],'free')
        self.reject(lambda:self.e.reliable_attack_struggle(self.p,self.foe,row['id']),'opportunity')
        self.reject(lambda:self.e.reliable_attack_struggle(self.p,self.foe,'fabricated'),'completed')
        self.restore();self.valid()

    def test_reliable_hit_spends_frequency_and_new_action_expires_miss_offer(self):
        self.teach('reliable_attack','move/불꽃세례');self.attack('move/불꽃세례');self.assertEqual(self.p.move_uses['move/불꽃세례'],1)
        row=self.attack('move/불꽃세례',face=1);self.e.gm.set_move(self.p,'move/울음소리',reason='actual next action')
        self.begin(self.p)
        self.reject(lambda:self.e.reliable_attack_struggle(self.p,self.foe,row['id']),'immediate')

    def test_alternative_energy_both_directions_real_damage_evasion_and_individual_scope(self):
        for mid,original,changed in (('move/막치기','물리','특수'),('move/불꽃세례','특수','물리')):
            self.setup();self.teach('alternative_energy',mid);seen=[];original_roll=Engine.roll_damage
            def observe(e,a,t,move,*args,**kwargs):seen.append(move['class']);return original_roll(e,a,t,move,*args,**kwargs)
            with patch.object(Engine,'roll_damage',observe):row=self.attack(mid)
            self.assertEqual(seen[-1],changed);self.assertEqual(row['move']['class'],changed)
            self.assertEqual(self.rules.move(mid)['class'],original);self.assertEqual(A.prepare(self.e,self.q,self.rules.move(mid))['class'],original)
            self.restore();self.valid()

    def test_bloodied_speed_strict_half_native_advanced_turn_loan(self):
        self.teach('bloodied_speed','move/막치기')
        scheduled=self.e.prepare_initiative_schedule(self.e.everyone,source='gm/test-schedule',
            bindings=[{'slot':a.entity_id,'actor_id':a.entity_id,'role':a.entity_id} for a in self.e.everyone],
            order_groups=[[a.entity_id] for a in self.e.everyone])
        self.assertEqual(scheduled['status'],'prepared');self.e.start_round(self.e.everyone)
        self.e.gm.set_hp(self.p,self.p.max_hp//2,reason='exact half boundary')
        if self.p.max_hp%2==0:self.reject(lambda:self.e.bloodied_speed(self.p,self.foe,'move/막치기'),'strictly below half')
        self.e.gm.set_hp(self.p,(self.p.max_hp-1)//2,reason='strictly below half')
        with patch.object(Engine,'d20',return_value=18):receipt=self.e.bloodied_speed(self.p,self.foe,'move/막치기')
        self.assertEqual(receipt['source'],A.SIGNATURE);self.assertIs(self.e._active_turn_actor,self.p)
        self.assertEqual(self.p.budget['standard'],0);self.assertEqual(self.p.move_uses['move/막치기'],1);self.valid()

    def test_double_down_actual_two_rolls_combined_damage_and_once_effects(self):
        self.teach('double_down','move/불꽃세례');self.begin();before=self.foe.hp
        with patch.object(Engine,'d20',side_effect=[1,18]):self.e.use_move_on(self.p,self.foe,'move/불꽃세례',[self.foe],set_damage=True)
        row=self.completion();self.assertTrue(row['results'][self.foe.entity_id]['hit']);self.assertLess(self.foe.hp,before)
        strike=self.p.spec['multi_strike_history'][-1];self.assertEqual(len(strike['rolls']),2)
        self.assertEqual(self.p.move_uses['move/불꽃세례'],1);self.restore();self.valid()

    def test_double_down_untrusted_projected_keyword_has_no_authority(self):
        self.e.gm.set_move(self.p,'move/할퀴기',reason='ordinary actual Move')
        forged=dict(self.rules.move('move/할퀴기'),range='근접, 대상1, 이단타격')
        self.reject(lambda:__import__('multi_strike').preflight(self.e,self.p,forged),'printed keyword|source-owned')

    def test_motivation_actual_resolution_optional_negative_stats_cap_and_original_effect(self):
        self.teach('burst_of_motivation','move/울음소리')
        self.e.gm.set_stage(self.p,'atk',value=-1,reason='actual debuff');self.e.gm.set_stage(self.p,'spe',value=-4,reason='actual deeper debuff')
        row=self.attack('move/울음소리');self.assertEqual(self.foe.stages['atk'],-1)
        self.reject(lambda:self.e.burst_of_motivation(self.p,row['id'],{'atk':2}),'above zero')
        self.e.burst_of_motivation(self.p,row['id'],{'atk':1,'spe':2})
        self.assertEqual((self.p.stages['atk'],self.p.stages['spe']),(0,-2));self.assertEqual(self.foe.stages['atk'],-1)
        self.reject(lambda:self.e.burst_of_motivation(self.p,row['id'],{'spe':2}),'opportunity');self.restore();self.valid()

    def test_supreme_core_failed_save_preselected_technique_only_normal_cost(self):
        self.rules=Rules(ROOT,ruleset='core-confusion-1.05');self.setup();self.teach('supreme_concentration','move/울음소리')
        self.e.start_round(self.e.everyone);self.e.apply_status(self.p,'혼란')
        self.e.choose_supreme_concentration(self.p,move_id='move/울음소리',request_id='chosen-before-turn')
        with patch.object(Engine,'d20',return_value=1):self.e.start_of_turn(self.p,initiative_count=60)
        observation=self.p.custom_conditions['core_confusion_turns'][-1]
        self.assertEqual(observation['outcome'],'selected_supreme_concentration');self.assertIn('혼란',self.p.conditions)
        self.assertEqual(self.p.budget['standard'],1);hp=self.p.hp
        completions=len(getattr(self.e,'_move_completions',{}))
        self.e.gm.set_move(self.p,'move/막치기',reason='actual unrelated blocked Move')
        self.e.use_move(self.p,self.foe,'move/막치기')
        self.assertEqual(len(getattr(self.e,'_move_completions',{})),completions);self.assertEqual(self.p.budget['standard'],1)
        with patch.object(Engine,'d20',return_value=18):self.e.use_move_on(self.p,self.foe,'move/울음소리',[self.foe])
        self.assertEqual(self.p.budget['standard'],0);self.assertEqual(self.p.hp,hp);self.assertEqual(self.foe.stages['atk'],-1)
        self.assertFalse(__import__('turn').spend(self.e,self.p,'shift','Core Confusion does not unlock another action'))
        self.restore();self.valid()

    def test_supreme_exact_move_works_with_rage_paralysis_and_flinch_without_curing(self):
        for condition in ('난동','마비','풀죽음'):
            self.setup();self.teach('supreme_concentration','move/울음소리');self.begin(self.foe)
            self.e.apply_status(self.p,condition);self.close()
            with patch.object(Engine,'d20',return_value=1):self.e.start_of_turn(self.p,initiative_count=50)
            with patch.object(Engine,'d20',return_value=18):self.e.use_move_on(self.p,self.foe,'move/울음소리',[self.foe])
            self.assertEqual(self.p.budget['standard'],0);self.assertIn(condition,self.p.conditions)
            self.assertEqual(self.foe.stages['atk'],-1);self.valid()

    def test_supreme_core_decline_keeps_self_hit_and_unrelated_sleep_lock(self):
        self.rules=Rules(ROOT,ruleset='core-confusion-1.05');self.setup();self.teach('supreme_concentration','move/울음소리')
        self.e.start_round(self.e.everyone);self.e.apply_status(self.p,'혼란');hp=self.p.hp
        self.e.choose_supreme_concentration(self.p,move_id=None,request_id='decline-before-turn')
        with patch.object(Engine,'d20',return_value=1):self.e.start_of_turn(self.p,initiative_count=60)
        self.assertLess(self.p.hp,hp);self.assertNotEqual(self.p.custom_conditions['core_confusion_turns'][-1]['outcome'],'selected_supreme_concentration')
        self.close();self.e.cure_status(self.p,'혼란');self.e.apply_status(self.p,'잠듦')
        with patch.object(Engine,'d20',return_value=1):self.begin()
        before=len(getattr(self.e,'_move_completions',{}))
        self.e.use_move(self.p,self.foe,'move/울음소리');self.assertEqual(len(getattr(self.e,'_move_completions',{})),before)

    def test_supreme_feb_confusion_actual_after_resolution_hp_loss_retained(self):
        self.rules=Rules(ROOT,ruleset='core-confusion-feb2016');self.setup();self.teach('supreme_concentration','move/울음소리')
        self.e.apply_status(self.p,'혼란');self.begin();hp=self.p.hp
        with patch.object(__import__('roll_pools'),'die',return_value=1),patch.object(Engine,'d20',return_value=18):
            self.e.use_move_on(self.p,self.foe,'move/울음소리',[self.foe])
        self.assertEqual(self.foe.stages['atk'],-1);self.assertLess(self.p.hp,hp);self.assertIn('혼란',self.p.conditions);self.valid()

    def test_double_curse_same_activation_two_foes_core_and_adopted_exclusions(self):
        self.teach('double_curse','move/이상한빛');self.q.side='enemy'
        row=self.attack('move/이상한빛',targets=[self.foe,self.q]);self.assertEqual(len(row['targets']),2)
        self.assertEqual(self.p.move_uses['move/이상한빛'],1)
        self.assertTrue(all('혼란' in p.conditions for p in (self.foe,self.q)));self.restore();self.valid()
        self.setup();self.teach('double_curse','move/흉내내기',contract='core_1.05')
        self.reject(lambda:self.e.teach_signature_technique(self.t,self.p,move_id='move/흉내내기',modification='double_curse',
            source_contract='dataninja_class_errata',request_id='adopted-forbidden'),'non-Status')

    def test_csv60_and_four_class_data_rows_real_single_investment_consumers(self):
        cases=[('scattershot','move/파도타기',3),('guarding_strike','move/막치기',4),
               ('alternative_energy','move/불꽃세례',5),('burst_of_motivation','move/울음소리',6)]
        for mod,mid,record in cases:
            self.setup();before=self.p.spec['tutor_points']
            row=self.teach(mod,mid,clause='C2CSV/input/db/feats.csv:R60:main')
            self.assertEqual(self.p.spec['tutor_points'],before-2)
            self.assertEqual(row['csv_reference'],'C2CSV/input/db/class-data.csv:R'+str(record)+':technique')
            if mod=='burst_of_motivation':self.e.gm.set_stage(self.p,'atk',value=-1,reason='actual CSV technique debuff')
            targets=[self.foe,self.q,self.ps[2]] if mod=='scattershot' else None
            native=self.attack(mid,targets=targets);self.assertIn(A.MARKER,native['move'])
            if mod=='scattershot':self.assertEqual((native['move']['range'],len(native['targets'])),('4m, 대상3',3))
            elif mod=='guarding_strike':self.assertEqual(A.damage_reduction(self.p,self.foe),5)
            elif mod=='alternative_energy':self.assertEqual(native['move']['class'],'물리')
            else:
                self.e.burst_of_motivation(self.p,native['id'],{'atk':1});self.assertEqual(self.p.stages['atk'],0)
            self.restore();self.valid()

    def top_percentage_world(self):
        import test_category2_class_actor_state_actions as CASES
        case = CASES.ClassActorStateActionTests('runTest')
        case.rules = self.rules
        self.e, self.t, self.p, self.foe = case.fixture(level=100)
        self.ps = [self.p]
        self.q = self.p
        self.t.spec['exp_bank'] = 10  # Actual banked XP available for retraining.
        self.e.gm.set_skill(self.t, '명령', 5, reason='actual Expert Command before acquisition')

    def test_top_percentage_explicit_book_and_old_request_replay_preserve_actual_source(self):
        self.top_percentage_world()
        self.acquire()
        source = ACQ.STATIC_FEATURES[A.TOP]['clause_id']
        csv_source = 'C2CSV/input/db/feats.csv:R59:main'
        first = ACQ.acquire_static(self.e, self.t, A.TOP,
            acquisition_request_id='book/top', source_id=source)
        self.assertEqual(first['source']['clause_id'], source)
        self.reject(lambda: ACQ.acquire_static(self.e, self.t, A.TOP,
            acquisition_request_id='book/top', source_id=csv_source), 'changed intent or source')
        self.e.gm.snapshot('book-top')
        self.e.gm.set_skill(self.t, '명령', 1, reason='later skill loss preserves historical qualification')
        before = self.e.export_state()
        self.assertEqual(self.acquire(A.TOP, request='book/top'), first)
        self.assertEqual(self.e.export_state(), before)
        self.e.gm.restore('book-top')
        self.restore()
        self.assertEqual(self.acquire(A.TOP, request='book/top'), first)
        self.e.gm.set_level(self.p, 100, reason='actual maximum-level Pokemon')
        self.reject(lambda: self.e.offer_top_percentage_at_max_level(self.t, self.p), 'Core body|CSV59')
        self.retrain(A.TOP)
        self.restore()
        before = self.e.export_state()
        self.assertEqual(self.acquire(A.TOP, request='book/top'), dict(first, status='withdrawn'))
        self.assertEqual(self.e.export_state(), before)
        self.reject(lambda: ACQ.acquire_static(self.e, self.t, A.TOP,
            acquisition_request_id='book/top', source_id=csv_source), 'changed intent or source')
        self.valid()

    def test_top_percentage_declared_seven_plus_command_preserves_history_and_rejects_undeclared_ranks(self):
        self.top_percentage_world()
        self.reject(lambda: self.e.gm.set_skill(self.t, '명령', 7, reason='undeclared rank'),
                    'unresolved ordinary numeric skill rank')
        for number, name in ((7, '초월'), (9, '신화')):
            self.rules.rulings.set_mech('gameplay/skill-rank-dice', 'by_rank_name.' + name,
                {'rank': number, 'dice': str(number) + 'd6', 'eng': 'Epic' + str(number)},
                reason='explicit campaign rank', rules=self.rules)
        self.e.gm.set_skill(self.t, '명령', 7, reason='actual declared rank seven')
        self.acquire()
        self.e.gm.set_skill(self.t, '명령', 9, reason='actual declared rank nine')
        self.acquire(A.TOP)
        self.assertEqual(A.acquired(self.t, A.CLASS)['snapshot']['skills']['명령'], 7)
        self.assertEqual(A.acquired(self.t, A.TOP)['snapshot']['skills']['명령'], 9)
        self.reject(lambda: self.e.gm.set_skill(self.t, '명령', 8, reason='undeclared gap'),
                    'unresolved ordinary numeric skill rank')
        self.reject(lambda: self.e.gm.set_skill(self.t, '명령', 'Epci7', reason='misspelled rank'),
                    'unresolved skill rank')
        self.e.gm.set_skill(self.t, '명령', 1, reason='later skill loss preserves historical qualification')
        self.restore()
        self.assertEqual(A.acquired(self.t, A.TOP)['snapshot']['skills']['명령'], 9)
        self.valid()

    def test_top_percentage_body_exact_fifth_levels_lifetime_four_and_csv_exception_separate(self):
        import test_category2_class_actor_state_actions as EXISTING
        import downtime as DT
        fixture=EXISTING.ClassActorStateActionTests();fixture.rules=self.rules
        self.e,self.t,self.p,self.foe=fixture.fixture(feats=(),level=4,species='메타몽',moves=('변신',))
        self.ps=[self.p];self.q=self.p;self.t.spec['skills']['명령']=6
        self.t.spec['exp_bank']=10  # Actual banked XP, separate from the level.
        self.family(A.TOP)
        self.reject(lambda:self.e.offer_top_percentage_at_max_level(self.t,self.p),'maximum-level|CSV|body')
        before=self.p.spec['tutor_points']
        for level in (5,10,15,20):
            while self.p.level<level:DT.gain_exp_combatant(self.e,self.p,'to next level')
            pending=self.e.pending_class_actor_state_actions(self.t)
            for event in pending:self.e.resolve_class_actor_state_action(self.t,event['id'],use=event['payload']['level']==level)
        self.assertEqual(self.p.spec['tutor_points'],before+8)
        for stat in self.p.stats:self.assertEqual(self.p.stats[stat],self.p.spec['stats'][stat]+1)
        self.assertEqual(__import__('class_actor_state_actions')._top_percentage_count(self.e,self.p),4)
        self.assertEqual(self.p.spec[G.KEY]['sources']['top-percentage:'+self.p.entity_id]['top_percentage_uses'],4)
        self.e.gm.set_level(self.p,100,reason='actual observed maximum-level current state')
        self.reject(lambda:self.e.offer_top_percentage_at_max_level(self.t,self.p),'Core body|CSV59')
        self.retrain(A.TOP);self.restore();self.valid()

    def test_exact_sources_all_modification_groups_and_original_credit_boundary(self):
        contract=A.policy(self.rules)
        for key in ('body','core','feats_csv','class_data_csv','dataninja_class_errata'):
            row=contract[key];self.assertEqual(hashlib.sha256((ROOT/row['file']).read_bytes()).hexdigest(),row['sha256'])
        self.assertEqual((len(A.FEATURES),len(A.MODIFICATIONS)),(7,12))
        self.assertEqual((len(contract['body_credit_ids']),len(contract['csv_credit_ids'])),(7,6))
        self.assertFalse(contract['dataninja_class_errata']['official_playtest'])


if __name__=='__main__':unittest.main()
