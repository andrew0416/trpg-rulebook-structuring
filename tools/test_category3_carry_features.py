"""Observed Skill Monkey choices on real native staggering-load checks."""
import sys,json,hashlib,unittest
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from engine import Engine,Rules,Combatant
import common_checks as C
import skill_feature_actions as F
class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(str(ROOT),ruleset='core')
 def setUp(self):
  self.e=Engine(self.r,seed=765);self.a=Combatant(self.r,{'id':'trainer/a','name':'a','kind':'trainer','level':20,'stats':{'hp':40,'atk':20,'def':20,'spa':20,'spd':20,'spe':20},'skills':{'육상':1,'곡예':4,'통찰':4,'집중':4},'feats':[F.MONKEY],'movement':{'power':6,'land':6}})
  self.e.gm.everyone=[self.a];self.e.everyone=[self.a]
  self.e.gm.set_carried_objects(self.a,[{'id':'crate','weight_kg':60}],'weighed crate')
 def opts(self,**changes):
  opts={'fixed':[1],'round_id':'r1','roll_id':'carry-a-r1','feature':F.MONKEY,'feature_options':{'decision':lambda first:True,'reroll_faces':[2]}};opts.update(changes);return opts
 def used(self):return self.a.spec.get('frequency_state',{}).get('activations',{}).get(F.MONKEY,{}).get('used',0)
 def test_native_carry_final_reroll_reaches_exact_dc_and_closes_round(self):
  out=self.e.carry_check(self.a,**self.opts());self.assertTrue(out.passed);self.assertEqual(out.total,4);self.assertEqual(self.used(),1)
  self.assertEqual(self.a.spec['_carried_load']['checked_round'],'noncombat:r1');self.assertNotIn('skill_inflight',self.a.spec['_carried_load'])
  with self.assertRaises(ValueError):self.e.carry_check(self.a,**self.opts())
  self.assertEqual(self.used(),1)
 def test_failed_reroll_preserves_load_and_waits_for_gm_without_drop(self):
  out=self.e.carry_check(self.a,**self.opts(feature_options={'decision':lambda first:True,'reroll_faces':[1]}))
  self.assertIsInstance(out,C.PendingDecision);self.assertEqual(out.check.total,3);self.assertTrue(self.a.spec['_carried_load']['failure_pending']);self.assertEqual(len(self.a.spec['_carried_load']['objects']),1)
 def test_observed_error_requires_same_identity_then_resumes_same_first_roll(self):
  with self.assertRaises(ValueError):self.e.carry_check(self.a,**self.opts(feature_options={'decision':lambda first:'bad'}))
  first=F.event(self.e,self.a,'carry-a-r1').first;before=self.e.rng.getstate();self.assertEqual(self.used(),0)
  for changes in [{'feature':None},{'roll_id':'new'},{'round_id':'r2'},{'fixed':[6]}]:
   with self.assertRaises(ValueError):self.e.carry_check(self.a,**self.opts(**changes))
  self.assertEqual(self.e.rng.getstate(),before)
  out=self.e.carry_check(self.a,**self.opts());self.assertTrue(out.passed);self.assertIs(F.event(self.e,self.a,'carry-a-r1').first,first);self.assertEqual(self.used(),1)
 def test_decline_keeps_failed_original_and_spends_no_feature(self):
  out=self.e.carry_check(self.a,**self.opts(feature_options={'decision':lambda first:False}))
  self.assertEqual(out.check.total,1);self.assertEqual(self.used(),0);self.assertTrue(self.a.spec['_carried_load']['failure_pending'])
 def test_preflight_failure_never_creates_inflight_or_consumes_rng(self):
  before=self.e.rng.getstate()
  with self.assertRaises(ValueError):self.e.carry_check(self.a,**self.opts(feature_options={'decision':lambda first:True,'reroll_faces':[7]}))
  self.assertNotIn('skill_inflight',self.a.spec['_carried_load']);self.assertEqual(before,self.e.rng.getstate())
 def test_combat_carry_uses_free_trigger_without_granting_standard(self):
  self.e.start_round([self.a]);self.e.start_of_turn(self.a);before=dict(self.a.budget)
  out=self.e.carry_check(self.a,**self.opts(round_id=None));self.assertTrue(out.passed);self.assertEqual(self.a.budget,before);self.assertEqual(self.a._action_history,['free']);self.e.end_of_turn(self.a)
 def test_plain_identified_carry_result_is_final_and_cannot_later_reroll(self):
  out=self.e.carry_check(self.a,round_id='r1',roll_id='plain',fixed=[4]);self.assertTrue(out.passed)
  with self.assertRaises(ValueError):self.e.skill_roll(self.a,'육상',roll_id='plain',fixed=[4],feature=F.MONKEY,feature_options={'decision':lambda first:True})
