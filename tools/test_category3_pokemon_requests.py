"""CORE047/048: request -> GM response -> actual native Pokemon check/capability."""
from copy import deepcopy
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'));sys.path.insert(0,str(ROOT/'tools'))
import test_category3_pokemon_activities as _fixture_test_category3_pokemon_activities
from engine import Rules
from grid import Grid
import common_checks as C
class RequestTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(str(ROOT),ruleset='core')
 actor=_fixture_test_category3_pokemon_activities.PokemonActivityTests.actor
 act=_fixture_test_category3_pokemon_activities.PokemonActivityTests.act
 state=_fixture_test_category3_pokemon_activities.PokemonActivityTests.state
 def setUp(self):
  _fixture_test_category3_pokemon_activities.PokemonActivityTests.setUp(self);self.p.spec['trainer_id']=self.a.spec['id'];self.p.spec['loyalty']=3
  self.p.pos=(1,2);self.a.pos=(10,7);self.q.pos=(12,7);self.e.grid=Grid(20,10);self.e.everyone=[self.a,self.p,self.q]
  self.e.gm.set_movement_capabilities(self.p,{'land':6,'power':6,'teleport':4},basis='current',reason='GM current sheet')
 def request(self,action='common_action',options=None,rid='r'):
  return self.act('request_help',target=self.p,request_id=rid,intent='Help the trainer cross the obstacle',action=action,options=options)
 def resolve(self,decision='accept',rid='r',**kw):
  return self.act('resolve_help',target=self.p,request_id=rid,decision=decision,explanation=kw.pop('explanation','GM Pokemon response'),**kw)
 def teleport_request(self,rid='r'):
  return self.request('teleport',{'destination':[3,2],'surface_contact':True,'reason_text':'GM observed safe visible surface'},rid)
 def test_source_scopes_unchanged(self):
  r=json.loads((ROOT/'data/verification/category3-register.json').read_text(encoding='utf-8-sig'))
  for x in r['entries']:
   if x['id'] in ('C3-CORE-047','C3-CORE-048'):
    a=x['source_snapshot']['source'];text='\n'.join((ROOT/a['file']).read_text(encoding='utf-8-sig').splitlines()[a['start']-1:a['end']]);self.assertEqual(text,a['excerpt'])
 def test_player_request_alone_never_rolls_moves_or_spends_time(self):
  rng=self.e.rng.getstate();pos=self.p.pos;time=self.e.elapsed_seconds;r=self.teleport_request()
  self.assertEqual(r['status'],'awaiting_gm');self.assertIsInstance(r['result'],C.PendingDecision);self.assertEqual(self.p.pos,pos);self.assertEqual(self.e.rng.getstate(),rng);self.assertEqual(self.e.elapsed_seconds,time)
 def test_gm_accept_executes_real_pokemon_teleport_once(self):
  self.teleport_request();result=self.resolve();self.assertEqual(result['status'],'completed');self.assertEqual(self.p.pos,(3,2));self.assertEqual(self.a.pos,(10,7))
  with self.assertRaises(ValueError):self.resolve()
 def test_gm_refuses_low_loyalty_danger_or_morality_without_invented_dc(self):
  for i,flag in enumerate(('low_loyalty','severe_danger','moral_conflict')):
   self.p.spec['loyalty']=0 if i==0 else 6;rid=str(i);self.teleport_request(rid);rng=self.e.rng.getstate();r=self.resolve('refuse',rid,exceptions={flag:True},explanation='GM evaluates personality and this context')
   self.assertEqual(r['status'],'refused');self.assertEqual(self.p.pos,(1,2));self.assertEqual(self.e.rng.getstate(),rng);self.assertTrue(r['request']['responses'][-1]['exceptions'][flag])
 def test_low_loyalty_is_contextual_gm_judgment_not_combat_obedience_gate(self):
  self.p.spec['loyalty']=0;self.teleport_request();rng=self.e.rng.getstate();self.resolve(exceptions={'low_loyalty':True},explanation='Pokemon willingly helps in this safe context')
  self.assertEqual(self.p.pos,(3,2));self.assertEqual(self.e.rng.getstate(),rng)
 def test_gm_selected_skill_uses_pokemon_rank_not_trainer_and_stores_roll(self):
  self.p.spec['skills']['육상']='초보';self.a.spec['skills']['육상']='달인';self.request();r=self.resolve('check',skill='육상',dc=9,roll_options={'fixed':[3,3,3]})
  self.assertEqual(r['status'],'awaiting_result');self.assertEqual(r['result'].check.total,9);rng=self.e.rng.getstate()
  with self.assertRaises(ValueError):self.resolve('check',skill='육상',dc=9,roll_options={'fixed':[6,6,6]})
  result=self.resolve(outcome='success',explanation='GM describes actual useful result');self.assertEqual(result['status'],'completed');self.assertEqual(result['result'].check.total,9);self.assertEqual(self.e.rng.getstate(),rng)
 def test_failed_skill_retains_result_until_gm_refusal_no_reroll(self):
  self.request();r=self.resolve('check',skill='육상',dc=99,roll_options={'fixed':[1]*4});self.assertFalse(r['result'].check.passed);rng=self.e.rng.getstate()
  self.assertEqual(self.resolve()['status'],'awaiting_result');r=self.resolve('refuse',explanation='GM Pokemon cannot complete request');self.assertEqual(r['request']['check']['total'],4);self.assertEqual(self.e.rng.getstate(),rng)
 def test_success_with_cost_requires_explicit_failure_margin_and_cost(self):
  self.request();self.resolve('check',skill='육상',dc=5,roll_options={'fixed':[1]*4})
  r=self.resolve(outcome='success_with_cost',cost='GM establishes noisy crossing');self.assertEqual(r['status'],'awaiting_result')
  r=self.resolve(outcome='success_with_cost',cost='GM establishes noisy crossing',failure_margin_accepted=True);self.assertEqual(r['status'],'completed');self.assertEqual(r['result'].outcome,'success_with_cost')
 def test_gm_check_then_accept_runs_requested_native_action_without_extra_check(self):
  self.teleport_request();self.resolve('check',skill='육상',dc=4,roll_options={'fixed':[1]*4});self.assertEqual(self.p.pos,(1,2));rng=self.e.rng.getstate()
  result=self.resolve();self.assertEqual(self.p.pos,(3,2));self.assertEqual(result['request']['precondition_outcome']['check']['total'],4);self.assertEqual(self.e.rng.getstate(),rng)
 def test_requested_common_action_uses_native_check_then_world_response_once(self):
  self.request(options={'mode':'skill','skill':'육상','dc':12,'fixed':[3]*4,'outcome':None})
  r=self.resolve();self.assertEqual(r['status'],'awaiting_result');self.assertEqual(r['result'].check.total,12);rng=self.e.rng.getstate()
  r=self.resolve(outcome='success');self.assertEqual(r['status'],'completed');self.assertEqual(self.e.rng.getstate(),rng)
 def test_native_carry_check_and_gm_context_record_actual_load_round(self):
  self.e.gm.set_carried_objects(self.p,[{'id':'crate','weight_kg':100}],'GM weighs carried crate')
  self.request('carry_check',{'fixed':[1]*4,'round_id':'noncombat-1'});r=self.resolve()
  self.assertTrue(r['result'].passed);self.assertEqual(self.p.spec['_carried_load']['checked_round'],'noncombat:noncombat-1')
 def test_native_drag_moves_actual_world_object_and_pokemon(self):
  self.e.gm.set_physical_object('cart',weight_kg=150,position=(2,2),reason='GM observed heavy cart')
  self.request('drag_object',dict(object_id='cart',destination=[3,2],actor_destination=[2,2],action_cost='shift',reason='GM slow push',round_id='noncombat-1'))
  self.resolve();self.assertEqual(self.p.pos,(2,2));self.assertEqual(self.e._physical_objects['cart']['pos'],(3,2))
 def test_native_jump_moves_actual_pokemon_and_preserves_one_use(self):
  self.p.spec['movement'].update(high_jump=1,long_jump=2)
  self.request('jump',{'destination':[3,2],'jump_id':'j','difficult':False,'clear_path':True,'reason_text':'GM clear ordinary arc'})
  r=self.resolve();self.assertEqual(r['status'],'completed');self.assertEqual(self.p.pos,(3,2));self.assertTrue(r['result']['whole_shift']);self.assertTrue(self.p.spec['_jump_attempts']['j']['landed'])
  with self.assertRaises(ValueError):self.resolve()
 def test_native_boosted_jump_records_actual_check_as_plain_facts(self):
  self.p.spec['movement'].update(high_jump=1,long_jump=1)
  self.request('jump',{'destination':[3,2],'jump_id':'boost','difficult':False,'clear_path':True,'reason_text':'GM clear increased long jump','boost':'long_jump','boost_options':{'fixed':[4]*4}})
  r=self.resolve();self.assertEqual(self.p.pos,(3,2));self.assertEqual(r['result']['checks']['boost'].total,16)
  stored=self.a.spec['pokemon_requests']['r']['native_result'];self.assertEqual(stored['checks']['boost']['total'],16);json.dumps(self.a.spec['pokemon_requests'],allow_nan=False)
 def test_native_failed_jump_keeps_pending_check_without_request_reroll(self):
  self.p.spec['movement'].update(high_jump=1,long_jump=1)
  self.request('jump',{'destination':[3,2],'jump_id':'failed','difficult':False,'clear_path':True,'reason_text':'GM clear increased long jump','boost':'long_jump','boost_options':{'fixed':[1]*4}})
  r=self.resolve();self.assertEqual(r['status'],'native_pending');self.assertFalse(r['result'].check.passed);self.assertEqual(self.p.pos,(1,2));rng=self.e.rng.getstate()
  with self.assertRaises(ValueError):self.resolve()
  self.assertEqual(self.e.rng.getstate(),rng);self.assertEqual(self.p.spec['_jump_pending'],'failed')
 def test_native_source_conflict_is_preserved_not_fake_completion(self):
  self.request('sprint');r=self.resolve();self.assertEqual(r['status'],'native_pending');self.assertIsInstance(r['result'],C.PendingDecision);self.assertNotIn('질주',self.p.custom_conditions)
 def test_wrong_owner_target_or_combat_context_cannot_reuse_request(self):
  self.teleport_request();before=self.state();self.q.spec['trainer_id']=self.a.spec['id']
  with self.assertRaises(ValueError):self.act('resolve_help',target=self.q,request_id='r',decision='accept',explanation='different target')
  self.assertEqual(self.p.pos,(1,2));self.p.spec['trainer_id']='someone-else'
  with self.assertRaises(ValueError):self.resolve()
  self.p.spec['trainer_id']=self.a.spec['id'];self.e.encounter_active=True
  with self.assertRaises(ValueError):self.resolve()
 def test_duplicate_id_callback_actor_override_and_invalid_check_preflight_rejected(self):
  self.request();before=self.state()
  with self.assertRaises(ValueError):self.request()
  with self.assertRaises(ValueError):self.request('teleport',{'destination':lambda:None},'callback')
  with self.assertRaises(ValueError):self.request('carry_check',{'actor':self.a},'replace')
  with self.assertRaises(ValueError):self.resolve('check',skill='육상',dc=4,roll_options={'fixed':[1]})
  self.assertEqual(before,self.state())
 def test_native_execution_exception_cannot_replay_and_keeps_original_rng(self):
  self.request('sprint',{'source_policy':'ch06_once'});original=self.e.sprint
  def failed(actor,**kw):self.e.rng.randint(1,20);raise RuntimeError('native exception after RNG')
  self.e.sprint=failed;before=self.e.rng.getstate()
  with self.assertRaises(RuntimeError):self.resolve()
  self.assertNotEqual(before,self.e.rng.getstate());rng=self.e.rng.getstate();self.e.sprint=original
  with self.assertRaises(ValueError):self.resolve()
  self.assertEqual(rng,self.e.rng.getstate());self.assertEqual(self.a.spec['pokemon_requests']['r']['status'],'execution_error')
 def test_native_action_refusal_is_not_reported_as_completed(self):
  self.request('sprint',{'source_policy':'ch06_once'});self.e.gm.faint(self.p,'Pokemon became unconscious before GM response');rng=self.e.rng.getstate()
  r=self.resolve();self.assertEqual(r['status'],'not_executed');self.assertIs(r['result'],False);self.assertNotIn('질주',self.p.custom_conditions);self.assertEqual(self.e.rng.getstate(),rng)
  with self.assertRaises(ValueError):self.resolve()
