"""Actual source-selected terrain and Terrain Talent check consumers."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
from datetime import datetime,timezone
import hashlib,json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from engine import Engine,Rules,Combatant
from grid import Grid
from ruleset import RuleFilter,ExcludedRuleSelection
import survivalist_features as V
import skill_feature_actions as SF
import common_checks as C
import turn as TURN
class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(ROOT)
 def setUp(self):
  # Both synthetic movement fixtures are observed one-cell Medium bodies.
  self.e=Engine(self.r,seed=3)
  self.a=Combatant(self.r,{'id':'trainer/a','name':'A','kind':'trainer','size':'중형','level':20,'stats':dict(hp=10,atk=10,**{'def':10},spa=10,spd=10,spe=10),'skills':{'생존':6,'육상':4,'곡예':4,'은신':3,'통찰':3,'집중':3},'classes':[V.SURVIVALIST],'feats':[],'movement':{'land':6}})
  self.b=Combatant(self.r,{'id':'trainer/b','name':'B','kind':'trainer','size':'중형','level':20,'stats':dict(hp=10,atk=10,**{'def':10},spa=10,spd=10,spe=10),'skills':{'육상':4},'pos':(5,0)})
  self.e.everyone=[self.a,self.b]
 def env(self,*terrains,light='normal'):
  return V.observe_environment(self.e,self.a,terrains=terrains,light=light,reason='GM actual terrain and light')
 def night(self,terrain,identity):
  self.env(terrain);V.begin_night(self.e,self.a,night_id=identity,terrain_name=terrain,reason='GM overnight beginning')
  self.e.advance_time(60,[self.a]);return V.finish_night(self.e,self.a,night_id=identity,reason='GM overnight completed')
 def master(self,terrain):
  for n in range(3):self.night(terrain,terrain+str(n))
  return V.select_terrain(self.e,self.a,terrain_name=terrain,minutes=7,reason='GM Extended selection duration')
 def talent(self,*terrains):
  self.a.spec['feats'].append('feat/내추럴-파이터')
  for terrain in terrains:self.master(terrain)
  self.a.spec['feats'].append(V.TALENT);self.a.spec['feat_ranks']={V.TALENT:1}
  V.choose_talents(self.e,self.a,terrains=terrains)
 def context(self,purpose):return {'purpose':purpose,'reason':'GM concrete skill purpose'}
 def opts(self,skill='생존',faces=None,**kw):
  n=6 if skill=='생존' else 4
  check={'skill':skill,'fixed':faces or [2]*n};check.update(kw)
  return {'movement_id':'walk1','frequency':'once_per_shift','reason':'GM one check over this continuous terrain','check_options':[check]}
 def movement(self):
  self.e.grid=Grid(6,1,rough={(1,0),(2,0)});self.a.pos=(0,0);self.b.pos=(5,0)
  TURN.reset_budget(self.e,self.a)
 def test_actual_three_nights_and_extended_selection_records_clock_once(self):
  self.master('cave');self.assertEqual(self.e.elapsed_seconds,600);self.assertEqual(V.selected(self.e,self.a),('cave',))
  self.assertEqual(self.a._action_history,['extended']);before=self.e.elapsed_seconds
  with self.assertRaises(ValueError):V.select_terrain(self.e,self.a,terrain_name='cave',minutes=7,reason='repeat')
  self.assertEqual(self.e.elapsed_seconds,before)
 def test_missing_third_night_and_wrong_terrain_fail_without_time(self):
  for n in range(2):self.night('cave',str(n))
  before=self.e.elapsed_seconds
  for terrain in ('cave','forest'):
   with self.assertRaises(ValueError):V.select_terrain(self.e,self.a,terrain_name=terrain,minutes=1,reason='GM selection')
  self.assertEqual(self.e.elapsed_seconds,before)
 def test_duplicate_zero_duration_and_interrupted_overnights_reject(self):
  self.env('cave');V.begin_night(self.e,self.a,night_id='n',terrain_name='cave',reason='begin')
  with self.assertRaises(ValueError):V.finish_night(self.e,self.a,night_id='n',reason='end')
  with self.assertRaises(ValueError):V.begin_night(self.e,self.a,night_id='n2',terrain_name='cave',reason='begin')
  self.e.advance_time(60,[self.a]);self.env('forest');self.env('cave')
  with self.assertRaises(ValueError):V.finish_night(self.e,self.a,night_id='n',reason='end')
 def test_actual_class_novice_and_known_source_required(self):
  for mutation in (lambda:self.a.spec.update(classes=[]),lambda:self.a.spec['skills'].update({'생존':2})):
   self.setUp();mutation();before=self.e.elapsed_seconds
   with self.assertRaises(ValueError):V.select_terrain(self.e,self.a,terrain_name='cave',minutes=1,reason='GM selection')
   self.assertEqual(self.e.elapsed_seconds,before)
 def test_additional_terrain_requires_actual_two_four_six_feature_counts(self):
  self.master('cave')
  for n in range(3):self.night('forest','forest'+str(n))
  with self.assertRaises(ValueError):V.select_terrain(self.e,self.a,terrain_name='forest',minutes=1,reason='GM')
  self.a.spec['feats'].append('feat/내추럴-파이터');V.select_terrain(self.e,self.a,terrain_name='forest',minutes=1,reason='GM')
  self.a.spec['feats'].extend(['feat/트래퍼','feat/야생-가이드']);self.master('mountain')
  for n in range(3):self.night('urban','urban'+str(n))
  with self.assertRaises(ValueError):V.select_terrain(self.e,self.a,terrain_name='urban',minutes=1,reason='GM')
  self.a.spec['feats'].append(V.TALENT);self.a.spec['feat_ranks']={V.TALENT:1};V.choose_talents(self.e,self.a,terrains=['cave','forest'])
  self.a.spec['feats'].append('feat/지리-적응');V.select_terrain(self.e,self.a,terrain_name='urban',minutes=1,reason='GM')
  self.assertEqual(len(V.selected(self.e,self.a)),4)
  self.a.spec['feat_ranks'][V.TALENT]=2;V.choose_talents(self.e,self.a,terrains=['cave','forest','mountain','urban']);self.assertEqual(len(V.talents(self.e,self.a)),4)
 def test_talent_requires_two_mastered_terrains_and_distinct_choices(self):
  self.master('cave');self.a.spec['feats']=[V.TALENT];self.a.spec['feat_ranks']={V.TALENT:1}
  with self.assertRaises(ValueError):V.choose_talents(self.e,self.a,terrains=['cave','forest'])
  self.master('forest')
  with self.assertRaises(ValueError):V.choose_talents(self.e,self.a,terrains=['cave','cave'])
  V.choose_talents(self.e,self.a,terrains=['cave','forest'])
  with self.assertRaises(ValueError):V.choose_talents(self.e,self.a,terrains=['forest','cave'])
 def test_native_five_skills_get_terrain_bonus_and_other_skills_do_not(self):
  self.master('cave');self.env('cave')
  for skill,n in [('생존',6),('육상',4),('곡예',4),('은신',3),('통찰',3),('집중',3)]:
   out=self.e.skill_roll(self.a,skill,fixed=[1]*n);self.assertEqual(out.total,n+(0 if skill=='집중' else 2))
  self.env('forest');self.assertEqual(self.e.skill_roll(self.a,'Survival',fixed=[1]*6).total,6)
 def test_multiple_matching_terrains_never_duplicate_base_bonus(self):
  self.talent('grassland','mountain');self.env('grassland','mountain')
  self.assertEqual(self.e.skill_roll(self.a,'육상',fixed=[1]*4).total,6)
 def test_actual_unknown_current_environment_holds_before_rng(self):
  self.master('cave');self.a.spec.pop('_survivalist_environment');state=self.e.rng.getstate()
  with self.assertRaises(ValueError):self.e.skill_roll(self.a,'생존')
  self.assertEqual(self.e.rng.getstate(),state)
 def test_plains_distant_perception_works_outside_grassland_and_only_for_that_check(self):
  self.talent('grassland','mountain');self.env('urban')
  self.assertEqual(self.e.skill_roll(self.a,'통찰',fixed=[1]*3,skill_context=self.context('distant_object')).total,5)
  self.assertEqual(self.e.skill_roll(self.a,'통찰',fixed=[1]*3).total,3)
  self.assertEqual(self.e.skill_roll(self.a,'생존',fixed=[1]*6,skill_context=self.context('distant_object')).total,6)
 def test_surefooted_context_and_actual_opposed_defender_use_bonus(self):
  self.talent('grassland','mountain');self.env('urban')
  for purpose in ('climb','balance','maintain_footing','resist_push','resist_trip'):
   self.assertEqual(self.e.skill_roll(self.a,'육상',fixed=[1]*4,skill_context=self.context(purpose)).total,6)
  out=self.e.opposed_check(self.b,'육상',self.a,'육상',challenger_options={'fixed':[1,1,2,2]},defender_options={'fixed':[1]*4,'skill_context':self.context('resist_push')})
  self.assertFalse(out)
 def test_base_and_talent_stack_once_and_native_common_action_uses_result(self):
  self.talent('grassland','mountain');self.env('grassland')
  out=self.e.common_action(self.a,'통찰',7,mode='skill',fixed=[1]*3,skill_context=self.context('distant_object'))
  self.assertTrue(out.check.passed);self.assertEqual(out.check.total,7)
 def test_skill_monkey_retains_terrain_talent_bonus_once_in_final_check(self):
  self.talent('grassland','mountain');self.env('grassland');self.a.spec['feats'].append(SF.MONKEY)
  out=self.e.skill_roll(self.a,'통찰',fixed=[1]*3,skill_context=self.context('distant_object'),roll_id='r',feature=SF.MONKEY,feature_options={'decision':lambda first:True,'reroll_faces':[2]*3})
  self.assertEqual(SF.event(self.e,self.a,'r').first.total,7);self.assertEqual(out.total,12)
 def test_observed_skill_context_cannot_be_rewritten(self):
  self.talent('grassland','mountain');self.env('urban');self.a.spec['feats'].append(SF.MONKEY)
  args=dict(fixed=[1]*3,roll_id='r',feature=SF.MONKEY,feature_options={'decision':lambda first:'invalid'})
  with self.assertRaises(ValueError):self.e.skill_roll(self.a,'통찰',skill_context=self.context('distant_object'),**args)
  args['feature_options']={'decision':lambda first:False}
  with self.assertRaises(ValueError):self.e.skill_roll(self.a,'통찰',skill_context=self.context('balance'),**args)
 def test_cave_light_is_source_specific_and_talents_work_outside_habitat(self):
  self.talent('cave','grassland');self.env('urban',light='low_light');self.assertEqual(V.vision(self.e,self.a),('none',False))
  self.env('urban',light='complete_darkness');self.assertEqual(V.vision(self.e,self.a),('ordinary',True))
  self.a.conditions.add('실명');self.env('urban');self.assertEqual(V.vision(self.e,self.a),('ordinary',False))
  with self.assertRaises(ValueError):V.blinded_plan(self.e,self.a,{'skill':'생존','fixed':[1]*6})
 def test_real_blinded_shift_survival_dc10_equality_moves_and_spends_once(self):
  self.talent('cave','grassland');self.env('urban',light='complete_darkness');self.movement()
  self.e.approach(self.a,self.b,blindness_options=self.opts(faces=[1,1,2,2,2,2]))
  self.assertEqual(self.a.pos,(4,0));self.assertNotIn('넘어짐',self.a.conditions);self.assertEqual(self.a.budget['shift'],0)
  self.assertEqual(self.a.spec['_survivalist_shift']['checks'][0]['result'].total,10)
 def test_real_failed_blinded_shift_stops_tripped_on_actual_hazard(self):
  self.talent('cave','grassland');self.env('urban',light='complete_darkness');self.movement()
  self.e.approach(self.a,self.b,blindness_options=self.opts(faces=[1]*6))
  self.assertEqual(self.a.pos,(1,0));self.assertIn('넘어짐',self.a.conditions);self.assertEqual(self.a.budget['shift'],0)
 def test_low_light_cave_and_clear_actual_path_do_not_draw_phantom_dice(self):
  self.talent('cave','grassland');self.env('urban',light='low_light');self.movement();state=self.e.rng.getstate()
  self.e.approach(self.a,self.b);self.assertEqual(self.e.rng.getstate(),state);self.assertEqual(self.a.pos,(4,0))
  self.movement();self.env('urban',light='complete_darkness');self.e.grid.rough.clear();state=self.e.rng.getstate()
  self.e.approach(self.a,self.b);self.assertEqual(self.e.rng.getstate(),state)
 def test_missing_frequency_and_wrong_substitution_reject_before_shift_cost(self):
  self.talent('cave','grassland');self.env('urban',light='complete_darkness');self.movement();before=dict(self.a.budget)
  opts=self.opts();opts.pop('frequency')
  with self.assertRaises(ValueError):self.e.approach(self.a,self.b,blindness_options=opts)
  self.assertEqual(self.a.budget,before)
  opts=self.opts(skill='육상',faces=[2]*4)
  with self.assertRaises(ValueError):self.e.approach(self.a,self.b,blindness_options=opts)
  self.assertEqual(self.a.budget,before)
 def test_total_blindness_without_cave_is_explicit_pre_cost_boundary(self):
  self.master('cave');self.env('cave',light='complete_darkness');self.movement();before=dict(self.a.budget)
  with self.assertRaises(ValueError):self.e.approach(self.a,self.b)
  self.assertEqual(self.a.budget,before)
 def test_blinded_skill_monkey_invalid_later_decision_resumes_same_shift(self):
  self.talent('cave','grassland');self.env('urban',light='complete_darkness');self.movement();self.a.spec['feats'].append(SF.MONKEY)
  opts=self.opts(faces=[1]*6,roll_id='walk-roll',feature=SF.MONKEY,feature_options={'decision':lambda first:'bad'})
  with self.assertRaises(ValueError):self.e.approach(self.a,self.b,blindness_options=opts)
  self.assertEqual(self.a.budget['shift'],0);first=SF.event(self.e,self.a,'walk-roll').first
  opts['check_options'][0]['feature_options']={'decision':lambda first:True,'reroll_faces':[2]*6}
  self.e.approach(self.a,self.b,blindness_options=opts)
  self.assertEqual(self.a.pos,(4,0));self.assertEqual(SF.event(self.e,self.a,'walk-roll').first,first)
  self.assertEqual(self.a._action_history.count('shift'),1);self.assertEqual(self.a._action_history.count('free'),1)
 def test_ordinary_one_metre_shift_triggers_actual_aoo_before_departure(self):
  self.a.spec['classes']=[];self.a.pos=(1,0);self.a.side='players';self.a.spec['movement']={'land':1}
  self.b.pos=(0,0);self.b.side='enemies';self.b.accuracy_stage=6
  target=Combatant(self.r,dict(self.b.spec,id='trainer/goal',name='Goal',pos=(3,0)));target.side='players'
  self.e.everyone=[self.a,self.b,target];self.e.grid=Grid(4,1);TURN.reset_budget(self.e,self.a);before=self.a.hp
  with patch.object(self.e,'d20',return_value=20):self.e.approach(self.a,target)
  self.assertEqual(self.a.pos,(2,0));self.assertTrue(self.b.aoo_used);self.assertLess(self.a.hp,before);self.assertEqual(self.a.budget['shift'],0)
 def test_explicit_disengage_one_metre_spends_shift_without_aoo(self):
  self.a.spec['classes']=[];self.a.pos=(1,0);self.a.side='players';self.b.pos=(0,0);self.b.side='enemies'
  self.e.grid=Grid(4,1);self.e.start_round([self.a,self.b]);self.e.start_of_turn(self.a);before=self.a.hp
  self.e.disengage(self.a,(2,0))
  self.assertEqual(self.a.pos,(2,0));self.assertFalse(getattr(self.b,'aoo_used',False));self.assertEqual(self.a.hp,before);self.assertEqual(self.a.budget['shift'],0)
 def test_blindsense_and_darkvision_do_not_receive_phantom_darkness_checks(self):
  self.master('cave');self.env('cave',light='complete_darkness');self.movement();self.a.spec['capabilities']=['Darkvision']
  before=self.e.rng.getstate();self.e.approach(self.a,self.b);self.assertEqual(self.a.pos,(4,0));self.assertEqual(self.e.rng.getstate(),before)
  self.a.conditions.add('실명');self.a.spec['capabilities']=['Blindsense'];self.assertEqual(V.vision(self.e,self.a),('none',False))
 def test_per_cell_policy_only_checks_reached_hazard_cells(self):
  self.talent('cave','grassland');self.env('urban',light='complete_darkness');self.movement();opts=self.opts(faces=[1]*6)
  opts['frequency']='each_hazard_cell';opts['check_options'].append({'skill':'생존','fixed':[6]*6})
  self.e.approach(self.a,self.b,blindness_options=opts)
  self.assertEqual(len(self.a.spec['_survivalist_shift']['checks']),1);self.assertEqual(self.a.pos,(1,0))
 def test_path_dependent_option_count_rejects_before_shift_cost(self):
  self.talent('cave','grassland');self.env('urban',light='complete_darkness');self.movement();opts=self.opts();opts['frequency']='each_hazard_cell';before=dict(self.a.budget)
  with self.assertRaises(ValueError):self.e.approach(self.a,self.b,blindness_options=opts)
  self.assertEqual(self.a.budget,before);self.assertEqual(self.a.pos,(0,0))
 def test_later_hazard_choice_error_and_snapshot_resume_prior_world_movement(self):
  self.talent('cave','grassland');self.env('urban',light='complete_darkness');self.movement();self.a.spec['feats'].append(SF.MONKEY)
  opts=self.opts(faces=[2]*6,roll_id='cell1',feature=SF.MONKEY,feature_options={'decision':lambda first:False})
  opts['frequency']='each_hazard_cell';opts['check_options'].append({'skill':'생존','fixed':[1]*6,'roll_id':'cell2','feature':SF.MONKEY,'feature_options':{'decision':lambda first:'bad'}})
  with self.assertRaises(ValueError):self.e.approach(self.a,self.b,blindness_options=opts)
  self.assertEqual(self.a.pos,(1,0));self.assertEqual(len(self.a.spec['_survivalist_shift']['checks']),1)
  first=SF.event(self.e,self.a,'cell1').first;second=SF.event(self.e,self.a,'cell2').first
  self.e.gm.everyone=self.e.everyone;self.e.gm.snapshot('pending-blind')
  opts['check_options'][1]['feature_options']={'decision':lambda first:True,'reroll_faces':[2]*6}
  self.e.approach(self.a,self.b,blindness_options=opts);self.assertEqual(self.a.pos,(4,0));self.assertEqual(self.a._action_history.count('shift'),1)
  self.e.gm.restore('pending-blind');self.assertEqual(self.a.pos,(1,0));self.assertEqual(SF.event(self.e,self.a,'cell1').first,first);self.assertEqual(SF.event(self.e,self.a,'cell2').first,second)
  self.e.approach(self.a,self.b,blindness_options=opts);self.assertEqual(self.a.pos,(4,0));self.assertEqual(self.a._action_history.count('shift'),1);self.assertEqual(self.a._action_history.count('free'),1)
 def test_aoo_knockout_prevents_unreached_blinded_skill_check(self):
  self.talent('cave','grassland');self.env('urban',light='complete_darkness');self.a.pos=(1,0);self.a.side='players';self.a.hp=1
  self.b.pos=(0,0);self.b.side='enemies';self.b.accuracy_stage=6
  target=Combatant(self.r,dict(self.b.spec,id='trainer/goal',name='Goal',pos=(4,0)));target.side='players'
  self.e.everyone=[self.a,self.b,target];self.e.grid=Grid(5,1,rough={(2,0)});TURN.reset_budget(self.e,self.a)
  opts=self.opts(roll_id='unreached')
  with patch.object(self.e,'d20',return_value=20):self.e.approach(self.a,target,blindness_options=opts)
  self.assertTrue(self.a.fainted);self.assertEqual(self.a.pos,(1,0));self.assertNotIn('unreached',self.e._ap_rolls);self.assertFalse(self.a.spec['_survivalist_shift']['checks'])
 def test_native_push_and_trip_defender_receives_surefooted_without_caller_bonus(self):
  for maneuver,skill in [('push','육상'),('trip','곡예')]:
   self.setUp();self.talent('grassland','mountain');self.env('urban')
   self.a.pos=(2,0);self.b.pos=(1,0);self.a.side='defender';self.b.side='attacker';self.b.spec['skills'][skill]=4
   self.b.spec['movement']={'land':6,'power':4};self.a.spec['weight_kg']=30
   self.e.grid=Grid(5,1);self.e.begin_encounter(self.e.everyone);self.e.start_round(self.e.everyone);self.e.start_of_turn(self.b)
   result=getattr(self.e,maneuver)(self.b,self.a,challenger_skill=skill,defender_skill=skill,fixed_accuracy=20,challenger_options={'fixed':[1,1,2,2]},defender_options={'fixed':[1]*4})
   self.assertFalse(result);self.assertEqual(self.a.pos,(2,0));self.assertNotIn('넘어짐',self.a.conditions);self.assertEqual(self.b.budget['standard'],0)
   self.assertTrue(any('수비 측 승' in line for line in self.e.log_lines))
 def test_fixed_source_snapshot_and_complete_quoted_scope_unchanged(self):
  row=next(r for r in json.loads((ROOT/'data/verification/category3-register.json').read_text(encoding='utf-8'))['entries'] if r['id']=='C3-EX-072')
  self.assertEqual(row['scope_sha256'],'33d9bd7b2a70594aebf0ee2e3973503119704f3ee00f185abf4a1b7469cdfde9')
  for anchor in row['source_snapshot']['source_anchors']:
   lines=(ROOT/anchor['file']).read_text(encoding='utf-8-sig').splitlines();excerpt='\n'.join(lines[anchor['start_line']-1:anchor['end_line']])
   self.assertEqual(excerpt,anchor['excerpt']);self.assertEqual(hashlib.sha256(excerpt.encode()).hexdigest(),anchor['excerpt_sha256'])
 def test_source_exclusion_rejects_before_rng(self):
  self.master('cave');self.env('cave');self.r.ruleset=RuleFilter({'sources':['core'],'exclude_units':[V.SURVIVALIST]});self.r._apply_ruleset();state=self.e.rng.getstate()
  try:
   with self.assertRaises(ExcludedRuleSelection):self.e.skill_roll(self.a,'생존')
   self.assertEqual(self.e.rng.getstate(),state)
  finally:self.r.ruleset=RuleFilter({});self.r._apply_ruleset()

if __name__=='__main__':
 class Result(unittest.TextTestResult):
  def __init__(self,*a,**kw):super().__init__(*a,**kw);self.rows=[]
  def addSuccess(self,t):super().addSuccess(t);self.rows.append({'id':t._testMethodName,'status':'pass'})
  def addFailure(self,t,e):super().addFailure(t,e);self.rows.append({'id':t._testMethodName,'status':'fail'})
  def addError(self,t,e):super().addError(t,e);self.rows.append({'id':t._testMethodName,'status':'error'})
 result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
 paths=sorted(str(p.relative_to(ROOT)).replace('\\','/') for p in (ROOT/'engine').glob('*.py'))+['input/ch04-trainer-classes.md','input/ch07-combat.md','tools/test_category3_survivalist.py','data/skill-check-policy.json','data/adjudication-guidance.json']
 paths += ['engine/campaign_rewards.py', 'engine/league_consequences.py', 'data/campaign-reward-policy.json']
 paths += ['engine/pokemon_understanding.py', 'engine/regional_pokemon.py', 'engine/source_context.py']
 paths += ['engine/blessing_skill_features.py', 'engine/combat_precision_features.py', 'engine/pokemon_intelligence.py', 'engine/pokemon_party.py', 'engine/pokemon_teaching.py', 'data/pokemon-machines.json']

 paths += ['engine/arithmetic.py', 'engine/arithmetic_policy.py', 'engine/effect_contracts.py', 'engine/effect_lifetimes.py', 'engine/maneuver_grants.py', 'engine/move_activation.py', 'engine/native_rule_policy.py', 'data/native-rule-policy.json']

 paths += ['engine/action_lifecycle.py', 'engine/action_metadata.py', 'engine/action_points.py', 'engine/adjudication_guidance.py', 'engine/ap_roll_bonus.py', 'engine/bandages.py', 'engine/bound_ap.py', 'engine/builder.py', 'engine/capability_actions.py', 'engine/combat_maneuvers.py', 'engine/combat_social_edges.py', 'engine/combat_stage_sources.py', 'engine/combat_timing.py', 'engine/common_action_checks.py', 'engine/common_checks.py', 'engine/contest.py', 'engine/contest_features.py', 'engine/context_actions.py', 'engine/crafting_activities.py', 'engine/custom_species.py', 'engine/damage_reactions.py', 'engine/demo_rulings.py', 'engine/downtime.py', 'engine/effects.py', 'engine/effects_ext.py', 'engine/elemental_connection.py', 'engine/encounter.py', 'engine/enduring_awareness.py', 'engine/engine.py', 'engine/environmental_effects.py', 'engine/focus_tasks.py', 'engine/food_effects.py', 'engine/frequency.py', 'engine/gm_console.py', 'engine/gm_state.py', 'engine/grid.py', 'engine/heavy_injury_adapter.py', 'engine/heavy_injury_kernel.py', 'engine/heavy_standard_adapter.py', 'engine/initiative.py', 'engine/injury_recovery.py', 'engine/items.py', 'engine/jump_actions.py', 'engine/league_agenda.py', 'engine/league_runtime.py', 'engine/life.py', 'engine/maneuver_edges.py', 'engine/movement_actions.py', 'engine/net_capsule.py', 'engine/observed_resolution.py', 'engine/passive_event_profiles.py', 'engine/passive_events.py', 'engine/physical_limits.py', 'engine/physics_maneuvers.py', 'engine/pokemon_activities.py', 'engine/pokemon_requests.py', 'engine/precise_actions.py', 'engine/researcher_features.py', 'engine/resolution_transaction.py', 'engine/rest_intervals.py', 'engine/restorative_items.py', 'engine/root_admission.py', 'engine/root_children.py', 'engine/root_common_checks.py', 'engine/root_common_engine.py', 'engine/root_inputs.py', 'engine/root_machine.py', 'engine/root_resolution.py', 'engine/root_scheduler.py', 'engine/ruleset.py', 'engine/rulings.py', 'engine/skill_feature_actions.py', 'engine/skill_maneuver_actions.py', 'engine/skill_modifiers.py', 'engine/skill_stunts.py', 'engine/skill_targets.py', 'engine/survivalist_features.py', 'engine/temporary_hp.py', 'engine/test_builder.py', 'engine/test_contest.py', 'engine/test_downtime.py', 'engine/test_effects.py', 'engine/test_gm_state.py', 'engine/test_grid.py', 'engine/test_items.py', 'engine/test_maintenance.py', 'engine/test_playthrough.py', 'engine/test_rules.py', 'engine/test_ruleset.py', 'engine/test_rulings.py', 'engine/test_turn.py', 'engine/trainer_capabilities.py', 'engine/turn.py', 'engine/weapon_actions.py', 'engine/wild_equipment.py', 'data/content-source-identities.json', 'data/context-check-policy.json', 'data/skill-check-policy.json', 'data/adjudication-guidance.json', 'data/rulesets.json']
 report={'generated_at':datetime.now(timezone.utc).isoformat(),'successful':result.wasSuccessful(),'scope':['C3-EX-072'],'completion_scopes':['C3-EX-072'],'partial_scopes':[],'source_scope_sha256':'33d9bd7b2a70594aebf0ee2e3973503119704f3ee00f185abf4a1b7469cdfde9','results':result.rows,'input_hashes':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}}
 (ROOT/'output/category3-survivalist-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 raise SystemExit(not result.wasSuccessful())