if __name__=='__main__':
 class Result(unittest.TextTestResult):
  def __init__(self,*a,**kw):super().__init__(*a,**kw);self.rows=[]
  def addSuccess(self,t):super().addSuccess(t);self.rows.append({'id':t._testMethodName,'status':'pass'})
  def addFailure(self,t,e):super().addFailure(t,e);self.rows.append({'id':t._testMethodName,'status':'fail'})
  def addError(self,t,e):super().addError(t,e);self.rows.append({'id':t._testMethodName,'status':'error'})
 result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
 files=['engine/adjudication_guidance.py','data/adjudication-guidance.json','engine/skill_maneuver_actions.py','engine/food_effects.py','engine/combat_social_edges.py','engine/net_capsule.py','engine/trainer_capabilities.py','engine/researcher_features.py','engine/precise_actions.py','engine/environmental_effects.py','engine/wild_equipment.py','engine/injury_recovery.py','engine/downtime.py','engine/items.py','engine/heavy_injury_adapter.py','engine/jump_actions.py','engine/context_actions.py','engine/pokemon_requests.py','engine/combat_timing.py','engine/combat_maneuvers.py','data/context-check-policy.json','data/cultivation-policy.json','tools/test_category3_carry_features.py','engine/capability_actions.py','engine/physical_limits.py','engine/engine.py','engine/skill_feature_actions.py','engine/contest_features.py','engine/common_checks.py','engine/common_action_checks.py','engine/skill_modifiers.py','engine/resolution_transaction.py','engine/action_lifecycle.py','engine/frequency.py','engine/ap_roll_bonus.py','engine/turn.py','engine/gm_state.py','data/core-rules.json','data/skill-check-policy.json','data/capability-policy.json','output/ruleunits.jsonl','input/ch03-skills-edges-feats.md','input/ch06-gameplay.md']
 files += ['engine/campaign_rewards.py', 'engine/league_consequences.py', 'data/campaign-reward-policy.json']
 files += ['engine/pokemon_understanding.py', 'engine/regional_pokemon.py', 'engine/source_context.py']
 files += ['engine/blessing_skill_features.py', 'engine/combat_precision_features.py', 'engine/pokemon_intelligence.py', 'engine/pokemon_party.py', 'engine/pokemon_teaching.py', 'data/pokemon-machines.json']

 files += ['engine/arithmetic.py', 'engine/arithmetic_policy.py', 'engine/effect_contracts.py', 'engine/effect_lifetimes.py', 'engine/maneuver_grants.py', 'engine/move_activation.py', 'engine/native_rule_policy.py', 'data/native-rule-policy.json']

 files += ['engine/action_lifecycle.py', 'engine/action_metadata.py', 'engine/action_points.py', 'engine/adjudication_guidance.py', 'engine/ap_roll_bonus.py', 'engine/bandages.py', 'engine/bound_ap.py', 'engine/builder.py', 'engine/capability_actions.py', 'engine/combat_maneuvers.py', 'engine/combat_social_edges.py', 'engine/combat_stage_sources.py', 'engine/combat_timing.py', 'engine/common_action_checks.py', 'engine/common_checks.py', 'engine/contest.py', 'engine/contest_features.py', 'engine/context_actions.py', 'engine/crafting_activities.py', 'engine/custom_species.py', 'engine/damage_reactions.py', 'engine/demo_rulings.py', 'engine/downtime.py', 'engine/effects.py', 'engine/effects_ext.py', 'engine/elemental_connection.py', 'engine/encounter.py', 'engine/enduring_awareness.py', 'engine/engine.py', 'engine/environmental_effects.py', 'engine/focus_tasks.py', 'engine/food_effects.py', 'engine/frequency.py', 'engine/gm_console.py', 'engine/gm_state.py', 'engine/grid.py', 'engine/heavy_injury_adapter.py', 'engine/heavy_injury_kernel.py', 'engine/heavy_standard_adapter.py', 'engine/initiative.py', 'engine/injury_recovery.py', 'engine/items.py', 'engine/jump_actions.py', 'engine/league_agenda.py', 'engine/league_runtime.py', 'engine/life.py', 'engine/maneuver_edges.py', 'engine/movement_actions.py', 'engine/net_capsule.py', 'engine/observed_resolution.py', 'engine/passive_event_profiles.py', 'engine/passive_events.py', 'engine/physical_limits.py', 'engine/physics_maneuvers.py', 'engine/pokemon_activities.py', 'engine/pokemon_requests.py', 'engine/precise_actions.py', 'engine/researcher_features.py', 'engine/resolution_transaction.py', 'engine/rest_intervals.py', 'engine/restorative_items.py', 'engine/root_admission.py', 'engine/root_children.py', 'engine/root_common_checks.py', 'engine/root_common_engine.py', 'engine/root_inputs.py', 'engine/root_machine.py', 'engine/root_resolution.py', 'engine/root_scheduler.py', 'engine/ruleset.py', 'engine/rulings.py', 'engine/skill_feature_actions.py', 'engine/skill_maneuver_actions.py', 'engine/skill_modifiers.py', 'engine/skill_stunts.py', 'engine/skill_targets.py', 'engine/survivalist_features.py', 'engine/temporary_hp.py', 'engine/test_builder.py', 'engine/test_contest.py', 'engine/test_downtime.py', 'engine/test_effects.py', 'engine/test_gm_state.py', 'engine/test_grid.py', 'engine/test_items.py', 'engine/test_maintenance.py', 'engine/test_playthrough.py', 'engine/test_rules.py', 'engine/test_ruleset.py', 'engine/test_rulings.py', 'engine/test_turn.py', 'engine/trainer_capabilities.py', 'engine/turn.py', 'engine/weapon_actions.py', 'engine/wild_equipment.py', 'data/content-source-identities.json', 'data/context-check-policy.json', 'data/skill-check-policy.json', 'data/adjudication-guidance.json', 'data/rulesets.json']
 report={'generated_at':datetime.now(timezone.utc).isoformat(),'successful':result.wasSuccessful(),'results':result.rows,'input_hashes':{f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files}}
 (ROOT/'output/category3-carry-feature-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 raise SystemExit(0 if result.wasSuccessful() else 1)
