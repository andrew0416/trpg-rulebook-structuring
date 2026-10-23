"""EX014 source-complete additional Focus and actual opposed/precision paths."""
from pathlib import Path
from copy import deepcopy
from datetime import datetime,timezone
import hashlib,json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from engine import Engine,Rules,Combatant
import common_checks as C
import skill_feature_actions as SF
import test_category3_combat_next as _fixture_test_category3_combat_next
class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(ROOT)
 def setUp(self):
  self.e=Engine(self.r,seed=73);self.a=self.actor('a');self.b=self.actor('b');self.e.everyone=[self.a,self.b]
 def actor(self,name):return Combatant(self.r,{'id':'trainer/'+name,'name':name,'kind':'trainer','level':20,'stats':dict(hp=20,atk=5,**{'def':5},spa=5,spd=5,spe=5),'skills':{'은신':3,'집중':4,'육상':4,'곡예':4,'협박':3},'feats':[SF.MONKEY]})
 def focus(self,**options):
  defaults={'mode':'focus_task','context':{'kind':'stressful','purpose':'poisoned lock picking','focus_reason':'pain disrupts fine hand control'},'focus_dc':12,'task_options':{'fixed':[4]*3},'focus_options':{'fixed':[3]*4}};defaults.update(options)
  return self.e.common_action(self.a,'은신',12,**defaults)
 def opposed(self,case,**options):
  defaults={'mode':'context','case':case,'context':{'purpose':'GM specified actual influence','supernatural_mental_influence':True,'emotional_duress':True},'target':self.b,'defender_role':'status_quo','challenger_options':{'fixed':[3]*4},'defender_options':{'fixed':[3]*4}};defaults.update(options)
  return self.e.common_action(self.a,**defaults)
 def featured(self,uid,**updates):
  out={'roll_id':uid,'fixed':[1]*4,'feature':SF.MONKEY,'feature_options':{'decision':lambda first:True,'reroll_faces':[3]*4}};out.update(updates);return out
 def test_extra_focus_is_separate_not_replacement_or_sum(self):
  out=self.focus();self.assertIsInstance(out,C.PendingDecision);self.assertIsNone(out.check)
  self.assertEqual((out.basis['task_roll'].rank,out.basis['focus_roll'].rank),(3,4));self.assertEqual(out.basis['task_check'].total,12);self.assertEqual(out.basis['focus_check'].total,12)
  self.assertTrue(out.basis['task_check'].passed);self.assertTrue(out.basis['focus_check'].passed)
 def test_two_gm_dcs_preserve_different_successes_without_precision_penalty(self):
  out=self.focus(focus_dc=13);self.assertTrue(out.basis['task_check'].passed);self.assertFalse(out.basis['focus_check'].passed);self.assertEqual(out.basis['task_roll'].modifier,0);self.assertNotIn('focus_penalty',out.basis)
 def test_complex_task_and_explicit_world_response_preserve_both_checks(self):
  out=self.focus(context={'kind':'complex','purpose':'pull lever at landing instant','focus_reason':'coordinate movement and timing'},outcome='success',description='GM confirms lever moved on landing')
  self.assertIsInstance(out,C.ActionOutcome);self.assertEqual(out.outcome,'success');self.assertIn('focus_check',out.basis)
 def test_missing_context_or_dc_never_rolls(self):
  before=self.e.rng.getstate()
  for options in [{'focus_dc':None},{'context':None},{'context':{'kind':'complex','purpose':'jump'}},{'context':{'kind':'other','purpose':'jump','focus_reason':'timing'}}]:self.assertIsInstance(self.focus(**options),C.PendingDecision)
  self.assertEqual(self.e.rng.getstate(),before)
 def test_combat_precision_is_explicit_distinct_procedure(self):
  before=self.e.rng.getstate();out=self.focus(context={'kind':'stressful','purpose':'fine repair under attack','focus_reason':'incoming blow','delicate_in_combat':True})
  self.assertIsInstance(out,C.PendingDecision);self.assertNotIn('task_roll',out.basis or {});self.assertEqual(self.e.rng.getstate(),before)
 def test_invalid_second_roll_is_transactional(self):
  state=self.e.rng.getstate();logs=list(self.e.log_lines)
  with self.assertRaises(ValueError):self.focus(task_options={},focus_options={'fixed':[1]})
  self.assertEqual(self.e.rng.getstate(),state);self.assertEqual(self.e.log_lines,logs)
 def test_observed_task_is_not_repeated_after_later_focus_choice_error(self):
  self.a.spec['skills']['은신']=4
  options={'task_options':self.featured('task'),'focus_options':self.featured('focus',feature_options={'decision':lambda first:'invalid'})}
  with self.assertRaises(ValueError):self.focus(**options)
  first=SF.event(self.e,self.a,'task').final;focus_first=SF.event(self.e,self.a,'focus').first
  options['focus_options']['feature_options']={'decision':lambda first:False};out=self.focus(**options)
  self.assertEqual(out.basis['task_roll'],first);self.assertEqual(out.basis['focus_roll'],focus_first)
  self.assertEqual(self.a.spec['frequency_state']['activations'][SF.MONKEY]['used'],1)
  with self.assertRaises(ValueError):self.focus(**options)
 def test_observed_focus_dc_cannot_change_on_resume(self):
  self.a.spec['skills']['은신']=4;options={'task_options':self.featured('task'),'focus_options':self.featured('focus',feature_options={'decision':lambda first:'invalid'})}
  with self.assertRaises(ValueError):self.focus(**options)
  options['focus_options']['feature_options']={'decision':lambda first:False}
  with self.assertRaises(ValueError):self.focus(focus_dc=11,**options)
 def test_each_added_roll_requires_own_identity(self):
  with self.assertRaises(ValueError):self.focus(task_options={'fixed':[4]*3,'roll_id':'same'},focus_options={'fixed':[3]*4,'roll_id':'same'})
 def test_mental_influence_uses_focus_on_both_sides_status_quo_tie(self):
  out=self.opposed('mental_influence');self.assertFalse(out.check.passed);self.assertEqual((out.check.total,out.check.dc),(12,12));self.assertEqual(out.basis['defender_skill'],'집중')
 def test_mental_influence_numerical_win_does_not_invent_control_effect(self):
  before=deepcopy(self.b.spec);out=self.opposed('mental_influence',challenger_options={'fixed':[4]*4})
  self.assertTrue(out.check.passed);self.assertIsInstance(out,C.PendingDecision);self.assertEqual(self.b.spec,before)
 def test_emotional_duress_uses_actual_intimidate_vs_focus(self):
  out=self.opposed('emotional_disruption',challenger_options={'fixed':[5]*3});self.assertEqual(out.basis['skill'],'협박');self.assertEqual((out.check.total,out.check.dc),(15,12))
 def test_missing_influence_context_never_rolls(self):
  state=self.e.rng.getstate();out=self.opposed('mental_influence',context={'purpose':'not established'})
  self.assertIsInstance(out,C.PendingDecision);self.assertEqual(state,self.e.rng.getstate())
 def test_no_opponent_intense_emotion_uses_focus_dc(self):
  out=self.e.common_action(self.a,dc=12,mode='context',case='self_control',context={'purpose':'remain calm in fire','intense_emotion':True},fixed=[3]*4)
  self.assertTrue(out.check.passed);self.assertNotIn('defender_roll',out.basis)
 def test_fixed_full_scope_snapshot_matches(self):
  row=next(r for r in json.loads((ROOT/'data/verification/category3-register.json').read_text(encoding='utf-8'))['entries'] if r['id']=='C3-EX-014');self.assertEqual(row['scope_sha256'],'489bcf77ffbe65e4a5c17557fc810dc29e23a72c081ce026d110a463360dbf0f')
  for a in row['source_snapshot']['source_anchors']:
   excerpt='\n'.join((ROOT/a['file']).read_text(encoding='utf-8-sig').splitlines()[a['start_line']-1:a['end_line']]);self.assertEqual(excerpt,a['excerpt']);self.assertEqual(hashlib.sha256(excerpt.encode()).hexdigest(),a['excerpt_sha256'])
