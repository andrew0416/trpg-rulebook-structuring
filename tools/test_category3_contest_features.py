"""C3-EX-061: native Style Flourish, including acquisition, choice and lifetime."""
from copy import deepcopy
from datetime import datetime,timezone
import hashlib,json,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from contest import ContestEngine,ContestRules
from engine import Engine,Rules,Combatant
from ruleset import RuleFilter,ExcludedRuleSelection
import action_points as AP
import contest_features as F
class Sequence:
 def __init__(self,faces):self.faces=list(faces)
 def randint(self,a,b):return self.faces.pop(0)
class Ones:
 def randint(self,a,b):return 1
class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.nr=Rules(ROOT);cls.cr=ContestRules(ROOT)
 def setUp(self):
  self.native=Engine(self.nr);self.e=ContestEngine(self.cr);self.e.rng=Ones()
  self.ts=[];self.ps=[];self.cs=[]
  for i in range(3):
   common={'level':25,'stats':dict.fromkeys(['hp','atk','def','spa','spd','spe'],10),'moves':['연속자르기','헤롱헤롱']}
   t=Combatant(self.nr,dict(common,id=f't{i}',name=f'T{i}',kind='trainer',skills={'명령':'전문','매력':'초보'},classes=['class/코디네이터',F.STYLE],edges=['edge/우아함'],feats=['feat/근사한-행위',F.FLOURISH],feat_ranks={'feat/근사한-행위':2},feature_choices={F.STYLE:['근사함'],F.FLOURISH:['근사함']}))
   p=Combatant(self.nr,dict(common,id=f'p{i}',name=f'P{i}',kind='pokemon',trainer_id=f't{i}',poffins=['근사함']*3))
   self.ts.append(t);self.ps.append(p)
   self.cs.append(self.e.contestant_from_combatants(self.native,p,t,'매력',{'근사함':4}))
  self.native.everyone=[*self.ts,*self.ps]
 def use(self,**kw):
  opts=dict(fixed_rolls=[1,2,1,6],flourish_decision=lambda first:True);opts.update(kw)
  return self.e.perform(self.cs[0],'연속자르기','근사함',[],False,**opts)
 def test_source_scope_and_inherited_prerequisites_are_recorded(self):
  row=next(r for r in json.loads((ROOT/'data/verification/category3-register.json').read_text(encoding='utf-8'))['entries'] if r['id']=='C3-EX-061')
  self.assertEqual(row['scope_sha256'],'6a0fa28733956c1d4f985a8d6162f2d54910d5e32e8e845afe04f14ca73c7db4')
  anchor=row['source_snapshot']['source_anchors'][0];lines=(ROOT/anchor['file']).read_text(encoding='utf-8-sig').splitlines();excerpt='\n'.join(lines[anchor['start_line']-1:anchor['end_line']])
  self.assertEqual(hashlib.sha256(excerpt.encode()).hexdigest(),anchor['excerpt_sha256'])
  source=(ROOT/'input/ch03-skills-edges-feats.md').read_text(encoding='utf-8')
  for phrase in ('“기본” 재주는 이 합계를 계산','각 랭크를 계산','매번 다른 전문화'):self.assertIn(phrase,source)
 def test_only_initial_ones_reroll_once_and_final_faces_score(self):
  self.e.rng=Sequence([1,6,4]);before=AP.available(self.ts[0]);seen=[]
  self.use(flourish_decision=lambda first:seen.append(first) or True)
  self.assertEqual(seen[0]['rolls'],(1,2,1,6));self.assertEqual(self.e.rng.faces,[4])
  self.assertEqual((self.cs[0].appeal,self.cs[0].fumble),(5,0))
  self.assertEqual(AP.available(self.ts[0]),before-1);self.assertEqual(self.ts[0]._action_history,['free'])
  self.assertEqual(len(self.e._flourish_used),1)
 def test_decline_keeps_ap_and_use_and_second_use_is_rejected(self):
  self.use(flourish_decision=lambda first:False)
  self.assertFalse(self.e._flourish_used);self.assertNotIn('ap_spent',self.ts[0].spec)
  self.use(fixed_rolls=[1]*5)
  self.assertEqual(self.ts[0].spec['ap_spent'],1)
  snapshot=deepcopy(vars(self.cs[0]))
  with self.assertRaises(ValueError):self.use(fixed_rolls=[1]*6)
  self.assertEqual(vars(self.cs[0]),snapshot);self.assertEqual(self.ts[0].spec['ap_spent'],1)
 def test_native_run_preserves_center_faces_and_one_use_for_trainer_and_pokemon(self):
  partner=self.e.trainer_participant(self.cs[0]);seen=[]
  for c in self.cs[1:]:self.e.trainer_participant(c)
  def choose(actor,rnd,adj,center):
   if actor is partner and rnd==1:return '연속자르기',0,{'flourish_decision':lambda first:seen.append(first) or True}
   return '연속자르기',0
  self.e.run(self.cs,'근사함',choose,trainer_model='simultaneous',trainer_order=lambda c,t,r:[t,c])
  self.assertEqual(len(seen),1);self.assertEqual(self.ts[0].spec['ap_spent'],1)
  self.assertTrue(seen[0]['center']);self.assertEqual(partner.fumble,4)
  with self.assertRaises(ValueError):self.use(fixed_rolls=None)
 def test_rank_and_base_count_and_three_pokemon_alternative(self):
  t=self.ts[0];p=self.ps[0]
  self.assertEqual(F.style_feature_count(self.native,t,F.style_expert(self.native,t)),4)
  t.spec['feat_ranks']['feat/근사한-행위']=1;t.spec['feats'].append('feat/근사함의-규칙')
  self.assertEqual(F.style_feature_count(self.native,t,F.style_expert(self.native,t)),4)
  t.spec['classes'].remove('class/코디네이터');t.spec['edges']=[]
  for i in (1,2):self.ps[i].spec['trainer_id']=t.spec['id']
  self.use()
  self.assertEqual(t.spec['ap_spent'],1)
 def test_invalid_source_prerequisites_type_ap_and_ownership_before_roll(self):
  changes=[lambda t,p:t.spec['feats'].remove(F.FLOURISH),lambda t,p:t.spec['classes'].remove(F.STYLE),lambda t,p:t.spec['feat_ranks'].update({'feat/근사한-행위':1}),lambda t,p:t.spec['skills'].update({'명령':'초보'}),lambda t,p:p.spec.update(poffins=['근사함']*2),lambda t,p:p.spec.update(trainer_id='other'),lambda t,p:t.spec['feature_choices'].update({F.FLOURISH:['귀여움']}),lambda t,p:t.spec.update(ap_spent=AP.maximum(t))]
  for change in changes:
   with self.subTest(change=changes.index(change)):
    self.setUp();change(self.ts[0],self.ps[0]);before=deepcopy(vars(self.cs[0]));native=deepcopy(self.ts[0].spec)
    with self.assertRaises(ValueError):self.use()
    self.assertEqual(vars(self.cs[0]),before);self.assertEqual(self.ts[0].spec,native);self.assertFalse(self.e._flourish_used)
  self.setUp()
  with self.assertRaises(ValueError):self.e.perform(self.cs[0],'헤롱헤롱','귀여움',[],False,flourish_decision=lambda first:True)
 def test_observed_choice_error_keeps_original_move_but_preflight_error_does_not_roll(self):
  import observed_resolution as OBS
  for mode in ('sleep','decision','bad_reroll'):
   with self.subTest(mode=mode):
    self.setUp();self.e.rng=Sequence([0 if mode=='bad_reroll' else 6,6]);before=deepcopy(vars(self.cs[0]));native=deepcopy(self.ts[0].spec)
    if mode=='sleep':self.ts[0].conditions.add('잠듦')
    decision=(lambda first:'yes') if mode=='decision' else (lambda first:True)
    rng_before=self.e.rng.faces[:]
    with self.assertRaises(ValueError):self.use(flourish_decision=decision)
    self.assertEqual(self.ts[0].spec,native);self.assertEqual(self.e.rng.faces,rng_before);self.assertFalse(self.e._flourish_used)
    if mode=='sleep':self.assertEqual(vars(self.cs[0]),before);self.assertFalse(self.e.log_lines);continue
    self.assertEqual(self.cs[0].last_move,'move/연속자르기');self.assertEqual(self.cs[0].appeal,0)
    observed=next(iter(self.e._performance_observations.values()))[OBS.KEY];self.assertEqual(observed['state'],'pending')
    self.use(flourish_decision=lambda first:False)
    self.assertEqual((self.cs[0].appeal,self.cs[0].fumble),self.e.score([1,2,1,6],False));self.assertEqual(observed['state'],'complete');self.assertEqual(self.e.rng.faces,rng_before)
 def test_branch_uses_are_distinct_and_different_types_keep_their_trigger(self):
  t=self.ts[0];p=self.ps[0]
  t.spec['feature_choices']={F.STYLE:['근사함','귀여움'],F.FLOURISH:['근사함','귀여움']}
  p.spec['poffins']=['근사함']*3+['귀여움']*3
  self.use()
  self.e.perform(self.cs[0],'헤롱헤롱','귀여움',[],False,fixed_rolls=[1]*4,flourish_decision=lambda first:True)
  self.assertEqual(len(self.e._flourish_used),2);self.assertEqual(t.spec['ap_spent'],2)
 def test_all_style_branches_validate_their_ranked_skill_prerequisite(self):
  for stat,(ranked,skill,children) in F.RANKED.items():
   with self.subTest(stat=stat):
    self.setUp();t=self.ts[0];p=self.ps[0]
    t.spec['feature_choices']={F.STYLE:[stat],F.FLOURISH:[stat]}
    t.spec['feats']=[ranked,F.FLOURISH];t.spec['feat_ranks']={ranked:2};t.spec['skills']={skill:'전문'};p.spec['poffins']=[stat]*3
    self.assertEqual(F.flourish(self.native,t,p,stat),(F.FLOURISH,stat))
    t.spec['skills']={skill:'숙련'}
    with self.assertRaises(ValueError):F.flourish(self.native,t,p,stat)
 def test_final_flourish_faces_alone_drive_face_triggered_voltage(self):
  t=self.ts[0];p=self.ps[0];c=self.cs[0]
  t.spec['feature_choices']={F.STYLE:['슬기로움'],F.FLOURISH:['슬기로움']}
  t.spec['feats']=['feat/슬기로운-계획',F.FLOURISH];t.spec['feat_ranks']={'feat/슬기로운-계획':2};t.spec['skills']={'교활':'전문'}
  p.spec['poffins']=['슬기로움']*3;p.moves=['move/엉겨붙기'];c.moves=p.moves
  self.e.rng=Sequence([6,1,4])
  self.e.perform(c,'move/엉겨붙기','슬기로움',[],False,fixed_rolls=[1,1,2],flourish_decision=lambda first:True)
  self.assertEqual((c.appeal,c.fumble,c.excitement),(3,0,1));self.assertEqual(self.e.rng.faces,[4])
 def test_contest_profile_exclusions_include_acquisition_dependency(self):
  for uid in (F.FLOURISH,F.STYLE,'feat/근사한-행위','class/코디네이터','edge/우아함'):
   with self.subTest(uid=uid):
    self.e.r=ContestRules(ROOT,RuleFilter({'exclude_units':[uid]}))
    with self.assertRaises(ExcludedRuleSelection):self.use()
    self.assertFalse(self.e.log_lines);self.assertFalse(self.e._flourish_used)
