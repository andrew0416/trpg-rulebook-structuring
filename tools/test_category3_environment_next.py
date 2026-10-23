"""Environmental source procedure on actual Engine clock, recovery and damage."""
import hashlib,json,sys,unittest
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"engine"))
from engine import Rules,Engine,Combatant
from common_checks import PendingDecision
import environmental_effects as ENV
import injury_recovery as RECOVERY

class EnvironmentTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(str(ROOT))
 def setUp(self):
  self.e=Engine(self.r,seed=9)
  self.c=self.actor("T")
  self.e.everyone=[self.c]
 def actor(self,name,kind="trainer",species=None):
  # Legal trainer level3/hp8 retains the source fall example max HP40.
  spec={"name":name,"kind":kind,"level":3 if kind=="trainer" else 1,"stats":{"hp":8 if kind=="trainer" else 10,"atk":200,"def":5,"spa":200,"spd":5,"spe":5},"moves":[],"skills":{"곡예":"전문"},"movement":{"land":6,"high_jump":2,"long_jump":3},"weight_class":3}
  if species:spec["species"]=species
  return Combatant(self.r,spec)
 def breath(self,available=False,**kw):
  return self.e.observe_breathing(self.c,air_available=available,medium="air" if available else "airless",reason="GM actual breathing observation",**kw)
 def fall(self,**kw):
  opts=dict(action_id="fall",meters=3,intentional=False,reason="GM observed cliff fall",fixed_damage=[3,3])
  opts.update(kw)
  return self.e.falling_damage(self.c,**opts)
 def test_breathless_grace_and_repeated_observation_do_not_restart_timer(self):
  self.breath(timing_policy="grace_boundary");self.e.advance_time(59)
  self.assertEqual(self.c.injuries,0)
  self.breath();self.e.advance_time(1)
  self.assertEqual((self.c.injuries,ENV.protected_injuries(self.c)),(1,1))
  self.e.advance_time(20);self.assertEqual(self.c.injuries,3)
 def test_ambiguous_first_phase_blocks_all_clock_changes(self):
  self.breath();self.e.advance_time(59)
  before=(self.e.elapsed_seconds,self.c.life_elapsed_seconds,self.c.injuries)
  with self.assertRaisesRegex(ValueError,"60/70"):self.e.advance_time(1)
  self.assertEqual(before,(self.e.elapsed_seconds,self.c.life_elapsed_seconds,self.c.injuries))
  self.breath(timing_policy="completed_round_after_grace");self.e.advance_time(10)
  self.assertEqual(self.c.injuries,0);self.e.advance_time(1);self.assertEqual(self.c.injuries,1)
 def test_only_breathing_removes_protected_injuries_without_daily_allowance(self):
  self.c.injuries=2;self.breath(timing_policy="grace_boundary");self.e.advance_time(80)
  self.assertEqual(RECOVERY.heal(self.e,self.c,5,source="pokemon_center"),2)
  self.assertEqual((self.c.injuries,ENV.protected_injuries(self.c)),(3,3))
  self.breath(True)
  self.assertEqual((self.c.injuries,ENV.protected_injuries(self.c),RECOVERY.healed_today(self.c)),(0,0,2))
 def test_gilled_pokemon_and_trainer_breathe_underwater_only(self):
  for kind in ("pokemon","trainer"):
   c=self.actor(kind,kind);c.spec["capabilities"]=["아가미"]
   self.e.observe_breathing(c,air_available=False,medium="water",reason="submerged")
   self.e.advance_time(100,[c]);self.assertEqual(c.injuries,0)
   self.e.observe_breathing(c,air_available=False,medium="airless",reason="vacuum",timing_policy="grace_boundary")
   self.e.advance_time(60);self.assertEqual(c.injuries,1)
   self.e.observe_breathing(c,air_available=True,medium="air",reason="fresh air")
 def test_actual_round_clock_adds_one_per_round_after_selected_grace(self):
  self.e.start_round([self.c])
  self.assertIsInstance(self.breath(timing_policy="grace_boundary"),PendingDecision)
  self.breath(timing_policy="grace_boundary",round_offset_seconds=0)
  for _ in range(6):self.e.end_round();self.e.start_round([self.c])
  self.assertEqual(self.c.injuries,1)
  self.e.end_round();self.assertEqual(self.c.injuries,2)
 def test_breathing_recovery_does_not_resurrect_dead_actor(self):
  self.breath(timing_policy="grace_boundary");self.e.advance_time(150)
  self.assertEqual(self.c.injuries,10);self.assertTrue(self.c.dead)
  self.breath(True);self.assertEqual(self.c.injuries,0);self.assertTrue(self.c.dead)
 def test_unknown_partial_round_cannot_prove_suffocation_elapsed(self):
  self.e.start_round([self.c]);self.breath(timing_policy="grace_boundary",round_offset_seconds=0)
  self.e.end_encounter()
  with self.assertRaisesRegex(ValueError,"unknown elapsed"):self.e.advance_time(60)
  self.assertIsInstance(self.breath(True),PendingDecision)
 def test_snapshot_restores_provenance_and_actual_registered_actor(self):
  self.breath(timing_policy="grace_boundary");self.e.advance_time(60)
  self.e.gm.snapshot("airless");self.breath(True);self.e.gm.restore("airless")
  self.assertEqual(ENV.protected_injuries(self.c),1)
  self.e.advance_time(10);self.assertEqual(self.c.injuries,2)
 def test_changed_gilled_capability_requires_new_timed_observation(self):
  self.c.spec["capabilities"]=["아가미"]
  self.e.observe_breathing(self.c,air_available=False,medium="water",reason="submerged")
  self.c.spec["capabilities"]=[]
  with self.assertRaisesRegex(ValueError,"new timed"):self.e.advance_time(1)
  self.e.observe_breathing(self.c,air_available=False,medium="water",reason="gills lost",timing_policy="grace_boundary")
  self.e.advance_time(60);self.assertEqual(self.c.injuries,1)
 def test_typeless_damage_uses_defense_without_attack_stat_stab_or_type(self):
  self.c.types=["고스트","강철"]
  out=self.fall()
  self.assertEqual((out["damage_base"],out["raw_damage"],out["damage"],self.c.hp),(6,14,9,31))
 def test_source_two_stage_awning_example_exact_hp_and_injuries(self):
  out=self.fall(meters=5,surface_meters=-2,surface_reason="elastic awning")
  self.assertEqual((out["damage"],self.c.hp,self.c.injuries),(9,31,0))
  out=self.fall(action_id="fall-second",meters=10,surface_meters=-2,surface_reason="pile of garbage",fixed_damage=[10,10,10,5,1])
  self.assertIsInstance(out,PendingDecision)
  self.assertEqual((self.c.hp,self.c.injuries,self.c.dead),(-20,8,False))
  self.assertEqual(out.basis["height_injuries"],4)
 def test_source_fifteen_meter_example_exact_hp_injuries_death(self):
  out=self.fall(meters=15,fixed_damage=[12,12,12,12,6,2,2,2])
  self.assertEqual((self.c.hp,self.c.injuries,self.c.dead),(-95,14,True))
  self.assertEqual(out.basis["damage_base"],28)
 def test_weight_class_one_two_db20_and_three_six_db28_caps(self):
  for wc in range(1,7):
   self.e=Engine(self.r,seed=9);self.c=self.actor("weight"+str(wc));self.c.spec["weight_class"]=wc
   out=self.fall(meters=100,fixed_damage=None)
   result=out.basis if isinstance(out,PendingDecision) else out
   self.assertEqual(result["damage_base"],20 if wc<=2 else 28)
 def test_natural_species_sky_reduces_height_injuries_learned_sky_does_not(self):
  for species,expected in (("pokemon/피죤",2),("pokemon/피카츄",3)):
   self.c=self.actor(species,"pokemon",species);self.c.stats["hp"]=100
   self.c.hp=self.c.base_max_hp;self.c.spec["movement"]["sky"]=8
   out=self.fall(meters=6,fixed_damage=None)
   self.assertEqual(out["height_injuries"],expected)
 def test_trainer_current_sky_never_gets_pokemon_natural_exception(self):
  self.c.spec["movement"]["sky"]=8;self.c.stats["hp"]=100;self.c.hp=self.c.base_max_hp
  out=self.fall(meters=6,fixed_damage=None)
  self.assertEqual(out["height_injuries"],3)
 def test_pokemon_without_species_needs_explicit_natural_capability_fact(self):
  self.c=self.actor("unknown","pokemon")
  before=(self.e.rng.getstate(),self.c.hp)
  with self.assertRaisesRegex(ValueError,"natural Sky requires"):self.fall()
  self.assertEqual(before,(self.e.rng.getstate(),self.c.hp))
  self.fall(natural_sky=False,natural_sky_reason="GM species baseline has no Sky")
 def test_falling_acrobatics_dc12_intentional_and20_unintentional(self):
  for intentional,faces,passed in ((True,[3]*5,True),(False,[3]*5,False),(False,[4]*5,True)):
   self.c=self.actor("acro");self.c.spec["movement"]["high_jump"]=0
   out=self.fall(intentional=intentional,acrobatics=True,acrobatics_options={"fixed":faces},fixed_damage=None)
   self.assertEqual(out["checks"]["falling_acrobatics"].passed,passed)
   self.assertEqual(out["damage_distance"],2 if passed else 3)
 def test_same_intentional_jump_uses_live_high_jump_running_and_separate_boost(self):
  out=self.fall(meters=5,intentional=True,running_start=True,running_reason="actual run up",running_bonus_included=False,
     high_jump_boost=True,boost_options={"fixed":[4]*5},acrobatics=True,acrobatics_options={"fixed":[3]*5},fixed_damage=[])
  self.assertEqual((out["base_high_jump"],out["high_jump"],out["damage_distance"],out["damage"]),(3,4,0,0))
  self.assertEqual(len(out["checks"]),2)
 def test_past_successful_jump_receipt_cannot_supply_extra_fall_boost(self):
  self.c.spec["_jump_attempts"]={"old":{"landed":True,"effective_limits":{"high_jump":99}}}
  out=self.fall(intentional=True,meters=3,fixed_damage=[1])
  self.assertEqual(out["high_jump"],2)
 def test_successful_acrobatics_injury_boundary_needs_policy_before_mutation(self):
  before=(self.e.rng.getstate(),self.c.hp,self.c.injuries)
  with self.assertRaisesRegex(ValueError,"injury-distance"):
   self.fall(meters=4,acrobatics=True,acrobatics_options={"fixed":[4]*5})
  self.assertEqual(before,(self.e.rng.getstate(),self.c.hp,self.c.injuries))
  out=self.fall(meters=4,acrobatics=True,acrobatics_options={"fixed":[4]*5},acrobatics_injury_policy="distance")
  self.assertEqual(out["height_injuries"],0)
 def test_surface_rock_and_tree_adjustments_are_explicit_actual_damage(self):
  self.c.stats["hp"]=100;self.c.hp=self.c.base_max_hp
  out=self.fall(meters=2,surface_meters=1,surface_dice="1d6",surface_reason="rock and sharp tree branches",fixed_surface=[6])
  self.assertEqual((out["damage_base"],out["raw_damage"],out["damage"]),(6,20,15))
 def test_temporary_hp_absorbs_actual_fall_but_not_height_injuries(self):
  # GM API is the actual explicit permanent override, not a fake feature grant.
  self.e.gm.set_temp_hp(self.c,100,reason="GM fixture")
  out=self.fall(meters=4,fixed_damage=[3,3])
  self.assertEqual(self.c.hp,40);self.assertEqual(self.c.injuries,2)
  self.assertLess(self.c.temp_hp,100)
 def test_invalid_fixed_damage_has_no_rng_hp_or_roll_identity_consumption(self):
  before=(self.e.rng.getstate(),self.c.hp,dict(self.e._ap_rolls))
  with self.assertRaisesRegex(ValueError,"dice count"):
   self.fall(acrobatics=True,acrobatics_options={"fixed":[1]*5,"roll_id":"invalid-fall"},fixed_damage=[1])
  self.assertEqual(before,(self.e.rng.getstate(),self.c.hp,dict(self.e._ap_rolls)))
 def test_replayed_actual_fall_identity_rejected(self):
  self.fall();before=(self.e.rng.getstate(),self.c.hp)
  with self.assertRaisesRegex(ValueError,"already resolved"):self.fall()
  self.assertEqual(before,(self.e.rng.getstate(),self.c.hp))
 def test_pending_fall_blocks_next_action_and_time_until_actual_ruling_receipt(self):
  self.c.stats["hp"]=100;self.c.hp=100;self.c.injuries=2
  self.fall(meters=6,fixed_damage=[1,1,1])
  with self.assertRaises(ENV.EnvironmentalPending):self.e.advance_time(1)
  with self.assertRaises(ENV.EnvironmentalPending):self.e.skill_roll(self.c,"곡예")
  self.assertEqual(self.e.elapsed_seconds,0)
  before=ENV.observe(self.c)
  with self.assertRaisesRegex(ValueError,"actual applied"):
   self.e.resolve_fall_ruling(self.c,action_id="fall",expected_current_state=before,disposition="resolved_externally",hp_loss_applied=5,temp_hp_loss_applied=0,injury_delta_applied=0,reason="GM order",continuation_reason="remaining loss")
  self.e.gm.set_hp(self.c,delta=-5,reason="GM additional heavy consequence")
  receipt=self.e.resolve_fall_ruling(self.c,action_id="fall",expected_current_state=ENV.observe(self.c),disposition="resolved_externally",hp_loss_applied=5,temp_hp_loss_applied=0,injury_delta_applied=0,reason="GM fall treated as attack",continuation_reason="base already applied; only five HP loss remained")
  self.assertEqual(receipt["hp_loss_applied"],5);self.assertFalse(receipt["source_conformance_proven"])
  self.e.advance_time(1)
  with self.assertRaisesRegex(ValueError,"no unresolved"):
   self.e.resolve_fall_ruling(self.c,action_id="fall",expected_current_state=ENV.observe(self.c),disposition="cancelled_by_ruling",hp_loss_applied=0,temp_hp_loss_applied=0,injury_delta_applied=0,reason="again",continuation_reason="again")
 def test_snapshot_restores_actual_environmental_pending_and_resolution_isolation(self):
  self.fall(meters=15,fixed_damage=[12,12,12,12,6,2,2,2]);self.e.gm.snapshot("fall-pending")
  self.e.resolve_fall_ruling(self.c,action_id="fall",expected_current_state=ENV.observe(self.c),disposition="cancelled_by_ruling",hp_loss_applied=0,temp_hp_loss_applied=0,injury_delta_applied=0,reason="GM rules no heavy supplement for this fall",continuation_reason="all source fall consequences already applied")
  self.e.advance_time(1);self.e.gm.restore("fall-pending")
  with self.assertRaises(ENV.EnvironmentalPending):self.e.advance_time(1)
  self.assertNotIn("resolution",self.c.spec["_fall_events"]["fall"])
 def test_preexisting_heavy_injuries_preserve_fall_roll_before_external_base_resolution(self):
  self.c.injuries=5;before=self.c.hp
  out=self.fall();self.assertIsInstance(out,PendingDecision)
  self.assertEqual(self.c.hp,before);self.assertEqual(out.basis["status"],"pending_heavy_composition")
  with self.assertRaises(ENV.EnvironmentalPending):self.fall(action_id="new")
 def test_fall_physical_damage_has_defense_and_dr_floor_one_but_zero_distance_zero(self):
  self.c.stats["def"]=999;self.c.damage_reduction=999
  out=self.fall();self.assertEqual((out["damage"],self.c.hp),(1,39))
  out=self.fall(action_id="fully-cushioned",surface_meters=-3,surface_reason="GM soft landing",fixed_damage=[])
  self.assertEqual((out["damage"],self.c.hp),(0,39))

 def test_physical_and_generic_dr_apply_without_type_specific_dr(self):
  self.c.damage_reduction=2
  self.c.modifiers += [{"type":"damage_reduction","value":3,"_scope":{"class":"물리"}}, {"type":"damage_reduction","value":99,"_scope":{"type":"불꽃"}}, {"type":"immunity","to":"전기"}]
  out=self.fall();self.assertEqual(out["damage"],4)
 def test_end_round_phase_pending_does_not_close_count_effects_or_round(self):
  self.e.start_round([self.c]);self.breath(round_offset_seconds=0)
  for _ in range(5):self.e.end_round();self.e.start_round([self.c])
  before=(self.e.elapsed_seconds,self.e.round_no,self.e.round_start_seconds)
  with self.assertRaisesRegex(ValueError,"60/70"):self.e.end_round()
  self.assertEqual(before,(self.e.elapsed_seconds,self.e.round_no,self.e.round_start_seconds))

 def test_selected_source_variant_does_not_inherit_core_environment_rules(self):
  original=self.r._selected_rule
  self.r._selected_rule=lambda uid,*a,**kw:uid+"-variant" if uid in (ENV.SUFFOCATION,ENV.FALL) else original(uid,*a,**kw)
  try:
   with self.assertRaisesRegex(ValueError,"variant"):self.breath()
   with self.assertRaisesRegex(ValueError,"variant"):self.fall()
  finally:self.r._selected_rule=original

