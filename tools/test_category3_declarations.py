"""Native declaration/response boundaries and remaining ordinary-check clauses."""
from copy import deepcopy
from datetime import datetime,timezone
from fractions import Fraction
import hashlib,itertools,json,random,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'engine'));sys.path.insert(0,str(ROOT/'tools'))
from engine import Engine,Rules,Combatant
import common_checks as C
from audit_common_probabilities import probability
CLAUSES=[*(f'C3-CORE-{n:03}' for n in (8,9,10,13,15,25,49,50,73)),'C3-EX-031','C3-EX-007']

class Category3DeclarationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.rules=Rules(str(ROOT),ruleset='core')
    def setUp(self):
        self.e=Engine(self.rules,seed=149)
        self.a=Combatant(self.rules,{'name':'행위자','kind':'trainer','level':20,
          'stats':{'hp':10,'atk':5,'def':5,'spa':5,'spd':5,'spe':5},
          'skills':{'은신':'초보','교활':'숙련','육상':'초보','일반지식':'전문'}})
        self.declaration={'action':'도시에서 뒤따른다','intent':'대상에게 들키지 않는다',
          'method':'군중에 섞여 동행인 척한다','proposed_skill':'은신'}
    def act(self,**kw):
        opts=dict(declaration=self.declaration,mode='skill',skill='교활',dc=10,fixed=[2,2,3,3])
        opts.update(kw)
        return self.e.common_action(self.a,**opts)
    def test_all_ten_scoped_source_groups_match(self):
        ledger=json.loads((ROOT/'data/verification/category3-register.json').read_text(encoding='utf-8'))
        found=set()
        for entry in ledger['entries']:
            if entry['id'] not in CLAUSES:continue
            found.add(entry['id']);snap=entry['source_snapshot']
            for src in snap.get('source_anchors') or [snap['source']]:
                start=src.get('start_line',src.get('start'));end=src.get('end_line',src.get('end'))
                actual='\n'.join((ROOT/src['file']).read_text(encoding='utf-8-sig').splitlines()[start-1:end])
                self.assertEqual(actual,src['excerpt'])
                self.assertEqual(hashlib.sha256(actual.encode()).hexdigest(),src['excerpt_sha256'])
        self.assertEqual(found,set(CLAUSES))
        text=(ROOT/'input/ch03-skills-edges-feats.md').read_text(encoding='utf-8').splitlines()
        self.assertIn('학자(Scholar)',text[543]);self.assertIn('전문 일반지식',text[544])
    def test_rank_judgment_reads_actual_athletics_and_waits_for_gm_without_rng(self):
        before=self.e.rng.getstate()
        out=self.e.common_action(self.a,'Athletics',mode='rank',declaration={'action':'긴 비탈을 오른다'})
        self.assertIsInstance(out,C.PendingDecision)
        self.assertEqual(out.basis['ordinary_rank'],3);self.assertEqual(out.basis['effective_rank'],3)
        self.assertIsNone(out.check);self.assertEqual(self.e.rng.getstate(),before)
        self.assertEqual(out.declaration['gm_selection']['mode'],'rank')
    def test_rank_judgment_retains_gm_failure_even_for_high_rank(self):
        self.a.spec['skills']['육상']='달인';before=self.e.rng.getstate()
        out=self.e.common_action(self.a,'육상',mode='rank',outcome='failure',description='GM: 이 조건에서는 재능 한계를 넘어 등반 불가')
        self.assertEqual(out.outcome,'failure');self.assertEqual(out.basis['ordinary_rank'],6)
        self.assertEqual(self.e.rng.getstate(),before)
        with self.assertRaises(ValueError):self.e.common_action(self.a,'육상',mode='rank',fixed=[6]*6)
        with self.assertRaises(ValueError):self.e.common_action(self.a,'육상',dc=15,mode='rank')
    def test_declaration_and_gm_world_response_are_preserved_separately(self):
        out=self.act(outcome='success',description='상대가 눈치채지 못하고 골목으로 들어간다')
        self.assertEqual(out.declaration['action'],self.declaration['action'])
        self.assertEqual(out.declaration['intent'],self.declaration['intent'])
        self.assertEqual(out.description,'상대가 눈치채지 못하고 골목으로 들어간다')
        self.assertEqual((out.check.total,out.check.passed),(10,True))
        self.declaration['intent']='나중에 변경'
        self.assertEqual(out.declaration['intent'],'대상에게 들키지 않는다')
    def test_declaration_is_not_automatic_eligibility_cost_or_world_effect(self):
        before=(self.e.rng.getstate(),deepcopy(self.a.spec),self.a.hp)
        p=self.act(mode=None)
        self.assertIsInstance(p,C.PendingDecision);self.assertIsNone(p.check)
        self.assertEqual((self.e.rng.getstate(),self.a.spec,self.a.hp),before)
    def test_same_tree_action_uses_gm_context_for_roll_or_no_roll(self):
        decl={'action':'나무에 오른다','intent':'나뭇가지에 앉는다','context':'공원에서 수다'}
        before=self.e.rng.getstate()
        a=self.e.common_action(self.a,mode='no_roll',declaration=decl,outcome='success',description='가지에 올라앉는다')
        self.assertIsNone(a.check);self.assertEqual(self.e.rng.getstate(),before)
        decl['intent']='추격하는 무리에게서 숨는다';decl['context']='추격 중'
        b=self.e.common_action(self.a,'육상',12,mode='skill',declaration=decl)
        oracle=random.Random(149);expected=sum(oracle.randint(1,6) for _ in range(3))
        self.assertEqual(b.check.total,expected)
        self.assertEqual(self.e.rng.getstate(),oracle.getstate())
        self.assertEqual(b.declaration['context'],'추격 중')
    def test_no_roll_still_waits_for_gm_world_response(self):
        before=self.e.rng.getstate()
        p=self.act(mode='no_roll',skill=None,dc=None,fixed=None)
        self.assertIsInstance(p,C.PendingDecision);self.assertIsNone(p.check)
        out=C.adjudicate(outcome='success',description='도착한다',declaration=p.declaration)
        self.assertEqual(out.declaration['intent'],self.declaration['intent'])
        self.assertEqual(self.e.rng.getstate(),before)
    def test_proposed_skill_never_substitutes_for_gm_selection(self):
        p=self.act(skill=None)
        self.assertIsNone(p.check)
        out=self.act()
        self.assertEqual(out.declaration['proposed_skill'],'은신')
        self.assertEqual(out.declaration['gm_selection'],{'mode':'skill','skill':'교활','dc':10})
        self.assertEqual(out.check.total,10)
    def test_same_outward_action_can_preserve_different_intents(self):
        results=[]
        for intent in ('다음 마을로 이동한다','야생 포켓몬을 찾는다'):
            decl={'action':'마을 외곽의 길을 걷는다','intent':intent,'method':'길을 따라 걷는다'}
            results.append(self.e.common_action(self.a,mode='no_roll',declaration=decl,
                outcome='success',description='GM이 목적에 맞게 정한 반응'))
        self.assertEqual(results[0].declaration['action'],results[1].declaration['action'])
        self.assertNotEqual(results[0].declaration['intent'],results[1].declaration['intent'])
    def test_specialized_activities_cannot_be_completed_by_generic_skill_roll(self):
        for activity in ('breeding','capture','befriending','fossils','fishing','mounting','combat'):
            before=self.e.rng.getstate()
            p=self.act(declaration={'action':'전문 활동을 시도한다','activity':activity},
                outcome='success',description='일반 DC를 넘음')
            self.assertIsInstance(p,C.PendingDecision);self.assertIsNone(p.check)
            self.assertIn('own procedure',p.required)
            self.assertEqual(p.declaration['activity'],activity)
            self.assertEqual(self.e.rng.getstate(),before)
    def test_undeclared_specialized_mode_still_cannot_fall_back_to_skill(self):
        before=self.e.rng.getstate()
        for mode in ('capture','breeding','combat','unknown'):
            p=self.e.common_action(self.a,'육상',1,mode=mode,fixed=[6]*3)
            self.assertIsInstance(p,C.PendingDecision);self.assertIsNone(p.check)
        self.assertEqual(self.e.rng.getstate(),before)
    def test_invalid_declarations_reject_before_rng(self):
        before=self.e.rng.getstate()
        for decl in ('attack',{}, {'action':''},{'action':'걷는다','unrecognized':True},{'action':'걷는다','intent':2}):
            with self.assertRaises(ValueError):self.act(declaration=decl)
        self.assertEqual(self.e.rng.getstate(),before)
    def test_gm_context_penalty_is_optional_and_preserves_task_dc(self):
        ordinary=self.act()
        penalized=self.act(penalty_count=1,fixed_penalties=[3])
        self.assertEqual((ordinary.check.total,ordinary.check.dc),(10,10))
        self.assertEqual((penalized.check.total,penalized.check.dc),(7,10))
        self.assertFalse(penalized.check.passed)
    def test_cost_success_requires_cost_and_explicit_small_margin_acceptance(self):
        p=self.act(dc=11)
        self.assertFalse(p.check.passed);self.assertEqual(p.check.margin,-1)
        for cost,accepted in [(None,True),('유물 하나 분실',False)]:
            result=C.adjudicate(p.check,outcome='success_with_cost',description='건너지만 유물을 잃는다',
                cost=cost,failure_margin_accepted=accepted,declaration=p.declaration)
            self.assertIsInstance(result,C.PendingDecision)
            self.assertEqual(result.declaration,p.declaration)
        result=C.adjudicate(p.check,outcome='success_with_cost',description='건너지만 유물을 잃는다',
            cost='유물 하나 분실',failure_margin_accepted=True,declaration=p.declaration)
        self.assertIsInstance(result,C.ActionOutcome)
        self.assertFalse(result.check.passed);self.assertEqual(result.cost,'유물 하나 분실')
        self.assertEqual(result.declaration,p.declaration)
    def test_small_failure_threshold_is_not_invented(self):
        for deficit in (1,2,5):
            p=self.act(dc=10+deficit,outcome='success_with_cost',description='대가를 치름',cost='GM 지정 대가')
            self.assertIsInstance(p,C.PendingDecision)
            self.assertFalse(p.check.passed)
    def test_probability_lookup_offsets_dc_once_and_does_not_change_real_check(self):
        for n in range(1,7):
            self.assertEqual(probability(n,14,modifier=4),probability(n,10))
        self.assertEqual(probability(3,14,modifier=4),Fraction(5,8))
        out=self.e.common_action(self.a,'육상',14,mode='skill',mods=4,fixed=[3,3,4])
        self.assertEqual((out.check.total,out.check.dc,out.check.margin),(14,14,0))
        # +4 remains below 14 when raw sum is 9; do not lower play DC to 10 and add +4 again.
        out=self.e.common_action(self.a,'육상',14,mode='skill',mods=4,fixed=[3,3,3])
        self.assertEqual((out.check.total,out.check.dc,out.check.passed),(13,14,False))
    def test_probability_offset_matches_independent_enumeration(self):
        for n in range(1,4):
            for modifier in (-2,0,4):
                total=6**n
                successful=sum(sum(faces)+modifier>=10 for faces in itertools.product(range(1,7),repeat=n))
                self.assertEqual(probability(n,10,modifier),Fraction(successful,total))
    def test_scholar_bonuses_all_six_skills_including_physical_survival(self):
        self.a.spec['edges']=['edge/학자']
        for skill in ('일반 지식','의학','오컬트학','포켓몬학','기술학','생존'):
            self.a.spec['skills'][skill]='전문'
            r=self.e.skill_roll(self.a,skill,fixed=[1]*5)
            self.assertEqual(r.total,6,skill)
        for skill in ('교활','통찰','집중','육상'):
            n=4 if skill=='교활' else 3 if skill=='육상' else 2
            self.assertEqual(self.e.skill_roll(self.a,skill,fixed=[1]*n).total,n)
    def test_scholar_requires_ownership_prerequisite_and_selected_profile(self):
        self.assertEqual(self.e.skill_roll(self.a,'일반지식',fixed=[1]*5).total,5)
        self.a.spec['edges']=['Scholar']
        self.a.spec['skills']['일반지식']='숙련'
        before=self.e.rng.getstate()
        with self.assertRaises(ValueError):self.e.skill_roll(self.a,'의학')
        self.assertEqual(self.e.rng.getstate(),before)
        self.a.spec['skills']['일반지식']='전문'
        self.assertEqual(self.e.skill_roll(self.a,'의학',fixed=[1]*2).total,3)
        from ruleset import RuleFilter
        rules=Rules(str(ROOT),ruleset='core')
        rules.ruleset=RuleFilter({'sources':['core'],'variants':[],'exclude_units':['edge/학자']})
        rules._apply_ruleset()
        e=Engine(rules,seed=149)
        with self.assertRaises(ValueError):e.skill_roll(self.a,'의학')
    def test_scholar_does_not_accept_fabricated_choices_or_repeat_stack(self):
        self.a.spec['edges']=['학자']
        self.a.spec['edge_choices']={'학자':['육상']}
        with self.assertRaises(ValueError):self.e.skill_roll(self.a,'육상')
        self.a.spec['edge_choices']={}
        self.a.spec['edges']=['학자','학자']
        with self.assertRaises(ValueError):self.e.skill_roll(self.a,'의학')

