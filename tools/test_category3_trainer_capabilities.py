"""Trainer base capability formulas applied to real native movement and jumps."""
import sys,json,hashlib,unittest
from unittest.mock import patch
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from engine import Engine,Rules,Combatant
from grid import Grid
import trainer_capabilities as T
import jump_actions as J
import common_checks as C
class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(str(ROOT),ruleset='core')
 def setUp(self):
  self.e=Engine(self.r,seed=782);self.a=Combatant(self.r,{'id':'trainer/a','name':'a','kind':'trainer','level':20,'stats':{'hp':40,'atk':10,'def':10,'spa':10,'spd':10,'spe':10},'skills':{'곡예':2,'육상':2},'movement':{'power':6},'movement_basis':'trainer_base'})
  self.a.spec['size']='medium'
  self.a.pos=(1,1);self.e.grid=Grid(25,6);self.e.everyone=[self.a];self.e.gm.everyone=[self.a]
 def jump(self,**kw):
  opts=dict(jump_id='j1',difficult=False,clear_path=True,reason_text='observed clear jump arc and landing');opts.update(kw)
  return self.e.jump(self.a,(2,1),**opts)
 def test_source_scope_and_formula_are_unchanged(self):
  ledger=json.loads((ROOT/'data/verification/category3-register.json').read_text(encoding='utf-8'));c=next(x for x in ledger['entries'] if x['id']=='C3-EX-004')
  for a in c['source_snapshot']['source_anchors']:
   lines=(ROOT/a['file']).read_text(encoding='utf-8-sig').splitlines();self.assertEqual(hashlib.sha256('\n'.join(lines[a['start_line']-1:a['end_line']]).encode()).hexdigest(),a['excerpt_sha256'])
 def test_all_ordinary_rank_pairs_derive_high_long_and_floor_overland(self):
  for acro in range(1,7):
   for ath in range(1,7):
    self.a.spec['skills']={'곡예':acro,'육상':ath};out=T.values(self.a)
    self.assertEqual(out,{'high_jump':int(acro>=4)+int(acro>=6),'long_jump':acro//2,'land':(acro+ath)//2+3})
 def test_current_sheet_is_preserved_and_derived_fields_cannot_be_double_supplied(self):
  self.a.spec.update(movement_basis='current',movement={'land':9,'high_jump':3,'long_jump':5})
  self.assertEqual(self.e.move_profile(self.a)[0],9);self.assertEqual(J.limits(self.a),{'high_jump':3,'long_jump':5})
  with self.assertRaises(ValueError):self.e.gm.set_movement_capabilities(self.a,{'land':9},basis='trainer_base',reason='current values cannot be base')
 def test_live_rank_change_updates_native_movement_and_jump_limits(self):
  self.assertEqual(self.e.move_profile(self.a)[0],5);self.assertEqual(J.limits(self.a),{'high_jump':0,'long_jump':1})
  self.a.spec['skills']={'곡예':5,'육상':4};self.assertEqual(self.e.move_profile(self.a)[0],7);self.assertEqual(J.limits(self.a),{'high_jump':1,'long_jump':2})
 def test_owned_acrobat_uses_common_composition_without_rounding_observed_values(self):
  self.a.spec.update(edges=['edge/곡예사'],skills={'곡예':3,'육상':2},movement_basis='base',
   movement={'land':6,'high_jump':0.5,'long_jump':2.25})
  before=json.dumps(self.a.spec,sort_keys=True)
  with patch.object(T.LIMITS.COMPOSITION,'derive',wraps=T.LIMITS.COMPOSITION.derive) as shared:
   self.assertEqual(J.limits(self.a),{'high_jump':1.5,'long_jump':3.25})
  self.assertTrue(any(call.args[1][0]['source']=='edge/곡예사' for call in shared.call_args_list))
  self.assertEqual(json.dumps(self.a.spec,sort_keys=True),before)
 def test_virtuoso_rank_eight_changes_derived_values_without_eight_dice(self):
  self.a.spec['skills']['곡예']=6;self.a.spec.update(edges=['거장'],edge_choices={'거장':['곡예']})
  self.assertEqual(T.values(self.a),{'high_jump':2,'long_jump':4,'land':8});self.assertEqual(len(self.e.skill_roll(self.a,'곡예').faces),6)
 def test_zero_high_jump_allows_less_than_one_metre_without_roll(self):
  before=self.e.rng.getstate();out=self.jump(apex_height=0.9)
  self.assertTrue(out['landed']);self.assertEqual(out['checks'],{});self.assertEqual(self.e.rng.getstate(),before)
 def test_one_metre_at_zero_high_requires_actual_dc16_boost(self):
  before=self.e.rng.getstate()
  with self.assertRaises(ValueError):self.jump(apex_height=1)
  self.assertEqual(before,self.e.rng.getstate());out=self.jump(apex_height=1,boost='high_jump',boost_options={'fixed':[6,6],'mods':4})
  self.assertEqual((out['checks']['boost'].total,out['checks']['boost'].dc),(16,16));self.assertTrue(out['landed'])
 def test_running_start_adds_one_to_high_only_for_this_real_attempt(self):
  before=T.values(self.a);out=self.jump(apex_height=1,running_start=True,running_reason='already running toward this gap')
  self.assertEqual(out['base_limits'],{'high_jump':1,'long_jump':1});self.assertEqual(out['checks'],{});self.assertEqual(T.values(self.a),before)
 def test_running_and_successful_acrobatics_boost_add_separately_once(self):
  self.a.spec['skills']['곡예']=6
  out=self.jump(apex_height=4,running_start=True,running_reason='actual run-up',boost='high_jump',boost_options={'fixed':[3]*6})
  self.assertEqual(out['effective_limits']['high_jump'],4);self.assertEqual(T.values(self.a)['high_jump'],2)
 def test_running_current_sheet_needs_explicit_bonus_inclusion(self):
  self.a.spec.update(movement_basis='current',movement={'high_jump':1,'long_jump':1,'land':5})
  with self.assertRaises(ValueError):self.jump(apex_height=1,running_start=True,running_reason='observed run-up')
  out=self.jump(apex_height=1,running_start=True,running_reason='observed run-up',running_bonus_included=True)
  self.assertEqual(out['base_limits']['high_jump'],1)
 def test_no_running_bonus_for_pokemon_or_missing_world_reason(self):
  with self.assertRaises(ValueError):self.jump(running_start=True)
  self.a.kind='pokemon';self.a.spec.update(movement_basis='current',movement={'high_jump':1,'long_jump':1,'land':5})
  with self.assertRaises(ValueError):self.jump(running_start=True,running_reason='cannot copy trainer formula')
 def test_derived_overland_reaches_actual_position_within_only_its_limit(self):
  self.a.spec['size']='medium'
  self.a.spec['skills']={'곡예':4,'육상':4};self.a.pos=(1,0);self.e.grid=Grid(25,1);self.e.start_round([self.a]);self.e.start_of_turn(self.a)
  target=Combatant(self.r,{'id':'target','name':'target','kind':'pokemon','size':'small','level':1,'stats':{'hp':10,'atk':1,'def':1,'spa':1,'spd':1,'spe':1}});target.pos=(16,0);target.side='b';self.a.side='a';self.e.everyone.append(target)
  self.e.approach(self.a,target);self.assertEqual(self.a.pos,(8,0));self.assertEqual(self.a.budget['shift'],0)
if __name__=='__main__':
 class Result(unittest.TextTestResult):
  def __init__(self,*a,**kw):super().__init__(*a,**kw);self.rows=[]
  def addSuccess(self,t):super().addSuccess(t);self.rows.append({'id':t._testMethodName,'status':'pass'})
  def addFailure(self,t,e):super().addFailure(t,e);self.rows.append({'id':t._testMethodName,'status':'fail'})
  def addError(self,t,e):super().addError(t,e);self.rows.append({'id':t._testMethodName,'status':'error'})
 result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
 files=['engine/adjudication_guidance.py','data/adjudication-guidance.json','engine/skill_maneuver_actions.py','engine/food_effects.py','engine/combat_social_edges.py','engine/net_capsule.py','engine/researcher_features.py','engine/precise_actions.py','engine/environmental_effects.py','engine/wild_equipment.py','engine/injury_recovery.py','engine/downtime.py','engine/items.py','engine/heavy_injury_adapter.py','engine/context_actions.py','engine/pokemon_requests.py','engine/combat_timing.py','engine/combat_maneuvers.py','data/context-check-policy.json','data/cultivation-policy.json','tools/test_category3_trainer_capabilities.py','engine/trainer_capabilities.py','engine/movement_actions.py','engine/jump_actions.py','engine/engine.py','engine/skill_modifiers.py','engine/common_checks.py','engine/capability_actions.py','engine/physical_limits.py','engine/skill_feature_actions.py','engine/contest_features.py','engine/turn.py','engine/action_lifecycle.py','engine/ap_roll_bonus.py','engine/common_action_checks.py','engine/gm_state.py','engine/ruleset.py','engine/grid.py','engine/effects_ext.py','data/skill-check-policy.json','data/core-rules.json','data/rulesets.json','output/ruleunits.jsonl','input/ch02-character-creation.md','input/ch06-gameplay.md']
 files += ['engine/campaign_rewards.py', 'engine/league_consequences.py', 'data/campaign-reward-policy.json']
 files += ['engine/pokemon_understanding.py', 'engine/regional_pokemon.py', 'engine/source_context.py']
 files += ['engine/blessing_skill_features.py', 'engine/combat_precision_features.py', 'engine/pokemon_intelligence.py', 'engine/pokemon_party.py', 'engine/pokemon_teaching.py', 'data/pokemon-machines.json']

 files += ['engine/arithmetic.py', 'engine/arithmetic_policy.py', 'engine/effect_contracts.py', 'engine/effect_lifetimes.py', 'engine/maneuver_grants.py', 'engine/move_activation.py', 'engine/native_rule_policy.py', 'data/native-rule-policy.json']

 files += ['engine/action_lifecycle.py', 'engine/action_metadata.py', 'engine/action_points.py', 'engine/adjudication_guidance.py', 'engine/ap_roll_bonus.py', 'engine/bandages.py', 'engine/bound_ap.py', 'engine/builder.py', 'engine/capability_actions.py', 'engine/combat_maneuvers.py', 'engine/combat_social_edges.py', 'engine/combat_stage_sources.py', 'engine/combat_timing.py', 'engine/common_action_checks.py', 'engine/common_checks.py', 'engine/contest.py', 'engine/contest_features.py', 'engine/context_actions.py', 'engine/crafting_activities.py', 'engine/custom_species.py', 'engine/damage_reactions.py', 'engine/demo_rulings.py', 'engine/downtime.py', 'engine/effects.py', 'engine/effects_ext.py', 'engine/elemental_connection.py', 'engine/encounter.py', 'engine/enduring_awareness.py', 'engine/engine.py', 'engine/environmental_effects.py', 'engine/focus_tasks.py', 'engine/food_effects.py', 'engine/frequency.py', 'engine/gm_console.py', 'engine/gm_state.py', 'engine/grid.py', 'engine/heavy_injury_adapter.py', 'engine/heavy_injury_kernel.py', 'engine/heavy_standard_adapter.py', 'engine/initiative.py', 'engine/injury_recovery.py', 'engine/items.py', 'engine/jump_actions.py', 'engine/league_agenda.py', 'engine/league_runtime.py', 'engine/life.py', 'engine/maneuver_edges.py', 'engine/movement_actions.py', 'engine/net_capsule.py', 'engine/observed_resolution.py', 'engine/passive_event_profiles.py', 'engine/passive_events.py', 'engine/physical_limits.py', 'engine/physics_maneuvers.py', 'engine/pokemon_activities.py', 'engine/pokemon_requests.py', 'engine/precise_actions.py', 'engine/researcher_features.py', 'engine/resolution_transaction.py', 'engine/rest_intervals.py', 'engine/restorative_items.py', 'engine/root_admission.py', 'engine/root_children.py', 'engine/root_common_checks.py', 'engine/root_common_engine.py', 'engine/root_inputs.py', 'engine/root_machine.py', 'engine/root_resolution.py', 'engine/root_scheduler.py', 'engine/ruleset.py', 'engine/rulings.py', 'engine/skill_feature_actions.py', 'engine/skill_maneuver_actions.py', 'engine/skill_modifiers.py', 'engine/skill_stunts.py', 'engine/skill_targets.py', 'engine/survivalist_features.py', 'engine/temporary_hp.py', 'engine/test_builder.py', 'engine/test_contest.py', 'engine/test_downtime.py', 'engine/test_effects.py', 'engine/test_gm_state.py', 'engine/test_grid.py', 'engine/test_items.py', 'engine/test_maintenance.py', 'engine/test_playthrough.py', 'engine/test_rules.py', 'engine/test_ruleset.py', 'engine/test_rulings.py', 'engine/test_turn.py', 'engine/trainer_capabilities.py', 'engine/turn.py', 'engine/weapon_actions.py', 'engine/wild_equipment.py', 'data/content-source-identities.json', 'data/context-check-policy.json', 'data/skill-check-policy.json', 'data/adjudication-guidance.json', 'data/rulesets.json']
 report={'generated_at':datetime.now(timezone.utc).isoformat(),'successful':result.wasSuccessful(),'scope':['C3-EX-004'],'results':result.rows,'input_hashes':{f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files}}
 (ROOT/'output/category3-trainer-capability-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 raise SystemExit(0 if result.wasSuccessful() else 1)
