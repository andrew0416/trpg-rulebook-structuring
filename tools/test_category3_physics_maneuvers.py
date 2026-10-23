"""Native Push/Trip differences and explicit unresolved repetition boundary."""
from pathlib import Path
from copy import deepcopy
from datetime import datetime,timezone
from unittest.mock import patch
import hashlib,json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from engine import Rules,Engine,Combatant
from grid import Grid
import common_checks as C
import skill_feature_actions as SF
import capability_actions as CAP
import turn as TURN
import physics_maneuvers as P
class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(ROOT)
 def actor(self,name,side,pos):
  return Combatant(self.r,dict(id='trainer/'+name,name=name,kind='trainer',size='Medium',side=side,pos=pos,level=20,stats=dict(hp=20,atk=10,**{'def':10},spa=10,spd=10,spe=1),skills={'전투':4,'육상':4,'곡예':4,'은신':4},movement={'land':6,'power':4},weight_kg=30,feats=[]))
 def setUp(self):
  self.e=Engine(self.r,7);self.a=self.actor('A','party',(1,1));self.b=self.actor('B','wild',(2,1));self.w=self.actor('W','wild',(1,2))
  self.e.everyone=[self.a,self.b];self.e.gm.everyone=self.e.everyone;self.e.grid=Grid(8,8)
  self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a,initiative_count=20)
 def options(self,**changes):
  out=dict(challenger_skill='전투',defender_skill='전투',fixed_accuracy=20,challenger_options={'fixed':[3]*4},defender_options={'fixed':[2]*4});out.update(changes);return out
 def push(self,**changes):return self.e.push(self.a,self.b,**self.options(**changes))
 def trip(self,**changes):return self.e.trip(self.a,self.b,**self.options(**changes))
 def state(self):return deepcopy((self.a.budget,self.a.hp,self.b.hp,self.a.pos,self.b.pos,self.e.rng.getstate(),self.b.conditions))
 def test_push_actual_standard_accuracy_four_and_world_position_without_free_follow(self):
  out=self.push(fixed_accuracy=4);self.assertEqual(out['target_position'],(3,1));self.assertEqual(self.a.pos,(1,1));self.assertEqual(self.a.budget,{'standard':0,'shift':1,'swift':1});self.assertFalse(self.b.aoo_used)
 def test_trip_actual_accuracy_six_equality_status_and_native_movement_denial(self):
  self.assertTrue(self.trip(fixed_accuracy=6));self.assertIn('넘어짐',self.b.conditions);self.assertEqual(self.b.evasion('변화'),0)
  TURN.reset_budget(self.e,self.b);before=self.b.pos;self.e.approach(self.b,self.a,reach=0);self.assertEqual(self.b.pos,before)
 def test_same_accuracy_roll_can_hit_push_but_miss_trip(self):
  self.assertTrue(self.push(fixed_accuracy=4));self.setUp();self.assertFalse(self.trip(fixed_accuracy=4));self.assertNotIn('넘어짐',self.b.conditions)
 def test_opposed_tie_defends_for_both_without_reusing_dc_equality_rule(self):
  for kind in ('push','trip'):
   self.setUp();self.assertFalse(getattr(self,kind)(defender_options={'fixed':[3]*4}));self.assertEqual(self.b.pos,(2,1));self.assertNotIn('넘어짐',self.b.conditions)
 def test_each_side_can_independently_choose_its_allowed_skill(self):
  for kind,other in [('push','육상'),('trip','곡예')]:
   for chosen_a,chosen_b in [('전투',other),(other,'전투'),(other,other)]:
    self.setUp();self.assertTrue(getattr(self,kind)(challenger_skill=chosen_a,defender_skill=chosen_b))
 def test_push_athletics_and_trip_acrobatics_are_not_interchangeable(self):
  for kind,wrong in [('push','곡예'),('trip','육상')]:
   self.setUp();before=self.state()
   with self.assertRaises(ValueError):getattr(self,kind)(defender_skill=wrong)
   self.assertEqual(self.state(),before)
 def test_heavy_lifting_exact_upper_limit_allowed_but_heavier_rejected(self):
  self.b.spec['weight_kg']=CAP.limits(self.a)['heavy'][1];self.assertTrue(self.push())
  self.setUp();self.b.spec['weight_kg']=CAP.limits(self.a)['heavy'][1]+.1;before=self.state()
  with self.assertRaises(ValueError):self.push()
  self.assertEqual(self.state(),before)
 def test_missing_actual_weight_or_power_never_guessed_from_size_or_rank(self):
  for key,actor in [('weight_kg',self.b),('power',self.a)]:
   if key=='power':actor.spec['movement'].pop(key)
   else:actor.spec.pop(key)
   before=self.state()
   with self.assertRaises(ValueError):self.push()
   self.assertEqual(self.state(),before)
   actor.spec[key]=30 if key=='weight_kg' else 4
 def test_ac_miss_does_not_roll_opposed_or_change_target(self):
  for kind in ('push','trip'):
   self.setUp();state=self.e.rng.getstate()
   with patch.object(self.e,'opposed_check',wraps=self.e.opposed_check) as opposed:
    self.assertFalse(getattr(self,kind)(fixed_accuracy=1));self.assertEqual(opposed.call_count,0)
   self.assertEqual(self.e.rng.getstate(),state);self.assertEqual(self.b.pos,(2,1));self.assertEqual(self.a.budget['standard'],0)
 def test_native_aoo_from_other_enemy_but_not_the_maneuver_target(self):
  self.e.everyone.append(self.w);TURN.reset_budget(self.e,self.w)
  self.assertTrue(self.trip());self.assertTrue(self.w.aoo_used);self.assertFalse(self.b.aoo_used)
 def test_repeat_push_is_pre_cost_pending_not_invented_same_roll_or_new_standard(self):
  before=self.state();out=self.push(follow_steps=2);self.assertIsInstance(out,C.PendingDecision);self.assertEqual(self.state(),before)
 def test_collision_and_diagonal_forced_geometry_are_explicit_pending(self):
  self.e.grid.blocking.add((3,1));before=self.state();self.assertIsInstance(self.push(),C.PendingDecision);self.assertEqual(self.state(),before)
  self.e.grid.blocking.clear();self.b.pos=(2,2);before=self.state();self.assertIsInstance(self.push(),C.PendingDecision);self.assertEqual(self.state(),before)
 def test_context_cannot_spoof_an_unrelated_terrain_bonus(self):
  for kind in ('push','trip'):
   self.setUp();before=self.state()
   with self.assertRaises(ValueError):getattr(self,kind)(defender_options={'fixed':[2]*4,'skill_context':{'purpose':'climb','reason':'different'}})
   self.assertEqual(self.state(),before)
 def feature_options(self,bad=False):
  self.a.spec['feats']=[SF.MONKEY];self.b.spec['feats']=[SF.MONKEY]
  return self.options(challenger_options={'roll_id':'a','fixed':[1]*4,'feature':SF.MONKEY,'feature_options':{'decision':lambda first:True,'reroll_faces':[4]*4}},defender_options={'roll_id':'b','fixed':[1]*4,'feature':SF.MONKEY,'feature_options':{'decision':(lambda first:'bad') if bad else (lambda first:False)}})
 def test_observed_later_choice_retry_keeps_first_roll_standard_and_accuracy(self):
  for kind in ('push','trip'):
   self.setUp();method=getattr(self.e,kind)
   with patch.object(self.e,'accuracy_check',wraps=self.e.accuracy_check) as accuracy:
    with self.assertRaises(ValueError):method(self.a,self.b,**self.feature_options(True))
    first=SF.event(self.e,self.a,'a').first;before=self.e.rng.getstate();self.assertEqual(self.a.budget['standard'],0);self.assertEqual(accuracy.call_count,1)
    self.assertTrue(method(self.a,self.b,**self.feature_options()));self.assertEqual(accuracy.call_count,1);self.assertEqual(self.e.rng.getstate(),before);self.assertIs(SF.event(self.e,self.a,'a').first,first)
 def test_pending_maneuver_cannot_change_actual_skill_context_or_accuracy(self):
  with self.assertRaises(ValueError):self.e.trip(self.a,self.b,**self.feature_options(True))
  opts=self.feature_options();opts['fixed_accuracy']=19
  with self.assertRaises(ValueError):self.e.trip(self.a,self.b,**opts)
  self.assertTrue(self.e.trip(self.a,self.b,**self.feature_options()))
 def test_native_push_moves_onto_actual_enter_cell_consumer_once(self):
  import effects_ext as EXT
  with patch.object(EXT,'on_enter_cell',wraps=EXT.on_enter_cell) as entered:
   self.assertTrue(self.push());entered.assert_called_once_with(self.e,self.b,(3,1))
 def test_heavy_standard_and_nonadjacent_geometry_do_not_silently_execute(self):
  self.a.injuries=5;before=self.state()
  with self.assertRaises(ValueError):self.trip()
  self.assertEqual(self.state(),before);self.a.injuries=0;self.b.pos=(4,1)
  with self.assertRaises(ValueError):self.trip()
 def test_source_scope_is_unchanged_and_no_whole_domain_completion_claim(self):
  entries=json.loads((ROOT/'data/verification/category3-register.json').read_text(encoding='utf-8'))['entries'];entry=next(x for x in entries if x['id']=='DOMAIN-022')
  for anchor in entry['source_snapshot']['anchors']:
   lines=(ROOT/anchor['file']).read_text(encoding='utf-8-sig').splitlines();self.assertEqual('\n'.join(lines[anchor['start']-1:anchor['end']]),anchor['excerpt'])
  self.assertNotEqual(entry['status'],'completed')
