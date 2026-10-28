"""Native learned movement, underground action debt, and Teleporter constraints."""
import sys,json,hashlib,unittest
from copy import deepcopy
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from engine import Engine,Rules,Combatant
from grid import Grid
import turn as TURN
import movement_actions as M
import common_checks as C
import state_codec as CODEC
class MovementTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(str(ROOT),ruleset='core')
 def setUp(self):
  self.e=Engine(self.r,seed=833);self.a=Combatant(self.r,{'id':'a','name':'a','kind':'pokemon','level':20,'size':'medium','stats':{'hp':30,'atk':15,'def':10,'spa':15,'spd':10,'spe':10},'movement':{'land':6},'moves':['move/화염방사']})
  self.a.pos=(1,1);self.e.grid=Grid(25,10);self.e.everyone=[self.a];self.e.gm.everyone=[self.a]
 def base(self,values=None):
  self.e.gm.choose_learned_capability_policy(self.a,'move/공중날기','capability_entry',reason='explicit capability paragraph policy')
  return self.e.gm.set_movement_capabilities(self.a,values or {'land':6},basis='base',reason='GM confirms pre-learning species capabilities')
 def turn(self):self.e.start_round([self.a]);self.e.start_of_turn(self.a)
 def test_core_overland_diagonal_budget_and_paid_turn_survive_codec(self):
  self.base({'land':4});self.a.pos=(0,0)
  target=Combatant(self.r,{'id':'far-target','name':'far target','kind':'pokemon','level':20,'size':'Medium','stats':{'hp':30,'atk':10,'def':10,'spa':10,'spd':10,'spe':10},'moves':[]})
  target.pos=(10,10);self.e.everyone=self.e.gm.everyone=[self.a,target]
  self.e.grid=Grid(12,12,blocking=[(x,y) for x in range(12) for y in range(12) if x!=y])
  self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a)
  self.e.approach(self.a,target)
  self.assertEqual((self.a.pos,self.a._diagonal_steps,self.a.budget['shift']),((3,3),3,0))
  loaded=CODEC.load_engine(self.r,json.loads(json.dumps(CODEC.dump_engine(self.e),ensure_ascii=False)))
  actors={c.entity_id:c for c in loaded.everyone};a=actors[self.a.entity_id];target=actors[target.entity_id]
  self.assertEqual((a.pos,a._diagonal_steps),((3,3),3))
  before=deepcopy((a.spec,a.pos,a.budget,loaded.rng.getstate()))
  loaded.approach(a,target)
  self.assertEqual((a.spec,a.pos,a.budget,loaded.rng.getstate()),before)
  loaded.end_of_turn(a);loaded.end_round();loaded.start_round(loaded.everyone);loaded.start_of_turn(a)
  loaded.approach(a,target)
  self.assertEqual((a.pos,a._diagonal_steps,a.budget['shift']),((6,6),3,0))
  self.assertTrue(loaded.validate_state()['valid'])
 def dig(self,surface=False):return self.e.burrow_move(self.a,[self.a.pos,(self.a.pos[0]+1,self.a.pos[1])],diggable=True,reason_text='diggable earth path surveyed',surface=surface)
 def tele(self,dest,**kw):return self.e.teleport(self.a,dest,surface_contact=kw.pop('surface_contact',True),reason_text='GM mapped destination surface',**kw)
 def test_source_scope_hashes_unchanged(self):
  r=json.loads((ROOT/'data/verification/category3-register.json').read_text(encoding='utf-8'))
  for e in r['entries']:
   if e['id'] not in ['C3-CORE-044','C3-CORE-045','C3-CORE-046']:continue
   a=e['source_snapshot']['source'];lines=(ROOT/a['file']).read_text(encoding='utf-8-sig').splitlines();actual='\n'.join(lines[a['start']-1:a['end']])
   self.assertEqual(hashlib.sha256(actual.encode()).hexdigest(),a['excerpt_sha256'])
 def test_each_learned_move_grants_missing_or_adds_existing_capability(self):
  for uid,(mode,bonus) in {'move/구멍파기':('burrow',3),'move/공중날기':('sky',4),'move/다이빙':('swim',3),'move/순간이동':('teleport',4)}.items():
   self.a.moves=[uid];self.base();self.assertEqual(self.e.move_profile(self.a,movement_mode=mode)[0],bonus)
   self.base({'land':6,mode:2});self.assertEqual(self.e.move_profile(self.a,movement_mode=mode)[0],2+bonus)
   self.assertEqual(self.e.move_profile(self.a,movement_mode=mode)[0],2+bonus)
 def test_learning_is_not_current_move_use_frequency_or_six_move_activation(self):
  self.a.moves=['move/구멍파기'];self.base();self.a.move_uses['move/구멍파기']={'used':999};self.a.conditions.add('침묵')
  self.assertEqual(self.e.move_profile(self.a,movement_mode='burrow')[0],3)
  self.a.moves=[]
  with self.assertRaises(ValueError):self.e.move_profile(self.a,movement_mode='burrow')
 def test_current_sheet_never_double_adds_learned_bonuses(self):
  self.a.moves=['move/구멍파기'];self.e.gm.set_movement_capabilities(self.a,{'land':6,'burrow':7},basis='current',reason='sheet includes learned bonus')
  self.assertEqual(self.e.move_profile(self.a,movement_mode='burrow')[0],7)
 def test_actual_levitate_ability_new_four_existing_plus_two(self):
  for ability in ('부유','ability/부유','Levitate'):
   self.setUp();__import__('state_grants').replace_baseline(self.e,self.a,'abilities',[ability]);self.assertIn(ability,self.a.abilities)
   self.base();self.assertEqual(self.e.move_profile(self.a,movement_mode='levitate')[0],4)
   self.base({'land':6,'levitate':3});self.assertEqual(self.e.move_profile(self.a,movement_mode='levitate')[0],5)
   __import__('state_grants').replace_baseline(self.e,self.a,'abilities',[]);self.assertEqual(self.e.move_profile(self.a,movement_mode='levitate')[0],3)
 def test_invalid_basis_selected_source_and_suppressed_ability_do_not_rewrite_sheet(self):
  before=deepcopy(self.a.spec)
  with self.assertRaises(ValueError):self.e.gm.set_movement_capabilities(self.a,{'land':True},basis='base',reason='invalid')
  self.assertEqual(self.a.spec,before)
  self.a.abilities=['ability/부유'];self.base();self.a.abilities_suppressed=True
  with self.assertRaises(ValueError):self.e.move_profile(self.a)
 def test_native_sprint_cost_standard_once_and_extends_actual_shift(self):
  self.turn();rng=self.e.rng.getstate();self.assertTrue(self.e.sprint(self.a,source_policy="ch06_once"));self.assertEqual(self.a.budget['standard'],0)
  target=deepcopy(self.a);target.pos=(20,1)
  self.e.approach(self.a,target,movement_mode='land')
  self.assertEqual(self.a.pos[0],10);self.assertEqual(self.a.budget['shift'],0);self.assertNotIn('질주',self.a.custom_conditions);self.assertEqual(self.e.rng.getstate(),rng)
 def test_sprint_source_conflict_requires_explicit_choice(self):
  self.turn();before=deepcopy(self.a.budget)
  self.assertIsInstance(self.e.sprint(self.a),C.PendingDecision);self.assertEqual(self.a.budget,before)
  self.e.sprint(self.a,source_policy='ch07_turn');M.consume_sprint(self.a);self.assertIn('질주',self.a.custom_conditions)
  self.e.end_of_turn(self.a);self.assertNotIn('질주',self.a.custom_conditions)
 def test_teleport_leaving_adjacency_uses_existing_real_opportunity_attack(self):
  self.a.moves=['move/순간이동'];self.a.side='party';self.base()
  enemy=Combatant(self.r,{'id':'enemy','name':'enemy','kind':'pokemon','level':20,'size':'Medium','stats':{'hp':20,'atk':5,'def':5,'spa':5,'spd':5,'spe':5},'moves':[]});enemy.pos=(0,1);enemy.side='wild';self.e.everyone.append(enemy)
  self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a);self.tele((5,1))
  self.assertTrue(enemy.aoo_used);self.assertTrue(any('기회 공격' in line for line in self.e.log_lines));self.assertEqual(self.a.pos,(5,1))
 def test_no_sprint_stacking_and_unused_sprint_expires_at_turn_end(self):
  self.turn();self.e.sprint(self.a,source_policy="ch06_once")
  with self.assertRaises(ValueError):self.e.sprint(self.a,source_policy="ch06_once")
  self.e.end_of_turn(self.a);self.assertNotIn('질주',self.a.custom_conditions)
 def test_burrow_actual_path_position_tunnel_size_and_standard_upkeep(self):
  self.a.moves.append('move/구멍파기');self.base();self.turn();result=self.dig()
  self.assertEqual((result['position'],result['tunnel_size']),((2,1),'medium'));self.assertTrue(self.a.spec['_burrow']['underground'])
  self.assertEqual(self.e._burrow_tunnels[-1]['body_size'],'medium');self.e.end_of_turn(self.a)
  self.assertEqual(self.a.budget['standard'],0);self.assertFalse(self.a.spec['_burrow'].get('standard_debt',False))
 def test_used_standard_defers_exactly_next_standard_and_surface_does_not_erase_debt(self):
  self.a.moves.append('move/구멍파기');self.base();self.turn();TURN.spend(self.e,self.a,'standard','earlier actual action');self.dig();self.e.end_of_turn(self.a)
  self.assertTrue(self.a.spec['_burrow']['standard_debt']);self.e.start_round([self.a]);self.e.start_of_turn(self.a)
  self.assertEqual(self.a.budget['standard'],0);self.assertFalse(self.a.spec['_burrow']['standard_debt']);self.dig(surface=True);self.e.end_of_turn(self.a)
  self.e.start_round([self.a]);self.e.start_of_turn(self.a);self.assertEqual(self.a.budget['standard'],1)
 def test_remaining_underground_renews_debt_after_preceding_debt_is_paid(self):
  self.a.moves.append('move/구멍파기');self.base();self.turn();TURN.spend(self.e,self.a,'standard','earlier action');self.dig();self.e.end_of_turn(self.a)
  self.e.start_round([self.a]);self.e.start_of_turn(self.a);self.e.end_of_turn(self.a);self.assertTrue(self.a.spec['_burrow']['standard_debt'])
 def test_invalid_burrow_or_omitted_turn_cannot_silently_spend_or_skip_upkeep(self):
  self.a.moves.append('move/구멍파기');self.base();self.turn();before=deepcopy(self.a.budget)
  with self.assertRaises(ValueError):self.e.burrow_move(self.a,[(1,1),(6,1)],diggable=True,reason_text='invalid disconnected path')
  self.assertEqual(self.a.budget,before);self.dig();self.e.end_of_turn(self.a);self.e.start_round([self.a])
  with self.assertRaises(ValueError):self.e.end_round()
 def test_underground_debt_snapshot_and_unresolved_other_loss_conjunction(self):
  self.a.moves.append('move/구멍파기');self.base();self.turn();TURN.spend(self.e,self.a,'standard','earlier action');self.dig();self.e.end_of_turn(self.a);self.e.gm.snapshot('debt')
  self.e.start_round([self.a]);self.e.start_of_turn(self.a);self.e.gm.restore('debt');self.assertTrue(self.a.spec['_burrow']['standard_debt'])
  self.e.start_round([self.a]);self.a.pending_action_loss={'standard':1};before=deepcopy(self.a.budget)
  with self.assertRaises(ValueError):self.e.start_of_turn(self.a)
  self.assertIsNone(self.e._active_turn_actor);self.assertEqual(self.a.budget,before)
 def test_aerial_levitate_height_and_real_position(self):
  self.a.abilities=['부유'];self.base();self.turn();before=deepcopy(self.a.budget)
  with self.assertRaises(ValueError):self.e.aerial_move(self.a,(1,1),mode='levitate',altitude=3,reason_text='above height limit')
  self.assertEqual(self.a.budget,before)
  result=self.e.aerial_move(self.a,(1,1),mode='levitate',altitude=2,reason_text='vertical ascent')
  self.assertEqual((result['altitude'],self.a.budget['shift']),(2,0));self.assertTrue(self.a.airborne)
 def test_teleport_actual_shift_los_and_once_per_round(self):
  self.a.moves.append('move/순간이동');self.base();self.turn();before=self.e.rng.getstate();self.tele((5,1))
  self.assertEqual((self.a.pos,self.a.budget['shift']),((5,1),0));self.assertEqual(self.e.rng.getstate(),before)
  with self.assertRaises(ValueError):self.tele((6,1))
  self.e.end_of_turn(self.a);self.e.start_round([self.a]);self.e.start_of_turn(self.a);self.tele((9,1));self.assertEqual(self.a.pos,(9,1))
 def test_teleport_does_not_gain_sprint_distance_or_use_walking_path(self):
  self.a.moves.append('move/순간이동');self.base();self.turn();self.e.sprint(self.a,source_policy="ch06_once");before=deepcopy(self.a.budget)
  with self.assertRaises(ValueError):self.tele((7,1))
  self.assertEqual(self.a.budget,before)
  with self.assertRaises(ValueError):self.e.approach(self.a,type('Target',(),{'pos':(12,1)})(),movement_mode='teleport')
 def test_teleport_blocked_los_no_surface_and_unpossessed_capability_are_atomic(self):
  self.a.moves.append('move/순간이동');self.base();self.turn();before=deepcopy(self.a.budget);self.e.grid.blocking.add((3,1))
  with self.assertRaises(ValueError):self.tele((5,1))
  self.e.grid.blocking.clear()
  with self.assertRaises(ValueError):self.tele((2,1),surface_contact=False,altitude=1,gm_distance=2)
  self.a.moves=[]
  with self.assertRaises(ValueError):self.tele((2,1))
  self.assertEqual(self.a.budget,before);self.assertEqual(self.a.pos,(1,1))
 def test_teleport_air_levitate_limit_and_sky_ambiguity_preserved(self):
  self.a.moves=['move/순간이동'];self.a.abilities=['부유'];self.base();self.turn()
  with self.assertRaises(ValueError):self.tele((1,1),surface_contact=False,altitude=3)
  self.tele((1,1),surface_contact=False,altitude=2);self.assertTrue(self.a.airborne)
  self.e.end_of_turn(self.a);self.e.start_round([self.a]);self.e.start_of_turn(self.a);self.a.abilities=[];self.a.moves.append('move/공중날기')
  result=self.tele((2,1),surface_contact=False,altitude=3,gm_distance=2);self.assertIsInstance(result,C.PendingDecision);self.assertEqual(self.a.budget['shift'],1)
  self.tele((2,1),surface_contact=False,altitude=3,gm_distance=2,sky_air_policy='sky_unlimited');self.assertEqual(self.a.pos,(2,1))
 def test_noncombat_teleport_has_no_invented_once_per_day_limit_and_snapshot_restores(self):
  self.a.moves=['move/순간이동'];self.base();self.e.gm.snapshot('before')
  self.tele((3,1));self.tele((5,1));self.e.gm.restore('before');self.assertEqual(self.a.pos,(1,1));self.assertNotIn('_teleport',self.a.spec)