if __name__=='__main__':
    class Result(unittest.TextTestResult):
        def __init__(self,*a,**kw):super().__init__(*a,**kw);self.rows=[]
        def addSuccess(self,t):super().addSuccess(t);self.rows.append({'id':t._testMethodName,'status':'pass'})
        def addFailure(self,t,e):super().addFailure(t,e);self.rows.append({'id':t._testMethodName,'status':'fail'})
        def addError(self,t,e):super().addError(t,e);self.rows.append({'id':t._testMethodName,'status':'error'})
    result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(Category3DeclarationTests))
    files=['engine/adjudication_guidance.py','data/adjudication-guidance.json','engine/skill_maneuver_actions.py','engine/food_effects.py','engine/combat_social_edges.py','engine/net_capsule.py','engine/trainer_capabilities.py','engine/skill_feature_actions.py','engine/researcher_features.py','engine/precise_actions.py','engine/environmental_effects.py','engine/wild_equipment.py','engine/injury_recovery.py','engine/downtime.py','engine/items.py','engine/gm_state.py','engine/heavy_injury_adapter.py','engine/jump_actions.py','engine/context_actions.py','engine/pokemon_requests.py','engine/combat_timing.py','engine/combat_maneuvers.py','data/context-check-policy.json','data/cultivation-policy.json','engine/movement_actions.py','engine/weapon_actions.py','data/weapon-policy.json','engine/bandages.py','engine/crafting_activities.py','engine/contest_features.py','data/planter-policy.json','engine/capability_actions.py','engine/physical_limits.py','data/capability-policy.json','engine/temporary_hp.py','engine/engine.py','engine/ap_roll_bonus.py','engine/common_checks.py','engine/common_action_checks.py','engine/skill_modifiers.py',
       'engine/ruleset.py','engine/rulings.py','engine/resolution_transaction.py',
       'data/skill-check-policy.json','data/core-rules.json','data/lookup-tables.json','data/rulesets.json',
       'output/ruleunits.jsonl','input/ch03-skills-edges-feats.md','input/ch06-gameplay.md','input/ch11-running-the-game.md',
       'tools/audit_common_probabilities.py','tools/test_category3_declarations.py']
    files += ['engine/campaign_rewards.py', 'engine/league_consequences.py', 'data/campaign-reward-policy.json']
    files += ['engine/pokemon_understanding.py', 'engine/regional_pokemon.py', 'engine/source_context.py']
    files += ['engine/blessing_skill_features.py', 'engine/combat_precision_features.py', 'engine/pokemon_intelligence.py', 'engine/pokemon_party.py', 'engine/pokemon_teaching.py', 'data/pokemon-machines.json']

    files += ['engine/arithmetic.py', 'engine/arithmetic_policy.py', 'engine/effect_contracts.py', 'engine/effect_lifetimes.py', 'engine/maneuver_grants.py', 'engine/move_activation.py', 'engine/native_rule_policy.py', 'data/native-rule-policy.json']

    files += ['engine/action_lifecycle.py', 'engine/action_metadata.py', 'engine/action_points.py', 'engine/adjudication_guidance.py', 'engine/ap_roll_bonus.py', 'engine/bandages.py', 'engine/bound_ap.py', 'engine/builder.py', 'engine/capability_actions.py', 'engine/combat_maneuvers.py', 'engine/combat_social_edges.py', 'engine/combat_stage_sources.py', 'engine/combat_timing.py', 'engine/common_action_checks.py', 'engine/common_checks.py', 'engine/contest.py', 'engine/contest_features.py', 'engine/context_actions.py', 'engine/crafting_activities.py', 'engine/custom_species.py', 'engine/damage_reactions.py', 'engine/demo_rulings.py', 'engine/downtime.py', 'engine/effects.py', 'engine/effects_ext.py', 'engine/elemental_connection.py', 'engine/encounter.py', 'engine/enduring_awareness.py', 'engine/engine.py', 'engine/environmental_effects.py', 'engine/focus_tasks.py', 'engine/food_effects.py', 'engine/frequency.py', 'engine/gm_console.py', 'engine/gm_state.py', 'engine/grid.py', 'engine/heavy_injury_adapter.py', 'engine/heavy_injury_kernel.py', 'engine/heavy_standard_adapter.py', 'engine/initiative.py', 'engine/injury_recovery.py', 'engine/items.py', 'engine/jump_actions.py', 'engine/league_agenda.py', 'engine/league_runtime.py', 'engine/life.py', 'engine/maneuver_edges.py', 'engine/movement_actions.py', 'engine/net_capsule.py', 'engine/observed_resolution.py', 'engine/passive_event_profiles.py', 'engine/passive_events.py', 'engine/physical_limits.py', 'engine/physics_maneuvers.py', 'engine/pokemon_activities.py', 'engine/pokemon_requests.py', 'engine/precise_actions.py', 'engine/researcher_features.py', 'engine/resolution_transaction.py', 'engine/rest_intervals.py', 'engine/restorative_items.py', 'engine/root_admission.py', 'engine/root_children.py', 'engine/root_common_checks.py', 'engine/root_common_engine.py', 'engine/root_inputs.py', 'engine/root_machine.py', 'engine/root_resolution.py', 'engine/root_scheduler.py', 'engine/ruleset.py', 'engine/rulings.py', 'engine/skill_feature_actions.py', 'engine/skill_maneuver_actions.py', 'engine/skill_modifiers.py', 'engine/skill_stunts.py', 'engine/skill_targets.py', 'engine/survivalist_features.py', 'engine/temporary_hp.py', 'engine/test_builder.py', 'engine/test_contest.py', 'engine/test_downtime.py', 'engine/test_effects.py', 'engine/test_gm_state.py', 'engine/test_grid.py', 'engine/test_items.py', 'engine/test_maintenance.py', 'engine/test_playthrough.py', 'engine/test_rules.py', 'engine/test_ruleset.py', 'engine/test_rulings.py', 'engine/test_turn.py', 'engine/trainer_capabilities.py', 'engine/turn.py', 'engine/weapon_actions.py', 'engine/wild_equipment.py', 'data/content-source-identities.json', 'data/context-check-policy.json', 'data/skill-check-policy.json', 'data/adjudication-guidance.json', 'data/rulesets.json']
    report={'generated_at':datetime.now(timezone.utc).isoformat(),'successful':result.wasSuccessful(),'scope':CLAUSES,
       'results':result.rows,'input_hashes':{f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files}}
    (ROOT/'output/category3-declaration-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    raise SystemExit(0 if result.wasSuccessful() else 1)