if __name__=="__main__":
 class Result(unittest.TextTestResult):
  def __init__(self,*a,**k):super().__init__(*a,**k);self.rows=[]
  def addSuccess(self,t):super().addSuccess(t);self.rows.append({"id":t._testMethodName,"status":"pass"})
  def addFailure(self,t,e):super().addFailure(t,e);self.rows.append({"id":t._testMethodName,"status":"fail"})
  def addError(self,t,e):super().addError(t,e);self.rows.append({"id":t._testMethodName,"status":"error"})
 r=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(EnvironmentTests))
 files=['engine/adjudication_guidance.py','data/adjudication-guidance.json','engine/skill_maneuver_actions.py','engine/food_effects.py','engine/combat_social_edges.py','engine/net_capsule.py','engine/researcher_features.py','engine/wild_equipment.py','engine/downtime.py','engine/items.py','engine/skill_modifiers.py','engine/context_actions.py','engine/pokemon_requests.py','engine/combat_timing.py','engine/combat_maneuvers.py','data/context-check-policy.json','data/cultivation-policy.json',"engine/environmental_effects.py","engine/heavy_injury_adapter.py","engine/gm_state.py","engine/engine.py","engine/injury_recovery.py","engine/bandages.py","engine/trainer_capabilities.py","engine/jump_actions.py","engine/temporary_hp.py","engine/precise_actions.py","engine/common_checks.py","engine/common_action_checks.py","engine/skill_feature_actions.py","engine/life.py","data/lookup-tables.json","input/ch07-combat.md","tools/test_category3_environment_next.py"]
 files += ['engine/campaign_rewards.py', 'engine/league_consequences.py', 'data/campaign-reward-policy.json']
 files += ['engine/pokemon_understanding.py', 'engine/regional_pokemon.py', 'engine/source_context.py']
 files += ['engine/blessing_skill_features.py', 'engine/combat_precision_features.py', 'engine/pokemon_intelligence.py', 'engine/pokemon_party.py', 'engine/pokemon_teaching.py', 'data/pokemon-machines.json']

 files += ['engine/arithmetic.py', 'engine/arithmetic_policy.py', 'engine/effect_contracts.py', 'engine/effect_lifetimes.py', 'engine/maneuver_grants.py', 'engine/move_activation.py', 'engine/native_rule_policy.py', 'data/native-rule-policy.json']

 files += ['engine/action_lifecycle.py', 'engine/action_metadata.py', 'engine/action_points.py', 'engine/adjudication_guidance.py', 'engine/ap_roll_bonus.py', 'engine/bandages.py', 'engine/bound_ap.py', 'engine/builder.py', 'engine/capability_actions.py', 'engine/combat_maneuvers.py', 'engine/combat_social_edges.py', 'engine/combat_stage_sources.py', 'engine/combat_timing.py', 'engine/common_action_checks.py', 'engine/common_checks.py', 'engine/contest.py', 'engine/contest_features.py', 'engine/context_actions.py', 'engine/crafting_activities.py', 'engine/custom_species.py', 'engine/damage_reactions.py', 'engine/demo_rulings.py', 'engine/downtime.py', 'engine/effects.py', 'engine/effects_ext.py', 'engine/elemental_connection.py', 'engine/encounter.py', 'engine/enduring_awareness.py', 'engine/engine.py', 'engine/environmental_effects.py', 'engine/focus_tasks.py', 'engine/food_effects.py', 'engine/frequency.py', 'engine/gm_console.py', 'engine/gm_state.py', 'engine/grid.py', 'engine/heavy_injury_adapter.py', 'engine/heavy_injury_kernel.py', 'engine/heavy_standard_adapter.py', 'engine/initiative.py', 'engine/injury_recovery.py', 'engine/items.py', 'engine/jump_actions.py', 'engine/league_agenda.py', 'engine/league_runtime.py', 'engine/life.py', 'engine/maneuver_edges.py', 'engine/movement_actions.py', 'engine/net_capsule.py', 'engine/observed_resolution.py', 'engine/passive_event_profiles.py', 'engine/passive_events.py', 'engine/physical_limits.py', 'engine/physics_maneuvers.py', 'engine/pokemon_activities.py', 'engine/pokemon_requests.py', 'engine/precise_actions.py', 'engine/researcher_features.py', 'engine/resolution_transaction.py', 'engine/rest_intervals.py', 'engine/restorative_items.py', 'engine/root_admission.py', 'engine/root_children.py', 'engine/root_common_checks.py', 'engine/root_common_engine.py', 'engine/root_inputs.py', 'engine/root_machine.py', 'engine/root_resolution.py', 'engine/root_scheduler.py', 'engine/ruleset.py', 'engine/rulings.py', 'engine/skill_feature_actions.py', 'engine/skill_maneuver_actions.py', 'engine/skill_modifiers.py', 'engine/skill_stunts.py', 'engine/skill_targets.py', 'engine/survivalist_features.py', 'engine/temporary_hp.py', 'engine/test_builder.py', 'engine/test_contest.py', 'engine/test_downtime.py', 'engine/test_effects.py', 'engine/test_gm_state.py', 'engine/test_grid.py', 'engine/test_items.py', 'engine/test_maintenance.py', 'engine/test_playthrough.py', 'engine/test_rules.py', 'engine/test_ruleset.py', 'engine/test_rulings.py', 'engine/test_turn.py', 'engine/trainer_capabilities.py', 'engine/turn.py', 'engine/weapon_actions.py', 'engine/wild_equipment.py', 'data/content-source-identities.json', 'data/context-check-policy.json', 'data/skill-check-policy.json', 'data/adjudication-guidance.json', 'data/rulesets.json']
 report={"generated_at":datetime.now(timezone.utc).isoformat(),"successful":r.wasSuccessful(),"scope":["DOMAIN-033"],"full_scope_verified":False,"results":r.rows,"input_hashes":{f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files}}
 (ROOT/"output/category3-environment-next-tests.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 raise SystemExit(0 if r.wasSuccessful() else 1)