if __name__=='__main__':
 class Result(unittest.TextTestResult):
  def __init__(self,*a,**kw):super().__init__(*a,**kw);self.rows=[]
  def addSuccess(self,t):super().addSuccess(t);self.rows.append({'id':t._testMethodName,'status':'pass'})
  def addFailure(self,t,e):super().addFailure(t,e);self.rows.append({'id':t._testMethodName,'status':'fail'})
  def addError(self,t,e):super().addError(t,e);self.rows.append({'id':t._testMethodName,'status':'error'})
 suite=unittest.defaultTestLoader.loadTestsFromTestCase(Tests)
 for name in unittest.defaultTestLoader.getTestCaseNames(_fixture_test_category3_combat_next.CombatTests):
  if name.startswith('test_precision_'):suite.addTest(_fixture_test_category3_combat_next.CombatTests(name))
 result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(suite)
 paths=sorted(str(p.relative_to(ROOT)).replace('\\','/') for p in (ROOT/'engine').glob('*.py'))+['input/ch03-skills-edges-feats.md','input/ch07-combat.md','tools/test_category3_focus_scope.py','tools/test_category3_combat_next.py','data/context-check-policy.json','data/skill-check-policy.json','data/adjudication-guidance.json']
 paths += ['engine/campaign_rewards.py', 'engine/league_consequences.py', 'data/campaign-reward-policy.json']
 paths += ['engine/pokemon_understanding.py', 'engine/regional_pokemon.py', 'engine/source_context.py']
 paths += ['engine/blessing_skill_features.py', 'engine/combat_precision_features.py', 'engine/pokemon_intelligence.py', 'engine/pokemon_party.py', 'engine/pokemon_teaching.py', 'data/pokemon-machines.json']

 paths += ['engine/arithmetic.py', 'engine/arithmetic_policy.py', 'engine/effect_contracts.py', 'engine/effect_lifetimes.py', 'engine/maneuver_grants.py', 'engine/move_activation.py', 'engine/native_rule_policy.py', 'data/native-rule-policy.json']

 paths += ['engine/action_lifecycle.py', 'engine/action_metadata.py', 'engine/action_points.py', 'engine/adjudication_guidance.py', 'engine/ap_roll_bonus.py', 'engine/bandages.py', 'engine/bound_ap.py', 'engine/builder.py', 'engine/capability_actions.py', 'engine/combat_maneuvers.py', 'engine/combat_social_edges.py', 'engine/combat_stage_sources.py', 'engine/combat_timing.py', 'engine/common_action_checks.py', 'engine/common_checks.py', 'engine/contest.py', 'engine/contest_features.py', 'engine/context_actions.py', 'engine/crafting_activities.py', 'engine/custom_species.py', 'engine/damage_reactions.py', 'engine/demo_rulings.py', 'engine/downtime.py', 'engine/effects.py', 'engine/effects_ext.py', 'engine/elemental_connection.py', 'engine/encounter.py', 'engine/enduring_awareness.py', 'engine/engine.py', 'engine/environmental_effects.py', 'engine/focus_tasks.py', 'engine/food_effects.py', 'engine/frequency.py', 'engine/gm_console.py', 'engine/gm_state.py', 'engine/grid.py', 'engine/heavy_injury_adapter.py', 'engine/heavy_injury_kernel.py', 'engine/heavy_standard_adapter.py', 'engine/initiative.py', 'engine/injury_recovery.py', 'engine/items.py', 'engine/jump_actions.py', 'engine/league_agenda.py', 'engine/league_runtime.py', 'engine/life.py', 'engine/maneuver_edges.py', 'engine/movement_actions.py', 'engine/net_capsule.py', 'engine/observed_resolution.py', 'engine/passive_event_profiles.py', 'engine/passive_events.py', 'engine/physical_limits.py', 'engine/physics_maneuvers.py', 'engine/pokemon_activities.py', 'engine/pokemon_requests.py', 'engine/precise_actions.py', 'engine/researcher_features.py', 'engine/resolution_transaction.py', 'engine/rest_intervals.py', 'engine/restorative_items.py', 'engine/root_admission.py', 'engine/root_children.py', 'engine/root_common_checks.py', 'engine/root_common_engine.py', 'engine/root_inputs.py', 'engine/root_machine.py', 'engine/root_resolution.py', 'engine/root_scheduler.py', 'engine/ruleset.py', 'engine/rulings.py', 'engine/skill_feature_actions.py', 'engine/skill_maneuver_actions.py', 'engine/skill_modifiers.py', 'engine/skill_stunts.py', 'engine/skill_targets.py', 'engine/survivalist_features.py', 'engine/temporary_hp.py', 'engine/test_builder.py', 'engine/test_contest.py', 'engine/test_downtime.py', 'engine/test_effects.py', 'engine/test_gm_state.py', 'engine/test_grid.py', 'engine/test_items.py', 'engine/test_maintenance.py', 'engine/test_playthrough.py', 'engine/test_rules.py', 'engine/test_ruleset.py', 'engine/test_rulings.py', 'engine/test_turn.py', 'engine/trainer_capabilities.py', 'engine/turn.py', 'engine/weapon_actions.py', 'engine/wild_equipment.py', 'data/content-source-identities.json', 'data/context-check-policy.json', 'data/skill-check-policy.json', 'data/adjudication-guidance.json', 'data/rulesets.json']
 report={'generated_at':datetime.now(timezone.utc).isoformat(),'successful':result.wasSuccessful(),'scope':['C3-EX-014'],'completion_scopes':['C3-EX-014'],'partial_scopes':[],'source_scope_sha256':'489bcf77ffbe65e4a5c17557fc810dc29e23a72c081ce026d110a463360dbf0f','results':result.rows,'input_hashes':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}}
 (ROOT/'output/category3-focus-scope-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 raise SystemExit(not result.wasSuccessful())
