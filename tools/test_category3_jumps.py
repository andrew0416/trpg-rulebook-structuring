"""Native Jump branches and capability-vs-skill eligibility."""
import sys,json,hashlib,unittest
from copy import deepcopy
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from engine import Engine,Rules,Combatant
from grid import Grid
import common_checks as C
class JumpTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(str(ROOT),ruleset='core')
 def setUp(self):
  self.e=Engine(self.r,seed=93);self.a=Combatant(self.r,{'id':'a','name':'a','kind':'pokemon','level':20,'stats':{'hp':30,'atk':10,'def':10,'spa':10,'spd':10,'spe':10},'skills':{'곡예':'숙련','육상':'달인'},'movement':{'land':6,'power':6,'high_jump':2,'long_jump':3},'moves':[]})
  self.a.spec['size']='Medium'
  self.a.pos=(1,1);self.e.grid=Grid(20,10);self.e.everyone=[self.a];self.e.gm.everyone=[self.a]
 def jump(self,dest=(4,1),**opts):
  defaults=dict(jump_id='one',difficult=False,clear_path=True,reason_text='GM observed landing and clear jump arc');defaults.update(opts)
  return self.e.jump(self.a,dest,**defaults)
 def turn(self):self.e.start_round([self.a]);self.e.start_of_turn(self.a)
 def test_source_scope_hashes_unchanged(self):
  data=json.loads((ROOT/'data/verification/category3-register.json').read_text(encoding='utf-8'))
  for e in data['entries']:
   if e['id'] not in ['C3-CORE-036','C3-CORE-043']:continue
   a=e['source_snapshot']['source'];lines=(ROOT/a['file']).read_text(encoding='utf-8-sig').splitlines()
   self.assertEqual(hashlib.sha256('\n'.join(lines[a['start']-1:a['end']]).encode()).hexdigest(),a['excerpt_sha256'])
 def test_within_capability_clear_jump_moves_without_rng_and_uses_whole_shift(self):
  self.turn();before=self.e.rng.getstate();result=self.jump()
  self.assertEqual((self.a.pos,self.a.budget['shift']),((4,1),0));self.assertEqual(self.a.budget['standard'],1);self.assertEqual(result['checks'],{});self.assertEqual(before,self.e.rng.getstate())
 def test_pokemon_and_trainer_use_their_actual_current_jump_capabilities(self):
  for kind in ['trainer','pokemon']:
   self.a.kind=kind;self.a.pos=(1,1)
   out=self.jump((1,1),jump_id=kind,landing_altitude=2,apex_height=2)
   self.assertEqual(out['effective_limits']['high_jump'],2);self.assertEqual(self.a.spec['_movement_altitude'],2);self.a.spec['_movement_altitude']=0
 def test_six_dice_high_result_cannot_bypass_unboosted_jump_limit(self):
  before=self.e.rng.getstate()
  with self.assertRaises(ValueError):self.jump((5,1),difficult=True,difficulty_skill='육상',difficulty_dc=4,difficulty_options={'fixed':[6]*6})
  self.assertEqual(self.a.pos,(1,1));self.assertEqual(self.e.rng.getstate(),before)
 def test_boost_dc16_equality_adds_exactly_one_to_chosen_long_capability(self):
  out=self.jump((5,1),boost='long_jump',boost_options={'fixed':[4]*4})
  self.assertTrue(out['checks']['boost'].passed);self.assertEqual(out['effective_limits'],{'high_jump':2,'long_jump':4});self.assertEqual(self.a.spec['movement']['long_jump'],3)
 def test_boost_high_never_also_increases_long_jump(self):
  with self.assertRaises(ValueError):self.jump((5,1),boost='high_jump',apex_height=3,boost_options={'fixed':[6]*4})
  out=self.jump((1,1),boost='high_jump',landing_altitude=3,apex_height=3,boost_options={'fixed':[4]*4})
  self.assertEqual(out['effective_limits'],{'high_jump':3,'long_jump':3})
 def test_failed_boost_is_recorded_without_automatic_fall_damage_or_reroll(self):
  self.turn();hp=self.a.hp;out=self.jump((5,1),boost='long_jump',boost_options={'fixed':[1]*4})
  self.assertIsInstance(out,C.PendingDecision);self.assertEqual((self.a.pos,self.a.hp),((1,1),hp));self.assertEqual(self.a.budget['shift'],0)
  state=self.e.rng.getstate();out2=self.jump((5,1),jump_id='another',boost='long_jump',boost_options={'fixed':[6]*4});self.assertIsInstance(out2,C.PendingDecision);self.assertEqual(state,self.e.rng.getstate())
  self.e.gm.resolve_jump_failure(self.a,decision='abort',reason='actor stops at the edge')
  with self.assertRaises(ValueError):self.jump((5,1),boost='long_jump',boost_options={'fixed':[6]*4})
 def test_short_but_difficult_jump_still_needs_separate_gm_check(self):
  out=self.jump((2,1),difficult=True);self.assertIsInstance(out,C.PendingDecision);self.assertEqual(self.a.pos,(1,1))
  out=self.jump((2,1),difficult=True,difficulty_skill='곡예',difficulty_dc=17,difficulty_options={'fixed':[4]*4})
  self.assertIsInstance(out,C.PendingDecision);self.assertEqual(out.check.total,16);self.assertEqual(self.a.pos,(1,1))
 def test_successful_boost_does_not_replace_difficult_landing_check(self):
  out=self.jump((5,1),boost='long_jump',boost_options={'fixed':[4]*4},difficult=True,difficulty_skill='곡예',difficulty_dc=5,difficulty_options={'fixed':[1]*4})
  self.assertIsInstance(out,C.PendingDecision);self.assertTrue(out.basis['checks']['boost'].passed);self.assertFalse(out.basis['checks']['difficulty'].passed);self.assertEqual(self.a.pos,(1,1))
 def test_two_real_checks_keep_separate_ap_roll_identities(self):
  with self.assertRaises(ValueError):self.jump((5,1),boost='long_jump',boost_options={'roll_id':'same'},difficult=True,difficulty_skill='곡예',difficulty_dc=5,difficulty_options={'roll_id':'same'})
  self.assertNotIn('_jump_attempts',self.a.spec)
 def test_invalid_late_plan_keeps_action_budget_rng_and_position(self):
  self.turn();state=self.e.rng.getstate();budget=dict(self.a.budget)
  with self.assertRaises(ValueError):self.jump((5,1),boost='long_jump',boost_options={'fixed':[4]*4},difficult=True,difficulty_skill='곡예',difficulty_dc=5,difficulty_options={'fixed':[1]})
  self.assertEqual(self.e.rng.getstate(),state);self.assertEqual(self.a.budget,budget);self.assertEqual(self.a.pos,(1,1))
 def test_missing_context_or_capability_does_not_create_a_default(self):
  self.assertIsInstance(self.jump(difficult=None),C.PendingDecision);self.assertIsInstance(self.jump(clear_path=None),C.PendingDecision)
  self.a.spec['movement'].pop('high_jump')
  with self.assertRaises(ValueError):self.jump()
 def test_unconscious_or_wrong_turn_cannot_jump(self):
  self.turn();self.e.end_of_turn(self.a);self.assertFalse(self.jump());self.a.hp=0;self.e.encounter_active=False;self.assertFalse(self.jump())
 def test_snapshot_restores_landing_and_failed_attempt_history(self):
  self.e.gm.snapshot('start');self.jump();self.assertEqual(self.a.pos,(4,1));self.e.gm.restore('start');self.assertEqual(self.a.pos,(1,1));self.assertNotIn('_jump_attempts',self.a.spec)
 def test_known_arc_can_clear_low_wall_without_teleport_los_rule(self):
  self.e.grid.blocking.add((2,1));self.jump(apex_height=2);self.assertEqual(self.a.pos,(4,1))
 def test_specialized_declaration_cannot_be_completed_by_generic_high_skill(self):
  out=self.e.common_action(self.a,'육상',1,mode='skill',fixed=[6]*6,outcome='success',description='automatic impossible jump',declaration={'action':'jump a huge gap','activity':'jump'})
  self.assertIsInstance(out,C.PendingDecision);self.assertEqual(self.a.pos,(1,1))
