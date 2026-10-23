"""Category 3 native skill composition, source choices and GM result boundaries."""
from copy import deepcopy
from datetime import datetime,timezone
import hashlib,json,random,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'engine'))
from engine import Engine,Rules,Combatant
import common_checks as C
import items
CATEGORY='edge/단정적인-경향'
ENHANCEMENT='edge/스킬-향상'
CLAUSES=[*(f'C3-CORE-{n:03}' for n in (11,18,23,24,29,77,78)),*(f'C3-EX-{n:03}' for n in (6,16,17))]

class Category3SkillTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.rules=Rules(str(ROOT),ruleset='core')
    def setUp(self):
        self.e=Engine(self.rules,seed=937)
        self.a=self.actor('검사자','전문')
        self.b=self.actor('포켓몬 동료','초보','pokemon')
    def actor(self,name,rank,kind='trainer'):
        actor=Combatant(self.rules,{'name':name,'kind':kind,'level':20,
         'stats':{'hp':10,'atk':5,'def':5,'spa':5,'spd':5,'spe':5},
         'skills':{'육상':rank,'통찰':rank,'집중':rank}})
        self.e.gm.everyone.append(actor)
        return actor
    def equip_edges(self,edges,choices):
        self.a.spec['edges']=edges
        self.a.spec['edge_choices']=choices
    def roll(self,skill='athletics',**kw):
        return self.e.skill_roll(self.a,skill,**kw)
    def unchanged_rejection(self,call):
        before=(self.e.rng.getstate(),list(self.e.log_lines),deepcopy(self.a.__dict__, {id(self.a.r):self.a.r}))
        with self.assertRaises(ValueError):call()
        self.assertEqual((self.e.rng.getstate(),self.e.log_lines,self.a.__dict__),before)
    def test_scoped_source_anchors_unchanged(self):
        ledger=json.loads((ROOT/'data/verification/category3-register.json').read_text(encoding='utf-8'))
        found=set()
        for entry in ledger['entries']:
            if entry['id'] not in CLAUSES:continue
            found.add(entry['id']);snapshot=entry['source_snapshot']
            anchors=snapshot.get('source_anchors') or [snapshot['source']]
            for src in anchors:
                start=src.get('start_line',src.get('start'));end=src.get('end_line',src.get('end'))
                text='\n'.join((ROOT/src['file']).read_text(encoding='utf-8-sig').splitlines()[start-1:end])
                self.assertEqual(text,src['excerpt'])
                self.assertEqual(hashlib.sha256(text.encode()).hexdigest(),src['excerpt_sha256'])
        self.assertEqual(found,set(CLAUSES))
    def test_all_six_ranks_named_numeric_and_english(self):
        for n,(ko,en) in enumerate(zip(['불능','미숙','초보','숙련','전문','달인'],
                ['Pathetic','Untrained','Novice','Adept','Expert','Master']),1):
            for stored in (ko,en,n):
                self.a.spec['skills']={'육상':stored}
                for query in ('육상','Athletics','athletics'):
                    r=self.roll(query,fixed=[2]*n,mods=3)
                    self.assertEqual((r.rank,len(r.faces),r.total),(n,n,n*2+3))
    def test_ordinary_untrained_start_and_conflicting_alias_rejection(self):
        self.a.spec['skills']={}
        self.assertEqual(self.roll(fixed=[1,2]).total,3)
        self.a.spec['skills']={'육상':3,'Athletics':'숙련'}
        self.unchanged_rejection(self.roll)
    def test_invalid_rank_or_faces_rejected_before_rng(self):
        for bad in (0,7,True,3.0,'거장'):
            self.a.spec['skills']={'육상':bad}
            self.unchanged_rejection(self.roll)
        self.a.spec['skills']={'육상':3}
        for bad in ([1,2],[1,2,3,4],[1,2,7],[1,True,3]):
            self.unchanged_rejection(lambda:self.roll(fixed=bad))
    def test_expert_athletics_source_example_five_d6_plus_two(self):
        self.equip_edges([ENHANCEMENT],{ENHANCEMENT:[['육상','집중']]})
        r=self.roll(fixed=[1,2,3,4,5])
        self.assertEqual((r.rank,r.modifier,r.total),(5,2,17))
        self.assertTrue(self.e.skill_check(self.a,'육상',17,fixed=[1,2,3,4,5])[0])
        self.assertFalse(self.e.skill_check(self.a,'육상',18,fixed=[1,2,3,4,5])[0])
    def test_other_resolved_modifiers_add_without_changing_pool(self):
        self.equip_edges([ENHANCEMENT],{ENHANCEMENT:[['육상','집중']]})
        for external,expected in [(4,11),(-3,4),(0,7)]:
            r=self.roll(fixed=[1]*5,mods=external)
            self.assertEqual((len(r.faces),r.modifier,r.total),(5,external+2,expected))
    def test_category_bonus_all_seventeen_source_skills(self):
        groups={'신체':['곡예','육상','전투','협박','은신','생존'],
          '정신':['일반 지식','의학','오컬트학','포켓몬학','기술학','교활','통찰'],
          '영혼':['매력','명령','집중','직감']}
        for chosen,skills in groups.items():
            self.equip_edges([CATEGORY],{CATEGORY:chosen})
            for group,others in groups.items():
                for skill in others:
                    self.a.spec['skills']={skill:3}
                    r=self.roll(skill,fixed=[1]*3)
                    self.assertEqual(r.total,4 if group==chosen else 3,(chosen,skill))
    def test_category_aliases_and_edge_name_aliases(self):
        for category in ('육체','신체','physical','body'):
            self.equip_edges(['Categoric Inclination'],{'단정적인 경향':category})
            self.assertEqual(self.roll(fixed=[1]*5).total,6)
        self.equip_edges(['Skill Enhancement'],{'스킬 향상':[['Athletics','General Education']]})
        self.a.spec['skills']={'일반지식':3}
        self.assertEqual(self.roll('general_education',fixed=[2]*3).total,8)
    def test_enhancement_distinct_two_skills_and_once_per_skill(self):
        self.equip_edges([ENHANCEMENT]*2,{ENHANCEMENT:[['육상','통찰'],['Athletics','Focus']]})
        for skill in ('육상','통찰','집중'):
            self.assertEqual(self.roll(skill,fixed=[1]*5).total,7)
        self.assertEqual(self.roll('charm',fixed=[1]*2).total,2)
    def test_missing_or_invalid_edge_choice_rejected_before_rng(self):
        cases=[([CATEGORY],{}),([CATEGORY],{CATEGORY:'unknown'}),
          ([CATEGORY]*2,{CATEGORY:'신체'}),([ENHANCEMENT],{}),
          ([ENHANCEMENT],{ENHANCEMENT:[['육상']]}),
          ([ENHANCEMENT],{ENHANCEMENT:[['육상','Athletics']]}),
          ([ENHANCEMENT],{ENHANCEMENT:[['unknown','집중']]}),
          ([ENHANCEMENT]*2,{ENHANCEMENT:[['육상','집중']]}),
          ([ENHANCEMENT],{ENHANCEMENT:[['육상','집중']], 'Skill Enhancement':[['육상','통찰']]})]
        for edges,choices in cases:
            with self.subTest(choices=choices):
                self.equip_edges(edges,choices);self.unchanged_rejection(self.roll)
    def test_choices_cannot_grant_unowned_or_pokemon_edge(self):
        for edges,choices in [([],{CATEGORY:'신체'}),([],{ENHANCEMENT:[['육상','집중']]}),
             (['poke_edge/스킬-향상'],{ENHANCEMENT:[['육상','집중']]})]:
            self.equip_edges(edges,choices);self.unchanged_rejection(self.roll)
        self.equip_edges([ENHANCEMENT],{ENHANCEMENT:[['육상','집중']]})
        self.a.kind='pokemon';self.unchanged_rejection(self.roll)
    def test_excluded_edge_does_not_grant_bonus(self):
        from ruleset import RuleFilter,RuleSelection
        rules=Rules(str(ROOT),ruleset='core')
        rules.ruleset=RuleFilter({'sources':['core'],'variants':[],'exclude_units':[ENHANCEMENT]})
        rules._apply_ruleset()
        rules.selection=RuleSelection(rules.ruleset,list(rules.selection.units.values()))
        self.rules=rules
        self.e=Engine(rules,seed=937)
        self.a=self.actor('검사자','전문')
        self.equip_edges([ENHANCEMENT],{ENHANCEMENT:[['육상','집중']]})
        self.unchanged_rejection(self.roll)
    def test_legacy_feat_registration_does_not_duplicate_bonus(self):
        self.equip_edges([CATEGORY,ENHANCEMENT],{CATEGORY:'신체',ENHANCEMENT:[['육상','집중']]})
        for _ in range(2):items.register_feats(self.e,self.a)
        r=self.roll(fixed=[1]*5)
        self.assertEqual((r.modifier,r.total),(3,8))
        self.assertTrue(any(CATEGORY in line for line in self.e.log_lines))
        self.assertTrue(any(ENHANCEMENT in line for line in self.e.log_lines))
        self.a.spec['edges']=[]
        self.a.spec['edge_choices']={}
        self.assertEqual(self.roll(fixed=[1]*5).total,5)
    def test_team_and_assistance_are_explicit_distinct_cooperation_modes(self):
        self.equip_edges([ENHANCEMENT],{ENHANCEMENT:[['육상','집중']]})
        team=self.e.common_action(skill='육상',dc=6,mode='team',participants=[self.a,self.b],
            required_people=2,equal_contribution=True,no_main_actor=True,
            participant_options=[{'fixed':[1]*5},{'fixed':[2]*3}])
        assist=self.e.common_action(self.a,'육상',6,mode='skill',helper=self.b,fixed=[1]*5)
        solo=self.e.common_action(self.a,'육상',6,mode='skill',fixed=[1]*5)
        self.assertEqual((team.check.total,team.check.dc),(13,12))
        self.assertEqual((assist.check.total,assist.check.dc),(8,6))
        self.assertEqual((solo.check.total,solo.check.dc),(7,6))
        pending=self.e.common_action(skill='육상',dc=6,mode='team',participants=[self.a,self.b],
            required_people=2,equal_contribution=False,no_main_actor=False)
        self.assertIsNone(pending.check)
    def test_signed_margin_is_preserved_for_gm_description(self):
        for dc,margin,description in [(16,-1,'거의 건넜지만 끝에서 추락'),(15,0,'간신히 건넘'),(7,8,'여유 있게 건넘')]:
            pending=self.e.common_action(self.a,'육상',dc,mode='skill',fixed=[3]*5)
            self.assertIsInstance(pending,C.PendingDecision)
            self.assertEqual(pending.check.margin,margin)
            out=C.adjudicate(pending.check,outcome='failure' if margin<0 else 'success',description=description)
            self.assertEqual((out.check.margin,out.description),(margin,description))
    def test_large_success_never_fabricates_a_reward(self):
        for margin in (4,5,20):
            p=self.e.common_action(self.a,'통찰',30-margin,mode='skill',fixed=[6]*5)
            self.assertIsInstance(p,C.PendingDecision)
            self.assertEqual(p.check.margin,margin)
            for description in ('숨겨진 스위치만 발견','스위치와 최근 사용 흔적 발견'):
                out=C.adjudicate(p.check,outcome='success',description=description)
                self.assertEqual(out.description,description)
        self.assertEqual(self.a.hp,self.a.max_hp)
    def extended(self,**kw):
        args=dict(task_id='연구',interval_id='1',interval={'amount':1,'unit':'day'},
             interval_completed=True,complexity=2,limited=False,fixed=[1]*5)
        args.update(kw)
        return self.e.common_action(self.a,'육상',20,mode='extended',**args)
    def test_interval_units_are_gm_chosen_and_one_roll_per_confirmed_interval(self):
        for amount,unit in [(5,'minute'),(1,'day'),(1,'week')]:
            task=unit
            before_seconds=self.e.elapsed_seconds
            first=self.extended(task_id=task,interval={'amount':amount,'unit':unit})
            self.assertEqual(first.result.attempts_used,1)
            self.assertEqual(self.e.elapsed_seconds-before_seconds,amount*{'minute':60,'day':86400,'week':604800}[unit])
            self.assertEqual(self.e._extended_checks[task]['basis']['interval'],{'amount':amount,'unit':unit})
            before=self.e.rng.getstate()
            pending=self.extended(task_id=task,interval_id='2',interval={'amount':amount,'unit':unit},interval_completed=False)
            self.assertIsInstance(pending,C.PendingDecision)
            self.assertEqual(self.e.rng.getstate(),before)
            self.assertEqual(self.e._extended_checks[task]['result'].attempts_used,1)
            with self.assertRaises(ValueError):self.extended(task_id=task,interval={'amount':amount,'unit':unit})
    def test_extended_modifiers_and_ownership_changes_require_new_ruling(self):
        self.equip_edges([ENHANCEMENT],{ENHANCEMENT:[['육상','집중']]})
        self.assertEqual(self.extended().result.total,7)
        self.a.spec['edge_choices'][ENHANCEMENT]=[['통찰','집중']]
        self.unchanged_rejection(lambda:self.extended(interval_id='2'))
    def test_penalty_dice_keep_task_dc_and_original_pool(self):
        p=self.e.common_action(self.a,'육상',12,mode='skill',fixed=[3]*5,
            penalty_count=2,fixed_penalties=[2,4])
        self.assertEqual((p.check.dc,p.check.total,p.check.margin),(12,9,-3))
        r=self.roll(fixed=[3]*5,penalty_count=2,fixed_penalties=[2,4])
        self.assertEqual((len(r.faces),r.penalties),(5,(2,4)))
    def test_penalties_at_or_above_rank_still_allow_attempt_and_success(self):
        self.a.spec['skills']={'육상':1}
        for penalties in ([1],[1,1]):
            p=self.e.common_action(self.a,'육상',4,mode='skill',fixed=[6],
                penalty_count=len(penalties),fixed_penalties=penalties)
            self.assertTrue(p.check.passed)
            self.assertEqual(p.check.total,6-len(penalties))
        p=self.e.common_action(self.a,'육상',1,mode='skill',fixed=[1],penalty_count=3,fixed_penalties=[6]*3)
        self.assertEqual(p.check.total,-17)
        self.assertFalse(p.check.passed)
    def test_penalties_consume_separate_rng_draws_after_all_validation(self):
        oracle=random.Random(937)
        faces=tuple(oracle.randint(1,6) for _ in range(5))
        penalties=tuple(oracle.randint(1,6) for _ in range(6))
        r=self.roll(penalty_count=6)
        self.assertEqual((r.faces,r.penalties),(faces,penalties))
        self.assertEqual(self.e.rng.getstate(),oracle.getstate())
        self.unchanged_rejection(lambda:self.roll(penalty_count=2,fixed_penalties=[7,1]))