if __name__=='__main__':
 class Result(unittest.TextTestResult):
  def __init__(self,*a,**kw):super().__init__(*a,**kw);self.rows=[]
  def addSuccess(self,t):super().addSuccess(t);self.rows.append({'id':t._testMethodName,'status':'pass'})
  def addFailure(self,t,e):super().addFailure(t,e);self.rows.append({'id':t._testMethodName,'status':'fail'})
  def addError(self,t,e):super().addError(t,e);self.rows.append({'id':t._testMethodName,'status':'error'})
 result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(MovementTests))
 files=['engine/adjudication_guidance.py','data/adjudication-guidance.json','engine/skill_maneuver_actions.py','engine/food_effects.py','engine/combat_social_edges.py','engine/net_capsule.py','engine/trainer_capabilities.py','engine/skill_feature_actions.py','engine/researcher_features.py','engine/precise_actions.py','engine/environmental_effects.py','engine/wild_equipment.py','engine/injury_recovery.py','engine/downtime.py','engine/items.py','engine/skill_modifiers.py','engine/common_action_checks.py','engine/heavy_injury_adapter.py','engine/jump_actions.py','engine/context_actions.py','engine/pokemon_requests.py','engine/combat_timing.py','engine/combat_maneuvers.py','data/context-check-policy.json','data/cultivation-policy.json','engine/weapon_actions.py','data/weapon-policy.json','engine/bandages.py','engine/crafting_activities.py','engine/contest_features.py','data/planter-policy.json','tools/test_category3_movement.py','engine/movement_actions.py','engine/engine.py','engine/turn.py','engine/effects_ext.py','engine/action_lifecycle.py','engine/capability_actions.py','engine/physical_limits.py','engine/gm_state.py','engine/grid.py','engine/ruleset.py','engine/temporary_hp.py','engine/common_checks.py','data/rulesets.json','data/core-rules.json','data/capability-policy.json','data/conditions.json','output/ruleunits.jsonl','output/entities/moves.json','input/ch06-gameplay.md','input/ch07-combat.md']
 files += ['engine/campaign_rewards.py', 'engine/league_consequences.py', 'data/campaign-reward-policy.json']
 files += ['engine/pokemon_understanding.py', 'engine/regional_pokemon.py', 'engine/source_context.py']
 files += ['engine/blessing_skill_features.py', 'engine/combat_precision_features.py', 'engine/pokemon_intelligence.py', 'engine/pokemon_party.py', 'engine/pokemon_teaching.py', 'data/pokemon-machines.json']

 files += ['engine/arithmetic.py', 'engine/arithmetic_policy.py', 'engine/effect_contracts.py', 'engine/effect_lifetimes.py', 'engine/maneuver_grants.py', 'engine/move_activation.py', 'engine/native_rule_policy.py', 'data/native-rule-policy.json']

 files += ['engine/action_lifecycle.py', 'engine/action_metadata.py', 'engine/action_points.py', 'engine/adjudication_guidance.py', 'engine/ap_roll_bonus.py', 'engine/bandages.py', 'engine/bound_ap.py', 'engine/builder.py', 'engine/capability_actions.py', 'engine/combat_maneuvers.py', 'engine/combat_social_edges.py', 'engine/combat_stage_sources.py', 'engine/combat_timing.py', 'engine/common_action_checks.py', 'engine/common_checks.py', 'engine/contest.py', 'engine/contest_features.py', 'engine/context_actions.py', 'engine/crafting_activities.py', 'engine/custom_species.py', 'engine/damage_reactions.py', 'engine/demo_rulings.py', 'engine/downtime.py', 'engine/effects.py', 'engine/effects_ext.py', 'engine/elemental_connection.py', 'engine/encounter.py', 'engine/enduring_awareness.py', 'engine/engine.py', 'engine/environmental_effects.py', 'engine/focus_tasks.py', 'engine/food_effects.py', 'engine/frequency.py', 'engine/gm_console.py', 'engine/gm_state.py', 'engine/grid.py', 'engine/heavy_injury_adapter.py', 'engine/heavy_injury_kernel.py', 'engine/heavy_standard_adapter.py', 'engine/initiative.py', 'engine/injury_recovery.py', 'engine/items.py', 'engine/jump_actions.py', 'engine/league_agenda.py', 'engine/league_runtime.py', 'engine/life.py', 'engine/maneuver_edges.py', 'engine/movement_actions.py', 'engine/net_capsule.py', 'engine/observed_resolution.py', 'engine/passive_event_profiles.py', 'engine/passive_events.py', 'engine/physical_limits.py', 'engine/physics_maneuvers.py', 'engine/pokemon_activities.py', 'engine/pokemon_requests.py', 'engine/precise_actions.py', 'engine/researcher_features.py', 'engine/resolution_transaction.py', 'engine/rest_intervals.py', 'engine/restorative_items.py', 'engine/root_admission.py', 'engine/root_children.py', 'engine/root_common_checks.py', 'engine/root_common_engine.py', 'engine/root_inputs.py', 'engine/root_machine.py', 'engine/root_resolution.py', 'engine/root_scheduler.py', 'engine/ruleset.py', 'engine/rulings.py', 'engine/skill_feature_actions.py', 'engine/skill_maneuver_actions.py', 'engine/skill_modifiers.py', 'engine/skill_stunts.py', 'engine/skill_targets.py', 'engine/survivalist_features.py', 'engine/temporary_hp.py', 'engine/test_builder.py', 'engine/test_contest.py', 'engine/test_downtime.py', 'engine/test_effects.py', 'engine/test_gm_state.py', 'engine/test_grid.py', 'engine/test_items.py', 'engine/test_maintenance.py', 'engine/test_playthrough.py', 'engine/test_rules.py', 'engine/test_ruleset.py', 'engine/test_rulings.py', 'engine/test_turn.py', 'engine/trainer_capabilities.py', 'engine/turn.py', 'engine/weapon_actions.py', 'engine/wild_equipment.py', 'data/content-source-identities.json', 'data/context-check-policy.json', 'data/skill-check-policy.json', 'data/adjudication-guidance.json', 'data/rulesets.json']
 report={'generated_at':datetime.now(timezone.utc).isoformat(),'successful':result.wasSuccessful(),'scope':['C3-CORE-044','C3-CORE-045','C3-CORE-046'],'results':result.rows,'input_hashes':{f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files}}
 (ROOT/'output/category3-movement-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 raise SystemExit(0 if result.wasSuccessful() else 1)
