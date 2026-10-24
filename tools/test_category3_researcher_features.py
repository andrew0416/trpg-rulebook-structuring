"""Researcher EX071 actual training, duration and native skill plans."""
from pathlib import Path
from datetime import datetime,timezone
from copy import deepcopy
import hashlib,json,sys,unittest
from unittest.mock import patch
import importlib.util
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from engine import Engine,Rules,Combatant
from builder import build_pokemon
from ruleset import RuleFilter,ExcludedRuleSelection
import researcher_features as RF
import downtime as DT
import common_checks as C

class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(ROOT)
 def setUp(self,*,fossil=False):
  self.e=Engine(self.r,1)
  trainer=dict(id='trainer/t',kind='trainer',name='T',level=20,stats=dict(hp=10,atk=10,**{'def':10},spa=10,spd=10,spe=10),skills={'포켓몬학':3,'명령':3},classes=[RF.RESEARCHER],feats=[RF.PUSHER,RF.SKILL_TRAINER],edges=['edge/미용사'],items={'미용사 킷':1},feature_choices={RF.RESEARCHER:[['pokemon_caretaking','paleontology']]})
  if fossil:
   trainer['skills']['포켓몬학']=5;trainer['edges'].append('edge/고생물학자');trainer['items']['복원기']=1
   trainer['feats'].extend([RF.FOSSIL_RESTORATION,RF.PREHISTORIC_BOND])
  self.t=Combatant(self.r,trainer)
  self.p=Combatant(self.r,build_pokemon(self.r,'이상해씨',10,name='P',extra={'trainer_id':'trainer/t','skills':{'육상':4,'통찰':3}}))
  self.e.everyone=[self.t,self.p];self.e.gm.everyone=self.e.everyone
 def groom(self,skill='육상'):
  return self.e.pokemon_activity(self.t,'groom',targets=[self.p],pushed_skills={self.p.spec['id']:skill},safe=True)
 def test_actual_training_grants_pushed_pool_without_changing_base_rank(self):
  before=self.e.elapsed_seconds;out=self.e.pokemon_activity(self.t,'experience_training',targets=[self.p],pushed_skills={self.p.spec['id']:'육상'},safe=True)
  self.assertEqual(self.e.elapsed_seconds-before,3600);self.assertEqual(self.p.spec['pushed_skill']['training_source'],'experience_training')
  roll=self.e.skill_roll(self.p,'육상',fixed=[2]*5)
  self.assertEqual((roll.rank,len(roll.faces),roll.total),(4,5,10));self.assertEqual(self.p.spec['skills']['육상'],4)
  self.assertEqual(self.t._action_history,['free']);self.assertTrue(out['awards'][0]>0)
 def test_grooming_actual_hour_and_one_pushed_skill_replacement_without_stacking(self):
  self.groom();self.groom('통찰')
  self.assertEqual(self.e.elapsed_seconds,7200);self.assertEqual(self.p.spec['pushed_skill']['skill'],'perception')
  self.assertEqual(len(self.e.skill_roll(self.p,'육상',fixed=[2]*4).faces),4)
  self.assertEqual(len(self.e.skill_roll(self.p,'통찰',fixed=[2]*4).faces),4)
 def test_real_pokemon_expressions_below_equal_and_above_six_keep_fixed_modifiers(self):
  for n,face_count,bonus in [(1,2,2),(5,6,2),(6,6,5),(7,7,5)]:
   with self.subTest(n=n):
    self.p.spec['skills']['육상']=str(n)+'d6+2';self.groom()
    result=self.e.skill_roll(self.p,'육상',fixed=[2]*face_count)
    self.assertEqual(result.rank,n);self.assertEqual(result.total,2*face_count+bonus)
 def test_short_rest_and_new_day_do_not_expire_but_actual_extended_rest_does(self):
  self.p.spec['skills']['육상']='7d6+2';self.groom();DT.new_day(self.p)
  DT.rest(self.e,self.p,60,rest_id='rest');self.assertIn('pushed_skill',self.p.spec)
  DT.rest(self.e,self.p,180,rest_id='rest');self.assertNotIn('pushed_skill',self.p.spec)
  self.assertEqual(self.e.skill_roll(self.p,'육상',fixed=[2]*7).total,16)
 def test_owner_field_source_and_acquisition_reject_before_time_or_push(self):
  mutators=[lambda:self.t.spec['feats'].remove(RF.PUSHER),lambda:self.t.spec['feats'].remove(RF.SKILL_TRAINER),lambda:self.t.spec['classes'].clear(),lambda:self.t.spec['skills'].update({'포켓몬학':2}),lambda:self.t.spec['feature_choices'].update({RF.RESEARCHER:[['general','paleontology']]}),lambda:self.p.spec.update(trainer_id='someone_else')]
  for change in mutators:
   self.setUp();change();before=self.e.elapsed_seconds
   with self.assertRaises(ValueError):self.groom()
   self.assertEqual(self.e.elapsed_seconds,before);self.assertNotIn('pushed_skill',self.p.spec)
 def test_choice_must_match_actual_trained_target_and_canonical_skill(self):
  for choices in ({},{'fake':'육상'},{self.p.spec['id']:'invented'}):
   with self.assertRaises(ValueError):self.e.pokemon_activity(self.t,'groom',targets=[self.p],pushed_skills=choices,safe=True)
   self.assertEqual(self.e.elapsed_seconds,0)
 def test_actual_extended_check_uses_unmodified_base_rank_attempt_limit(self):
  self.groom();out=self.e.common_action(self.p,'육상',10,mode='extended',task_id='pushed-task',interval_id='one',interval={'amount':1,'unit':'minute'},interval_completed=True,complexity=2,limited=True,fixed=[2]*5)
  self.assertEqual(out.result.total,10);self.assertEqual(out.result.attempt_limit,2)
 def test_inactive_or_nonmatching_skill_does_not_add_bonus(self):
  initial=self.e.skill_roll(self.p,'육상',fixed=[2]*4);self.groom('통찰')
  self.assertEqual(self.e.skill_roll(self.p,'육상',fixed=[2]*4).total,initial.total)
 def test_source_profile_exclusion_blocks_training_effect_before_time(self):
  self.e.r.ruleset=RuleFilter({'sources':['core'],'exclude_units':[RF.SOURCE]});self.e.r._apply_ruleset()
  try:
   with self.assertRaises(ExcludedRuleSelection):self.groom()
   self.assertEqual(self.e.elapsed_seconds,0)
  finally:self.e.r.ruleset=RuleFilter({'sources':['core']});self.e.r._apply_ruleset()

 def test_researcher_legacy_canonical_and_shared_records_normalize_without_inventing_fields(self):
  self.t.spec['research_fields']=['고생물학','포켓몬 관리'];original=deepcopy(self.t.spec)
  self.assertEqual(set(RF.researcher(self.e,self.t,'포켓몬 관리')),{'paleontology','pokemon_caretaking'});self.assertEqual(self.t.spec,original)
  del self.t.spec['feature_choices'];self.groom()
  self.t.spec['feature_choices']={RF.RESEARCHER:[['general','pokemon_caretaking']]}
  before=self.e.elapsed_seconds
  with self.assertRaises(ValueError):self.groom()
  self.assertEqual(self.e.elapsed_seconds,before)
  self.t.spec.pop('research_fields');self.t.spec['feature_choices'][RF.RESEARCHER]=[['general','pokemon_caretaking'],['apothecary','paleontology']]
  self.assertEqual(len(RF.researcher(self.e,self.t,'약사')),4)

 def restored(self,species='pokemon/아마루스',nature='노력',name='Fossil'):
  self.setUp(fossil=True)  # Initial owned Features precede Combatant creation; this does not model acquisition.
  self.e.pokemon_activity(self.t,'fossil',phase='search',site={'name':'GM deposit','fossils_present':True},dc=15,minutes=120,discovery={'id':name,'species':species},fixed=[3]*5)
  egg=self.e.pokemon_activity(self.t,'fossil',phase='restore',fossil_id=name)['egg']
  details=dict(gender='female',nature=nature,abilities=self.r.learnsets[species.removeprefix('pokemon/')]['abilities']['기본 특성'][:1],moves=[],inheritance_moves=[],special_appearance=False)
  return self.e.pokemon_activity(self.t,'hatch_fossil',egg_id=egg['id'],name=name,ready=True,reason='GM confirmed actual egg hatch',details=details)['pokemon']
 def crown(self,p,**kw):return self.e.craft_relic_crown(self.t,p,minutes=10,**kw)
 def test_source_snapshot_entire_named_effects_and_anchor_hashes_match(self):
  row=next(x for x in json.loads((ROOT/'data/verification/category3-register.json').read_text(encoding='utf-8'))['entries'] if x['id']=='C3-EX-071')
  self.assertEqual(row['scope_sha256'],'6e3b0af5aa76c1cb8dcef5b96373f942c0a891f3f0087cf4a970d707499c02b9')
  for a in row['source_snapshot']['source_anchors']:
   text='\n'.join((ROOT/a['file']).read_text(encoding='utf-8-sig').splitlines()[a['start_line']-1:a['end_line']])
   self.assertEqual(hashlib.sha256(text.encode()).hexdigest(),a['excerpt_sha256'])
 def test_actual_fossil_hatch_crown_production_equipment_and_native_start_end_saves(self):
  import items as ITEMS
  p=self.restored();before=self.e.elapsed_seconds;record=self.crown(p);identity=record['id']
  self.assertEqual(self.e.elapsed_seconds-before,600);self.assertEqual(record['highest_stats'],['hp'])
  self.assertEqual(p.save_mod,0);self.e.equip_relic_crown(self.t,p,identity)
  self.assertEqual((p.save_mod,self.t.spec['items'][identity]),(2,0))
  p.conditions={'마비'}
  with patch.object(self.e,'d20',return_value=9):self.assertIsNone(self.e.start_of_turn(p))
  p.conditions={'혼란'}
  dc=next(x['dc'] for x in self.r.condition_effects('혼란') if x['type']=='save')
  with patch.object(self.e,'d20',return_value=dc-2):self.e.end_of_turn(p)
  self.assertNotIn('혼란',p.conditions)
  self.assertEqual(ITEMS.register_item(self.e,p,identity),0);self.assertEqual(p.save_mod,2)
  ITEMS.unregister_item(self.e,p,identity);self.assertEqual(p.save_mod,0)
  p.conditions={'마비'}
  with patch.object(self.e,'d20',return_value=9):self.assertIsNotNone(self.e.start_of_turn(p))
 def test_all_native_saving_conditions_use_the_same_equipped_two_point_bonus(self):
  import effects_ext as EXT
  p=self.restored();identity=self.crown(p)['id'];self.e.equip_relic_crown(self.t,p,identity)
  seen=[]
  for cond in ('마비','얼음','잠듦','혼란','헤롱헤롱','난동'):
   for effect in self.r.condition_effects(cond):
    if effect['type']=='save':
     seen.append(cond);self.assertEqual(EXT.save_dc(self.e,p,cond,effect['dc']),effect['dc']-2)
  self.assertGreaterEqual(len(seen),5)
 def test_crown_uses_species_and_nature_only_and_keeps_gm_tie_choice(self):
  p=self.restored(nature='외로움');p.stats['spe']=200;p.spec['base_stats']={'hp':999};p.spec['vitamins']={'hp':20}
  before=self.e.elapsed_seconds
  for kw in ({},{'tie_stat':'atk','tie_reason':'other stat'},{'tie_stat':'hp'}):
   with self.assertRaises(ValueError):self.crown(p,**kw)
   self.assertEqual(self.e.elapsed_seconds,before)
  r=self.crown(p,tie_stat='hp',tie_reason='GM selected HP among equal base HP and Attack')
  self.assertEqual(r['highest_stats'],['hp','atk']);self.assertEqual(r['base_stats_with_nature']['hp'],8)
  self.assertEqual(r['base_stats_with_nature']['spe'],5)
 def test_non_hp_highest_refused_even_when_allocated_actual_hp_is_larger(self):
  p=self.restored(species='pokemon/투구');p.stats['hp']=500
  before=self.e.elapsed_seconds
  with self.assertRaises(ValueError):self.crown(p)
  self.assertEqual(self.e.elapsed_seconds,before)
 def test_crown_actual_prerequisite_ownership_and_remains_reuse_boundaries(self):
  mutations=[lambda:self.t.spec['feats'].remove(RF.FOSSIL_RESTORATION),lambda:self.t.spec['feats'].remove(RF.PREHISTORIC_BOND),lambda:self.t.spec['edges'].remove('edge/고생물학자'),lambda:self.t.spec['skills'].update({'포켓몬학':4}),lambda:self.t.spec['feature_choices'].update({RF.RESEARCHER:[['general','pokemon_caretaking']]}),lambda:p.spec.update(trainer_id='other')]
  for mutate in mutations:
   self.setUp();p=self.restored();mutate();before=self.e.elapsed_seconds
   with self.assertRaises(ValueError):self.crown(p)
   self.assertEqual(self.e.elapsed_seconds,before);self.assertNotIn('relic_items',self.t.spec)
  self.setUp();p=self.restored();self.crown(p);before=self.e.elapsed_seconds
  with self.assertRaises(ValueError):self.crown(p)
  self.assertEqual(self.e.elapsed_seconds,before)
 def test_crown_wrong_individual_missing_native_origin_or_occupied_slot_has_no_effect(self):
  import items as ITEMS
  p=self.restored();identity=self.crown(p)['id']
  other=Combatant(self.r,deepcopy(p.spec));other.spec['id']='pokemon/other'
  self.assertEqual(ITEMS.register_item(self.e,other,identity),0);self.assertEqual(other.save_mod,0)
  with self.assertRaises(ValueError):self.e.equip_relic_crown(self.t,other,identity)
  p.item='기합의띠'
  with self.assertRaises(ValueError):self.e.equip_relic_crown(self.t,p,identity)
  p.item=None
  origin=p.spec.pop('fossil_egg_entity_id')
  try:
   with self.assertRaises(ValueError):self.e.equip_relic_crown(self.t,p,identity)
  finally:p.spec['fossil_egg_entity_id']=origin
  self.assertEqual(self.t.spec['items'][identity],1);self.assertEqual(p.save_mod,0)
 def test_crown_selected_source_and_extended_action_are_checked_before_time(self):
  p=self.restored();before=self.e.elapsed_seconds
  self.t.conditions={'잠듦'}
  with self.assertRaises(ValueError):self.crown(p)
  self.t.conditions.clear();self.e.encounter_active=True
  with self.assertRaises(ValueError):self.crown(p)
  self.e.encounter_active=False
  self.e.r.ruleset=RuleFilter({'sources':['core'],'exclude_units':[RF.SOURCE]});self.e.r._apply_ruleset()
  try:
   with self.assertRaises(ExcludedRuleSelection):self.crown(p)
  finally:self.e.r.ruleset=RuleFilter({'sources':['core']});self.e.r._apply_ruleset()
  self.assertEqual(self.e.elapsed_seconds,before)
 def test_reliable_average_uses_pushed_actual_dice_and_preserves_large_pool_modifier(self):
  import contest_features as CF
  self.t.spec['classes'].append('class/코디네이터');self.t.spec['edges'].append('edge/우아함')
  self.t.spec['feats'].extend([CF.NUANCED,CF.RELIABLE]);self.t.spec['skills']['매력']=6
  self.groom();out=self.e.contest_skill_feature(self.t,self.p,CF.RELIABLE,'육상',10)
  self.assertEqual((out['roll'].rank,out['roll'].base),(4,17))
  self.p.spec['skills']['육상']='7d6+2';out=self.e.contest_skill_feature(self.t,self.p,CF.RELIABLE,'육상',10)
  self.assertEqual((out['roll'].base,out['roll'].total),(24,29))
 def test_pushed_skill_keeps_bonus_in_actual_contest_reroll_and_replacement_pool(self):
  import contest_features as CF
  path=ROOT/'tools/test_category3_contest_skill_features.py';spec=importlib.util.spec_from_file_location('contest_fixture',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
  fixture=module.Tests();fixture.r=self.r
  for stat,feature in [('근사함',CF.STUNT),('슬기로움',CF.MISTAKES)]:
   fixture.fixture(stat,feature);e,t,p=fixture.e,fixture.t,fixture.p
   t.spec['classes'].append(RF.RESEARCHER);t.spec['feats'].extend([RF.PUSHER,RF.SKILL_TRAINER]);t.spec['edges'].append('edge/미용사');t.spec['items']={'미용사 킷':1};t.spec['skills']['포켓몬학']=3
   t.spec['feature_choices'][RF.RESEARCHER]=[['pokemon_caretaking','paleontology']]
   e.pokemon_activity(t,'groom',targets=[p],pushed_skills={p.spec['id']:'육상'},safe=True)
   if feature==CF.STUNT:
    out=fixture.stunt(fixed=[1]*6);self.assertEqual(len(out['roll'].faces),6)
    p.spec['poffins']=['근사함']*6
    out=fixture.stunt(fixed=[1]*8);self.assertEqual((len(out['roll'].faces),out['roll'].modifier),(8,5))
   else:
    out=fixture.mistakes(fixed=[1]*4,reroll_faces=[2]*4);self.assertEqual(len(out['roll'].faces),4)

if __name__=='__main__':
 class Result(unittest.TextTestResult):
  def __init__(self,*a,**kw):super().__init__(*a,**kw);self.rows=[]
  def addSuccess(self,t):super().addSuccess(t);self.rows.append({'id':t._testMethodName,'status':'pass'})
  def addFailure(self,t,e):super().addFailure(t,e);self.rows.append({'id':t._testMethodName,'status':'fail'})
  def addError(self,t,e):super().addError(t,e);self.rows.append({'id':t._testMethodName,'status':'error'})
 result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
 files=['engine/adjudication_guidance.py','data/adjudication-guidance.json','engine/skill_maneuver_actions.py','engine/food_effects.py','engine/combat_social_edges.py','engine/net_capsule.py','engine/trainer_capabilities.py','engine/skill_feature_actions.py','engine/researcher_features.py','engine/precise_actions.py','engine/environmental_effects.py','engine/wild_equipment.py','engine/injury_recovery.py','engine/downtime.py','engine/items.py','engine/skill_modifiers.py','engine/common_action_checks.py','engine/gm_state.py','engine/heavy_injury_adapter.py','engine/jump_actions.py','engine/context_actions.py','engine/pokemon_requests.py','engine/combat_timing.py','engine/combat_maneuvers.py','data/context-check-policy.json','data/cultivation-policy.json',*sorted(str(p.relative_to(ROOT)).replace('\\','/') for p in (ROOT/'engine').glob('*.py')),'tools/test_category3_researcher_features.py','tools/test_category3_contest_skill_features.py','data/core-rules.json','data/rulesets.json','output/ruleunits.jsonl','input/ch03-skills-edges-feats.md','input/ch04-trainer-classes.md','input/ch05-pokemon.md','data/skill-check-policy.json']
 files += ['engine/campaign_rewards.py', 'engine/league_consequences.py', 'data/campaign-reward-policy.json']
 files += ['engine/pokemon_understanding.py', 'engine/regional_pokemon.py', 'engine/source_context.py']
 files += ['engine/blessing_skill_features.py', 'engine/combat_precision_features.py', 'engine/pokemon_intelligence.py', 'engine/pokemon_party.py', 'engine/pokemon_teaching.py', 'data/pokemon-machines.json']

 files += ['engine/arithmetic.py', 'engine/arithmetic_policy.py', 'engine/effect_contracts.py', 'engine/effect_lifetimes.py', 'engine/maneuver_grants.py', 'engine/move_activation.py', 'engine/native_rule_policy.py', 'data/native-rule-policy.json']

 files += ['engine/action_lifecycle.py', 'engine/action_metadata.py', 'engine/action_points.py', 'engine/adjudication_guidance.py', 'engine/ap_roll_bonus.py', 'engine/bandages.py', 'engine/bound_ap.py', 'engine/builder.py', 'engine/capability_actions.py', 'engine/combat_maneuvers.py', 'engine/combat_social_edges.py', 'engine/combat_stage_sources.py', 'engine/combat_timing.py', 'engine/common_action_checks.py', 'engine/common_checks.py', 'engine/contest.py', 'engine/contest_features.py', 'engine/context_actions.py', 'engine/crafting_activities.py', 'engine/custom_species.py', 'engine/damage_reactions.py', 'engine/demo_rulings.py', 'engine/downtime.py', 'engine/effects.py', 'engine/effects_ext.py', 'engine/elemental_connection.py', 'engine/encounter.py', 'engine/enduring_awareness.py', 'engine/engine.py', 'engine/environmental_effects.py', 'engine/focus_tasks.py', 'engine/food_effects.py', 'engine/frequency.py', 'engine/gm_console.py', 'engine/gm_state.py', 'engine/grid.py', 'engine/heavy_injury_adapter.py', 'engine/heavy_injury_kernel.py', 'engine/heavy_standard_adapter.py', 'engine/initiative.py', 'engine/injury_recovery.py', 'engine/items.py', 'engine/jump_actions.py', 'engine/league_agenda.py', 'engine/league_runtime.py', 'engine/life.py', 'engine/maneuver_edges.py', 'engine/movement_actions.py', 'engine/net_capsule.py', 'engine/observed_resolution.py', 'engine/passive_event_profiles.py', 'engine/passive_events.py', 'engine/physical_limits.py', 'engine/physics_maneuvers.py', 'engine/pokemon_activities.py', 'engine/pokemon_requests.py', 'engine/precise_actions.py', 'engine/researcher_features.py', 'engine/resolution_transaction.py', 'engine/rest_intervals.py', 'engine/restorative_items.py', 'engine/root_admission.py', 'engine/root_children.py', 'engine/root_common_checks.py', 'engine/root_common_engine.py', 'engine/root_inputs.py', 'engine/root_machine.py', 'engine/root_resolution.py', 'engine/root_scheduler.py', 'engine/ruleset.py', 'engine/rulings.py', 'engine/skill_feature_actions.py', 'engine/skill_maneuver_actions.py', 'engine/skill_modifiers.py', 'engine/skill_stunts.py', 'engine/skill_targets.py', 'engine/survivalist_features.py', 'engine/temporary_hp.py', 'engine/test_builder.py', 'engine/test_contest.py', 'engine/test_downtime.py', 'engine/test_effects.py', 'engine/test_gm_state.py', 'engine/test_grid.py', 'engine/test_items.py', 'engine/test_maintenance.py', 'engine/test_playthrough.py', 'engine/test_rules.py', 'engine/test_ruleset.py', 'engine/test_rulings.py', 'engine/test_turn.py', 'engine/trainer_capabilities.py', 'engine/turn.py', 'engine/weapon_actions.py', 'engine/wild_equipment.py', 'data/content-source-identities.json', 'data/context-check-policy.json', 'data/skill-check-policy.json', 'data/adjudication-guidance.json', 'data/rulesets.json']
 report={'generated_at':datetime.now(timezone.utc).isoformat(),'successful':result.wasSuccessful(),'scope':['C3-EX-071'],'completion_scopes':['C3-EX-071'],'partial_scopes':[],'source_scope_sha256':'6e3b0af5aa76c1cb8dcef5b96373f942c0a891f3f0087cf4a970d707499c02b9','results':result.rows,'input_hashes':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in files}}
 (ROOT/'output/category3-researcher-feature-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 raise SystemExit(not result.wasSuccessful())

