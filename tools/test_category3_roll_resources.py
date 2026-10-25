"""Native pre-roll AP and rank-dependent Virtuoso integration."""
import sys,json,hashlib,unittest
from copy import deepcopy
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'engine'))
from engine import Engine,Rules,Combatant
import skill_modifiers as S
import action_points as AP
class RollResourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.r=Rules(str(ROOT),ruleset='core')
    def setUp(self):
        self.e=Engine(self.r,seed=716)
        self.a=self.actor('trainer','trainer');self.p=self.actor('pokemon','pokemon')
    def actor(self,name,kind):
        actor=Combatant(self.r,{'name':name,'kind':kind,'level':20,'stats':{'hp':20,'atk':5,'def':5,'spa':5,'spd':5,'spe':5},'skills':{'육상':'달인','명령':'달인'},'moves':['move/화염방사']})
        self.e.gm.add_combatant(actor)
        return actor
    def prepare(self,actor=None,kind='skill',rid='one'):
        actor=actor or self.a
        if actor is not self.a:
            # ch06:85, Core 1.05 p.221: the bonus reaches only the payer's own current, registered Pokemon.
            actor.spec['trainer_id']=self.a.entity_id
        return self.e.boost_roll(self.a,actor,roll_id=rid,kind=kind)
    def test_source_before_once_free_self_or_pokemon(self):
        line=(ROOT/'input/ch06-gameplay.md').read_text(encoding='utf-8').splitlines()[84]
        for phrase in ['하기 전에 1 액션 포인트','프리 액션','굴림당 두 번 이상','포켓몬의 명중 또는 스킬']:self.assertIn(phrase,line)
        before=AP.available(self.a);self.prepare()
        self.assertEqual(AP.available(self.a),before-1)
        self.assertEqual(self.e.skill_roll(self.a,'육상',fixed=[1]*6,roll_id='one').total,7)
        self.assertEqual(self.e.skill_roll(self.a,'육상',fixed=[1]*6).total,6)
    def test_pokemon_skill_and_accuracy_get_one_without_changing_natural_face(self):
        self.prepare(self.p);self.assertEqual(self.e.skill_roll(self.p,'육상',fixed=[1]*6,roll_id='one').total,7)
        self.prepare(self.p,'accuracy','two')
        move=self.r.move('move/화염방사');target=self.actor('enemy','pokemon')
        target.stats['spe']=0;target.stats['spd']=5
        hit,natural,crit=self.e.accuracy_check(self.p,target,move,fixed_roll=move['ac'],roll_id='two')
        self.assertTrue(hit);self.assertEqual(natural,move['ac']);self.assertFalse(crit)
    def test_actual_move_consumes_bonus_and_natural_one_still_misses(self):
        target=self.actor('enemy','pokemon');target.stats['spd']=5;target.stats['spe']=0
        class FixedRng:
            def randint(self,a,b):return 2
        self.e.rng=FixedRng();self.prepare(self.p,'accuracy','attack')
        # The now trainer-owned attacker is a commanded Pokemon; its loyalty is an observed fact.
        self.e.gm.observe_loyalty(self.p,6,reason='observed relationship of the payer-owned Pokemon')
        self.assertGreater(self.e.use_move(self.p,target,'move/화염방사',set_damage=True,roll_id='attack'),0)
        self.assertEqual(self.e._ap_rolls['attack']['state'],'resolved')
        self.prepare(self.p,'accuracy','miss')
        self.assertFalse(self.e.accuracy_check(self.p,target,self.r.move('move/화염방사'),fixed_roll=1,roll_id='miss')[0])

    def test_duplicate_and_post_result_preparation_rejected(self):
        self.prepare();spent=self.a.spec['ap_spent']
        with self.assertRaises(ValueError):self.prepare()
        self.assertEqual(self.a.spec['ap_spent'],spent)
        self.e.skill_roll(self.a,'육상',fixed=[1]*6,roll_id='unboosted')
        with self.assertRaises(ValueError):self.prepare(rid='unboosted')
        self.e.skill_roll(self.a,'육상',fixed=[1]*6,roll_id='one')
        with self.assertRaises(ValueError):self.e.skill_roll(self.a,'육상',roll_id='one')
    def test_invalid_faces_preserve_prepared_bonus_and_rng(self):
        self.prepare();before=self.e.rng.getstate()
        with self.assertRaises(ValueError):self.e.skill_roll(self.a,'육상',fixed=[1],roll_id='one')
        self.assertEqual(self.e._ap_rolls['one']['state'],'prepared');self.assertEqual(self.e.rng.getstate(),before)
    def test_wrong_actor_kind_and_insufficient_ap_reject_before_spending(self):
        self.prepare();before=deepcopy(self.a.spec);rng=self.e.rng.getstate()
        with self.assertRaises(ValueError):self.e.skill_roll(self.p,'육상',roll_id='one')
        with self.assertRaises(ValueError):self.e.accuracy_check(self.a,self.p,self.r.move('move/화염방사'),roll_id='one')
        self.assertEqual(self.a.spec,before);self.assertEqual(self.e.rng.getstate(),rng)
        self.a.spec['ap_spent']=AP.maximum(self.a)
        with self.assertRaises(ValueError):self.prepare(rid='two')
        self.assertNotIn('two',self.e._ap_rolls)
    def test_free_action_must_be_permitted(self):
        self.e.encounter_active=True;before=deepcopy(self.a.spec)
        with self.assertRaises(ValueError):self.prepare()
        self.assertEqual(self.a.spec,before);self.assertEqual(self.e._ap_rolls,{})
    def test_team_and_opposed_duplicate_identity_reject_before_roll(self):
        for mode in ['team','opposed']:
            before=self.e.rng.getstate()
            with self.assertRaises(ValueError):
                if mode=='team':self.e.common_action(skill='육상',dc=10,mode='team',participants=[self.a,self.p],required_people=2,equal_contribution=True,no_main_actor=True,participant_options=[{'roll_id':'same'},{'roll_id':'same'}])
                else:self.e.opposed_check(self.a,'육상',self.p,'육상',challenger_options={'roll_id':'same'},defender_options={'roll_id':'same'})
            self.assertEqual(self.e.rng.getstate(),before);self.assertEqual(self.e._ap_rolls,{})
    def test_team_uses_prepaid_roll_once_and_preserves_live_references(self):
        self.prepare()
        out=self.e.common_action(skill='육상',dc=6,mode='team',participants=[self.a,self.p],required_people=2,equal_contribution=True,no_main_actor=True,participant_options=[{'roll_id':'one','fixed':[1]*6},{'roll_id':'two','fixed':[1]*6}])
        self.assertEqual(out.check.total,13);self.assertEqual(self.e._ap_rolls['one']['state'],'resolved')
        self.assertIs(self.a.r,self.r)
    def test_scene_and_snapshot_do_not_create_free_reusable_bonus(self):
        self.prepare();self.e.gm.everyone=[self.a,self.p];self.e.gm.snapshot('prepared')
        self.e.skill_roll(self.a,'육상',roll_id='one',fixed=[1]*6);self.e.gm.restore('prepared')
        self.assertIs(self.e._ap_rolls['one']['beneficiary'],self.a)
        self.e.end_scene([self.a,self.p])
        self.assertEqual(self.e._ap_rolls['one']['state'],'expired');self.assertEqual(AP.available(self.a),AP.maximum(self.a))
    def test_procedural_edge_source_scope_unchanged(self):
        ledger=json.loads((ROOT/'data/verification/category3-register.json').read_text(encoding='utf-8'))
        entry=next(e for e in ledger['entries'] if e['id']=='C3-EX-028')
        anchor=entry['source_snapshot']['source_anchors'][0]
        lines=(ROOT/anchor['file']).read_text(encoding='utf-8-sig').splitlines()
        excerpt='\n'.join(lines[anchor['start_line']-1:anchor['end_line']])
        self.assertEqual(hashlib.sha256(excerpt.encode('utf-8')).hexdigest(),anchor['excerpt_sha256'])
    def test_instruction_unconscious_helper_rejected_before_rng(self):
        self.a.spec['edges']=['edge/설명'];self.a.spec['skills']['일반지식']='초보'
        for field,value in [('hp',0),('dead',True)]:
            old=getattr(self.a,field);setattr(self.a,field,value);rng=self.e.rng.getstate()
            with self.assertRaises(ValueError):self.e.common_action(self.p,'육상',10,mode='skill',helper=self.a,helper_skill='일반지식')
            self.assertEqual(self.e.rng.getstate(),rng);setattr(self.a,field,old)
    def test_instinctive_aptitude_self_skill_and_accuracy_plus_two_for_one_ap(self):
        self.a.spec['edges']=['edge/타고난-적성'];self.a.spec['skills']['직감']='숙련'
        before=AP.available(self.a);self.assertEqual(self.prepare(),2)
        self.assertEqual(AP.available(self.a),before-1)
        self.assertEqual(self.e.skill_roll(self.a,'육상',fixed=[1]*6,roll_id='one').total,8)
        self.a.stats['spe']=0;self.p.stats['spe']=0;self.p.stats['spd']=0
        self.prepare(self.a,'accuracy','accuracy')
        move=dict(self.r.move('move/화염방사'));move['ac']=6
        self.assertTrue(self.e.accuracy_check(self.a,self.p,move,fixed_roll=4,roll_id='accuracy')[0])
    def test_instinctive_aptitude_cannot_enhance_pokemon_bonus_or_multiply_ap(self):
        self.a.spec['edges']=['Instinctive Aptitude'];self.a.spec['skills']['직감']='숙련'
        self.assertEqual(self.prepare(self.p),1)
        self.assertEqual(self.e.skill_roll(self.p,'육상',fixed=[1]*6,roll_id='one').total,7)
        with self.assertRaises(ValueError):self.prepare(self.p)
    def test_instinctive_prerequisite_and_selected_version_checked_before_ap(self):
        self.a.spec['edges']=['edge/타고난-적성'];before=deepcopy(self.a.spec);rng=self.e.rng.getstate()
        with self.assertRaises(ValueError):self.prepare()
        self.assertEqual(self.a.spec,before);self.assertEqual(self.e.rng.getstate(),rng)
        self.a.spec['skills']['직감']='숙련'
        original=self.r._selected_rule
        self.r._selected_rule=lambda uid, *args, **kwargs: 'alternate' if uid == 'edge/타고난-적성' else original(uid, *args, **kwargs)
        try:
            before=AP.available(self.a)
            with self.assertRaises(ValueError):self.prepare()
            self.assertEqual(AP.available(self.a),before)
        finally:self.r._selected_rule=original
    def test_instruction_uses_full_live_helper_rank_for_all_six_education_skills(self):
        helper=self.actor('helper','trainer');helper.spec['edges']=['Instruction']
        helper.spec['skills']['일반지식']='초보'
        for skill in ['일반지식','의학','오컬트학','포켓몬학','기술학','생존']:
            helper.spec['skills'][skill]='전문'
            out=self.e.common_action(self.p,'육상',11,mode='skill',helper=helper,helper_skill=skill,fixed=[1]*6)
            self.assertEqual((out.check.total,out.check.passed),(11,True))
    def test_instruction_non_education_help_keeps_half_and_own_roll_has_no_bonus(self):
        self.a.spec['edges']=['edge/설명'];self.a.spec['skills']['일반지식']='초보'
        out=self.e.common_action(self.p,'육상',9,mode='skill',helper=self.a,helper_skill='육상',fixed=[1]*6)
        self.assertEqual(out.check.total,9)
        self.assertEqual(self.e.skill_roll(self.a,'육상',fixed=[1]*6).total,6)
    def test_instruction_virtuoso_eight_bonus_is_separate_from_six_dice(self):
        self.a.spec['skills']['일반지식']='달인';self.a.spec['edges']=['edge/설명','edge/거장'];self.a.spec['edge_choices']={'Virtuoso':['일반지식']}
        out=self.e.common_action(self.p,'육상',14,mode='skill',helper=self.a,helper_skill='일반지식',fixed=[1]*6)
        self.assertEqual(out.check.total,14)
    def test_instruction_ineligible_helper_or_forged_bonus_rejects_before_rng(self):
        self.a.spec['edges']=['edge/설명'];before=self.e.rng.getstate()
        with self.assertRaises(ValueError):self.e.common_action(self.p,'육상',10,mode='skill',helper=self.a,helper_skill='육상')
        self.a.spec['skills']['일반지식']='초보'
        with self.assertRaises(ValueError):self.e.common_action(self.p,'육상',10,mode='skill',helper=self.a,helper_skill='의학')
        with self.assertRaises(ValueError):self.e.common_action(self.p,'육상',10,mode='skill',helper=self.a,helper_bonus=99)
        self.assertEqual(self.e.rng.getstate(),before)
    def test_instruction_selected_variant_or_pokemon_ownership_does_not_apply(self):
        self.a.spec['edges']=['edge/설명'];self.a.spec['skills']['일반지식']='초보'
        original=self.r._selected_rule
        self.r._selected_rule=lambda uid, *args, **kwargs: 'alternate' if uid == 'edge/설명' else original(uid, *args, **kwargs)
        try:
            with self.assertRaises(ValueError):self.e.common_action(self.p,'육상',10,mode='skill',helper=self.a,helper_skill='일반지식')
        finally:self.r._selected_rule=original
        self.a.kind='pokemon'
        with self.assertRaises(ValueError):self.e.common_action(self.p,'육상',10,mode='skill',helper=self.a,helper_skill='일반지식')
    def virtuoso(self,skills=None):
        self.a.spec['edges']=['edge/거장']*(len(skills) if skills else 1)
        self.a.spec['edge_choices']={'Virtuoso':skills or ['육상']}
    def test_virtuoso_effective_rank_eight_keeps_six_dice(self):
        self.virtuoso()
        self.assertEqual(S.effective_rank(self.r,self.a,'Athletics'),8)
        self.assertEqual(S.effective_rank(self.r,self.a,'명령'),6)
        self.assertEqual(self.e.skill_roll(self.a,'육상',fixed=[1]*6).total,6)
        with self.assertRaises(ValueError):self.e.skill_roll(self.a,'육상',fixed=[1]*8)
    def test_virtuoso_actual_helper_adds_four(self):
        self.virtuoso()
        out=self.e.common_action(self.p,'육상',10,mode='skill',helper=self.a,fixed=[1]*6)
        self.assertEqual(out.check.total,10)
    def test_virtuoso_extended_allows_four_six_die_intervals(self):
        self.virtuoso()
        for i in range(4):
            out=self.e.common_action(self.a,'육상',20,mode='extended',task_id='work',interval_id=str(i),interval={'amount':1,'unit':'hour'},interval_completed=True,complexity=2,limited=True,fixed=[1]*6)
            self.assertEqual(out.result.attempt_limit,4)
        self.assertEqual((out.result.status,out.result.total),('exhausted',24))
    def test_virtuoso_ownership_prerequisite_choices_and_repeated_distinct_skills(self):
        self.virtuoso(['육상','명령']);self.assertEqual(S.effective_rank(self.r,self.a,'명령'),8)
        self.a.spec['edge_choices']['Virtuoso']=['육상','Athletics']
        with self.assertRaises(ValueError):S.effective_rank(self.r,self.a,'육상')
        self.virtuoso();self.a.level=19
        with self.assertRaises(ValueError):S.effective_rank(self.r,self.a,'육상')
        self.a.level=20;self.a.spec['skills']['육상']='전문'
        with self.assertRaises(ValueError):S.effective_rank(self.r,self.a,'육상')
        self.a.spec['edges']=[]
        with self.assertRaises(ValueError):S.effective_rank(self.r,self.a,'육상')
