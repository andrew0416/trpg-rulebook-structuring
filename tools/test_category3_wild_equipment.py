"""Actual bait, Standard replacement, and sourced modern Snare bonus."""
from copy import deepcopy
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'));sys.path.insert(0,str(ROOT/'tools'))
import test_category3_pokemon_activities as _fixture_test_category3_pokemon_activities
from engine import Rules
import wild_equipment as W
import turn as TURN
from action_metadata import ActionCost
class WildEquipmentTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(str(ROOT),ruleset='core')
 actor=_fixture_test_category3_pokemon_activities.PokemonActivityTests.actor
 act=_fixture_test_category3_pokemon_activities.PokemonActivityTests.act
 state=_fixture_test_category3_pokemon_activities.PokemonActivityTests.state
 def setUp(self):_fixture_test_category3_pokemon_activities.PokemonActivityTests.setUp(self);self.a.spec['items']['미끼']=2;self.p.spec['skills']['집중']='숙련'
 def distract(self,faces=None):return self.act('distract_bait',target=self.p,fixed=faces or [1]*4)
 def tech(self,*names):self.a.spec['classes']=['class/포획전문가'];self.a.spec['capture_techniques']=list(names)
 def place(self):
  self.p.spec['species']='잉어킹';return self.act('attract_bait',phase='place',bait_id='bait',habitat={'region':'local river','species':['잉어킹'],'reason':'GM observed local species'})
 def test_attraction_reserves_actual_bait_and_three_fifteen_minute_failures_consume(self):
  self.place();self.assertEqual(self.a.spec['items']['미끼'],1);self.assertEqual(self.e.elapsed_seconds,0)
  for _ in range(3):r=self.act('attract_bait',phase='wait',bait_id='bait',fixed=14)
  self.assertEqual(self.e.elapsed_seconds,2700);self.assertEqual(r['status'],'consumed_without_encounter');self.assertEqual(self.a.spec['items']['미끼'],1)
  with self.assertRaises(ValueError):self.act('attract_bait',phase='wait',bait_id='bait',fixed=20)
 def test_attraction_equal_fifteen_waits_for_gm_actual_similar_party_encounter(self):
  self.place();r=self.act('attract_bait',phase='wait',bait_id='bait',fixed=15);self.assertEqual(r['status'],'awaiting_encounter');self.assertEqual(self.e.elapsed_seconds,900)
  self.act('attract_bait',phase='select',bait_id='bait');self.q.spec['trainer_id']=self.a.spec['id'];r=self.act('attract_bait',phase='encounter',bait_id='bait',target=self.p,party=[self.q],level_match_reason='GM selected comparable level20 encounter')
  self.assertIs(r['target'],self.p);self.assertFalse(self.p.captured);self.assertEqual(r['party_levels'],{self.q.spec['id']:20})
  with self.assertRaises(ValueError):self.act('attract_bait',phase='wait',bait_id='bait',fixed=20)
 def test_tools_trade_requires_real_class_skills_selected_source_and_adds_four(self):
  self.tech('작업 도구');self.place();self.a.spec['classes']=[];before=self.state()
  with self.assertRaises(ValueError):self.act('attract_bait',phase='wait',bait_id='bait',fixed=11)
  self.assertEqual(before,self.state());self.a.spec['classes']=['class/포획전문가'];r=self.act('attract_bait',phase='wait',bait_id='bait',fixed=11);self.assertEqual(r['checks'][-1]['total'],15)
 def test_tools_trade_actual_lure_and_reel_producers_apply_four_and_two(self):
  self.tech('작업 도구');self.a.spec['items'].update({'대단한낚싯대':1,'루어':1});self.act('fishing',phase='start',rod='대단한낚싯대',attachment='루어')
  r=self.act('fishing',phase='wait',roll_d20=11);self.assertEqual(r['bite_total'],15);self.assertEqual(r['bite_bonus'],4);self.assertEqual(self.e.elapsed_seconds,300)
  r=self.act('fishing',phase='reel',target=self.p,fixed=[1,1,2,2]);self.assertTrue(r['check'].passed);self.assertEqual(r['check'].total,8);self.assertEqual(self.a.spec['fishing_session']['status'],'landed')
 def test_tools_trade_ball_accuracy_bonus_is_not_capture_result_bonus(self):
  self.tech('작업 도구');self.a.spec['items']['몬스터볼']=1;self.p.spec['evolutions_remaining']=0
  self.e.throw_ball(self.a,self.p,fixed_accuracy=5,fixed_capture=7);r=self.a.spec['capture_attempts']['capture-1'];self.assertTrue(r['hit']);self.assertEqual(r['tools_accuracy'],2);self.assertEqual(r['capture_total'],10);self.assertFalse(r['captured'])
 def test_invalid_attraction_inputs_do_not_consume_clock_or_rng(self):
  self.place();before=self.state()
  with self.assertRaises(ValueError):self.act('attract_bait',phase='wait',bait_id='bait',fixed=21)
  self.assertEqual(before,self.state())
  with self.assertRaises(ValueError):self.act('attract_bait',phase='encounter',bait_id='bait',target=self.p,party=[self.q],level_match_reason='no successful check')
  self.assertEqual(before,self.state())
 def test_focus_exact_dc12_resists_and_failed_real_check_creates_distraction(self):
  self.a.budget={'standard':1,'shift':1,'swift':1};r=self.distract([3]*4);self.assertEqual(r['check'].total,12);self.assertFalse(W.pending(self.p));self.assertEqual(self.a.budget['standard'],0);self.assertEqual(self.a.spec['items']['미끼'],1)
  self.a.budget['standard']=1;r=self.distract();self.assertTrue(W.pending(self.p));self.assertEqual(r['check'].dc,12);self.assertEqual(self.a.spec['items']['미끼'],0)
 def test_invalid_target_dice_or_no_action_never_consumes_bait(self):
  before=self.state()
  with self.assertRaises(ValueError):self.distract([1])
  self.assertEqual(before,self.state());self.p.spec['trainer_id']='owner'
  with self.assertRaises(ValueError):self.distract()
  self.p.spec.pop('trainer_id');self.a.budget={'standard':0,'shift':1,'swift':1};self.assertIs(self.distract(),False);self.assertEqual(self.a.spec['items']['미끼'],2)
 def test_actual_turn_next_standard_eats_without_original_move_rng_frequency_or_damage(self):
  actors=[self.a,self.p,self.q];self.e.start_round(actors);self.e.start_of_turn(self.a);self.distract();self.e.end_of_turn(self.a);self.e.start_of_turn(self.p)
  self.assertTrue(TURN.spend(self.e,self.p,'shift','move first'));self.assertTrue(W.pending(self.p));before=(self.e.rng.getstate(),self.q.hp,dict(self.p.move_uses))
  self.assertEqual(self.e.use_move(self.p,self.q,'struggle',set_damage=True),0);self.assertEqual(before,(self.e.rng.getstate(),self.q.hp,dict(self.p.move_uses)));self.assertEqual(self.p.budget['standard'],0);self.assertEqual(self.p.spec['bait_distraction']['status'],'eaten')
  self.assertEqual(self.p._action_history.count('standard'),1)
  self.e.end_of_turn(self.p);self.e.start_round(actors);self.e.start_of_turn(self.p);rng=self.e.rng.getstate();self.e.use_move(self.p,self.q,'struggle',set_damage=True);self.assertNotEqual(self.e.rng.getstate(),rng)
 def test_unconscious_sleeping_or_no_standard_preserves_distraction(self):
  self.distract()
  for cond in ('잠듦','얼음'):
   self.p.conditions.add(cond);self.assertFalse(TURN.spend(self.e,self.p,'standard','blocked'));self.assertTrue(W.pending(self.p));self.p.conditions.remove(cond)
  self.p.hp=0;self.assertFalse(TURN.spend(self.e,self.p,'standard','unconscious'));self.assertTrue(W.pending(self.p));self.p.hp=20;self.p.budget={'standard':0,'shift':1,'swift':1};self.assertFalse(TURN.spend(self.e,self.p,'standard','no token'));self.assertTrue(W.pending(self.p))
 def test_full_compound_and_standard_downgrade_are_explicitly_held(self):
  self.distract();self.p.budget={'standard':1,'shift':1,'swift':1}
  for kind in ('full',ActionCost(('standard','swift'))):
   before=deepcopy(self.p.budget)
   with self.assertRaises(ValueError):TURN.spend(self.e,self.p,kind,'unresolved composition')
   self.assertEqual(self.p.budget,before);self.assertTrue(W.pending(self.p))
  self.p.budget['shift']=0
  with self.assertRaises(ValueError):TURN.spend(self.e,self.p,'shift','downgrade')
  self.assertEqual(self.p.budget['standard'],1);self.assertTrue(W.pending(self.p))
 def test_heavy_injury_eating_is_explicitly_held_before_cost(self):
  self.distract();self.e.start_round([self.a,self.p]);self.e.start_of_turn(self.p);self.p.injuries=5;before=dict(self.p.budget)
  with self.assertRaises(ValueError):TURN.spend(self.e,self.p,'standard','heavy eating')
  self.assertEqual(self.p.budget,before);self.assertTrue(W.pending(self.p))
 def test_snare_actual_bait_adds_two_to_modern_capture_and_consumed_state_adds_zero(self):
  self.tech('덫');self.distract();self.a.spec['items']['몬스터볼']=1;self.p.spec['evolutions_remaining']=0
  self.assertTrue(self.e.throw_ball(self.a,self.p,fixed_accuracy=20,fixed_capture=7));r=self.a.spec['capture_attempts']['capture-1'];self.assertEqual(r['snare_bonus'],2);self.assertEqual(r['capture_total'],12);self.assertEqual(self.a.spec['items']['몬스터볼'],0)
  self.setUp();self.tech('덫');self.distract();self.assertFalse(TURN.spend(self.e,self.p,'standard','eat'));self.a.spec['items']['몬스터볼']=1;self.p.spec['evolutions_remaining']=0
  self.assertFalse(self.e.throw_ball(self.a,self.p,fixed_accuracy=20,fixed_capture=7));self.assertEqual(self.a.spec['capture_attempts']['capture-1']['snare_bonus'],0)
 def test_unacquired_snare_cannot_use_bait_bonus_and_bad_acquisition_costs_nothing(self):
  self.distract();self.assertEqual(W.snare_bonus(self.e,self.a,self.p),0);self.tech('덫');self.a.spec['skills']['교활']='미숙';self.a.spec['skills']['통찰']='미숙';self.a.spec['items']['몬스터볼']=1;before=self.state()
  with self.assertRaises(ValueError):self.e.throw_ball(self.a,self.p,fixed_accuracy=20,fixed_capture=20)
  self.assertEqual(before,self.state())
