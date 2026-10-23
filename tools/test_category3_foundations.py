"""Source-scoped audit of existing native dice and adopted source profiles."""
import contextlib,io,json,hashlib,re,sys,unittest
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'engine'))
from engine import Rules,Engine,Combatant
import test_ruleset
class Audit(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(str(ROOT),ruleset='core')
 def actor(self,name):
  return Combatant(self.r,{'id':'pokemon/'+name,'name':name,'kind':'pokemon','size':'중형','level':30,'types':['노말'],'stats':{'hp':30,'atk':10,'def':5,'spa':10,'spd':5,'spe':1},'skills':{'육상':'숙련'},'moves':['move/화염방사']})
 def test_fixed_source_scopes_are_unchanged(self):
  ledger=json.loads((ROOT/'data/verification/category3-register.json').read_text(encoding='utf-8'))
  for e in ledger['entries']:
   if e['id'] not in ('C3-CORE-001','C3-CORE-004'):continue
   a=e['source_snapshot']['source'];lines=(ROOT/a['file']).read_text(encoding='utf-8-sig').splitlines()
   self.assertEqual(hashlib.sha256('\n'.join(lines[a['start']-1:a['end']]).encode()).hexdigest(),a['excerpt_sha256'])
 def test_real_skill_accuracy_and_damage_use_distinct_dice(self):
  from random import Random
  class Observed(Random):
   def __init__(self):super().__init__(17);self.calls=[]
   def randint(self,a,b):self.calls.append((a,b));return super().randint(a,b)
  e=Engine(self.r);a=self.actor('A');t=self.actor('T');e.everyone=e.gm.everyone=[a,t];rng=Observed();e.rng=rng
  rolled=e.skill_roll(a,'육상');self.assertEqual(len(rolled.faces),4);self.assertEqual(rng.calls,[(1,6)]*4)
  rng.calls.clear();e.accuracy_check(a,t,self.r.move('move/화염방사'));self.assertEqual(rng.calls,[(1,20)])
  kinds=set()
  for uid,m in self.r.moves.items():
   db=m.get('damage_base')
   if uid in self.r.excluded_moves or type(db) is not int or not 1<=db<=28 or m.get('class') not in ('물리','특수') or m.get('type')=='노말':continue
   actual=e.damage_base(a,m);expr=self.r.mech('combat/damage-chart')['by_damage_base'][str(actual)]['dice']
   match=re.fullmatch(r'(\d+)d(\d+)(?:\+(\d+))?',expr)
   if not match:continue
   n,faces=int(match[1]),int(match[2])
   if faces in kinds:continue
   rng.calls.clear();e.roll_damage(a,t,m)
   self.assertEqual(rng.calls,[(1,faces)]*n);kinds.add(faces)
   if kinds=={6,8,10,12}:break
  self.assertEqual(kinds,{6,8,10,12})
  # Intro mentions d4, while the fixed detailed damage chart has no d4 row.
  # Keep the existing general damage expression support without inventing a DB.
  rng.calls.clear();total,faces=e.roll_expr('2d4+3');self.assertEqual(rng.calls,[(1,4)]*2);self.assertEqual(total,sum(faces)+3)
 def test_existing_real_profile_filter_and_execution_regression(self):
  with contextlib.redirect_stdout(io.StringIO()):result=test_ruleset.run(str(ROOT))
  self.assertTrue(result)
 def test_unadopted_supplement_move_is_rejected_before_cost_rng(self):
  e=Engine(self.r);a=self.actor('A');t=self.actor('T');a.moves.append('move/폴리곤-쇼크')
  a.budget={'standard':1,'shift':1,'swift':1};before=e.rng.getstate();hp=t.hp
  self.assertEqual(e.use_move(a,t,'move/폴리곤-쇼크'),0)
  self.assertEqual((a.budget['standard'],t.hp),(1,hp));self.assertEqual(e.rng.getstate(),before)
 def test_each_actual_supplement_group_requires_campaign_adoption(self):
  from ruleset import RuleFilter
  units=[json.loads(line) for line in (ROOT/'output/ruleunits.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
  from ruleset import classify
  for group in ('polygon','blessings','fantasy'):
   actual=[u for u in units if classify(u)==(group,None)]
   self.assertTrue(actual,group)
   chosen=RuleFilter({'sources':['core',group],'variants':[]},'chosen')
   for unit in actual:
    self.assertFalse(self.r.ruleset.allows(unit)[0],unit['id'])
    self.assertTrue(chosen.allows(unit)[0],unit['id'])
if __name__=='__main__':
 class Result(unittest.TextTestResult):
  def __init__(self,*a,**kw):super().__init__(*a,**kw);self.rows=[]
  def addSuccess(self,t):super().addSuccess(t);self.rows.append({'id':t._testMethodName,'status':'pass'})
  def addFailure(self,t,e):super().addFailure(t,e);self.rows.append({'id':t._testMethodName,'status':'fail'})
  def addError(self,t,e):super().addError(t,e);self.rows.append({'id':t._testMethodName,'status':'error'})
 result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(Audit))
 paths=['engine/adjudication_guidance.py','data/adjudication-guidance.json','engine/skill_maneuver_actions.py','engine/food_effects.py','engine/combat_social_edges.py','engine/net_capsule.py','engine/trainer_capabilities.py','engine/skill_feature_actions.py','engine/researcher_features.py','engine/precise_actions.py','engine/environmental_effects.py','engine/wild_equipment.py','engine/injury_recovery.py','engine/downtime.py','engine/items.py','engine/common_action_checks.py','engine/gm_state.py','engine/heavy_injury_adapter.py','engine/jump_actions.py','engine/context_actions.py','engine/pokemon_requests.py','engine/combat_timing.py','engine/combat_maneuvers.py','data/context-check-policy.json','data/cultivation-policy.json','engine/movement_actions.py','engine/weapon_actions.py','data/weapon-policy.json','engine/bandages.py','engine/crafting_activities.py','engine/contest_features.py','data/planter-policy.json','tools/test_category3_foundations.py','engine/test_ruleset.py','tools/filter_ruleunits.py','tools/item_records.py','engine/engine.py','engine/ruleset.py','engine/skill_modifiers.py','engine/common_checks.py','engine/effects.py','engine/effects_ext.py','engine/turn.py','engine/action_lifecycle.py','engine/capability_actions.py','engine/physical_limits.py','engine/temporary_hp.py','engine/ap_roll_bonus.py','data/rulesets.json','data/core-rules.json','data/lookup-tables.json','data/skill-check-policy.json','data/capability-policy.json','data/abilities-reviewed.json','data/moves-reviewed.json','data/moves-mech.json','data/moves-llm.json','data/moves-llm-partial.json','data/moves-hand.json','output/entities/abilities.json','output/entities/moves.json','output/ruleunits.jsonl','input/ch01-intro.md','input/ch07-combat.md']
 paths += ['engine/campaign_rewards.py', 'engine/league_consequences.py', 'data/campaign-reward-policy.json']
 paths += ['engine/pokemon_understanding.py', 'engine/regional_pokemon.py', 'engine/source_context.py']
 paths += ['engine/blessing_skill_features.py', 'engine/combat_precision_features.py', 'engine/pokemon_intelligence.py', 'engine/pokemon_party.py', 'engine/pokemon_teaching.py', 'data/pokemon-machines.json']

 paths += ['engine/arithmetic.py', 'engine/arithmetic_policy.py', 'engine/effect_contracts.py', 'engine/effect_lifetimes.py', 'engine/maneuver_grants.py', 'engine/move_activation.py', 'engine/native_rule_policy.py', 'data/native-rule-policy.json']

 paths += ['engine/action_lifecycle.py', 'engine/action_metadata.py', 'engine/action_points.py', 'engine/adjudication_guidance.py', 'engine/ap_roll_bonus.py', 'engine/bandages.py', 'engine/bound_ap.py', 'engine/builder.py', 'engine/capability_actions.py', 'engine/combat_maneuvers.py', 'engine/combat_social_edges.py', 'engine/combat_stage_sources.py', 'engine/combat_timing.py', 'engine/common_action_checks.py', 'engine/common_checks.py', 'engine/contest.py', 'engine/contest_features.py', 'engine/context_actions.py', 'engine/crafting_activities.py', 'engine/custom_species.py', 'engine/damage_reactions.py', 'engine/demo_rulings.py', 'engine/downtime.py', 'engine/effects.py', 'engine/effects_ext.py', 'engine/elemental_connection.py', 'engine/encounter.py', 'engine/enduring_awareness.py', 'engine/engine.py', 'engine/environmental_effects.py', 'engine/focus_tasks.py', 'engine/food_effects.py', 'engine/frequency.py', 'engine/gm_console.py', 'engine/gm_state.py', 'engine/grid.py', 'engine/heavy_injury_adapter.py', 'engine/heavy_injury_kernel.py', 'engine/heavy_standard_adapter.py', 'engine/initiative.py', 'engine/injury_recovery.py', 'engine/items.py', 'engine/jump_actions.py', 'engine/league_agenda.py', 'engine/league_runtime.py', 'engine/life.py', 'engine/maneuver_edges.py', 'engine/movement_actions.py', 'engine/net_capsule.py', 'engine/observed_resolution.py', 'engine/passive_event_profiles.py', 'engine/passive_events.py', 'engine/physical_limits.py', 'engine/physics_maneuvers.py', 'engine/pokemon_activities.py', 'engine/pokemon_requests.py', 'engine/precise_actions.py', 'engine/researcher_features.py', 'engine/resolution_transaction.py', 'engine/rest_intervals.py', 'engine/restorative_items.py', 'engine/root_admission.py', 'engine/root_children.py', 'engine/root_common_checks.py', 'engine/root_common_engine.py', 'engine/root_inputs.py', 'engine/root_machine.py', 'engine/root_resolution.py', 'engine/root_scheduler.py', 'engine/ruleset.py', 'engine/rulings.py', 'engine/skill_feature_actions.py', 'engine/skill_maneuver_actions.py', 'engine/skill_modifiers.py', 'engine/skill_stunts.py', 'engine/skill_targets.py', 'engine/survivalist_features.py', 'engine/temporary_hp.py', 'engine/test_builder.py', 'engine/test_contest.py', 'engine/test_downtime.py', 'engine/test_effects.py', 'engine/test_gm_state.py', 'engine/test_grid.py', 'engine/test_items.py', 'engine/test_maintenance.py', 'engine/test_playthrough.py', 'engine/test_rules.py', 'engine/test_ruleset.py', 'engine/test_rulings.py', 'engine/test_turn.py', 'engine/trainer_capabilities.py', 'engine/turn.py', 'engine/weapon_actions.py', 'engine/wild_equipment.py', 'data/content-source-identities.json', 'data/context-check-policy.json', 'data/skill-check-policy.json', 'data/adjudication-guidance.json', 'data/rulesets.json']
 report={'generated_at':datetime.now(timezone.utc).isoformat(),'successful':result.wasSuccessful(),'scope':['C3-CORE-001','C3-CORE-004'],'results':result.rows,'input_hashes':{s:hashlib.sha256((ROOT/s).read_bytes()).hexdigest() for s in paths},'scope_notes':['The intro d4 statement is retained as general expression support; no invented d4 DB row. Detailed dice-count exceptions remain their own scopes.','Campaign adoption is explicit in the selected Rules profile. The historical all profile means explicitly permitting all sources; source conflicts still hold.']}
 (ROOT/'output/category3-foundations-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 raise SystemExit(0 if result.wasSuccessful() else 1)
