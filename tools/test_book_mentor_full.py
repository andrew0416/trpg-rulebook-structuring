"""Mentor actual acquisition, four lessons, source differences and native consumers."""
from pathlib import Path
from copy import deepcopy
import json,sys,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from builder import build_trainer,build_pokemon
import mentor as M,pokemon_teaching as T,pokemon_skill_edges as SK,pokemon_capability_edges as CAP
import state_codec as CODEC,world_entities as W,state_grants as G,frequency as F
import growth_milestones as GM,skill_modifiers as S,move_state as MOVES,grant_payments as PAY
from native_scenario_fixture import assert_rejections_unchanged
STATS=dict.fromkeys(('hp','atk','def','spa','spd','spe'),10)


class MentorFullTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.r=Rules(ROOT,ruleset='core')

    def setUp(self):
        self.e=Engine(self.r,seed=1024627)
        self.a=self.add(build_trainer(self.r,'actual Mentor',20,STATS,abilities=[],extra={
            'classes':[],'feats':[],'skills':dict.fromkeys(M.SKILLS,6),
            'movement_basis':'current','power_basis':'current'}))

    def add(self,spec):
        actor=Combatant(self.r,spec)
        self.e.gm.add_combatant(actor,pos=(0,0),side='party',reason='actual source participant')
        return actor

    def acquire(self,feature=M.CLASS,skills=('매력','포켓몬학'),variant='core',policy='core',request=None):
        return self.e.acquire_mentor_feature(self.a,feature,request_id=request or 'acquire/'+feature,
            skills=list(skills) if feature==M.CLASS else None,variant=variant,tutoring_policy=policy)

    def pupil(self,species='이상해씨',level=5,tp=8,owned=True,**extra):
        if owned:extra.setdefault('trainer_id',self.a.entity_id)
        return self.add(build_pokemon(self.r,species,level,moves=[],abilities=extra.pop('abilities',[]),
            nature=extra.pop('nature','노력'),extra={'tutor_points':tp,**extra}))

    def lessons(self,skills=('매력','포켓몬학'),variant='core'):
        self.acquire(skills=skills);self.acquire(M.LESSONS,variant=variant)

    def lesson(self,p,name,request=None,**choices):
        return self.e.mentor_lesson(self.a,p,name,request_id=request or name,seconds=60,
            reason='actual observed Extended lesson',**choices)

    def reject(self,*operations,pattern='.'):
        return assert_rejections_unchanged(self.e,list(operations),reason_pattern=pattern)

    def teach(self,p,move,feature=M.CLASS):
        return T.teach_feature(self.e,self.a,target=p,move_id=move,feature=feature,seconds=60,
            reason='actual observed Extended teaching')

    def edges(self,p):
        choices=[key for key in p.spec['skills'] if SK.skill_pool(self.r,p.spec,S.skill_id(self.r.skill_policy,key,required=True))[0]<6]
        return [{'edge':SK.SOURCE,'choice':choices[0]},
                {'edge':CAP.MOBILITY,'choice':'land'},{'edge':CAP.TRAINING,'choice':'power'}]

    def new_day(self):
        for actor in self.e.everyone:F.new_day(actor)

    def restore(self,fresh_rules=False):
        data=json.loads(json.dumps(CODEC.dump_engine(self.e),ensure_ascii=False))
        if fresh_rules:
            definitions=list(getattr(self.r,'_authored_policy_sources',{}).values())
            self.r=Rules(ROOT,ruleset='core')
            if definitions:self.r.register_source_policy_definitions(definitions)
        self.e=CODEC.load_engine(self.r,data);self.a=W.actor_index(self.e)[self.a.entity_id]
        return W.actor_index(self.e)

    def egg_policy(self,p,scope='individual_egg_list'):
        document={'schema':1,'id':'actual/csv109/'+p.entity_id,'variants':[{
            'rule_id':M.CSV_EGG_POLICY,
            'source':{'file':'input/db/feats.csv','sha256':M.contract(self.r)['source_hashes']['input/db/feats.csv']},
            'values':{'target_id':p.entity_id,'scope':{'$input':'scope'},'allowed_egg_moves':['move/치유파동','move/몸통박치기']},
            'inputs':{'scope':{'type':'string','authority':'gm','decision_kind':'source_conflict',
                'choices':['individual_egg_list','individual_inheritance_list'],
                'question':'Resolve the unknown CSV109 individual list interpretation explicitly; no global species edit.'}}}]}
        pending=self.e.mentor_egg_list_policy(self.a,p,document)
        decision={'scope':{'value':scope,'reason':'explicit local interpretation, not a source-lineage conclusion','scope':pending['decision_scope']}}
        return document,decision

    def test_class_choice_does_not_auto_grant_other_features_and_replays_fixed_choice(self):
        row=self.acquire();before=CODEC.dump_engine(self.e)
        self.assertEqual(self.acquire(),row)
        self.assertEqual(CODEC.dump_engine(self.e),before)
        self.assertEqual(self.a.spec['mentor_skills'],['매력','포켓몬학'])
        for feature in set(M.FEATURES)-{M.CLASS}:self.assertIsNone(M.acquired(self.a,feature))
        self.reject(lambda:self.acquire(skills=('직감','협박')),
            lambda:T.select_mentor_skills(self.e,self.a,['직감','협박'],reason='changed fixed choice'))

    def test_class_requires_two_distinct_ordinary_novice_not_effect_rank(self):
        self.e.gm.set_skill(self.a,'직감',2,reason='actual untrained choice')
        self.reject(lambda:self.acquire(skills=('매력','매력')),
            lambda:self.acquire(skills=('매력','직감')),lambda:self.acquire(skills=('육상','포켓몬학')))
        self.e.gm.set_skill(self.a,'직감',3,reason='actual novice');self.acquire(skills=('매력','직감'))

    def test_followups_require_actual_parents_and_preserve_sealed_skill_choice(self):
        self.reject(lambda:self.acquire(M.LESSONS),lambda:self.acquire(M.MOVE_TUTOR))
        self.acquire(skills=('직감','협박'));self.acquire(M.LESSONS)
        self.assertEqual(M.acquired(self.a,M.LESSONS)['snapshot']['skills'],['직감','협박'])
        self.reject(lambda:self.acquire(M.EGG_TUTOR),lambda:self.acquire(M.LIFELONG))
        self.acquire(M.MOVE_TUTOR);self.acquire(M.EGG_TUTOR);self.acquire(M.LIFELONG)

    def test_followup_printed_expert_master_thresholds_do_not_add_current_two_novice(self):
        self.acquire()
        self.e.gm.set_skill(self.a,'매력',2,reason='actual later rank loss with retained acquired parent')
        self.e.gm.set_skill(self.a,'포켓몬학',4,reason='actual below selected Expert')
        self.acquire(M.LESSONS);self.acquire(M.EXPAND);self.acquire(M.GUIDANCE)
        self.reject(lambda:self.acquire(M.MOVE_TUTOR))
        self.e.gm.set_skill(self.a,'포켓몬학',5,reason='actual selected Expert');self.acquire(M.MOVE_TUTOR)
        self.acquire(M.EGG_TUTOR);self.reject(lambda:self.acquire(M.LIFELONG))
        self.e.gm.set_skill(self.a,'포켓몬학',6,reason='actual selected Master');self.acquire(M.LIFELONG)

    def test_source_selection_and_immutable_projection_survive_data_restore(self):
        self.acquire(policy='official_sep2015');self.acquire(M.LESSONS,variant='local_translation')
        actors=self.restore();self.assertEqual(M.teaching_policy(self.a),'official_sep2015')
        self.assertEqual(M.teaching_variant(self.a,M.LESSONS),'local_translation')
        original=deepcopy(self.a.spec['mentor_skills']);self.a.spec['mentor_skills'].reverse()
        with self.assertRaises(ValueError):CODEC.dump_engine(self.e)
        self.a.spec['mentor_skills']=original
        self.assertTrue(self.e.validate_state()['valid'])

    def test_core_mentor_current_level_plus_both_ranks_paid_and_natural_for_any_pokemon(self):
        self.acquire();p=self.pupil('브케인',level=28,owned=False,tp=1)
        result=self.teach(p,'화염방사')
        self.assertEqual((result['point_cost'],result['classification'],p.spec['tutor_points']),(1,'natural',0))
        row=p.spec['move_learning']['move/화염방사'];self.assertEqual(row['mentor_skill_ranks'],[6,6])
        self.assertEqual(MOVES.describe(self.r,p.spec)['taught_count'],0)
        self.assertEqual(self.e.elapsed_seconds,60)

    def test_core_mentor_current_level_move_still_costs_one_and_requires_one(self):
        self.acquire();zero=self.pupil(tp=0);self.reject(lambda:self.teach(zero,'몸통박치기'))
        p=self.pupil(tp=1);out=self.teach(p,'몸통박치기')
        self.assertEqual((out['point_cost'],p.spec['tutor_points']),(1,0))

    def test_core_mentor_daily_three_and_outside_allowance_are_atomic(self):
        self.acquire();bad=self.pupil('브케인',level=27)
        self.reject(lambda:self.teach(bad,'화염방사'))
        for unused in range(3):self.teach(self.pupil(),'몸통박치기')
        p=self.pupil();self.reject(lambda:self.teach(p,'몸통박치기'),pattern='daily frequency')
        self.new_day();self.teach(p,'몸통박치기')

    def test_actual_effect_rank_changes_allowance_without_changing_ordinary_acquisition(self):
        self.a.spec.setdefault('edges',[]).append('edge/거장');self.a.spec['edge_choices']={'edge/거장':['매력']}
        row=self.acquire();self.assertEqual(row['snapshot']['ranks'],[6,6])
        p=self.pupil('브케인',level=26);self.teach(p,'화염방사')
        self.assertEqual(p.spec['move_learning']['move/화염방사']['mentor_skill_ranks'],[8,6])

    def test_expand_requires_ownership_extended_time_and_once_lifetime(self):
        self.acquire();self.acquire(M.EXPAND);p=self.pupil(tp=0);other=self.pupil(owned=False)
        self.reject(lambda:self.e.expand_horizons(self.a,other,request_id='wrong',seconds=60,reason='actual instruction'))
        result=self.e.expand_horizons(self.a,p,request_id='expand',seconds=60,reason='actual instruction')
        self.assertEqual((result['points'],p.spec['tutor_points'],self.e.elapsed_seconds),(3,3,60))
        before=CODEC.dump_engine(self.e)
        self.assertEqual(self.e.expand_horizons(self.a,p,request_id='expand',seconds=60,reason='actual instruction'),result)
        self.assertEqual(CODEC.dump_engine(self.e),before)
        self.new_day();self.reject(lambda:self.e.expand_horizons(self.a,p,request_id='again',seconds=60,reason='actual instruction'))

    def test_expand_history_survives_json_restore_and_owner_transfer(self):
        import pokemon_party as PARTY
        self.acquire();self.acquire(M.EXPAND);p=self.pupil()
        self.e.expand_horizons(self.a,p,request_id='expand',seconds=60,reason='actual instruction')
        new=self.add(build_trainer(self.r,'recipient',20,STATS,abilities=[],extra={'classes':[],'feats':[],'skills':dict.fromkeys(M.SKILLS,6)}))
        PARTY.configure(self.e,self.a,mode='unlimited',reason='actual roster',roster=[p])
        PARTY.configure(self.e,new,mode='unlimited',reason='actual roster',roster=[])
        PARTY.transfer(self.e,self.a,target=p,new_owner=new,reason='actual gift',request_id='gift')
        actors=self.restore();p=actors[p.entity_id];new=actors[new.entity_id]
        self.e.acquire_mentor_feature(new,request_id='recipient/class',skills=['매력','포켓몬학'])
        self.e.acquire_mentor_feature(new,M.EXPAND,request_id='recipient/expand')
        self.reject(lambda:self.e.expand_horizons(new,p,request_id='again',seconds=60,reason='same lifetime'))

    def test_changing_viewpoints_native_nature_stats_and_same_axis(self):
        self.lessons(skills=('직감','협박'))
        catalog=self.r.mech('pokemon/natures')['by_name'];names=[n for n,v in catalog.items() if v['up']!=v['down']]
        old=names[0];pair=next(n for n in names if n!=old and (catalog[n]['up']==catalog[old]['up'] or catalog[n]['down']==catalog[old]['down']))
        invalid=next(n for n in names if catalog[n]['up']!=catalog[old]['up'] and catalog[n]['down']!=catalog[old]['down'])
        p=self.pupil(nature=old);self.reject(lambda:self.lesson(p,'changing',nature=old),lambda:self.lesson(p,'changing',nature=invalid))
        result=self.lesson(p,'changing',nature=pair)
        self.assertEqual((p.spec['nature'],result['point_cost'],p.spec['tutor_points']),(pair,1,7))
        self.assertEqual(result['nature_change']['source'],M.LESSONS)
        self.assertTrue(self.e.validate_state()['valid'])

    def test_changing_requires_selected_intuition_and_can_target_other_owner(self):
        self.lessons();p=self.pupil(owned=False)
        self.reject(lambda:self.lesson(p,'changing',nature='노력'),pattern='selected Mentor skill')

    def test_class_data_changing_has_no_unprinted_tp_cost_and_any_other_nature(self):
        self.acquire(skills=('직감','협박'));p=self.pupil(tp=0)
        nature=next(n for n in self.r.mech('pokemon/natures')['by_name'] if n!='노력')
        result=self.lesson(p,'changing',variant='class_data',nature=nature)
        self.assertEqual((result['point_cost'],p.spec['tutor_points']),(0,0))
        self.assertEqual(result['admission']['source'],M.TECHNIQUES['changing'])

    def test_empowered_uses_three_real_native_edges_one_total_point_below_level20(self):
        self.lessons();p=self.pupil(level=5,tp=1);edges=self.edges(p)
        before=CAP.amounts(self.r,p.spec);out=self.lesson(p,'empowered',edges=edges)
        self.assertEqual((p.spec['tutor_points'],out['point_cost'],self.e.elapsed_seconds),(0,1,60))
        self.assertEqual(len([r for r in p.spec['learned_poke_edges'] if r['status']=='active']),3)
        self.assertEqual(CAP.amounts(self.r,p.spec)['land'],before.get('land',0)+2)
        group=p.spec['state_grants']['payments']['mentor-empowered/empowered']
        self.assertEqual((group['paid'],group['allocation']),(1,None))
        self.assertTrue(self.e.validate_state()['valid'])

    def test_empowered_keeps_duplicate_and_existing_capability_restrictions_atomic(self):
        self.lessons();p=self.pupil();edge=self.edges(p)[0]
        self.reject(lambda:self.lesson(p,'empowered',edges=[edge,edge,edge]),
            lambda:self.lesson(p,'empowered',edges=[edge,{'edge':CAP.MOBILITY,'choice':'sky'},{'edge':CAP.TRAINING,'choice':'power'}]))
        self.assertNotIn('mentor_empowered_history',p.spec)
        self.lesson(p,'empowered',edges=self.edges(p));self.new_day()
        self.reject(lambda:self.lesson(p,'empowered',request='again',edges=self.edges(p)),pattern='once')

    def test_empowered_late_extended_failure_rolls_back_real_edges_payment_and_rng(self):
        import activity_jobs as JOBS
        self.lessons();p=self.pupil()
        with patch.object(JOBS,'run_fixed',side_effect=ValueError('late actual Extended failure')):
            self.reject(lambda:self.lesson(p,'empowered',edges=self.edges(p)),pattern='late actual Extended failure')
        self.lesson(p,'empowered',edges=self.edges(p))

    def test_corrective_whole_empowered_effect_refunds_one_and_removes_three_contributions(self):
        self.lessons(skills=('매력','협박'));p=self.pupil();self.lesson(p,'empowered',edges=self.edges(p))
        out=self.lesson(p,'corrective',effect_id='mentor-empowered/empowered')
        self.assertEqual((out['refunded_points'],p.spec['tutor_points']),(1,8))
        self.assertFalse(any(r['status']=='active' for r in p.spec['learned_poke_edges']))
        self.reject(lambda:self.lesson(p,'corrective',request='twice',effect_id='mentor-empowered/empowered'))

    def test_corrective_partial_empowered_requires_original_explicit_allocation(self):
        self.lessons(skills=('매력','협박'));p=self.pupil();self.lesson(p,'empowered',edges=self.edges(p))
        children=p.spec['mentor_empowered_history'][0]['children'];group='mentor-empowered/empowered'
        self.reject(lambda:self.lesson(p,'corrective',effect_id=children[0]),pattern='explicit allocation')
        out=self.lesson(p,'corrective',effect_id=children[0],allocations={group:dict(zip(children,[1,0,0]))})
        self.assertEqual((out['refunded_points'],p.spec['tutor_points']),(1,8))
        self.assertEqual(sum(r['status']=='active' for r in p.spec['learned_poke_edges']),2)

    def test_corrective_actual_ordinary_edge_and_group_feature_refund_not_fake_prerequisite_loss(self):
        self.lessons(skills=('협박','포켓몬학'));p=self.pupil(level=20)
        T.teach_edge(self.e,self.a,target=p,edge=SK.SOURCE,skill='육상',safe=True)
        row=next(r for r in p.spec['learned_poke_edges'] if r['status']=='active')
        out=self.lesson(p,'corrective',effect_id=M.native_effect_id(row));self.assertEqual(out['refunded_points'],1)
        refunded=next(r for r in p.spec['learned_poke_edges'] if r.get('status')=='refunded')
        self.assertNotIn('lost_prerequisite',refunded['refund'])
        PAY.acquire(self.e,p,'actual-feature',[{'source_id':'actual-feature/child','field':'capabilities','value':'Jump=1'}],2,rule_id=M.LESSONS,reason='actual paid Feature')
        out=self.lesson(p,'corrective',request='feature',effect_id='actual-feature/child')
        self.assertEqual(out['refunded_points'],2)

    def test_corrective_actual_stat_edge_removes_exemption_and_uses_growth_migration(self):
        import pokemon_stat_edges as ST
        self.lessons(skills=('협박','포켓몬학'));p=self.pupil('근육몬',level=35)
        T.teach_edge(self.e,self.a,target=p,edge=ST.ATTACK_CONFLICT,stat='atk',safe=True)
        row=next(r for r in p.spec['learned_poke_edges'] if r['source']==ST.ATTACK_CONFLICT)
        self.assertEqual(ST.exemptions(self.r,p.spec),{'atk'})
        before=deepcopy(p.spec['stats']);out=self.lesson(p,'corrective',effect_id=M.native_effect_id(row))
        self.assertEqual((out['refunded_points'],p.spec['tutor_points']),(1,8))
        self.assertEqual(ST.exemptions(self.r,p.spec),set());self.assertEqual(p.spec['stats'],before)
        self.assertEqual(p.spec['mentor_corrective_history'][-1]['removed_native_record']['stat'],'atk')

    def test_versatile_permanent_basic_exchange_and_own_csv_free_cost(self):
        self.lessons();p=self.pupil('아보',abilities=['탈피'],tp=1)
        out=self.lesson(p,'versatile',old_ability='탈피',new_ability='위협')
        self.assertEqual((out['point_cost'],p.spec['tutor_points']),(1,0))
        native_ids=lambda:[__import__('ability_transitions').ability_id(self.r,x) for x in p.spec['abilities']]
        self.assertIn('ability/위협',native_ids());self.assertNotIn('ability/탈피',native_ids())
        actors=self.restore();p=actors[p.entity_id];self.assertIn('ability/위협',native_ids())
        self.r=self.e.r
        # Actual Core species: Basic InnerFocus/Infiltrator; Advanced Insomnia/Vanguard.
        advanced=[]
        for replacement in ('틈새포착','선봉'):
            target=self.pupil('주뱃',level=30,abilities=['정신력','불면'],tp=1)
            result=self.lesson(target,'versatile',request='advanced/'+replacement,old_ability='불면',new_ability=replacement)
            ids=[__import__('ability_transitions').ability_id(self.r,x) for x in target.spec['abilities']]
            self.assertEqual((result['point_cost'],target.spec['tutor_points']),(1,0))
            self.assertIn('ability/정신력',ids);self.assertIn('ability/'+replacement,ids);self.assertNotIn('ability/불면',ids)
            advanced.append((target.entity_id,replacement))
        actors=self.restore()
        for identity,replacement in advanced:
            target=actors[identity];ids=[__import__('ability_transitions').ability_id(self.r,x) for x in target.spec['abilities']]
            self.assertIn('ability/'+replacement,ids);self.assertNotIn('ability/불면',ids)
            self.assertEqual(target.spec['tutor_points'],0)
        self.assertEqual(self.e.elapsed_seconds,180)

    def test_versatile_core_rejects_basic_to_advanced_or_hidden_and_duplicate(self):
        self.lessons();p=self.pupil('아보',level=50,abilities=['탈피','위협'])
        pools=self.r.learnsets['아보']['abilities'];advanced=pools['숨겨진 특성'][0];hidden=pools['대단한 특성'][0]
        self.reject(lambda:self.lesson(p,'versatile',old_ability='탈피',new_ability='위협'),
            lambda:self.lesson(p,'versatile',old_ability='탈피',new_ability=advanced),
            lambda:self.lesson(p,'versatile',old_ability='탈피',new_ability=hidden))

    def test_csv105_lessons_own_versatile_is_free_but_other_pokemon_pays_one(self):
        self.lessons(variant='local_csv');own=self.pupil('아보',abilities=['탈피'],tp=0)
        self.assertEqual(self.lesson(own,'versatile',old_ability='탈피',new_ability='위협')['point_cost'],0)
        other=self.pupil('아보',owned=False,abilities=['탈피'],tp=1)
        self.assertEqual(self.lesson(other,'versatile',request='other',old_ability='탈피',new_ability='위협')['point_cost'],1)

    def test_csv106_keeps_plus_three_once_and_conditionally_all_four_lesson_permissions(self):
        self.acquire();self.acquire(M.EXPAND,variant='local_csv')
        p=self.pupil();out=self.e.expand_horizons(self.a,p,request_id='csv106',seconds=60,reason='actual printed CSV106 +3')
        self.assertEqual(out['points'],3)
        self.reject(lambda:self.lesson(p,'changing',nature='노력'))
        self.acquire(M.LESSONS,variant='local_csv')
        self.e.gm.set_skill(self.a,'직감',2,reason='actual below Novice fourth skill')
        self.reject(lambda:self.lesson(p,'changing',nature='노력'),pattern='selected Mentor skill')
        self.e.gm.set_skill(self.a,'직감',3,reason='actual fourth ordinary Novice')
        catalog=self.r.mech('pokemon/natures')['by_name'];old=catalog[p.spec['nature']]
        nature=next(n for n,v in catalog.items() if n!=p.spec['nature'] and (v['up']==old['up'] or v['down']==old['down']))
        out=self.lesson(p,'changing',nature=nature);self.assertTrue(out['admission']['all_lesson_permission'])
        out=self.lesson(p,'empowered',request='csv106/empowered',edges=self.edges(p))
        self.assertTrue(out['admission']['all_lesson_permission'])
        out=self.lesson(p,'corrective',request='csv106/corrective',effect_id='mentor-empowered/csv106/empowered')
        self.assertTrue(out['admission']['all_lesson_permission'])
        other=self.pupil('아보',abilities=['탈피'],tp=0)
        self.reject(lambda:self.lesson(other,'versatile',old_ability='탈피',new_ability='위협'),pattern='daily')
        self.new_day();out=self.lesson(other,'versatile',old_ability='탈피',new_ability='위협')
        self.assertTrue(out['admission']['all_lesson_permission'])
        self.reject(lambda:self.e.expand_horizons(self.a,p,request_id='csv106/again',seconds=60,reason='same lifetime'),pattern='once')

    def test_core_three_kr_two_csv_three_lesson_daily_pools_are_distinct(self):
        self.lessons(variant='local_translation')
        for i in range(2):self.lesson(self.pupil('아보',abilities=['탈피']),'versatile',request='kr/'+str(i),old_ability='탈피',new_ability='위협')
        p=self.pupil('아보',abilities=['탈피']);self.reject(lambda:self.lesson(p,'versatile',request='third',old_ability='탈피',new_ability='위협'),pattern='daily')
        self.new_day();self.lesson(p,'versatile',request='next',old_ability='탈피',new_ability='위협')

    def test_csv19_uses_level_pools_preserves_one_basic_and_no_unprinted_tp_cost(self):
        self.acquire();p=self.pupil('아보',level=30,abilities=['탈피','위협'],tp=0)
        advanced=self.r.learnsets['아보']['abilities']['숨겨진 특성'][0]
        out=self.lesson(p,'versatile',variant='class_data',old_ability='위협',new_ability=advanced)
        self.assertEqual((out['point_cost'],p.spec['tutor_points']),(0,0))
        self.assertEqual(out['admission']['source'],M.TECHNIQUES['versatile'])

    def test_guidance_and_lifelong_actual_acquisition_project_native_owned_slots(self):
        self.acquire();p=self.pupil(level=30)
        self.acquire(M.GUIDANCE);self.acquire(M.MOVE_TUTOR);self.acquire(M.LIFELONG)
        view=MOVES.describe(self.r,p.spec)
        self.assertEqual((view['total'],view['taught']),(7,4))
        self.assertIn(M.GUIDANCE,{r.get('rule_id') for r in view['sources']})
        self.assertIn(M.LIFELONG,{r.get('rule_id') for r in view['sources']})

    def test_move_tutor_core_any_pokemon_cost_two_daily_and_species_list(self):
        self.acquire();self.acquire(M.MOVE_TUTOR);p=self.pupil('브케인',level=30,owned=False)
        result=self.teach(p,'열풍',M.MOVE_TUTOR)
        self.assertEqual((result['classification'],result['point_cost'],p.spec['tutor_points']),('taught',2,6))
        self.reject(lambda:self.teach(p,'누르기',M.MOVE_TUTOR),pattern='daily frequency')

    def test_csv108_is_own_pokemon_daily_two_and_not_core_daily_one(self):
        self.acquire();self.acquire(M.MOVE_TUTOR,variant='local_csv');other=self.pupil('브케인',level=30,owned=False)
        self.reject(lambda:self.teach(other,'열풍',M.MOVE_TUTOR),pattern='own Pokemon')
        p=self.pupil('브케인',level=30);self.teach(p,'열풍',M.MOVE_TUTOR);self.teach(p,'누르기',M.MOVE_TUTOR)
        third=self.pupil('브케인',level=30)
        self.reject(lambda:self.teach(third,'열풍',M.MOVE_TUTOR),pattern='daily frequency')

    def test_core_egg_tutor_permanent_natural_once_even_after_forget_day_restore(self):
        self.acquire();self.acquire(M.MOVE_TUTOR);self.acquire(M.EGG_TUTOR);p=self.pupil('브케인',owned=False)
        out=self.teach(p,'두번차기',M.EGG_TUTOR)
        self.assertEqual((out['classification'],out['point_cost'],p.spec['tutor_points']),('natural',2,6))
        self.e.gm.set_move(p,'두번차기',add=False,reason='actual forgetting');self.new_day();p=self.restore()[p.entity_id]
        self.reject(lambda:self.teach(p,'탐내기',M.EGG_TUTOR),pattern='only once')

    def test_csv109_effective_own_loyalty_can_exceed_six_without_replacing_baseline(self):
        import pokemon_entities as ENT,pokemon_activities as ACT
        self.acquire();self.acquire(M.MOVE_TUTOR);self.acquire(M.EGG_TUTOR,variant='local_csv')
        p=self.pupil();self.e.gm.observe_loyalty(p,6,reason='actual top baseline loyalty')
        self.assertEqual((ENT.loyalty_value(p),ENT.effective_loyalty_value(p,engine=self.e),ACT.command_loyalty_value(self.e,p)),(6,7,7))
        other_owner=self.add(build_trainer(self.r,'other actual owner',20,STATS,abilities=[]))
        other=self.pupil(owned=False,trainer_id=other_owner.entity_id);self.e.gm.observe_loyalty(other,6,reason='actual other baseline loyalty')
        self.assertEqual(ENT.effective_loyalty_value(other,engine=self.e),6)
        import effects as FX
        self.assertEqual(FX.evaluate('user.loyalty',{'attacker':p,'engine':self.e}),7)
        self.assertEqual(FX.evaluate('user.loyalty',{'attacker':p}),6)
        self.reject(lambda:self.teach(p,'두번차기',M.EGG_TUTOR),pattern='EggList')

    def test_csv109_pending_and_wrong_target_policy_do_not_edit_charge_or_learn(self):
        self.acquire();self.acquire(M.MOVE_TUTOR);self.acquire(M.EGG_TUTOR,variant='local_csv');p=self.pupil(tp=0)
        document,decision=self.egg_policy(p)
        self.assertEqual(self.e.mentor_egg_list_policy(self.a,p,document)['status'],'PolicyInputsRequired')
        self.reject(lambda:self.e.edit_mentor_egg_list(self.a,p,'치유파동',document=document,request_id='pending',seconds=60,reason='actual attempt'),pattern='pending')
        other=self.pupil();wrong=deepcopy(document);wrong['variants'][0]['values']['target_id']=other.entity_id
        self.reject(lambda:self.e.edit_mentor_egg_list(self.a,p,'치유파동',document=wrong,decisions=decision,request_id='wrong',seconds=60,reason='actual attempt'))
        self.assertNotIn('mentor_egg_list',p.spec);self.assertNotIn('move/치유파동',p.moves)

    def test_csv109_scoped_individual_add_replace_zero_tp_daily_two_and_no_immediate_learning(self):
        self.acquire();self.acquire(M.MOVE_TUTOR);self.acquire(M.EGG_TUTOR,variant='local_csv');p=self.pupil(tp=0)
        document,decision=self.egg_policy(p);species_before=deepcopy(self.r.learnsets['이상해씨']['egg'])
        def edit(move,request,**extra):
            return self.e.edit_mentor_egg_list(self.a,p,move,document=document,decisions=decision,request_id=request,seconds=60,reason='actual source-scoped edit',**extra)
        out=edit('치유파동','add');self.assertEqual(out['point_cost'],0)
        registered=self.pupil('이브이',abilities=['도주'])
        self.assertIn('도주',registered.abilities)
        self.assertNotIn('move/치유파동',p.moves)
        teacher=self.add(build_trainer(self.r,'other actual Core Egg Tutor',20,STATS,abilities=[],
            extra={'classes':[],'feats':[],'skills':dict.fromkeys(M.SKILLS,6)}))
        for feature in (M.CLASS,M.MOVE_TUTOR,M.EGG_TUTOR):
            options={'skills':['매력','포켓몬학']} if feature==M.CLASS else {}
            self.e.acquire_mentor_feature(teacher,feature,request_id='other/'+feature,**options)
        __import__('pokemon_progression').observe_balance(self.e,p,balance=2,reason='GM observes actual available learning points')
        taught=T.teach_feature(self.e,teacher,target=p,move_id='치유파동',feature=M.EGG_TUTOR,seconds=60,reason='actual other Core teacher consumes individual EggList')
        self.assertEqual(taught['classification'],'natural')
        edit('몸통박치기','replace',replace='치유파동')
        self.assertEqual((p.spec['tutor_points'],self.e.elapsed_seconds),(0,180))
        self.assertEqual(self.r.learnsets['이상해씨']['egg'],species_before)
        self.assertIn('move/치유파동',p.moves);self.assertNotIn('move/몸통박치기',p.moves)
        self.assertEqual(MOVES.classifications(self.r,p.spec)['move/치유파동'],'natural')
        self.reject(lambda:edit('치유파동','third'),pattern='daily frequency')
        actors=self.restore(fresh_rules=True);p=actors[p.entity_id]
        self.assertIn('move/몸통박치기',M.individual_egg_list(self.r,p.spec))
        self.assertEqual(self.r._authored_policy_sources[M.CSV_EGG_POLICY]['locator'],{'record':109})
        self.assertEqual(MOVES.classifications(self.r,p.spec)['move/치유파동'],'natural')
        self.assertEqual(edit('치유파동','add'),out)

    def test_csv109_inheritance_scope_changes_only_the_named_individual_future_candidates(self):
        self.acquire();self.acquire(M.MOVE_TUTOR);self.acquire(M.EGG_TUTOR,variant='local_csv')
        p=self.pupil(level=20,inheritance_moves=[],inheritance_tutoring_policy='official_sep2015')
        other=self.pupil(level=20,inheritance_moves=[],inheritance_tutoring_policy='official_sep2015')
        document,decision=self.egg_policy(p,'individual_inheritance_list')
        self.e.edit_mentor_egg_list(self.a,p,'치유파동',document=document,decisions=decision,request_id='inheritance/add',seconds=60,reason='explicit individual inheritance interpretation')
        self.assertEqual(p.spec['inheritance_moves'],['move/치유파동']);self.assertEqual(other.spec['inheritance_moves'],[])
        GM.offer_inheritance(self.r,p.spec);self.assertEqual(p.spec[GM.KEY]['inheritance:20']['offered']['options'],[])

    def test_core_and_csv_lessons_each_consume_daily_three_instead_of_kr_two(self):
        for variant in ('core','local_csv'):
            self.setUp();self.lessons(variant=variant)
            for i in range(3):self.lesson(self.pupil('아보',abilities=['탈피']),'versatile',request=variant+'/'+str(i),old_ability='탈피',new_ability='위협')
            p=self.pupil('아보',abilities=['탈피'])
            self.reject(lambda:self.lesson(p,'versatile',request='fourth',old_ability='탈피',new_ability='위협'),pattern='daily')

    def test_class_data17_real_three_edge_effect_uses_exact_technique_source(self):
        self.acquire();p=self.pupil(tp=1)
        out=self.lesson(p,'empowered',variant='class_data',edges=self.edges(p))
        self.assertEqual((out['point_cost'],out['admission']['source']),(1,M.TECHNIQUES['empowered']))

    def test_class_data18_removes_actual_paid_effect_and_refunds_its_receipt(self):
        self.acquire(skills=('협박','포켓몬학'));p=self.pupil()
        PAY.acquire(self.e,p,'paid-effect',[{'source_id':'paid-effect/child','field':'skill_modifier','skill':'육상','delta':2}],2,rule_id=M.LESSONS,reason='actual TP effect')
        out=self.lesson(p,'corrective',variant='class_data',effect_id='paid-effect/child')
        self.assertEqual((out['refunded_points'],out['admission']['source']),(2,M.TECHNIQUES['corrective']))

    def test_lessons_reject_actual_combat_context_after_real_turn_initialization(self):
        self.lessons();p=self.pupil('이브이',abilities=['도주'])
        self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a,initiative_count=20)
        self.reject(lambda:self.lesson(p,'versatile',old_ability='도주',new_ability='전력질주'),pattern='active encounter')

    def test_chronicler_actual_archive_tutor_preserves_explicit_official_source_admission(self):
        import test_book_chronicler_actions as CF
        case=CF.ChroniclerActionTests('runTest');case.rules=self.r;case.setUp();case.whole()
        case.archive_move('move/전기자석파')
        out=case.tutor(case.p,'move/전기자석파',tutoring_policy='official_sep2015')
        self.assertEqual(out['point_cost'],2)
        self.assertEqual(case.p.spec['move_learning']['move/전기자석파']['archive_tutor_admission']['policy'],'official_sep2015')

    def test_official_tutor_under20_db7_vs_kr6_and_scene20_db9_thirty_unrestricted(self):
        under=self.r.move_id('베어가르기')
        self.assertEqual(T.tutor_admission(self.r,under,19,policy='official_sep2015')['damage_base'],7)
        with self.assertRaises(ValueError):T.tutor_admission(self.r,under,19,policy='kr_errata')
        heal=self.r.move_id('치유파동')
        with self.assertRaises(ValueError):T.tutor_admission(self.r,heal,20,policy='official_sep2015')
        self.assertEqual(T.tutor_admission(self.r,heal,30,policy='official_sep2015')['learned_at_level'],30)
        self.assertEqual(T.tutor_admission(self.r,heal,1,policy='core')['policy'],'core')

    def test_official_inheritance_preserves_future_candidate_and_delays_actual_learning20_to30(self):
        self.acquire();p=self.pupil(level=20,inheritance_moves=['move/치유파동'],inheritance_tutoring_policy='official_sep2015')
        GM.offer_inheritance(self.r,p.spec);self.assertEqual(p.spec[GM.KEY]['inheritance:20']['offered']['options'],[])
        self.assertEqual(p.spec['inheritance_moves'],['move/치유파동'])
        self.reject(lambda:self.e.choose_inheritance_move(p,20,'치유파동',reason='not yet eligible'))
        self.e.gm.set_level(p,30,reason='actual attained later inheritance level')
        out=self.e.choose_inheritance_move(p,30,'치유파동',reason='actual chosen later inheritance slot')
        self.assertFalse(out['replayed']);self.assertIn('move/치유파동',p.moves)
        self.assertEqual(p.spec['move_learning']['move/치유파동']['inheritance_slot'],30)
        self.assertEqual(MOVES.classifications(self.r,p.spec)['move/치유파동'],'natural')
        self.e.gm.set_level(p,31,reason='actual later level preserves permanent natural inheritance')
        self.assertTrue(p.spec['move_learning']['move/치유파동']['natural'])

    def test_official_inheritance_actual_egg_preserves_candidates_without_immediate_birth_learning(self):
        import test_foundation_egg_creation as EF
        case=EF.EggTests('runTest');case.r=self.r;case.setUp()
        policy=case.policy();policy['inheritance']['tutoring_policy']='official_sep2015'
        row=case.create(policy)
        self.assertEqual(row['inheritance_moves'],['move/뿌리박기'])
        assert_rejections_unchanged(case.e,[lambda:case.hatch(row)],reason_pattern='inherited candidates')
        choices=case.choices();choices['moves']=[]
        child=case.hatch(row,choices=choices)['pokemon']
        self.assertEqual(child.spec['inheritance_moves'],['move/뿌리박기'])
        self.assertNotIn('move/뿌리박기',child.moves)
        self.assertEqual(child.spec['inheritance_tutoring_policy'],'official_sep2015')

    def test_inheritance_native_levelup_producer_offers_slot_and_preserves_no_automatic_choice(self):
        import downtime as D
        p=self.pupil(level=19,inheritance_moves=['move/치유파동'],inheritance_tutoring_policy='official_sep2015')
        spec=deepcopy(p.spec);D.level_up(self.r,spec)
        self.assertIn('inheritance:20',spec[GM.KEY]);self.assertIsNone(spec[GM.KEY]['inheritance:20']['selection'])
        self.assertNotIn('move/치유파동',spec['moves'])


if __name__=='__main__':unittest.main()