if __name__=='__main__':
 class Result(unittest.TextTestResult):
  def __init__(self,*a,**kw):super().__init__(*a,**kw);self.rows=[]
  def addSuccess(self,t):super().addSuccess(t);self.rows.append({'id':t._testMethodName,'status':'pass'})
  def addFailure(self,t,e):super().addFailure(t,e);self.rows.append({'id':t._testMethodName,'status':'fail'})
  def addError(self,t,e):super().addError(t,e);self.rows.append({'id':t._testMethodName,'status':'error'})
 result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(WildEquipmentTests))
 files=['engine/adjudication_guidance.py','data/adjudication-guidance.json','engine/skill_maneuver_actions.py','engine/food_effects.py','engine/combat_social_edges.py','engine/net_capsule.py','engine/trainer_capabilities.py','engine/skill_feature_actions.py','engine/researcher_features.py','engine/precise_actions.py','engine/environmental_effects.py','engine/injury_recovery.py','engine/downtime.py','engine/items.py','engine/common_action_checks.py','engine/gm_state.py','engine/heavy_injury_adapter.py','engine/jump_actions.py','engine/context_actions.py','engine/pokemon_requests.py','engine/combat_timing.py','engine/combat_maneuvers.py','data/context-check-policy.json','data/cultivation-policy.json','engine/wild_equipment.py','engine/pokemon_activities.py','engine/engine.py','engine/turn.py','engine/action_lifecycle.py','engine/common_checks.py','engine/skill_modifiers.py','engine/crafting_activities.py','data/rulesets.json','data/skill-check-policy.json','data/core-rules.json','output/ruleunits.jsonl','input/ch04-trainer-classes.md','input/ch09-equipment.md','input/supp-errata.md','tools/test_category3_wild_equipment.py']
 files += ['engine/campaign_rewards.py', 'engine/league_consequences.py', 'data/campaign-reward-policy.json']
 files += ['engine/pokemon_understanding.py', 'engine/regional_pokemon.py', 'engine/source_context.py']
 files += ['engine/blessing_skill_features.py', 'engine/combat_precision_features.py', 'engine/pokemon_intelligence.py', 'engine/pokemon_party.py', 'engine/pokemon_teaching.py', 'data/pokemon-machines.json']

 files += ['engine/arithmetic.py', 'engine/arithmetic_policy.py', 'engine/effect_contracts.py', 'engine/effect_lifetimes.py', 'engine/maneuver_grants.py', 'engine/move_activation.py', 'engine/native_rule_policy.py', 'data/native-rule-policy.json']

 files += ['engine/action_lifecycle.py', 'engine/action_metadata.py', 'engine/action_points.py', 'engine/adjudication_guidance.py', 'engine/ap_roll_bonus.py', 'engine/bandages.py', 'engine/bound_ap.py', 'engine/builder.py', 'engine/capability_actions.py', 'engine/combat_maneuvers.py', 'engine/combat_social_edges.py', 'engine/combat_stage_sources.py', 'engine/combat_timing.py', 'engine/common_action_checks.py', 'engine/common_checks.py', 'engine/contest.py', 'engine/contest_features.py', 'engine/context_actions.py', 'engine/crafting_activities.py', 'engine/custom_species.py', 'engine/damage_reactions.py', 'engine/demo_rulings.py', 'engine/downtime.py', 'engine/effects.py', 'engine/effects_ext.py', 'engine/elemental_connection.py', 'engine/encounter.py', 'engine/enduring_awareness.py', 'engine/engine.py', 'engine/environmental_effects.py', 'engine/focus_tasks.py', 'engine/food_effects.py', 'engine/frequency.py', 'engine/gm_console.py', 'engine/gm_state.py', 'engine/grid.py', 'engine/heavy_injury_adapter.py', 'engine/heavy_injury_kernel.py', 'engine/heavy_standard_adapter.py', 'engine/initiative.py', 'engine/injury_recovery.py', 'engine/items.py', 'engine/jump_actions.py', 'engine/league_agenda.py', 'engine/league_runtime.py', 'engine/life.py', 'engine/maneuver_edges.py', 'engine/movement_actions.py', 'engine/net_capsule.py', 'engine/observed_resolution.py', 'engine/passive_event_profiles.py', 'engine/passive_events.py', 'engine/physical_limits.py', 'engine/physics_maneuvers.py', 'engine/pokemon_activities.py', 'engine/pokemon_requests.py', 'engine/precise_actions.py', 'engine/researcher_features.py', 'engine/resolution_transaction.py', 'engine/rest_intervals.py', 'engine/restorative_items.py', 'engine/root_admission.py', 'engine/root_children.py', 'engine/root_common_checks.py', 'engine/root_common_engine.py', 'engine/root_inputs.py', 'engine/root_machine.py', 'engine/root_resolution.py', 'engine/root_scheduler.py', 'engine/ruleset.py', 'engine/rulings.py', 'engine/skill_feature_actions.py', 'engine/skill_maneuver_actions.py', 'engine/skill_modifiers.py', 'engine/skill_stunts.py', 'engine/skill_targets.py', 'engine/survivalist_features.py', 'engine/temporary_hp.py', 'engine/test_builder.py', 'engine/test_contest.py', 'engine/test_downtime.py', 'engine/test_effects.py', 'engine/test_gm_state.py', 'engine/test_grid.py', 'engine/test_items.py', 'engine/test_maintenance.py', 'engine/test_playthrough.py', 'engine/test_rules.py', 'engine/test_ruleset.py', 'engine/test_rulings.py', 'engine/test_turn.py', 'engine/trainer_capabilities.py', 'engine/turn.py', 'engine/weapon_actions.py', 'engine/wild_equipment.py', 'data/content-source-identities.json', 'data/context-check-policy.json', 'data/skill-check-policy.json', 'data/adjudication-guidance.json', 'data/rulesets.json']
 report={'generated_at':datetime.now(timezone.utc).isoformat(),'successful':result.wasSuccessful(),'scope':['DOMAIN-068 bait partial','C3-EX-123 Snare bait branch partial'],'completion':'partial; other restraint producers and Standard compositions unresolved','results':result.rows,'input_hashes':{f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files}}
 (ROOT/'output/category3-wild-equipment-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 raise SystemExit(0 if result.wasSuccessful() else 1)
