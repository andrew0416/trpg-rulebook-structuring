"""Actual Awareness acquisition, native save consumers and owner lifetime."""
from pathlib import Path
from copy import deepcopy
from datetime import datetime,timezone
import hashlib,json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Engine,Rules,Combatant
from grid import Grid
from ruleset import RuleFilter,ExcludedRuleSelection
import enduring_awareness as A
import effects_ext as EXT
import items as ITEMS
import turn as TURN
class FixedRng:
 def __init__(self,values):self.values=list(values)
 def randint(self,lo,hi):
  n=self.values.pop(0);assert lo<=n<=hi;return n
class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(ROOT)
 def actor(self,uid,kind='pokemon'):
  return Combatant(self.r,{'id':uid,'name':uid,'kind':kind,'level':20,'trainer_id':'t','stats':dict(hp=20,atk=10,**{'def':10},spa=10,spd=10,spe=10),'skills':{'육상':3,'집중':3,'기술학':4},'movement':{'power':5,'land':6},'abilities':['두꺼운지방'] if kind=='pokemon' else []})
 def setUp(self):
  self.e=Engine(self.r,7);self.t=self.actor('t','trainer');self.p=[self.actor('p'+str(i)) for i in range(3)];self.t.spec.update(classes=[A.ENDURING],feats=[A.AWARENESS])
  self.e.everyone=[self.t,*self.p];self.e.gm.everyone=self.e.everyone
 def records(self):return [{'pokemon':p,'ability':'두꺼운지방','defensive_reason':'reduces incoming elemental damage'} for p in self.p]
 def confirm(self):return self.e.gm.confirm_awareness(self.t,self.records(),reason='GM confirms actual acquisition with defensive Pokemon')
 def test_actual_source_prerequisites_and_historical_acquisition_are_preserved(self):
  r=self.confirm();self.assertEqual(len(r['defenders']),3);self.assertEqual(A.bonus(self.e,self.p[0]),2);self.assertEqual(A.bonus(self.e,self.t),0)
  self.p[1].abilities.clear();self.p[1].spec['trainer_id']='elsewhere';self.assertEqual(A.bonus(self.e,self.p[0]),2)
 def test_unowned_feature_class_or_skill_cannot_confirm(self):
  for field,value in [('feats',[]),('classes',[]),('skills',{'육상':2,'집중':3})]:
   self.setUp();self.t.spec[field]=value
   with self.assertRaises(ValueError):self.confirm()
   self.assertNotIn('_awareness_acquisition',self.t.spec)
 def test_three_distinct_actual_owned_pokemon_and_defensive_reasons_required(self):
  for mutate in (lambda rows:rows.pop(),lambda rows:rows.__setitem__(2,rows[0]),lambda rows:rows[0].update(ability='no ability'),lambda rows:rows[0].update(defensive_reason='')):
   self.setUp();rows=self.records();mutate(rows)
   with self.assertRaises(ValueError):self.e.gm.confirm_awareness(self.t,rows,reason='GM evidence')
   self.assertNotIn('_awareness_acquisition',self.t.spec)
  self.setUp();self.p[0].spec['trainer_id']='another'
  with self.assertRaises(ValueError):self.confirm()
 def test_missing_acquisition_is_held_before_native_save_rng_or_turn_cost(self):
  p=self.p[0];p.conditions.add('마비');self.e.start_round(self.e.everyone);state=self.e.rng.getstate()
  with self.assertRaises(ValueError):self.e.start_of_turn(p,initiative_count=10)
  self.assertEqual(self.e.rng.getstate(),state);self.assertIsNone(self.e._active_turn_actor)
 def test_all_condition_saving_checks_receive_two_not_just_specific_status_group(self):
  self.confirm()
  for condition in ('마비','얼음','잠듦','혼란','난동','헤롱헤롱',None):
   self.assertEqual(EXT.save_dc(self.e,self.p[0],condition,15),13)
 def test_actual_paralysis_boundary_passes_without_curing_or_granting_extra_action(self):
  self.confirm();p=self.p[0];self.e.apply_status(p,'마비');self.e.start_round(self.e.everyone);self.e.rng=FixedRng([9]);self.e.start_of_turn(p,initiative_count=10)
  self.assertIsNone(p._turn_action_limit);self.assertIn('마비',p.conditions);self.assertEqual(p.budget,{'standard':1,'shift':1,'swift':1});self.assertFalse(self.e.rng.values)
 def test_actual_sleep_save_success_uses_bonus_and_cures_through_native_end_turn(self):
  self.confirm();p=self.p[0];self.e.apply_status(p,'잠듦');self.e.start_round(self.e.everyone);self.e.start_of_turn(p,initiative_count=10)
  saves=[x for x in self.r.condition_effects('잠듦') if x.get('type')=='save'];dc=saves[0]['dc'];self.e.rng=FixedRng([dc-2]);self.e.end_of_turn(p);self.assertNotIn('잠듦',p.conditions)
 def test_native_unrelated_pokemon_and_trainer_do_not_receive_owner_bonus(self):
  self.confirm();other=self.actor('foreign');other.spec['trainer_id']='other';self.e.everyone.append(other)
  self.assertEqual(EXT.save_dc(self.e,other,'마비',11),11);self.assertEqual(EXT.save_dc(self.e,self.t,'마비',11),11)
 def test_lost_ownership_and_removed_feature_stop_the_bonus_without_stale_static_value(self):
  self.confirm();p=self.p[0];self.assertEqual(p.save_mod,0);p.spec['trainer_id']='elsewhere';self.assertEqual(A.bonus(self.e,p),0)
  p.spec['trainer_id']='t';self.t.spec['feats']=[];self.assertEqual(A.bonus(self.e,p),0)
 def test_fainted_owner_cannot_apply_a_feature_but_recovery_restores_eligibility(self):
  self.confirm();self.t.hp=0;self.assertEqual(A.bonus(self.e,self.p[0]),0);self.t.hp=1;self.assertEqual(A.bonus(self.e,self.p[0]),2)
 def test_repeated_registration_does_not_duplicate_save_mod_or_grant_trainer_bonus(self):
  self.confirm();ITEMS.register_feats(self.e,self.t,pokemon=self.p);ITEMS.register_feats(self.e,self.t,pokemon=self.p)
  self.assertEqual([p.save_mod for p in [self.t,*self.p]],[0]*4);self.assertEqual(EXT.save_dc(self.e,self.p[0],'마비',11),9)
 def test_other_actual_equipment_bonus_stacks_without_being_replaced(self):
  self.confirm();p=self.p[0];p.save_mod=3;self.assertEqual(EXT.save_dc(self.e,p,'마비',11),6)
 def test_duplicate_feature_aliases_and_duplicate_trainer_ids_are_rejected(self):
  self.confirm();self.t.spec['feats'].append('Awareness')
  with self.assertRaises(ValueError):A.bonus(self.e,self.p[0])
  self.t.spec['feats'].pop();self.e.everyone.append(self.actor('t','trainer'))
  with self.assertRaises(ValueError):A.bonus(self.e,self.p[0])
 def test_selected_source_exclusion_is_checked_at_actual_save(self):
  self.confirm();r=Rules(ROOT);r.ruleset=RuleFilter({'sources':['core'],'exclude_units':[A.AWARENESS]});r._apply_ruleset();self.e.r=r
  with self.assertRaises(ExcludedRuleSelection):A.bonus(self.e,self.p[0])
 def test_native_net_save_total_and_dc_show_real_bonus_once(self):
  from test_category3_net_capsule import NetTests
  fixture=NetTests();fixture.rules=self.r;fixture.setUp();e,t,p=fixture.e,fixture.a,fixture.p
  for actor in [*e.everyone,*e.gm.everyone]:actor.spec.setdefault('size','Medium')
  t.spec.update(classes=[A.ENDURING],feats=[A.AWARENESS],skills={'육상':3,'집중':3,'기술학':4});p.spec['trainer_id']=t.spec['id'];p.abilities=['두꺼운지방']
  extra=[]
  for i in range(2):
   q=self.actor('additional'+str(i));q.spec.update(trainer_id=t.spec['id'],size='Medium');q.side=t.side;q.pos=(15+i,15);extra.append(q);e.everyone.append(q)
  rows=[{'pokemon':q,'ability':'두꺼운지방','defensive_reason':'native incoming damage defense'} for q in [p,*extra]]
  e.gm.confirm_awareness(t,rows,reason='GM actual acquisition');fixture.fire();out=e.remove_net(p,fixed=8)
  self.assertTrue(out['removed']);self.assertEqual(out['check']['total'],15);self.assertEqual(out['check']['dc'],15);self.assertEqual(out['check']['save_modifier'],2)
 def test_gm_snapshot_restores_feature_evidence_and_live_owner_lookup(self):
  self.confirm();self.e.gm.snapshot('awareness');self.t.spec['feats']=[];self.assertEqual(A.bonus(self.e,self.p[0]),0);self.e.gm.restore('awareness');self.assertEqual(A.bonus(self.e,self.p[0]),2)
 def test_exact_fixed_clause_and_metadata_sources_remain_unchanged(self):
  r=json.loads((ROOT/'data/verification/category3-register.json').read_text(encoding='utf-8'));entry=next(x for x in r['entries'] if x['id']=='C3-EX-055')
  for a in entry['source_snapshot']['source_anchors']:
   lines=(ROOT/a['file']).read_text(encoding='utf-8-sig').splitlines();self.assertEqual('\n'.join(lines[a['start_line']-1:a['end_line']]),a['excerpt'])
