"""Fixed DOMAIN069 item application, consent, cost and X-item lifetime."""
from copy import deepcopy
from datetime import datetime,timezone
from pathlib import Path
import hashlib,json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules
import test_category3_food_effects as _fixture_test_category3_food_effects
import restorative_items as R
import common_checks as C
import effects as FX
class RestorativeTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(str(ROOT),ruleset='core')
 setUp=_fixture_test_category3_food_effects.FoodTests.setUp
 actor=_fixture_test_category3_food_effects.FoodTests.actor
 state=_fixture_test_category3_food_effects.FoodTests.state
 def stock(self,name='상처약',user=None):
  user=user or self.a;user.spec['items'][name]=user.spec['items'].get(name,0)+1
 def turn(self,actor=None):
  actor=actor or self.a;self.e.start_round([self.a,self.p,self.q]);self.e.start_of_turn(actor)
 def test_other_recipient_standard_use_and_next_standard_swift_loss_exactly_once(self):
  self.stock();self.p.hp=1;self.turn();self.e.use_item(self.a,'상처약',self.p)
  self.assertEqual(self.p.hp,21);self.assertEqual(self.a.budget,{'standard':0,'shift':1,'swift':1});self.assertEqual(self.a.spec['items']['상처약'],0)
  self.e.end_of_turn(self.a);self.e.start_of_turn(self.p);self.assertEqual(self.p.budget,{'standard':0,'shift':1,'swift':0});self.e.end_of_turn(self.p)
  self.e.start_round([self.p]);self.e.start_of_turn(self.p);self.assertEqual(self.p.budget,{'standard':1,'shift':1,'swift':1})
 def test_self_restorative_full_consumes_standard_shift_without_future_loss(self):
  self.stock(user=self.p);self.p.hp=1;self.turn(self.p);self.e.use_item(self.p,'상처약',self.p)
  self.assertEqual(self.p.hp,21);self.assertEqual(self.p.budget,{'standard':0,'shift':0,'swift':1});self.assertIsNone(getattr(self.p,'pending_action_loss',None))
  self.e.end_of_turn(self.p);self.e.start_round([self.p]);self.e.start_of_turn(self.p);self.assertEqual(self.p.budget,{'standard':1,'shift':1,'swift':1})
 def test_self_x_item_is_standard_not_restorative_full_and_does_have_next_loss(self):
  self.stock('플러스파워',self.p);self.turn(self.p);self.e.use_item(self.p,'플러스파워',self.p)
  self.assertEqual(self.p.stages['atk'],2);self.assertEqual(self.p.budget,{'standard':0,'shift':1,'swift':1});self.assertEqual(self.p.pending_action_loss,{'standard':1,'swift':1})
 def test_actual_qualified_medic_exempts_other_recipient_not_using_trainer_cost(self):
  self.a.spec['edges']=['edge/메딕-훈련'];self.a.spec['skills']['의학']='초보';self.stock();self.turn();self.e.use_item(self.a,'상처약',self.p)
  self.assertEqual(self.a.budget['standard'],0);self.assertIsNone(getattr(self.p,'pending_action_loss',None));self.e.end_of_turn(self.a);self.e.start_of_turn(self.p);self.assertEqual(self.p.budget['standard'],1)
 def test_medic_unqualified_or_replaced_source_cannot_bypass_target_cost(self):
  self.a.spec['edges']=['메딕 훈련'];self.a.spec['skills']['의학']='미숙';self.stock();before=self.state()
  with self.assertRaises(ValueError):self.e.use_item(self.a,'상처약',self.p)
  self.assertEqual(before,self.state());self.a.spec['skills']['의학']='초보';original=self.e.r._selected_rule
  try:
   self.e.r._selected_rule=lambda uid:uid+'/unselected' if uid==R.MEDIC else original(uid);before=self.state()
   with self.assertRaises(ValueError):self.e.use_item(self.a,'상처약',self.p)
   self.assertEqual(before,self.state())
  finally:self.e.r._selected_rule=original
 def test_declined_target_and_fractional_bottle_never_spend_inventory_or_actions(self):
  self.stock();self.turn();before=self.state();self.assertEqual(self.e.use_item(self.a,'상처약',self.p,accepted=False),(0,0));self.assertEqual(before,self.state())
  for count in (0,0.5,2):
   with self.assertRaises(ValueError):self.e.use_item(self.a,'상처약',self.p,count=count)
   self.assertEqual(before,self.state())
 def test_all_eight_x_categories_reject_trainers_before_cost(self):
  self.turn()
  for uid in sorted(R.X_ITEMS):
   self.stock(uid);before=self.state();self.assertEqual(self.e.use_item(self.a,uid,self.a),(0,0));self.assertEqual(before,self.state())
 def test_five_stat_x_and_accuracy_reset_at_encounter_end(self):
  for uid,stat in zip(('item/플러스파워','item/디펜드업','item/스페셜파워','item/스페셜가드','item/스피드업'),('atk','def','spa','spd','spe')):
   self.stock(uid);self.e.use_item(self.a,uid,self.p);self.assertEqual(self.p.stages[stat],2)
  self.stock('잘-맞히기');self.e.use_item(self.a,'잘-맞히기',self.p);self.assertEqual(self.p.accuracy_stage,2)
  self.e.end_encounter([self.p]);self.assertEqual(set(self.p.stages.values()),{0});self.assertEqual(self.p.accuracy_stage,0)
 def test_dire_hit_changes_native_critical_boundary_and_expires_without_removing_other_source(self):
  self.stock('크리티컬 커터');self.p.modifiers.append({'type':'crit_range','delta':1,'moves':'all','source':'independent test fixture'})
  self.e.use_item(self.a,'크리티컬 커터',self.p);move=self.e.r.move('struggle')
  self.assertTrue(self.e.accuracy_check(self.p,self.q,move,fixed_roll=17)[2]);self.assertFalse(self.e.accuracy_check(self.p,self.q,move,fixed_roll=16)[2])
  self.e.end_encounter([self.p]);self.assertFalse(self.e.accuracy_check(self.p,self.q,move,fixed_roll=18)[2]);self.assertTrue(self.e.accuracy_check(self.p,self.q,move,fixed_roll=19)[2]);self.assertEqual(len(self.p.modifiers),1)
 def test_guard_spec_protects_stat_and_accuracy_five_recipient_turns_then_expires(self):
  self.stock('이펙트가드');self.turn();self.e.use_item(self.a,'이펙트가드',self.p);self.e.end_of_turn(self.a)
  for turn in range(5):
   if turn:self.e.start_round([self.p])
   self.e.start_of_turn(self.p);self.e.change_stage(self.p,'atk',-1);FX.h_accuracy_mod(self.e,self.a,self.p,{'value':-1,'target':'target'},{});self.assertEqual(self.p.stages['atk'],0);self.assertEqual(self.p.accuracy_stage,0);self.e.end_of_turn(self.p)
  self.e.change_stage(self.p,'atk',-1);FX.h_accuracy_mod(self.e,self.a,self.p,{'value':-1,'target':'target'},{});self.assertEqual(self.p.stages['atk'],-1);self.assertEqual(self.p.accuracy_stage,-1)
 def test_guard_mid_recipient_turn_is_explicitly_held_before_any_cost(self):
  self.stock('이펙트가드',self.p);self.turn(self.p);before=self.state();self.assertIsInstance(self.e.use_item(self.p,'이펙트가드',self.p),C.PendingDecision);self.assertEqual(before,self.state())
 def test_guard_blocked_burn_penalty_is_not_reversed_into_false_bonus_on_cure(self):
  self.stock('이펙트가드');self.e.use_item(self.a,'이펙트가드',self.p);self.e.apply_status(self.p,'화상');self.assertEqual(self.p.stages['def'],0);self.e.cure_status(self.p,'화상');self.assertEqual(self.p.stages['def'],0)
  self.e.end_encounter([self.p]);self.e.apply_status(self.p,'화상');self.assertEqual(self.p.stages['def'],-2);self.e.cure_status(self.p,'화상');self.assertEqual(self.p.stages['def'],0)
 def test_guard_also_ends_at_encounter_before_fifth_turn(self):
  self.stock('이펙트가드');self.e.use_item(self.a,'이펙트가드',self.p);self.e.end_encounter([self.p]);self.e.change_stage(self.p,'atk',-1);self.assertEqual(self.p.stages['atk'],-1)
 def test_unavailable_budget_and_sleep_do_not_consume_or_heal(self):
  self.stock();self.p.hp=1;self.turn();self.a.budget['standard']=0;before=self.state();self.e.use_item(self.a,'상처약',self.p);self.assertEqual(before,self.state())
  self.a.budget['standard']=1;self.e.apply_status(self.a,'잠듦');before=self.state();self.e.use_item(self.a,'상처약',self.p);self.assertEqual(before,self.state())
 def test_absent_or_malformed_owned_inventory_never_authorizes_item_or_cost(self):
  for malformed in (None,[],False):
   self.setUp();self.a.spec['items']=malformed;self.p.hp=1;self.turn();before=self.state()
   with self.assertRaises(ValueError):self.e.use_item(self.a,'상처약',self.p)
   self.assertEqual(before,self.state())
  self.setUp();self.a.spec.pop('items');self.p.hp=1;self.turn();before=self.state()
  with self.assertRaises(ValueError):self.e.use_item(self.a,'상처약',self.p)
  self.assertEqual(before,self.state())
 def test_noninteger_stock_cannot_pay_one_actual_item(self):
  for stock in (True,1.5,'1'):
   self.setUp();self.a.spec['items']['상처약']=stock;self.turn();before=self.state()
   with self.assertRaises(ValueError):self.e.use_item(self.a,'상처약',self.p)
   self.assertEqual(before,self.state())
 def test_untracked_stage_state_rejected_before_item_inventory_action_and_target_debt(self):
  import combat_stage_sources as STAGES
  for item in ('플러스파워','만능가루'):
   self.setUp();self.stock(item);self.turn();STAGES.add_base(self.p,'herbal_restoratives','atk',-1,source='ch09-equipment/모험-도구/약',ends='extended_rest');self.p.stages['atk']=2;before=self.state()
   with self.assertRaises(ValueError):self.e.use_item(self.a,item,self.p)
   self.assertEqual(before,self.state());self.assertEqual(self.a.spec['items'][item],1);self.assertEqual(self.a.budget['standard'],1);self.assertIsNone(getattr(self.p,'pending_action_loss',None))
