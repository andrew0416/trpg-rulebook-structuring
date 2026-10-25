"""Source-based Category 3 common-action tests using existing native Engine paths."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib, json, random, sys, unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'engine'))
from engine import Engine, Rules, Combatant
import common_checks as C
import state_codec as CODEC
import action_points as AP

CLAUSES=[f'C3-CORE-{n:03}' for n in (12,16,17,19,20,21,22,28,30,31,32)]

class Category3CommonActionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.rules=Rules(str(ROOT),ruleset='core')
    def setUp(self):
        self.e=Engine(self.rules,seed=419)
        self.a=self.actor('주행위자','초보')
        self.b=self.actor('포켓몬 동료','숙련',kind='pokemon')
        self.e.gm.everyone=[self.a,self.b]
    def actor(self,name,rank,kind='trainer'):
        return Combatant(self.rules,{'name':name,'kind':kind,'level':20,
          'stats':{'hp':10,'atk':5,'def':5,'spa':5,'spd':5,'spe':5},
          'skills':{'athletics':rank,'focus':rank}})
    def state(self):
        return (self.e.rng.getstate(),list(self.e.log_lines),deepcopy(getattr(self.e,'_extended_checks',{}), {id(c):c for c in self.e.gm.everyone}))
    def team(self,**kw):
        opts={'participants':[self.a,self.b],'required_people':2,'equal_contribution':True,
              'no_main_actor':True,'participant_options':[{'fixed':[2,2,2]},{'fixed':[1,1,2,2]}]}
        opts.update(kw)
        return self.e.common_action(skill='athletics',dc=6,mode='team',**opts)
    def extended(self,interval_id='i1',**kw):
        opts={'task_id':'repair','interval_id':interval_id,'interval':{'amount':1,'unit':'hour'},
              'interval_completed':True,'complexity':2,'limited':False,'fixed':[1,1,1]}
        opts.update(kw)
        return self.e.common_action(self.a,'athletics',3,mode='extended',**opts)
    def test_source_scopes_still_match_exact_excerpts(self):
        ledger=json.loads((ROOT/'data/verification/category3-register.json').read_text(encoding='utf-8'))
        for entry in ledger['entries']:
            if entry['id'] not in CLAUSES:continue
            source=entry['source_snapshot']['source']
            actual='\n'.join((ROOT/source['file']).read_text(encoding='utf-8-sig').splitlines()[source['start']-1:source['end']])
            self.assertEqual(actual,source['excerpt'],entry['id'])
            self.assertEqual(hashlib.sha256(actual.encode()).hexdigest(),source['excerpt_sha256'])
    def test_weighted_team_counts_chosen_actual_result_twice_not_required_dc(self):
        out=self.e.common_action(skill='athletics',dc=10,mode='team',participants=[self.a,self.b],required_people=2,
            equal_contribution=False,no_main_actor=True,contribution_weights=[1,2],weighting_reason='GM: huge high-Power Pokemon helps lift',
            participant_options=[{'fixed':[2,2,2]},{'fixed':[1,2,2,2]}])
        self.assertEqual((out.check.total,out.check.dc,out.check.passed),(20,20,True))
        self.assertEqual(out.basis['weights'],(1,2))
        self.assertIn('high-Power',out.basis['reason'])
    def test_weighting_never_infers_bonus_from_species_size_or_power(self):
        self.b.spec['size']='거대';self.b.spec['movement']={'power':16}
        self.assertEqual(self.team().check.total,12)
        before=self.state()
        self.assertIsInstance(self.team(equal_contribution=False),C.PendingDecision)
        self.assertEqual(self.state(),before)
    def test_weighting_requires_reason_and_valid_complete_multipliers_before_rng(self):
        before=self.state()
        self.assertIsInstance(self.team(equal_contribution=False,contribution_weights=[1,2]),C.PendingDecision)
        for weights in [[1],[1,0],[1,True],[1,1.5]]:
            with self.assertRaises(ValueError):self.team(equal_contribution=False,contribution_weights=weights,weighting_reason='GM context')
        self.assertEqual(self.state(),before)
    def test_weighted_team_invalid_last_actor_is_still_atomic(self):
        before=self.state()
        with self.assertRaises(ValueError):self.team(equal_contribution=False,contribution_weights=[1,2],weighting_reason='GM context',
            participant_options=[{}, {'fixed':[1]}])
        self.assertEqual(self.state(),before)
    def test_weighting_does_not_create_a_main_actor_or_helper_stacking(self):
        before=self.state()
        self.assertIsInstance(self.team(equal_contribution=False,no_main_actor=False,contribution_weights=[1,2],weighting_reason='GM'),C.PendingDecision)
        with self.assertRaises(ValueError):self.team(equal_contribution=False,contribution_weights=[1,2],weighting_reason='GM',
            participant_options=[{'helper':self.b},{}])
        self.assertEqual(self.state(),before)
    def test_dc_below_equal_above_and_gm_failure_response(self):
        for dc,passed in [(8,True),(9,True),(10,False)]:
            with self.subTest(dc=dc):
                result=self.e.common_action(self.a,'athletics',dc,mode='skill',fixed=[2,3,4],
                   outcome='success' if passed else 'failure',description='GM이 정한 행동 결과')
                self.assertEqual((result.check.total,result.check.dc,result.check.passed),(9,dc,passed))
                self.assertEqual(result.description,'GM이 정한 행동 결과')
    def test_numeric_failure_does_not_become_success_without_cost_and_gm_decision(self):
        result=self.e.common_action(self.a,'athletics',10,mode='skill',fixed=[3,3,3])
        self.assertIsInstance(result,C.PendingDecision);self.assertFalse(result.check.passed)
        result=self.e.common_action(self.a,'athletics',10,mode='skill',fixed=[3,3,3],
             outcome='success_with_cost',description='건너지만 물건 손실',cost='물건 하나',failure_margin_accepted=True)
        self.assertEqual(result.outcome,'success_with_cost');self.assertFalse(result.check.passed)
    def test_opposed_different_skills_and_separate_modifiers(self):
        self.assertTrue(self.e.opposed_check(self.a,'athletics',self.b,'focus',
             challenger_options={'fixed':[2,2,2],'mods':2},defender_options={'fixed':[1,1,1,1],'mods':3}))
        self.assertFalse(self.e.opposed_check(self.a,'athletics',self.b,'focus',
             challenger_options={'fixed':[1,1,1]},defender_options={'fixed':[1,1,1,1]}))
    def test_opposed_tie_favors_identified_status_quo_defender(self):
        self.assertFalse(self.e.opposed_check(self.a,'athletics',self.b,'focus',
             challenger_options={'fixed':[2,2,2]},defender_options={'fixed':[1,1,2,2]}))
        self.assertFalse(self.e.opposed_check(self.b,'focus',self.a,'athletics',
             challenger_options={'fixed':[1,1,2,2]},defender_options={'fixed':[2,2,2]}))
    def test_opposed_self_is_not_a_second_participant(self):
        before=self.state()
        with self.assertRaises(ValueError):self.e.opposed_check(self.a,'athletics',self.a,'focus')
        self.assertEqual(self.state(),before)
    def test_preflight_normalizes_supplied_dice_iterators_once(self):
        self.assertFalse(self.e.opposed_check(self.a,'athletics',self.b,'focus',
            challenger_options={'fixed':iter([2,2,2])},defender_options={'fixed':iter([1,1,2,2])}))
        team=self.team(participant_options=[{'fixed':iter([2,2,2])},{'fixed':iter([1,1,2,2])}])
        self.assertEqual(team.check.total,12)
        ext=self.extended(fixed=iter([1,1,1]))
        self.assertEqual(ext.result.total,3)

    def test_invalid_opponent_does_not_consume_challenger_rng(self):
        self.b.spec['skills']['focus']='알 수 없음';before=self.state()
        with self.assertRaises(ValueError):self.e.opposed_check(self.a,'athletics',self.b,'focus')
        self.assertEqual(self.state(),before)
    def test_team_requires_equal_contribution_and_no_main_actor(self):
        for change in ({'equal_contribution':None},{'no_main_actor':False},{'required_people':None}):
            before=self.state();result=self.team(**change)
            self.assertIsInstance(result,C.PendingDecision);self.assertIsNone(result.check)
            self.assertEqual(self.state(),before)
    def test_team_uses_required_count_and_actual_mixed_participants(self):
        result=self.team(required_people=3)
        self.assertIsInstance(result,C.PendingDecision)
        self.assertIsNotNone(result.check)
        self.assertEqual((result.check.total,result.check.dc,result.check.passed),(12,18,False))
    def test_extra_team_participant_does_not_change_dc(self):
        c=self.actor('추가 참가자','불능')
        self.e.gm.add_combatant(c,reason='actual additional team contributor')
        result=self.team(participants=[self.a,self.b,c],
              participant_options=[{'fixed':[2,2,2]},{'fixed':[1,1,2,2]},{'fixed':[6]}])
        self.assertIsNotNone(result.check)
        self.assertEqual((result.check.total,result.check.dc,result.check.passed),(18,12,True))
    def test_team_sum_and_dc_equality_success(self):
        result=self.team(outcome='success',description='함께 바위를 막음')
        self.assertIsInstance(result,C.ActionOutcome)
        self.assertEqual((result.check.total,result.check.dc,result.check.margin,result.check.passed),(12,12,0,True))
    def test_team_preflights_last_participant_before_any_roll(self):
        before=self.state()
        with self.assertRaises(ValueError):
            self.team(participant_options=[{}, {'fixed':[7,1,1,1]}])
        self.assertEqual(self.state(),before)
    def test_team_rejects_duplicate_empty_and_helper_composition(self):
        for opts in ({'participants':[],'participant_options':[]},
                     {'participants':[self.a,self.a],'participant_options':[{},{}]},
                     {'participant_options':[{'helper_rank':3},{}]}):
            before=self.state()
            with self.assertRaises(ValueError):self.team(**opts)
            self.assertEqual(self.state(),before)
    def test_assistance_uses_actual_helper_rank_and_normal_dc(self):
        for name,bonus in [('초보',1),('숙련',2),('전문',2),('달인',3)]:
            self.b.spec['skills']['focus']=name
            result=self.e.common_action(self.a,'athletics',9,mode='skill',helper=self.b,
                helper_skill='focus',fixed=[2,2,2])
            self.assertEqual((result.check.total,result.check.dc),(6+bonus,9))
    def test_assistance_rejects_ineligible_helper_before_rng(self):
        for rank in ('불능','미숙'):
            self.b.spec['skills']['focus']=rank;before=self.state()
            with self.assertRaises(ValueError):
                self.e.common_action(self.a,'athletics',9,mode='skill',helper=self.b,helper_skill='focus')
            self.assertEqual(self.state(),before)
        self.b.spec['skills']['focus']='초보';self.b.hp=0;before=self.state()
        with self.assertRaises(ValueError):
            self.e.common_action(self.a,'athletics',9,mode='skill',helper=self.b,helper_skill='focus')
        self.assertEqual(self.state(),before)
    def test_assistance_rejects_self_or_conflicting_rank(self):
        for opts in ({'helper':self.a,'helper_skill':'athletics'},
                     {'helper':self.b,'helper_skill':'focus','helper_rank':6}):
            before=self.state()
            with self.assertRaises(ValueError):self.e.common_action(self.a,'athletics',9,mode='skill',**opts)
            self.assertEqual(self.state(),before)
    def test_extended_dc_is_selected_multiplier_not_task_name(self):
        for factor in range(2,6):
            result=self.extended(task_id=f'task-{factor}',complexity=factor)
            self.assertEqual(result.result.dc,3*factor)
        before=self.state()
        with self.assertRaises(ValueError):self.extended(task_id='bad',complexity=6)
        self.assertEqual(self.state(),before)
    def test_zero_or_negative_extended_dc_is_not_rejected_or_forced_to_roll(self):
        for dc in (0,-1):
            before=self.e.rng.getstate()
            result=self.e.common_action(self.a,'athletics',dc,mode='extended',task_id=f'zero-{dc}',interval_id='1',
                interval={'amount':1,'unit':'hour'},interval_completed=True,complexity=2,limited=False)
            self.assertEqual((result.result.total,result.result.dc,result.result.status,result.result.attempts_used),(0,dc*2,'complete',0))
            self.assertEqual(self.e.rng.getstate(),before)

    def test_extended_missing_gm_decision_or_elapsed_interval_is_pending(self):
        for opts in ({'complexity':None},{'limited':None},{'interval_completed':False},{'interval':None}):
            before=self.state();result=self.extended(**opts)
            self.assertIsInstance(result,C.PendingDecision);self.assertEqual(self.state(),before)
    def test_unlimited_extended_accumulates_then_stops_on_equality(self):
        first=self.extended()
        self.assertEqual((first.result.total,first.result.status,first.result.attempt_limit),(3,'in_progress',None))
        final=self.extended('i2',outcome='success',description='수리 완료')
        self.assertEqual((final.result.total,final.result.status,final.result.attempts_used),(6,'complete',2))
        self.assertEqual(final.outcome.description,'수리 완료')
        before=self.state()
        with self.assertRaises(ValueError):self.extended('i3')
        self.assertEqual(self.state(),before)
    def test_unlimited_does_not_fabricate_completion_from_nonpositive_progress(self):
        first=self.extended(mods=-4)
        second=self.extended('i2',mods=-4)
        self.assertEqual((first.result.total,second.result.total,second.result.status),(-1,-2,'in_progress'))
    def test_limited_attempt_count_uses_rank_half_rounded_down(self):
        for rank,name,limit in [(1,'불능',0),(2,'미숙',1),(3,'초보',1),(4,'숙련',2),(5,'전문',2),(6,'달인',3)]:
            actor=self.actor(name,name);before=self.e.rng.getstate()
            result=self.e.common_action(actor,'athletics',100,mode='extended',task_id=name,interval_id='1',
                interval={'amount':1,'unit':'hour'},interval_completed=True,complexity=2,limited=True,fixed=[1]*rank)
            self.assertEqual(result.result.attempt_limit,limit)
            if rank==1:
                self.assertEqual((result.result.attempts_used,result.result.status),(0,'exhausted'))
                self.assertEqual(self.e.rng.getstate(),before)
    def test_limited_last_allowed_attempt_can_complete(self):
        self.a.spec['skills']['athletics']='전문'
        first=self.extended(limited=True,fixed=[1]*5)
        self.assertEqual((first.result.attempts_used,first.result.attempt_limit,first.result.status),(1,2,'in_progress'))
        final=self.extended('i2',limited=True,fixed=[1]*5)
        self.assertEqual((final.result.total,final.result.status),(10,'complete'))
    def test_limited_last_allowed_attempt_equality_is_success(self):
        self.a.spec['skills']['athletics']='전문'
        for interval in ('i1','i2'):
            result=self.e.common_action(self.a,'athletics',5,mode='extended',task_id='limited',interval_id=interval,
                interval={'amount':1,'unit':'hour'},interval_completed=True,complexity=2,limited=True,fixed=[1]*5)
        self.assertEqual((result.result.total,result.result.dc,result.result.status),(10,10,'complete'))
    def test_limited_exhaustion_cannot_be_retried_silently(self):
        result=self.extended(limited=True)
        self.assertEqual((result.result.total,result.result.status),(3,'exhausted'))
        before=self.state()
        with self.assertRaises(ValueError):self.extended('i2',limited=True)
        self.assertEqual(self.state(),before)
    def test_duplicate_interval_and_changed_task_identity_are_rejected(self):
        self.extended();before=self.state()
        with self.assertRaises(ValueError):self.extended()
        self.assertEqual(self.state(),before)
        for opts in ({'complexity':3},{'interval':{'amount':2,'unit':'hour'}},{'limited':True}):
            with self.assertRaises(ValueError):self.extended('i2',**opts)
            self.assertEqual(self.state(),before)
        self.a.spec['skills']['athletics']='숙련'
        with self.assertRaises(ValueError):self.extended('i2',fixed=[1]*4)
        self.assertEqual(self.state(),before)
    def test_extended_snapshot_restore_keeps_history_and_live_actor_identity(self):
        self.extended();self.e.gm.snapshot('halfway')
        self.extended('i2');self.e.gm.restore('halfway')
        result=self.extended('i2')
        self.assertEqual((result.result.total,result.result.attempts_used),(6,2))
        self.assertIs(self.e._extended_checks['repair']['actor'],self.a)
    def test_extended_does_not_run_during_combat(self):
        self.e.encounter_active=True;before=self.state()
        result=self.extended()
        self.assertIsInstance(result,C.PendingDecision);self.assertEqual(self.state(),before)
    def test_mixed_team_and_assistance_use_same_live_participants_after_codec(self):
        self.e.everyone=self.e.gm.everyone
        out=self.team(outcome='success',description='actual mixed trainer and Pokemon team')
        self.assertEqual((out.check.total,out.check.dc),(12,12))
        out=self.e.common_action(self.a,'athletics',9,mode='skill',helper=self.b,helper_skill='focus',fixed=[2,2,3])
        self.assertEqual((out.check.total,out.check.dc),(9,9))
        loaded=CODEC.load_engine(self.rules,json.loads(json.dumps(CODEC.dump_engine(self.e),ensure_ascii=False)));actors={c.entity_id:c for c in loaded.everyone}
        a,b=actors[self.a.entity_id],actors[self.b.entity_id]
        out=loaded.common_action(a,'athletics',9,mode='skill',helper=b,helper_skill='focus',fixed=[2,2,3])
        self.assertEqual((out.check.total,out.check.dc),(9,9));self.assertTrue(loaded.validate_state()['valid'])
    def test_limited_and_unlimited_extended_history_resumes_same_actor_after_codec(self):
        for limited in (False,True):
            with self.subTest(limited=limited):
                self.setUp();self.e.everyone=self.e.gm.everyone
                options=dict(mode='extended',task_id='durable-native',interval={'amount':1,'unit':'minute'},interval_completed=True,complexity=2,limited=limited,fixed=[1]*4)
                first=self.e.common_action(self.b,'athletics',3,interval_id='one',**options)
                self.assertEqual((first.result.total,first.result.status,first.result.attempt_limit),(4,'in_progress',2 if limited else None))
                loaded=CODEC.load_engine(self.rules,json.loads(json.dumps(CODEC.dump_engine(self.e),ensure_ascii=False)));actor=next(c for c in loaded.everyone if c.entity_id==self.b.entity_id)
                self.assertIs(loaded._extended_checks['durable-native']['actor'],actor)
                final=loaded.common_action(actor,'athletics',3,interval_id='two',**options)
                self.assertEqual((final.result.total,final.result.status,final.result.attempts_used),(8,'complete',2))
                before=(loaded.rng.getstate(),deepcopy(actor.spec),tuple(loaded._extended_checks['durable-native']['interval_ids']))
                with self.assertRaisesRegex(ValueError,'terminal'):loaded.common_action(actor,'athletics',3,interval_id='three',**options)
                self.assertEqual((loaded.rng.getstate(),actor.spec,tuple(loaded._extended_checks['durable-native']['interval_ids'])),before)
    def test_pre_roll_ap_bonus_self_and_pokemon_skill_accuracy_survives_codec_once(self):
        self.e.everyone=self.e.gm.everyone
        # ch06:85, Core 1.05 p.221 "your Pokemon's": the boosted Pokemon is the paying trainer's own.
        self.b.spec['trainer_id']=self.a.entity_id
        for beneficiary_key,rank in [('a',3),('b',4)]:
            for kind in ['skill','accuracy']:
                beneficiary=getattr(self,beneficiary_key);roll_id=beneficiary_key+':'+kind;available=AP.available(self.a)
                self.assertEqual(self.e.boost_roll(self.a,beneficiary,roll_id=roll_id,kind=kind),1)
                self.assertEqual(AP.available(self.a),available-1);before=(AP.available(self.a),self.e.rng.getstate())
                with self.assertRaisesRegex(ValueError,'already'):self.e.boost_roll(self.a,beneficiary,roll_id=roll_id,kind=kind)
                self.assertEqual((AP.available(self.a),self.e.rng.getstate()),before)
                loaded=CODEC.load_engine(self.rules,json.loads(json.dumps(CODEC.dump_engine(self.e),ensure_ascii=False)));actors={c.entity_id:c for c in loaded.everyone}
                self.a,self.b=actors[self.a.entity_id],actors[self.b.entity_id];self.e=loaded;beneficiary=getattr(self,beneficiary_key)
                self.assertIs(loaded._ap_rolls[roll_id]['payer'],self.a);self.assertIs(loaded._ap_rolls[roll_id]['beneficiary'],beneficiary)
                if kind=='skill':
                    out=loaded.common_action(beneficiary,'athletics',1,mode='skill',fixed=[1]*rank,roll_id=roll_id)
                    self.assertEqual(out.check.total,rank+1)
                else:
                    other=self.b if beneficiary is self.a else self.a
                    self.assertTrue(loaded.accuracy_check(beneficiary,other,self.rules.move('move/블록'),fixed_roll=2,roll_id=roll_id)[0])
                self.assertEqual(loaded._ap_rolls[roll_id]['state'],'resolved');self.assertEqual(AP.available(self.a),available-1)
        self.assertTrue(self.e.validate_state()['valid'])
    def test_native_accuracy_meets_printed_ac_plus_actual_evasion_at_equality(self):
        self.e.everyone=self.e.gm.everyone;move=self.rules.move('move/블록');self.assertEqual(move['ac'],2)
        self.assertFalse(self.e.accuracy_check(self.a,self.b,move,fixed_roll=2)[0])
        self.assertTrue(self.e.accuracy_check(self.a,self.b,move,fixed_roll=3)[0])
    def test_random_team_rolls_use_each_actual_rank(self):
        oracle=random.Random(419)
        expected=sum(oracle.randint(1,6) for _ in range(7))
        result=self.team(participant_options=[{},{}])
        self.assertIsNotNone(result.check)
        self.assertEqual(result.check.total,expected);self.assertEqual(self.e.rng.getstate(),oracle.getstate())

if __name__=='__main__':
    class Result(unittest.TextTestResult):
        def __init__(self,*a,**kw):super().__init__(*a,**kw);self.rows=[]
        def addSuccess(self,t):super().addSuccess(t);self.rows.append({'id':t._testMethodName,'status':'pass'})
        def addFailure(self,t,e):super().addFailure(t,e);self.rows.append({'id':t._testMethodName,'status':'fail'})
        def addError(self,t,e):super().addError(t,e);self.rows.append({'id':t._testMethodName,'status':'error'})
    result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(Category3CommonActionTests))
    files=['engine/adjudication_guidance.py','data/adjudication-guidance.json','engine/skill_maneuver_actions.py','engine/food_effects.py','engine/combat_social_edges.py','engine/net_capsule.py','engine/trainer_capabilities.py','engine/skill_feature_actions.py','engine/researcher_features.py','engine/precise_actions.py','engine/environmental_effects.py','engine/wild_equipment.py','engine/injury_recovery.py','engine/downtime.py','engine/items.py','engine/heavy_injury_adapter.py','engine/jump_actions.py','engine/context_actions.py','engine/pokemon_requests.py','engine/combat_timing.py','engine/combat_maneuvers.py','data/context-check-policy.json','data/cultivation-policy.json','engine/movement_actions.py','engine/weapon_actions.py','data/weapon-policy.json','engine/bandages.py','engine/crafting_activities.py','engine/contest_features.py','data/planter-policy.json','engine/capability_actions.py','engine/physical_limits.py','data/capability-policy.json','engine/temporary_hp.py','engine/skill_modifiers.py','data/skill-check-policy.json','engine/engine.py','engine/ap_roll_bonus.py','engine/common_checks.py','engine/gm_state.py','engine/ruleset.py','engine/resolution_transaction.py',
           'data/core-rules.json','data/lookup-tables.json','data/rulesets.json','engine/rulings.py','output/ruleunits.jsonl','input/ch06-gameplay.md','input/ch03-skills-edges-feats.md',
           'tools/test_category3_common_actions.py']
    files += ['engine/campaign_rewards.py', 'engine/league_consequences.py', 'data/campaign-reward-policy.json']
    files += ['engine/pokemon_understanding.py', 'engine/regional_pokemon.py', 'engine/source_context.py']
    files += ['engine/blessing_skill_features.py', 'engine/combat_precision_features.py', 'engine/pokemon_intelligence.py', 'engine/pokemon_party.py', 'engine/pokemon_teaching.py', 'data/pokemon-machines.json']

    files += ['engine/arithmetic.py', 'engine/arithmetic_policy.py', 'engine/effect_contracts.py', 'engine/effect_lifetimes.py', 'engine/maneuver_grants.py', 'engine/move_activation.py', 'engine/native_rule_policy.py', 'data/native-rule-policy.json']

    files += ['engine/action_lifecycle.py', 'engine/action_metadata.py', 'engine/action_points.py', 'engine/adjudication_guidance.py', 'engine/ap_roll_bonus.py', 'engine/bandages.py', 'engine/bound_ap.py', 'engine/builder.py', 'engine/capability_actions.py', 'engine/combat_maneuvers.py', 'engine/combat_social_edges.py', 'engine/combat_stage_sources.py', 'engine/combat_timing.py', 'engine/common_action_checks.py', 'engine/common_checks.py', 'engine/contest.py', 'engine/contest_features.py', 'engine/context_actions.py', 'engine/crafting_activities.py', 'engine/custom_species.py', 'engine/damage_reactions.py', 'engine/demo_rulings.py', 'engine/downtime.py', 'engine/effects.py', 'engine/effects_ext.py', 'engine/elemental_connection.py', 'engine/encounter.py', 'engine/enduring_awareness.py', 'engine/engine.py', 'engine/environmental_effects.py', 'engine/focus_tasks.py', 'engine/food_effects.py', 'engine/frequency.py', 'engine/gm_console.py', 'engine/gm_state.py', 'engine/grid.py', 'engine/heavy_injury_adapter.py', 'engine/heavy_injury_kernel.py', 'engine/heavy_standard_adapter.py', 'engine/initiative.py', 'engine/injury_recovery.py', 'engine/items.py', 'engine/jump_actions.py', 'engine/league_agenda.py', 'engine/league_runtime.py', 'engine/life.py', 'engine/maneuver_edges.py', 'engine/movement_actions.py', 'engine/net_capsule.py', 'engine/observed_resolution.py', 'engine/passive_event_profiles.py', 'engine/passive_events.py', 'engine/physical_limits.py', 'engine/physics_maneuvers.py', 'engine/pokemon_activities.py', 'engine/pokemon_requests.py', 'engine/precise_actions.py', 'engine/researcher_features.py', 'engine/resolution_transaction.py', 'engine/rest_intervals.py', 'engine/restorative_items.py', 'engine/root_admission.py', 'engine/root_children.py', 'engine/root_common_checks.py', 'engine/root_common_engine.py', 'engine/root_inputs.py', 'engine/root_machine.py', 'engine/root_resolution.py', 'engine/root_scheduler.py', 'engine/ruleset.py', 'engine/rulings.py', 'engine/skill_feature_actions.py', 'engine/skill_maneuver_actions.py', 'engine/skill_modifiers.py', 'engine/skill_stunts.py', 'engine/skill_targets.py', 'engine/survivalist_features.py', 'engine/temporary_hp.py', 'engine/test_builder.py', 'engine/test_contest.py', 'engine/test_downtime.py', 'engine/test_effects.py', 'engine/test_gm_state.py', 'engine/test_grid.py', 'engine/test_items.py', 'engine/test_maintenance.py', 'engine/test_playthrough.py', 'engine/test_rules.py', 'engine/test_ruleset.py', 'engine/test_rulings.py', 'engine/test_turn.py', 'engine/trainer_capabilities.py', 'engine/turn.py', 'engine/weapon_actions.py', 'engine/wild_equipment.py', 'data/content-source-identities.json', 'data/context-check-policy.json', 'data/skill-check-policy.json', 'data/adjudication-guidance.json', 'data/rulesets.json']
    if (ROOT/'engine/common_action_checks.py').exists():files.append('engine/common_action_checks.py')
    report={'generated_at':datetime.now(timezone.utc).isoformat(),'successful':result.wasSuccessful(),
            'scope':CLAUSES,'results':result.rows,
            'input_hashes':{f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files}}
    (ROOT/'output/category3-common-action-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    raise SystemExit(0 if result.wasSuccessful() else 1)