if __name__=='__main__':
 class Result(unittest.TextTestResult):
  def __init__(self,*a,**kw):super().__init__(*a,**kw);self.rows=[]
  def addSuccess(self,t):super().addSuccess(t);self.rows.append({'id':t._testMethodName,'status':'pass'})
  def addFailure(self,t,e):super().addFailure(t,e);self.rows.append({'id':t._testMethodName,'status':'fail'})
  def addError(self,t,e):super().addError(t,e);self.rows.append({'id':t._testMethodName,'status':'error'})
 result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
 paths=['engine/observed_resolution.py','engine/adjudication_guidance.py','data/adjudication-guidance.json','engine/skill_maneuver_actions.py','engine/food_effects.py','engine/combat_social_edges.py','engine/net_capsule.py','engine/trainer_capabilities.py','engine/skill_feature_actions.py','engine/researcher_features.py','engine/precise_actions.py','engine/environmental_effects.py','engine/wild_equipment.py','engine/injury_recovery.py','engine/downtime.py','engine/items.py','engine/common_action_checks.py','engine/gm_state.py','engine/jump_actions.py','engine/context_actions.py','engine/pokemon_requests.py','engine/combat_timing.py','engine/combat_maneuvers.py','data/context-check-policy.json','data/cultivation-policy.json','engine/movement_actions.py','engine/weapon_actions.py','data/weapon-policy.json','engine/bandages.py','engine/crafting_activities.py','data/planter-policy.json','tools/test_category3_contest_features.py','engine/contest.py','engine/contest_features.py','engine/engine.py','engine/ruleset.py','engine/skill_modifiers.py','engine/common_checks.py','engine/resolution_transaction.py','engine/action_points.py','engine/turn.py','engine/action_lifecycle.py','engine/action_metadata.py','engine/capability_actions.py','engine/physical_limits.py','engine/heavy_injury_adapter.py','data/capability-policy.json','data/skill-check-policy.json','data/lookup-tables.json','data/core-rules.json','data/contest-rules.json','data/conditions.json','data/rulesets.json','output/entities/moves.json','output/ruleunits.jsonl','input/ch03-skills-edges-feats.md','input/ch04-trainer-classes.md','input/ch08-contests.md','output/source-audit/2026-10-10/ptu-core-1.05.pdf']
 paths += ['engine/campaign_rewards.py', 'engine/league_consequences.py', 'data/campaign-reward-policy.json']
 paths += ['engine/pokemon_understanding.py', 'engine/regional_pokemon.py', 'engine/source_context.py']
 paths += ['engine/blessing_skill_features.py', 'engine/combat_precision_features.py', 'engine/pokemon_intelligence.py', 'engine/pokemon_party.py', 'engine/pokemon_teaching.py', 'data/pokemon-machines.json']

 paths += ['engine/arithmetic.py', 'engine/arithmetic_policy.py', 'engine/effect_contracts.py', 'engine/effect_lifetimes.py', 'engine/maneuver_grants.py', 'engine/move_activation.py', 'engine/native_rule_policy.py', 'data/native-rule-policy.json']

 paths += ['engine/action_lifecycle.py', 'engine/action_metadata.py', 'engine/action_points.py', 'engine/adjudication_guidance.py', 'engine/ap_roll_bonus.py', 'engine/bandages.py', 'engine/bound_ap.py', 'engine/builder.py', 'engine/capability_actions.py', 'engine/combat_maneuvers.py', 'engine/combat_social_edges.py', 'engine/combat_stage_sources.py', 'engine/combat_timing.py', 'engine/common_action_checks.py', 'engine/common_checks.py', 'engine/contest.py', 'engine/contest_features.py', 'engine/context_actions.py', 'engine/crafting_activities.py', 'engine/custom_species.py', 'engine/damage_reactions.py', 'engine/demo_rulings.py', 'engine/downtime.py', 'engine/effects.py', 'engine/effects_ext.py', 'engine/elemental_connection.py', 'engine/encounter.py', 'engine/enduring_awareness.py', 'engine/engine.py', 'engine/environmental_effects.py', 'engine/focus_tasks.py', 'engine/food_effects.py', 'engine/frequency.py', 'engine/gm_console.py', 'engine/gm_state.py', 'engine/grid.py', 'engine/heavy_injury_adapter.py', 'engine/heavy_injury_kernel.py', 'engine/heavy_standard_adapter.py', 'engine/initiative.py', 'engine/injury_recovery.py', 'engine/items.py', 'engine/jump_actions.py', 'engine/league_agenda.py', 'engine/league_runtime.py', 'engine/life.py', 'engine/maneuver_edges.py', 'engine/movement_actions.py', 'engine/net_capsule.py', 'engine/observed_resolution.py', 'engine/passive_event_profiles.py', 'engine/passive_events.py', 'engine/physical_limits.py', 'engine/physics_maneuvers.py', 'engine/pokemon_activities.py', 'engine/pokemon_requests.py', 'engine/precise_actions.py', 'engine/researcher_features.py', 'engine/resolution_transaction.py', 'engine/rest_intervals.py', 'engine/restorative_items.py', 'engine/root_admission.py', 'engine/root_children.py', 'engine/root_common_checks.py', 'engine/root_common_engine.py', 'engine/root_inputs.py', 'engine/root_machine.py', 'engine/root_resolution.py', 'engine/root_scheduler.py', 'engine/ruleset.py', 'engine/rulings.py', 'engine/skill_feature_actions.py', 'engine/skill_maneuver_actions.py', 'engine/skill_modifiers.py', 'engine/skill_stunts.py', 'engine/skill_targets.py', 'engine/survivalist_features.py', 'engine/temporary_hp.py', 'engine/test_builder.py', 'engine/test_contest.py', 'engine/test_downtime.py', 'engine/test_effects.py', 'engine/test_gm_state.py', 'engine/test_grid.py', 'engine/test_items.py', 'engine/test_maintenance.py', 'engine/test_playthrough.py', 'engine/test_rules.py', 'engine/test_ruleset.py', 'engine/test_rulings.py', 'engine/test_turn.py', 'engine/trainer_capabilities.py', 'engine/turn.py', 'engine/weapon_actions.py', 'engine/wild_equipment.py', 'data/content-source-identities.json', 'data/context-check-policy.json', 'data/skill-check-policy.json', 'data/adjudication-guidance.json', 'data/rulesets.json']
 report={'generated_at':datetime.now(timezone.utc).isoformat(),'successful':result.wasSuccessful(),'scope':['C3-EX-061'],'results':result.rows,'input_hashes':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths},'source_review':{'ptu_page':115,'inherited_prerequisite_lines':['ch03:576','ch03:607','ch03:609','ch04:1180-1188'],'battle_effect_outside_scope':'C3-EX-061 is explicitly the Contest effect at ch04:1188; ch04:1189 is not claimed.'}}
 (ROOT/'output/category3-contest-features-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 raise SystemExit(not result.wasSuccessful())