if __name__=='__main__':
 class Result(unittest.TextTestResult):
  def __init__(self,*a,**kw):super().__init__(*a,**kw);self.rows=[]
  def addSuccess(self,t):super().addSuccess(t);self.rows.append({'id':t._testMethodName,'status':'pass'})
  def addFailure(self,t,e):super().addFailure(t,e);self.rows.append({'id':t._testMethodName,'status':'fail'})
  def addError(self,t,e):super().addError(t,e);self.rows.append({'id':t._testMethodName,'status':'error'})
 result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(RestorativeTests))
 files=['engine/restorative_items.py','engine/food_effects.py','engine/combat_stage_sources.py','engine/items.py','engine/engine.py','engine/downtime.py','engine/temporary_hp.py','engine/effects.py','engine/effects_ext.py','engine/turn.py','engine/action_lifecycle.py','engine/combat_timing.py','data/rulesets.json','data/items-mech.json','data/items-reviewed.json','output/ruleunits.jsonl','input/ch09-equipment.md','input/ch03-skills-edges-feats.md','input/db/inventory.csv','tools/test_category3_food_effects.py','tools/test_category3_restorative.py']
 files += ['engine/campaign_rewards.py', 'engine/league_consequences.py', 'data/campaign-reward-policy.json']
 files += ['engine/pokemon_understanding.py', 'engine/regional_pokemon.py', 'engine/source_context.py']
 files += ['engine/blessing_skill_features.py', 'engine/combat_precision_features.py', 'engine/pokemon_intelligence.py', 'engine/pokemon_party.py', 'engine/pokemon_teaching.py', 'data/pokemon-machines.json']

 files += ['engine/arithmetic.py', 'engine/arithmetic_policy.py', 'engine/effect_contracts.py', 'engine/effect_lifetimes.py', 'engine/maneuver_grants.py', 'engine/move_activation.py', 'engine/native_rule_policy.py', 'data/native-rule-policy.json']

 files += ['engine/action_lifecycle.py', 'engine/action_metadata.py', 'engine/action_points.py', 'engine/adjudication_guidance.py', 'engine/ap_roll_bonus.py', 'engine/bandages.py', 'engine/bound_ap.py', 'engine/builder.py', 'engine/capability_actions.py', 'engine/combat_maneuvers.py', 'engine/combat_social_edges.py', 'engine/combat_stage_sources.py', 'engine/combat_timing.py', 'engine/common_action_checks.py', 'engine/common_checks.py', 'engine/contest.py', 'engine/contest_features.py', 'engine/context_actions.py', 'engine/crafting_activities.py', 'engine/custom_species.py', 'engine/damage_reactions.py', 'engine/demo_rulings.py', 'engine/downtime.py', 'engine/effects.py', 'engine/effects_ext.py', 'engine/elemental_connection.py', 'engine/encounter.py', 'engine/enduring_awareness.py', 'engine/engine.py', 'engine/environmental_effects.py', 'engine/focus_tasks.py', 'engine/food_effects.py', 'engine/frequency.py', 'engine/gm_console.py', 'engine/gm_state.py', 'engine/grid.py', 'engine/heavy_injury_adapter.py', 'engine/heavy_injury_kernel.py', 'engine/heavy_standard_adapter.py', 'engine/initiative.py', 'engine/injury_recovery.py', 'engine/items.py', 'engine/jump_actions.py', 'engine/league_agenda.py', 'engine/league_runtime.py', 'engine/life.py', 'engine/maneuver_edges.py', 'engine/movement_actions.py', 'engine/net_capsule.py', 'engine/observed_resolution.py', 'engine/passive_event_profiles.py', 'engine/passive_events.py', 'engine/physical_limits.py', 'engine/physics_maneuvers.py', 'engine/pokemon_activities.py', 'engine/pokemon_requests.py', 'engine/precise_actions.py', 'engine/researcher_features.py', 'engine/resolution_transaction.py', 'engine/rest_intervals.py', 'engine/restorative_items.py', 'engine/root_admission.py', 'engine/root_children.py', 'engine/root_common_checks.py', 'engine/root_common_engine.py', 'engine/root_inputs.py', 'engine/root_machine.py', 'engine/root_resolution.py', 'engine/root_scheduler.py', 'engine/ruleset.py', 'engine/rulings.py', 'engine/skill_feature_actions.py', 'engine/skill_maneuver_actions.py', 'engine/skill_modifiers.py', 'engine/skill_stunts.py', 'engine/skill_targets.py', 'engine/survivalist_features.py', 'engine/temporary_hp.py', 'engine/test_builder.py', 'engine/test_contest.py', 'engine/test_downtime.py', 'engine/test_effects.py', 'engine/test_gm_state.py', 'engine/test_grid.py', 'engine/test_items.py', 'engine/test_maintenance.py', 'engine/test_playthrough.py', 'engine/test_rules.py', 'engine/test_ruleset.py', 'engine/test_rulings.py', 'engine/test_turn.py', 'engine/trainer_capabilities.py', 'engine/turn.py', 'engine/weapon_actions.py', 'engine/wild_equipment.py', 'data/content-source-identities.json', 'data/context-check-policy.json', 'data/skill-check-policy.json', 'data/adjudication-guidance.json', 'data/rulesets.json']
 report={'generated_at':datetime.now(timezone.utc).isoformat(),'successful':result.wasSuccessful(),'scope':['DOMAIN-069'],'completion':'native fixed medicine/X application; combine herbal food suite before full-scope certification','results':result.rows,'input_hashes':{f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files}}
 (ROOT/'output/category3-restorative-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 raise SystemExit(0 if result.wasSuccessful() else 1)
