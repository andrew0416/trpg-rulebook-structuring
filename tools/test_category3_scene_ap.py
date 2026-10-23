"""Source-scoped scene boundaries and AP eligibility through native consumers."""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import hashlib, json, sys, unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'engine'))
from engine import Engine, Rules, Combatant
from grid import Grid
import action_points as AP
import contest_features as F
import frequency as FREQ
import state_codec as CODEC
class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(ROOT,ruleset='core')
 def setUp(self):
  self.e=Engine(self.r,seed=27)
  stats=dict(hp=20,atk=10,**{'def':5},spa=10,spd=5,spe=5)
  self.t=Combatant(self.r,dict(id='t',name='Trainer',kind='trainer',level=25,stats=stats,classes=['class/코디네이터'],edges=['edge/우아함'],feats=[F.NUANCED,F.RELIABLE],skills={'매력':6,'육상':3,'곡예':3},movement_basis='trainer_base'))
  self.p=Combatant(self.r,dict(id='p',name='Pokemon',kind='pokemon',trainer_id='t',level=25,stats=stats,skills={'육상':3},moves=['move/몸통박치기']))
  self.enemy=Combatant(self.r,dict(id='enemy',name='Enemy',kind='pokemon',level=25,stats=stats,skills={'육상':3}))
  self.t.pos=(0,0);self.p.pos=(2,0);self.enemy.pos=(3,0)
  self.e.everyone=[self.t,self.p,self.enemy]
  import pokemon_entities as ENTITIES
  ENTITIES.observe_loyalty(self.e,self.p,3,reason='GM observed loyal partner for actual attack fixture')
  self.e.time_actors(self.e.everyone)
 def reliable(self):return self.e.contest_skill_feature(self.t,self.p,F.RELIABLE,'육상',10)
 def test_at_will_native_move_keeps_paid_action_after_durable_restore(self):
  self.e.gm.everyone=self.e.everyone
  mid='move/몸통박치기';self.assertEqual(FREQ.move_frequency(self.e,mid,self.p),('at_will',1))
  self.e.start_round(self.e.everyone);self.e.start_of_turn(self.p)
  self.e.use_move(self.p,self.enemy,mid,set_damage=True)
  self.assertEqual(self.p.move_uses[mid],1);self.assertEqual(self.p.budget['standard'],0)
  loaded=CODEC.load_engine(self.r,json.loads(json.dumps(CODEC.dump_engine(self.e),ensure_ascii=False)))
  actors={c.entity_id:c for c in loaded.everyone};p=actors[self.p.entity_id];enemy=actors[self.enemy.entity_id]
  self.assertTrue(FREQ.move_allowed(loaded,p,mid)[0])
  before=deepcopy((p.spec,p.budget,enemy.hp,loaded.rng.getstate(),p._action_history))
  loaded.use_move(p,enemy,mid,set_damage=True)
  self.assertEqual((p.spec,p.budget,enemy.hp,loaded.rng.getstate(),p._action_history),before)
  loaded.end_of_turn(p);loaded.end_round();loaded.start_round(loaded.everyone);loaded.start_of_turn(p)
  loaded.use_move(p,enemy,mid,set_damage=True)
  self.assertEqual(p.move_uses[mid],2);self.assertEqual(p.budget['standard'],0)
  self.assertTrue(loaded.validate_state()['valid'])
 def test_fixed_scene_and_ap_eligibility_scopes_match(self):
  rows=json.loads((ROOT/'data/verification/category3-register.json').read_text('utf-8'))['entries']
  for row in rows:
   if row['id'] not in ('C3-CORE-026','C3-CORE-027','C3-CORE-033'):continue
   src=row['source_snapshot']['source'];lines=(ROOT/src['file']).read_text('utf-8-sig').splitlines()
   self.assertEqual(hashlib.sha256('\n'.join(lines[src['start']-1:src['end']]).encode()).hexdigest(),src['excerpt_sha256'])
 def test_multiple_encounters_in_one_scene_do_not_refresh_native_ap(self):
  self.reliable();spent=AP.available(self.t);scene=FREQ.state(self.t)['scene']
  for _ in range(2):
   self.e.start_round(self.e.everyone)
   self.e.end_encounter(round_elapsed_seconds=10)
   self.assertEqual(AP.available(self.t),spent)
   self.assertEqual(FREQ.state(self.t)['scene'],scene)
  self.e.end_scene()
  self.assertEqual(AP.available(self.t),AP.maximum(self.t))
  self.assertEqual(FREQ.state(self.t)['scene'],scene+1)
 def test_elapsed_seconds_and_skill_success_do_not_infer_a_scene_boundary(self):
  self.reliable();before=AP.available(self.t);scene=FREQ.state(self.t)['scene']
  for seconds in (0,1,60,3600,86400):
   self.e.advance_time(seconds)
   self.e.common_action(self.t,'육상',3,mode='skill',fixed=[1]*3)
   self.assertEqual(AP.available(self.t),before)
   self.assertEqual(FREQ.state(self.t)['scene'],scene)
 def test_explicit_scene_has_no_fixed_duration_or_automatic_extra_time(self):
  for elapsed in (0,1,73):
   self.setUp();self.reliable();self.e.advance_time(elapsed)
   self.e.end_scene()
   self.assertEqual(self.e.elapsed_seconds,elapsed)
   self.assertEqual(AP.available(self.t),AP.maximum(self.t))
 def test_scene_ends_open_combat_but_does_not_guess_partial_round_seconds(self):
  self.reliable();self.e.start_round(self.e.everyone);self.e.at_round_offset(3)
  self.e.end_scene()
  self.assertFalse(self.e.encounter_active);self.assertIsNone(self.e.round_start_seconds)
  self.assertEqual(self.e.elapsed_seconds,3)
  self.assertEqual(self.e.unresolved_time_intervals[-1]['known_seconds'],3)
  self.assertEqual(AP.available(self.t),AP.maximum(self.t))
 def test_native_feature_with_zero_or_one_ap_is_rejected_before_rng_or_action(self):
  for available in (0,1):
   self.setUp();self.t.spec['ap_spent']=AP.maximum(self.t)-available
   before=deepcopy(self.t.spec);rng=self.e.rng.getstate()
   with self.assertRaises(ValueError):self.reliable()
   self.assertEqual(self.t.spec,before);self.assertEqual(self.e.rng.getstate(),rng)
   self.assertFalse(getattr(self.t,'_action_history',[]))
 def test_exact_native_feature_cost_is_sufficient_and_pays_only_two(self):
  self.t.spec['ap_spent']=AP.maximum(self.t)-2
  out=self.reliable();self.assertTrue(out['check'].passed)
  self.assertEqual(AP.available(self.t),0);self.assertEqual(self.t._action_history,['free'])
 def test_bound_and_removed_reservations_reduce_available_feature_ap(self):
  for key,value in (('ap_bound',AP.maximum(self.t)-1),('ap_bound',{'existing-active-effect':AP.maximum(self.t)-1}),('ap_removed',AP.maximum(self.t)-1)):
   self.setUp();self.t.spec[key]=value;before=deepcopy(self.t.spec)
   with self.assertRaises(ValueError):self.reliable()
   self.assertEqual(self.t.spec,before)
 def test_zero_ap_does_not_block_unpriced_checks_jump_or_pokemon_move(self):
  self.t.spec['ap_spent']=AP.maximum(self.t)
  out=self.e.common_action(self.t,'육상',6,mode='skill',fixed=[2]*3)
  self.assertTrue(out.check.passed)
  self.t.pos=(0,0);self.e.grid=Grid(6,6)
  for actor in self.e.everyone:
   self.e.gm.set_footprint(actor,[(0,0)],reason='GM observed one-cell participant bodies for the AP-free jump')
  out=self.e.jump(self.t,destination=(1,0),apex_height=0,difficult=False,jump_id='zero-ap',reason_text='observed one meter gap',gm_distance=1,clear_path=True)
  self.assertEqual(self.t.pos,(1,0));self.assertEqual(AP.available(self.t),0)
  self.e.rng.seed(27);before=self.enemy.hp
  self.e.use_move(self.p,self.enemy,'move/몸통박치기',set_damage=True)
  self.assertLess(self.enemy.hp,before);self.assertEqual(AP.available(self.t),0)
 def test_gm_can_choose_elapsed_time_after_observing_actual_check(self):
  out=self.e.common_action(self.t,'육상',8,mode='skill',fixed=[3]*3)
  self.assertEqual(out.check.margin,1)
  self.assertEqual(self.e.elapsed_seconds,0)
  # 47 seconds is this GM's explicit world decision, not a rule formula.
  self.e.advance_time(47,[self.t])
  self.assertEqual(self.e.elapsed_seconds,47)
 def test_extended_requires_actual_completed_noncombat_interval(self):
  import common_checks as C
  opts=dict(mode='extended',task_id='repair',interval_id='one',interval={'amount':10,'unit':'minute'},complexity=2,limited=False,fixed=[2]*3)
  before=self.e.rng.getstate()
  out=self.e.common_action(self.t,'육상',6,interval_completed=False,**opts)
  self.assertIsInstance(out,C.PendingDecision);self.assertEqual(self.e.rng.getstate(),before)
  self.assertEqual(self.e.elapsed_seconds,0)
  self.e.start_round(self.e.everyone)
  out=self.e.common_action(self.t,'육상',6,interval_completed=True,**opts)
  self.assertIsInstance(out,C.PendingDecision);self.assertEqual(self.e.rng.getstate(),before)
  self.e.end_encounter(round_elapsed_seconds=0)
  self.e.advance_time(600,[self.t])
  out=self.e.common_action(self.t,'육상',6,interval_completed=True,**opts)
  self.assertEqual(out.result.total,6);self.assertEqual(self.e.elapsed_seconds,600)
  self.assertEqual(self.e._extended_checks['repair']['basis']['interval'],{'amount':10,'unit':'minute'})
  with self.assertRaises(ValueError):self.e.common_action(self.t,'육상',6,interval_completed=True,**opts)
  self.assertEqual(self.e.elapsed_seconds,600)
 def test_gm_duration_native_fossil_activity_costs_chosen_time_even_on_failure(self):
  self.t.spec['skills']['생존']=4
  for i,(minutes,face) in enumerate(((42,6),(91,1))):
   before=self.e.elapsed_seconds
   out=self.e.pokemon_activity(self.t,'fossil',phase='search',skill='생존',site={'name':'survey '+str(i),'fossils_present':False},dc=15,minutes=minutes,fixed=[face]*4)
   self.assertEqual(self.e.elapsed_seconds-before,minutes*60)
   self.assertEqual(out['check'].passed,face==6)
  self.e.start_round(self.e.everyone);before=self.e.elapsed_seconds;rng=self.e.rng.getstate()
  with self.assertRaises(ValueError):self.e.pokemon_activity(self.t,'fossil',phase='search',site={'name':'during battle','fossils_present':False},dc=15,minutes=42)
  self.assertEqual(self.e.elapsed_seconds,before);self.assertEqual(self.e.rng.getstate(),rng)
 def test_action_labels_do_not_invent_numeric_durations(self):
  import action_metadata as A
  source=(ROOT/'input/ch06-gameplay.md').read_text('utf-8').splitlines()[60]
  for phrase in ('몇 초','훨씬 더 빠릅니다','전투 중에 불가능','구체적인 시간은 GM'):self.assertIn(phrase,source)
  for label in ('standard','swift','free','extended'):
   self.assertEqual(A.resolve_feature_action({'frequency':{'action':label}}),(label,''))
  self.reliable()
  self.assertEqual(self.t._action_history,['free']);self.assertEqual(self.e.elapsed_seconds,0)
