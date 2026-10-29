"""Actual activity cost/observation resumption for Skill Monkey."""
from copy import deepcopy
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'));sys.path.insert(0,str(ROOT/'tools'))
import test_category3_pokemon_activities as _fixture_test_category3_pokemon_activities
from engine import Rules
import skill_feature_actions as SF
class ActivityFeatureTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(str(ROOT),ruleset='core')
 actor=_fixture_test_category3_pokemon_activities.PokemonActivityTests.actor
 act=_fixture_test_category3_pokemon_activities.PokemonActivityTests.act
 state=_fixture_test_category3_pokemon_activities.PokemonActivityTests.state
 own=_fixture_test_category3_pokemon_activities.PokemonActivityTests.own
 def setUp(self):_fixture_test_category3_pokemon_activities.PokemonActivityTests.setUp(self);self.a.spec['feats'].append(SF.MONKEY)
 def opts(self,rid='r',decision=None):return dict(roll_id=rid,fixed=[1]*4,feature=SF.MONKEY,feature_options={'decision':decision or (lambda first:True),'reroll_faces':[4]*4})
 def bad(self,rid='r'):return self.opts(rid,lambda first:'invalid')
 def used(self):return self.a.spec.get('frequency_state',{}).get('activations',{}).get(SF.MONKEY,{}).get('used',0)
 def test_standard_activity_observed_failure_resume_spends_action_only_once(self):
  self.own('maniac');self.a.budget={'standard':1,'shift':1,'swift':1}
  with self.assertRaises(ValueError):self.act('pokemaniac',target=self.p,**self.bad())
  self.assertEqual(self.a.budget['standard'],0);self.assertEqual(SF.event(self.e,self.a,'r').first.total,4);rng=self.e.rng.getstate();self.assertEqual(self.used(),0)
  r=self.act('pokemaniac',target=self.p,**self.opts());self.assertTrue(r['check'].passed);self.assertEqual(self.used(),1);self.assertEqual(self.e.rng.getstate(),rng);self.assertEqual(self.a._action_history.count('standard'),1)
  with self.assertRaises(ValueError):self.act('pokemaniac',target=self.p,**self.opts())
 def test_observed_activity_cannot_switch_target_action_or_fixed_first_roll(self):
  self.own('maniac')
  with self.assertRaises(ValueError):self.act('pokemaniac',target=self.p,**self.bad())
  before=self.state();self.q.spec['nature']='대담'
  with self.assertRaises(ValueError):self.act('pokemaniac',target=self.q,**self.opts())
  with self.assertRaises(ValueError):self.act('pokemon_interaction',target=self.p,skill='포켓몬학',dc=10,**self.opts())
  options=self.opts();options['fixed']=[2]*4
  with self.assertRaises(ValueError):self.act('pokemaniac',target=self.p,**options)
  self.assertEqual(before,self.state());self.assertEqual(self.used(),0)
 def test_breeding_keeps_first_four_hours_and_check_on_resume(self):
  self.own('breeder')
  with self.assertRaises(ValueError):self.act('breed',pair=[self.p,self.q],task_id='egg',phase='check',compatible=True,**self.bad())
  self.assertEqual(self.e.elapsed_seconds,14400);self.assertNotIn('breeding_tasks',self.a.spec)
  r=self.act('breed',pair=[self.p,self.q],task_id='egg',phase='check',compatible=True,**self.opts());self.assertTrue(r['check'].passed);self.assertEqual(self.e.elapsed_seconds,14400)
  self.act('breed',pair=[self.p,self.q],task_id='egg',phase='finish');self.assertEqual(self.e.elapsed_seconds,28800);self.assertEqual(len(self.a.spec['eggs']),1);self.assertEqual(self.used(),1)
 def test_breeding_task_identity_cannot_change_after_observation(self):
  self.own('breeder')
  with self.assertRaises(ValueError):self.act('breed',pair=[self.p,self.q],task_id='egg',phase='check',compatible=True,**self.bad())
  with self.assertRaises(ValueError):self.act('breed',pair=[self.p,self.q],task_id='other',phase='check',compatible=True,**self.opts())
  self.assertEqual(self.e.elapsed_seconds,14400)
 def test_fossil_search_keeps_paid_duration_and_discovery_identity(self):
  kw=dict(phase='search',site={'name':'site','fossils_present':True},dc=15,minutes=120,discovery={'id':'f','species':'pokemon/암나이트'})
  with self.assertRaises(ValueError):self.act('fossil',**kw,**self.bad())
  self.assertEqual(self.e.elapsed_seconds,7200)
  with self.assertRaises(ValueError):self.act('fossil',**{**kw,'minutes':121},**self.opts())
  r=self.act('fossil',**kw,**self.opts());self.assertTrue(r['check'].passed);self.assertEqual(self.e.elapsed_seconds,7200);self.assertEqual(self.a.spec['fossils']['f']['status'],'fossil')
 def test_befriend_failure_is_written_only_after_final_choice_then_blocks_retry(self):
  self.a.budget={'standard':1,'shift':1,'swift':1}
  with self.assertRaises(ValueError):self.act('befriend',target=self.p,**self.bad())
  self.assertNotIn('befriend_failures',self.p.spec)
  r=self.act('befriend',target=self.p,**self.opts(decision=lambda first:False));self.assertFalse(r['check'].passed);self.assertEqual(self.a._action_history.count('standard'),1);self.assertEqual(self.used(),0)
  with self.assertRaises(ValueError):self.act('befriend',target=self.p,**self.opts('second'))
 def test_repair_reroll_updates_actual_inventory_and_current_nested_records(self):
  _fixture_test_category3_pokemon_activities.PokemonActivityTests.repairable(self)
  r=self.act('repair_ball',ball_id='b1',**self.opts());self.assertTrue(r['check'].passed);self.assertEqual(self.a.spec['broken_balls']['b1']['status'],'repaired');self.assertEqual(self.a.spec['capture_attempts']['capture-1']['status'],'repaired');self.assertEqual(self.a.spec['items']['몬스터볼'],0)
  with self.assertRaises(ValueError):self.act('repair_ball',ball_id='b1',**self.opts('second'))
 def test_fossil_identify_and_fishing_reroll_write_current_owned_nested_records(self):
  self.own('paleontologist');self.a.spec['fossils']={'f':{'species':'pokemon/암나이트','status':'fossil'}}
  self.act('fossil',phase='identify',fossil_id='f',**self.opts());self.assertTrue(self.a.spec['fossils']['f']['identified'])
  self.a.spec['items'].update({'대단한낚싯대':1,'루어':1});self.act('fishing',phase='start',rod='대단한낚싯대',attachment='루어');self.act('fishing',phase='wait',roll_d20=15)
  self.act('fishing',phase='reel',target=self.p,**self.opts('fishing'));self.assertEqual(self.a.spec['fishing_session']['status'],'landed');self.assertEqual(self.a.spec['fishing_session']['target_id'],self.p.spec['id'])
 def test_invalid_feature_options_and_unavailable_action_have_no_observation_or_cost(self):
  self.own('maniac');self.a.budget={'standard':0,'shift':1,'swift':1};before=self.state()
  r=self.act('pokemaniac',target=self.p,**self.opts());self.assertEqual(type(r).__name__,'PendingDecision');self.assertEqual(before,self.state());self.assertIsNone(SF.event(self.e,self.a,'r'))
  self.own('breeder');options=self.opts();options['feature_options']['reroll_faces']=[1]
  with self.assertRaises(ValueError):self.act('breed',pair=[self.p,self.q],task_id='egg',phase='check',compatible=True,**options)
  self.assertEqual(self.e.elapsed_seconds,0)