if __name__=='__main__':
 class Result(unittest.TextTestResult):
  def __init__(self,*a,**kw):super().__init__(*a,**kw);self.rows=[]
  def addSuccess(self,t):super().addSuccess(t);self.rows.append({'id':t._testMethodName,'status':'pass'})
  def addFailure(self,t,e):super().addFailure(t,e);self.rows.append({'id':t._testMethodName,'status':'fail'})
  def addError(self,t,e):super().addError(t,e);self.rows.append({'id':t._testMethodName,'status':'error'})
 result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
 files=['engine/physics_maneuvers.py','engine/engine.py','engine/turn.py','engine/skill_maneuver_actions.py','engine/skill_feature_actions.py','engine/survivalist_features.py','engine/skill_modifiers.py','engine/common_checks.py','engine/capability_actions.py','engine/physical_limits.py','engine/precise_actions.py','engine/combat_maneuvers.py','engine/effects_ext.py','engine/action_lifecycle.py','data/capability-policy.json','input/ch07-combat.md','tools/test_category3_physics_maneuvers.py']
 files += ['engine/campaign_rewards.py', 'engine/league_consequences.py', 'data/campaign-reward-policy.json']
 files += ['engine/pokemon_understanding.py', 'engine/regional_pokemon.py', 'engine/source_context.py']
 files += ['engine/blessing_skill_features.py', 'engine/combat_precision_features.py', 'engine/pokemon_intelligence.py', 'engine/pokemon_party.py', 'engine/pokemon_teaching.py', 'data/pokemon-machines.json']

 files += ['engine/arithmetic.py', 'engine/arithmetic_policy.py', 'engine/effect_contracts.py', 'engine/effect_lifetimes.py', 'engine/maneuver_grants.py', 'engine/move_activation.py', 'engine/native_rule_policy.py', 'data/native-rule-policy.json']

 files += ['engine/action_lifecycle.py', 'engine/action_metadata.py', 'engine/action_points.py', 'engine/adjudication_guidance.py', 'engine/ap_roll_bonus.py', 'engine/bandages.py', 'engine/bound_ap.py', 'engine/builder.py', 'engine/capability_actions.py', 'engine/combat_maneuvers.py', 'engine/combat_social_edges.py', 'engine/combat_stage_sources.py', 'engine/combat_timing.py', 'engine/common_action_checks.py', 'engine/common_checks.py', 'engine/contest.py', 'engine/contest_features.py', 'engine/context_actions.py', 'engine/crafting_activities.py', 'engine/custom_species.py', 'engine/damage_reactions.py', 'engine/demo_rulings.py', 'engine/downtime.py', 'engine/effects.py', 'engine/effects_ext.py', 'engine/elemental_connection.py', 'engine/encounter.py', 'engine/enduring_awareness.py', 'engine/engine.py', 'engine/environmental_effects.py', 'engine/focus_tasks.py', 'engine/food_effects.py', 'engine/frequency.py', 'engine/gm_console.py', 'engine/gm_state.py', 'engine/grid.py', 'engine/heavy_injury_adapter.py', 'engine/heavy_injury_kernel.py', 'engine/heavy_standard_adapter.py', 'engine/initiative.py', 'engine/injury_recovery.py', 'engine/items.py', 'engine/jump_actions.py', 'engine/league_agenda.py', 'engine/league_runtime.py', 'engine/life.py', 'engine/maneuver_edges.py', 'engine/movement_actions.py', 'engine/net_capsule.py', 'engine/observed_resolution.py', 'engine/passive_event_profiles.py', 'engine/passive_events.py', 'engine/physical_limits.py', 'engine/physics_maneuvers.py', 'engine/pokemon_activities.py', 'engine/pokemon_requests.py', 'engine/precise_actions.py', 'engine/researcher_features.py', 'engine/resolution_transaction.py', 'engine/rest_intervals.py', 'engine/restorative_items.py', 'engine/root_admission.py', 'engine/root_children.py', 'engine/root_common_checks.py', 'engine/root_common_engine.py', 'engine/root_inputs.py', 'engine/root_machine.py', 'engine/root_resolution.py', 'engine/root_scheduler.py', 'engine/ruleset.py', 'engine/rulings.py', 'engine/skill_feature_actions.py', 'engine/skill_maneuver_actions.py', 'engine/skill_modifiers.py', 'engine/skill_stunts.py', 'engine/skill_targets.py', 'engine/survivalist_features.py', 'engine/temporary_hp.py', 'engine/test_builder.py', 'engine/test_contest.py', 'engine/test_downtime.py', 'engine/test_effects.py', 'engine/test_gm_state.py', 'engine/test_grid.py', 'engine/test_items.py', 'engine/test_maintenance.py', 'engine/test_playthrough.py', 'engine/test_rules.py', 'engine/test_ruleset.py', 'engine/test_rulings.py', 'engine/test_turn.py', 'engine/trainer_capabilities.py', 'engine/turn.py', 'engine/weapon_actions.py', 'engine/wild_equipment.py', 'data/content-source-identities.json', 'data/context-check-policy.json', 'data/skill-check-policy.json', 'data/adjudication-guidance.json', 'data/rulesets.json']
 report={'generated_at':datetime.now(timezone.utc).isoformat(),'successful':result.wasSuccessful(),'scope':['DOMAIN-022'],'full_scope_verified':False,'results':result.rows,'input_hashes':{f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files},'remaining':['Repeated Push roll unit and actual remaining-round movement','Diagonal forced one-metre movement geometry','Collision world response'], 'external_dependencies':['Heavy injury Standard ordering','Vertical or underground maneuver geometry']}
 (ROOT/'output/category3-physics-maneuver-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 raise SystemExit(0 if result.wasSuccessful() else 1)