if __name__=='__main__':
    class Result(unittest.TextTestResult):
        def __init__(self,*a,**kw):super().__init__(*a,**kw);self.rows=[]
        def addSuccess(self,t):super().addSuccess(t);self.rows.append({'id':t._testMethodName,'status':'pass'})
        def addFailure(self,t,e):super().addFailure(t,e);self.rows.append({'id':t._testMethodName,'status':'fail'})
        def addError(self,t,e):super().addError(t,e);self.rows.append({'id':t._testMethodName,'status':'error'})
    result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(Category3SkillTests))
    files=['engine/adjudication_guidance.py','data/adjudication-guidance.json','engine/skill_maneuver_actions.py','engine/food_effects.py','engine/combat_social_edges.py','engine/net_capsule.py','engine/trainer_capabilities.py','engine/skill_feature_actions.py','engine/researcher_features.py','engine/precise_actions.py','engine/environmental_effects.py','engine/wild_equipment.py','engine/injury_recovery.py','engine/downtime.py','engine/gm_state.py','engine/heavy_injury_adapter.py','engine/jump_actions.py','engine/context_actions.py','engine/pokemon_requests.py','engine/combat_timing.py','engine/combat_maneuvers.py','data/context-check-policy.json','data/cultivation-policy.json','engine/movement_actions.py','engine/weapon_actions.py','data/weapon-policy.json','engine/bandages.py','engine/crafting_activities.py','engine/contest_features.py','data/planter-policy.json','engine/capability_actions.py','engine/physical_limits.py','data/capability-policy.json','engine/temporary_hp.py','engine/engine.py','engine/ap_roll_bonus.py','engine/skill_modifiers.py','engine/common_action_checks.py','engine/common_checks.py',
       'engine/resolution_transaction.py','engine/ruleset.py','engine/rulings.py','engine/items.py',
       'data/skill-check-policy.json','data/core-rules.json','data/lookup-tables.json','data/rulesets.json',
       'data/edges-llm.json','data/edges-reviewed.json','output/ruleunits.jsonl',
       'input/ch03-skills-edges-feats.md','input/ch06-gameplay.md','input/ch11-running-the-game.md',
       'tools/test_category3_skill_modifiers.py']
    files += ['engine/campaign_rewards.py', 'engine/league_consequences.py', 'data/campaign-reward-policy.json']
    files += ['engine/pokemon_understanding.py', 'engine/regional_pokemon.py', 'engine/source_context.py']
    files += ['engine/blessing_skill_features.py', 'engine/combat_precision_features.py', 'engine/pokemon_intelligence.py', 'engine/pokemon_party.py', 'engine/pokemon_teaching.py', 'data/pokemon-machines.json']

    files += ['engine/arithmetic.py', 'engine/arithmetic_policy.py', 'engine/effect_contracts.py', 'engine/effect_lifetimes.py', 'engine/maneuver_grants.py', 'engine/move_activation.py', 'engine/native_rule_policy.py', 'data/native-rule-policy.json']

    files += ['engine/action_lifecycle.py', 'engine/action_metadata.py', 'engine/action_points.py', 'engine/adjudication_guidance.py', 'engine/ap_roll_bonus.py', 'engine/bandages.py', 'engine/bound_ap.py', 'engine/builder.py', 'engine/capability_actions.py', 'engine/combat_maneuvers.py', 'engine/combat_social_edges.py', 'engine/combat_stage_sources.py', 'engine/combat_timing.py', 'engine/common_action_checks.py', 'engine/common_checks.py', 'engine/contest.py', 'engine/contest_features.py', 'engine/context_actions.py', 'engine/crafting_activities.py', 'engine/custom_species.py', 'engine/damage_reactions.py', 'engine/demo_rulings.py', 'engine/downtime.py', 'engine/effects.py', 'engine/effects_ext.py', 'engine/elemental_connection.py', 'engine/encounter.py', 'engine/enduring_awareness.py', 'engine/engine.py', 'engine/environmental_effects.py', 'engine/focus_tasks.py', 'engine/food_effects.py', 'engine/frequency.py', 'engine/gm_console.py', 'engine/gm_state.py', 'engine/grid.py', 'engine/heavy_injury_adapter.py', 'engine/heavy_injury_kernel.py', 'engine/heavy_standard_adapter.py', 'engine/initiative.py', 'engine/injury_recovery.py', 'engine/items.py', 'engine/jump_actions.py', 'engine/league_agenda.py', 'engine/league_runtime.py', 'engine/life.py', 'engine/maneuver_edges.py', 'engine/movement_actions.py', 'engine/net_capsule.py', 'engine/observed_resolution.py', 'engine/passive_event_profiles.py', 'engine/passive_events.py', 'engine/physical_limits.py', 'engine/physics_maneuvers.py', 'engine/pokemon_activities.py', 'engine/pokemon_requests.py', 'engine/precise_actions.py', 'engine/researcher_features.py', 'engine/resolution_transaction.py', 'engine/rest_intervals.py', 'engine/restorative_items.py', 'engine/root_admission.py', 'engine/root_children.py', 'engine/root_common_checks.py', 'engine/root_common_engine.py', 'engine/root_inputs.py', 'engine/root_machine.py', 'engine/root_resolution.py', 'engine/root_scheduler.py', 'engine/ruleset.py', 'engine/rulings.py', 'engine/skill_feature_actions.py', 'engine/skill_maneuver_actions.py', 'engine/skill_modifiers.py', 'engine/skill_stunts.py', 'engine/skill_targets.py', 'engine/survivalist_features.py', 'engine/temporary_hp.py', 'engine/test_builder.py', 'engine/test_contest.py', 'engine/test_downtime.py', 'engine/test_effects.py', 'engine/test_gm_state.py', 'engine/test_grid.py', 'engine/test_items.py', 'engine/test_maintenance.py', 'engine/test_playthrough.py', 'engine/test_rules.py', 'engine/test_ruleset.py', 'engine/test_rulings.py', 'engine/test_turn.py', 'engine/trainer_capabilities.py', 'engine/turn.py', 'engine/weapon_actions.py', 'engine/wild_equipment.py', 'data/content-source-identities.json', 'data/context-check-policy.json', 'data/skill-check-policy.json', 'data/adjudication-guidance.json', 'data/rulesets.json']
    report={'generated_at':datetime.now(timezone.utc).isoformat(),'successful':result.wasSuccessful(),
        'scope':CLAUSES,'results':result.rows,'input_hashes':{f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files}}
    (ROOT/'output/category3-skill-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    raise SystemExit(0 if result.wasSuccessful() else 1)