if __name__=='__main__':
 class Result(unittest.TextTestResult):
  def __init__(self,*a,**kw):super().__init__(*a,**kw);self.rows=[]
  def addSuccess(self,t):super().addSuccess(t);self.rows.append({'id':t._testMethodName,'status':'pass'})
  def addFailure(self,t,e):super().addFailure(t,e);self.rows.append({'id':t._testMethodName,'status':'fail'})
  def addError(self,t,e):super().addError(t,e);self.rows.append({'id':t._testMethodName,'status':'error'})
 result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
 files=['engine/adjudication_guidance.py','data/adjudication-guidance.json','engine/skill_maneuver_actions.py','engine/food_effects.py','engine/combat_social_edges.py','engine/net_capsule.py','engine/precise_actions.py','engine/wild_equipment.py','engine/injury_recovery.py','engine/downtime.py','engine/items.py','engine/gm_state.py','engine/heavy_injury_adapter.py','engine/context_actions.py','engine/pokemon_requests.py','engine/combat_maneuvers.py','data/context-check-policy.json','data/cultivation-policy.json','engine/pokemon_activities.py','engine/action_metadata.py','tools/test_category3_scene_ap.py','engine/engine.py','engine/frequency.py','engine/action_points.py','engine/contest_features.py','engine/common_action_checks.py','engine/common_checks.py','engine/skill_modifiers.py','engine/skill_feature_actions.py','engine/researcher_features.py','engine/ap_roll_bonus.py','engine/trainer_capabilities.py','engine/jump_actions.py','engine/movement_actions.py','engine/capability_actions.py','engine/turn.py','engine/action_lifecycle.py','engine/environmental_effects.py','engine/bandages.py','engine/life.py','engine/temporary_hp.py','engine/combat_timing.py','engine/ruleset.py','data/core-rules.json','data/skill-check-policy.json','data/rulesets.json','output/ruleunits.jsonl','input/ch06-gameplay.md']
 files += ['engine/campaign_rewards.py', 'engine/league_consequences.py', 'data/campaign-reward-policy.json']
 files += ['engine/pokemon_understanding.py', 'engine/regional_pokemon.py', 'engine/source_context.py']
 files += ['engine/blessing_skill_features.py', 'engine/combat_precision_features.py', 'engine/pokemon_intelligence.py', 'engine/pokemon_party.py', 'engine/pokemon_teaching.py', 'data/pokemon-machines.json']

 files += ['engine/arithmetic.py', 'engine/arithmetic_policy.py', 'engine/effect_contracts.py', 'engine/effect_lifetimes.py', 'engine/maneuver_grants.py', 'engine/move_activation.py', 'engine/native_rule_policy.py', 'data/native-rule-policy.json']

 files += ['engine/action_lifecycle.py', 'engine/action_metadata.py', 'engine/action_points.py', 'engine/adjudication_guidance.py', 'engine/ap_roll_bonus.py', 'engine/bandages.py', 'engine/bound_ap.py', 'engine/builder.py', 'engine/capability_actions.py', 'engine/combat_maneuvers.py', 'engine/combat_social_edges.py', 'engine/combat_stage_sources.py', 'engine/combat_timing.py', 'engine/common_action_checks.py', 'engine/common_checks.py', 'engine/contest.py', 'engine/contest_features.py', 'engine/context_actions.py', 'engine/crafting_activities.py', 'engine/custom_species.py', 'engine/damage_reactions.py', 'engine/demo_rulings.py', 'engine/downtime.py', 'engine/effects.py', 'engine/effects_ext.py', 'engine/elemental_connection.py', 'engine/encounter.py', 'engine/enduring_awareness.py', 'engine/engine.py', 'engine/environmental_effects.py', 'engine/focus_tasks.py', 'engine/food_effects.py', 'engine/frequency.py', 'engine/gm_console.py', 'engine/gm_state.py', 'engine/grid.py', 'engine/heavy_injury_adapter.py', 'engine/heavy_injury_kernel.py', 'engine/heavy_standard_adapter.py', 'engine/initiative.py', 'engine/injury_recovery.py', 'engine/items.py', 'engine/jump_actions.py', 'engine/league_agenda.py', 'engine/league_runtime.py', 'engine/life.py', 'engine/maneuver_edges.py', 'engine/movement_actions.py', 'engine/net_capsule.py', 'engine/observed_resolution.py', 'engine/passive_event_profiles.py', 'engine/passive_events.py', 'engine/physical_limits.py', 'engine/physics_maneuvers.py', 'engine/pokemon_activities.py', 'engine/pokemon_requests.py', 'engine/precise_actions.py', 'engine/researcher_features.py', 'engine/resolution_transaction.py', 'engine/rest_intervals.py', 'engine/restorative_items.py', 'engine/root_admission.py', 'engine/root_children.py', 'engine/root_common_checks.py', 'engine/root_common_engine.py', 'engine/root_inputs.py', 'engine/root_machine.py', 'engine/root_resolution.py', 'engine/root_scheduler.py', 'engine/ruleset.py', 'engine/rulings.py', 'engine/skill_feature_actions.py', 'engine/skill_maneuver_actions.py', 'engine/skill_modifiers.py', 'engine/skill_stunts.py', 'engine/skill_targets.py', 'engine/survivalist_features.py', 'engine/temporary_hp.py', 'engine/test_builder.py', 'engine/test_contest.py', 'engine/test_downtime.py', 'engine/test_effects.py', 'engine/test_gm_state.py', 'engine/test_grid.py', 'engine/test_items.py', 'engine/test_maintenance.py', 'engine/test_playthrough.py', 'engine/test_rules.py', 'engine/test_ruleset.py', 'engine/test_rulings.py', 'engine/test_turn.py', 'engine/trainer_capabilities.py', 'engine/turn.py', 'engine/weapon_actions.py', 'engine/wild_equipment.py', 'data/content-source-identities.json', 'data/context-check-policy.json', 'data/skill-check-policy.json', 'data/adjudication-guidance.json', 'data/rulesets.json']
 report={'generated_at':datetime.now(timezone.utc).isoformat(),'successful':result.wasSuccessful(),'scope':['C3-CORE-026','C3-CORE-027','C3-CORE-033'],'results':result.rows,'input_hashes':{f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files}}
 (ROOT/'output/category3-scene-ap-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 raise SystemExit(0 if result.wasSuccessful() else 1)