if __name__=='__main__':
    class Result(unittest.TextTestResult):
        def __init__(self,*a,**kw):super().__init__(*a,**kw);self.rows=[]
        def addSuccess(self,t):super().addSuccess(t);self.rows.append({'id':t._testMethodName,'status':'pass'})
        def addFailure(self,t,e):super().addFailure(t,e);self.rows.append({'id':t._testMethodName,'status':'fail'})
        def addError(self,t,e):super().addError(t,e);self.rows.append({'id':t._testMethodName,'status':'error'})
    result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(RollResourceTests))
    files=['engine/adjudication_guidance.py','data/adjudication-guidance.json','engine/skill_maneuver_actions.py','engine/food_effects.py','engine/combat_social_edges.py','engine/net_capsule.py','engine/trainer_capabilities.py','engine/skill_feature_actions.py','engine/researcher_features.py','engine/precise_actions.py','engine/environmental_effects.py','engine/wild_equipment.py','engine/injury_recovery.py','engine/downtime.py','engine/items.py','engine/heavy_injury_adapter.py','engine/jump_actions.py','engine/context_actions.py','engine/pokemon_requests.py','engine/combat_timing.py','engine/combat_maneuvers.py','data/context-check-policy.json','data/cultivation-policy.json','engine/movement_actions.py','engine/weapon_actions.py','data/weapon-policy.json','engine/bandages.py','engine/crafting_activities.py','engine/contest_features.py','data/planter-policy.json','engine/capability_actions.py','engine/physical_limits.py','data/capability-policy.json','engine/temporary_hp.py','engine/engine.py','engine/ap_roll_bonus.py','engine/action_points.py','engine/common_checks.py','engine/common_action_checks.py','engine/skill_modifiers.py','engine/turn.py','engine/action_lifecycle.py','engine/resolution_transaction.py','engine/gm_state.py','engine/ruleset.py','data/skill-check-policy.json','data/core-rules.json','output/ruleunits.jsonl','input/ch03-skills-edges-feats.md','input/ch06-gameplay.md','tools/test_category3_roll_resources.py']
    files += ['engine/campaign_rewards.py', 'engine/league_consequences.py', 'data/campaign-reward-policy.json']
    files += ['engine/pokemon_understanding.py', 'engine/regional_pokemon.py', 'engine/source_context.py']
    files += ['engine/blessing_skill_features.py', 'engine/combat_precision_features.py', 'engine/pokemon_intelligence.py', 'engine/pokemon_party.py', 'engine/pokemon_teaching.py', 'data/pokemon-machines.json']

    files += ['engine/arithmetic.py', 'engine/arithmetic_policy.py', 'engine/effect_contracts.py', 'engine/effect_lifetimes.py', 'engine/maneuver_grants.py', 'engine/move_activation.py', 'engine/native_rule_policy.py', 'data/native-rule-policy.json']

    files += ['engine/action_lifecycle.py', 'engine/action_metadata.py', 'engine/action_points.py', 'engine/adjudication_guidance.py', 'engine/ap_roll_bonus.py', 'engine/bandages.py', 'engine/bound_ap.py', 'engine/builder.py', 'engine/capability_actions.py', 'engine/combat_maneuvers.py', 'engine/combat_social_edges.py', 'engine/combat_stage_sources.py', 'engine/combat_timing.py', 'engine/common_action_checks.py', 'engine/common_checks.py', 'engine/contest.py', 'engine/contest_features.py', 'engine/context_actions.py', 'engine/crafting_activities.py', 'engine/custom_species.py', 'engine/damage_reactions.py', 'engine/demo_rulings.py', 'engine/downtime.py', 'engine/effects.py', 'engine/effects_ext.py', 'engine/elemental_connection.py', 'engine/encounter.py', 'engine/enduring_awareness.py', 'engine/engine.py', 'engine/environmental_effects.py', 'engine/focus_tasks.py', 'engine/food_effects.py', 'engine/frequency.py', 'engine/gm_console.py', 'engine/gm_state.py', 'engine/grid.py', 'engine/heavy_injury_adapter.py', 'engine/heavy_injury_kernel.py', 'engine/heavy_standard_adapter.py', 'engine/initiative.py', 'engine/injury_recovery.py', 'engine/items.py', 'engine/jump_actions.py', 'engine/league_agenda.py', 'engine/league_runtime.py', 'engine/life.py', 'engine/maneuver_edges.py', 'engine/movement_actions.py', 'engine/net_capsule.py', 'engine/observed_resolution.py', 'engine/passive_event_profiles.py', 'engine/passive_events.py', 'engine/physical_limits.py', 'engine/physics_maneuvers.py', 'engine/pokemon_activities.py', 'engine/pokemon_requests.py', 'engine/precise_actions.py', 'engine/researcher_features.py', 'engine/resolution_transaction.py', 'engine/rest_intervals.py', 'engine/restorative_items.py', 'engine/root_admission.py', 'engine/root_children.py', 'engine/root_common_checks.py', 'engine/root_common_engine.py', 'engine/root_inputs.py', 'engine/root_machine.py', 'engine/root_resolution.py', 'engine/root_scheduler.py', 'engine/ruleset.py', 'engine/rulings.py', 'engine/skill_feature_actions.py', 'engine/skill_maneuver_actions.py', 'engine/skill_modifiers.py', 'engine/skill_stunts.py', 'engine/skill_targets.py', 'engine/survivalist_features.py', 'engine/temporary_hp.py', 'engine/test_builder.py', 'engine/test_contest.py', 'engine/test_downtime.py', 'engine/test_effects.py', 'engine/test_gm_state.py', 'engine/test_grid.py', 'engine/test_items.py', 'engine/test_maintenance.py', 'engine/test_playthrough.py', 'engine/test_rules.py', 'engine/test_ruleset.py', 'engine/test_rulings.py', 'engine/test_turn.py', 'engine/trainer_capabilities.py', 'engine/turn.py', 'engine/weapon_actions.py', 'engine/wild_equipment.py', 'data/content-source-identities.json', 'data/context-check-policy.json', 'data/skill-check-policy.json', 'data/adjudication-guidance.json', 'data/rulesets.json']
    report={'generated_at':datetime.now(timezone.utc).isoformat(),'successful':result.wasSuccessful(),'scope':['C3-CORE-035','C3-EX-028'],'results':result.rows,'input_hashes':{f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files}}
    (ROOT/'output/category3-roll-resource-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    raise SystemExit(0 if result.wasSuccessful() else 1)