if __name__=='__main__':
 class Result(unittest.TextTestResult):
  def __init__(self,*a,**kw):super().__init__(*a,**kw);self.rows=[]
  def addSuccess(self,t):super().addSuccess(t);self.rows.append({'id':t._testMethodName,'status':'pass'})
  def addFailure(self,t,e):super().addFailure(t,e);self.rows.append({'id':t._testMethodName,'status':'fail'})
  def addError(self,t,e):super().addError(t,e);self.rows.append({'id':t._testMethodName,'status':'error'})
 result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(ActivityFeatureTests))
 files=['engine/adjudication_guidance.py','data/adjudication-guidance.json','engine/skill_maneuver_actions.py','engine/food_effects.py','engine/combat_social_edges.py','engine/net_capsule.py','engine/trainer_capabilities.py','engine/researcher_features.py','engine/precise_actions.py','engine/environmental_effects.py','engine/injury_recovery.py','engine/downtime.py','engine/items.py','engine/common_action_checks.py','engine/gm_state.py','engine/heavy_injury_adapter.py','engine/jump_actions.py','engine/context_actions.py','engine/pokemon_requests.py','engine/combat_timing.py','engine/combat_maneuvers.py','data/context-check-policy.json','data/cultivation-policy.json','engine/pokemon_activities.py','engine/skill_feature_actions.py','engine/contest_features.py','engine/engine.py','engine/common_checks.py','engine/skill_modifiers.py','engine/turn.py','engine/action_lifecycle.py','engine/frequency.py','engine/wild_equipment.py','data/rulesets.json','data/skill-check-policy.json','output/ruleunits.jsonl','input/ch03-skills-edges-feats.md','input/ch05-pokemon.md','tools/test_category3_activity_features.py']
 files += ['engine/campaign_rewards.py', 'engine/league_consequences.py', 'data/campaign-reward-policy.json']
 files += ['engine/pokemon_understanding.py', 'engine/regional_pokemon.py', 'engine/source_context.py']
 files += ['engine/blessing_skill_features.py', 'engine/combat_precision_features.py', 'engine/pokemon_intelligence.py', 'engine/pokemon_party.py', 'engine/pokemon_teaching.py', 'data/pokemon-machines.json']

 files += ['engine/arithmetic.py', 'engine/arithmetic_policy.py', 'engine/effect_contracts.py', 'engine/effect_lifetimes.py', 'engine/maneuver_grants.py', 'engine/move_activation.py', 'engine/native_rule_policy.py', 'data/native-rule-policy.json']

 files += ['engine/action_lifecycle.py', 'engine/action_metadata.py', 'engine/action_points.py', 'engine/adjudication_guidance.py', 'engine/ap_roll_bonus.py', 'engine/bandages.py', 'engine/bound_ap.py', 'engine/builder.py', 'engine/capability_actions.py', 'engine/combat_maneuvers.py', 'engine/combat_social_edges.py', 'engine/combat_stage_sources.py', 'engine/combat_timing.py', 'engine/common_action_checks.py', 'engine/common_checks.py', 'engine/contest.py', 'engine/contest_features.py', 'engine/context_actions.py', 'engine/crafting_activities.py', 'engine/custom_species.py', 'engine/damage_reactions.py', 'engine/demo_rulings.py', 'engine/downtime.py', 'engine/effects.py', 'engine/effects_ext.py', 'engine/elemental_connection.py', 'engine/encounter.py', 'engine/enduring_awareness.py', 'engine/engine.py', 'engine/environmental_effects.py', 'engine/focus_tasks.py', 'engine/food_effects.py', 'engine/frequency.py', 'engine/gm_console.py', 'engine/gm_state.py', 'engine/grid.py', 'engine/heavy_injury_adapter.py', 'engine/heavy_injury_kernel.py', 'engine/heavy_standard_adapter.py', 'engine/initiative.py', 'engine/injury_recovery.py', 'engine/items.py', 'engine/jump_actions.py', 'engine/league_agenda.py', 'engine/league_runtime.py', 'engine/life.py', 'engine/maneuver_edges.py', 'engine/movement_actions.py', 'engine/net_capsule.py', 'engine/observed_resolution.py', 'engine/passive_event_profiles.py', 'engine/passive_events.py', 'engine/physical_limits.py', 'engine/physics_maneuvers.py', 'engine/pokemon_activities.py', 'engine/pokemon_requests.py', 'engine/precise_actions.py', 'engine/researcher_features.py', 'engine/resolution_transaction.py', 'engine/rest_intervals.py', 'engine/restorative_items.py', 'engine/root_admission.py', 'engine/root_children.py', 'engine/root_common_checks.py', 'engine/root_common_engine.py', 'engine/root_inputs.py', 'engine/root_machine.py', 'engine/root_resolution.py', 'engine/root_scheduler.py', 'engine/ruleset.py', 'engine/rulings.py', 'engine/skill_feature_actions.py', 'engine/skill_maneuver_actions.py', 'engine/skill_modifiers.py', 'engine/skill_stunts.py', 'engine/skill_targets.py', 'engine/survivalist_features.py', 'engine/temporary_hp.py', 'engine/test_builder.py', 'engine/test_contest.py', 'engine/test_downtime.py', 'engine/test_effects.py', 'engine/test_gm_state.py', 'engine/test_grid.py', 'engine/test_items.py', 'engine/test_maintenance.py', 'engine/test_playthrough.py', 'engine/test_rules.py', 'engine/test_ruleset.py', 'engine/test_rulings.py', 'engine/test_turn.py', 'engine/trainer_capabilities.py', 'engine/turn.py', 'engine/weapon_actions.py', 'engine/wild_equipment.py', 'data/content-source-identities.json', 'data/context-check-policy.json', 'data/skill-check-policy.json', 'data/adjudication-guidance.json', 'data/rulesets.json']
 report={'generated_at':datetime.now(timezone.utc).isoformat(),'successful':result.wasSuccessful(),'scope':['C3-EX-045 activity integration'],'results':result.rows,'input_hashes':{f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files}}
 (ROOT/'output/category3-activity-feature-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 raise SystemExit(0 if result.wasSuccessful() else 1)