if __name__=='__main__':
 class Result(unittest.TextTestResult):
  def __init__(self,*a,**kw):super().__init__(*a,**kw);self.rows=[]
  def addSuccess(self,t):super().addSuccess(t);self.rows.append({'id':t._testMethodName,'status':'pass'})
  def addFailure(self,t,e):super().addFailure(t,e);self.rows.append({'id':t._testMethodName,'status':'fail'})
  def addError(self,t,e):super().addError(t,e);self.rows.append({'id':t._testMethodName,'status':'error'})
 result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
 files=['engine/enduring_awareness.py','engine/engine.py','engine/turn.py','engine/effects_ext.py','engine/items.py','engine/net_capsule.py','engine/gm_state.py','engine/skill_modifiers.py','engine/action_lifecycle.py','engine/combat_social_edges.py','engine/food_effects.py','input/ch04-trainer-classes.md','tools/test_category3_awareness.py']
 files += ['engine/campaign_rewards.py', 'engine/league_consequences.py', 'data/campaign-reward-policy.json']
 files += ['engine/pokemon_understanding.py', 'engine/regional_pokemon.py', 'engine/source_context.py']
 files += ['engine/blessing_skill_features.py', 'engine/combat_precision_features.py', 'engine/pokemon_intelligence.py', 'engine/pokemon_party.py', 'engine/pokemon_teaching.py', 'data/pokemon-machines.json']

 files += ['engine/arithmetic.py', 'engine/arithmetic_policy.py', 'engine/effect_contracts.py', 'engine/effect_lifetimes.py', 'engine/maneuver_grants.py', 'engine/move_activation.py', 'engine/native_rule_policy.py', 'data/native-rule-policy.json']

 files += ['engine/action_lifecycle.py', 'engine/action_metadata.py', 'engine/action_points.py', 'engine/adjudication_guidance.py', 'engine/ap_roll_bonus.py', 'engine/bandages.py', 'engine/bound_ap.py', 'engine/builder.py', 'engine/capability_actions.py', 'engine/combat_maneuvers.py', 'engine/combat_social_edges.py', 'engine/combat_stage_sources.py', 'engine/combat_timing.py', 'engine/common_action_checks.py', 'engine/common_checks.py', 'engine/contest.py', 'engine/contest_features.py', 'engine/context_actions.py', 'engine/crafting_activities.py', 'engine/custom_species.py', 'engine/damage_reactions.py', 'engine/demo_rulings.py', 'engine/downtime.py', 'engine/effects.py', 'engine/effects_ext.py', 'engine/elemental_connection.py', 'engine/encounter.py', 'engine/enduring_awareness.py', 'engine/engine.py', 'engine/environmental_effects.py', 'engine/focus_tasks.py', 'engine/food_effects.py', 'engine/frequency.py', 'engine/gm_console.py', 'engine/gm_state.py', 'engine/grid.py', 'engine/heavy_injury_adapter.py', 'engine/heavy_injury_kernel.py', 'engine/heavy_standard_adapter.py', 'engine/initiative.py', 'engine/injury_recovery.py', 'engine/items.py', 'engine/jump_actions.py', 'engine/league_agenda.py', 'engine/league_runtime.py', 'engine/life.py', 'engine/maneuver_edges.py', 'engine/movement_actions.py', 'engine/net_capsule.py', 'engine/observed_resolution.py', 'engine/passive_event_profiles.py', 'engine/passive_events.py', 'engine/physical_limits.py', 'engine/physics_maneuvers.py', 'engine/pokemon_activities.py', 'engine/pokemon_requests.py', 'engine/precise_actions.py', 'engine/researcher_features.py', 'engine/resolution_transaction.py', 'engine/rest_intervals.py', 'engine/restorative_items.py', 'engine/root_admission.py', 'engine/root_children.py', 'engine/root_common_checks.py', 'engine/root_common_engine.py', 'engine/root_inputs.py', 'engine/root_machine.py', 'engine/root_resolution.py', 'engine/root_scheduler.py', 'engine/ruleset.py', 'engine/rulings.py', 'engine/skill_feature_actions.py', 'engine/skill_maneuver_actions.py', 'engine/skill_modifiers.py', 'engine/skill_stunts.py', 'engine/skill_targets.py', 'engine/survivalist_features.py', 'engine/temporary_hp.py', 'engine/test_builder.py', 'engine/test_contest.py', 'engine/test_downtime.py', 'engine/test_effects.py', 'engine/test_gm_state.py', 'engine/test_grid.py', 'engine/test_items.py', 'engine/test_maintenance.py', 'engine/test_playthrough.py', 'engine/test_rules.py', 'engine/test_ruleset.py', 'engine/test_rulings.py', 'engine/test_turn.py', 'engine/trainer_capabilities.py', 'engine/turn.py', 'engine/weapon_actions.py', 'engine/wild_equipment.py', 'data/content-source-identities.json', 'data/context-check-policy.json', 'data/skill-check-policy.json', 'data/adjudication-guidance.json', 'data/rulesets.json']
 report={'generated_at':datetime.now(timezone.utc).isoformat(),'successful':result.wasSuccessful(),'scope':['C3-EX-055'],'full_scope_verified':True,'results':result.rows,'input_hashes':{f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files},'boundaries':['Defensive ability categorization requires an explicit GM classification on three actual owned Pokemon at acquisition.','Acquisition evidence is historical; current owner/feature and conscious trainer determine the passive save benefit.','No automated bonus to trainer saves; no automatic save is granted when another rule forbids the save.']}
 (ROOT/'output/category3-awareness-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 raise SystemExit(0 if result.wasSuccessful() else 1)