if __name__=='__main__':
 class Result(unittest.TextTestResult):
  def __init__(self,*a,**kw):super().__init__(*a,**kw);self.rows=[]
  def addSuccess(self,t):super().addSuccess(t);self.rows.append({'id':t._testMethodName,'status':'pass'})
  def addFailure(self,t,e):super().addFailure(t,e);self.rows.append({'id':t._testMethodName,'status':'fail'})
  def addError(self,t,e):super().addError(t,e);self.rows.append({'id':t._testMethodName,'status':'error'})
 result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(JumpTests))
 files=['engine/adjudication_guidance.py','data/adjudication-guidance.json','engine/skill_maneuver_actions.py','engine/food_effects.py','engine/combat_social_edges.py','engine/net_capsule.py','engine/trainer_capabilities.py','engine/skill_feature_actions.py','engine/researcher_features.py','engine/precise_actions.py','engine/environmental_effects.py','engine/wild_equipment.py','engine/injury_recovery.py','engine/downtime.py','engine/items.py','engine/heavy_injury_adapter.py','engine/context_actions.py','engine/pokemon_requests.py','engine/combat_timing.py','engine/combat_maneuvers.py','data/context-check-policy.json','data/cultivation-policy.json','tools/test_category3_jumps.py','engine/jump_actions.py','engine/movement_actions.py','engine/engine.py','engine/capability_actions.py','engine/physical_limits.py','engine/turn.py','engine/action_lifecycle.py','engine/common_checks.py','engine/common_action_checks.py','engine/skill_modifiers.py','engine/resolution_transaction.py','engine/ap_roll_bonus.py','engine/gm_state.py','engine/ruleset.py','engine/effects_ext.py','data/skill-check-policy.json','data/capability-policy.json','data/core-rules.json','data/rulesets.json','data/conditions.json','output/ruleunits.jsonl','input/ch06-gameplay.md','input/ch07-combat.md']
 files += ['engine/campaign_rewards.py', 'engine/league_consequences.py', 'data/campaign-reward-policy.json']
 files += ['engine/pokemon_understanding.py', 'engine/regional_pokemon.py', 'engine/source_context.py']
 files += ['engine/blessing_skill_features.py', 'engine/combat_precision_features.py', 'engine/pokemon_intelligence.py', 'engine/pokemon_party.py', 'engine/pokemon_teaching.py', 'data/pokemon-machines.json']

 files += ['engine/arithmetic.py', 'engine/arithmetic_policy.py', 'engine/effect_contracts.py', 'engine/effect_lifetimes.py', 'engine/maneuver_grants.py', 'engine/move_activation.py', 'engine/native_rule_policy.py', 'data/native-rule-policy.json']

 files += ['engine/action_lifecycle.py', 'engine/action_metadata.py', 'engine/action_points.py', 'engine/adjudication_guidance.py', 'engine/ap_roll_bonus.py', 'engine/bandages.py', 'engine/bound_ap.py', 'engine/builder.py', 'engine/capability_actions.py', 'engine/combat_maneuvers.py', 'engine/combat_social_edges.py', 'engine/combat_stage_sources.py', 'engine/combat_timing.py', 'engine/common_action_checks.py', 'engine/common_checks.py', 'engine/contest.py', 'engine/contest_features.py', 'engine/context_actions.py', 'engine/crafting_activities.py', 'engine/custom_species.py', 'engine/damage_reactions.py', 'engine/demo_rulings.py', 'engine/downtime.py', 'engine/effects.py', 'engine/effects_ext.py', 'engine/elemental_connection.py', 'engine/encounter.py', 'engine/enduring_awareness.py', 'engine/engine.py', 'engine/environmental_effects.py', 'engine/focus_tasks.py', 'engine/food_effects.py', 'engine/frequency.py', 'engine/gm_console.py', 'engine/gm_state.py', 'engine/grid.py', 'engine/heavy_injury_adapter.py', 'engine/heavy_injury_kernel.py', 'engine/heavy_standard_adapter.py', 'engine/initiative.py', 'engine/injury_recovery.py', 'engine/items.py', 'engine/jump_actions.py', 'engine/league_agenda.py', 'engine/league_runtime.py', 'engine/life.py', 'engine/maneuver_edges.py', 'engine/movement_actions.py', 'engine/net_capsule.py', 'engine/observed_resolution.py', 'engine/passive_event_profiles.py', 'engine/passive_events.py', 'engine/physical_limits.py', 'engine/physics_maneuvers.py', 'engine/pokemon_activities.py', 'engine/pokemon_requests.py', 'engine/precise_actions.py', 'engine/researcher_features.py', 'engine/resolution_transaction.py', 'engine/rest_intervals.py', 'engine/restorative_items.py', 'engine/root_admission.py', 'engine/root_children.py', 'engine/root_common_checks.py', 'engine/root_common_engine.py', 'engine/root_inputs.py', 'engine/root_machine.py', 'engine/root_resolution.py', 'engine/root_scheduler.py', 'engine/ruleset.py', 'engine/rulings.py', 'engine/skill_feature_actions.py', 'engine/skill_maneuver_actions.py', 'engine/skill_modifiers.py', 'engine/skill_stunts.py', 'engine/skill_targets.py', 'engine/survivalist_features.py', 'engine/temporary_hp.py', 'engine/test_builder.py', 'engine/test_contest.py', 'engine/test_downtime.py', 'engine/test_effects.py', 'engine/test_gm_state.py', 'engine/test_grid.py', 'engine/test_items.py', 'engine/test_maintenance.py', 'engine/test_playthrough.py', 'engine/test_rules.py', 'engine/test_ruleset.py', 'engine/test_rulings.py', 'engine/test_turn.py', 'engine/trainer_capabilities.py', 'engine/turn.py', 'engine/weapon_actions.py', 'engine/wild_equipment.py', 'data/content-source-identities.json', 'data/context-check-policy.json', 'data/skill-check-policy.json', 'data/adjudication-guidance.json', 'data/rulesets.json']
 report={'generated_at':datetime.now(timezone.utc).isoformat(),'successful':result.wasSuccessful(),'scope':['C3-CORE-036','C3-CORE-043'],'results':result.rows,'input_hashes':{f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files}}
 (ROOT/'output/category3-jump-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 raise SystemExit(0 if result.wasSuccessful() else 1)