if __name__=='__main__':
 class Result(unittest.TextTestResult):
  def __init__(self,*a,**kw):super().__init__(*a,**kw);self.rows=[]
  def addSuccess(self,t):super().addSuccess(t);self.rows.append({'id':t._testMethodName,'status':'pass'})
  def addFailure(self,t,e):super().addFailure(t,e);self.rows.append({'id':t._testMethodName,'status':'fail'})
  def addError(self,t,e):super().addError(t,e);self.rows.append({'id':t._testMethodName,'status':'error'})
 result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(RequestTests))
 files=['engine/adjudication_guidance.py','data/adjudication-guidance.json','engine/skill_maneuver_actions.py','engine/food_effects.py','engine/combat_social_edges.py','engine/net_capsule.py','engine/trainer_capabilities.py','engine/skill_feature_actions.py','engine/researcher_features.py','engine/precise_actions.py','engine/environmental_effects.py','engine/wild_equipment.py','engine/injury_recovery.py','engine/downtime.py','engine/items.py','engine/heavy_injury_adapter.py','engine/jump_actions.py','engine/context_actions.py','engine/combat_timing.py','engine/combat_maneuvers.py','data/context-check-policy.json','data/cultivation-policy.json','engine/pokemon_requests.py','engine/pokemon_activities.py','engine/engine.py','engine/common_checks.py','engine/common_action_checks.py','engine/skill_modifiers.py','engine/movement_actions.py','engine/capability_actions.py','engine/physical_limits.py','engine/gm_state.py','engine/turn.py','engine/action_lifecycle.py','data/core-rules.json','data/skill-check-policy.json','data/capability-policy.json','data/rulesets.json','output/ruleunits.jsonl','input/ch06-gameplay.md','tools/test_category3_pokemon_requests.py']
 files += ['engine/campaign_rewards.py', 'engine/league_consequences.py', 'data/campaign-reward-policy.json']
 files += ['engine/pokemon_understanding.py', 'engine/regional_pokemon.py', 'engine/source_context.py']
 files += ['engine/blessing_skill_features.py', 'engine/combat_precision_features.py', 'engine/pokemon_intelligence.py', 'engine/pokemon_party.py', 'engine/pokemon_teaching.py', 'data/pokemon-machines.json']

 files += ['engine/arithmetic.py', 'engine/arithmetic_policy.py', 'engine/effect_contracts.py', 'engine/effect_lifetimes.py', 'engine/maneuver_grants.py', 'engine/move_activation.py', 'engine/native_rule_policy.py', 'data/native-rule-policy.json']

 files += ['engine/action_lifecycle.py', 'engine/action_metadata.py', 'engine/action_points.py', 'engine/adjudication_guidance.py', 'engine/ap_roll_bonus.py', 'engine/bandages.py', 'engine/bound_ap.py', 'engine/builder.py', 'engine/capability_actions.py', 'engine/combat_maneuvers.py', 'engine/combat_social_edges.py', 'engine/combat_stage_sources.py', 'engine/combat_timing.py', 'engine/common_action_checks.py', 'engine/common_checks.py', 'engine/contest.py', 'engine/contest_features.py', 'engine/context_actions.py', 'engine/crafting_activities.py', 'engine/custom_species.py', 'engine/damage_reactions.py', 'engine/demo_rulings.py', 'engine/downtime.py', 'engine/effects.py', 'engine/effects_ext.py', 'engine/elemental_connection.py', 'engine/encounter.py', 'engine/enduring_awareness.py', 'engine/engine.py', 'engine/environmental_effects.py', 'engine/focus_tasks.py', 'engine/food_effects.py', 'engine/frequency.py', 'engine/gm_console.py', 'engine/gm_state.py', 'engine/grid.py', 'engine/heavy_injury_adapter.py', 'engine/heavy_injury_kernel.py', 'engine/heavy_standard_adapter.py', 'engine/initiative.py', 'engine/injury_recovery.py', 'engine/items.py', 'engine/jump_actions.py', 'engine/league_agenda.py', 'engine/league_runtime.py', 'engine/life.py', 'engine/maneuver_edges.py', 'engine/movement_actions.py', 'engine/net_capsule.py', 'engine/observed_resolution.py', 'engine/passive_event_profiles.py', 'engine/passive_events.py', 'engine/physical_limits.py', 'engine/physics_maneuvers.py', 'engine/pokemon_activities.py', 'engine/pokemon_requests.py', 'engine/precise_actions.py', 'engine/researcher_features.py', 'engine/resolution_transaction.py', 'engine/rest_intervals.py', 'engine/restorative_items.py', 'engine/root_admission.py', 'engine/root_children.py', 'engine/root_common_checks.py', 'engine/root_common_engine.py', 'engine/root_inputs.py', 'engine/root_machine.py', 'engine/root_resolution.py', 'engine/root_scheduler.py', 'engine/ruleset.py', 'engine/rulings.py', 'engine/skill_feature_actions.py', 'engine/skill_maneuver_actions.py', 'engine/skill_modifiers.py', 'engine/skill_stunts.py', 'engine/skill_targets.py', 'engine/survivalist_features.py', 'engine/temporary_hp.py', 'engine/test_builder.py', 'engine/test_contest.py', 'engine/test_downtime.py', 'engine/test_effects.py', 'engine/test_gm_state.py', 'engine/test_grid.py', 'engine/test_items.py', 'engine/test_maintenance.py', 'engine/test_playthrough.py', 'engine/test_rules.py', 'engine/test_ruleset.py', 'engine/test_rulings.py', 'engine/test_turn.py', 'engine/trainer_capabilities.py', 'engine/turn.py', 'engine/weapon_actions.py', 'engine/wild_equipment.py', 'data/content-source-identities.json', 'data/context-check-policy.json', 'data/skill-check-policy.json', 'data/adjudication-guidance.json', 'data/rulesets.json']
 report={'generated_at':datetime.now(timezone.utc).isoformat(),'successful':result.wasSuccessful(),'scope':['C3-CORE-047','C3-CORE-048'],'completion':'full source reviewed; native action pending boundaries preserved','results':result.rows,'input_hashes':{f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files}}
 (ROOT/'output/category3-pokemon-request-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 raise SystemExit(0 if result.wasSuccessful() else 1)
